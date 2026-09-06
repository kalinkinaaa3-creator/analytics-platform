from datetime import date
from tempfile import TemporaryFile

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from seo_analytics.models import SeoGoal
from seo_analytics.services.clickhouse import (
    CONVERSION_TABLE, LANDING_TABLE, PHRASE_TABLE, TRAFFIC_TABLE,
    ensure_seo_tables,
)


HEADER_FILL = PatternFill("solid", fgColor="536F50")
MAX_SHEET_ROWS = 900_000
LABELS = {
    "month": "Месяц", "device": "Тип устройства",
    "search_engine": "Поисковая система", "region": "Область",
    "robotness": "Роботность",
    "age_interval": "Возраст", "gender": "Пол",
    "search_phrase": "Поисковая фраза", "phrase_type": "Тип фразы",
    "landing_url": "Страница входа", "goal_id": "ID цели",
    "goal_name": "Наименование цели", "visits": "Визиты",
    "pageviews": "Просмотры", "users": "Посетители",
    "new_users": "Новые посетители", "returned_users": "Вернувшиеся посетители",
    "new_share": "Доля новых, %", "returned_share": "Доля вернувшихся, %",
    "page_depth": "Глубина просмотра", "goal_reaches": "Достижения цели",
    "goal_users": "Уникальные конверсии", "conversion": "Конверсия, %",
    "loaded_at": "Дата загрузки",
}


def _definition(page):
    if page in {"visits", "new-visitors", "returning-visitors", "traffic-change"}:
        return {
            "table": TRAFFIC_TABLE,
            "columns": (
                "month", "device", "search_engine", "region", "robotness",
                "age_interval", "gender", "visits", "pageviews",
                "users", "new_users", "returned_users", "new_share",
                "returned_share", "page_depth", "loaded_at",
            ),
            "select": (
                "month, device, search_engine, region, robotness, "
                "age_interval, gender, visits, pageviews, users, new_users, "
                "greatest(toInt64(users) - toInt64(new_users), 0) returned_users, "
                "if(users=0, 0, new_users*100.0/users) new_share, "
                "if(users=0, 0, greatest(toInt64(users)-toInt64(new_users),0)*100.0/users) returned_share, "
                "if(visits=0, 0, pageviews*1.0/visits) page_depth, loaded_at"
            ),
            "filters": {"device", "search_engine", "region", "robotness"},
        }
    if page == "search-phrases":
        return {
            "table": PHRASE_TABLE,
            "columns": (
                "month", "search_engine", "robotness", "search_phrase", "phrase_type",
                "visits", "pageviews", "users", "new_users", "returned_users",
                "new_share", "returned_share", "page_depth", "loaded_at",
            ),
            "select": (
                "month, search_engine, robotness, search_phrase, phrase_type, visits, "
                "pageviews, users, new_users, "
                "greatest(toInt64(users)-toInt64(new_users),0) returned_users, "
                "if(users=0,0,new_users*100.0/users) new_share, "
                "if(users=0,0,greatest(toInt64(users)-toInt64(new_users),0)*100.0/users) returned_share, "
                "if(visits=0,0,pageviews*1.0/visits) page_depth, loaded_at"
            ),
            "filters": {"search_engine", "robotness", "phrase_type"},
        }
    if page in {"conversions", "unique-conversions"}:
        conversion_expression = (
            "if(goal_id=0 OR users=0,0,goal_users*100.0/users)"
            if page == "unique-conversions"
            else "if(goal_id=0 OR visits=0,0,goal_reaches*100.0/visits)"
        )
        return {
            "table": CONVERSION_TABLE,
            "columns": (
                "month", "device", "search_engine", "region", "search_phrase",
                "phrase_type", "age_interval", "gender", "goal_id", "goal_name", "goal_reaches", "goal_users",
                "visits", "users", "conversion", "loaded_at",
            ),
            "select": (
                "month, device, search_engine, region, search_phrase, phrase_type, age_interval, gender, "
                "goal_id, goal_name, goal_reaches, goal_users, visits, users, "
                f"{conversion_expression} conversion, loaded_at"
            ),
            "filters": {"device", "search_engine", "region", "phrase_type"},
        }
    if page == "landing-pages":
        return {
            "table": LANDING_TABLE,
            "columns": (
                "month", "device", "search_engine", "region", "landing_url", "visits",
                "pageviews", "users", "new_users", "new_share", "page_depth", "loaded_at",
            ),
            "select": (
                "month, device, search_engine, region, landing_url, visits, pageviews, "
                "users, new_users, if(users=0,0,new_users*100.0/users) new_share, "
                "if(visits=0,0,pageviews*1.0/visits) page_depth, loaded_at"
            ),
            "filters": {"device", "search_engine", "region"},
        }
    return None


