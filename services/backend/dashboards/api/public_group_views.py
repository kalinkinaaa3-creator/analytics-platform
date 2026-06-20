from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import NotFound, PermissionDenied

from dashboards.models import DashboardPublicGroup
from dashboards.services.dashboard_builder import build_dashboard
from dashboards.services.audit import log_dashboard_view


def get_public_group_or_404(token):
    try:
        group = DashboardPublicGroup.objects.prefetch_related(
            "items__dashboard"
        ).get(token=token)
    except DashboardPublicGroup.DoesNotExist:
        raise NotFound("Public group not found")

    if not group.is_valid():
        raise PermissionDenied("Public group expired")

    return group


def get_public_group_dashboard_or_403(group, dashboard_slug):
    group_item = (
        group.items
        .select_related("dashboard")
        .filter(dashboard__slug=dashboard_slug)
        .first()
    )

    if group_item is None:
        raise PermissionDenied("Dashboard is not available in this public group")

    return group_item


def get_filters_from_query_params(request):
    filters = {}

    for key in request.query_params.keys():
        values = request.query_params.getlist(key)

        if len(values) > 1:
            filters[key] = values
        elif values:
            filters[key] = values[0]

    return filters


def get_filters_from_body(request):
    return request.data or {}


class PublicDashboardGroupView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request, token):
        group = get_public_group_or_404(token)

        sections = {}

        for item in group.items.all().order_by(
            "section",
            "position",
        ):
            sections.setdefault(item.section, []).append({
                "dashboard_id": item.dashboard.id,
                "dashboard_slug": item.dashboard.slug,
                "name": item.display_name,
                "section": item.section,
            })

        return Response({
            "group_name": group.name,
            "token": str(group.token),
            "sections": sections,
        })


class PublicGroupDashboardView(APIView):
    authentication_classes = []
    permission_classes = []

    def _build_response(self, request, token, dashboard_slug, filters):
        group = get_public_group_or_404(token)

        group_item = get_public_group_dashboard_or_403(
            group=group,
            dashboard_slug=dashboard_slug,
        )

        result = build_dashboard(
            dashboard_id=group_item.dashboard_id,
            user=None,
            filters=filters,
        )

        log_dashboard_view(
            request=request,
            dashboard=group_item.dashboard,
            filters=filters,
            access_type="public",
        )

        return Response(result)

    def get(self, request, token, dashboard_slug):
        filters = get_filters_from_query_params(request)

        return self._build_response(
            request=request,
            token=token,
            dashboard_slug=dashboard_slug,
            filters=filters,
        )

    def post(self, request, token, dashboard_slug):
        filters = get_filters_from_body(request)

        return self._build_response(
            request=request,
            token=token,
            dashboard_slug=dashboard_slug,
            filters=filters,
        )