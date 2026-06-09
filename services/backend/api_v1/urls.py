from django.urls import path, include
from .views import health


'''
urlpatterns = [
    path("health/", include("api_v1.common.urls")),
    path("dashboards/", include("api_v1.dashboards.urls")),
    path("reports/", include("api_v1.reports.urls")),
    path("datasets/", include("api_v1.datasets.urls")),
]
'''
urlpatterns = [
    path("health/", health),
]