from __future__ import annotations

from analytics.services.bitrix_notify import send_bitrix_message

import os
import subprocess
import sys
from datetime import datetime, timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.utils import timezone


LOCK_KEY = "bitrix24:refresh:running"
STATE_KEY = "bitrix24:refresh:state"
LOCK_TIMEOUT_SECONDS = 4 * 60 * 60
LOCK_STARTUP_GRACE_SECONDS = 60
ADVISORY_LOCK_NAME = "bitrix24_refresh"


def _lock_payload() -> dict:
    return {"started_at": timezone.now().isoformat()}


def _lock_is_in_startup_grace(value) -> bool:
    if not isinstance(value, dict) or not value.get("started_at"):
        return False
    try:
        started_at = datetime.fromisoformat(value["started_at"])
        if timezone.is_naive(started_at):
            started_at = timezone.make_aware(started_at)
    except (TypeError, ValueError):
        return False
    return timezone.now() - started_at < timedelta(
        seconds=LOCK_STARTUP_GRACE_SECONDS
    )


def advisory_refresh_lock_is_free() -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_try_advisory_lock(hashtext(%s))",
            [ADVISORY_LOCK_NAME],
        )
        acquired = bool(cursor.fetchone()[0])
        if acquired:
            cursor.execute(
                "SELECT pg_advisory_unlock(hashtext(%s))",
                [ADVISORY_LOCK_NAME],
            )
    return acquired


def acquire_refresh_cache_lock() -> bool:
    payload = _lock_payload()
    if cache.add(LOCK_KEY, payload, timeout=LOCK_TIMEOUT_SECONDS):
        return True
    existing = cache.get(LOCK_KEY)
    if _lock_is_in_startup_grace(existing):
        return False
    if not advisory_refresh_lock_is_free():
        return False
    cache.delete(LOCK_KEY)
    return cache.add(LOCK_KEY, payload, timeout=LOCK_TIMEOUT_SECONDS)


def refresh_state() -> dict:
    from bitrix24.models import BitrixSyncRun

    state = cache.get(STATE_KEY) or {}
    completed = list(BitrixSyncRun.objects.filter(
        entity="leads", status=BitrixSyncRun.Status.SUCCESS, finished_at__isnull=False,
    ).values_list("started_at", "finished_at")[:3])
    average_duration_seconds = round(sum((finished - started).total_seconds() for started, finished in completed) / len(completed)) if completed else None
    return {"running": bool(cache.get(LOCK_KEY)), **state, "average_duration_seconds": average_duration_seconds}


def launch_refresh(*, skip_bitrix: bool = False) -> int:
    if not acquire_refresh_cache_lock():
        raise RuntimeError("Обновление Аналитики CRM уже выполняется.")
    cache.set(
        STATE_KEY,
        {"status": "running", "started_at": timezone.now().isoformat()},
        timeout=None,
    )
    log_dir = settings.BASE_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(settings.BASE_DIR / "manage.py"), "refresh_bitrix24"]
    command.append("--lock-acquired")
    if skip_bitrix:
        command.append("--skip-bitrix")
    environment = os.environ.copy()
    environment.setdefault("MALLOC_ARENA_MAX", "2")
    log_file = open(log_dir / "bitrix24_refresh.log", "a", encoding="utf-8")
    try:
        process = subprocess.Popen(
            command,
            cwd=settings.BASE_DIR,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=environment,
        )
    except BaseException:
        cache.delete(LOCK_KEY)
        send_bitrix_message("[b]bitrix24[/b] \u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0437\u0430\u043f\u0443\u0441\u0442\u0438\u0442\u044c \u0444\u043e\u043d\u043e\u0432\u0443\u044e \u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0443. \u041f\u043e\u0434\u0440\u043e\u0431\u043d\u043e\u0441\u0442\u0438 \u0432 \u043b\u043e\u0433\u0430\u0445 Django.", logger_name="bitrix24")
        raise
    finally:
        log_file.close()
    return process.pid
