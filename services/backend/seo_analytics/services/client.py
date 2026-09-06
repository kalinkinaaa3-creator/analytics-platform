import logging
import hashlib
import json
import time
from urllib.parse import urljoin

import requests
from django.conf import settings
from django.core.cache import cache

from seo_analytics.models import SeoApiRequestLog


logger = logging.getLogger("seo_analytics.metrika")


class MetrikaConfigurationError(RuntimeError):
    pass


class MetrikaApiError(RuntimeError):
    pass


class MetrikaClient:
    cache_prefix = "seo:metrika:v1"
    logger = logger

    def __init__(self, *, progress=None):
        self.token = settings.YANDEX_METRIKA_TOKEN.strip()
        self.counter_id = settings.YANDEX_METRIKA_COUNTER_ID.strip()
        self.base_url = settings.YANDEX_METRIKA_API_URL.rstrip("/") + "/"
        self.timeout = settings.YANDEX_METRIKA_API_TIMEOUT
        self.progress = progress
        if not self.token or not self.counter_id:
            raise MetrikaConfigurationError(
                "Не заданы YANDEX_METRIKA_TOKEN и YANDEX_METRIKA_COUNTER_ID."
            )

    def request(self, endpoint, *, report_key="", **params):
        url = urljoin(self.base_url, endpoint.lstrip("/"))
        request_params = {
            "ids": self.counter_id,
            "lang": "ru",
            "accuracy": "high",
            **params,
        }
        request_params = {
            key: ",".join(str(item) for item in value) if isinstance(value, (list, tuple)) else value
            for key, value in request_params.items()
            if value not in (None, "", [], ())
        }
        safe_params = dict(request_params)
        query_hash = hashlib.sha256(
            json.dumps(
                {"endpoint": endpoint, "params": request_params},
                sort_keys=True,
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        cache_key = f"{self.cache_prefix}:{query_hash}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        started = time.monotonic()
        last_error = ""
        status_code = None

        transient_attempt = 0
        accuracy_levels = ("high", "medium", "low")
        accuracy_index = 0
        while True:
            try:
                response = requests.get(
                    url,
                    headers={"Authorization": f"OAuth {self.token}"},
                    params=request_params,
                    timeout=self.timeout,
                )
                status_code = response.status_code
                if self.progress:
                    self.progress(report_key, status_code)
                if response.status_code == 429 or response.status_code >= 500:
                    response.raise_for_status()
                if response.status_code >= 400:
                    detail = response.text[:1000]
                    normalized_detail = detail.lower()
                    if (
                        response.status_code == 400
                        and accuracy_index < len(accuracy_levels) - 1
                        and (
                            "слишком слож" in normalized_detail
                            or "query is too complex" in normalized_detail
                        )
                    ):
                        accuracy_index += 1
                        request_params["accuracy"] = accuracy_levels[accuracy_index]
                        safe_params = dict(request_params)
                        self.logger.warning(
                            "Metrika query is too complex (%s); retrying with accuracy=%s",
                            report_key,
                            request_params["accuracy"],
                        )
                        continue
                    raise MetrikaApiError(
                        f"Метрика вернула HTTP {response.status_code}: {detail}"
                    )
                payload = response.json()
                self._log(
                    endpoint=endpoint,
                    report_key=report_key,
                    params=safe_params,
                    status_code=status_code,
                    duration_ms=int((time.monotonic() - started) * 1000),
                    payload=payload,
                    success=True,
                )
                cache.set(
                    cache_key,
                    payload,
                    timeout=settings.SEO_METRIKA_QUERY_CACHE_TIMEOUT,
                )
                return payload
            except (requests.RequestException, ValueError, MetrikaApiError) as exc:
                last_error = str(exc)
                if transient_attempt < 2 and (
                    isinstance(exc, requests.RequestException)
                    and (status_code == 429 or status_code is None or status_code >= 500)
                ):
                    transient_attempt += 1
                    time.sleep(1.5 * transient_attempt)
                    continue
                break

        self._log(
            endpoint=endpoint,
            report_key=report_key,
            params=safe_params,
            status_code=status_code,
            duration_ms=int((time.monotonic() - started) * 1000),
            payload={},
            success=False,
            error=last_error,
        )
        self.logger.error("Metrika request failed (%s): %s", report_key, last_error)
        raise MetrikaApiError(last_error or "Не удалось получить данные Метрики.")

    @staticmethod
    def _log(*, endpoint, report_key, params, status_code, duration_ms, payload, success, error=""):
        try:
            SeoApiRequestLog.objects.create(
                endpoint=endpoint,
                report_key=report_key,
                params=params,
                status_code=status_code,
                duration_ms=duration_ms,
                sampled=payload.get("sampled") if payload else None,
                sample_share=payload.get("sample_share") if payload else None,
                data_lag=payload.get("data_lag") if payload else None,
                success=success,
                error=error[:4000],
            )
        except Exception:
            logger.exception("Failed to persist Metrika request log")

    def table(self, *, report_key="", **params):
        return self.request("stat/v1/data", report_key=report_key, **params)

    def table_all(self, *, report_key="", page_size=100000, **params):
        """Download the complete /data result using Metrika's 1-based offset."""
        rows = []
        offset = 1
        page_number = 0
        metadata = {}
        while True:
            page_number += 1
            payload = self.table(
                report_key=f"{report_key}.page-{page_number}",
                **params,
                limit=page_size,
                offset=offset,
            )
            page_rows = payload.get("data") or []
            rows.extend(page_rows)
            metadata = payload
            if len(page_rows) < page_size:
                break
            offset += page_size
        return {
            **metadata,
            "data": rows,
            "total_rows": len(rows),
            "pages_loaded": page_number,
        }

    def goals(self):
        endpoint = f"management/v1/counter/{self.counter_id}/goals"
        url = urljoin(self.base_url, endpoint)
        started = time.monotonic()
        try:
            response = requests.get(
                url,
                headers={"Authorization": f"OAuth {self.token}"},
                params={"lang": "ru"},
                timeout=self.timeout,
            )
            if self.progress:
                self.progress("goals.catalog", response.status_code)
            if response.status_code >= 400:
                raise MetrikaApiError(
                    f"Метрика вернула HTTP {response.status_code}: {response.text[:1000]}"
                )
            payload = response.json()
            self._log(
                endpoint=endpoint,
                report_key="goals.catalog",
                params={"counter_id": self.counter_id},
                status_code=response.status_code,
                duration_ms=int((time.monotonic() - started) * 1000),
                payload=payload,
                success=True,
            )
            return payload.get("goals") or []
        except (requests.RequestException, ValueError, MetrikaApiError) as exc:
            self._log(
                endpoint=endpoint,
                report_key="goals.catalog",
                params={"counter_id": self.counter_id},
                status_code=getattr(locals().get("response"), "status_code", None),
                duration_ms=int((time.monotonic() - started) * 1000),
                payload={},
                success=False,
                error=str(exc),
            )
            raise MetrikaApiError(str(exc)) from exc
