import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from context_analytics.models import ContextExportRun


MAX_AGE = timedelta(hours=24)


class ExportAlreadyRunning(RuntimeError):
    pass


def export_directory():
    path = Path(settings.MEDIA_ROOT) / "analytics_exports" / "context"
    path.mkdir(parents=True, exist_ok=True)
    return path


def cleanup_expired():
    stale_cutoff = timezone.now() - timedelta(seconds=settings.ANALYTICS_EXPORT_TIMEOUT)
    ContextExportRun.objects.filter(status="running", heartbeat_at__lt=stale_cutoff).update(
        status="failed", finished_at=timezone.now(),
        error="Формирование экспорта превысило допустимое время выполнения.",
    )
    cutoff = timezone.now() - MAX_AGE
    for pattern in ("*.xlsx", "*.part"):
        for path in export_directory().glob(pattern):
            if path.stat().st_mtime < cutoff.timestamp():
                path.unlink(missing_ok=True)
    for run in ContextExportRun.objects.exclude(status="running").filter(started_at__lt=cutoff):
        run.delete()


def launch_export(user, page, filters):
    cleanup_expired()
    lock_key = "context:export:launch"
    if not cache.add(lock_key, "launching", 60):
        raise ExportAlreadyRunning("Экспорт контекстной аналитики уже запускается.")
    try:
        existing = ContextExportRun.objects.filter(status="running").first()
        if existing:
            raise ExportAlreadyRunning("Экспорт контекстной аналитики уже выполняется.")
        run = ContextExportRun.objects.create(
            page=page, filters=filters, started_by=user, heartbeat_at=timezone.now(),
        )
        log_dir = Path(settings.BASE_DIR) / "logs" / "context_analytics"
        log_dir.mkdir(parents=True, exist_ok=True)
        stream = open(log_dir / "export.log", "ab", buffering=0)
        try:
            subprocess.Popen(
                [sys.executable, str(Path(settings.BASE_DIR) / "manage.py"),
                 "build_context_export", "--run-id", str(run.id)],
                cwd=settings.BASE_DIR, stdout=stream, stderr=subprocess.STDOUT,
                start_new_session=True, env=os.environ.copy(),
            )
        except Exception as exc:
            run.status = "failed"
            run.error = str(exc)[:10000]
            run.finished_at = timezone.now()
            run.save(update_fields=("status", "error", "finished_at"))
            raise
        finally:
            stream.close()
        return run
    finally:
        cache.delete(lock_key)


def state(run):
    stale_cutoff = timezone.now() - timedelta(seconds=settings.ANALYTICS_EXPORT_TIMEOUT)
    if run.status == "running" and run.heartbeat_at and run.heartbeat_at < stale_cutoff:
        run.status = "failed"
        run.error = "Формирование экспорта превысило допустимое время выполнения."
        run.finished_at = timezone.now()
        run.save(update_fields=("status", "error", "finished_at"))
    return {
        "id": str(run.id), "status": run.status, "running": run.status == "running",
        "ready": run.status == "success", "error": run.error,
        "started_at": run.started_at, "finished_at": run.finished_at,
    }
