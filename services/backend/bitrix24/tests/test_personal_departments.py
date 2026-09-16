from datetime import date
from dataclasses import replace
from unittest import TestCase
from unittest.mock import Mock

from bitrix24.services.crm_marts import MartReader
from bitrix24.services.dashboard_query import LeadDashboardFilters, LeadDashboardQuery, UNTRACKED_DEPARTMENT_NAME
from bitrix24.services.lead_mart_query import PublishedLeadQuery
from bitrix24.services.personal_departments import department_mapping, personal_tracking


class PersonalDepartmentTests(TestCase):
    def setUp(self):
        self.mapping = department_mapping([
            {"manager_id": 1079, "display_name": "Филиал МСК", "selected": True},
            {"manager_id": 1080, "display_name": "Другой филиал", "selected": True},
            {"manager_id": 1081, "display_name": "Дирекция", "selected": False},
        ])
        self.filters = LeadDashboardFilters(
            date_start=date(2026, 1, 1), date_end=date(2026, 9, 16),
            department_names=("Филиал МСК",), tracked_manager_ids=(1079, 1080),
            personal_departments=self.mapping,
        )

    def mart(self):
        mart = object.__new__(MartReader)
        mart.refs = {"tracking": {key: {"department_name": "Дирекция"} for key in (1079, 1080, 1081)},
                     "users": {}, "categories": [], "stages": {}, "sources": []}
        mart.client = Mock()
        mart.client.execute.side_effect = lambda sql, args: [(1079,), (1080,), (1081,)] if "DISTINCT manager_id " in sql else []
        return mart

    def deal_filters(self, names, exclude=True):
        return {"date_start": self.filters.date_start, "date_end": self.filters.date_end,
                "department_names": names, "personal_departments": self.mapping,
                "tracked_manager_ids": [1079, 1080], "exclude_untracked_department": exclude}

    def test_same_source_department_splits_into_personal_groups(self):
        mart = self.mart()
        filters = self.deal_filters(["Филиал МСК"])
        _, args = mart.conditions(filters)
        self.assertEqual(args["departments"], (1079,))
        self.assertEqual(set(personal_tracking(mart.refs, filters)), {1079, 1080})
        self.assertEqual(mart.refs["tracking"][1079]["department_name"], "Дирекция")

    def test_deal_mixed_selection_keeps_untracked_separate(self):
        parts, args = self.mart().conditions(self.deal_filters(["Филиал МСК", UNTRACKED_DEPARTMENT_NAME], False))
        self.assertEqual(args["departments"], (1079,))
        self.assertEqual(set(args["tracked"]), {1079, 1080})
        self.assertIn("OR manager_id NOT IN", " ".join(parts))

    def test_deal_facet_has_no_original_department(self):
        result = self.mart().options(self.deal_filters(["Филиал МСК"]))
        self.assertEqual({r["department_name"] for r in result["departments"]},
                         {"Филиал МСК", "Другой филиал", UNTRACKED_DEPARTMENT_NAME})

    def test_lead_filter_and_facets_use_same_manager_groups(self):
        where, args = LeadDashboardQuery._where(self.filters)
        self.assertIn("multiIf", where)
        index = next(key.rsplit("_", 1)[1] for key, value in args.items() if key.startswith("personal_name_") and value == "Филиал МСК")
        self.assertEqual(args[f"personal_ids_{index}"], (1079,))
        query = object.__new__(PublishedLeadQuery)
        query._dict_rows = Mock(return_value=[])
        query.options(self.filters)
        sql, facet_args = query._dict_rows.call_args_list[0].args
        self.assertIn("AS effective_department", sql)
        self.assertEqual(facet_args[f"personal_ids_{index}"], (1079,))

    def test_comparison_periods_preserve_personal_groups(self):
        query = LeadDashboardQuery(client=Mock())
        query.dimension_dynamics = Mock(return_value=[])
        query.cards = Mock(return_value={})
        query.build(self.filters)
        self.assertEqual(query.dimension_dynamics.call_count, 12)
        for call in query.dimension_dynamics.call_args_list:
            self.assertEqual(call.args[0].personal_departments, self.mapping)

    def test_detail_and_export_rows_use_personal_names(self):
        query = object.__new__(PublishedLeadQuery)
        flags = {key: 0 for key in ("is_return_customer", "is_apm", "is_low_quality", "is_unmapped", "is_processed", "is_final")}
        query._dict_rows = Mock(return_value=[{"manager_id": 1079, **flags}, {"manager_id": 1081, **flags}])
        query.check = Mock()
        rows = list(query.export_rows(self.filters, {}))
        self.assertEqual([r.department_name for r in rows], ["Филиал МСК", UNTRACKED_DEPARTMENT_NAME])

    def test_empty_tracking_and_untracked_only(self):
        filters = replace(self.filters, personal_departments=(), tracked_manager_ids=(),
                          department_names=(UNTRACKED_DEPARTMENT_NAME,), exclude_untracked_department=False)
        where, args = LeadDashboardQuery._where(filters)
        self.assertNotIn("multiIf", where)
        self.assertEqual(args["personal_untracked"], UNTRACKED_DEPARTMENT_NAME)
        query = object.__new__(PublishedLeadQuery)
        query._dict_rows = Mock(return_value=[])
        query.options(personal_departments=())
        self.assertIn("%(personal_untracked)s AS effective_department", query._dict_rows.call_args_list[0].args[0])
