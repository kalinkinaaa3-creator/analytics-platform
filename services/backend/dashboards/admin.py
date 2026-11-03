from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db import router, transaction
from organizations.admin_helpers import full_name, department_name

from dashboards.models import (
    Dashboard,
    DashboardWidget,
    DashboardAccess,
    DashboardPublicAccess,
    UserLoginLog,
    DashboardViewLog,
    DashboardPublicGroup,
    DashboardPublicGroupItem,
)


@admin.register(Dashboard)
class DashboardAdmin(admin.ModelAdmin):
    list_display = ("id", "organization", "slug", "name", "owner", "created_at")
    list_filter = ("organization", "component", "show_in_menu")

    def get_readonly_fields(self, request, obj=None):
        return ("organization",) if obj else ()


@admin.register(DashboardWidget)
class DashboardWidgetAdmin(admin.ModelAdmin):
    list_display = ("id", "dashboard", "type", "position")

    list_filter = ("type", "dashboard")




@admin.register(DashboardAccess)
class DashboardAccessAdmin(admin.ModelAdmin):
    list_display = (
        "organization",
        "dashboard",
        "user",
        "display_full_name",
        "display_department",
        "can_view",
        "can_edit",
        "access_source",
        "created_at",
    )

    list_filter = (
        "dashboard__organization",
        "can_view",
        "can_edit",
        "dashboard",
    )

    search_fields = (
        "user__email",
        "user__username",
        "user__organization_profile__full_name",
        "user__organization_memberships__department",
        "dashboard__name",
    )

    readonly_fields = (
        "created_at",
        "access_source",
    )

    ordering = ("dashboard", "user")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("dashboard__organization", "user__organization_profile").prefetch_related("user__organization_memberships__organization")

    @admin.display(description="ФИО")
    def display_full_name(self, obj):
        return full_name(obj.user)

    @admin.display(description="Department name")
    def display_department(self, obj):
        return department_name(obj.user, obj.dashboard.organization_id)

    @admin.display(description="Источник доступа")
    def access_source(self, obj):
        if obj.from_department_group:
            return "Подразделение + вручную" if obj.manual_can_view is not None else "Подразделение"
        return "Вручную"

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.from_department_group and obj.manual_can_view is None:
            return (*self.readonly_fields, "user", "dashboard", "can_view", "can_edit")
        return (*self.readonly_fields, "user", "dashboard") if obj else self.readonly_fields

    def save_model(self, request, obj, form, change):
        # Opening/saving a generated grant must not convert it into a manual one.
        if change and obj.from_department_group and obj.manual_can_view is None:
            return
        super().save_model(request, obj, form, change)

    def delete_queryset(self, request, queryset):
        using = queryset.db
        with transaction.atomic(using=using):
            user_ids = queryset.values_list("user_id", flat=True)
            list(get_user_model().objects.using(using).select_for_update().filter(pk__in=user_ids).order_by("pk"))
            super().delete_queryset(request, queryset)

    def delete_model(self, request, obj):
        using = router.db_for_write(DashboardAccess, instance=obj)
        with transaction.atomic(using=using):
            get_user_model().objects.using(using).select_for_update().get(pk=obj.user_id)
            super().delete_model(request, obj)

    @admin.display(description="Организация", ordering="dashboard__organization")
    def organization(self, obj):
        return obj.dashboard.organization


@admin.register(DashboardPublicAccess)
class DashboardPublicAccessAdmin(admin.ModelAdmin):
    list_display = (
        "dashboard",
        "token",
        "is_active",
        "expires_at",
        "created_at",
    )

    list_filter = (
        "is_active",
        "dashboard",
    )

    search_fields = (
        "dashboard__name",
    )

    readonly_fields = (
        "token",
        "created_at",
    )

    ordering = ("-created_at",)


@admin.register(UserLoginLog)
class UserLoginLogAdmin(admin.ModelAdmin):
    list_display = (
        "organization_name", "full_name", "department_name",
        "created_at",
        "username",
        "success",
        "ip_address",
    )

    list_filter = (
        "success",
        "created_at",
    )

    search_fields = (
        "username",
        "ip_address",
    )

    readonly_fields = (
        "organization", "organization_name", "full_name", "department_name",
        "created_at",
        "user",
        "username",
        "success",
        "ip_address",
        "user_agent",
    )

    ordering = ("-created_at",)
    

@admin.register(DashboardViewLog)
class DashboardViewLogAdmin(admin.ModelAdmin):
    list_display = (
        "organization_name", "full_name", "department_name",
        "created_at",
        "user",
        "dashboard",
        "access_type",
        "ip_address",
    )
    list_filter = (
        "access_type",
        "dashboard",
        "created_at",
    )
    search_fields = (
        "user__email",
        "user__username",
        "dashboard__name",
        "ip_address",
    )
    readonly_fields = (
        "organization", "organization_name", "full_name", "department_name",
        "created_at",
        "user",
        "dashboard",
        "public_access",
        "access_type",
        "filters",
        "ip_address",
        "user_agent",
    )
    ordering = ("-created_at",)





class DashboardPublicGroupItemInline(admin.TabularInline):
    model = DashboardPublicGroupItem
    extra = 1


@admin.register(DashboardPublicGroup)
class DashboardPublicGroupAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "token",
        "is_active",
        "expires_at",
        "created_at",
    )

    list_filter = (
        "is_active",
        "created_at",
    )

    search_fields = (
        "name",
    )

    readonly_fields = (
        "token",
        "created_at",
    )

    ordering = ("-created_at",)

    inlines = [
        DashboardPublicGroupItemInline,
    ]


@admin.register(DashboardPublicGroupItem)
class DashboardPublicGroupItemAdmin(admin.ModelAdmin):
    list_display = (
        "group",
        "section",
        "display_name",
        "dashboard",
        "position",
    )

    list_filter = (
        "group",
        "section",
    )

    search_fields = (
        "group__name",
        "display_name",
        "dashboard__name",
    )

    ordering = (
        "group",
        "section",
        "position",
    )


from .department_admin import DashboardDepartmentGroupAdmin  # noqa: E402,F401
