from dashboards.models import DashboardAccess


def user_can_view_dashboard(user, dashboard) -> bool:
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    if dashboard.owner_id == user.id:
        return True

    return DashboardAccess.objects.filter(
        user=user,
        dashboard=dashboard,
        can_view=True,
    ).exists()


def user_can_edit_dashboard(user, dashboard) -> bool:
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    if dashboard.owner_id == user.id:
        return True

    return DashboardAccess.objects.filter(
        user=user,
        dashboard=dashboard,
        can_edit=True,
    ).exists()