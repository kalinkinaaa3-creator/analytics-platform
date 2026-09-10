from analytics.services.bitrix_notify import send_bitrix_message
from django.core.cache import cache
from django.core.management.base import CommandError
from django.db import connection
from django.core.management.base import BaseCommand
from django.utils import timezone

from bitrix24.models import BitrixSyncRun
from bitrix24.services.calculators import (
    rebuild_lead_analytics,
    rebuild_lead_processing,
    rebuild_stage_intervals,
)
from bitrix24.services.clickhouse import sync_lead_analytics_to_clickhouse
from bitrix24.services.client import Bitrix24Client
from bitrix24.services.loaders import (
    load_crm_dictionaries,
    load_crm_fields,
    load_departments,
    load_deals,
    load_deal_categories,
    load_deal_stages,
    load_leads,
    load_stage_history,
    load_users,
)
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
    help = "Refresh the complete Bitrix24 CRM analytics pipeline."

    def add_arguments(self, parser):
        parser.add_argument("--skip-bitrix", action="store_true")
        parser.add_argument("--lock-acquired", action="store_true")

    def handle(self, *args, **options):
        owns_cache_lock = not options["lock_acquired"]
        if owns_cache_lock and not acquire_refresh_cache_lock():
            raise CommandError("Обновление Аналитики CRM уже выполняется.")
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_try_advisory_lock(hashtext(%s))",
                [ADVISORY_LOCK_NAME],
            )
            advisory_lock = bool(cursor.fetchone()[0])
        if not advisory_lock:
            if owns_cache_lock:
                cache.delete(LOCK_KEY)
            raise CommandError("Обновление Аналитики CRM уже выполняется.")
        try:
            recover_interrupted_sync_runs()
            if not options["skip_bitrix"]:
                client = Bitrix24Client()
                load_departments(client, mode=BitrixSyncRun.Mode.FULL)
                load_users(client, mode=BitrixSyncRun.Mode.FULL)
                load_crm_dictionaries(client, mode=BitrixSyncRun.Mode.FULL)
                load_crm_fields(client, mode=BitrixSyncRun.Mode.FULL)
                load_leads(client, mode=BitrixSyncRun.Mode.INCREMENTAL)
                load_stage_history(client, mode=BitrixSyncRun.Mode.INCREMENTAL)
                load_deal_categories(client)
                load_deal_stages(client)
                load_crm_fields(client, entity_type_id=2)
                load_deals(client)
                load_stage_history(client, entity_type_id=2)
            rebuild_stage_intervals(entity_type_id=1)
            rebuild_stage_intervals(entity_type_id=2)
            rebuild_lead_processing()
            rebuild_lead_analytics()
            rows = sync_lead_analytics_to_clickhouse(chunk_size=500)
            finished_at = timezone.now().isoformat()
            cache.set(
                STATE_KEY,
                {"status": "success", "finished_at": finished_at, "rows": rows},
                timeout=None,
            )
            rebuild_mart_safely()
            self.stdout.write(self.style.SUCCESS(f"CRM analytics refreshed: rows={rows}."))
        except BaseException as exc:
            if not getattr(exc, "_bitrix_notification_attempted", False):
                exc._bitrix_notification_attempted = True
                send_bitrix_message("[b]CRM: refresh_bitrix24[/b] \u041e\u0448\u0438\u0431\u043a\u0430 \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u044f. \u041f\u043e\u0434\u0440\u043e\u0431\u043d\u043e\u0441\u0442\u0438 \u0432 logs/bitrix24_refresh.log \u0438 \u043b\u043e\u0433\u0435 \u043a\u043e\u043c\u0430\u043d\u0434\u044b.", logger_name="bitrix24")
            cache.set(
                STATE_KEY,
                {
                    "status": "failed",
                    "finished_at": timezone.now().isoformat(),
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
        notify_dashboard_updated("CRMAnalytics", updated_at=finished_at)
