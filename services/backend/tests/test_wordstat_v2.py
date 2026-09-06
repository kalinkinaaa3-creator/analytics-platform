"""Run: python -m unittest tests.test_wordstat_v2 (Django + requests required)."""
import os
import unittest
from contextlib import nullcontext
from datetime import date
from unittest.mock import Mock, patch

os.environ["DJANGO_SETTINGS_MODULE"] = "tests.wordstat_settings"
import django
django.setup()

from django.db import connection
from django.test import override_settings

from datasets.models import (
    YdWordstatPhraseRef, YdWordstatDeviceRef, YdWordstatIplastRegionRef,
    YdWordstatRegionRef, YdWordstatRegionRaw, YdWordstatAllRaw, YdWordstatMacroregionRaw,
    YdWordstatDeviceRaw, YdWordstatIplastRaw, YdWordstatApiCheckpoint, YdWordstatApiQuota,
)
from datasets.services.external_api import yd_wordstat_api_loader as loader
from datasets.services.external_api import yd_wordstat_search_api_client as client
from datasets.services.external_api import yd_wordstat_contract as contract
from datasets.services.external_api.yd_wordstat_region_ref_loader import refresh_yd_wordstat_regions_from_api
from analytics.services import yd_wordstat_api_pipeline as pipeline

if connection.vendor != "sqlite" or connection.settings_dict["NAME"] != ":memory:":
    raise RuntimeError("Wordstat tests must only run against in-memory SQLite")

TODAY = date(2026, 9, 6)
MODELS = [YdWordstatPhraseRef, YdWordstatDeviceRef, YdWordstatIplastRegionRef,
          YdWordstatRegionRef, YdWordstatRegionRaw, YdWordstatAllRaw, YdWordstatDeviceRaw,
          YdWordstatIplastRaw, YdWordstatApiCheckpoint, YdWordstatApiQuota, YdWordstatMacroregionRaw]


def mappings():
    return [{"macroregion_label": name, "region_value": index + 1}
            for index, name in enumerate(sorted(contract.IPLAST_GROUPS))]


def tree():
    return {"regions": [{"id": str(item["region_value"]), "label": item["macroregion_label"]}
                        for item in mappings()]}


def response_for(phrase, start, finish, **kwargs):
    return {"results": [{"date": day.isoformat() + "T00:00:00Z", "count": "42"}
                        for day in contract.month_dates(start, finish)]}


class ContractTests(unittest.TestCase):
    def test_monthly_wire_format(self):
        body = contract.dynamics_body("test", date(2026, 8, 1), date(2026, 8, 31), ["all"], [1, 2])
        self.assertEqual(body["regions"], ["1", "2"])
        self.assertEqual(body["devices"], ["DEVICE_ALL"])
        self.assertEqual(body["period"], "PERIOD_MONTHLY")
        self.assertEqual(body["toDate"], "2026-08-31T00:00:00Z")

    def test_invalid_request_rejected_before_http(self):
        for devices, regions in [([], None), (["all", "phone"], None), (["unknown"], None), (["all"], []), (["all"], list(range(101)))]:
            with self.subTest(devices=devices, regions=regions), self.assertRaises(ValueError):
                contract.dynamics_body("test", date(2026, 8, 1), date(2026, 8, 31), devices, regions)

    def test_valid_zero_count_and_int64(self):
        data = {"results": [
            {"date": "2026-07-01T00:00:00Z", "count": "0"},
            {"date": "2026-08-01T00:00:00Z", "count": str(2**40)},
        ]}
        rows = contract.parse_monthly_results(data, date(2026, 7, 1), date(2026, 8, 31))
        self.assertEqual([row["count"] for row in rows], [0, 2**40])

    def test_bad_responses_are_not_empty_success(self):
        valid = {"date": "2026-08-01T00:00:00Z", "count": "42"}
        for data in [{}, {"dynamics": []}, {"results": []}, {"results": [valid, valid]},
                     {"results": [{**valid, "count": "oops"}]},
                     {"results": [{**valid, "date": "2026-08-02T00:00:00Z"}]},
                     {"results": [{**valid, "count": -1}]},
                     {"results": [{**valid, "count": 1.5}]}]:
            with self.subTest(data=data), self.assertRaises(ValueError):
                contract.parse_monthly_results(data, date(2026, 8, 1), date(2026, 8, 31))

    def test_groups_and_stable_membership_fingerprint(self):
        groups = contract.build_iplast_groups(mappings())
        self.assertEqual(groups, contract.build_iplast_groups(list(reversed(mappings()))))
        self.assertEqual(contract.validate_group_tree(groups, tree())["groups"], 7)
        with self.assertRaises(ValueError):
            contract.build_iplast_groups(mappings()[:-1])

    def test_1433_phrases_produce_15763_requests(self):
        config = {
            "phrases": [{"phrase": str(index), "feature": None, "category": None} for index in range(1433)],
            "devices": ["desktop", "phone", "tablet"],
            "groups": contract.build_iplast_groups(mappings()),
        }
        self.assertEqual(sum(1 for _ in loader.make_jobs(config)), 15763)

    def test_group_missing_region_and_overlap_are_rejected(self):
        groups = contract.build_iplast_groups(mappings())
        for invalid in [
            {"regions": tree()["regions"][:-1]},
            {"regions": [{**tree()["regions"][0], "children": [tree()["regions"][1]]}] + tree()["regions"][2:]},
            {"regions": tree()["regions"] + [tree()["regions"][0]]},
        ]:
            with self.assertRaises(ValueError):
                contract.validate_group_tree(groups, invalid)


class DatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with connection.schema_editor() as editor:
            for model in MODELS:
                editor.create_model(model)

    @classmethod
    def tearDownClass(cls):
        with connection.schema_editor() as editor:
            for model in reversed(MODELS):
                editor.delete_model(model)

    def setUp(self):
        for model in MODELS:
            model.objects.all().delete()
        YdWordstatPhraseRef.objects.create(phrase="test", feature="f", category="c")
        for device in ("desktop", "phone", "tablet"):
            YdWordstatDeviceRef.objects.create(device=device)
        YdWordstatIplastRegionRef.objects.bulk_create([YdWordstatIplastRegionRef(**item) for item in mappings()])

    def test_one_request_per_iplast_group_and_old_region_data_untouched(self):
        YdWordstatRegionRaw.objects.create(phrase="test", region_value=1, date=date(2020, 1, 1), count=99)
        config = loader.get_configuration()
        self.assertEqual(len(list(loader.make_jobs(config))), 11)
        with patch.object(loader, "fetch_dynamics", side_effect=response_for) as fetch:
            result = loader.run_source("region", TODAY, config)
        self.assertEqual(fetch.call_count, 7)
        for call, group in zip(fetch.call_args_list, config["groups"]):
            self.assertEqual(call.kwargs["regions"], group["regions"])
        self.assertEqual(result["pairs"], 7)
        self.assertEqual(YdWordstatRegionRaw.objects.get().count, 99)
        self.assertEqual(YdWordstatApiCheckpoint.objects.count(), 7)

    def test_resume_skips_saved_groups(self):
        config = loader.get_configuration()
        job = next(loader.make_jobs(config, "region"))
        with patch.object(loader, "fetch_dynamics", side_effect=response_for):
            loader.load_job(job, TODAY)
        with patch.object(loader, "fetch_dynamics", side_effect=response_for) as fetch:
            loader.run_source("region", TODAY, config)
        self.assertEqual(fetch.call_count, 6)

    def test_incomplete_response_preserves_previous_data_and_checkpoint(self):
        job = next(loader.make_jobs(loader.get_configuration(), "region"))
        YdWordstatIplastRaw.objects.create(**job.data_filters, date=date(2026, 8, 1), count=99)
        with patch.object(loader, "fetch_dynamics", return_value={"results": []}), self.assertRaises(ValueError):
            loader.load_job(job, TODAY)
        self.assertEqual(YdWordstatIplastRaw.objects.get().count, 99)
        self.assertFalse(YdWordstatApiCheckpoint.objects.exists())

    def test_transaction_rolls_back_on_insert_failure(self):
        job = next(loader.make_jobs(loader.get_configuration(), "region"))
        YdWordstatIplastRaw.objects.create(**job.data_filters, date=date(2026, 8, 1), count=99)
        with patch.object(loader, "fetch_dynamics", side_effect=response_for), \
             patch.object(YdWordstatIplastRaw.objects, "bulk_create", side_effect=RuntimeError("insert failed")), \
             self.assertRaises(RuntimeError):
            loader.load_job(job, TODAY)
        self.assertEqual(YdWordstatIplastRaw.objects.get().count, 99)
        self.assertFalse(YdWordstatApiCheckpoint.objects.exists())

    def test_changed_group_reloads_history(self):
        config = loader.get_configuration()
        job = next(loader.make_jobs(config, "region"))
        with patch.object(loader, "fetch_dynamics", side_effect=response_for):
            loader.load_job(job, TODAY)
        YdWordstatIplastRegionRef.objects.create(region_value=99, macroregion_label=job.dimension)
        new_job = next(loader.make_jobs(loader.get_configuration(), "region"))
        self.assertNotEqual(job.fingerprint, new_job.fingerprint)
        self.assertEqual(loader.job_period(new_job, TODAY)["date_start"], date(2018, 1, 1))
        with patch.object(loader, "fetch_dynamics", side_effect=response_for):
            loader.load_job(new_job, TODAY)
        self.assertFalse(YdWordstatIplastRaw.objects.exclude(group_fingerprint=new_job.fingerprint).exists())

    def test_hole_or_duplicate_invalidates_checkpoint(self):
        job = next(loader.make_jobs(loader.get_configuration(), "all"))
        with patch.object(loader, "fetch_dynamics", side_effect=response_for):
            loader.load_job(job, TODAY)
        self.assertTrue(loader.checkpoint_is_complete(job, TODAY))
        YdWordstatAllRaw.objects.filter(date=date(2026, 7, 1)).delete()
        self.assertFalse(loader.checkpoint_is_complete(job, TODAY))
        YdWordstatAllRaw.objects.filter(date=date(2019, 1, 1)).delete()
        self.assertEqual(loader.job_period(job, TODAY)["date_start"], date(2019, 1, 1))

    def test_plan_makes_no_http_calls_or_writes(self):
        with patch.object(client.requests, "post", side_effect=AssertionError("HTTP forbidden")):
            result = loader.estimate_load(today=TODAY)
        self.assertEqual(result["requests_full_pass"], 11)
        self.assertEqual(result["requests_pending"], 11)
        self.assertFalse(YdWordstatApiQuota.objects.exists())
        self.assertFalse(YdWordstatApiCheckpoint.objects.exists())

    @override_settings(YD_WORDSTAT_REQUESTS_PER_SECOND=2, YD_WORDSTAT_REQUESTS_PER_HOUR=3)
    def test_quota_persists_and_waits_for_both_windows(self):
        clock = [10000.0]
        def sleep(seconds):
            clock[0] += seconds
        with patch.object(client.time, "time", side_effect=lambda: clock[0]), patch.object(client.time, "sleep", side_effect=sleep):
            client.reserve_request()
            client.reserve_request()
            client.reserve_request()
            self.assertGreaterEqual(clock[0], 10001)
            client.reserve_request()
        self.assertGreaterEqual(clock[0], 13600)
        self.assertEqual(YdWordstatApiQuota.objects.count(), 1)

    def test_server_quota_wait_is_shared(self):
        with patch.object(client.time, "time", return_value=10000):
            client.block_quota(120)
            client.block_quota(10)
        self.assertEqual(YdWordstatApiQuota.objects.get().blocked_until, 10120)

    def test_reference_refresh_preserves_selection_and_hierarchy(self):
        YdWordstatRegionRef.objects.create(region_value=1, country_label="Россия", macroregion_label="business", region_label="old")
        with patch("datasets.services.external_api.yd_wordstat_region_ref_loader.fetch_yd_wordstat_regions_tree", return_value=tree()):
            refresh_yd_wordstat_regions_from_api()
        obj = YdWordstatRegionRef.objects.get()
        self.assertEqual(obj.region_label, tree()["regions"][0]["label"])
        self.assertEqual(obj.macroregion_label, "business")
        with patch("datasets.services.external_api.yd_wordstat_region_ref_loader.fetch_yd_wordstat_regions_tree", return_value={"regions": []}), self.assertRaises(ValueError):
            refresh_yd_wordstat_regions_from_api()
        self.assertEqual(YdWordstatRegionRef.objects.count(), 1)

    def test_incomplete_combinations_block_publication(self):
        config = loader.get_configuration()
        with override_settings(YD_WORDSTAT_V2_LOAD_ENABLED=True), \
             patch.object(pipeline, "wordstat_pipeline_lock", return_value=nullcontext()), \
             patch.object(pipeline, "_notify"), \
             patch.object(pipeline, "check_regions", return_value={}), \
             patch.object(pipeline, "load_job", return_value={"saved": 0, "skipped": 1}), \
             self.assertRaisesRegex(RuntimeError, "incomplete"):
            pipeline.run_yd_wordstat_api_pipeline()
        self.assertFalse(loader.validate_download(config, TODAY)["ok"])

    def test_probe_comparison_detects_missing_regions_and_duplicates(self):
        from datasets.management.commands.probe_yd_wordstat_v2 import compare_stored_regions

        rows = [{"date": date(2026, 8, 1), "count": 42}]
        for region in (1, 2):
            YdWordstatRegionRaw.objects.create(phrase="test", region_value=region, date=rows[0]["date"], count=21)
        result = compare_stored_regions("test", [1, 2], rows)[0]
        self.assertTrue(result["stored_complete"])
        self.assertEqual(result["difference"], 0)
        self.assertFalse(compare_stored_regions("test", [1, 2, 3], rows)[0]["stored_complete"])
        YdWordstatRegionRaw.objects.create(phrase="test", region_value=1, date=rows[0]["date"], count=21)
        self.assertFalse(compare_stored_regions("test", [1, 2], rows)[0]["stored_complete"])

    def test_sql_uses_api_aggregate_without_adding_legacy_regions(self):
        from analytics.services import yd_wordstat_rebuild_sql as rebuild

        job = next(loader.make_jobs(loader.get_configuration(), "region"))
        YdWordstatIplastRaw.objects.create(**job.data_filters, date=date(2026, 8, 1), count=42)
        YdWordstatRegionRaw.objects.create(phrase="test", date=date(2026, 8, 1), count=1000, macroregion_iplast=job.dimension)
        cursor = Mock()
        cursor.fetchone.return_value = [1]
        db = Mock()
        db.cursor.return_value.__enter__ = Mock(return_value=cursor)
        db.cursor.return_value.__exit__ = Mock(return_value=False)
        with patch.object(rebuild, "connection", db), patch.object(rebuild.transaction, "atomic", return_value=nullcontext()):
            rebuild.rebuild_yd_wordstat_for_from_raw_sql(region_source="iplast")
        statements = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertFalse(any("UPDATE yd_wordstat_region " in sql for sql in statements))
        insert = next(sql for sql in statements if "INSERT INTO yd_wordstat_macroregion_label" in sql)
        connection.connection.create_function("NOW", 0, lambda: "2026-09-06 00:00:00")
        with connection.cursor() as real_cursor:
            real_cursor.execute(insert)
        result = YdWordstatMacroregionRaw.objects.get()
        self.assertEqual(result.count, 42)
        self.assertEqual(result.macroregion_label, job.dimension)


