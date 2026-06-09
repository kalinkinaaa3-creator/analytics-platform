from django.shortcuts import get_object_or_404

from rest_framework.viewsets import ModelViewSet
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from dashboards.models import Dashboard
from .serializers import DashboardSerializer

from dashboards.engine.v3.dashboard_engine import DashboardEngineV3
from dashboards.cache.dashboard_cache import (
    get_dashboard_cache,
    set_dashboard_cache,
)


class DashboardViewSet(ModelViewSet):
    queryset = Dashboard.objects.all()
    serializer_class = DashboardSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Dashboard.objects.filter(owner=self.request.user)


class DashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):

        dashboard = get_object_or_404(
            Dashboard.objects.prefetch_related("widgets"),
            id=pk,
            owner=request.user,
        )

        cache_key = f"dashboard:v3:user:{request.user.id}:dashboard:{pk}"

        cached = get_dashboard_cache(cache_key)
        if cached:
            return Response(cached)

        engine = DashboardEngineV3()

        data = engine.build_dashboard({
            "id": dashboard.id,
            "dataset_id": 1,
            "widgets": list(
                dashboard.widgets.order_by("position").values("type", "config")
            )
        })

        set_dashboard_cache(cache_key, data)

        return Response(data)