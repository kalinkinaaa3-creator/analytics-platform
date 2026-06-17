import base64
import json
import logging
from datetime import date

import requests
from django.conf import settings


logger = logging.getLogger("external_api.fb_accreceiv")


class FBAccreceivApiError(Exception):
    pass


def build_basic_auth_header(username: str, password: str) -> dict:
    user_pass = f"{username}:{password}".encode("utf-8")
    auth_header = base64.b64encode(user_pass).decode("ascii")

    return {
        "Authorization": f"Basic {auth_header}",
    }


def fetch_fb_accreceiv_api_rows(
    date_start: date,
    date_end: date,
) -> list[dict]:
    if not settings.FB_ACCRECEIV_API_URL:
        raise FBAccreceivApiError("FB_ACCRECEIV_API_URL is empty")

    if not settings.FB_ACCRECEIV_API_USERNAME or not settings.FB_ACCRECEIV_API_PASSWORD:
        raise FBAccreceivApiError(
            "FB_ACCRECEIV_API_USERNAME and FB_ACCRECEIV_API_PASSWORD are required"
        )

    headers = build_basic_auth_header(
        settings.FB_ACCRECEIV_API_USERNAME,
        settings.FB_ACCRECEIV_API_PASSWORD,
    )

    params = {
        "date_start": date_start.strftime("%Y%m%d"),
        "date_end": date_end.strftime("%Y%m%d"),
    }

    logger.info(
        "FBAccreceiv API request started: date_start=%s, date_end=%s",
        params["date_start"],
        params["date_end"],
    )

    try:
        response = requests.get(
            settings.FB_ACCRECEIV_API_URL,
            headers=headers,
            params=params,
            timeout=settings.FB_ACCRECEIV_API_TIMEOUT,
            verify=False,
        )

        logger.info(
            "FBAccreceiv API response received: status_code=%s",
            response.status_code,
        )

        response.raise_for_status()

        text = response.content.decode("utf-8-sig")
        data = json.loads(text)

    except Exception as exc:
        logger.exception("FBAccreceiv API request failed")
        raise FBAccreceivApiError(str(exc)) from exc

    if not isinstance(data, list):
        raise FBAccreceivApiError(
            f"Expected list from FBAccreceiv API, got {type(data).__name__}"
        )

    logger.info("FBAccreceiv API JSON parsed: rows=%s", len(data))

    return data