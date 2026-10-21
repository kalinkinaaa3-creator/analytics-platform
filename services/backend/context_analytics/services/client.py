import csv
import io
import time

import requests
from django.conf import settings

from context_analytics.models import ContextApiRequestLog


class DirectClient:
    ATTRIBUTION = "LSCCD"

    # Яндекс сообщил:
    # "Данный метод можно запрашивать не чаще чем 1 раз в 10 секунд".
    # Добавляем небольшой запас.
    REPORT_MIN_INTERVAL = 11.0

    # 8 попыток может быть мало, если отчёт долго формируется.
    REPORT_MAX_ATTEMPTS = 30

    def __init__(self):
        self.token = settings.YANDEX_DIRECT_TOKEN.strip()
        self.base_url = settings.YANDEX_DIRECT_API_URL.rstrip("/")
        self.timeout = settings.YANDEX_DIRECT_API_TIMEOUT
        self.client_login = settings.YANDEX_DIRECT_CLIENT_LOGIN.strip()

        # Время последнего обращения к /reports
        self._last_report_request_at = 0.0

        if not self.token:
            raise RuntimeError("Не задан YANDEX_DIRECT_TOKEN.")

    def _headers(self, reports=False):
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept-Language": "ru",
        }

        if self.client_login:
            headers["Client-Login"] = self.client_login

        if reports:
            headers.update({
                "processingMode": "auto",
                "skipReportHeader": "true",
                "skipReportSummary": "true",
                "returnMoneyInMicros": "false",
            })
        else:
            headers["Content-Type"] = "application/json; charset=utf-8"

        return headers

    def _wait_before_report_request(self):
        """
        Не отправляем запросы к /reports чаще,
        чем один раз в REPORT_MIN_INTERVAL секунд.
        """
        if not self._last_report_request_at:
            return

        elapsed = time.monotonic() - self._last_report_request_at
        wait_seconds = self.REPORT_MIN_INTERVAL - elapsed

        if wait_seconds > 0:
            time.sleep(wait_seconds)

    def _post_report(self, payload):
        """
        Один запрос к Reports API с соблюдением rate limit.
        """
        self._wait_before_report_request()

        try:
            return requests.post(
                f"{self.base_url}/reports",
                json=payload,
                headers=self._headers(reports=True),
                timeout=self.timeout,
            )
        finally:
            # Фиксируем именно момент обращения к API.
            self._last_report_request_at = time.monotonic()

    def campaigns(self):
        campaigns = []
        offset = 0
        seen_offsets = {offset}

        while True:
            payload = {
                "method": "get",
                "params": {
                    "SelectionCriteria": {},
                    "FieldNames": [
                        "Id",
                        "Name",
                        "Type",
                        "Status",
                        "State",
                        "StartDate",
                    ],
                    "Page": {
                        "Limit": 10000,
                        "Offset": offset,
                    },
                },
            }

            response = requests.post(
                f"{self.base_url}/campaigns",
                json=payload,
                headers=self._headers(),
                timeout=self.timeout,
            )

            response.raise_for_status()

            result = response.json().get("result") or {}
            page = result.get("Campaigns") or []

            campaigns.extend(page)

            limited_by = result.get("LimitedBy")

            if limited_by is None:
                break

            try:
                next_offset = int(limited_by)
            except (TypeError, ValueError) as exc:
                raise RuntimeError(
                    f"Директ вернул некорректный LimitedBy: {limited_by!r}."
                ) from exc

            if (
                not page
                or next_offset <= offset
                or next_offset in seen_offsets
            ):
                raise RuntimeError(
                    "Директ вернул некорректную пагинацию кампаний: "
                    f"offset={offset}, "
                    f"LimitedBy={limited_by!r}, "
                    f"rows={len(page)}."
                )

            seen_offsets.add(next_offset)
            offset = next_offset

        return campaigns

    def report(
        self,
        *,
        report_key,
        date_from,
        date_to,
        fields,
        goals=(),
        progress=None,
    ):
        params = {
            "SelectionCriteria": {
                "DateFrom": str(date_from),
                "DateTo": str(date_to),
            },
            "FieldNames": fields,
            "ReportName": f"context_{report_key}_{time.time_ns()}",
            "ReportType": "CUSTOM_REPORT",
            "DateRangeType": "CUSTOM_DATE",
            "Format": "TSV",
            "IncludeVAT": "YES",
            "IncludeDiscount": "NO",
        }

        if goals:
            params["Goals"] = [str(goal) for goal in goals]
            params["AttributionModels"] = [self.ATTRIBUTION]

        payload = {
            "params": params,
        }

        started = time.monotonic()
        status = None
        error = ""

        try:
            for attempt in range(1, self.REPORT_MAX_ATTEMPTS + 1):
                response = self._post_report(payload)

                status = response.status_code

                if progress:
                    progress(attempt, status)

                # Отчёт готов
                if status == 200:
                    reader = csv.DictReader(
                        io.StringIO(response.text),
                        delimiter="\t",
                    )
                    return list(reader)

                # Отчёт ещё формируется
                if status in {201, 202}:
                    retry_in_raw = response.headers.get("retryIn", "1")

                    try:
                        retry_in = float(retry_in_raw)
                    except (TypeError, ValueError):
                        retry_in = 1.0

                    # Даже если Яндекс написал retryIn=1,
                    # не нарушаем обнаруженный лимит 1 запрос / 10 сек.
                    wait_seconds = max(
                        retry_in,
                        self.REPORT_MIN_INTERVAL,
                    )

                    time.sleep(wait_seconds)
                    continue

                detail = (response.text or "").strip()[:4000]

                # Временная ошибка rate limit
                if status == 400:
                    error_code = None

                    try:
                        body = response.json()
                        error_code = str(
                            (body.get("error") or {}).get(
                                "error_code",
                                "",
                            )
                        )
                    except (ValueError, TypeError, AttributeError):
                        pass

                    if error_code == "56":
                        time.sleep(self.REPORT_MIN_INTERVAL)
                        continue

                # Остальные ошибки считаем реальными ошибками запроса
                raise RuntimeError(
                    f"Direct вернул HTTP {status}: "
                    f"{detail or 'без описания'}"
                )

            raise RuntimeError(
                "Direct не завершил формирование отчёта "
                f"за {self.REPORT_MAX_ATTEMPTS} попыток."
            )

        except Exception as exc:
            error = str(exc)
            raise

        finally:
            ContextApiRequestLog.objects.create(
                endpoint="reports",
                report_key=report_key,
                params={
                    "date_from": str(date_from),
                    "date_to": str(date_to),
                    "fields": fields,
                    "goal_count": len(goals),
                },
                status_code=status,
                duration_ms=int(
                    (time.monotonic() - started) * 1000
                ),
                success=not error,
                error=error[:10000],
            )