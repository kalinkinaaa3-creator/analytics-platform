from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from bitrix24.models import (
    BitrixCrmDictionary,
    BitrixCrmField,
    BitrixDepartment,
    BitrixLead,
    BitrixSyncRun,
    BitrixSyncState,
    BitrixUser,
    BitrixUserDepartment,
)
from bitrix24.services.loaders import (
    load_crm_dictionaries,
    load_crm_fields,
    load_departments,
    load_leads,
    load_users,
)


class FakeClient:
    def __init__(self, *, pages=None, items=None, payload=None):
        self.pages = pages or {}
        self.items = items or {}
        self.payload = payload
        self.calls = []

    def iter_pages(self, method, params=None):
        self.calls.append((method, params))
        yield from self.pages.get(method, [])

    def iter_items(self, method, params=None):
        self.calls.append((method, params))
        entity_id = (params or {}).get("filter", {}).get("ENTITY_ID")
        yield from self.items.get((method, entity_id), [])

    def call(self, method, params=None):
        self.calls.append((method, params))
        return self.payload


class ReferenceLoaderTests(TestCase):
    def test_full_department_load_upserts_and_deactivates_missing(self):
        BitrixDepartment.objects.create(department_id=99, name="Старое")
        client = FakeClient(
            pages={
                "department.get": [
                    [{"ID": "10", "NAME": "Продажи", "PARENT": "1", "SORT": "20"}]
                ]
            }
        )

        run = load_departments(client)

        self.assertEqual(run.status, BitrixSyncRun.Status.SUCCESS)
        self.assertEqual(run.rows_created, 1)
        self.assertEqual(run.rows_deactivated, 1)
        self.assertTrue(BitrixDepartment.objects.get(department_id=99).is_deleted)
        self.assertFalse(BitrixDepartment.objects.get(department_id=10).is_deleted)

    def test_user_uses_first_department_as_primary(self):
        first = BitrixDepartment.objects.create(department_id=10, name="Первое")
        BitrixDepartment.objects.create(department_id=20, name="Второе")
        client = FakeClient(
            pages={
                "user.get": [
                    [
                        {
                            "ID": "7",
                            "ACTIVE": "Y",
                            "NAME": "Иван",
                            "LAST_NAME": "Иванов",
                            "UF_DEPARTMENT": ["10", "20"],
                        }
                    ]
                ]
            }
        )

        load_users(client)

        user = BitrixUser.objects.get(user_id=7)
        self.assertEqual(user.primary_department_id, 10)
        self.assertEqual(user.department_ids, [10, 20])
        link = BitrixUserDepartment.objects.get(user=user, is_primary=True)
        self.assertEqual(link.department, first)

    def test_dictionary_and_field_loaders_preserve_external_codes(self):
        dictionary_client = FakeClient(
            items={
                ("crm.status.list", "STATUS"): [
                    {"STATUS_ID": "5", "NAME": "Передано в Айпласт Маркет"}
                ],
                ("crm.status.list", "SOURCE"): [],
            }
        )
        load_crm_dictionaries(dictionary_client)

        field_client = FakeClient(
            payload={
                "result": {
                    "UF_CRM_TEST": {
                        "type": "string",
                        "title": "Тестовое поле",
                        "isMultiple": False,
                        "isRequired": False,
                    }
                }
            }
        )
        load_crm_fields(field_client)

        self.assertEqual(
            BitrixCrmDictionary.objects.get(entity_id="STATUS").status_id,
            "5",
        )
        self.assertTrue(BitrixCrmField.objects.get(field_code="UF_CRM_TEST").is_custom)


class LeadLoaderTests(TestCase):
    def test_incremental_load_uses_overlap_and_updates_existing_row(self):
        watermark = timezone.now() - timedelta(hours=1)
        BitrixSyncState.objects.create(
            entity="leads",
            status=BitrixSyncState.Status.SUCCESS,
            last_source_updated_at=watermark,
        )
        BitrixLead.objects.create(lead_id=100, status_id="NEW", title="Лид")
        modified_at = timezone.now()
        client = FakeClient(
            pages={
                "crm.lead.list": [
                    [
                        {
                            "ID": "100",
                            "TITLE": "Лид обновлён",
                            "STATUS_ID": "IN_PROCESS",
                            "DATE_CREATE": (modified_at - timedelta(days=1)).isoformat(),
                            "DATE_MODIFY": modified_at.isoformat(),
                        }
                    ]
                ]
            }
        )

        run = load_leads(client)

        lead = BitrixLead.objects.get(lead_id=100)
        self.assertEqual(lead.status_id, "IN_PROCESS")
        self.assertEqual(run.rows_created, 0)
        self.assertEqual(run.rows_updated, 1)
        params = client.calls[0][1]
        self.assertEqual(
            params["filter"][">=DATE_MODIFY"],
            (watermark - timedelta(minutes=10)).isoformat(),
        )
        state = BitrixSyncState.objects.get(entity="leads")
        self.assertEqual(state.last_source_updated_at, modified_at)

    def test_empty_incremental_load_does_not_reset_watermark(self):
        watermark = timezone.now() - timedelta(hours=1)
        BitrixSyncState.objects.create(
            entity="leads",
            status=BitrixSyncState.Status.SUCCESS,
            last_source_updated_at=watermark,
        )
        client = FakeClient(pages={"crm.lead.list": [[]]})

        load_leads(client)

        self.assertEqual(
            BitrixSyncState.objects.get(entity="leads").last_source_updated_at,
            watermark,
        )
