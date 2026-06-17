import logging
import requests

from django.conf import settings


def send_bitrix_message(message: str, logger_name: str = "analytics") -> bool:
    logger = logging.getLogger(logger_name)

    if not settings.ENABLE_BITRIX_NOTIFICATIONS:
        logger.info("Bitrix notification skipped: disabled")
        return False

    if not settings.BITRIX_WEBHOOK_URL or not settings.BITRIX_NOTIFY_USER_ID:
        logger.warning("Bitrix notification skipped: webhook or user_id is empty")
        return False

    url = settings.BITRIX_WEBHOOK_URL.rstrip("/") + "/im.message.add.json"

    payload = {
        "DIALOG_ID": settings.BITRIX_NOTIFY_USER_ID,
        "MESSAGE": message,
    }

    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()

        logger.info("Bitrix notification sent")
        return True

    except Exception as exc:
        logger.exception("Bitrix notification failed: %s", exc)
        return False