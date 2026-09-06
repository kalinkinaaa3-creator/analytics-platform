from io import BytesIO
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, TestCase, override_settings
from openpyxl import Workbook

from seo_analytics.models import SeoBrandMask, SeoGoal
from seo_analytics.services.configuration import (
    CONFIG_BRANDS,
    CONFIG_GOALS,
    build_configuration_workbook,
    load_configuration,
)
from seo_analytics.services.client import MetrikaClient
from seo_analytics.services.clickhouse import SEO_LIVE_TABLES, _validate_seo_staged_tables
from seo_analytics.services.export import _definition
from seo_analytics.services.goals import sync_goal_catalog
from seo_analytics.services.warehouse_reporting import _engine_group_expression


class SeoWarehouseReportingTests(SimpleTestCase):
    def test_engine_group_expression_is_safe_for_parameterized_query(self):
        expression = _engine_group_expression({})
        rendered = (f"SELECT {expression} WHERE month >= %(date_from)s") % {
            "date_from": "2026-01-01",
        }

        self.assertIn("LIKE '%google%'", rendered)
        self.assertIn("LIKE '%yandex%'", rendered)

    def test_conversion_exports_use_their_own_numerator_and_denominator(self):
        self.assertIn(
            "goal_reaches*100.0/visits",
            _definition("conversions")["select"],
        )
        self.assertIn(
            "goal_users*100.0/users",
            _definition("unique-conversions")["select"],
        )

    def test_accepts_only_expected_generated_staging_names(self):
        tables = {table: f"{table}__refresh_deadbeef" for table in SEO_LIVE_TABLES}
        self.assertEqual(_validate_seo_staged_tables(tables), tables)

        tables[SEO_LIVE_TABLES[0]] = f"{SEO_LIVE_TABLES[0]}__refresh_bad-name"
        with self.assertRaises(ValueError):
            _validate_seo_staged_tables(tables)



class SeoConfigurationTests(TestCase):
    def _upload(self, kind=CONFIG_GOALS):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Загрузка"
        if kind == CONFIG_GOALS:
            sheet.append(["goal_id", "Наименование для отражения"])
            sheet.append([500791856, "Формы с сайта"])
            sheet.append([234432026, "КЦ — Все целевые действия"])
        else:
            sheet.append(["Брендовая маска"])
            sheet.append(["iplast"])
        stream = BytesIO()
        workbook.save(stream)
        stream.seek(0)
        return stream

    def test_load_configuration_replaces_active_set(self):
        result = load_configuration(self._upload(), CONFIG_GOALS)
        self.assertEqual(result["goals"], 2)
        self.assertEqual(result["active_goals"], 2)
        self.assertTrue(SeoGoal.objects.get(external_id=500791856).is_active)
        self.assertTrue(SeoGoal.objects.get(external_id=234432026).is_active)
        masks = load_configuration(self._upload(CONFIG_BRANDS), CONFIG_BRANDS)
        self.assertEqual(masks["active_brand_masks"], 1)
        self.assertTrue(SeoBrandMask.objects.get(mask="iplast").is_active)

    def test_template_is_valid_workbook(self):
        SeoGoal.objects.create(external_id=1, name="Тест", is_active=True)
        stream = build_configuration_workbook(CONFIG_GOALS)
        self.assertGreater(len(stream.getvalue()), 1000)
        self.assertGreater(len(build_configuration_workbook(CONFIG_BRANDS).getvalue()), 1000)


class MetrikaClientTests(TestCase):
    @override_settings(
        YANDEX_METRIKA_TOKEN="test-token",
        YANDEX_METRIKA_COUNTER_ID="1",
        YANDEX_METRIKA_API_URL="https://api-metrika.yandex.net/",
        YANDEX_METRIKA_API_TIMEOUT=10,
        SEO_METRIKA_QUERY_CACHE_TIMEOUT=60,
    )
    @patch("seo_analytics.services.client.requests.get")
    def test_complex_query_retries_with_lower_accuracy(self, request_get):
        complex_response = Mock(status_code=400, text="Запрос слишком сложный")
        success_response = Mock(status_code=200, text="")
        success_response.json.return_value = {"data": [], "totals": [0]}
        accuracies = []

        def respond(*args, **kwargs):
            accuracies.append(kwargs["params"]["accuracy"])
            return complex_response if len(accuracies) == 1 else success_response

        request_get.side_effect = respond

        payload = MetrikaClient().table(
            report_key="test.complex",
            date1="2026-07-01",
            date2="2026-08-29",
            metrics="ym:s:visits",
        )

        self.assertEqual(payload["totals"], [0])
        self.assertEqual(request_get.call_count, 2)
        self.assertEqual(accuracies, ["high", "medium"])

    @override_settings(
        YANDEX_METRIKA_TOKEN="test-token",
        YANDEX_METRIKA_COUNTER_ID="1",
        YANDEX_METRIKA_API_URL="https://api-metrika.yandex.net/",
        YANDEX_METRIKA_API_TIMEOUT=10,
        SEO_METRIKA_QUERY_CACHE_TIMEOUT=60,
    )
    @patch("seo_analytics.services.client.MetrikaClient.table")
    def test_table_all_uses_offset_until_short_page(self, table):
        table.side_effect = [
            {"data": [{"id": 1}, {"id": 2}]},
            {"data": [{"id": 3}]},
        ]
        payload = MetrikaClient().table_all(
            report_key="complete", page_size=2, metrics="ym:s:visits"
        )
        self.assertEqual([row["id"] for row in payload["data"]], [1, 2, 3])
        self.assertEqual(table.call_args_list[0].kwargs["offset"], 1)
        self.assertEqual(table.call_args_list[1].kwargs["offset"], 3)


class SeoGoalCatalogTests(TestCase):
    def test_catalog_adds_new_goals_without_overwriting_display_name(self):
        existing = SeoGoal.objects.create(
            external_id=101, name="Название для отражения", source_name="Старое",
            is_active=True, is_available=True,
        )
        client = Mock()
        client.goals.return_value = [
            {"id": 101, "name": "Новое имя Метрики"},
            {"id": 202, "name": "Новая цель", "type": "composite", "steps": [
                {"id": 203, "name": "Шаг составной цели", "type": "action"},
            ]},
        ]
        result = sync_goal_catalog(client)
        existing.refresh_from_db()
        created = SeoGoal.objects.get(external_id=202)
        nested = SeoGoal.objects.get(external_id=203)
        self.assertEqual(result["received"], 3)
        self.assertEqual(existing.name, "Название для отражения")
        self.assertEqual(existing.source_name, "Новое имя Метрики")
        self.assertTrue(created.is_active)
        self.assertEqual(created.name, "Новая цель")
        self.assertEqual(nested.parent_external_id, 202)
        self.assertEqual(nested.nesting_level, 1)
        self.assertEqual(nested.goal_type, "action")
