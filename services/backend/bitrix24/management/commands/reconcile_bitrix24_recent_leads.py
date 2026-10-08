from analytics.services.bitrix_notify import send_bitrix_message
from datetime import date

from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone

from bitrix24.models import BitrixLead, BitrixDeal, BitrixSyncRun
from bitrix24.services.calculators import (
    rebuild_lead_analytics,
    rebuild_lead_processing,
    rebuild_stage_intervals,
)
from bitrix24.services.clickhouse import sync_lead_analytics_to_clickhouse
from bitrix24.services.client import Bitrix24Client
from bitrix24.services.loaders import reconcile_leads_window, load_deals
from bitrix24.services.reconciliation import purge_deleted_lead_derivatives, purge_deleted_deal_derivatives
from bitrix24.services.reconciliation_periods import MOSCOW_TZ, reconciliation_windows
from bitrix24.services.refresh import (
    ADVISORY_LOCK_NAME,
    LOCK_KEY,
    STATE_KEY,
    acquire_refresh_cache_lock,
)
from bitrix24.services.sync_state import recover_interrupted_sync_runs
from dashboards.realtime import notify_dashboard_updated
from lead_generation.clickhouse import rebuild_mart_safely


class Command(BaseCommand):
    help = "Reconcile recent Bitrix24 leads, then deals, by creation date."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=14, help="Complete calendar days to reconcile leads.")
        parser.add_argument("--deals-months", type=int, default=4, help="Calendar months to reconcile deals.")
        parser.add_argument(
            "--as-of-date",
            type=date.fromisoformat,
            help="Right-open reconciliation boundary in Europe/Moscow (YYYY-MM-DD).",
        )

    def handle(self, *args, **options):
        days = options["days"]
        boundary_date = options["as_of_date"] or timezone.now().astimezone(
            MOSCOW_TZ
        ).date()
        try:
            created_from, deals_created_from, created_to = reconciliation_windows(
                boundary_date, lead_days=days, deal_months=options["deals_months"],
            )
        except (ValueError, OverflowError) as exc:
            raise CommandError(str(exc)) from exc

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
                "deals_created_from": deals_created_from.isoformat(),
                "deals_created_to": created_to.isoformat(),
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
            recover_interrupted_sync_runs(entities=("leads", "deals"))
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
            deal_run = load_deals(
                Bitrix24Client(), mode=BitrixSyncRun.Mode.REPAIR,
                created_from=deals_created_from, created_to=created_to,
            )
            deal_purged = purge_deleted_deal_derivatives()
            received_deal_ids = BitrixDeal.objects.filter(
                is_deleted=False, source_created_at__gte=deals_created_from,
                source_created_at__lt=created_to, last_seen_at__gte=deal_run.started_at,
            ).values_list("deal_id", flat=True)
            rebuild_stage_intervals(entity_type_id=2, entity_ids=received_deal_ids)
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
                    "deals_created_from": deals_created_from.isoformat(),
                    "deals_created_to": created_to.isoformat(),
                    "received": run.rows_received,
                    "deactivated": run.rows_deactivated,
                    "purged": purged,
                    "deals_received": deal_run.rows_received,
                    "deals_deactivated": deal_run.rows_deactivated,
                    "deals_purged": deal_purged,
                    "rows": rows,
                },
                timeout=None,
            )
            rebuild_mart_safely()
            self.stdout.write(
                self.style.SUCCESS(
                    "Recent Bitrix24 leads and deals reconciled: "
                    f"leads_window=[{created_from.isoformat()}, {created_to.isoformat()}), "
                    f"deals_window=[{deals_created_from.isoformat()}, {created_to.isoformat()}), "
                    f"received={run.rows_received}, deactivated={run.rows_deactivated}, "
                    f"deals_received={deal_run.rows_received}, deals_deactivated={deal_run.rows_deactivated}, "
                    f"analytics_rows={rows}."
                )
            )
        except BaseException as exc:
            if not getattr(exc, "_bitrix_notification_attempted", False):
                exc._bitrix_notification_attempted = True
                send_bitrix_message("[b]CRM: reconcile_bitrix24_recent_leads[/b] \u041e\u0448\u0438\u0431\u043a\u0430 \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u044f. \u041f\u043e\u0434\u0440\u043e\u0431\u043d\u043e\u0441\u0442\u0438 \u0432 logs/bitrix24_refresh.log \u0438 \u043b\u043e\u0433\u0435 \u043a\u043e\u043c\u0430\u043d\u0434\u044b.", logger_name="bitrix24")
            cache.set(
                STATE_KEY,
                {
                    "status": "failed",
                    "finished_at": timezone.now().isoformat(),
                    "operation": "recent_leads_reconciliation",
                    "created_from": created_from.isoformat(),
                    "created_to": created_to.isoformat(),
                    "error": str(exc)[:1000],
                    "deals_created_from": deals_created_from.isoformat(),
                    "deals_created_to": created_to.isoformat(),
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
        notify_dashboard_updated("CRMAnalytics", updated_at=finished_at)
