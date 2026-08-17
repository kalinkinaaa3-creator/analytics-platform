from rest_framework.permissions import BasePermission

from dashboards.models import Dashboard
from dashboards.services.access import (
    user_can_edit_dashboard,
    user_can_view_dashboard,
)


IPRICE_DASHBOARD_SLUG = "iprice"


def get_iprice_dashboard(request):
    if hasattr(request, "_iprice_dashboard"):
        return request._iprice_dashboard

    request._iprice_dashboard = (
        Dashboard.objects
        .filter(slug=IPRICE_DASHBOARD_SLUG)
        .first()
    )
    return request._iprice_dashboard


class CanViewIPriceDashboard(BasePermission):
    message = "Нет доступа к просмотру iPrice."

    def has_permission(self, request, view):
        dashboard = get_iprice_dashboard(request)
        return bool(
            dashboard
            and user_can_view_dashboard(
                request.user,
                dashboard,
            )
        )


class CanEditIPriceDashboard(BasePermission):
    message = "Нет доступа к редактированию iPrice."

    def has_permission(self, request, view):
        dashboard = get_iprice_dashboard(request)
        return bool(
            dashboard
            and user_can_edit_dashboard(
                request.user,
                dashboard,
            )
        )
