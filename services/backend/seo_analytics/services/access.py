from dashboards.models import Dashboard, DashboardAccess
from dashboards.services.access import user_can_view_dashboard


SEO_DASHBOARD_NAME = "SEO-аналитика"


def get_seo_dashboard():
    return Dashboard.objects.get(organization__code="iplast", name=SEO_DASHBOARD_NAME)


def can_view(user):
    return user_can_view_dashboard(user, get_seo_dashboard())


def can_edit(user):
    dashboard = get_seo_dashboard()
    if user.is_superuser or dashboard.owner_id == user.id:
        return True
    return DashboardAccess.objects.filter(user=user, dashboard=dashboard, can_edit=True).exists()

