from __future__ import annotations

import tempfile
from datetime import datetime, time, timedelta
from pathlib import Path

from django.db.models import Q
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Alignment, Font, PatternFill

from bitrix24.models import BitrixLeadAnalytics
from bitrix24.services.dashboard_query import LeadDashboardFilters
from bitrix24.services.dashboard_query import UNTRACKED_DEPARTMENT_NAME


HEADERS = (
    "ID",
    "Название лида",
    "Наименование контрагента",
    "Повторное обращение",
    "Менеджер",
    "Стадия",
    "Источник",
    "Мероприятия",
    "Проект",
    "Дата создания",
    "Дата изменения (по данным Bitrix24)",
    "Скорость рассчитана по",
    "Сумма, руб",
    "Скорость обработки",
)


def _aware_start(value):
    return timezone.make_aware(datetime.combine(value, time.min))


def _excel_datetime(value):
    if value is None:
        return None
    if timezone.is_aware(value):
        value = timezone.localtime(value)
    return value.replace(tzinfo=None)


def _format_duration(seconds):
    if seconds is None:
        return None
    seconds = max(0, int(seconds))
    if seconds < 3600:
        return f"{max(1, round(seconds / 60))} мин."
    if seconds < 86400:
        return f"{max(1, seconds // 3600)} час."
    days, remainder = divmod(seconds, 86400)
    return f"{days} дн. {remainder // 3600} час."


def filtered_lead_analytics_queryset(
    filters: LeadDashboardFilters,
    *,
    segment_type=None,
    segment_key="",
    segment_keys=(),
    period=None,
    sort_by="source_created_at",
    sort_direction="desc",
):
    queryset = BitrixLeadAnalytics.objects.filter(
        source_created_at__gte=_aware_start(filters.date_start),
        source_created_at__lt=_aware_start(filters.date_end + timedelta(days=1)),
    )
    if filters.exclude_untracked_department:
        queryset = queryset.exclude(
            department_name=UNTRACKED_DEPARTMENT_NAME
        )
    for field_name, values in (
        ("department_name", filters.department_names),
        ("manager_id", filters.manager_ids),
        ("source_id", filters.source_ids),
        ("project_id", filters.project_ids),
        ("status_semantic_id", filters.semantic_status_ids),
        ("status_id", filters.status_ids),
    ):
        if values:
            queryset = queryset.filter(**{f"{field_name}__in": values})
    if segment_type and (segment_key or segment_keys):
        segment_fields = {
            "dashboard_status": "dashboard_status",
            "source": "source_id",
            "manager": "manager_id",
            "low_quality_status": "status_id",
        }
        segment_field = segment_fields[segment_type]
        if segment_type == "manager" and segment_keys:
            assigned_keys = [key for key in segment_keys if key != "__unassigned__"]
            manager_filter = Q(manager_id__in=assigned_keys)
            if "__unassigned__" in segment_keys:
                manager_filter |= Q(manager_id__isnull=True)
            queryset = queryset.filter(manager_filter)
        elif segment_type == "manager" and segment_key == "__unassigned__":
            queryset = queryset.filter(manager_id__isnull=True)
        elif segment_keys:
            queryset = queryset.filter(**{f"{segment_field}__in": segment_keys})
        else:
            queryset = queryset.filter(**{segment_field: segment_key})
        if segment_type == "low_quality_status":
            queryset = queryset.filter(is_low_quality=True, is_apm=False)
    if period:
        if filters.group_by == "day":
            period_end = period + timedelta(days=1)
        elif filters.group_by == "week":
            period_end = period + timedelta(days=7)
        elif filters.group_by == "month":
            period_end = (period.replace(day=28) + timedelta(days=4)).replace(day=1)
        else:
            period_end = period.replace(year=period.year + 1, month=1, day=1)
        queryset = queryset.filter(
            source_created_at__gte=_aware_start(period),
            source_created_at__lt=_aware_start(period_end),
        )
    prefix = "-" if sort_direction == "desc" else ""
    return queryset.order_by(f"{prefix}{sort_by}", "lead_id")


def export_leads_xlsx(filters: LeadDashboardFilters, **query_options) -> tuple[Path, int]:
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("Лидогенерация")
    sheet.freeze_panes = "A2"
    header_fill = PatternFill("solid", fgColor="1F4E78")
    header_font = Font(color="FFFFFF", bold=True)
    header_cells = []
    for title in HEADERS:
        cell = WriteOnlyCell(sheet, value=title)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
        header_cells.append(cell)
    sheet.append(header_cells)

    count = 0
    for item in filtered_lead_analytics_queryset(
        filters, **query_options
    ).iterator(chunk_size=1000):
        sheet.append(
            (
                item.lead_id,
                item.title,
                item.company_name,
                (
                    "Повторный" if item.is_return_customer is True
                    else ("Новый" if item.is_return_customer is False else "Не определён")
                ),
                item.manager_name,
                item.status_name or item.status_id,
                item.source_name or item.source_id,
                item.activity_name,
                item.project_name or item.project_id or "Не указан",
                _excel_datetime(item.source_created_at),
                _excel_datetime(item.source_updated_at),
                _excel_datetime(item.first_processing_at or item.calculated_at),
                item.opportunity,
                _format_duration(item.processing_duration_seconds),
            )
        )
        count += 1

    temporary = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    path = Path(temporary.name)
    temporary.close()
    workbook.save(path)
    return path, count