def _where(filters, supported, date_from, date_to, page):
    clauses = ["month >= %(date_from)s", "month <= %(date_to)s"]
    params = {
        "date_from": date_from.replace(day=1),
        "date_to": date_to.replace(day=1),
    }
    for key in ("device", "search_engine", "region", "robotness", "phrase_type"):
        values = tuple(filters.get(key) or ())
        if key in supported and values:
            clauses.append(f"{key} IN %({key})s")
            params[key] = values
    if page in {"conversions", "unique-conversions"}:
        goal_ids = tuple(SeoGoal.objects.filter(is_active=True, is_available=True).values_list("external_id", flat=True))
        clauses.append("goal_id IN %(goal_ids)s")
        # goal_id=0 is a technical denominator row named "Итого" and must not
        # be exposed as a data row in user exports.
        params["goal_ids"] = goal_ids or (-1,)
    return " AND ".join(clauses), params


def _header(sheet, columns):
    sheet.freeze_panes = "A2"
    for index, column in enumerate(columns, 1):
        width = 34 if column in {"search_phrase", "landing_url", "goal_name"} else 19
        sheet.column_dimensions[get_column_letter(index)].width = width
    cells = []
    for column in columns:
        cell = WriteOnlyCell(sheet, value=LABELS.get(column, column))
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = HEADER_FILL
        cells.append(cell)
    sheet.append(cells)
    sheet.auto_filter.ref = f"A1:{get_column_letter(len(columns))}1"


def _month_label(month):
    return month.strftime("%m.%Y")


def _export_columns(definition):
    # Keep a single linear month column followed by dimensions and individual
    # metric columns. loaded_at is an internal field and is not report data.
    return tuple(column for column in definition["columns"] if column != "loaded_at")


def build_report_workbook(page, filters, destination=None, progress=None):
    definition = _definition(page)
    workbook = Workbook(write_only=True)
    if definition is None:
        sheet = workbook.create_sheet("Данные")
        sheet.append(["Данные раздела пока недоступны"])
    else:
        client = ensure_seo_tables()
        date_from = date.fromisoformat(filters["date_from"])
        date_to = date.fromisoformat(filters["date_to"])
        columns = _export_columns(definition)
        source_columns = definition["columns"]
        indexes = tuple(source_columns.index(column) for column in columns)
        where, params = _where(
            filters, definition["filters"], date_from, date_to, page,
        )
        rows = client.execute_iter(
            f"SELECT {definition['select']} FROM {definition['table']} "
            f"WHERE {where} ORDER BY month, search_engine",
            params,
            settings={"max_block_size": 10_000},
        )
        sheet = None
        sheet_index = 0
        row_number = 0
        total_rows = 0
        for source_row in rows:
            if sheet is None or row_number >= MAX_SHEET_ROWS - 1:
                if sheet is not None:
                    sheet.auto_filter.ref = f"A1:{get_column_letter(len(columns))}{row_number + 1}"
                sheet_index += 1
                title = "Данные" if sheet_index == 1 else f"Данные {sheet_index}"
                sheet = workbook.create_sheet(title)
                _header(sheet, columns)
                row_number = 0
            output_row = [source_row[index] for index in indexes]
            output_row[0] = _month_label(output_row[0])
            sheet.append(output_row)
            row_number += 1
            total_rows += 1
            if progress and total_rows % 10_000 == 0:
                progress(total_rows)
        if sheet is None:
            sheet = workbook.create_sheet("Данные")
            _header(sheet, columns)
        else:
            sheet.auto_filter.ref = f"A1:{get_column_letter(len(columns))}{row_number + 1}"
    if destination is not None:
        workbook.save(destination)
        return destination
    output = TemporaryFile(mode="w+b")
    workbook.save(output)
    output.seek(0)
    return output
