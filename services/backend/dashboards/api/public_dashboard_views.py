from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.exceptions import NotFound, PermissionDenied

from dashboards.models import DashboardPublicAccess
from dashboards.services.dashboard_builder import build_dashboard
from dashboards.services.audit import log_dashboard_view


class PublicDashboardBuilderView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, token):
        public_access = (
            DashboardPublicAccess.objects
            .select_related("dashboard")
            .filter(token=token)
            .first()
        )

        if public_access is None:
            raise NotFound("Public dashboard link not found")

        if not public_access.is_valid():
            raise PermissionDenied("Public dashboard link is inactive or expired")

        filters = request.query_params.dict()

        result = build_dashboard(
            dashboard_id=public_access.dashboard_id,
            user=None,
            filters=filters,
        )

        log_dashboard_view(
            request=request,
            dashboard=public_access.dashboard,
            filters=filters,
            access_type="public",
            public_access=public_access,
        )

        return Response(result)