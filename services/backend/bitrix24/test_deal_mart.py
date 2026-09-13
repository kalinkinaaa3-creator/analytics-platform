from unittest.mock import Mock, patch

from django.test import TestCase
from django.core.cache import cache

from bitrix24.services.crm_marts import (
    TABLE, LEGACY_TABLE, REFS, MartReader, SnapshotChanged, publish,
)


class DealMartTests(TestCase):
    def setUp(self):
        cache.clear()

    def mart_client(self, *, empty=False):
        client = Mock()
        def execute(sql, args=None):
            if sql.startswith("SELECT engine"):
                return [("MergeTree", "published")]
            if empty:
                return []
            if "SELECT DISTINCT category_id," in sql:
                return [(2, "Sales", 20)]
            if "SELECT DISTINCT stage_key," in sql:
                return [("2:NEW", "NEW", "New", 2, "Sales", 20, 10, "P")]
            if "SELECT DISTINCT manager_id," in sql:
                return [(5, "Manager", "Department", 1), (6, "Untracked", "Other", 0)]
            if "SELECT DISTINCT source_id," in sql:
                return [("web", "Website"), ("", "")]
            return []
        client.execute.side_effect = execute
        return client

    def test_reference_values_come_from_analytic_records_without_legacy_tables(self):
        client = self.mart_client()
        reader = MartReader(client)
        self.assertEqual(reader.table, TABLE)
        self.assertEqual(reader.refs["stages"]["2:NEW"]["sort"], 10)
        self.assertEqual(reader.refs["categories"][0]["sort"], 20)
        self.assertEqual(reader.refs["users"][5]["full_name"], "Manager")
        self.assertEqual(set(reader.refs["tracking"]), {5})
        self.assertEqual(reader.refs["sources"], [{"source_id": "web", "source_name": "Website"}])
        self.assertFalse(any(LEGACY_TABLE in c.args[0] or REFS in c.args[0] for c in client.execute.call_args_list))

    def test_empty_publication_is_valid(self):
        reader = MartReader(self.mart_client(empty=True))
        self.assertEqual(reader.snapshot, "published")
        self.assertEqual(reader.refs["categories"], [])
        self.assertEqual(reader.select(), [])

    def test_snapshot_switch_while_reading_references_is_rejected(self):
        client = self.mart_client()
        execute = client.execute.side_effect
        calls = 0
        def changing(sql, args=None):
            nonlocal calls
            if sql.startswith("SELECT engine"):
                calls += 1
                return [("MergeTree", "old" if calls == 1 else "new")]
            return execute(sql, args)
        client.execute.side_effect = changing
        with self.assertRaises(SnapshotChanged):
            MartReader(client).refs

    def test_publication_migrates_view_and_preserves_legacy_physical_tables(self):
        client = Mock()
        client.execute.side_effect = lambda sql, *args: (
            [(0,)] if sql.startswith("SELECT count()") else
            [("View", "")] if sql.startswith("SELECT engine") else []
        )
        with patch("bitrix24.services.crm_marts.get_clickhouse_client", return_value=client):
            self.assertEqual(publish(), 0)
        sqls = [c.args[0] for c in client.execute.call_args_list]
        rename = next(sql for sql in sqls if sql.startswith("RENAME TABLE"))
        self.assertIn(f"{TABLE} TO {TABLE}_backup_", rename)
        self.assertFalse(any(LEGACY_TABLE in sql or REFS in sql for sql in sqls))
        create = next(sql for sql in sqls if sql.startswith("CREATE TABLE"))
        self.assertIn("COMMENT '", create)
        self.assertIn("manager_tracked UInt8", create)

    def test_failed_build_never_replaces_published_table(self):
        client = Mock()
        with patch("bitrix24.services.crm_marts.get_clickhouse_client", return_value=client), patch(
            "bitrix24.services.crm_marts.source.references", side_effect=RuntimeError("build failed")
        ), self.assertRaisesRegex(RuntimeError, "build failed"):
            publish()
        sqls = [c.args[0] for c in client.execute.call_args_list]
        self.assertFalse(any(sql.startswith(("EXCHANGE", "RENAME")) for sql in sqls))
        self.assertTrue(sqls[-1].startswith(f"DROP TABLE IF EXISTS {TABLE}_staging_"))
