from django.core.management.base import BaseCommand, CommandError
from django.core.cache import cache
from django.db import connection
from django.utils import timezone

from bitrix24.services.clickhouse import sync_lead_analytics_to_clickhouse
from lead_generation.clickhouse import rebuild_mart_safely
from bitrix24.services.refresh import ADVISORY_LOCK_NAME, LOCK_KEY, STATE_KEY, acquire_refresh_cache_lock
from dashboards.realtime import notify_dashboard_updated


class Command(BaseCommand):
    help = "Publish CRM deal marts from PostgreSQL without Bitrix API calls."

    def add_arguments(self, parser):
        parser.add_argument("--chunk-size", type=int, default=1000)

    def handle(self, *args, **options):
        chunk_size = options["chunk_size"]
        if chunk_size <= 0 or chunk_size > 10000:
            raise ValueError("--chunk-size must be between 1 and 10000.")
        if not acquire_refresh_cache_lock():
            raise CommandError("Обновление Аналитики CRM уже выполняется.")
        acquired = False
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_try_advisory_lock(hashtext(%s))", [ADVISORY_LOCK_NAME])
                acquired = bool(cursor.fetchone()[0])
            if not acquired:
                raise CommandError("Обновление Аналитики CRM уже выполняется.")
            cache.set(STATE_KEY, {"status": "running", "started_at": timezone.now().isoformat()}, timeout=None)
            inserted = sync_lead_analytics_to_clickhouse(chunk_size=chunk_size)
            rebuild_mart_safely()
            finished_at = timezone.now().isoformat()
            cache.set(STATE_KEY, {"status": "success", "finished_at": finished_at, "rows": inserted}, timeout=None)
        except BaseException as exc:
            if acquired:
                cache.set(STATE_KEY, {"status": "failed", "finished_at": timezone.now().isoformat(), "error": str(exc)[:1000]}, timeout=None)
            raise
        finally:
            cache.delete(LOCK_KEY)
            if acquired:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_unlock(hashtext(%s))", [ADVISORY_LOCK_NAME])
        notify_dashboard_updated("CRMAnalytics", updated_at=finished_at)
        self.stdout.write(
            self.style.SUCCESS(
                f"Bitrix24 ClickHouse mart published: rows={inserted}."
            )
        )
