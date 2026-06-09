from django.contrib import admin
from dashboards.models import Dashboard, DashboardWidget


@admin.register(Dashboard)
class DashboardAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "owner", "created_at")


@admin.register(DashboardWidget)
class DashboardWidgetAdmin(admin.ModelAdmin):
    list_display = ("id", "dashboard", "type", "position")

    list_filter = ("type", "dashboard")