import logging
import time

import requests
from django.conf import settings


logger = logging.getLogger("external_api.yd_wordstat")


class YdWordstatApiError(Exception):
    pass


class YdWordstatQuotaExceeded(YdWordstatApiError):
    pass


def get_yd_wordstat_headers():
    if not settings.YD_WORDSTAT_API_TOKEN:
        raise YdWordstatApiError("YD_WORDSTAT_API_TOKEN is empty")

    return {
        "Authorization": f"Bearer {settings.YD_WORDSTAT_API_TOKEN}",
        "Accept-Language": "ru",
        "Content-Type": "application/json",
    }


def extract_daily_limit_remaining(data: dict):
    """
    Поддерживаем оба возможных формата:
    1. {"userInfo": {"dailyLimitRemaining": 123}}
    2. {"dailyLimitRemaining": 123}
    """

    if not isinstance(data, dict):
        return None

    user_info = data.get("userInfo") or {}

    if isinstance(user_info, dict):
        daily_limit_remaining = user_info.get("dailyLimitRemaining")

        if daily_limit_remaining is not None:
            return daily_limit_remaining

    return data.get("dailyLimitRemaining")


def fetch_yd_wordstat_user_info():
    url = "https://api.wordstat.yandex.net/v1/userInfo"

    try:
        response = requests.post(
            url,
            headers=get_yd_wordstat_headers(),
            timeout=settings.YD_WORDSTAT_API_TIMEOUT,
        )

        logger.info(
            "YD Wordstat userInfo response received: status_code=%s",
            response.status_code,
        )

        response.raise_for_status()
        data = response.json()

    except Exception as exc:
        logger.exception("YD Wordstat userInfo request failed")
        raise YdWordstatApiError(str(exc)) from exc

    daily_limit_remaining = extract_daily_limit_remaining(data)

    logger.info(
        "YD Wordstat quota checked: dailyLimitRemaining=%s",
        daily_limit_remaining,
    )

    return {
        "raw": data,
        "daily_limit_remaining": daily_limit_remaining,
    }


def ensure_yd_wordstat_quota_available():
    quota = fetch_yd_wordstat_user_info()
    remaining = quota["daily_limit_remaining"]

    if remaining is None:
        logger.warning(
            "YD Wordstat quota value is absent in userInfo response. Continue without quota pre-check."
        )
        return quota

    try:
        remaining_int = int(remaining)
    except Exception:
        logger.warning(
            "YD Wordstat quota value is not integer: dailyLimitRemaining=%s. Continue without quota pre-check.",
            remaining,
        )
        return quota

    if remaining_int <= 0:
        raise YdWordstatQuotaExceeded("YD Wordstat daily quota exhausted")

    return quota


def fetch_yd_wordstat_regions_tree():
    url = "https://api.wordstat.yandex.net/v1/getRegionsTree"

    logger.info("YD Wordstat regions tree request started")

    try:
        ensure_yd_wordstat_quota_available()

        response = requests.post(
            url,
            headers=get_yd_wordstat_headers(),
            timeout=settings.YD_WORDSTAT_API_TIMEOUT,
        )

        logger.info(
            "YD Wordstat regions tree response received: status_code=%s",
            response.status_code,
        )

        response.raise_for_status()
        data = response.json()

    except YdWordstatQuotaExceeded:
        raise
    except Exception as exc:
        logger.exception("YD Wordstat regions tree request failed")
        raise YdWordstatApiError(str(exc)) from exc

    return data


def fetch_yd_wordstat_dynamics(
    phrase: str,
    date_start,
    date_finish,
    devices: list[str] | None = None,
    regions: list[int] | None = None,
):
    ensure_yd_wordstat_quota_available()

    url = "https://api.wordstat.yandex.net/v1/dynamics"

    body = {
        "phrase": str(phrase),
        "period": "monthly",
        "fromDate": str(date_start),
        "toDate": str(date_finish),
    }

    if devices:
        body["devices"] = devices

    if regions:
        body["regions"] = regions

    logger.info(
        "YD Wordstat dynamics request started: phrase=%s, date_start=%s, date_finish=%s, devices=%s, regions=%s",
        phrase,
        date_start,
        date_finish,
        devices,
        regions,
    )

    try:
        time.sleep(1)

        response = requests.post(
            url,
            headers=get_yd_wordstat_headers(),
            json=body,
            timeout=settings.YD_WORDSTAT_API_TIMEOUT,
        )

        logger.info(
            "YD Wordstat dynamics response received: status_code=%s, phrase=%s",
            response.status_code,
            phrase,
        )

        response.raise_for_status()
        data = response.json()

    except YdWordstatQuotaExceeded:
        raise
    except Exception as exc:
        logger.exception("YD Wordstat dynamics request failed")
        raise YdWordstatApiError(str(exc)) from exc

    return data