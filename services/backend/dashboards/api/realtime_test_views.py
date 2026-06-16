from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from dashboards.realtime import notify_dashboard_updated


class DashboardRealtimeTestView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        dashboard_name = request.data.get("dashboard") or "PlannedSales"

        notify_dashboard_updated(dashboard_name)

        return Response({
            "status": "ok",
            "event": "dashboard_updated",
            "dashboard": dashboard_name,
        })