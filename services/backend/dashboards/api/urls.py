from django.urls import path, include
from rest_framework.routers import DefaultRouter

from dashboards.api.views import DashboardViewSet
from .dashboard_builder_views import DashboardBuilderView
from .wordstat_demand_views import WordstatDemandView, PublicWordstatDemandView

from dashboards.api.realtime_test_views import DashboardRealtimeTestView
from dashboards.api.public_dashboard_views import PublicDashboardBuilderView

from dashboards.api.menu_views import DashboardMenuView
from .public_group_views import PublicDashboardGroupView, PublicGroupDashboardView




router = DefaultRouter()
router.register(r"", DashboardViewSet, basename="dashboards")


urlpatterns = [
    path("wordstat/demand-analysis/", WordstatDemandView.as_view()),
    path("public-group/<uuid:token>/wordstat/demand-analysis/", PublicWordstatDemandView.as_view()),
    
    path("menu/", DashboardMenuView.as_view()),

    path(
        "builder/<slug:dashboard_slug>/",
        DashboardBuilderView.as_view()
    ),

    path("realtime-test/", DashboardRealtimeTestView.as_view()),

    path(
        "public-group/<uuid:token>/",
        PublicDashboardGroupView.as_view(),
    ),

    path(
        "public-group/<uuid:token>/dashboard/<slug:dashboard_slug>/",
        PublicGroupDashboardView.as_view(),
    ),

    path("public/<uuid:token>/", PublicDashboardBuilderView.as_view()),


    path("", include(router.urls)),
]
