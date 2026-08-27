from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone

from bitrix24.services.refresh import (
    ADVISORY_LOCK_NAME,
    LOCK_KEY,
    STATE_KEY,
    acquire_refresh_cache_lock,
)
from bitrix24.services.sync_state import recover_interrupted_sync_runs


class Command(BaseCommand):
    help = "Safely close orphaned Bitrix24 synchronization runs."

    def add_arguments(self, parser):
        parser.add_argument("--entity", action="append", dest="entities")

    def handle(self, *args, **options):
        if not acquire_refresh_cache_lock():
            raise CommandError("Обновление Аналитики CRM сейчас выполняется.")
        advisory_lock = False
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_try_advisory_lock(hashtext(%s))",
                    [ADVISORY_LOCK_NAME],
                )
                advisory_lock = bool(cursor.fetchone()[0])
            if not advisory_lock:
                raise CommandError("Обновление Аналитики CRM сейчас выполняется.")
            recovered = recover_interrupted_sync_runs(
                entities=options.get("entities")
            )
            if recovered:
                cache.set(
                    STATE_KEY,
                    {
                        "status": "failed",
                        "finished_at": timezone.now().isoformat(),
                        "error": (
                            "Восстановлены прерванные состояния синхронизации: "
                            f"{recovered}."
                        ),
                    },
                    timeout=None,
                )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Interrupted Bitrix24 sync states recovered: {recovered}."
                )
            )
        finally:
            cache.delete(LOCK_KEY)
            if advisory_lock:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT pg_advisory_unlock(hashtext(%s))",
                        [ADVISORY_LOCK_NAME],
                    )
