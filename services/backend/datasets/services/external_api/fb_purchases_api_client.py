import base64
import json
import logging
from datetime import date

import requests
from django.conf import settings


logger = logging.getLogger("external_api.fb_purchases")


class FBPurchasesApiError(Exception):
    pass


def build_basic_auth_header(username: str, password: str) -> dict:
    user_pass = f"{username}:{password}".encode("utf-8")
    auth_header = base64.b64encode(user_pass).decode("ascii")

    return {
        "Authorization": f"Basic {auth_header}",
    }


def fetch_fb_purchases_api_rows(
    start_date: date,
    end_date: date,
) -> list[dict]:
    if not settings.FB_PURCHASES_API_URL:
        raise FBPurchasesApiError("FB_PURCHASES_API_URL is empty")

    if not settings.FB_PURCHASES_API_USERNAME or not settings.FB_PURCHASES_API_PASSWORD:
        raise FBPurchasesApiError(
            "FB_PURCHASES_API_USERNAME and FB_PURCHASES_API_PASSWORD are required"
        )

    headers = build_basic_auth_header(
        settings.FB_PURCHASES_API_USERNAME,
        settings.FB_PURCHASES_API_PASSWORD,
    )

    params = {
        "DateN": start_date.strftime("%Y%m%d"),
        "DateK": end_date.strftime("%Y%m%d"),
    }

    logger.info(
        "FBPurchases API request started: DateN=%s, DateK=%s",
        params["DateN"],
        params["DateK"],
    )

    try:
        response = requests.get(
            settings.FB_PURCHASES_API_URL,
            headers=headers,
            params=params,
            timeout=settings.FB_PURCHASES_API_TIMEOUT,
            verify=False,
        )

        logger.info(
            "FBPurchases API response received: status_code=%s",
            response.status_code,
        )

        response.raise_for_status()

        text = response.content.decode("utf-8-sig")
        data = json.loads(text)

    except Exception as exc:
        logger.exception("FBPurchases API request failed")
        raise FBPurchasesApiError(str(exc)) from exc

    if not isinstance(data, list):
        raise FBPurchasesApiError(
            f"Expected list from FBPurchases API, got {type(data).__name__}"
        )

    logger.info("FBPurchases API JSON parsed: rows=%s", len(data))

    return data