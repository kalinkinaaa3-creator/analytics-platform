from django.urls import path, include
from rest_framework.routers import DefaultRouter

from dashboards.api.views import DashboardViewSet
from .dashboard_builder_views import DashboardBuilderView

from dashboards.api.realtime_test_views import DashboardRealtimeTestView




router = DefaultRouter()
router.register(r"", DashboardViewSet, basename="dashboards")


urlpatterns = [
    path(
        "builder/<int:dashboard_id>/",
        DashboardBuilderView.as_view()
    ),

    path("realtime-test/", DashboardRealtimeTestView.as_view()),

    path("", include(router.urls)),
]