class MigrationTests(unittest.TestCase):
    def test_additive_migrations_preserve_existing_statistics(self):
        from django.db.migrations.loader import MigrationLoader

        graph = MigrationLoader(None)
        state = graph.project_state([("datasets", "0062_remove_product_control_and_add_classification_article")])
        names = ["YdWordstatAllRaw", "YdWordstatDeviceRaw", "YdWordstatFor", "YdWordstatMacroregionRaw"]
        with connection.schema_editor() as editor:
            for name in names:
                editor.create_model(state.apps.get_model("datasets", name))
        try:
            state.apps.get_model("datasets", "YdWordstatAllRaw").objects.create(phrase="retained", date=date(2026, 1, 1), count=17)
            for migration_name in ["0063_wordstat_v2_iplast", "0064_wordstat_count_int64"]:
                with connection.schema_editor() as editor:
                    state = graph.get_migration("datasets", migration_name).apply(state, editor)
            self.assertEqual(YdWordstatAllRaw.objects.get().count, 17)
            self.assertEqual(YdWordstatIplastRaw.objects.count(), 0)
        finally:
            with connection.schema_editor() as editor:
                for name in ["YdWordstatIplastRaw", "YdWordstatApiCheckpoint", "YdWordstatApiQuota"] + names:
                    model = state.apps.get_model("datasets", name)
                    if model._meta.db_table in connection.introspection.table_names():
                        editor.delete_model(model)


