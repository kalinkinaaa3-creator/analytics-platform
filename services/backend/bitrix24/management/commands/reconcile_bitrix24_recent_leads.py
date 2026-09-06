from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone

from bitrix24.models import BitrixLead
from bitrix24.services.calculators import (
    rebuild_lead_analytics,
    rebuild_lead_processing,
    rebuild_stage_intervals,
)
from bitrix24.services.clickhouse import sync_lead_analytics_to_clickhouse
from bitrix24.services.client import Bitrix24Client
from bitrix24.services.loaders import reconcile_leads_window
from bitrix24.services.reconciliation import purge_deleted_lead_derivatives
from bitrix24.services.refresh import (
    ADVISORY_LOCK_NAME,
    LOCK_KEY,
    STATE_KEY,
    acquire_refresh_cache_lock,
)
from bitrix24.services.sync_state import recover_interrupted_sync_runs
from dashboards.realtime import notify_dashboard_updated
from lead_generation.clickhouse import rebuild_mart_safely


MOSCOW_TZ = ZoneInfo("Europe/Moscow")


class Command(BaseCommand):
    help = "Reconcile recent Bitrix24 leads by creation date without touching older leads."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=14)
        parser.add_argument(
            "--as-of-date",
            type=date.fromisoformat,
            help="Right-open reconciliation boundary in Europe/Moscow (YYYY-MM-DD).",
        )

    def handle(self, *args, **options):
        days = options["days"]
        if days < 1:
            raise CommandError("--days must be a positive integer.")
        boundary_date = options["as_of_date"] or timezone.now().astimezone(
            MOSCOW_TZ
        ).date()
        created_to = datetime.combine(boundary_date, time.min, tzinfo=MOSCOW_TZ)
        created_from = created_to - timedelta(days=days)

        if not acquire_refresh_cache_lock():
            raise CommandError("Обновление Аналитики CRM уже выполняется.")
        cache.set(
            STATE_KEY,
            {
                "status": "running",
                "started_at": timezone.now().isoformat(),
                "operation": "recent_leads_reconciliation",
                "created_from": created_from.isoformat(),
                "created_to": created_to.isoformat(),
            },
            timeout=None,
        )
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_try_advisory_lock(hashtext(%s))",
                [ADVISORY_LOCK_NAME],
            )
            advisory_lock = bool(cursor.fetchone()[0])
        if not advisory_lock:
            cache.delete(LOCK_KEY)
            raise CommandError("Обновление Аналитики CRM уже выполняется.")

        try:
            recover_interrupted_sync_runs(entities=("leads",))
            run = reconcile_leads_window(
                Bitrix24Client(),
                created_from=created_from,
                created_to=created_to,
            )
            purged = purge_deleted_lead_derivatives()
            received_lead_ids = BitrixLead.objects.filter(
                is_deleted=False,
                source_created_at__gte=created_from,
                source_created_at__lt=created_to,
                last_seen_at__gte=run.started_at,
            ).values_list("lead_id", flat=True)
            rebuild_stage_intervals(
                entity_type_id=1,
                entity_ids=received_lead_ids,
            )
            rebuild_lead_processing()
            rebuild_lead_analytics()
            rows = sync_lead_analytics_to_clickhouse(chunk_size=500)
            finished_at = timezone.now().isoformat()
            cache.set(
                STATE_KEY,
                {
                    "status": "success",
                    "finished_at": finished_at,
                    "operation": "recent_leads_reconciliation",
                    "created_from": created_from.isoformat(),
                    "created_to": created_to.isoformat(),
                    "received": run.rows_received,
                    "deactivated": run.rows_deactivated,
                    "purged": purged,
                    "rows": rows,
                },
                timeout=None,
            )
            rebuild_mart_safely()
            notify_dashboard_updated("CRMAnalytics", updated_at=finished_at)
            self.stdout.write(
                self.style.SUCCESS(
                    "Recent Bitrix24 leads reconciled: "
                    f"window=[{created_from.isoformat()}, {created_to.isoformat()}), "
                    f"received={run.rows_received}, deactivated={run.rows_deactivated}, "
                    f"analytics_rows={rows}."
                )
            )
        except BaseException as exc:
            cache.set(
                STATE_KEY,
                {
                    "status": "failed",
                    "finished_at": timezone.now().isoformat(),
                    "operation": "recent_leads_reconciliation",
                    "created_from": created_from.isoformat(),
                    "created_to": created_to.isoformat(),
                    "error": str(exc)[:1000],
                },
                timeout=None,
            )
            raise
        finally:
            cache.delete(LOCK_KEY)
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_unlock(hashtext(%s))",
                    [ADVISORY_LOCK_NAME],
                )
