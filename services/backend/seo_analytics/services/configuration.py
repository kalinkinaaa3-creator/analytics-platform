from io import BytesIO

from django.db import transaction
from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Font, PatternFill

from seo_analytics.models import SeoBrandMask, SeoGoal


HEADER_FILL = PatternFill("solid", fgColor="DDE4D8")
CONFIG_GOALS = "goals"
CONFIG_BRANDS = "brand-masks"


def _excel_safe(value):
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def _style_sheet(sheet, widths):
    for cell in sheet[1]:
        cell.font = Font(bold=True)
        cell.fill = HEADER_FILL
    for column, width in widths.items():
        sheet.column_dimensions[column].width = width
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions


def build_configuration_workbook(kind):
    if kind not in {CONFIG_GOALS, CONFIG_BRANDS}:
        raise ValueError("Неизвестный тип настроек SEO.")
    workbook = Workbook()
    upload = workbook.active
    upload.title = "Загрузка"
    actual = workbook.create_sheet("Актуальные")

    if kind == CONFIG_GOALS:
        headers = ["goal_id", "Наименование для отражения"]
        upload.append(headers)
        actual.append(headers)
        for goal in SeoGoal.objects.filter(is_active=True, is_available=True).order_by("position", "id"):
            actual.append([goal.external_id, _excel_safe(goal.name)])
        widths = {"A": 18, "B": 42}
    else:
        headers = ["Брендовая маска"]
        upload.append(headers)
        actual.append(headers)
        explanation = (
            "Укажите фрагменты, по которым поисковая фраза считается брендовой. "
            "Регистр букв не учитывается; достаточно совпадения с одной маской. "
            "Фразы без совпадений относятся к небрендовым, пустые — к «Не определено». "
            "При загрузке список масок полностью заменяется содержимым листа «Загрузка»."
        )
        upload["A1"].comment = Comment(explanation, "SEO-аналитика")
        actual["A1"].comment = Comment(explanation, "SEO-аналитика")
        for mask in SeoBrandMask.objects.filter(is_active=True).order_by("mask"):
            actual.append([_excel_safe(mask.mask)])
        widths = {"A": 46}
    _style_sheet(upload, widths)
    _style_sheet(actual, widths)

    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return output


def _read_goals(sheet):
    try:
        header = [str(value or "").strip() for value in next(sheet.iter_rows(values_only=True))]
    except StopIteration:
        raise ValueError("Лист «Загрузка» пуст.")
    expected = ["goal_id", "Наименование для отражения"]
    if header[:2] != expected:
        raise ValueError(f"Первая строка листа «Загрузка» должна быть: {', '.join(expected)}.")
    values, seen = [], set()
    for row_number, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), 2):
        if not any(value not in (None, "") for value in row[:2]):
            continue
        try:
            external_id = int(row[0])
        except (TypeError, ValueError):
            raise ValueError(f"Строка {row_number}: goal_id должен быть целым числом.")
        name = str(row[1] or "").strip()
        if external_id <= 0 or not name or len(name) > 255:
            raise ValueError(f"Строка {row_number}: проверьте goal_id и наименование.")
        if external_id in seen:
            raise ValueError(f"Строка {row_number}: goal_id {external_id} повторяется.")
        seen.add(external_id)
        values.append((external_id, name))
    if not values:
        raise ValueError("Лист «Загрузка» не содержит целей.")
    return values, seen


def _read_masks(sheet):
    try:
        header = [str(value or "").strip() for value in next(sheet.iter_rows(values_only=True))]
    except StopIteration:
        raise ValueError("Лист «Загрузка» пуст.")
    if header[:1] not in (["Брендовая маска"], ["Маска"]):
        raise ValueError("Первая строка листа «Загрузка» должна быть: Брендовая маска.")
    values, seen = [], set()
    for row_number, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), 2):
        mask = str((row or [None])[0] or "").strip()
        if not mask:
            continue
        normalized = mask.lower().replace("ё", "е")
        if len(mask) > 255:
            raise ValueError(f"Строка {row_number}: маска длиннее 255 символов.")
        if normalized in seen:
            raise ValueError(f"Строка {row_number}: брендовая маска повторяется.")
        seen.add(normalized)
        values.append(mask)
    if not values:
        raise ValueError("Лист «Загрузка» не содержит брендовых масок.")
    return values


def load_configuration(file_obj, kind):
    if kind not in {CONFIG_GOALS, CONFIG_BRANDS}:
        raise ValueError("Неизвестный тип настроек SEO.")
    workbook = load_workbook(file_obj, read_only=True, data_only=True)
    try:
        if "Загрузка" not in workbook.sheetnames:
            raise ValueError("В файле отсутствует лист «Загрузка».")
        if kind == CONFIG_GOALS:
            goals, seen = _read_goals(workbook["Загрузка"])
            with transaction.atomic():
                for position, (external_id, name) in enumerate(goals, 1):
                    goal = SeoGoal.objects.filter(external_id=external_id).first()
                    if goal is None or not goal.is_available:
                        raise ValueError(
                            f"Цель goal_id={external_id} не возвращена текущим каталогом Метрики. "
                            "Она могла остаться в служебной истории, но недоступна для новой загрузки. "
                            "Скачайте актуальный шаблон целей после обновления SEO."
                        )
                    goal.name = name
                    goal.is_active = True
                    goal.position = position * 10
                    goal.save(update_fields=("name", "is_active", "position", "date_update"))
                SeoGoal.objects.exclude(external_id__in=seen).update(is_active=False)
            return {"goals": len(goals), "active_goals": len(goals)}

        masks = _read_masks(workbook["Загрузка"])
        with transaction.atomic():
            values = []
            for mask in masks:
                values.append(mask)
                SeoBrandMask.objects.update_or_create(mask=mask, defaults={"is_active": True})
            SeoBrandMask.objects.exclude(mask__in=values).update(is_active=False)
        return {"brand_masks": len(masks), "active_brand_masks": len(masks)}
    finally:
        workbook.close()
