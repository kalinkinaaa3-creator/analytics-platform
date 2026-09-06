from datetime import date

from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from analytics.services.wordstat_demand import build_demand
from dashboards.models import Dashboard
from dashboards.services.access import user_can_view_dashboard


class DemandParams(serializers.Serializer):
    feature = serializers.CharField(required=False, allow_blank=True, max_length=255)
    category = serializers.CharField(required=False, allow_blank=True, max_length=255)
    phrase = serializers.CharField(required=False, allow_blank=True, max_length=255)
    level = serializers.ChoiceField(choices=["feature", "category", "phrase"], default="feature")
    period_months = serializers.ChoiceField(choices=[1, 3, 6, 12], default=12)
    end_month = serializers.RegexField(r"^\d{4}-\d{2}$", required=False)

    def validate_end_month(self, value):
        from django.utils import timezone
        try:
            month = date.fromisoformat(value + "-01")
        except ValueError:
            raise serializers.ValidationError("Некорректный месяц.")
        if month.year < 1901 or month >= timezone.localdate().replace(day=1):
            raise serializers.ValidationError("Выберите завершённый месяц.")
        return month


class WordstatDemandView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        dashboard = Dashboard.objects.filter(slug="wordstat").first()
        if not dashboard or not user_can_view_dashboard(request.user, dashboard):
            raise PermissionDenied("Нет доступа к дашборду Wordstat.")
        params = DemandParams(data=request.query_params)
        params.is_valid(raise_exception=True)
        return Response(build_demand(params.validated_data))


class PublicWordstatDemandView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request, token):
        from dashboards.api.public_group_views import get_public_group_or_404, get_public_group_dashboard_or_403
        group = get_public_group_or_404(token)
        get_public_group_dashboard_or_403(group, "wordstat")
        params = DemandParams(data=request.query_params)
        params.is_valid(raise_exception=True)
        return Response(build_demand(params.validated_data))