class ClientTests(unittest.TestCase):
    def request(self):
        return client.fetch_dynamics("test", date(2026, 8, 1), date(2026, 8, 31), regions=[1, 2])

    def test_nonretryable_auth_errors(self):
        for status in (400, 401, 403):
            response = Mock(status_code=status, headers={})
            with patch.object(client.requests, "post", return_value=response) as post, \
                 patch.object(client, "reserve_request"), \
                 self.assertRaises(client.YdWordstatSearchApiError):
                self.request()
            self.assertEqual(post.call_count, 1)

    def test_retry_503_then_success(self):
        success = Mock(status_code=200)
        success.json.return_value = {"results": []}
        with patch.object(client.requests, "post", side_effect=[Mock(status_code=503, headers={}), success]) as post, \
             patch.object(client, "reserve_request") as reserve, patch.object(client.time, "sleep"):
            self.request()
        self.assertEqual(post.call_count, 2)
        self.assertEqual(reserve.call_count, 2)
        self.assertEqual(post.call_args.kwargs["json"]["regions"], ["1", "2"])
        self.assertEqual(post.call_args.kwargs["json"]["folderId"], "test-folder")

    def test_429_honors_retry_after(self):
        success = Mock(status_code=200)
        success.json.return_value = {"results": []}
        with patch.object(client.requests, "post", side_effect=[Mock(status_code=429, headers={"Retry-After": "120"}), success]), \
             patch.object(client, "reserve_request"), patch.object(client, "block_quota") as block:
            self.request()
        block.assert_called_once_with(120)

    def test_v2_load_is_opt_in(self):
        with self.assertRaisesRegex(RuntimeError, "disabled"):
            pipeline.run_yd_wordstat_api_pipeline()


if __name__ == "__main__":
    unittest.main()
