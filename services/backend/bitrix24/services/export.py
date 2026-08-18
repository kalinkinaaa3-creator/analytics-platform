from __future__ import annotations

import tempfile
from datetime import datetime, time, timedelta
from pathlib import Path

from django.utils import timezone
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Alignment, Font, PatternFill

from bitrix24.models import BitrixLeadAnalytics
from bitrix24.services.dashboard_query import LeadDashboardFilters


HEADERS = (
    "ID",
    "Название лида",
    "Менеджер",
    "Стадия",
    "Источник",
    "Дата создания",
    "Дата изменения (по данным Bitrix24)",
    "Сумма, руб",
    "Обработка, дней",
)


def _aware_start(value):
    return timezone.make_aware(datetime.combine(value, time.min))


def _excel_datetime(value):
    if value is None:
        return None
    if timezone.is_aware(value):
        value = timezone.localtime(value)
    return value.replace(tzinfo=None)


def filtered_lead_analytics_queryset(filters: LeadDashboardFilters):
    queryset = BitrixLeadAnalytics.objects.filter(
        source_created_at__gte=_aware_start(filters.date_start),
        source_created_at__lt=_aware_start(filters.date_end + timedelta(days=1)),
    )
    for field_name, values in (
        ("primary_department_id", filters.department_ids),
        ("manager_id", filters.manager_ids),
        ("source_id", filters.source_ids),
        ("status_id", filters.status_ids),
    ):
        if values:
            queryset = queryset.filter(**{f"{field_name}__in": values})
    return queryset.order_by("source_created_at", "lead_id")


def export_leads_xlsx(filters: LeadDashboardFilters) -> tuple[Path, int]:
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
    for item in filtered_lead_analytics_queryset(filters).iterator(chunk_size=1000):
        sheet.append(
            (
                item.lead_id,
                item.title,
                item.manager_name,
                item.status_name or item.status_id,
                item.source_name or item.source_id,
                _excel_datetime(item.source_created_at),
                _excel_datetime(item.source_updated_at),
                item.opportunity,
                item.processing_duration_days,
            )
        )
        count += 1

    temporary = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    path = Path(temporary.name)
    temporary.close()
    workbook.save(path)
    return path, count
