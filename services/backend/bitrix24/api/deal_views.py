from datetime import timedelta
from io import BytesIO

from django.http import FileResponse
from openpyxl import Workbook
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, APIException
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from bitrix24.cache import get_dashboard_cache, set_dashboard_cache
from bitrix24.services import full_cycle
from bitrix24.services.deal_metrics import metrics, panel, dimension
from bitrix24.services.deal_repository import (
    DEFAULT_CATEGORIES, MOSCOW,
)
from bitrix24.services.dashboard_query import previous_comparison_date, group_period_start, previous_group_period
from bitrix24.services.refresh import refresh_state
from bitrix24.services.crm_marts import MartReader, MartUnavailable, SnapshotChanged
from .views import _can_view_crm


class DealRequest(serializers.Serializer):
    date_start = serializers.DateField()
    date_end = serializers.DateField()
    department_names = serializers.ListField(child=serializers.CharField(max_length=255), default=list)
    manager_ids = serializers.ListField(child=serializers.IntegerField(), default=list)
    category_ids = serializers.ListField(child=serializers.IntegerField(min_value=0), default=lambda: list(DEFAULT_CATEGORIES))
    stage_keys = serializers.ListField(child=serializers.RegexField(r"^\d+:.+$", max_length=200), default=list)
    results = serializers.ListField(child=serializers.ChoiceField(choices=("S", "F", "P", "?")), default=list)
    source_ids = serializers.ListField(child=serializers.CharField(allow_blank=True, max_length=128), default=list)
    exclude_untracked_department = serializers.BooleanField(default=True)
    group_by = serializers.ChoiceField(choices=("day", "week", "month", "year"), default="month")
    tab = serializers.ChoiceField(choices=("funnel", "managers"), default="funnel")
    segment_type = serializers.ChoiceField(choices=("stages", "results", "managers", "loss-reasons", "lead-stage", "deal-stage", "standalone"), allow_null=True, default=None)
    segment_key = serializers.CharField(max_length=200, allow_blank=True, default="")
    segment_keys = serializers.ListField(child=serializers.CharField(max_length=200), default=list)
    detail_category_id = serializers.IntegerField(min_value=0, allow_null=True, default=None)
    period = serializers.DateField(allow_null=True, default=None)
    page = serializers.IntegerField(min_value=1, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=200, default=50)
    sort_by = serializers.ChoiceField(choices=("deal_id", "lead_id", "title", "lead_title", "link_state", "manager_name", "department_name", "category_name", "stage_name", "amount", "source_created_at", "closed_at", "stage_days", "cycle_days", "full_cycle_days", "selected_stage_days", "lead_created_at"), default="source_created_at")
    sort_direction = serializers.ChoiceField(choices=("asc", "desc"), default="desc")

    def validate(self, attrs):
        if attrs["date_end"] < attrs["date_start"]:
            raise serializers.ValidationError("Дата окончания раньше даты начала.")
        return attrs


class Updating(APIException):
    status_code = 409
    default_detail = "Идёт обновление CRM. Отчёт будет загружен после его завершения."


class NotPublished(APIException):
    status_code = 503
    default_detail = "Витрины CRM ещё не опубликованы. Выполните refresh_bitrix24 --skip-bitrix."


def reader():
    try:
        return MartReader()
    except MartUnavailable as exc:
        raise NotPublished() from exc


def bundle(section, filters):
    scope = {key: value for key, value in filters.items() if key not in (
        "tab", "segment_type", "segment_key", "segment_keys", "detail_category_id", "period", "page", "page_size", "sort_by", "sort_direction")}
    if section == "full-cycle":
        scope.pop("stage_keys", None)
        scope.pop("results", None)
    mart = reader()
    key = {"crm_section": section, "schema": 2, "snapshot": mart.snapshot, **scope}
    cached = get_dashboard_cache(key)
    if cached is not None:
        return cached
    if refresh_state().get("running"):
        raise Updating()
    refs = mart.refs
    previous = {**scope, "date_start": previous_comparison_date(scope["date_start"], scope["group_by"]),
                "date_end": previous_comparison_date(scope["date_end"], scope["group_by"])}
    if section == "deals":
        start = group_period_start(scope["date_start"], scope["group_by"])
        prior = {**scope, "date_start": previous_group_period(start, scope["group_by"]), "date_end": start - timedelta(days=1)}
        current, old, prior_rows = mart.deals(scope), mart.deals(previous), mart.deals(prior)
        result = {"current": current, "previous": old, "prior": prior_rows, "refs": refs}
    else:
        current, deals, standalone = mart.cohort(scope)
        old, old_deals, _ = mart.cohort(previous, include_standalone=False)
        result = {"current": current, "deals": deals, "standalone": standalone,
                  "previous": old, "previous_deals": old_deals, "refs": refs}
    result["comparison_period"] = {"date_start": previous["date_start"], "date_end": previous["date_end"]}
    result["snapshot"] = mart.snapshot
    # Do not cache a result when a load started while its queries were running.
    if refresh_state().get("running"):
        raise Updating()
    try:
        mart.check()
    except SnapshotChanged as exc:
        raise Updating() from exc
    set_dashboard_cache(key, result)
    return result


