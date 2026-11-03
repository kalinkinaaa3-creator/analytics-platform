from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from organizations.models import Organization, OrganizationMembership, UserProfile
from .department_admin import DepartmentGroupForm
from .models import Dashboard, DashboardAccess, DashboardDepartmentGroup, DashboardDepartmentExclusion


class DepartmentAccessTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Main", code="iplast", postgres_schema="public")
        self.user = get_user_model().objects.create_user(username="employee")
        UserProfile.objects.create(user=self.user, full_name="Employee Full Name")
        self.membership = OrganizationMembership.objects.create(user=self.user, organization=self.org, department="Sales")
        self.dashboard = Dashboard.objects.create(name="Sales dashboard", organization=self.org)
        self.group = DashboardDepartmentGroup.objects.create(name="Sales", dashboard=self.dashboard, departments=["Sales"])

    def access(self):
        return DashboardAccess.objects.get(user=self.user, dashboard=self.dashboard)

    def test_group_membership_changes_and_reassignment(self):
        self.assertTrue(self.access().can_view)
        self.assertIsNone(self.access().manual_can_view)
        self.membership.department = "Other"
        self.membership.save()
        self.assertFalse(DashboardAccess.objects.filter(user=self.user).exists())
        self.membership.department = "Sales"
        self.membership.save()
        other = get_user_model().objects.create_user(username="new")
        self.membership.user = other
        self.membership.save()
        self.assertFalse(DashboardAccess.objects.filter(user=self.user).exists())
        self.assertTrue(DashboardAccess.objects.filter(user=other, can_view=True).exists())

    def test_deletion_is_permanent_until_manual_restore(self):
        self.access().delete()
        self.assertTrue(DashboardDepartmentExclusion.objects.filter(user=self.user).exists())
        self.group.can_edit = True
        self.group.save()
        self.membership.department = "Other"
        self.membership.save()
        self.membership.department = "Sales"
        self.membership.save()
        self.assertFalse(DashboardAccess.objects.filter(user=self.user).exists())
        DashboardAccess.objects.create(user=self.user, dashboard=self.dashboard, can_view=True)
        self.assertFalse(DashboardDepartmentExclusion.objects.filter(user=self.user).exists())
        self.assertTrue(self.access().can_edit)

    def test_overlapping_groups_and_manual_rights(self):
        second = DashboardDepartmentGroup.objects.create(name="Editors", dashboard=self.dashboard, departments=["Sales"], can_edit=True)
        self.assertTrue(self.access().can_edit)
        second.delete()
        self.assertFalse(self.access().can_edit)
        access = self.access()
        access.can_edit = True
        access.save()
        self.group.delete()
        self.assertTrue(self.access().can_edit)
        self.assertFalse(self.access().from_department_group)
        self.membership.delete()
        self.assertTrue(self.access().manual_can_edit)

    def test_inactive_membership_user_and_organization(self):
        for obj in (self.membership, self.user, self.org, self.group):
            obj.is_active = False
            obj.save()
            self.assertFalse(DashboardAccess.objects.filter(user=self.user).exists())
            obj.is_active = True
            obj.save()
            self.assertTrue(self.access().can_view)

    def test_departments_are_scoped_to_organization(self):
        other = Organization.objects.create(name="Other", code="other", postgres_schema="other")
        user = get_user_model().objects.create_user(username="other")
        OrganizationMembership.objects.create(user=user, organization=other, department="Sales")
        self.assertFalse(DashboardAccess.objects.filter(user=user).exists())

    def test_new_member_receives_access_and_group_dashboard_change_revokes_old(self):
        user = get_user_model().objects.create_user(username="new-member")
        OrganizationMembership.objects.create(user=user, organization=self.org, department="Sales")
        self.assertTrue(DashboardAccess.objects.filter(user=user, dashboard=self.dashboard).exists())
        other = Dashboard.objects.create(name="Other dashboard", organization=self.org)
        self.group.dashboard = other
        self.group.save()
        self.assertFalse(DashboardAccess.objects.filter(dashboard=self.dashboard).exists())
        self.assertEqual(DashboardAccess.objects.filter(dashboard=other).count(), 2)

    def test_user_cascade_does_not_create_exclusion(self):
        self.user.delete()
        self.assertFalse(DashboardDepartmentExclusion.objects.exists())

    def login_admin(self):
        user = get_user_model().objects.create_superuser(username="admin", password="test")
        self.client.force_login(user)

    def test_admin_pages_preview_and_form(self):
        self.login_admin()
        for model in ("dashboarddepartmentgroup", "dashboardaccess"):
            self.assertEqual(self.client.get(reverse(f"admin:dashboards_{model}_changelist")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:dashboards_dashboarddepartmentgroup_change", args=[self.group.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:auth_user_changelist")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:organizations_organizationmembership_changelist")).status_code, 200)
        self.assertIn(Group, admin.site._registry)
        self.access().delete()
        response = self.client.get(reverse("admin:dashboards_department_group_preview"), {"dashboard": self.dashboard.pk, "departments": ["Sales"]})
        self.assertEqual(response.json()["users"], [{"username": "employee", "full_name": "Employee Full Name", "department": "Sales", "excluded": True}])
        form = DepartmentGroupForm(data={"name": "Another", "dashboard": self.dashboard.pk, "departments": ["Sales"], "can_view": True, "is_active": True})
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.assertEqual(form.instance.name, "Sales")
        self.assertFalse(DashboardAccess.objects.filter(user=self.user).exists())

    def test_group_names_follow_departments_without_manual_input(self):
        OrganizationMembership.objects.create(user=get_user_model().objects.create_user(username="finance"), organization=self.org, department="Finance")
        form = DepartmentGroupForm(data={"dashboard": self.dashboard.pk, "departments": ["Sales", "Finance"], "can_view": True, "is_active": True})
        self.assertTrue(form.is_valid(), form.errors)
        group = form.save()
        self.assertEqual(group.name, "Sales; Finance")
        group.departments = ["Finance"]
        group.save(update_fields=["departments"])
        group.refresh_from_db()
        self.assertEqual(group.name, "Finance")
        self.login_admin()
        response = self.client.get(reverse("admin:dashboards_dashboarddepartmentgroup_change", args=[group.pk]))
        for label in ("Can view", "Can edit", "Active", "Groups accesses"):
            self.assertContains(response, label)

    def test_auth_groups_show_live_department_members_and_search(self):
        self.login_admin()
        url = reverse("admin:auth_group_changelist")
        response = self.client.get(url)
        self.assertContains(response, "Sales")
        self.assertContains(response, "Employee Full Name")
        self.assertContains(response, reverse("admin:auth_user_change", args=[self.user.pk]))
        self.assertContains(self.client.get(url, {"q": "Employee Full"}), "Sales")
        self.assertNotContains(self.client.get(url, {"q": "No match"}), "Employee Full Name")
        self.membership.department = "Finance"
        self.membership.save()
        response = self.client.get(url)
        self.assertEqual([group["name"] for group in response.context["page"]], ["Finance"])
        self.assertFalse(Group.objects.exists())

    def test_auth_groups_require_view_permission(self):
        from django.contrib.auth.models import Permission
        self.user.is_staff = True
        self.user.save()
        self.client.force_login(self.user)
        url = reverse("admin:auth_group_changelist")
        self.assertEqual(self.client.get(url).status_code, 403)
        self.user.user_permissions.add(Permission.objects.get(content_type__app_label="auth", codename="view_group"))
        response = self.client.get(url)
        self.assertContains(response, "Employee Full Name")
        self.assertNotContains(response, reverse("admin:auth_user_change", args=[self.user.pk]))

    def test_admin_bulk_delete_preserves_exclusion(self):
        self.login_admin()
        response = self.client.post(reverse("admin:dashboards_dashboardaccess_changelist"), {
            "action": "delete_selected", "_selected_action": [self.access().pk], "post": "yes",
        })
        self.assertEqual(response.status_code, 302)
        self.group.save()
        self.assertFalse(DashboardAccess.objects.filter(user=self.user).exists())

    def test_admin_save_generated_access_does_not_make_it_manual(self):
        self.login_admin()
        response = self.client.post(reverse("admin:dashboards_dashboardaccess_change", args=[self.access().pk]), {"_save": "Save"})
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(self.access().manual_can_view)
        self.group.delete()
        self.assertFalse(DashboardAccess.objects.filter(user=self.user).exists())

    def test_admin_individual_delete_and_column_order(self):
        self.login_admin()
        columns = admin.site._registry[DashboardAccess].list_display
        self.assertEqual(columns[:5], ("organization", "dashboard", "user", "display_full_name", "display_department"))
        response = self.client.post(reverse("admin:dashboards_dashboardaccess_delete", args=[self.access().pk]), {"post": "yes"})
        self.assertEqual(response.status_code, 302)
        self.group.save()
        self.assertFalse(DashboardAccess.objects.filter(user=self.user).exists())

    def test_preview_requires_permission(self):
        self.user.is_staff = True
        self.user.save()
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("admin:dashboards_department_group_preview"), {"dashboard": self.dashboard.pk}).status_code, 403)
