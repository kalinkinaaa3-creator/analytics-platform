from analytics.services.bitrix_notify import send_bitrix_message
import logging
import json
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from dashboards.realtime import notify_dashboard_updated
from seo_analytics.models import SeoRefreshRun


logger = logging.getLogger("seo_analytics.refresh")
LOCK_KEY = "seo:refresh:lock"
LAUNCH_LOCK_KEY = "seo:refresh:launch"


class SeoRefreshAlreadyRunning(RuntimeError):
    pass


def _notify_refresh(run):
    try:
        notify_dashboard_updated(
            "SEOAnalytics",
            status=run.status,
            run_id=run.id,
            updated_at=(run.finished_at or run.started_at).isoformat(),
            error=run.error,
        )
    except Exception:
        logger.exception("Failed to publish SEO refresh state")


def recover_stale_runs():
    cutoff = timezone.now() - timedelta(seconds=settings.SEO_REFRESH_LOCK_TIMEOUT)
    stale = SeoRefreshRun.objects.filter(status=SeoRefreshRun.Status.RUNNING).filter(
        Q(heartbeat_at__lt=cutoff) | Q(heartbeat_at__isnull=True, started_at__lt=cutoff)
    )
    count = stale.update(
        status=SeoRefreshRun.Status.FAILED,
        finished_at=timezone.now(),
        error="Обновление помечено как failed после превышения допустимого времени выполнения.",
    )
    if count:
        send_bitrix_message(f"[b]SEO-аналитика[/b] Загрузка прервана: {count} запусков без heartbeat. Подробности в журнале обновлений SEO.", logger_name=logger.name)


def heartbeat_run(run, stats=None):
    run.heartbeat_at = timezone.now()
    update_fields = ["heartbeat_at"]
    if stats is not None:
        run.stats = stats
        update_fields.append("stats")
    run.save(update_fields=update_fields)
    cache.touch(LOCK_KEY, settings.SEO_REFRESH_LOCK_TIMEOUT)


def start_run(*, trigger, user=None):
    recover_stale_runs()
    cache.delete(LAUNCH_LOCK_KEY)
    if not cache.add(LOCK_KEY, "running", timeout=settings.SEO_REFRESH_LOCK_TIMEOUT):
        raise SeoRefreshAlreadyRunning("Обновление SEO-аналитики уже выполняется.")
    try:
        with transaction.atomic():
            if SeoRefreshRun.objects.select_for_update().filter(status=SeoRefreshRun.Status.RUNNING).exists():
                raise SeoRefreshAlreadyRunning("Обновление SEO-аналитики уже выполняется.")
            run = SeoRefreshRun.objects.create(
                status=SeoRefreshRun.Status.RUNNING,
                trigger=trigger,
                started_by=user,
                heartbeat_at=timezone.now(),
            )
            transaction.on_commit(lambda: _notify_refresh(run))
            return run
    except Exception:
        cache.delete(LOCK_KEY)
        raise


def finish_run(run, stats):
    run.status = SeoRefreshRun.Status.SUCCESS
    run.stats = stats
    run.finished_at = timezone.now()
    run.heartbeat_at = timezone.now()
    run.save(update_fields=("status", "stats", "finished_at", "heartbeat_at"))
    cache.delete(LOCK_KEY)
    _notify_refresh(run)


def fail_run(run, error):
    already_failed = run.status == SeoRefreshRun.Status.FAILED
    run.status = SeoRefreshRun.Status.FAILED
    run.error = str(error)[:10000]
    run.finished_at = timezone.now()
    run.heartbeat_at = timezone.now()
    run.save(update_fields=("status", "error", "finished_at", "heartbeat_at"))
    cache.delete(LOCK_KEY)
    _notify_refresh(run)
    if not already_failed:
        send_bitrix_message(f"[b]SEO-аналитика[/b] Ошибка загрузки #{run.id} ({type(error).__name__}). Подробности в журнале обновлений SEO и logs/seo_analytics.", logger_name=logger.name)


def launch_background_refresh(user=None, *, page="", filters=None, trigger=None, window="default"):
    if not cache.add(LAUNCH_LOCK_KEY, "launching", timeout=60):
        raise SeoRefreshAlreadyRunning("Обновление SEO-аналитики уже запускается.")
    if cache.get(LOCK_KEY) or SeoRefreshRun.objects.filter(status=SeoRefreshRun.Status.RUNNING).exists():
        cache.delete(LAUNCH_LOCK_KEY)
        raise SeoRefreshAlreadyRunning("Обновление SEO-аналитики уже выполняется.")

    log_dir = Path(settings.BASE_DIR) / "logs" / "seo_analytics"
    log_dir.mkdir(parents=True, exist_ok=True)
    effective_trigger = trigger or SeoRefreshRun.Trigger.MANUAL
    log_name = "scheduled_refresh.log" if effective_trigger == SeoRefreshRun.Trigger.SCHEDULED else "manual_refresh.log"
    log_path = log_dir / log_name
    log_file = open(log_path, "ab", buffering=0)
    try:
        command = [
                sys.executable,
                str(Path(settings.BASE_DIR) / "manage.py"),
                "refresh_seo_analytics",
                "--trigger",
                effective_trigger,
                "--user-id",
                str(user.id if user else 0),
            ]
        if page:
            command.extend(["--page", page])
        if filters:
            command.extend(["--filters-json", json.dumps(filters, ensure_ascii=False)])
        if window != "default":
            command.extend(["--window", window])
        subprocess.Popen(
            command,
            cwd=settings.BASE_DIR,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=os.environ.copy(),
        )
    except Exception:
        cache.delete(LAUNCH_LOCK_KEY)
        send_bitrix_message("[b]seo_analytics[/b] \u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0437\u0430\u043f\u0443\u0441\u0442\u0438\u0442\u044c \u0444\u043e\u043d\u043e\u0432\u0443\u044e \u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0443. \u041f\u043e\u0434\u0440\u043e\u0431\u043d\u043e\u0441\u0442\u0438 \u0432 \u043b\u043e\u0433\u0430\u0445 Django.", logger_name="seo_analytics")
        raise
    finally:
        log_file.close()


def latest_state():
    recover_stale_runs()
    run = SeoRefreshRun.objects.first()
    completed = list(SeoRefreshRun.objects.filter(
        status=SeoRefreshRun.Status.SUCCESS,
        finished_at__isnull=False,
    ).values_list("started_at", "finished_at")[:3])
    average_duration_seconds = round(sum((finished - started).total_seconds() for started, finished in completed) / len(completed)) if completed else None
    if run is None:
        return {"status": "never", "running": False, "average_duration_seconds": average_duration_seconds}
    return {
        "id": run.id,
        "status": run.status,
        "running": run.status == SeoRefreshRun.Status.RUNNING,
        "trigger": run.trigger,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "stats": run.stats,
        "error": run.error,
        "average_duration_seconds": average_duration_seconds,
    }