def rows_for(section, data, filters):
    if section == "full-cycle":
        rows = full_cycle.detail_rows(data["current"], data["deals"], data["standalone"], filters)
    else:
        rows = data["current"]
        kind = filters["segment_type"]
        if kind == "standalone":
            rows = [row for row in rows if not row.get("lead_id")]
        keys = filters["segment_keys"] or ([filters["segment_key"]] if filters["segment_key"] else [])
        if kind in ("stages", "results", "managers", "loss-reasons"):
            rows = [row for row in rows if (kind != "loss-reasons" or row["result"] == "F") and (not keys or dimension(row, kind)[0] in keys)]
        if filters["period"]:
            rows = [row for row in rows if group_period_start(row["source_created_at"].date(), filters["group_by"]) == filters["period"]]
    field = filters["sort_by"]
    available = [row for row in rows if row.get(field) is not None]
    missing = [row for row in rows if row.get(field) is None]
    return sorted(available, key=lambda row: row[field], reverse=filters["sort_direction"] == "desc") + missing


EXPORT_COLUMNS = [("lead_id", "ID лида"), ("deal_id", "ID сделки"), ("lead_title", "Лид"), ("title", "Сделка"),
                  ("manager_name", "Менеджер сделки"), ("department_name", "Подразделение сделки"),
                  ("lead_manager", "Менеджер лида"), ("lead_department", "Подразделение лида"),
                  ("category_name", "Воронка"), ("category_id", "ID воронки"), ("stage_name", "Стадия"), ("stage_id", "ID стадии"),
                  ("result_name", "Результат"), ("source_name", "Источник лида"), ("lead_created_at", "Создан лид"),
                  ("source_created_at", "Создана сделка"), ("closed_at", "Завершена по истории"),
                  ("stage_days", "Дней на текущей стадии"), ("cycle_days", "Цикл сделки, дней"),
                  ("full_cycle_days", "Полный цикл, дней"), ("selected_stage_days", "Дней на выбранном этапе"), ("amount", "Сумма сделки, руб"), ("currency_id", "Валюта"),
                  ("link_state", "Связь лид → сделка")]


def export_response(rows, section, filters):
    book = Workbook(write_only=True)
    sheet = book.create_sheet("Сделки" if section == "deals" else "Полный цикл")
    sheet.freeze_panes = "C2"
    from openpyxl.cell import WriteOnlyCell
    def cell(value):
        result = WriteOnlyCell(sheet)
        if hasattr(value, "tzinfo"):
            value = value.astimezone(MOSCOW).replace(tzinfo=None) if value.tzinfo else value
            result.number_format = "dd.mm.yyyy hh:mm:ss"
        result.value = value
        if isinstance(value, str):
            result.data_type = "s"
        return result
    sheet.append([cell(label) for _, label in EXPORT_COLUMNS])
    for row in rows:
        sheet.append([cell(row.get(key)) for key, _ in EXPORT_COLUMNS])
    info = book.create_sheet("Условия")
    info.append(["Раздел", section])
    for key, value in filters.items():
        info.append([key, str(value)])
    info.append(["Период", "Дата создания лида; связанные сделки за всё время" if section == "full-cycle" else "Дата создания сделки"])
    stream = BytesIO()
    book.save(stream)
    stream.seek(0)
    return FileResponse(stream, as_attachment=True, filename=f"crm_{section}.xlsx")


class DealReportView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, section, part):
        if not _can_view_crm(request.user):
            raise PermissionDenied("Нет доступа к Аналитике CRM.")
        serializer = DealRequest(data=request.data)
        serializer.is_valid(raise_exception=True)
        filters = serializer.validated_data
        if part == "filters":
            mart = reader()
            return Response({**mart.options(filters), "snapshot": mart.snapshot})
        data = bundle(section, filters)
        def respond(value):
            return Response({**value, "snapshot": data["snapshot"]})
        if part in ("rows", "export"):
            rows = rows_for(section, data, filters)
            if part == "export":
                return export_response(rows, section, filters)
            start = (filters["page"] - 1) * filters["page_size"]
            public_rows = [{k: v for k, v in row.items() if k not in ("visits", "visited")} for row in rows[start:start + filters["page_size"]]]
            return respond({"items": public_rows, "total": len(rows), "page": filters["page"],
                             "pages": (len(rows) + filters["page_size"] - 1) // filters["page_size"]})
        comparison = data["comparison_period"]
        if section == "deals":
            if part == "summary":
                return respond({"cards": metrics(data["current"]), "comparison_period": comparison})
            if part in ("stages", "results", "managers", "loss-reasons"):
                return respond({**panel(data["current"], data["previous"], data["prior"], part, filters["group_by"], data["refs"]["stages"]), "comparison_period": comparison})
        else:
            leads, deals = data["current"], data["deals"]
            if part == "summary":
                return respond({"cards": full_cycle.summary(leads, deals),
                                 "previous": full_cycle.summary(data["previous"], data["previous_deals"]),
                                 "standalone": len(data["standalone"]), "comparison_period": comparison})
            if part == "funnel":
                return respond(full_cycle.funnel(leads, deals, data["refs"]))
            if part == "dynamics":
                return respond({"rows": full_cycle.dynamics(leads, deals, filters["group_by"])})
            if part == "managers":
                return respond({"rows": full_cycle.managers(leads, deals)})
        raise serializers.ValidationError("Неизвестный раздел отчёта.")
