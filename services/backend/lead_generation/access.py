from dashboards.models import Dashboard
from dashboards.services.access import user_can_edit_dashboard, user_can_view_dashboard


DASHBOARD_NAME = "Лидогенерация"


def get_dashboard():
    return Dashboard.objects.get(name=DASHBOARD_NAME)


def can_view(user):
    return user_can_view_dashboard(user, get_dashboard())


def can_edit(user):
    return user_can_edit_dashboard(user, get_dashboard())
