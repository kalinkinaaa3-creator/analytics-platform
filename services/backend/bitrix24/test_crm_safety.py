from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

from django.test import TestCase, SimpleTestCase
from openpyxl import load_workbook
from rest_framework.test import APIRequestFactory, force_authenticate

from bitrix24.api import views
from bitrix24.models import BitrixLead, BitrixDeal, BitrixDepartment, BitrixUser, BitrixCrmDictionary, BitrixCrmField, BitrixSyncRun
from bitrix24.services.client import Bitrix24ResponseError
from bitrix24.services.loaders.leads import load_leads
from bitrix24.services.loaders.deals import load_deals
from bitrix24.services.loaders.references import load_departments, load_users, load_crm_dictionaries, load_crm_fields
from bitrix24.services.export import export_leads_xlsx


class CrmAccessTests(SimpleTestCase):
    def test_denied_crm_user_cannot_read_lead_endpoints(self):
        factory = APIRequestFactory()
        for view in (views.LeadDashboardView, views.LeadDashboardFiltersView,
                     views.LeadDashboardRowsView, views.LeadDashboardExportView, views.LeadDashboardRefreshView):
            request = factory.post("/", {"date_start": "2026-01-01", "date_end": "2026-09-13"}, format="json")
            force_authenticate(request, user=Mock(is_authenticated=True))
            with self.subTest(view=view.__name__), patch("bitrix24.api.views._can_view_crm", return_value=False):
                self.assertEqual(view.as_view()(request).status_code, 403)

    def test_export_keeps_formula_like_text_as_text_and_numbers_as_numbers(self):
        item = SimpleNamespace(lead_id=1, title="=1+1", manager_name="=SUM(1,2)",
            is_return_customer=False, status_name="New", status_id="NEW", source_name="Web", source_id="web",
            activity_name="", source_created_at=None, source_updated_at=None, first_processing_at=None,
            calculated_at=None, opportunity=125.5, processing_duration_seconds=3600)
        path, _ = export_leads_xlsx(None, rows=[item])
        self.addCleanup(path.unlink)
        book = load_workbook(path)
        self.addCleanup(book.close)
        sheet = book.worksheets[0]
        self.assertEqual((sheet["B2"].value, sheet["B2"].data_type), ("=1+1", "s"))
        self.assertEqual(sheet["D2"].data_type, "s")
        self.assertEqual((sheet["K2"].value, sheet["K2"].data_type), (125.5, "n"))


class SafeLoadTests(TestCase):
    def setUp(self):
        self.notify = patch("analytics.services.bitrix_notify.send_bitrix_message").start()
        self.addCleanup(patch.stopall)

    def test_full_leads_reject_date_limits_before_request(self):
        client = Mock()
        with self.assertRaises(ValueError):
            load_leads(client, mode=BitrixSyncRun.Mode.FULL, date_from=datetime(2026, 9, 1, tzinfo=ZoneInfo("Europe/Moscow")))
        client.iter_pages.assert_not_called()

    def test_empty_full_leads_preserve_existing_and_mark_run_failed(self):
        BitrixLead.objects.create(lead_id=1)
        with self.assertRaises(Bitrix24ResponseError):
            load_leads(Mock(iter_pages=Mock(return_value=iter([[]]))), mode=BitrixSyncRun.Mode.FULL)
        self.assertFalse(BitrixLead.objects.get(lead_id=1).is_deleted)
        self.assertEqual(BitrixSyncRun.objects.get(entity="leads").status, BitrixSyncRun.Status.FAILED)

    def test_empty_initial_full_load_is_valid(self):
        run = load_leads(Mock(iter_pages=Mock(return_value=iter([[]]))), mode=BitrixSyncRun.Mode.FULL)
        self.assertEqual(run.status, BitrixSyncRun.Status.SUCCESS)

    def test_nonempty_full_leads_still_deactivate_missing_records(self):
        BitrixLead.objects.create(lead_id=1)
        load_leads(Mock(iter_pages=Mock(return_value=iter([[{"ID": "2", "DATE_MODIFY": "2026-09-13T00:00:00+03:00"}]]))), mode=BitrixSyncRun.Mode.FULL)
        self.assertTrue(BitrixLead.objects.get(lead_id=1).is_deleted)
        self.assertFalse(BitrixLead.objects.get(lead_id=2).is_deleted)

    def test_empty_reference_responses_preserve_existing_records(self):
        fixtures = [
            (load_departments, BitrixDepartment.objects.create(department_id=1), Mock(iter_pages=Mock(return_value=iter([[]]))), {}),
            (load_users, BitrixUser.objects.create(user_id=1), Mock(iter_pages=Mock(return_value=iter([[]]))), {}),
            (load_crm_dictionaries, BitrixCrmDictionary.objects.create(entity_id="STATUS", status_id="NEW"), Mock(iter_items=Mock(return_value=iter([]))), {"entity_ids": ("STATUS",)}),
            (load_crm_fields, BitrixCrmField.objects.create(entity_type_id=1, field_code="TITLE"), Mock(call=Mock(return_value={"result": {}})), {}),
        ]
        for loader, item, client, kwargs in fixtures:
            with self.subTest(loader=loader.__name__), self.assertRaises(Bitrix24ResponseError):
                loader(client, mode=BitrixSyncRun.Mode.FULL, **kwargs)
            item.refresh_from_db()
            self.assertFalse(item.is_deleted)

    def test_deal_select_keeps_analytics_fields_and_preserves_unrequested_columns(self):
        created = datetime(2026, 1, 1, tzinfo=ZoneInfo("Europe/Moscow"))
        BitrixDeal.objects.create(deal_id=1, contact_id=7, contact_ids=[7, 8], begin_date=created, close_date=created)
        values = dict(id=1, title="Deal", categoryId=2, stageId="C2:WON", stageSemanticId="S", assignedById=10,
            leadId=22, companyId=33, opportunity=125.5, currencyId="RUB", sourceId="web",
            createdTime=created.isoformat(), updatedTime="2026-09-13T00:00:00+03:00", isReturnCustomer=True,
            UF_CRM_69B904B3E0AD1="type", UF_CRM_64254B7D4853D="activity")
        def pages(method, params):
            self.assertEqual(set(params["select"]), set(values))
            self.assertNotIn("*", params["select"])
            self.assertEqual(params["useOriginalUfNames"], "Y")
            yield [values]
        load_deals(Mock(iter_pages=pages))
        deal = BitrixDeal.objects.get(deal_id=1)
        self.assertEqual((deal.contact_id, deal.contact_ids, deal.begin_date, deal.close_date), (7, [7, 8], created, created))
        self.assertEqual(deal.currency_id, "RUB")
        self.assertEqual(deal.lead_id, 22)
        self.assertTrue(deal.closed)
        self.assertEqual(deal.raw_payload["UF_CRM_64254B7D4853D"], "activity")
