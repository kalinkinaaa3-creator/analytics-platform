from django.urls import path

from .views import (
    LeadDashboardExportView,
    LeadDashboardFiltersView,
    LeadDashboardRowsView,
    LeadDashboardView,
    LeadDashboardRefreshView,
    ManagerTrackingTemplateView,
    ManagerTrackingUploadView,
)


urlpatterns = [
    path("dashboard/", LeadDashboardView.as_view(), name="bitrix24-dashboard"),
    path("dashboard/filters/", LeadDashboardFiltersView.as_view(), name="bitrix24-filters"),
    path("dashboard/export/", LeadDashboardExportView.as_view(), name="bitrix24-export"),
    path("dashboard/rows/", LeadDashboardRowsView.as_view(), name="bitrix24-rows"),
    path("dashboard/refresh/", LeadDashboardRefreshView.as_view(), name="bitrix24-refresh"),
    path("dashboard/managers/template/", ManagerTrackingTemplateView.as_view(), name="bitrix24-manager-template"),
    path("dashboard/managers/upload/", ManagerTrackingUploadView.as_view(), name="bitrix24-manager-upload"),
]
