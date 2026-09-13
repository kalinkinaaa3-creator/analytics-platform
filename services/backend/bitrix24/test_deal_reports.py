"""Regression cases for deal metrics, publication and actual closure history."""
from datetime import datetime, date, timedelta
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.db import connection
from unittest.mock import Mock, patch
from decimal import Decimal


from bitrix24.models import (BitrixDeal, BitrixDealCategory, BitrixCrmDictionary,
                            BitrixDepartment, BitrixUser, BitrixStageHistory)
from bitrix24.services.deal_repository import MOSCOW, references, deal_rows, enrich_rows
from bitrix24.services.deal_metrics import enrich_deal, metrics, panel
from bitrix24.services.crm_marts import MartReader, SnapshotChanged, publish


def stamp(month, day=1, year=2026):
    return datetime(year, month, day, tzinfo=MOSCOW)


class DealMetricsTests(TestCase):
    def test_closure_requires_final_matching_history_and_reopening_resets_it(self):
        stages = {"0:WON": {"name": "Отгрузка", "semantics": "S"}, "0:NEW": {"name": "Новая", "semantics": ""}}
        row = {"category_id": 0, "stage_id": "WON", "stage_semantic_id": "S", "source_created_at": stamp(1), "opportunity": 100}
        event = lambda i, month, stage, semantic: {"history_id": i, "created_at": stamp(month), "stage_id": stage, "stage_semantic_id": semantic, "category_id": 0}
        self.assertIsNone(enrich_deal(row, [], stages, stamp(6))["closed_at"])
        self.assertIsNone(enrich_deal(row, [event(1, 1, "NEW", "P")], stages, stamp(6))["closed_at"])
        history = [event(1, 1, "NEW", "P"), event(2, 2, "WON", "S"), event(3, 3, "NEW", "P"), event(4, 4, "WON", "S")]
        result = enrich_deal(row, history, stages, stamp(6))
        self.assertEqual(result["closed_at"], stamp(4))
        self.assertEqual(result["processing_duration_days"], 90)
        self.assertNotIn("cycle_days", result)
        self.assertNotIn("stage_days", result)
        running = enrich_deal({**row, "stage_id": "NEW", "stage_semantic_id": "P"}, history[:3], stages, stamp(6))
        self.assertEqual(running["processing_duration_days"], 151)
        self.assertIsNone(enrich_deal(row, [], stages, stamp(6))["processing_duration_days"])
        self.assertIsNone(enrich_deal({**row, "stage_id": "NEW", "stage_semantic_id": "P"}, history[:3], stages, stamp(6))["closed_at"])


