"""Regression cases for cohort membership, 1:N and actual closure history."""
from datetime import datetime, date, timedelta
from django.test import TestCase


from bitrix24.models import (BitrixDeal, BitrixDealCategory, BitrixCrmDictionary, BitrixLead,
                            BitrixLeadAnalytics, BitrixManagerTracking, BitrixUser, BitrixStageHistory)
from bitrix24.services.deal_repository import MOSCOW, references, cohort_rows, deal_rows
from bitrix24.services.deal_metrics import enrich_deal, metrics, panel
from bitrix24.services import full_cycle


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
        self.assertEqual(result["cycle_days"], 90)
        self.assertIsNone(enrich_deal({**row, "stage_id": "NEW", "stage_semantic_id": "P"}, history[:3], stages, stamp(6))["closed_at"])


class DealRepositoryTests(TestCase):
    models = [BitrixDeal, BitrixDealCategory, BitrixCrmDictionary, BitrixLead, BitrixLeadAnalytics,
              BitrixManagerTracking, BitrixUser, BitrixStageHistory]

    def setUp(self):
        BitrixUser.objects.create(user_id=10, full_name="Менеджер")
        BitrixManagerTracking.objects.create(user_id=10, manager_name="Менеджер", department_name="Отдел")
        for cid in (0, 2, 7):
            BitrixDealCategory.objects.create(category_id=cid, name=f"Воронка {cid}", sort=cid)
            entity = "DEAL_STAGE" if cid == 0 else f"DEAL_STAGE_{cid}"
            for stage, semantic, sort in [("NEW", "", 10), ("WON", "S", 20), ("LOSE", "F", 30)]:
                BitrixCrmDictionary.objects.create(entity_id=entity, status_id=stage, name=stage, semantics=semantic, sort=sort)
        self.filters = {"date_start": date(2026, 1, 1), "date_end": date(2026, 1, 31), "category_ids": [0, 2],
                        "department_names": [], "manager_ids": [], "source_ids": [], "stage_keys": [], "results": [],
                        "exclude_untracked_department": True, "group_by": "month"}

    def lead(self, id):
        BitrixLead.objects.create(lead_id=id, source_created_at=stamp(1), assigned_by_id=10)
        BitrixLeadAnalytics.objects.create(lead_id=id, source_created_at=stamp(1), manager_id=10,
                                         manager_name="Менеджер", department_name="Отдел", calculated_at=stamp(6))

    def deal(self, id, lead_id, category=0, month=2, stage="NEW", semantic="P", deleted=False):
        BitrixDeal.objects.create(deal_id=id, lead_id=lead_id, category_id=category, source_created_at=stamp(month),
                                  assigned_by_id=10, stage_id=stage, stage_semantic_id=semantic, opportunity=100,
                                  currency_id="RUB", is_deleted=deleted)

    def test_cohort_keeps_unconverted_leads_all_linked_deals_and_later_events(self):
        for id in (1, 2, 3, 4):
            self.lead(id)
        self.deal(11, 1, stage="WON", semantic="S")
        self.deal(12, 1, category=2)
        self.deal(13, 3, category=7)
        self.deal(14, 4, deleted=True)
        self.deal(15, None, month=1)
        BitrixStageHistory.objects.create(entity_type_id=2, history_id=1, entity_id=11, category_id=0,
                                         stage_id="WON", stage_semantic_id="S", created_at=stamp(3))
        refs = references()
        leads, deals, standalone = cohort_rows(self.filters, refs)
        self.assertEqual({r["lead_id"] for r in leads}, {1, 2, 4})
        self.assertEqual({r["deal_id"] for r in deals}, {11, 12})
        self.assertEqual([r["deal_id"] for r in standalone], [15])
        result = full_cycle.summary(leads, deals)
        self.assertEqual(result["converted_leads"], 1)
        self.assertEqual(result["deals"], 2)
        self.assertAlmostEqual(result["lead_to_deal"], 100 / 3)
        self.assertEqual(result["full_cycle_days"], 59)
        rows = full_cycle.detail_rows(leads, deals, standalone, self.filters)
        self.assertEqual(len(rows), 4)
        self.assertEqual({r.get("deal_id") for r in rows if r["lead_id"] == 1}, {11, 12})

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
