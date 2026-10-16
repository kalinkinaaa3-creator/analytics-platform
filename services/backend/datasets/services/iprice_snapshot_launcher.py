import os
import subprocess
import sys

from django.conf import settings


def launch_iprice_snapshot(
    *,
    snapshot_id: int,
    workspace=None,
) -> int:
    """
    Запускает расчет snapshot отдельным процессом.

    Возвращает PID процесса.
    """

    log_dir = (
        settings.BASE_DIR
        / "logs"
        / "iprice"
    )

    log_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    is_select_market = workspace is not None and workspace.code == 'select-market'
    log_path = (
        log_dir
        / f"{'select-market_' if is_select_market else ''}snapshot_{snapshot_id}.log"
    )

    command = [
        sys.executable,
        str(
            settings.BASE_DIR
            / "manage.py"
        ),
        "build_select_market_snapshot" if is_select_market else "build_iprice_snapshot",
        "--snapshot-id",
        str(snapshot_id),
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

    finally:
        log_file.close()

    return process.pid