class DealRepositoryTests(TestCase):
    models = [BitrixDeal, BitrixDealCategory, BitrixCrmDictionary,
              BitrixDepartment, BitrixUser, BitrixStageHistory]

    def setUp(self):
        BitrixDepartment.objects.create(department_id=100, name="Отдел")
        BitrixUser.objects.create(user_id=10, full_name="Менеджер", primary_department_id=100)
        for cid in (0, 2, 7):
            BitrixDealCategory.objects.create(category_id=cid, name=f"Воронка {cid}", sort=cid)
            entity = "DEAL_STAGE" if cid == 0 else f"DEAL_STAGE_{cid}"
            for stage, semantic, sort in [("NEW", "", 10), ("WON", "S", 20), ("LOSE", "F", 30)]:
                BitrixCrmDictionary.objects.create(entity_id=entity, status_id=stage, name=stage, semantics=semantic, sort=sort)
        self.filters = {"date_start": date(2026, 1, 1), "date_end": date(2026, 1, 31), "category_ids": [0, 2],
                        "department_names": [], "manager_ids": [], "source_ids": [], "stage_keys": [], "results": [],
                        "exclude_untracked_department": True, "group_by": "month"}

    def deal(self, id, lead_id, category=0, month=2, stage="NEW", semantic="P", deleted=False):
        BitrixDeal.objects.create(deal_id=id, lead_id=lead_id, category_id=category, source_created_at=stamp(month),
                                  assigned_by_id=10, stage_id=stage, stage_semantic_id=semantic, opportunity=100,
                                  currency_id="RUB", is_deleted=deleted)

    def test_deal_date_filters_stage_composite_keys_and_closed_conversion(self):
        self.deal(1, None, month=1, stage="WON", semantic="S")
        self.deal(2, None, month=1, category=2, stage="WON", semantic="S")
        self.deal(3, None, month=1, stage="LOSE", semantic="F")
        self.deal(4, None, month=1)
        self.deal(5, None, month=2)
        refs = references()
        rows = deal_rows(self.filters, refs)
        self.assertEqual(len(rows), 4)
        self.assertAlmostEqual(metrics(rows)["conversion"], 200 / 3)
        self.assertEqual([r["deal_id"] for r in deal_rows({**self.filters, "stage_keys": ["2:WON"]}, refs)], [2])
        result = panel(rows, [], [], "stages", "month", refs["stages"])
        self.assertEqual([r["key"] for r in result["summary"]], ["0:NEW", "0:WON", "0:LOSE", "2:WON"])
        self.assertEqual(result["total"]["total"], 4)

    def test_publication_checks_counts_before_atomic_exchange(self):
        self.deal(11, 1)
        client = Mock()
        client.execute.side_effect = lambda sql, *args: ([(1,)] if sql.startswith("SELECT count()") else [("MergeTree", "old")] if sql.startswith("SELECT engine") else [])
        with patch("bitrix24.services.crm_marts.get_clickhouse_client", return_value=client):
            self.assertEqual(publish(chunk_size=1), 1)
        calls = [call.args[0] for call in client.execute.call_args_list]
        self.assertEqual(sum(sql.startswith("EXCHANGE TABLES") for sql in calls), 1)
        self.assertLess(next(i for i, sql in enumerate(calls) if sql.startswith("SELECT count()")), next(i for i, sql in enumerate(calls) if sql.startswith("EXCHANGE TABLES")))
        client.reset_mock()
        client.execute.side_effect = lambda sql, *args: ([(0,)] if sql.startswith("SELECT count()") else [(1,)] if sql.startswith("EXISTS TABLE") else [])
        with patch("bitrix24.services.crm_marts.get_clickhouse_client", return_value=client), self.assertRaisesRegex(RuntimeError, "row count"):
            publish(chunk_size=1)
        self.assertFalse(any(c.args[0].startswith(("RENAME TABLE", "EXCHANGE TABLES")) for c in client.execute.call_args_list))

    def test_snapshot_detects_replacement(self):
        refs = references()
        client = Mock()
        from bitrix24.services.crm_marts import reference_rows
        client.execute.side_effect = [[("View", "")], [(1,)], [(1,)], [("old",)], reference_rows(refs, "old"), [("new",)], [("old",)]]
        reader = MartReader(client)
        with self.assertRaises(SnapshotChanged):
            reader.check()

    def test_analytics_extracts_only_used_json_values_with_original_fallback(self):
        payloads = [
            {"isReturnCustomer": True, "IS_RETURN_CUSTOMER": "N"},
            {"IS_RETURN_CUSTOMER": "Y"},
            {"isReturnCustomer": None, "IS_RETURN_CUSTOMER": "Y"},
            {},
        ]
        for index, payload in enumerate(payloads, 1):
            self.deal(index, None, month=1)
            BitrixDeal.objects.filter(deal_id=index).update(raw_payload={
                **payload, "UF_CRM_69B904B3E0AD1": "type-a",
                "UF_CRM_64254B7D4853D": "activity-b", "COMMENTS": "unused" * 10000,
            })
        refs = references()
        with CaptureQueriesContext(connection) as queries:
            rows = enrich_rows(BitrixDeal.objects.order_by("deal_id"), refs)
        self.assertEqual([row["is_return_customer"] for row in rows], [True, True, False, False])
        self.assertTrue(all(row["deal_type_id"] == "type-a" and row["activity_id"] == "activity-b" for row in rows))
        self.assertNotRegex(queries[0]["sql"], r'(?:SELECT |, )"bitrix24_deal"\."raw_payload"(?: AS |,)')
        self.assertTrue(all("raw_payload" not in row for row in rows))

    def test_stage_interval_rebuild_does_not_fetch_history_payload(self):
        from bitrix24.services.calculators.stage_intervals import rebuild_stage_intervals
        from bitrix24.models import BitrixStageInterval
        self.deal(1, None, month=1)
        for index, month in ((1, 1), (2, 2)):
            BitrixStageHistory.objects.create(
                entity_type_id=2, entity_id=1, history_id=index, stage_id="NEW" if index == 1 else "WON",
                created_at=stamp(month), raw_payload={"unused": "x" * 10000},
            )
        with CaptureQueriesContext(connection) as queries:
            count, affected = rebuild_stage_intervals(entity_type_id=2, calculated_at=stamp(3))
        self.assertEqual((count, affected), (2, {1}))
        self.assertEqual(list(BitrixStageInterval.objects.order_by("sequence_number").values_list("duration_seconds", "is_current")), [(31 * 86400, False), (28 * 86400, True)])
        self.assertTrue(all("raw_payload" not in query["sql"] for query in queries))


