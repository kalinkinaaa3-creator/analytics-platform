from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO

from django.db import transaction
from openpyxl import Workbook, load_workbook
from openpyxl.utils.datetime import from_excel

from .models import LeadGenerationPlan
from .cache import invalidate_lead_generation_cache


HEADERS = ("Неделя", "Бюджет, руб. с НДС", "Средняя цена целевого лида", "Кол-во целевых лидов", "План выручки (Потенциал выручки, руб)")
MIN_WEEK = date(2024, 12, 30)
HEADER_ALIASES = (
    {"неделя", "дата"}, {"бюджет, руб. с ндс", "бюджет"},
    {"средняя цена целевого лида", "стоимость лида"},
    {"кол-во целевых лидов", "количество целевых лидов"},
    {"план выручки (потенциал выручки, руб)", "план выручки", "потенциал выручки, руб"},
)


def _normalized_header(value):
    return " ".join(str(value or "").strip().lower().replace("ё", "е").split())


def _date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        converted = from_excel(value)
        return converted.date() if isinstance(converted, datetime) else converted
    text = str(value or "").strip()
    for pattern in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            pass
    raise ValueError(f"Некорректная дата недели: {text or 'пусто'}.")


def _decimal(value, coordinate):
    if value in (None, ""):
        raise ValueError(f"Ячейка {coordinate} не заполнена.")
    try:
        result = Decimal(str(value).replace(" ", "").replace(",", "."))
    except (InvalidOperation, ValueError):
        raise ValueError(f"Ячейка {coordinate} должна содержать число.")
    if not result.is_finite() or result < 0:
        raise ValueError(f"Ячейка {coordinate} должна содержать неотрицательное число.")
    return result


def load_plan(uploaded, user):
    content = uploaded.read()
    formulas = load_workbook(BytesIO(content), data_only=False, read_only=True)
    values = load_workbook(BytesIO(content), data_only=True, read_only=True)
    if not values.sheetnames:
        raise ValueError("Файл не содержит листов.")
    formula_sheet, value_sheet = formulas[formulas.sheetnames[0]], values[values.sheetnames[0]]
    if value_sheet.max_row < 2:
        raise ValueError("Файл не содержит строк плана.")
    for column, aliases in enumerate(HEADER_ALIASES, 1):
        actual = _normalized_header(value_sheet.cell(1, column).value)
        if actual not in aliases:
            raise ValueError(f"Некорректный заголовок {value_sheet.cell(1, column).coordinate}: ожидается «{HEADERS[column - 1]}».")
    rows, seen = [], set()
    for row_number in range(2, value_sheet.max_row + 1):
        raw = [value_sheet.cell(row_number, column).value for column in range(1, 6)]
        formula_cells = [formula_sheet.cell(row_number, column) for column in range(1, 6)]
        if all(value in (None, "") for value in raw) and all(cell.value in (None, "") for cell in formula_cells):
            continue
        for column, cell in enumerate(formula_cells):
            if cell.data_type == "f" and raw[column] is None:
                raise ValueError(f"Ячейка {cell.coordinate} содержит формулу без сохранённого результата.")
        week = _date(raw[0])
        if week.weekday() != 0:
            raise ValueError(f"Строка {row_number}: {week:%d.%m.%Y} не является понедельником.")
        if week < MIN_WEEK:
            raise ValueError(f"Строка {row_number}: неделя не может быть раньше {MIN_WEEK:%d.%m.%Y}.")
        if week in seen:
            raise ValueError(f"В файле повторяется неделя {week:%d.%m.%Y}.")
        seen.add(week)
        rows.append((week, *[_decimal(raw[column], value_sheet.cell(row_number, column + 1).coordinate) for column in range(1, 5)]))
    if not rows:
        raise ValueError("Файл не содержит заполненных строк плана.")
    created = updated = 0
    with transaction.atomic():
        for week, budget, price, leads, revenue in rows:
            _item, was_created = LeadGenerationPlan.objects.update_or_create(
                week_start=week,
                defaults={"budget_vat": budget, "target_lead_price": price, "target_leads": leads, "revenue_plan": revenue, "updated_by": user},
            )
            created += int(was_created)
            updated += int(not was_created)
    invalidate_lead_generation_cache()
    return {"loaded": len(rows), "created": created, "updated": updated}


def plan_workbook():
    workbook = Workbook()
    upload = workbook.active
    upload.title = "Загрузка"
    upload.append(HEADERS)
    current = workbook.create_sheet("Текущий план")
    current.append(HEADERS)
    for item in LeadGenerationPlan.objects.all():
        current.append([item.week_start, float(item.budget_vat), float(item.target_lead_price), float(item.target_leads), float(item.revenue_plan)])
    for sheet in workbook.worksheets:
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        sheet.column_dimensions["A"].width = 16
        for column in "BCDE":
            sheet.column_dimensions[column].width = 28
        for cell in sheet[1]:
            cell.font = cell.font.copy(bold=True, color="FFFFFF")
            cell.fill = cell.fill.copy(fill_type="solid", fgColor="536B50")
        for row in sheet.iter_rows(min_row=2):
            row[0].number_format = "DD.MM.YYYY"
            for cell in row[1:]:
                cell.number_format = '#,##0.00'
    stream = BytesIO()
    workbook.save(stream)
    stream.seek(0)
    return stream
