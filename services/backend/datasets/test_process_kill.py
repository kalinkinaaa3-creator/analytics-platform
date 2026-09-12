from datetime import datetime, timedelta
from io import StringIO
from unittest import TestCase
from unittest.mock import Mock, patch

from datasets.management.commands import kill_long_running_processes as command


class ProcessKillTests(TestCase):
    def check_process(self, cmdline):
        process = Mock(pid=157691)
        process.info = {
            "username": "worker", "name": "python", "exe": "/usr/bin/python",
            "cmdline": cmdline,
            "create_time": (datetime.now() - timedelta(hours=24)).timestamp(),
        }
        current = Mock(pid=2000)
        current.username.return_value = "worker"
        with patch.object(command.psutil, "Process", return_value=current), patch.object(
            command.psutil, "process_iter", return_value=[process]
        ), patch.object(command, "send_bitrix_message") as notify:
            command.Command(stdout=StringIO()).handle(max_hours=3, base_path="/app")
        return process, notify

    def test_long_wordstat_load_is_exempt_for_relative_and_absolute_paths(self):
        for manage in ("manage.py", "/app/manage.py", r"C:\app\manage.py"):
            with self.subTest(manage=manage):
                process, notify = self.check_process(["python", manage, "load_yd_wordstat_api", "--verbosity", "2"])
                process.terminate.assert_not_called()
                process.kill.assert_not_called()
                notify.assert_not_called()

    def test_other_long_running_command_is_still_terminated(self):
        process, notify = self.check_process(["python", "manage.py", "another_load"])
        process.terminate.assert_called_once()
        notify.assert_called_once()

    def test_similar_command_name_is_not_exempt(self):
        process, _ = self.check_process(["python", "manage.py", "load_yd_wordstat_api_extra"])
        process.terminate.assert_called_once()

    def test_command_name_in_an_argument_does_not_exempt_another_command(self):
        process, _ = self.check_process(["python", "manage.py", "another_load", "--label", "load_yd_wordstat_api"])
        process.terminate.assert_called_once()
