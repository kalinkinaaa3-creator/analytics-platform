from __future__ import annotations
from bitrix24.services.personal_departments import department_mapping

import os
from dataclasses import replace

from django.http import FileResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, APIException
from rest_framework.views import APIView

from bitrix24.cache import get_dashboard_cache, set_dashboard_cache
from bitrix24.models import BitrixLeadAnalytics, BitrixSyncState
from bitrix24.services.department_preferences import display_names, manager_options, save_manager_options
from bitrix24.services.dashboard_query import LeadDashboardFilters, UNTRACKED_DEPARTMENT_NAME
from bitrix24.services.export import (
    export_leads_xlsx,
    filtered_lead_analytics_queryset,
)
from bitrix24.services.refresh import launch_refresh, refresh_state
from bitrix24.services.lead_mart_query import PublishedLeadQuery
from bitrix24.services.crm_marts import SnapshotChanged, MartUnavailable
from dashboards.models import Dashboard
from dashboards.services.access import user_can_view_dashboard

from .serializers import (
    LeadDashboardRequestSerializer,
    LeadDashboardRowsRequestSerializer,
)


def _can_view_crm(user) -> bool:
    dashboard = Dashboard.objects.filter(organization__code="iplast", slug="crm-analytics").first()
    return bool(dashboard and user_can_view_dashboard(user, dashboard))


class CrmReadPermission(IsAuthenticated):
    def has_permission(self, request, view):
        return super().has_permission(request, view) and _can_view_crm(request.user)


class CrmPublishedView(APIView):
    permission_classes = (CrmReadPermission,)

    def handle_exception(self, exc):
        if isinstance(exc, (SnapshotChanged, MartUnavailable)):
            error = APIException("Витрина CRM обновилась. Повторите запрос." if isinstance(exc, SnapshotChanged)
                                 else "Витрина лидов CRM ещё не опубликована.")
            error.status_code = 409 if isinstance(exc, SnapshotChanged) else 503
            return super().handle_exception(error)
        return super().handle_exception(exc)


def _filters(validated_data) -> LeadDashboardFilters:
    return LeadDashboardFilters(
        date_start=validated_data["date_start"],
        date_end=validated_data["date_end"],
        department_names=tuple(validated_data["department_names"]),
        personal_departments=validated_data.get("personal_departments"),
        manager_ids=tuple(validated_data["manager_ids"]),
        tracked_manager_ids=tuple(validated_data["tracked_manager_ids"]) if "tracked_manager_ids" in validated_data else None,
        source_ids=tuple(validated_data["source_ids"]),
        project_ids=tuple(validated_data["project_ids"]),
        semantic_status_ids=tuple(validated_data["semantic_status_ids"]),
        status_ids=tuple(validated_data["status_ids"]),
        exclude_untracked_department=validated_data[
            "exclude_untracked_department"
        ],
        group_by=validated_data["group_by"],
    )


def _personal_payload(user, payload):
    payload = dict(payload)
    personal = manager_options(user)
    payload["personal_departments"] = department_mapping(personal)
    payload["tracked_manager_ids"] = [row["manager_id"] for row in personal if row["selected"]]
    if payload.pop("use_personal_departments", True) and not payload["department_names"] and not payload["manager_ids"]:
        payload["manager_ids"] = payload["tracked_manager_ids"] or [-1]
        payload["exclude_untracked_department"] = False
    return payload


class LeadDashboardView(CrmPublishedView):
    permission_classes = (CrmReadPermission,)

    def post(self, request):
        serializer = LeadDashboardRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = _personal_payload(request.user, serializer.validated_data)
        query = PublishedLeadQuery()
        key = {"published_leads": 1, "snapshot": query.snapshot, **payload}
        cached = get_dashboard_cache(key)
        if cached is not None:
            query.check()
            return Response(cached)

        result = {**query.build(_filters(payload)), "snapshot": query.snapshot}
        query.check()
        set_dashboard_cache(key, result)
        return Response(result)


