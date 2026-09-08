from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import Mock, patch

from django.test import TestCase

from bitrix24.models import BitrixDeal, BitrixCrmField, BitrixCrmDictionary, BitrixSyncState, BitrixStageHistory, BitrixStageInterval
from bitrix24.services.client import Bitrix24Client, Bitrix24ResponseError
from bitrix24.services.loaders.deals import load_deals, load_deal_categories, load_deal_stages
from bitrix24.services.loaders.references import load_crm_fields
from bitrix24.services.loaders.stage_history import load_stage_history
from bitrix24.services.calculators.stage_intervals import rebuild_stage_intervals


STAMP = datetime(2026, 9, 8, 10, tzinfo=timezone.utc)


def deal(**changes):
    return {"id": 7, "title": "Deal", "createdTime": "2019-01-01T12:00:00+03:00",
            "updatedTime": STAMP.isoformat(), "categoryId": 0, "stageId": "NEW",
            "leadId": 12, "opportunity": "123.45", "currencyId": "RUB", **changes}


class DealTests(TestCase):
    def test_initial_history_and_incremental_update(self):
        client = Mock()
        client.iter_pages.return_value = [[deal()]]
        load_deals(client)
        self.assertEqual(client.iter_pages.call_args.args[1]["filter"], {})
        row = BitrixDeal.objects.get(deal_id=7)
        self.assertEqual(row.lead_id, 12)
        self.assertEqual(row.opportunity, Decimal("123.45"))
        self.assertEqual(row.source_created_at.year, 2019)
        client.iter_pages.return_value = [[deal(stageId="C5:WON", categoryId=5, stageSemanticId="S")]]
        load_deals(client)
        self.assertEqual(client.iter_pages.call_args.args[1]["filter"][">=updatedTime"], (STAMP - timedelta(minutes=10)).isoformat())
        self.assertEqual(BitrixDeal.objects.count(), 1)
        row.refresh_from_db()
        self.assertEqual(row.category_id, 5)
        self.assertTrue(row.closed)

    def test_failure_keeps_cursor_and_replay_is_idempotent(self):
        client = Mock()
        client.iter_pages.return_value = [[deal()]]
        load_deals(client)
        def interrupted(*args):
            yield [deal(id=8, updatedTime=(STAMP + timedelta(hours=1)).isoformat())]
            raise Bitrix24ResponseError("test interruption")
        client.iter_pages.side_effect = interrupted
        with patch("analytics.services.bitrix_notify.send_bitrix_message"), self.assertRaises(Bitrix24ResponseError):
            load_deals(client)
        state = BitrixSyncState.objects.get(entity="deals")
        self.assertEqual(state.status, "failed")
        self.assertEqual(state.last_source_updated_at, STAMP)
        client.iter_pages.side_effect = None
        client.iter_pages.return_value = [[deal(), deal(id=8)]]
        load_deals(client)
        self.assertEqual(BitrixDeal.objects.count(), 2)

    def test_full_empty_response_preserves_existing_data(self):
        client = Mock()
        client.iter_pages.return_value = [[deal()]]
        load_deals(client)
        client.iter_pages.return_value = [[]]
        with patch("analytics.services.bitrix_notify.send_bitrix_message"), self.assertRaises(Bitrix24ResponseError):
            load_deals(client, mode="full")
        self.assertFalse(BitrixDeal.objects.get().is_deleted)
        with self.assertRaises(ValueError):
            load_deals(client, mode="full", date_from=STAMP)

    def test_categories_stages_and_field_namespaces(self):
        client = Mock()
        client.iter_pages.return_value = [[{"id": 0, "name": "Main", "isDefault": "Y"}, {"id": 5, "name": "Other"}]]
        load_deal_categories(client)
        client.iter_items.side_effect = lambda method, params: [{"STATUS_ID": "NEW", "NAME": "New"}]
        load_deal_stages(client)
        self.assertEqual(set(BitrixCrmDictionary.objects.values_list("entity_id", flat=True)), {"DEAL_STAGE", "DEAL_STAGE_5"})
        client.call.return_value = {"result": {"fields": {"UF_CRM_TEST": {"type": "string", "isDynamic": True}}}}
        load_crm_fields(client, entity_type_id=2)
        self.assertTrue(BitrixCrmField.objects.get(entity_type_id=2).is_custom)
        client.call.assert_called_with("crm.item.fields", {"entityTypeId": 2, "useOriginalUfNames": "Y"})

    def test_history_isolated_from_leads_and_replayed(self):
        BitrixStageHistory.objects.create(entity_type_id=1, entity_id=7, history_id=1, stage_id="LEAD", created_at=STAMP)
        client = Mock()
        client.iter_pages.return_value = [[
            {"ID": 1, "OWNER_ID": 7, "STAGE_ID": "NEW", "CATEGORY_ID": 0, "CREATED_TIME": STAMP.isoformat()},
            {"ID": 2, "OWNER_ID": 7, "STAGE_ID": "C5:WON", "CATEGORY_ID": 5, "STAGE_SEMANTIC_ID": "S", "CREATED_TIME": (STAMP + timedelta(hours=1)).isoformat()},
        ]]
        load_stage_history(client, entity_type_id=2)
        load_stage_history(client, entity_type_id=2)
        rebuild_stage_intervals(entity_type_id=2, calculated_at=STAMP + timedelta(hours=2))
        self.assertEqual(BitrixStageHistory.objects.filter(entity_type_id=2).count(), 2)
        self.assertEqual(BitrixStageHistory.objects.get(entity_type_id=1).stage_id, "LEAD")
        self.assertEqual(BitrixStageInterval.objects.get(entity_type_id=2, sequence_number=1).duration_seconds, 3600)
        self.assertEqual(BitrixStageHistory.objects.get(entity_type_id=2, history_id=2).category_id, 5)

    def test_category_response_pagination(self):
        client = object.__new__(Bitrix24Client)
        client.call = Mock(side_effect=[{"result": {"categories": [{"id": 0}]}, "next": 50},
                                        {"result": {"categories": [{"id": 5}]}}])
        self.assertEqual(list(client.iter_items("crm.category.list", {"entityTypeId": 2})), [{"id": 0}, {"id": 5}])
        self.assertEqual(client.call.call_args.args[1]["start"], 50)
