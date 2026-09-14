from io import BytesIO

from django.http import FileResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, APIException
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from bitrix24.cache import get_dashboard_cache, set_dashboard_cache
from bitrix24.services.deal_metrics import dimension
from bitrix24.services.deal_dashboard_query import DealDashboardQuery, PARTS
from bitrix24.services.deal_repository import (
    DEFAULT_CATEGORIES, MOSCOW,
)
from bitrix24.services.dashboard_query import group_period_start, UNTRACKED_DEPARTMENT_NAME
from bitrix24.services.crm_marts import MartReader, MartUnavailable, SnapshotChanged
from bitrix24.services.department_preferences import manager_options
from bitrix24.services.export import _format_duration
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
    use_personal_departments = serializers.BooleanField(default=True)
    group_by = serializers.ChoiceField(choices=("day", "week", "month", "year"), default="month")
    lead_link = serializers.ChoiceField(choices=("all", "linked"), default="all")
    tab = serializers.ChoiceField(choices=("funnel", "managers"), default="funnel")
    segment_type = serializers.ChoiceField(choices=("stages", "results", "sources", "managers", "loss-reasons"), allow_null=True, default=None)
    segment_key = serializers.CharField(max_length=200, allow_blank=True, default="")
    segment_keys = serializers.ListField(child=serializers.CharField(max_length=200), default=list)
    detail_category_id = serializers.IntegerField(min_value=0, allow_null=True, default=None)
    period = serializers.DateField(allow_null=True, default=None)
    page = serializers.IntegerField(min_value=1, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=200, default=50)
    sort_by = serializers.ChoiceField(choices=("deal_id", "lead_id", "title", "is_return_customer", "deal_type_name", "manager_name", "department_name", "category_name", "stage_name", "source_name", "activity_name", "amount", "source_created_at", "speed_calculated_at", "processing_duration_days"), default="source_created_at")
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
    except SnapshotChanged as exc:
        raise Updating() from exc


def report_scope(filters):
    return {key: sorted(value, key=str) if isinstance(value, (list, tuple)) else value
            for key, value in filters.items() if key not in (
                "tab", "segment_type", "segment_key", "segment_keys", "detail_category_id", "period",
                "page", "page_size", "sort_by", "sort_direction")}


def bundle(section, filters, mart=None):
    mart = mart or reader()
    scope = report_scope(filters)
    key = {"crm_section": section, "schema": 6, "snapshot": mart.snapshot, **scope}
    cached = get_dashboard_cache(key)
    if cached is not None:
        return cached
    result = {**DealDashboardQuery(mart).build(scope), "snapshot": mart.snapshot}
    try:
        mart.check()
    except SnapshotChanged as exc:
        raise Updating() from exc
    set_dashboard_cache(key, result)
    return result


def filter_options(mart, filters, personal_ids):
    scope = report_scope(filters)
    scope.pop("group_by", None)
    key = {"deal_options": 2, "snapshot": mart.snapshot, "personal_ids": personal_ids, **scope}
    cached = get_dashboard_cache(key)
    if cached is not None:
        return cached
    options = mart.options(scope, personal_manager_ids=personal_ids)
    mart.check()
    set_dashboard_cache(key, options)
    return options


def rows_for(section, data, filters):
    rows = data["current"]
    kind = filters["segment_type"]
    keys = filters["segment_keys"] or ([filters["segment_key"]] if filters["segment_key"] else [])
    if kind in ("stages", "results", "sources", "managers", "loss-reasons"):
        rows = [row for row in rows if (kind != "loss-reasons" or row["result"] == "F") and (not keys or dimension(row, kind)[0] in keys)]
    if filters["period"]:
        rows = [row for row in rows if group_period_start(row["source_created_at"].date(), filters["group_by"]) == filters["period"]]
    field = filters["sort_by"]
    available = [row for row in rows if row.get(field) is not None]
    missing = [row for row in rows if row.get(field) is None]
    return sorted(available, key=lambda row: row[field], reverse=filters["sort_direction"] == "desc") + missing


DEAL_EXPORT_COLUMNS = [
    ("deal_id", "ID сделки"), ("lead_id", "ID лида"), ("title", "Наименование сделки"),
    ("is_return_customer", "Повторная сделка"), ("deal_type_name", "Тип"),
    ("manager_name", "Менеджер"), ("department_name", "Подразделение"),
    ("category_name", "Воронка"), ("stage_name", "Стадия"), ("source_name", "Источник"),
    ("activity_name", "Мероприятие"), ("source_created_at", "Дата создания"),
    ("speed_calculated_at", "Скорость рассчитана по"), ("amount", "Сумма, руб"),
    ("processing_duration_days", "Скорость обработки"),
]


