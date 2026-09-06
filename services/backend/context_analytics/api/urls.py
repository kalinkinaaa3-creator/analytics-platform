from django.urls import path

from context_analytics.api.views import (
    ConfigurationTemplateView, ConfigurationUploadView, FilterOptionsView,
    ExportDownloadView, ExportStateView, InternalRefreshView, RefreshStateView,
    RefreshView, ReportExportView, ReportView,
)

urlpatterns = [
    path("filters/", FilterOptionsView.as_view()),
    path("reports/<slug:page>/", ReportView.as_view()),
    path("reports/<slug:page>/export/", ReportExportView.as_view()),
    path("exports/<uuid:run_id>/", ExportStateView.as_view()),
    path("exports/<uuid:run_id>/download/", ExportDownloadView.as_view()),
    path("configuration/goals/template/", ConfigurationTemplateView.as_view()),
    path("configuration/goals/upload/", ConfigurationUploadView.as_view()),
    path("refresh/", RefreshView.as_view()),
    path("refresh/state/", RefreshStateView.as_view()),
    path("refresh/internal/", InternalRefreshView.as_view()),
]