@override_settings(LEAD_GENERATION_REPORT_CACHE_TIMEOUT=900)
class PublicationLockTests(TestCase):
    def test_second_launch_does_not_publish_or_release_another_lock(self):
        from bitrix24.management.commands import sync_bitrix24_clickhouse as command
        from django.core.management.base import CommandError
        with patch.object(command, "acquire_refresh_cache_lock", return_value=False), patch.object(command, "sync_lead_analytics_to_clickhouse") as publish_mock, patch.object(command, "cache") as cache_mock:
            with self.assertRaises(CommandError):
                command.Command().handle(chunk_size=500)
            publish_mock.assert_not_called()
            cache_mock.delete.assert_not_called()

    def test_publication_failure_releases_lock_and_does_not_notify_success(self):
        from bitrix24.management.commands import sync_bitrix24_clickhouse as command
        cursor = Mock()
        cursor.fetchone.return_value = (True,)
        connection = Mock()
        connection.cursor.return_value.__enter__ = Mock(return_value=cursor)
        connection.cursor.return_value.__exit__ = Mock(return_value=False)
        with patch.object(command, "acquire_refresh_cache_lock", return_value=True), patch.object(command, "connection", connection), patch.object(command, "cache") as cache_mock, patch.object(command, "notify_dashboard_updated") as notify, patch.object(command, "sync_lead_analytics_to_clickhouse", side_effect=RuntimeError("test failure")):
            with self.assertRaisesRegex(RuntimeError, "test failure"):
                command.Command().handle(chunk_size=500)
            cache_mock.delete.assert_called_once_with(command.LOCK_KEY)
            self.assertIn("pg_advisory_unlock", cursor.execute.call_args.args[0])
            notify.assert_not_called()

    def test_success_event_is_sent_after_both_locks_are_released(self):
        from bitrix24.management.commands import sync_bitrix24_clickhouse as command
        events = []
        cursor = Mock()
        cursor.fetchone.return_value = (True,)
        cursor.execute.side_effect = lambda sql, params: events.append("unlock" if "pg_advisory_unlock" in sql else "lock")
        connection = Mock()
        connection.cursor.return_value.__enter__ = Mock(return_value=cursor)
        connection.cursor.return_value.__exit__ = Mock(return_value=False)
        with patch.object(command, "acquire_refresh_cache_lock", return_value=True), patch.object(command, "connection", connection), patch.object(command, "cache") as cache_mock, patch.object(command, "notify_dashboard_updated", side_effect=lambda *a, **k: events.append("socket")), patch.object(command, "sync_lead_analytics_to_clickhouse", return_value=2), patch.object(command, "rebuild_mart_safely"):
            cache_mock.delete.side_effect = lambda key: events.append("cache-unlock")
            command.Command().handle(chunk_size=500)
        self.assertLess(events.index("cache-unlock"), events.index("socket"))
        self.assertLess(events.index("unlock"), events.index("socket"))
