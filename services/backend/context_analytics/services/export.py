from tempfile import TemporaryFile
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from context_analytics.services.reporting import get_export_report, iter_criteria_export_rows

HEADER_FILL = PatternFill("solid", fgColor="536F50")
MAX_SHEET_ROWS = 900_000

COLUMN_LABELS = {
    "date": "Дата",
    "campaign_id": "ID кампании",
    "campaign_name": "Кампания",
    "campaign": "Кампания",
    "ad_group_id": "ID группы объявлений",
    "ad_group_name": "Группа объявлений",
    "ad_group": "Группа объявлений",
    "impressions": "Показы",
    "clicks": "Клики",
    "ctr": "CTR",
    "cpc": "CPC",
    "bounces": "Отказы",
    "bounce_rate": "Отказы, %",
    "avg_impression_position": "Ср. поз. показа",
    "avg_click_position": "Ср. поз. клика",
    "criterion_id": "ID ключевой фразы",
    "criterion": "Ключевая фраза",
    "criterion_type": "Тип условия показа",
    "gender": "Пол",
    "age": "Возраст",
    "device": "Тип устройства",
    "cost": "Расход",
    "visits": "Визиты",
    "users": "Посетители",
    "leads": "Лиды",
    "lead_growth": "Прирост лидов, %",
    "cr": "CR",
    "cpl": "CPL",
    "cpl_growth": "Прирост CPL, %",
    "week": "Неделя",
    "month": "Месяц",
    "goal_name": "Цель",
    "goal_reaches": "Достижения цели",
    "goal_users": "Уникальные конверсии",
    "conversion": "Конверсия, %",
    "source": "Источник",
    "medium": "Канал",
}


def build_workbook(page, filters, destination=None, progress=None):
    if page == "criteria":
        report = {}
        rows = iter_criteria_export_rows(filters)
        keys = [
            "date", "campaign_id", "campaign", "ad_group_id", "ad_group",
            "criterion_id", "criterion", "criterion_type", "impressions", "clicks",
            "ctr", "cpc", "cost", "leads", "cr", "cpl",
        ]
        columns = [COLUMN_LABELS.get(key, key) for key in keys]
    else:
        report = get_export_report(page, filters)
        rows = report.get("rows") or report.get("campaigns") or report.get("goals") or report.get("weekly") or []

    if page in {"lead_structure", "conversions"}:
        goals = report.get("configured_goals") or []
        source = report.get("campaign_groups") or []

        if page == "conversions":
            columns = ["Дата", "Кампания", "Группа объявлений", *[goal["name"] for goal in goals], "Все лиды"]
            keys = columns
            rows = ({
                "Дата": row.get("date"),
                "Кампания": row.get("campaign_name", ""),
                "Группа объявлений": row.get("ad_group_name", ""),
                **{goal["name"]: (row.get("goals") or {}).get(str(goal["id"]), 0) for goal in goals},
                "Все лиды": row.get("leads", 0),
            } for row in source)
        else:
            columns = ["Дата", "Кампания", "Группа объявлений", "Лиды", "CR", "CPL"]
            keys = columns
            rows = ({
                "Дата": row.get("date"),
                "Кампания": row.get("campaign_name", ""),
                "Группа объявлений": row.get("ad_group_name", ""),
                "Лиды": row.get("leads", 0),
                "CR": row.get("cr", 0),
                "CPL": row.get("cpl", 0),
            } for row in source)
    elif page != "criteria":
        keys = list(rows[0].keys()) if rows else []
        if "date" in keys:
            keys = ["date", *[key for key in keys if key != "date"]]
        else:
            keys = ["date", *keys]
            rows = ({"date": None, **row} for row in rows)
        columns = [COLUMN_LABELS.get(key, key) for key in keys]

    workbook = Workbook(write_only=True)
    def create_sheet(index):
        title = "Данные" if index == 1 else f"Данные {index}"
        new_sheet = workbook.create_sheet(title)
        header = []
        for value in columns:
            cell = WriteOnlyCell(new_sheet, value=value)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = HEADER_FILL
            header.append(cell)
        new_sheet.freeze_panes = "A2"
        new_sheet.append(header)
        return new_sheet

    if columns:
        sheet_index = 1
        sheet = create_sheet(sheet_index)
        sheet_row_count = 0
        total_rows = 0
        for row in rows:
            if sheet_row_count >= MAX_SHEET_ROWS - 1:
                sheet.auto_filter.ref = f"A1:{get_column_letter(len(columns))}{sheet_row_count + 1}"
                sheet_index += 1
                sheet = create_sheet(sheet_index)
                sheet_row_count = 0
            sheet.append([row.get(key) for key in keys])
            sheet_row_count += 1
            total_rows += 1
            if progress and total_rows % 10_000 == 0:
                progress(total_rows)
        sheet.auto_filter.ref = f"A1:{get_column_letter(len(columns))}{sheet_row_count + 1}"
    else:
        workbook.create_sheet("Данные")

    if destination is not None:
        workbook.save(destination)
        return destination
    stream = TemporaryFile(mode="w+b")
    workbook.save(stream)
    stream.seek(0)
    return stream
