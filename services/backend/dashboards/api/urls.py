from django.urls import path, include
from rest_framework.routers import DefaultRouter

from dashboards.api.views import DashboardViewSet
from .dashboard_builder_views import DashboardBuilderView


router = DefaultRouter()
router.register(r"", DashboardViewSet, basename="dashboards")


urlpatterns = [
    path("", include(router.urls)),

    path(
        "builder/<int:dashboard_id>/",
        DashboardBuilderView.as_view()
    ),
]