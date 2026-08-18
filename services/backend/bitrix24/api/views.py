from __future__ import annotations

import os

from django.http import FileResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView

from bitrix24.cache import get_dashboard_cache, set_dashboard_cache
from bitrix24.models import BitrixLeadAnalytics, BitrixSyncState
from bitrix24.services.dashboard_query import LeadDashboardFilters, LeadDashboardQuery
from bitrix24.services.export import (
    export_leads_xlsx,
    filtered_lead_analytics_queryset,
)
from bitrix24.services.manager_tracking import (
    ManagerTrackingValidationError,
    build_manager_tracking_template,
    load_manager_tracking,
)
from bitrix24.services.refresh import launch_refresh, refresh_state
from dashboards.models import Dashboard
from dashboards.services.access import user_can_edit_dashboard

from .serializers import (
    LeadDashboardRequestSerializer,
    LeadDashboardRowsRequestSerializer,
    ManagerTrackingUploadSerializer,
)


def _can_edit_crm(user) -> bool:
    dashboard = Dashboard.objects.filter(slug="crm-analytics").first()
    return bool(dashboard and user_can_edit_dashboard(user, dashboard))


def _filters(validated_data) -> LeadDashboardFilters:
    return LeadDashboardFilters(
        date_start=validated_data["date_start"],
        date_end=validated_data["date_end"],
        department_ids=tuple(validated_data["department_ids"]),
        manager_ids=tuple(validated_data["manager_ids"]),
        source_ids=tuple(validated_data["source_ids"]),
        status_ids=tuple(validated_data["status_ids"]),
        group_by=validated_data["group_by"],
    )


class LeadDashboardView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        serializer = LeadDashboardRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        cached = get_dashboard_cache(payload)
        if cached is not None:
            return Response(cached)

        result = LeadDashboardQuery().build(_filters(payload))
        set_dashboard_cache(payload, result)
        return Response(result)


class LeadDashboardFiltersView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        rows = BitrixLeadAnalytics.objects.all()
        sync_state = BitrixSyncState.objects.filter(entity="leads").first()
        current_refresh = refresh_state()
        return Response(
            {
                "departments": list(
                    rows.exclude(primary_department_id__isnull=True)
                    .values("primary_department_id", "department_name")
                    .distinct()
                    .order_by("department_name", "primary_department_id")
                ),
                "managers": list(
                    rows.exclude(manager_id__isnull=True)
                    .values("manager_id", "manager_name")
                    .distinct()
                    .order_by("manager_name", "manager_id")
                ),
                "sources": list(
                    rows.values("source_id", "source_name")
                    .distinct()
                    .order_by("source_name", "source_id")
                ),
                "statuses": list(
                    rows.values("status_id", "status_name", "dashboard_status", "is_apm")
                    .distinct()
                    .order_by("status_name", "status_id")
                ),
                "last_updated_at": (
                    current_refresh.get("finished_at")
                    if current_refresh.get("status") == "success"
                    else None
                ) or (sync_state.last_success_at if sync_state else None),
                "refresh": current_refresh,
            }
        )


class LeadDashboardExportView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        serializer = LeadDashboardRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        path, _ = export_leads_xlsx(_filters(serializer.validated_data))
        response = FileResponse(
            path.open("rb"),
            as_attachment=True,
            filename="bitrix24_lead_generation.xlsx",
            content_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )
        response._resource_closers.append(lambda: os.unlink(path) if path.exists() else None)
        return response


class LeadDashboardRowsView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        serializer = LeadDashboardRowsRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        page = payload["page"]
        page_size = payload["page_size"]
        queryset = filtered_lead_analytics_queryset(_filters(payload))
        total = queryset.count()
        offset = (page - 1) * page_size
        items = list(
            queryset.values(
                "lead_id",
                "title",
                "source_created_at",
                "source_updated_at",
                "opportunity",
                "source_id",
                "source_name",
                "status_id",
                "status_name",
                "dashboard_status",
                "manager_id",
                "manager_name",
                "primary_department_id",
                "department_name",
                "is_apm",
                "is_low_quality",
                "is_unmapped",
                "first_processing_at",
                "processing_duration_days",
                "processing_state",
            )[offset : offset + page_size]
        )
        return Response(
            {
                "items": items,
                "page": page,
                "page_size": page_size,
                "total": total,
                "pages": (total + page_size - 1) // page_size,
            }
        )


class LeadDashboardRefreshView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        return Response(refresh_state())

    def post(self, request):
        if not _can_edit_crm(request.user):
            return Response(
                {"detail": "Недостаточно прав для обновления Аналитики CRM."},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            pid = launch_refresh()
        except RuntimeError as exc:
            return Response(
                {"detail": str(exc), **refresh_state()},
                status=status.HTTP_409_CONFLICT,
            )
        return Response({"status": "running", "pid": pid}, status=status.HTTP_202_ACCEPTED)


class ManagerTrackingTemplateView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        if not _can_edit_crm(request.user):
            return Response(status=status.HTTP_403_FORBIDDEN)
        path = build_manager_tracking_template()
        response = FileResponse(
            path.open("rb"),
            as_attachment=True,
            filename="bitrix24_manager_tracking.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response._resource_closers.append(lambda: os.unlink(path) if path.exists() else None)
        return response


class ManagerTrackingUploadView(APIView):
    permission_classes = (IsAuthenticated,)
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request):
        if not _can_edit_crm(request.user):
            return Response(status=status.HTTP_403_FORBIDDEN)
        if refresh_state().get("running"):
            return Response(
                {"detail": "Сначала дождитесь завершения текущего обновления."},
                status=status.HTTP_409_CONFLICT,
            )
        serializer = ManagerTrackingUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = load_manager_tracking(serializer.validated_data["file"])
            pid = launch_refresh(skip_bitrix=True)
        except ManagerTrackingValidationError as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST
            )
        except RuntimeError as exc:
            return Response(
                {"detail": str(exc), **result}, status=status.HTTP_409_CONFLICT
            )
        return Response(
            {**result, "status": "running", "pid": pid},
            status=status.HTTP_202_ACCEPTED,
        )