def export_response(rows, section, filters):
    book = Workbook(write_only=True)
    sheet = book.create_sheet("Сделки" if section == "deals" else "Полный цикл")
    sheet.freeze_panes = "A2"
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
    columns = DEAL_EXPORT_COLUMNS
    header_fill = PatternFill("solid", fgColor="1F4E78")
    header_font = Font(color="FFFFFF", bold=True)
    header_cells = []
    for _, label in columns:
        header_cell = cell(label)
        header_cell.fill = header_fill
        header_cell.font = header_font
        header_cell.alignment = Alignment(horizontal="center", vertical="center")
        header_cells.append(header_cell)
    sheet.append(header_cells)
    for row in rows:
        row = dict(row)
        duration_days = row.get("processing_duration_days")
        row["processing_duration_days"] = _format_duration(
            duration_days * 86400 if duration_days is not None else None
        )
        sheet.append([cell(row.get(key)) for key, _ in columns])
    info = book.create_sheet("Условия")
    info.append(["Раздел", section])
    for key, value in filters.items():
        if key != "tracked_manager_ids":
            info.append([key, str(value)])
    info.append(["Период", "Дата создания сделки"])
    stream = BytesIO()
    book.save(stream)
    stream.seek(0)
    filename = "bitrix24_deals_detail.xlsx" if filters.get("segment_type") else "bitrix24_deals_generation.xlsx"
    return FileResponse(stream, as_attachment=True, filename=filename)


class DealReportView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, section, part):
        if not _can_view_crm(request.user):
            raise PermissionDenied("Нет доступа к Аналитике CRM.")
        serializer = DealRequest(data=request.data)
        serializer.is_valid(raise_exception=True)
        filters = serializer.validated_data
        personal = manager_options(request.user)
        selected_ids = [row["manager_id"] for row in personal if row["selected"]]
        filters["tracked_manager_ids"] = selected_ids
        use_personal = filters.pop("use_personal_departments", True) and not filters["department_names"] and not filters["manager_ids"]
        option_filters = dict(filters)
        if use_personal:
            filters["manager_ids"] = selected_ids or [-1]
            filters["exclude_untracked_department"] = False
        mart = reader()
        try:
            if part in ("filters", "report"):
                options = {**filter_options(mart, option_filters, selected_ids if use_personal else None),
                           "snapshot": mart.snapshot,
                           "default_department_names": sorted({row["filter_department_name"] for row in personal if row["selected"]}),
                           "department_preferences": personal}
                if part == "filters":
                    mart.check()
                    return Response(options)
            if part in ("rows", "export"):
                query = DealDashboardQuery(mart)
                if part == "export":
                    selected = set(selected_ids)
                    rows = ({**row, "department_name": row["department_name"] if row["manager_id"] in selected else UNTRACKED_DEPARTMENT_NAME}
                            for row in query.export_rows(filters))
                    response = export_response(rows, section, filters)
                    mart.check()
                    return response
                summary_key = {"deal_detail_summary": 1, "snapshot": mart.snapshot,
                               **{key: value for key, value in filters.items() if key not in ("page", "page_size", "sort_by", "sort_direction", "tab")}}
                summary = get_dashboard_cache(summary_key)
                if summary is None:
                    summary = query.detail_summary(filters)
                    mart.check()
                    set_dashboard_cache(summary_key, summary)
                rows = query.detail_rows(filters, limit=filters["page_size"], offset=(filters["page"] - 1) * filters["page_size"])
                names = {row["manager_id"]: row["display_name"] for row in personal}
                selected = set(selected_ids)
                for row in rows:
                    row["department_name"] = names.get(row["manager_id"], row["department_name"]) if row["manager_id"] in selected else UNTRACKED_DEPARTMENT_NAME
                mart.check()
                return Response({"items": rows, "total": summary["total"], "page": filters["page"],
                                 "pages": (summary["total"] + filters["page_size"] - 1) // filters["page_size"],
                                 "summary": summary, "snapshot": mart.snapshot})
            data = bundle(section, filters, mart)
            mart.check()
            if part == "report":
                return Response({**data, "options": options})
            if part == "summary":
                return Response({"cards": data["cards"], "comparison_period": data["comparison_period"], "snapshot": data["snapshot"]})
            if part in PARTS:
                return Response({**data[part], "snapshot": data["snapshot"]})
        except SnapshotChanged as exc:
            raise Updating() from exc
        raise serializers.ValidationError("\u041d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u044b\u0439 \u0440\u0430\u0437\u0434\u0435\u043b \u043e\u0442\u0447\u0451\u0442\u0430.")
