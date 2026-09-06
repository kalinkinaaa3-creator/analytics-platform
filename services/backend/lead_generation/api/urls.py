from django.urls import path

from .views import PlanDownloadView, PlanUploadView, RefreshInfoView, ReportExportView, ReportView, SourcePreferenceView


urlpatterns = [
    path("reports/<slug:page>/", ReportView.as_view()),
    path("reports/<slug:page>/export/", ReportExportView.as_view()),
    path("plan/download/", PlanDownloadView.as_view()),
    path("plan/upload/", PlanUploadView.as_view()),
    path("sources/", SourcePreferenceView.as_view()),
    path("refresh/info/", RefreshInfoView.as_view()),
]
