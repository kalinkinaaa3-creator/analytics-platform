from django import forms
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
from django.utils.html import format_html

from organizations.admin_helpers import full_name
from organizations.models import OrganizationMembership
from .models import Dashboard, DashboardDepartmentGroup, DashboardDepartmentExclusion


class DepartmentGroupForm(forms.ModelForm):
    name = forms.CharField(label="Name", required=False, disabled=True,
                          widget=forms.TextInput(attrs={"style": "width: min(600px, 100%)"}))
    departments = forms.MultipleChoiceField(
        label="Department name", widget=forms.SelectMultiple(attrs={"size": 8}),
        help_text="Выберите подразделения. Ctrl / Cmd — выбор нескольких. Доступ обновляется автоматически при смене подразделения пользователя.",
    )

    class Meta:
        model = DashboardDepartmentGroup
        fields = ("name", "dashboard", "departments", "can_view", "can_edit", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        dashboard_id = self.data.get("dashboard") if self.is_bound else self.initial.get("dashboard")
        dashboard = Dashboard.objects.filter(pk=dashboard_id).first() if str(dashboard_id or "").isdecimal() else None
        departments = set(self.instance.departments or [])
        if dashboard:
            departments.update(OrganizationMembership.objects.filter(organization_id=dashboard.organization_id).exclude(department="").values_list("department", flat=True))
        self.fields["departments"].choices = [(value, value) for value in sorted(departments)]

    def clean(self):
        cleaned = super().clean()
        cleaned["name"] = "; ".join(cleaned.get("departments", []))
        return cleaned


@admin.register(DashboardDepartmentGroup)
class DashboardDepartmentGroupAdmin(admin.ModelAdmin):
    form = DepartmentGroupForm
    list_display = ("name", "organization", "dashboard", "department_names", "can_view", "can_edit", "is_active")
    list_select_related = ("dashboard__organization",)
    list_filter = ("dashboard__organization", "dashboard", "is_active", "can_view", "can_edit")
    search_fields = ("name", "dashboard__name")
    readonly_fields = ("recipients",)
    fields = ("name", "dashboard", "departments", "can_view", "can_edit", "is_active", "recipients")

    class Media:
        js = ("dashboards/department_groups.js",)
        css = {"all": ("dashboards/department_groups.css",)}

    @admin.display(description="Организация")
    def organization(self, obj):
        return obj.dashboard.organization

    @admin.display(description="Department name")
    def department_names(self, obj):
        return "; ".join(obj.departments)

    @admin.display(description="Пользователи подразделений")
    def recipients(self, obj):
        return format_html(
            '<div id="department-recipients" data-preview-url="{}" aria-live="polite">Выберите дашборд и подразделения.</div>'
            '<p class="help">Удаление строки в Dashboard accesses исключает пользователя из группового доступа к этому дашборду. '
            'Исключение сохраняется при обновлении группы. Для восстановления добавьте персональный доступ вручную.</p>',
            reverse("admin:dashboards_department_group_preview"),
        )

    def get_urls(self):
        return [path("preview/", self.admin_site.admin_view(self.preview), name="dashboards_department_group_preview"), *super().get_urls()]

    def preview(self, request):
        if not (self.has_view_permission(request) or self.has_add_permission(request) or self.has_change_permission(request)):
            raise PermissionDenied
        dashboard_id = request.GET.get("dashboard", "")
        if not dashboard_id.isdecimal():
            return JsonResponse({"organization": "", "departments": [], "users": []})
        dashboard = get_object_or_404(Dashboard.objects.select_related("organization"), pk=dashboard_id)
        memberships = OrganizationMembership.objects.filter(organization_id=dashboard.organization_id)
        departments = sorted(set(memberships.exclude(department="").values_list("department", flat=True)))
        excluded = set(DashboardDepartmentExclusion.objects.filter(dashboard=dashboard).values_list("user_id", flat=True))
        users = memberships.filter(department__in=request.GET.getlist("departments"), is_active=True,
                                   user__is_active=True, organization__is_active=True).select_related("user__organization_profile").order_by("department", "user__username")
        return JsonResponse({"organization": dashboard.organization.name, "departments": departments, "users": [
            {"username": membership.user.username, "full_name": full_name(membership.user),
             "department": membership.department, "excluded": membership.user_id in excluded}
            for membership in users
        ]})
