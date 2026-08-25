"""Daily retention cleanup for local Airflow and backend application logs."""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.operators.python import PythonOperator


LOGGER = logging.getLogger(__name__)
RETENTION_DAYS = 7
LOG_ROOTS = (
    Path("/opt/airflow/logs"),
    Path("/opt/analytics-platform/services/backend/logs"),
)


def _cleanup_log_root(root: Path, cutoff_timestamp: float) -> tuple[int, int]:
    """Delete regular files older than cutoff and then remove empty directories."""
    if not root.is_dir():
        LOGGER.warning("Log directory does not exist: %s", root)
        return 0, 0

    deleted_files = 0
    freed_bytes = 0

    # topdown=False lets us remove empty nested directories after their files.
    # followlinks=False prevents cleanup from leaving either configured log tree.
    for current_dir, dir_names, file_names in os.walk(root, topdown=False, followlinks=False):
        current_path = Path(current_dir)

        for file_name in file_names:
            file_path = current_path / file_name
            try:
                if file_path.is_symlink():
                    continue
                stat = file_path.stat()
                if not file_path.is_file() or stat.st_mtime >= cutoff_timestamp:
                    continue
                file_path.unlink()
                deleted_files += 1
                freed_bytes += stat.st_size
            except FileNotFoundError:
                # A logger/rotator may have moved the file concurrently.
                continue
            except OSError:
                LOGGER.exception("Failed to delete old log file: %s", file_path)

        for dir_name in dir_names:
            dir_path = current_path / dir_name
            try:
                if not dir_path.is_symlink():
                    dir_path.rmdir()
            except (FileNotFoundError, OSError):
                # Non-empty and concurrently used directories must remain.
                continue

    return deleted_files, freed_bytes


def cleanup_logs() -> None:
    cutoff_timestamp = time.time() - timedelta(days=RETENTION_DAYS).total_seconds()
    total_files = 0
    total_bytes = 0

    for root in LOG_ROOTS:
        deleted_files, freed_bytes = _cleanup_log_root(root, cutoff_timestamp)
        total_files += deleted_files
        total_bytes += freed_bytes
        LOGGER.info(
            "Log cleanup completed for %s: deleted_files=%d freed_bytes=%d",
            root,
            deleted_files,
            freed_bytes,
        )

    LOGGER.info(
        "Log cleanup summary: retention_days=%d deleted_files=%d freed_bytes=%d",
        RETENTION_DAYS,
        total_files,
        total_bytes,
    )


with DAG(
    dag_id="log_cleanup_daily",
    description="Delete Airflow and backend logs older than seven days",
    schedule="20 3 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(hours=1),
    tags=["maintenance", "logs"],
) as dag:
    PythonOperator(
        task_id="cleanup_logs_older_than_7_days",
        python_callable=cleanup_logs,
    )
