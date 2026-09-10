from django.urls import path, re_path
from .deal_views import DealReportView

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
    re_path(r"^dashboard/(?P<section>deals|full-cycle)/(?P<part>filters|summary|results|sources|managers|loss-reasons|funnel|rows|export)/$", DealReportView.as_view(), name="bitrix24-deal-report"),
    path("dashboard/", LeadDashboardView.as_view(), name="bitrix24-dashboard"),
    path("dashboard/filters/", LeadDashboardFiltersView.as_view(), name="bitrix24-filters"),
    path("dashboard/export/", LeadDashboardExportView.as_view(), name="bitrix24-export"),
    path("dashboard/rows/", LeadDashboardRowsView.as_view(), name="bitrix24-rows"),
    path("dashboard/refresh/", LeadDashboardRefreshView.as_view(), name="bitrix24-refresh"),
    path("dashboard/managers/template/", ManagerTrackingTemplateView.as_view(), name="bitrix24-manager-template"),
    path("dashboard/managers/upload/", ManagerTrackingUploadView.as_view(), name="bitrix24-manager-upload"),
]
