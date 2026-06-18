from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import NotFound, PermissionDenied

from dashboards.models import DashboardPublicGroup

from dashboards.services.dashboard_builder import build_dashboard
from dashboards.services.audit import log_dashboard_view




class PublicDashboardGroupView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request, token):
        try:
            group = DashboardPublicGroup.objects.prefetch_related(
                "items__dashboard"
            ).get(token=token)

        except DashboardPublicGroup.DoesNotExist:
            raise NotFound("Public group not found")

        if not group.is_valid():
            raise PermissionDenied("Public group expired")

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

    def get(self, request, token, dashboard_slug):
        try:
            group = DashboardPublicGroup.objects.prefetch_related(
                "items__dashboard"
            ).get(token=token)
        except DashboardPublicGroup.DoesNotExist:
            raise NotFound("Public group not found")

        if not group.is_valid():
            raise PermissionDenied("Public group expired")

        group_item = (
            group.items
            .select_related("dashboard")
            .filter(dashboard__slug=dashboard_slug)
            .first()
        )

        if group_item is None:
            raise PermissionDenied("Dashboard is not available in this public group")

        filters = request.query_params.dict()

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