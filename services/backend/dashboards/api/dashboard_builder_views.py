from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from dashboards.services.dashboard_builder import build_dashboard


class DashboardBuilderView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, dashboard_id):
        result = build_dashboard(
            dashboard_id=dashboard_id,
            user=request.user,
            filters=request.query_params.dict(),
        )

        return Response(result)