import logging
import os
from datetime import datetime

import requests
from django.core.management.base import BaseCommand
from django.db.models import Q

from datasets.models import ParserProductUrl


logger = logging.getLogger("parsers.tara")

EXPECTED_INACTIVE_ERRORS = [
    "HTTP 404: product page not found",
    "missing_from_sitemap",
]


def send_bitrix_message(message: str) -> bool:
    enabled = os.getenv("ENABLE_BITRIX_NOTIFICATIONS", "false").lower() == "true"

    if not enabled:
        logger.info("Bitrix notification skipped: ENABLE_BITRIX_NOTIFICATIONS=false")
        return False

    webhook_url = os.getenv("BITRIX_WEBHOOK_URL")
    user_id = os.getenv("BITRIX_NOTIFY_USER_ID")

    if not webhook_url or not user_id:
        logger.warning("Bitrix notification skipped: webhook or user id is empty")
        return False

    url = webhook_url.rstrip("/") + "/im.notify.system.add.json"

    response = requests.post(
        url,
        json={
            "USER_ID": user_id,
            "MESSAGE": message,
        },
        timeout=30,
    )

    response.raise_for_status()

    logger.info("Bitrix notification sent")

    return True


class Command(BaseCommand):
    help = "Report Tara parser result to logs and Bitrix"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=30,
            help="How many problem URLs to include in message",
        )

    def handle(self, *args, **options):
        limit = options["limit"]

        total = ParserProductUrl.objects.filter(source="tara").count()
        active = ParserProductUrl.objects.filter(
            source="tara",
            status=ParserProductUrl.STATUS_ACTIVE,
        ).count()
        inactive = ParserProductUrl.objects.filter(
            source="tara",
            status=ParserProductUrl.STATUS_INACTIVE,
        ).count()
        loaded = ParserProductUrl.objects.filter(
            source="tara",
            status=ParserProductUrl.STATUS_ACTIVE,
            is_loaded=True,
        ).count()

        active_unloaded_qs = ParserProductUrl.objects.filter(
            source="tara",
            status=ParserProductUrl.STATUS_ACTIVE,
            is_loaded=False,
        ).order_by("id")

        unexpected_inactive_qs = (
            ParserProductUrl.objects.filter(
                source="tara",
                status=ParserProductUrl.STATUS_INACTIVE,
            )
            .filter(
                Q(last_error__isnull=True)
                | Q(last_error="")
                | ~Q(last_error__in=EXPECTED_INACTIVE_ERRORS)
            )
            .order_by("id")
        )

        active_unloaded_count = active_unloaded_qs.count()
        unexpected_inactive_count = unexpected_inactive_qs.count()

        active_unloaded_rows = list(
            active_unloaded_qs.values(
                "id",
                "url",
                "last_error",
                "date_update",
            )[:limit]
        )

        unexpected_inactive_rows = list(
            unexpected_inactive_qs.values(
                "id",
                "url",
                "last_error",
                "date_update",
            )[:limit]
        )

        lines = [
            "Tara parser pipeline finished",
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            f"Total URL: {total}",
            f"Active: {active}",
            f"Inactive: {inactive}",
            f"Loaded active: {loaded}",
            f"Active not loaded: {active_unloaded_count}",
            f"Unexpected inactive: {unexpected_inactive_count}",
            "",
        ]

        if active_unloaded_rows:
            lines.append("Active not loaded:")
            for row in active_unloaded_rows:
                lines.append(
                    f"- id={row['id']} error={row['last_error'] or 'NULL'} url={row['url']}"
                )
            lines.append("")

        if unexpected_inactive_rows:
            lines.append("Unexpected inactive:")
            for row in unexpected_inactive_rows:
                lines.append(
                    f"- id={row['id']} error={row['last_error'] or 'NULL'} url={row['url']}"
                )
            lines.append("")

        message = "\n".join(lines)

        logger.info(message)

        self.stdout.write(message)

        send_bitrix_message(message)