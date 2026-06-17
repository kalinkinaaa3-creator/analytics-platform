import base64
import json
import logging
from datetime import date

import requests
from django.conf import settings


logger = logging.getLogger("external_api.planned_sales")


class PlannedSalesApiError(Exception):
    pass


def build_basic_auth_header(username: str, password: str) -> dict:
    user_pass = f"{username}:{password}".encode("utf-8")
    auth_header = base64.b64encode(user_pass).decode("ascii")

    return {
        "Authorization": f"Basic {auth_header}",
    }


def fetch_planned_sales_api_rows(
    start_date: date,
    end_date: date,
) -> list[dict]:
    if not settings.PLANNED_SALES_API_URL:
        raise PlannedSalesApiError("PLANNED_SALES_API_URL is empty")

    if not settings.PLANNED_SALES_API_USERNAME or not settings.PLANNED_SALES_API_PASSWORD:
        raise PlannedSalesApiError(
            "PLANNED_SALES_API_USERNAME and PLANNED_SALES_API_PASSWORD are required"
        )

    headers = build_basic_auth_header(
        settings.PLANNED_SALES_API_USERNAME,
        settings.PLANNED_SALES_API_PASSWORD,
    )

    params = {
        "DataNach": start_date.strftime("%Y%m%d"),
        "DataKon": end_date.strftime("%Y%m%d"),
    }

    logger.info(
        "PlannedSales API request started: DataNach=%s, DataKon=%s",
        params["DataNach"],
        params["DataKon"],
    )

    try:
        response = requests.get(
            settings.PLANNED_SALES_API_URL,
            headers=headers,
            params=params,
            timeout=settings.PLANNED_SALES_API_TIMEOUT,
        )

        logger.info(
            "PlannedSales API response received: status_code=%s",
            response.status_code,
        )

        response.raise_for_status()

        text = response.content.decode("utf-8-sig")
        data = json.loads(text)

    except Exception as exc:
        logger.exception("PlannedSales API request failed")
        raise PlannedSalesApiError(str(exc)) from exc

    if not isinstance(data, list):
        raise PlannedSalesApiError(
            f"Expected list from PlannedSales API, got {type(data).__name__}"
        )

    logger.info("PlannedSales API JSON parsed: rows=%s", len(data))

    return data