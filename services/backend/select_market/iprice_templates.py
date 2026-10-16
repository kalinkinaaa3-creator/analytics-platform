"""User-facing workbooks for the five supported Select Market imports."""
from io import BytesIO

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from datasets.services.iprice_upload_template_export import UPLOAD_TEMPLATE_HEADERS
from .iprice_prices import COLUMNS
from .iprice_purchase_import import HEADERS as PURCHASE_HEADERS
from .iprice_regional_import import HEADERS as PARAMETER_HEADERS


def export_template(kind):
    headers = {'price': COLUMNS, 'product_cost': PURCHASE_HEADERS,
               'calculation_config': PARAMETER_HEADERS}.get(kind)
    if headers is None:
        if kind not in ('parser_prefixes', 'product_classification'):
            raise ValueError('Неизвестный тип источника.')
        headers = UPLOAD_TEMPLATE_HEADERS[kind]
    book = Workbook()
    sheet = book.active
    sheet.title = 'Шаблон загрузки'
    sheet.append(headers)
    sheet.freeze_panes = 'A2'
    sheet.auto_filter.ref = f'A1:{get_column_letter(len(headers))}1'
    hints = {
        'Код': 'Текстовый код 1С, например 001-А. Не удаляйте ведущие нули. Дата полного прайса выбирается в форме загрузки. Файл заменяет весь прайс за эту дату во всех регионах.',
        'Регион': 'Регион продажи. Для одного кода в одном регионе допускается одна строка.',
        'Номенклатура': 'Наименование товара. Наименование и группы одного кода должны совпадать во всех регионах.',
        'date': 'Месяц расчёта: дата Excel или текст ГГГГ-ММ-ДД, например 2026-10-01. Используется месяц указанной даты.',
        'code': 'Текстовый код 1С из прайса. Сохраняйте ведущие нули и буквы.',
        'region': 'Регион точно как в прайсе. Параметры и закупочная цена задаются отдельно для каждой пары код + регион.',
        'name': 'Справочное наименование. Название товара в расчёте берётся из полного прайса.',
        'cost': 'Закупочная цена БЕЗ НДС, до 4 знаков после запятой. Полный файл за один месяц: у отсутствующих пар закупочная цена за этот месяц очищается. Доставка и коэффициенты сохраняются.',
        'base_analog': 'Неотрицательный коэффициент к цене аналога, например 1. До 6 знаков после запятой.',
        'base_exclusive': 'Маржа эксклюзива долей: 0,3 = 30%. От 0 включительно до 1 не включительно.',
        'minimum_margin': 'Минимальная маржа долей: 0,1 = 10%. От 0 включительно до 1 не включительно.',
        'include_transport': '1 — учитывать доставку; 0 или пустая ячейка — не учитывать. Весь набор параметров строки заменяется, пустая ячейка не означает «оставить прежнее».',
        'logistics_unit': 'Доставка БЕЗ НДС на единицу, до 2 знаков после запятой. Обязательна, если include_transport = 1; иначе можно оставить пустой.',
        'source': 'Источник: tara, ps, tt или base (нижний регистр). Файл полностью заменяет список региональных префиксов.',
        'prefix': 'Текстовый префикс сайта, например spb. Для сайта без префикса — «-».',
        'shipp_region': 'Регион продажи для указанного источника и префикса.',
        'product_key': 'Целый ID записи URL из парсера Селект Маркета, НЕ код 1С и НЕ ID Ай-Пласта. URL должен быть активным. Файл содержит полную классификацию; ручные связи и исключения сохраняются.',
        'article_number_analogs': 'Обязательный текстовый идентификатор группы аналогов; одинаковый для сопоставляемых позиций. Ведущие нули сохраняются.',
        'item_type': 'Обязательно: product — товар, component — комплектующая.',
        'color': 'Цвет; «-» означает любой цвет при сопоставлении аналогов.',
    }
    texts = {'Код', 'Регион', 'Номенклатура', 'Группа', 'code', 'name', 'region',
             'source', 'prefix', 'shipp_region', 'category', 'subcategory', 'subcategory_type',
             'color', 'material', 'modification', 'article_number_analogs', 'item_type'}
    for index, header in enumerate(headers, 1):
        cell = sheet.cell(1, index)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(wrap_text=True, vertical='top')
        hint = hints.get(header, 'Текстовое значение классификации. Формулы не допускаются; вставляйте значения.')
        if kind == 'price' and index >= 8:
            hint = 'Исходная цена С НДС 22%. Без НДС: цена / 1,22 с математическим округлением до целого. Исходная сумма сохраняется отдельно. До 4 знаков после запятой; пустая цена допускается.'
        if header == 'Группа':
            hint = 'Группы заполняются от младшей слева к старшей справа. Пустые уровни пропускаются. Например: [подгруппа, группа, Торговый ассортимент, пусто] → группа 1 «Торговый ассортимент». Не вставляйте прочерк вместо пустого уровня.'
        if kind == 'calculation_config' and header in ('small', 'medium', 'large'):
            hint = 'Обязательная скидка долей: 0,15 = 15%. От 0 включительно до 1 не включительно; до 6 знаков после запятой. Все коэффициенты и скидки строки должны быть заполнены.'
        cell.comment = Comment(hint, 'Селект Маркет')
        column = sheet.column_dimensions[get_column_letter(index)]
        column.width = max(18, min(34, len(header) + 4))
        number_format = '@' if header in texts else 'yyyy-mm-dd' if header == 'date' else '0' if header in ('product_key', 'include_transport') else '0.00' if header == 'logistics_unit' else '0.######'
        column.number_format = number_format
        for row in sheet.iter_rows(min_row=2, max_row=1001, min_col=index, max_col=index):
            row[0].number_format = number_format
    sheet.row_dimensions[1].height = 32
    output = BytesIO()
    book.save(output)
    book.close()
    output.seek(0)
    return output
