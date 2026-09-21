import logging
from datetime import datetime

from django.core.management.base import BaseCommand
from django.db.models import Q

from analytics.services.bitrix_notify import send_bitrix_message
from datasets.models import ParserProductUrl


logger = logging.getLogger("parsers.tara")

EXPECTED_INACTIVE_ERRORS = [
    "HTTP 404: product page not found",
    "missing_from_sitemap",
]


class Command(BaseCommand):
    help = "Report Tara parser result to logs and Bitrix"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=30,
            help="How many problem URLs to include in message",
        )
        parser.add_argument("--skip-bitrix", action="store_true")
        parser.add_argument('--tara-run-id', type=int)

    def handle(self, *args, **options):
        if options.get('tara_run_id'):
            from datasets.models import TaraRun
            from datasets.services.parsers.tara_jobs import progress
            run = TaraRun.objects.get(pk=options['tara_run_id'])
            counts = progress(run)['counts']
            message = (
                f'Tara run #{run.pk}: {run.status}\n'
                f'Origin: {run.origin}; classified_only={bool(run.options.get("classified_only"))}\n'
                f'Total: {sum(counts.values())}; success: {counts.get("success", 0)}; '
                f'404: {counts.get("not_found", 0)}; errors: {counts.get("error", 0)}; '
                f'pending: {counts.get("pending", 0)}'
            )
            logger.info(message)
            self.stdout.write(message)
            if not options['skip_bitrix']:
                send_bitrix_message(message, logger_name='parsers.tara')
            return
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
                    f"- id={row['id']} "
                    f"error={row['last_error'] or 'NULL'} "
                    f"url={row['url']}"
                )
            lines.append("")

        if unexpected_inactive_rows:
            lines.append("Unexpected inactive:")
            for row in unexpected_inactive_rows:
                lines.append(
                    f"- id={row['id']} "
                    f"error={row['last_error'] or 'NULL'} "
                    f"url={row['url']}"
                )
            lines.append("")

        message = "\n".join(lines)

        logger.info(message)
        self.stdout.write(message)

        if not options["skip_bitrix"]:
            send_bitrix_message(
                message,
                logger_name="parsers.tara",
            )
