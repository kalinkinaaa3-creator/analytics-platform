from django.contrib import admin

from dashboards.models import (
    Dashboard,
    DashboardWidget,
    DashboardAccess,
    DashboardPublicAccess,
    UserLoginLog,
    DashboardViewLog,
    DashboardPublicGroup,
    DashboardPublicGroupItem,
    IPriceParameterChangeLog,
)


@admin.register(Dashboard)
class DashboardAdmin(admin.ModelAdmin):
    list_display = ("id", "slug", "name", "owner", "created_at")


@admin.register(DashboardWidget)
class DashboardWidgetAdmin(admin.ModelAdmin):
    list_display = ("id", "dashboard", "type", "position")

    list_filter = ("type", "dashboard")




@admin.register(DashboardAccess)
class DashboardAccessAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "dashboard",
        "can_view",
        "can_edit",
        "created_at",
    )

    list_filter = (
        "can_view",
        "can_edit",
        "dashboard",
    )

    search_fields = (
        "user__email",
        "user__username",
        "dashboard__name",
    )

    readonly_fields = (
        "created_at",
    )

    ordering = ("dashboard", "user")


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


@admin.register(IPriceParameterChangeLog)
class IPriceParameterChangeLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "snapshot_id",
        "mode",
        "user",
        "status",
    )
    list_filter = ("status", "mode", "created_at")
    search_fields = ("snapshot_id", "user__username", "user__email")
    readonly_fields = (
        "user",
        "snapshot_id",
        "mode",
        "filters",
        "search",
        "changes",
        "affected",
        "status",
        "error",
        "created_at",
        "finished_at",
    )
