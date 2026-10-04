from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import NotFound

from dashboards.models import Dashboard
from dashboards.services.audit import log_dashboard_view
from dashboards.services.dashboard_builder import build_dashboard


class DashboardBuilderView(APIView):
    organization_aware = True
    permission_classes = [IsAuthenticated]

    def _get_dashboard(self, dashboard_slug):
        dashboard = Dashboard.objects.filter(slug=dashboard_slug, organization=self.request.organization).first()

        if dashboard is None:
            raise NotFound("Dashboard not found")

        return dashboard

    def _normalize_filters(self, filters):
        filters = filters or {}
        normalized = {}

        for key, value in filters.items():
            if value in ("", None, [], ()):
                continue

            if isinstance(value, tuple):
                value = list(value)

            if isinstance(value, list):
                clean_values = [
                    item
                    for item in value
                    if item not in ("", None)
                ]

                if clean_values:
                    normalized[key] = clean_values

                continue

            normalized[key] = value

        return normalized

    def _get_filters_from_query_params(self, request):
        filters = {}

        for key in request.query_params.keys():
            values = request.query_params.getlist(key)

            if len(values) > 1:
                filters[key] = values
            elif values:
                filters[key] = values[0]

        return self._normalize_filters(filters)

    def _get_filters_from_body(self, request):
        filters = request.data or {}

        return self._normalize_filters(filters)

    def _build_response(self, request, dashboard_slug, filters):
        dashboard = self._get_dashboard(dashboard_slug)

        result = build_dashboard(
            dashboard_id=dashboard.id,
            user=request.user,
            filters=filters,
        )

        log_dashboard_view(
            request=request,
            dashboard=dashboard,
            filters=filters,
            access_type="auth",
        )

        return Response(result)

    def get(self, request, dashboard_slug):
        filters = self._get_filters_from_query_params(request)

        return self._build_response(
            request=request,
            dashboard_slug=dashboard_slug,
            filters=filters,
        )

    def post(self, request, dashboard_slug):
        filters = self._get_filters_from_body(request)

        return self._build_response(
            request=request,
            dashboard_slug=dashboard_slug,
            filters=filters,
        )
