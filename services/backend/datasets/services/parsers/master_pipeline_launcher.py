import logging
import os
import subprocess
import sys

from django.conf import settings


logger = logging.getLogger("parsers.master")


def launch_parser_master_pipeline(run_id: int) -> int:
    log_dir = settings.BASE_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    log_path = log_dir / f"parser_master_run_{run_id}.log"

    command = [
        sys.executable,
        str(settings.BASE_DIR / "manage.py"),
        "run_parser_master_pipeline",
        "--run-id",
        str(run_id),
    ]

    log_file = open(
        log_path,
        "a",
        encoding="utf-8",
    )

    try:
        process = subprocess.Popen(
            command,
            cwd=settings.BASE_DIR,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=os.environ.copy(),
        )
    except Exception:
        log_file.close()
        raise

    logger.info(
        "Parser master pipeline process launched "
        "run_id=%s pid=%s log=%s",
        run_id,
        process.pid,
        log_path,
    )

    return process.pid