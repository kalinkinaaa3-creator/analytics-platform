from analytics.services.bitrix_notify import send_bitrix_message
import os
import logging
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from context_analytics.models import ContextRefreshRun
from dashboards.realtime import notify_dashboard_updated


LOCK_KEY = "context:refresh:lock"
LAUNCH_KEY = "context:refresh:launch"
DEFAULT_INCREMENTAL_DAYS = 14
logger = logging.getLogger("context_analytics.refresh")


class ContextRefreshAlreadyRunning(RuntimeError):
    pass


def _notify(run):
    try:
        notify_dashboard_updated(
            "ContextAnalytics",
            status=run.status,
            run_id=run.id,
            updated_at=(run.finished_at or run.started_at).isoformat(),
            error=run.error,
        )
    except Exception:
        logger.exception("Failed to publish context analytics refresh state")


def recover_stale():
    cutoff = timezone.now() - timedelta(seconds=settings.CONTEXT_REFRESH_LOCK_TIMEOUT)
    count = ContextRefreshRun.objects.filter(status="running").filter(
        Q(heartbeat_at__lt=cutoff) | Q(heartbeat_at__isnull=True, started_at__lt=cutoff)
    ).update(
        status="failed", finished_at=timezone.now(), error="Обновление превысило допустимое время выполнения.")
    if count:
        send_bitrix_message(f"[b]Контекстная аналитика[/b] Загрузка прервана: {count} запусков без heartbeat. Подробности в журнале обновлений контекста.", logger_name=logger.name)


def heartbeat(run, stats=None):
    run.heartbeat_at = timezone.now()
    update_fields = ["heartbeat_at"]
    if stats is not None:
        run.stats = stats
        update_fields.append("stats")
    run.save(update_fields=update_fields)
    cache.touch(LOCK_KEY, settings.CONTEXT_REFRESH_LOCK_TIMEOUT)


def start_run(trigger, user=None):
    recover_stale()
    cache.delete(LAUNCH_KEY)
    if not cache.add(LOCK_KEY, "running", settings.CONTEXT_REFRESH_LOCK_TIMEOUT):
        raise ContextRefreshAlreadyRunning("Обновление контекстной рекламы уже выполняется.")
    try:
        with transaction.atomic():
            if ContextRefreshRun.objects.select_for_update().filter(status="running").exists():
                raise ContextRefreshAlreadyRunning("Обновление контекстной рекламы уже выполняется.")
            run = ContextRefreshRun.objects.create(status="running", trigger=trigger, started_by=user,
                                                   heartbeat_at=timezone.now())
            transaction.on_commit(lambda: _notify(run))
            return run
    except Exception:
        cache.delete(LOCK_KEY)
        raise


def finish(run, stats=None, error=""):
    already_failed = run.status == "failed"
    run.status = "failed" if error else "success"
    run.stats = stats or {}
    run.error = str(error)[:10000]
    run.finished_at = run.heartbeat_at = timezone.now()
    run.save(update_fields=("status","stats","error","finished_at","heartbeat_at"))
    cache.delete(LOCK_KEY)
    _notify(run)
    if error and not already_failed:
        send_bitrix_message(f"[b]Контекстная аналитика[/b] Ошибка загрузки #{run.id} ({type(error).__name__}). Подробности в журнале обновлений контекста и logs/context_analytics.", logger_name=logger.name)


def latest_state():
    recover_stale()
    run = ContextRefreshRun.objects.first()
    completed = list(ContextRefreshRun.objects.filter(status="success", finished_at__isnull=False)
                     .values_list("started_at", "finished_at")[:3])
    average_duration_seconds = round(sum((finished - started).total_seconds() for started, finished in completed) / len(completed)) if completed else None
    if not run:
        return {"status": "never", "running": False, "average_duration_seconds": average_duration_seconds}
    return {"id": run.id, "status": run.status, "running": run.status == "running", "trigger": run.trigger,
            "started_at": run.started_at, "finished_at": run.finished_at, "stats": run.stats, "error": run.error,
            "average_duration_seconds": average_duration_seconds}


def launch(user=None, *, trigger="manual", days=None):
    if not cache.add(LAUNCH_KEY, "launching", 60):
        raise ContextRefreshAlreadyRunning("Обновление уже запускается.")
    if cache.get(LOCK_KEY) or ContextRefreshRun.objects.filter(status="running").exists():
        cache.delete(LAUNCH_KEY)
        raise ContextRefreshAlreadyRunning("Обновление уже выполняется.")
    log_dir = Path(settings.BASE_DIR) / "logs" / "context_analytics"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_name = "scheduled_refresh.log" if trigger == "scheduled" else "manual_refresh.log"
    stream = open(log_dir / log_name, "ab", buffering=0)
    try:
        command = [
            sys.executable,
            str(Path(settings.BASE_DIR) / "manage.py"),
            "refresh_context_analytics",
            "--trigger", trigger,
            "--user-id", str(user.id if user else 0),
        ]
        if days is not None:
            command.extend(["--days", str(days)])
        subprocess.Popen(command,
                         cwd=settings.BASE_DIR, stdout=stream, stderr=subprocess.STDOUT,
                         start_new_session=True, env=os.environ.copy())
    except Exception:
        cache.delete(LAUNCH_KEY)
        send_bitrix_message("[b]context_analytics[/b] \u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0437\u0430\u043f\u0443\u0441\u0442\u0438\u0442\u044c \u0444\u043e\u043d\u043e\u0432\u0443\u044e \u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0443. \u041f\u043e\u0434\u0440\u043e\u0431\u043d\u043e\u0441\u0442\u0438 \u0432 \u043b\u043e\u0433\u0430\u0445 Django.", logger_name="context_analytics")
        raise
    finally:
        stream.close()
