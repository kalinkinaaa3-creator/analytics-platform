from django.urls import path, include
from dashboards.api.views import DashboardView, DashboardViewSet
from .dashboard_builder_views import DashboardBuilderView
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register("dashboards", DashboardViewSet)

urlpatterns = [
    path("", include(router.urls)),

    path(
        "builder/<int:dashboard_id>/",
        DashboardBuilderView.as_view()
    ),

    path("<int:pk>/", DashboardView.as_view()),
]