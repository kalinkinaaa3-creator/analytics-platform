from django.test import SimpleTestCase

from context_analytics.services.clickhouse import LIVE_TABLES, _validate_staged_tables
from context_analytics.services.metrika import ContextMetrikaClient
from context_analytics.services.warehouse import _nullable_float, _nullable_int
from seo_analytics.services.client import MetrikaClient


class ContextStagingTests(SimpleTestCase):
    def test_accepts_only_expected_generated_staging_names(self):
        tables = {table: f"{table}__refresh_deadbeef" for table in LIVE_TABLES}

        self.assertEqual(_validate_staged_tables(tables), tables)

    def test_rejects_incomplete_or_unsafe_staging_names(self):
        with self.assertRaises(ValueError):
            _validate_staged_tables({LIVE_TABLES[0]: f"{LIVE_TABLES[0]}__refresh_deadbeef"})

        tables = {table: f"{table}__refresh_deadbeef" for table in LIVE_TABLES}
        tables[LIVE_TABLES[0]] = f"{LIVE_TABLES[0]}__refresh_bad-name"
        with self.assertRaises(ValueError):
            _validate_staged_tables(tables)


class ContextMetrikaClientTests(SimpleTestCase):
    def test_context_and_seo_requests_use_different_cache_namespaces(self):
        self.assertEqual(ContextMetrikaClient.cache_prefix, "context:metrika:v1")
        self.assertEqual(MetrikaClient.cache_prefix, "seo:metrika:v1")


class ContextDirectMetricParsingTests(SimpleTestCase):
    def test_unavailable_metrics_are_not_converted_to_real_zeroes(self):
        self.assertIsNone(_nullable_int({"Bounces": "--"}, "Bounces"))
        self.assertIsNone(_nullable_float({"AvgImpressionPosition": "--"}, "AvgImpressionPosition"))

    def test_numeric_zero_remains_a_real_zero(self):
        self.assertEqual(_nullable_int({"Bounces": "0"}, "Bounces"), 0)
        self.assertEqual(_nullable_float({"AvgClickPosition": "0"}, "AvgClickPosition"), 0.0)
