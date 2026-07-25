import base64
import json
import logging
from datetime import date

import requests
from django.conf import settings


logger = logging.getLogger("external_api.price")


class PriceApiError(Exception):
    pass


def build_basic_auth_header(username: str, password: str) -> dict:
    user_pass = f"{username}:{password}".encode("utf-8")
    auth_header = base64.b64encode(user_pass).decode("ascii")

    return {
        "Authorization": f"Basic {auth_header}",
    }


def fetch_price_api_rows(load_date: date) -> list[dict]:
    if not settings.PRICE_API_URL:
        raise PriceApiError("PRICE_API_URL is empty")

    if not settings.PRICE_API_USERNAME or not settings.PRICE_API_PASSWORD:
        raise PriceApiError(
            "PRICE_API_USERNAME and PRICE_API_PASSWORD are required"
        )

    headers = build_basic_auth_header(
        settings.PRICE_API_USERNAME,
        settings.PRICE_API_PASSWORD,
    )

    params = {
        "date": load_date.strftime("%Y%m%d"),
    }

    logger.info(
        "Price API request started: date=%s",
        params["date"],
    )

    try:
        response = requests.get(
            settings.PRICE_API_URL,
            headers=headers,
            params=params,
            timeout=settings.PRICE_API_TIMEOUT,
        )

        logger.info(
            "Price API response received: date=%s status_code=%s",
            params["date"],
            response.status_code,
        )

        response.raise_for_status()

        text = response.content.decode("utf-8-sig")
        data = json.loads(text)

    except Exception as exc:
        logger.exception(
            "Price API request failed: date=%s",
            params["date"],
        )
        raise PriceApiError(str(exc)) from exc

    if not isinstance(data, list):
        raise PriceApiError(
            f"Expected list from Price API, got {type(data).__name__}"
        )

    logger.info(
        "Price API JSON parsed: date=%s rows=%s",
        params["date"],
        len(data),
    )

    return data