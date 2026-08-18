from __future__ import annotations

import os
import subprocess
import sys

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone


LOCK_KEY = "bitrix24:refresh:running"
STATE_KEY = "bitrix24:refresh:state"


def refresh_state() -> dict:
    state = cache.get(STATE_KEY) or {}
    return {"running": bool(cache.get(LOCK_KEY)), **state}


def launch_refresh(*, skip_bitrix: bool = False) -> int:
    if not cache.add(LOCK_KEY, True, timeout=60 * 60 * 6):
        raise RuntimeError("Обновление Аналитики CRM уже выполняется.")
    cache.set(
        STATE_KEY,
        {"status": "running", "started_at": timezone.now().isoformat()},
        timeout=None,
    )
    log_dir = settings.BASE_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(settings.BASE_DIR / "manage.py"), "refresh_bitrix24"]
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
        log_file.close()
        cache.delete(LOCK_KEY)
        raise
    return process.pid
