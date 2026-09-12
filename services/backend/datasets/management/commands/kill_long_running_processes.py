import logging
from datetime import datetime, timedelta

import psutil
from django.core.management.base import BaseCommand

from analytics.services.bitrix_notify import send_bitrix_message


logger = logging.getLogger("maintenance.process_kill")
EXEMPT_MANAGEMENT_COMMANDS = frozenset({"load_yd_wordstat_api"})


class Command(BaseCommand):
    help = "Kill long-running internal Python processes"

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-hours",
            type=int,
            default=3,
        )
        parser.add_argument(
            "--base-path",
            type=str,
            default="/app",
        )

    def handle(self, *args, **options):
        max_runtime = timedelta(hours=options["max_hours"])
        base_path = options["base_path"]

        current_pid = psutil.Process().pid
        current_user = psutil.Process().username()

        killed = []
        checked = 0

        logger.info(
            "Process kill check started: base_path=%s, max_runtime=%s",
            base_path,
            max_runtime,
        )

        for process in psutil.process_iter(["pid", "name", "username", "create_time", "cmdline", "exe"]):
            try:
                if process.pid == current_pid:
                    continue

                if process.pid < 1000:
                    continue

                if process.info.get("username") != current_user:
                    continue

                cmdline = process.info.get("cmdline") or []
                cmdline_str = " ".join(cmdline) if cmdline else "-"

                exe_path = process.info.get("exe") or ""

                # Не убиваем uvicorn / основной Django server
                if "uvicorn" in cmdline_str:
                    continue

                if any(
                    str(arg).replace("\\", "/").rsplit("/", 1)[-1] == "manage.py"
                    and cmdline[index + 1] in EXEMPT_MANAGEMENT_COMMANDS
                    for index, arg in enumerate(cmdline[:-1])
                ):
                    logger.info("Skipping exempt management command: pid=%s, cmdline=%s", process.pid, cmdline_str)
                    continue

                # Убиваем только процессы, связанные с /app/manage.py или /app
                is_target = (
                    exe_path.startswith(base_path)
                    or any(str(arg).startswith(base_path) for arg in cmdline)
                    or "manage.py" in cmdline_str
                )

                if not is_target:
                    continue

                checked += 1

                start_time_dt = datetime.fromtimestamp(process.info["create_time"])
                runtime = datetime.now() - start_time_dt

                logger.info(
                    "Process found: pid=%s, name=%s, start=%s, runtime=%s, cmdline=%s",
                    process.pid,
                    process.info.get("name"),
                    start_time_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    runtime,
                    cmdline_str,
                )

                if runtime <= max_runtime:
                    continue

                logger.warning(
                    "Process runtime exceeded. Terminating: pid=%s, runtime=%s, cmdline=%s",
                    process.pid,
                    runtime,
                    cmdline_str,
                )

                try:
                    process.terminate()
                    process.wait(timeout=5)

                    message = (
                        f"[b]process_kill.py[/b]\n"
                        f"Процесс PID={process.pid} успешно завершён.\n"
                        f"Runtime: {runtime}\n"
                        f"CMDLINE: {cmdline_str}"
                    )

                    logger.info(message)
                    send_bitrix_message(
                        message,
                        logger_name="maintenance.process_kill",
                    )

                    killed.append(process.pid)

                except psutil.TimeoutExpired:
                    process.kill()

                    message = (
                        f"[b]process_kill.py[/b]\n"
                        f"Процесс PID={process.pid} был убит принудительно.\n"
                        f"Runtime: {runtime}\n"
                        f"CMDLINE: {cmdline_str}"
                    )

                    logger.warning(message)
                    send_bitrix_message(
                        message,
                        logger_name="maintenance.process_kill",
                    )

                    killed.append(process.pid)

                except Exception as exc:
                    message = (
                        f"[b]process_kill.py[/b]\n"
                        f"Ошибка при завершении процесса PID={process.pid}: {exc}\n"
                        f"CMDLINE: {cmdline_str}"
                    )

                    logger.exception(message)
                    send_bitrix_message(
                        message,
                        logger_name="maintenance.process_kill",
                    )

            except (psutil.AccessDenied, psutil.NoSuchProcess):
                continue

        result = {
            "checked": checked,
            "killed": killed,
            "killed_count": len(killed),
        }

        logger.info("Process kill check finished: %s", result)

        self.stdout.write(str(result))
