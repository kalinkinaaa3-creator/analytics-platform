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
from .iprice_classification_columns import HEADERS as CLASSIFICATION_HEADERS, FILE_TO_MODEL


def export_template(kind):
    headers = {'price': COLUMNS, 'product_cost': PURCHASE_HEADERS,
               'calculation_config': PARAMETER_HEADERS}.get(kind)
    if headers is None:
        if kind not in ('parser_prefixes', 'product_classification'):
            raise ValueError('Неизвестный тип источника.')
        headers = UPLOAD_TEMPLATE_HEADERS[kind]
    if kind == 'product_classification':
        headers = (*CLASSIFICATION_HEADERS, 'code_1c', 'name', 'on_website')
    book = Workbook()
    sheet = book.active
    sheet.title = 'Шаблон загрузки'
    sheet.append(headers)
    sheet.freeze_panes = 'A2'
    sheet.auto_filter.ref = f'A1:{get_column_letter(len(headers))}1'
    hints = {
        'Статус ассортиментной матрицы': 'САМ товара. Текст целиком, одинаковый для одного кода во всех регионах. Пустое значение очищает САМ в новом прайсе.',
        'Код': 'Текстовый код 1С, например 001-А. Не удаляйте ведущие нули. Дата полного прайса выбирается в форме загрузки. Файл заменяет весь прайс за эту дату во всех регионах.',
        'Регион': 'Регион продажи. Для одного кода в одном регионе допускается одна строка.',
        'Номенклатура': 'Наименование товара. Наименование и группы одного кода должны совпадать во всех регионах.',
        'date': 'Месяц расчёта: дата Excel или текст ГГГГ-ММ-ДД, например 2026-10-01. Используется месяц указанной даты.',
        'code': 'Текстовый код 1С из прайса. Сохраняйте ведущие нули и буквы.',
        'region': 'Регион точно как в прайсе. Параметры и закупочная цена задаются отдельно для каждой пары код + регион.',
        'name': 'Справочное наименование. Название товара в расчёте берётся из полного прайса.',
        'cost': 'Закупочная цена БЕЗ НДС, до 4 знаков после запятой. Полный файл за один месяц: у отсутствующих пар закупочная цена за этот месяц очищается. Доставка и коэффициенты сохраняются.',
        'base_analog': 'Неотрицательный коэффициент к цене аналога, например 1. До 6 знаков после запятой.',
        'base_exclusive': 'Маржа по себестоимости долей: 0,3 = 30%. От 0 включительно до 1 не включительно.',
        'minimum_margin': 'Минимальная маржа долей: 0,1 = 10%. От 0 включительно до 1 не включительно.',
        'include_transport': '1 — учитывать доставку; 0 или пустая ячейка — не учитывать. Весь набор параметров строки заменяется, пустая ячейка не означает «оставить прежнее».',
        'logistics_unit': 'Доставка БЕЗ НДС на единицу, до 2 знаков после запятой. Обязательна, если include_transport = 1; иначе можно оставить пустой.',
        'source': 'Источник: tara, ps, tt или base (нижний регистр). Файл полностью заменяет список региональных префиксов.',
        'prefix': 'Текстовый префикс сайта, например spb. Для сайта без префикса — «-».',
        'shipp_region': 'Регион продажи для указанного источника и префикса.',
        'product_key': 'Постоянный ID товара (URL может отсутствовать). Целый ID записи из парсера Селект Маркета, НЕ код 1С и НЕ ID Ай-Пласта. Запись товара должна быть активной; наличие страницы сайта не требуется. Файл содержит полную классификацию; ручные связи и исключения сохраняются.',
        'code_1c': 'Справочный текстовый код 1С. Связь классификации задаётся по product_key.',
        'on_website': 'Справочно: есть ли товар в последней принятой выгрузке сайта. Это поле не меняет наличие товара.',
        'article_number_analogs': 'Обязательный текстовый идентификатор группы аналогов; одинаковый для сопоставляемых позиций. Ведущие нули сохраняются.',
        'item_type': 'Обязательно: product — товар, component — комплектующая.',
        'type': 'Тип товара в классификации iPrice (ранее столбец category).',
        'category': 'Категория в классификации iPrice (ранее столбец subcategory).',
        'subcategory': 'Подкатегория в классификации iPrice (ранее столбец subcategory_type).',
        'color': 'Цвет; «-» означает любой цвет при сопоставлении аналогов.',
    }
    texts = {'Статус ассортиментной матрицы', 'Код', 'Регион', 'Номенклатура', 'Группа', 'code', 'code_1c', 'on_website', 'name', 'region',
             'source', 'prefix', 'shipp_region', 'type', 'category', 'subcategory', 'subcategory_type',
             'color', 'material', 'modification', 'article_number_analogs', 'item_type'}
    for index, header in enumerate(headers, 1):
        cell = sheet.cell(1, index)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(wrap_text=True, vertical='top')
        hint = hints.get(header, 'Текстовое значение классификации. Формулы не допускаются; вставляйте значения.')
        if kind == 'price' and index >= 9:
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
    if kind == 'product_classification':
        from .iprice_domain_models import (ParserProductUrl, ParserProductClassification,
                                           BaseProductPrice, TtProductPrice, PsProductPrice, TaraProductPrice)
        from .iprice_models import IPricePriceImport, NomenclaturePrice
        batch = IPricePriceImport.objects.order_by('-date').first()
        names = dict(NomenclaturePrice.objects.filter(batch=batch).values_list('code', 'nom')) if batch else {}
        classes = {row.product_key: row for row in ParserProductClassification.objects.filter(status='active')}
        urls = list(ParserProductUrl.objects.filter(status='active').order_by('pk'))
        source_names = {}
        for source, model in [('base', BaseProductPrice), ('tt', TtProductPrice), ('ps', PsProductPrice), ('tara', TaraProductPrice)]:
            keys = [url.pk for url in urls if url.source == source and (source == 'base' or url.pk in classes)]
            for key, name in model.objects.filter(product_key__in=keys).order_by('-date_add', '-pk').values_list('product_key', 'name').iterator():
                source_names.setdefault(key, name)
        row_number = 2
        for url in urls:
            classification = classes.get(url.pk)
            if url.source != 'base' and classification is None:
                continue
            values = [url.pk] + [getattr(classification, FILE_TO_MODEL.get(key, key), None) if classification else ('product' if key == 'item_type' else None) for key in headers[1:-3]]
            name = names.get(url.own_code) if url.source == 'base' and url.own_code in names else source_names.get(url.pk)
            values += [url.own_code, name, ('Да' if url.on_website else 'Нет') if url.source == 'base' else None]
            for column, value in enumerate(values, 1):
                cell = sheet.cell(row_number, column, value)
                if isinstance(value, str):
                    cell.data_type = 's'
                    cell.number_format = '@'
            row_number += 1
        sheet.auto_filter.ref = f'A1:{get_column_letter(len(headers))}{max(1, row_number - 1)}'
    output = BytesIO()
    book.save(output)
    book.close()
    output.seek(0)
    return output
