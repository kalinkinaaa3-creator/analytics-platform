from django.urls import path

from seo_analytics.api.views import (
    SeoConfigurationTemplateView,
    SeoConfigurationUploadView,
    SeoFilterOptionsView,
    SeoRefreshStateView,
    SeoRefreshView,
    SeoInternalRefreshView,
    SeoExportDownloadView,
    SeoExportStateView,
    SeoReportExportView,
    SeoReportView,
)


urlpatterns = [
    path("filters/", SeoFilterOptionsView.as_view()),
    path("reports/<slug:page>/", SeoReportView.as_view()),
    path("reports/<slug:page>/export/", SeoReportExportView.as_view()),
    path("exports/<uuid:run_id>/", SeoExportStateView.as_view()),
    path("exports/<uuid:run_id>/download/", SeoExportDownloadView.as_view()),
    path("configuration/<slug:kind>/template/", SeoConfigurationTemplateView.as_view()),
    path("configuration/<slug:kind>/upload/", SeoConfigurationUploadView.as_view()),
    path("refresh/", SeoRefreshView.as_view()),
    path("refresh/state/", SeoRefreshStateView.as_view()),
    path("refresh/internal/", SeoInternalRefreshView.as_view()),
]
