"""Select Market columns; shared Excel formatting and effective price selection."""
from .iprice_prices import price_with_vat


def append_prices(*, workbook, regions):
    from datasets.services.iprice_snapshot_export import get_effective_prices, apply_header_style, apply_worksheet_dimensions
    labels = (('rrp', 'Розница'), ('small', 'Мелкий опт'), ('medium', 'Средний опт'), ('large', 'Крупный опт'))
    sheet = workbook.create_sheet('Цены')
    sheet.append(['Код 1С', 'Номенклатура', 'Группа 1', 'Группа 2', 'Группа 3',
                  'Тип', 'Категория', 'Подкатегория', 'Цвет', 'Материал', 'Модификация',
                  'Регион', 'Закупочная цена без НДС', 'Учитывать транспортные расходы',
                  'Доставка на единицу без НДС', 'Стоимость с доставкой без НДС',
                  *[f'{title}, руб. {tax}' for _, title in labels for tax in ('без НДС', 'с НДС')],
                  'Статус', 'Предупреждения', 'Ошибки'])
    errors = workbook.create_sheet('Ошибки')
    errors.append(['Код 1С', 'Регион', 'Предупреждения', 'Ошибки'])
    for row in regions:
        product = row.snapshot_product
        effective = get_effective_prices(row)
        values = []
        for key, _ in labels:
            net = effective[key]
            values.extend([net, price_with_vat(net) if net is not None else None])
        warnings = ', '.join(dict.fromkeys([*product.warning_codes, *row.warning_codes]))
        issues = ', '.join(dict.fromkeys([*product.error_codes, *row.error_codes]))
        sheet.append([product.code_1c, product.nom,
                      *[getattr(product, f'group_{level}') or '—' for level in range(2, 5)],
                      *[getattr(product, field) for field in ('category', 'subcategory', 'subcategory_type', 'color', 'material', 'modification')],
                      row.sale_region, row.product_cost, 'Да' if row.calculation_details.get('include_transport') else 'Нет',
                      row.logistics_unit, row.cost_with_logistics, *values, row.calculation_status, warnings, issues])
        if warnings or issues:
            errors.append([product.code_1c, row.sale_region, warnings, issues])
    for target in (sheet, errors):
        apply_header_style(target)
        apply_worksheet_dimensions(target)
    from openpyxl.styles import Alignment
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            if cell.data_type == 'n':
                cell.alignment = Alignment(horizontal='right')
                cell.number_format = '#,##0' if 17 <= cell.column <= 24 else '#,##0.00'
