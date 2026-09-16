from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from bitrix24.services import department_preferences as service


class ManagerInheritanceTests(TestCase):
    def setUp(self):
        self.directory = {i: dict(user_id=i, manager_name=str(i), active=i != 3,
                                  department_id=10, department_name="Original") for i in range(1, 6)}
        self.saved = [{"manager_id": 1, "selected": False, "display_name": "Moscow"},
                      {"manager_id": 5, "selected": False, "display_name": "Keep hidden"}]
        for target, value in (("automatic_manager_directory", self.directory), ("managers_with_data", {1, 2, 3, 4})):
            patcher = patch.object(service, target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(service, "BitrixUserDepartmentPreference")
        self.model = patcher.start()
        self.addCleanup(patcher.stop)
        self.model.objects.filter.return_value.first.return_value = SimpleNamespace(manager_settings=self.saved)
        patcher = patch.object(service, "invalidate_bitrix24_cache")
        patcher.start()
        self.addCleanup(patcher.stop)

    def options(self):
        return {row["manager_id"]: row for row in service.manager_options("user", with_data_only=True)}

    def test_only_own_history_and_inherit_even_from_unchecked_manager(self):
        rows = self.options()
        self.assertEqual(set(rows), {1, 2, 3, 4})
        self.assertEqual(rows[2]["display_name"], "Moscow")
        self.assertTrue(rows[2]["selected"])
        self.assertFalse(rows[3]["selected"])
        self.assertFalse(rows[1]["selected"])

    def test_conflict_and_preserving_hidden_settings(self):
        self.saved.append({"manager_id": 3, "selected": True, "display_name": "Petersburg"})
        rows = self.options()
        self.assertTrue(rows[2]["needs_department_review"])
        self.assertEqual(rows[2]["display_name"], "Original")
        service.save_manager_options("user", list(rows.values()))
        saved = self.model.objects.update_or_create.call_args.kwargs["defaults"]["manager_settings"]
        self.assertIn(self.saved[1], saved)
        self.assertTrue(next(r for r in saved if r["manager_id"] == 2)["needs_department_review"])
        rows[2]["display_name"] = "Moscow"
        service.save_manager_options("user", list(rows.values()))
        saved = self.model.objects.update_or_create.call_args.kwargs["defaults"]["manager_settings"]
        self.assertFalse(next(r for r in saved if r["manager_id"] == 2)["needs_department_review"])

    def test_no_inheritance_between_different_or_missing_department_ids(self):
        self.directory[2]["department_id"] = 20
        self.directory[3]["department_id"] = None
        rows = self.options()
        self.assertEqual(rows[2]["display_name"], "Original")
        self.assertEqual(rows[3]["display_name"], "Original")

    def test_saved_name_is_not_replaced(self):
        self.saved.append({"manager_id": 2, "selected": False, "display_name": "Individual"})
        self.assertEqual(self.options()[2]["display_name"], "Individual")
