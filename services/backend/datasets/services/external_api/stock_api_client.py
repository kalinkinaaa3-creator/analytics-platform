import base64
import json
import logging
from datetime import date

import requests
from django.conf import settings


logger = logging.getLogger("external_api.stock")


class StockApiError(Exception):
    pass


def build_basic_auth_header(username: str, password: str) -> dict:
    user_pass = f"{username}:{password}".encode("utf-8")
    auth_header = base64.b64encode(user_pass).decode("ascii")

    return {
        "Authorization": f"Basic {auth_header}",
    }


def fetch_stock_api_rows(load_date: date) -> list[dict]:
    if not settings.STOCK_API_URL:
        raise StockApiError("STOCK_API_URL is empty")

    if not settings.STOCK_API_USERNAME or not settings.STOCK_API_PASSWORD:
        raise StockApiError(
            "STOCK_API_USERNAME and STOCK_API_PASSWORD are required"
        )

    headers = build_basic_auth_header(
        settings.STOCK_API_USERNAME,
        settings.STOCK_API_PASSWORD,
    )

    params = {
        "Date": load_date.strftime("%Y%m%d"),
    }

    logger.info(
        "Stock API request started: date=%s",
        params["Date"],
    )

    try:
        response = requests.get(
            settings.STOCK_API_URL,
            headers=headers,
            params=params,
            timeout=settings.STOCK_API_TIMEOUT,
        )

        logger.info(
            "Stock API response received: date=%s status_code=%s",
            params["Date"],
            response.status_code,
        )

        response.raise_for_status()

        text = response.content.decode("utf-8-sig")
        data = json.loads(text)

    except Exception as exc:
        logger.exception(
            "Stock API request failed: date=%s",
            params["Date"],
        )
        raise StockApiError(str(exc)) from exc

    if not isinstance(data, list):
        raise StockApiError(
            f"Expected list from Stock API, got {type(data).__name__}"
        )

    logger.info(
        "Stock API JSON parsed: date=%s rows=%s",
        params["Date"],
        len(data),
    )

    return data