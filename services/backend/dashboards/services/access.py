from dashboards.models import DashboardAccess
from organizations.models import OrganizationMembership


def user_in_dashboard_organization(user, dashboard):
    if not user or not user.is_authenticated or not user.is_active:
        return False
    selected = getattr(user, "_request_organization_id", dashboard.organization_id)
    return selected == dashboard.organization_id and OrganizationMembership.objects.filter(
        user=user, organization_id=dashboard.organization_id,
        is_active=True, organization__is_active=True,
    ).exists()


def user_can_view_dashboard(user, dashboard) -> bool:
    if not user_in_dashboard_organization(user, dashboard):
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
    if not user_in_dashboard_organization(user, dashboard):
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
