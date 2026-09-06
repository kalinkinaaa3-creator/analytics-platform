import logging
import random
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests
from django.conf import settings
from django.db import transaction

from .yd_wordstat_contract import dynamics_body, fingerprint

logger = logging.getLogger("external_api.yd_wordstat")


class YdWordstatSearchApiError(RuntimeError):
    pass


def _headers():
    api_key = settings.YD_WORDSTAT_API_KEY.strip()
    if not api_key:
        raise YdWordstatSearchApiError("YD_WORDSTAT_API_KEY is empty")
    return {"Authorization": f"Api-Key {api_key}", "Content-Type": "application/json"}


def quota_scope():
    return fingerprint(settings.YD_WORDSTAT_FOLDER_ID.strip() or settings.YD_WORDSTAT_API_KEY.strip())


def reserve_request():
    """Reserve an attempt atomically across workers and restarts."""
    from datasets.models import YdWordstatApiQuota

    per_second = settings.YD_WORDSTAT_REQUESTS_PER_SECOND
    per_hour = settings.YD_WORDSTAT_REQUESTS_PER_HOUR
    if min(per_second, per_hour) < 1:
        raise YdWordstatSearchApiError("Wordstat request limits must be positive")
    scope = quota_scope()
    YdWordstatApiQuota.objects.get_or_create(scope=scope)
    while True:
        with transaction.atomic():
            state = YdWordstatApiQuota.objects.select_for_update().get(scope=scope)
            now = time.time()
            history = sorted(stamp for stamp in state.requests if stamp > now - 3600)
            waits = [0, state.blocked_until - now]
            if len(history) >= per_hour:
                waits.append(history[-per_hour] + 3600 - now)
            recent = [stamp for stamp in history if stamp > now - 1]
            if len(recent) >= per_second:
                waits.append(recent[-per_second] + 1 - now)
            wait = max(waits)
            if wait <= 0:
                state.requests = history + [now]
                state.save(update_fields=["requests"])
                return
        logger.info("Wordstat quota wait: %.1f seconds", wait)
        time.sleep(min(wait + 0.05, 60))


def block_quota(seconds):
    from datasets.models import YdWordstatApiQuota

    scope = quota_scope()
    YdWordstatApiQuota.objects.get_or_create(scope=scope)
    with transaction.atomic():
        state = YdWordstatApiQuota.objects.select_for_update().get(scope=scope)
        state.blocked_until = max(state.blocked_until, time.time() + seconds)
        state.save(update_fields=["blocked_until"])


def retry_after(response, default):
    value = response.headers.get("Retry-After", "")
    try:
        seconds = float(value)
    except ValueError:
        try:
            seconds = (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            return default
    return max(1, seconds)


def _request(method, body, *, statistical=False):
    headers = _headers()
    base_url = settings.YD_WORDSTAT_API_BASE_URL.rstrip("/")
    if base_url != "https://searchapi.api.cloud.yandex.net/v2/wordstat":
        raise YdWordstatSearchApiError("YD_WORDSTAT_API_BASE_URL must be the Wordstat v2 HTTPS endpoint")
    attempts = settings.YD_WORDSTAT_API_MAX_ATTEMPTS
    if attempts < 1:
        raise YdWordstatSearchApiError("YD_WORDSTAT_API_MAX_ATTEMPTS must be positive")
    for attempt in range(attempts):
        if statistical:
            reserve_request()
        backoff = min(60, 2 ** attempt) + random.random()
        try:
            response = requests.post(
                f"{base_url}/{method}", headers=headers, json=body,
                timeout=(settings.YD_WORDSTAT_API_CONNECT_TIMEOUT, settings.YD_WORDSTAT_API_TIMEOUT),
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            if attempt == attempts - 1:
                raise YdWordstatSearchApiError("Wordstat network request failed after retries") from exc
            time.sleep(backoff)
            continue
        if response.status_code == 200:
            try:
                data = response.json()
            except ValueError as exc:
                raise YdWordstatSearchApiError("Wordstat returned invalid JSON") from exc
            if not isinstance(data, dict):
                raise YdWordstatSearchApiError("Wordstat returned a non-object response")
            return data
        status = response.status_code
        request_id = response.headers.get("x-request-id") or response.headers.get("x-server-trace-id", "")
        # Response bodies may echo authentication or request data.
        message = f"Wordstat HTTP {status}; request_id={request_id}"
        if status == 429 and statistical:
            block_quota(retry_after(response, 3600))
        if status not in (429, 500, 502, 503, 504) or attempt == attempts - 1:
            raise YdWordstatSearchApiError(message)
        logger.warning("%s; retry %s/%s", message, attempt + 1, attempts)
        if status != 429 or not statistical:
            remaining = retry_after(response, backoff)
            while remaining > 0:
                pause = min(remaining, 60)
                time.sleep(pause)
                remaining -= pause
    raise YdWordstatSearchApiError("Wordstat request attempts exhausted")


def fetch_regions_tree(*, folder_id=None):
    body = {}
    folder_id = (settings.YD_WORDSTAT_FOLDER_ID if folder_id is None else folder_id).strip()
    if folder_id:
        body["folderId"] = folder_id
    data = _request("getRegionsTree", body)
    if not isinstance(data.get("regions"), list) or not data["regions"]:
        raise YdWordstatSearchApiError("Wordstat response has no nonempty regions array")
    return data


def fetch_dynamics(phrase, date_start, date_finish, devices=None, regions=None):
    body = dynamics_body(phrase, date_start, date_finish, devices, regions)
    if settings.YD_WORDSTAT_FOLDER_ID.strip():
        body["folderId"] = settings.YD_WORDSTAT_FOLDER_ID.strip()
    return _request("dynamics", body, statistical=True)