class LeadDashboardFiltersView(CrmPublishedView):
    permission_classes = (CrmReadPermission,)

    @staticmethod
    def _option_rows(filters, field_name, personal_ids=None):
        if filters is None:
            return BitrixLeadAnalytics.objects.all()
        changes = {field_name: ()}
        if field_name == "department_names":
            changes["exclude_untracked_department"] = False
        elif personal_ids is not None:
            changes["manager_ids"] = tuple(personal_ids) or (-1,)
            changes["exclude_untracked_department"] = False
        return filtered_lead_analytics_queryset(replace(filters, **changes))

    def _response(self, filters=None, user=None, use_personal_departments=True):
        personal = manager_options(user) if user else []
        if filters is not None and user:
            filters = replace(filters, tracked_manager_ids=tuple(row["manager_id"] for row in personal if row["selected"]), personal_departments=department_mapping(personal))
        personal_ids = [row["manager_id"] for row in personal if row["selected"]] if (
            user and filters and use_personal_departments and not filters.department_names and not filters.manager_ids
        ) else None
        query = PublishedLeadQuery()
        values = query.options(filters, personal_ids, personal_departments=department_mapping(personal) if user else None)
        query.check()
        sync_state = BitrixSyncState.objects.filter(entity="leads").first()
        current_refresh = refresh_state()
        selected_departments = sorted({row["filter_department_name"] for row in personal if row["selected"]})
        return Response(
            {
                **values,
                "snapshot": query.snapshot,
                "last_updated_at": (
                    current_refresh.get("finished_at")
                    if current_refresh.get("status") == "success"
                    else None
                ) or (sync_state.last_success_at if sync_state else None),
                "refresh": current_refresh,
                "default_department_names": selected_departments,
                "department_preferences": personal,
            }
        )

    def get(self, request):
        return self._response(user=request.user)

    def post(self, request):
        serializer = LeadDashboardRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self._response(_filters(serializer.validated_data), request.user, serializer.validated_data["use_personal_departments"])


class LeadDashboardExportView(CrmPublishedView):
    permission_classes = (CrmReadPermission,)

    def post(self, request):
        serializer = LeadDashboardRowsRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = _personal_payload(request.user, serializer.validated_data)
        options = {
            key: payload[key]
            for key in (
                "segment_type", "segment_key", "segment_keys", "period",
                "sort_by", "sort_direction",
            )
        }
        query = PublishedLeadQuery()
        path, _ = export_leads_xlsx(_filters(payload), rows=query.export_rows(_filters(payload), options))
        try:
            query.check()
        except BaseException:
            path.unlink(missing_ok=True)
            raise
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


class LeadDashboardRowsView(CrmPublishedView):
    permission_classes = (CrmReadPermission,)

    def post(self, request):
        serializer = LeadDashboardRowsRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = _personal_payload(request.user, serializer.validated_data)
        page = payload["page"]
        page_size = payload["page_size"]
        query = PublishedLeadQuery()
        filters = _filters(payload)
        summary = query.detail_summary(filters, payload)
        total = summary["total"]
        items = query.detail_rows(filters, payload, limit=page_size, offset=(page - 1) * page_size)
        query.check()
        tracked_ids = set(payload["tracked_manager_ids"])
        names = display_names(request.user)
        for item in items:
            item["department_name"] = names.get(item["manager_id"], item["department_name"]) if item["manager_id"] in tracked_ids else UNTRACKED_DEPARTMENT_NAME
        return Response(
            {
                "items": items,
                "page": page,
                "page_size": page_size,
                "total": total,
                "pages": (total + page_size - 1) // page_size,
                "summary": summary,
                "snapshot": query.snapshot,
            }
        )


class LeadDashboardRefreshView(APIView):
    permission_classes = (CrmReadPermission,)

    def get(self, request):
        return Response(refresh_state())

    def post(self, request):
        if not _can_view_crm(request.user):
            return Response(
                {"detail": "Недостаточно прав для просмотра Аналитики CRM."},
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


class DepartmentPreferenceView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        if not _can_view_crm(request.user):
            raise PermissionDenied("Нет доступа к Аналитике CRM.")
        return Response({"options": manager_options(request.user, with_data_only=True)})

    def post(self, request):
        if not _can_view_crm(request.user):
            raise PermissionDenied("Нет доступа к Аналитике CRM.")
        rows = request.data.get("rows")
        if not isinstance(rows, list):
            return Response({"rows": "Ожидается список менеджеров."}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"options": save_manager_options(request.user, rows)})
