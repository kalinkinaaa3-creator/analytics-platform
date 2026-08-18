from django.core.cache import cache
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
    load_leads,
    load_stage_history,
    load_users,
)
from bitrix24.services.refresh import LOCK_KEY, STATE_KEY
from dashboards.realtime import notify_dashboard_updated


class Command(BaseCommand):
    help = "Refresh the complete Bitrix24 CRM analytics pipeline."

    def add_arguments(self, parser):
        parser.add_argument("--skip-bitrix", action="store_true")

    def handle(self, *args, **options):
        try:
            if not options["skip_bitrix"]:
                client = Bitrix24Client()
                load_departments(client, mode=BitrixSyncRun.Mode.FULL)
                load_users(client, mode=BitrixSyncRun.Mode.FULL)
                load_crm_dictionaries(client, mode=BitrixSyncRun.Mode.FULL)
                load_crm_fields(client, mode=BitrixSyncRun.Mode.FULL)
                load_leads(client, mode=BitrixSyncRun.Mode.INCREMENTAL)
                load_stage_history(client, mode=BitrixSyncRun.Mode.INCREMENTAL)
            rebuild_stage_intervals(entity_type_id=1)
            rebuild_lead_processing()
            rebuild_lead_analytics()
            rows = sync_lead_analytics_to_clickhouse(chunk_size=500)
            finished_at = timezone.now().isoformat()
            cache.set(
                STATE_KEY,
                {"status": "success", "finished_at": finished_at, "rows": rows},
                timeout=None,
            )
            notify_dashboard_updated("CRMAnalytics", updated_at=finished_at)
            self.stdout.write(self.style.SUCCESS(f"CRM analytics refreshed: rows={rows}."))
        except BaseException as exc:
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
