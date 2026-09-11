from datetime import datetime, timezone

from django.contrib.auth import get_user_model
from django.test import TestCase

from bitrix24.models import (
    BitrixDeal, BitrixDepartment, BitrixLead, BitrixUser,
    BitrixUserDepartmentPreference,
)
from bitrix24.services.department_preferences import manager_options, save_manager_options, selected_manager_ids


class DepartmentPreferenceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="crm-settings")
        for key, name in [(1, "Leads"), (2, "Deals"), (3, "Empty"), (4, "Deleted")]:
            BitrixDepartment.objects.create(department_id=key, name=name)
            BitrixUser.objects.create(user_id=key, full_name=name, primary_department_id=key)
        BitrixUser.objects.create(user_id=5, full_name="Colleague", primary_department_id=1)
        historical_date = datetime(2022, 1, 1, tzinfo=timezone.utc)
        BitrixLead.objects.create(lead_id=1, assigned_by_id=1, source_created_at=historical_date)
        # All deal categories count, not only the dashboard's default funnels.
        BitrixDeal.objects.create(deal_id=1, assigned_by_id=2, category_id=99, source_created_at=historical_date)
        BitrixLead.objects.create(lead_id=2, assigned_by_id=4, is_deleted=True)
        BitrixDeal.objects.create(deal_id=2, assigned_by_id=4, is_deleted=True)

    def visible_ids(self):
        return {row["manager_id"] for row in manager_options(self.user, with_data_only=True)}

    def test_form_uses_both_entities_and_all_history_at_department_level(self):
        self.assertEqual(self.visible_ids(), {1, 2, 5})

    def test_history_of_inactive_manager_keeps_department_available(self):
        BitrixUser.objects.filter(user_id=1).update(active=False)
        self.assertEqual(self.visible_ids(), {2, 5})

    def test_no_history_produces_empty_form(self):
        BitrixLead.objects.all().delete()
        BitrixDeal.objects.all().delete()
        self.assertEqual(self.visible_ids(), set())

    def test_display_alias_does_not_change_department_eligibility(self):
        BitrixUserDepartmentPreference.objects.create(user=self.user, manager_settings=[
            {"manager_id": 1, "selected": True, "display_name": "Alias"},
        ])
        self.assertEqual(self.visible_ids(), {1, 2, 5})

    def test_saving_visible_rows_preserves_hidden_preferences(self):
        BitrixUserDepartmentPreference.objects.create(user=self.user, manager_settings=[
            {"manager_id": 3, "selected": False, "display_name": "Custom empty"},
            {"manager_id": 4, "selected": True, "display_name": "Custom deleted"},
        ])
        rows = manager_options(self.user, with_data_only=True)
        result = save_manager_options(self.user, [{**row, "selected": False} for row in rows])
        self.assertEqual({row["manager_id"] for row in result}, {1, 2, 5})
        self.assertTrue(all(not row["selected"] for row in result))
        saved = {row["manager_id"]: row for row in manager_options(self.user)}
        self.assertFalse(saved[3]["selected"])
        self.assertEqual(saved[3]["display_name"], "Custom empty")
        self.assertTrue(saved[4]["selected"])
        self.assertEqual(saved[4]["display_name"], "Custom deleted")

    def test_form_filter_does_not_change_dashboard_manager_directory(self):
        self.assertEqual({row["manager_id"] for row in manager_options(self.user)}, {1, 2, 3, 4, 5})

    def test_select_all_keeps_lead_and_deal_managers_in_personal_scope(self):
        BitrixUserDepartmentPreference.objects.create(user=self.user, manager_settings=[
            {"manager_id": key, "selected": False, "display_name": ""} for key in range(1, 6)
        ])
        rows = manager_options(self.user, with_data_only=True)
        save_manager_options(self.user, [{**row, "selected": True} for row in rows])
        selected = selected_manager_ids(self.user)
        self.assertEqual(set(selected), {1, 2, 5})
        self.assertEqual(BitrixLead.objects.filter(is_deleted=False, assigned_by_id__in=selected).count(), 1)
        self.assertEqual(BitrixDeal.objects.filter(is_deleted=False, assigned_by_id__in=selected).count(), 1)
