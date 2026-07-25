import base64
import json
import logging

import requests
from django.conf import settings


logger = logging.getLogger("external_api.nomenclature")


class NomenclatureApiError(Exception):
    pass


def build_basic_auth_header(username: str, password: str) -> dict:
    user_pass = f"{username}:{password}".encode("utf-8")
    auth_header = base64.b64encode(user_pass).decode("ascii")

    return {
        "Authorization": f"Basic {auth_header}",
    }


def fetch_nomenclature_api_rows() -> list[dict]:
    if not settings.NOMENCLATURE_API_URL:
        raise NomenclatureApiError("NOMENCLATURE_API_URL is empty")

    if (
        not settings.NOMENCLATURE_API_USERNAME
        or not settings.NOMENCLATURE_API_PASSWORD
    ):
        raise NomenclatureApiError(
            "NOMENCLATURE_API_USERNAME and NOMENCLATURE_API_PASSWORD are required"
        )

    headers = build_basic_auth_header(
        settings.NOMENCLATURE_API_USERNAME,
        settings.NOMENCLATURE_API_PASSWORD,
    )

    logger.info("Nomenclature API request started")

    try:
        response = requests.get(
            settings.NOMENCLATURE_API_URL,
            headers=headers,
            timeout=settings.NOMENCLATURE_API_TIMEOUT,
        )

        logger.info(
            "Nomenclature API response received: status_code=%s",
            response.status_code,
        )

        response.raise_for_status()

        text = response.content.decode("utf-8-sig")
        data = json.loads(text)

    except Exception as exc:
        logger.exception("Nomenclature API request failed")
        raise NomenclatureApiError(str(exc)) from exc

    if not isinstance(data, list):
        raise NomenclatureApiError(
            f"Expected list from Nomenclature API, got {type(data).__name__}"
        )

    logger.info(
        "Nomenclature API JSON parsed: rows=%s",
        len(data),
    )

    return data