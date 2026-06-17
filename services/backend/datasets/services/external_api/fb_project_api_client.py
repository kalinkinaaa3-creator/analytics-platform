import base64
import json
import logging
from datetime import date

import requests
from django.conf import settings


logger = logging.getLogger("external_api.fb_project")


class FBProjectApiError(Exception):
    pass


def build_basic_auth_header(username: str, password: str) -> dict:
    user_pass = f"{username}:{password}".encode("utf-8")
    auth_header = base64.b64encode(user_pass).decode("ascii")

    return {
        "Authorization": f"Basic {auth_header}",
    }


def fetch_fb_project_api_rows(load_date: date | None = None) -> list[dict]:
    load_date = load_date or date.today()

    username = settings.FB_PROJECT_API_USERNAME
    password = settings.FB_PROJECT_API_PASSWORD

    if not username or not password:
        raise FBProjectApiError(
            "FB_PROJECT_API_USERNAME and FB_PROJECT_API_PASSWORD are required"
        )

    headers = build_basic_auth_header(username, password)

    params = {
        "DataTek": load_date.strftime("%Y%m%d"),
    }

    logger.info(
        "FBProject API request started: url=%s, DataTek=%s",
        settings.FB_PROJECT_API_URL,
        params["DataTek"],
    )

    try:
        response = requests.get(
            settings.FB_PROJECT_API_URL,
            headers=headers,
            params=params,
            timeout=settings.FB_PROJECT_API_TIMEOUT,
        )
        response.raise_for_status()

        text = response.content.decode("utf-8-sig")
        data = json.loads(text)

    except Exception as exc:
        logger.exception("FBProject API request failed")
        raise FBProjectApiError(str(exc)) from exc

    if not isinstance(data, list):
        raise FBProjectApiError(
            f"Expected list from FBProject API, got {type(data).__name__}"
        )

    logger.info("FBProject API rows received: %s", len(data))

    return data