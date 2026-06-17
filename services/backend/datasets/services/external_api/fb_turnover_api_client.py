import base64
import json
import logging
from datetime import date

import requests
from django.conf import settings


logger = logging.getLogger("external_api.fb_turnover")


class FBTurnoverApiError(Exception):
    pass


def build_basic_auth_header(username: str, password: str) -> dict:
    user_pass = f"{username}:{password}".encode("utf-8")
    auth_header = base64.b64encode(user_pass).decode("ascii")

    return {
        "Authorization": f"Basic {auth_header}",
    }


def fetch_fb_turnover_api_rows(
    date_start: date,
    date_stock: date,
    date_end: date,
) -> list[dict]:
    if not settings.FB_TURNOVER_API_URL:
        raise FBTurnoverApiError("FB_TURNOVER_API_URL is empty")

    if not settings.FB_TURNOVER_API_USERNAME or not settings.FB_TURNOVER_API_PASSWORD:
        raise FBTurnoverApiError(
            "FB_TURNOVER_API_USERNAME and FB_TURNOVER_API_PASSWORD are required"
        )

    headers = build_basic_auth_header(
        settings.FB_TURNOVER_API_USERNAME,
        settings.FB_TURNOVER_API_PASSWORD,
    )

    params = {
        "date_start": date_start.strftime("%Y%m%d"),
        "date_stock": date_stock.strftime("%Y%m%d"),
        "date_end": date_end.strftime("%Y%m%d"),
    }

    logger.info(
        "FBTurnover API request started: date_start=%s, date_stock=%s, date_end=%s",
        params["date_start"],
        params["date_stock"],
        params["date_end"],
    )

    try:
        response = requests.get(
            settings.FB_TURNOVER_API_URL,
            headers=headers,
            params=params,
            timeout=settings.FB_TURNOVER_API_TIMEOUT,
            verify=False,
        )

        logger.info(
            "FBTurnover API response received: status_code=%s",
            response.status_code,
        )

        response.raise_for_status()

        text = response.content.decode("utf-8-sig")
        data = json.loads(text)

    except Exception as exc:
        logger.exception("FBTurnover API request failed")
        raise FBTurnoverApiError(str(exc)) from exc

    if not isinstance(data, list):
        raise FBTurnoverApiError(
            f"Expected list from FBTurnover API, got {type(data).__name__}"
        )

    logger.info("FBTurnover API JSON parsed: rows=%s", len(data))

    return data