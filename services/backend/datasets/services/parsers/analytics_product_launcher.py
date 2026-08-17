import logging
import os
import subprocess
import sys

from django.conf import settings


logger = logging.getLogger("analytics_product.launcher")


def launch_analytics_product_processing(run_id):
    log_dir = settings.BASE_DIR / "logs" / "analytics_product"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"run_{run_id}.log"
    command = [
        sys.executable, str(settings.BASE_DIR / "manage.py"),
        "run_analytics_product_processing", "--run-id", str(run_id),
    ]
    environment = os.environ.copy()
    # Keep glibc from creating many memory arenas in the background worker.
    environment.setdefault("MALLOC_ARENA_MAX", "2")
    log_file = open(log_path, "a", encoding="utf-8")
    try:
        process = subprocess.Popen(
            command, cwd=settings.BASE_DIR, stdin=subprocess.DEVNULL,
            stdout=log_file, stderr=subprocess.STDOUT, start_new_session=True,
            env=environment,
        )
    except Exception:
        log_file.close()
        raise
    log_file.close()
    logger.info(
        "Analytics product process launched run_id=%s pid=%s log=%s",
        run_id, process.pid, log_path,
    )
    return process.pid
