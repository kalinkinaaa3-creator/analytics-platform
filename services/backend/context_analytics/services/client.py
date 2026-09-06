import csv
import io
import time

import requests
from django.conf import settings

from context_analytics.models import ContextApiRequestLog


class DirectClient:
    ATTRIBUTION = "LSCCD"

    def __init__(self):
        self.token = settings.YANDEX_DIRECT_TOKEN.strip()
        self.base_url = settings.YANDEX_DIRECT_API_URL.rstrip("/")
        self.timeout = settings.YANDEX_DIRECT_API_TIMEOUT
        self.client_login = settings.YANDEX_DIRECT_CLIENT_LOGIN.strip()
        if not self.token:
            raise RuntimeError("Не задан YANDEX_DIRECT_TOKEN.")

    def _headers(self, reports=False):
        headers = {"Authorization": f"Bearer {self.token}", "Accept-Language": "ru"}
        if self.client_login:
            headers["Client-Login"] = self.client_login
        if reports:
            headers.update({"processingMode": "auto", "skipReportHeader": "true",
                            "skipReportSummary": "true", "returnMoneyInMicros": "false"})
        else:
            headers["Content-Type"] = "application/json; charset=utf-8"
        return headers

    def campaigns(self):
        campaigns = []
        offset = 0
        seen_offsets = {offset}

        while True:
            payload = {"method": "get", "params": {"SelectionCriteria": {},
                       "FieldNames": ["Id", "Name", "Type", "Status", "State", "StartDate"],
                       "Page": {"Limit": 10000, "Offset": offset}}}
            response = requests.post(f"{self.base_url}/campaigns", json=payload,
                                     headers=self._headers(), timeout=self.timeout)
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
            if not page or next_offset <= offset or next_offset in seen_offsets:
                raise RuntimeError(
                    "Директ вернул некорректную пагинацию кампаний: "
                    f"offset={offset}, LimitedBy={limited_by!r}, rows={len(page)}."
                )

            seen_offsets.add(next_offset)
            offset = next_offset

        return campaigns

    def report(self, *, report_key, date_from, date_to, fields, goals=(), progress=None):
        params = {"SelectionCriteria": {"DateFrom": str(date_from), "DateTo": str(date_to)},
                  "FieldNames": fields, "ReportName": f"context_{report_key}_{time.time_ns()}",
                  "ReportType": "CUSTOM_REPORT", "DateRangeType": "CUSTOM_DATE", "Format": "TSV",
                  "IncludeVAT": "YES", "IncludeDiscount": "NO"}
        if goals:
            params["Goals"] = [str(goal) for goal in goals]
            params["AttributionModels"] = [self.ATTRIBUTION]
        payload = {"params": params}
        started = time.monotonic()
        status = None
        error = ""
        try:
            for attempt in range(8):
                response = requests.post(f"{self.base_url}/reports", json=payload,
                                         headers=self._headers(reports=True), timeout=self.timeout)
                status = response.status_code
                if progress:
                    progress(attempt + 1, status)
                if status == 200:
                    reader = csv.DictReader(io.StringIO(response.text), delimiter="\t")
                    return list(reader)
                if status in {201, 202}:
                    time.sleep(min(int(response.headers.get("retryIn", "2")), 15))
                    continue
                detail = (response.text or "").strip()[:4000]
                raise RuntimeError(f"Direct вернул HTTP {status}: {detail or 'без описания'}")
            raise RuntimeError("Direct не завершил формирование отчёта за допустимое число попыток.")
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            ContextApiRequestLog.objects.create(
                endpoint="reports", report_key=report_key,
                params={"date_from": str(date_from), "date_to": str(date_to), "fields": fields,
                        "goal_count": len(goals)}, status_code=status,
                duration_ms=int((time.monotonic() - started) * 1000), success=not error, error=error[:10000],
            )
