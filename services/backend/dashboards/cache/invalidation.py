from dashboards.models import DashboardWidget, Dashboard
from dashboards.cache.dashboard_cache import (
    delete_dashboard_cache,
    delete_dashboard_cache_for_user,
)


def invalidate_dashboards_for_dataset(dataset_id: int):
    widgets = DashboardWidget.objects.select_related(
        "dashboard",
        "dashboard__owner",
    ).filter(
        config__dataset_id=dataset_id,
    )

    dashboard_ids = set()

    for widget in widgets:
        dashboard = widget.dashboard
        dashboard_ids.add(dashboard.id)

        if dashboard.owner_id:
            delete_dashboard_cache_for_user(
                user_id=dashboard.owner_id,
                dashboard_id=dashboard.id,
            )

    for dashboard_id in dashboard_ids:
        delete_dashboard_cache(dashboard_id)



def invalidate_dashboard_by_name(name: str):
    dashboards = Dashboard.objects.filter(name=name)

    for dashboard in dashboards:
        delete_dashboard_cache(dashboard.id)

        if dashboard.owner_id:
            delete_dashboard_cache_for_user(
                user_id=dashboard.owner_id,
                dashboard_id=dashboard.id,
            )