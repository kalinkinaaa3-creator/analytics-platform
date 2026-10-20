from io import StringIO
from unittest.mock import patch

from django.core.management.base import CommandError
from django.test import SimpleTestCase

from datasets.management.commands.load_base_products import Command
from datasets.services.iprice_workspace import IPriceWorkspace


class BaseCommandRoutingTests(SimpleTestCase):
    def run_command(self, organization, failed=0):
        result = dict.fromkeys(
            ("offers", "parsed", "created", "updated", "inactivated",
             "success", "failed", "inactive", "skipped", "properties", "prices"), 0,
        )
        result["failed"] = failed
        module = "datasets.management.commands.load_base_products."
        with patch(module + "load_base_products", return_value=result) as load, \
             patch(module + "sync_parser_source_images") as legacy_images, \
             patch(module + "sync_iprice_product_images") as scoped_images:
            command = Command(stdout=StringIO())
            if failed:
                with self.assertRaises(CommandError):
                    command.handle(organization=organization, limit=None)
            else:
                command.handle(organization=organization, limit=None)
            return load, legacy_images, scoped_images

    def test_default_remains_iplast(self):
        command = Command()
        options = command.create_parser("manage.py", "load_base_products").parse_args([])
        self.assertEqual(options.organization, "iplast")
        load, legacy, scoped = self.run_command(options.organization)
        load.assert_called_once_with(limit=None)
        legacy.assert_called_once_with("base")
        scoped.assert_not_called()

    def test_select_market_never_syncs_legacy_images(self):
        load, legacy, scoped = self.run_command("select-market")
        workspace = IPriceWorkspace("select-market")
        load.assert_called_once_with(limit=None, workspace=workspace)
        scoped.assert_called_once_with(source="base", workspace=workspace)
        legacy.assert_not_called()

    def test_partial_failure_fails_airflow_task(self):
        self.run_command("select-market", failed=1)
