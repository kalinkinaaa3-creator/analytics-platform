"""Manual monthly purchase prices, scoped by text code and sale region."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from openpyxl import load_workbook
from .iprice_models import IPriceRegionalInput

HEADERS = ('date', 'code', 'name', 'region', 'cost')


def parse_purchase(file_obj):
    book = load_workbook(file_obj, read_only=True, data_only=False)
    result, keys, months = [], set(), set()
    try:
        if len(book.worksheets) != 1:
            raise ValueError('В файле должен быть один лист.')
        rows = book.active.iter_rows(values_only=True)
        if tuple(next(rows, ())) != HEADERS:
            raise ValueError('Ожидаются столбцы: ' + ', '.join(HEADERS))
        for number, values in enumerate(rows, 2):
            if number > 100001:
                raise ValueError('Допускается не более 100 000 строк.')
            if all(value in (None, '') for value in values):
                continue
            try:
                raw_date, code, name, region, raw_cost = values
                if any(isinstance(value, str) and value.startswith('=') for value in values):
                    raise ValueError('формулы не допускаются')
                day = raw_date.date() if isinstance(raw_date, datetime) else raw_date if isinstance(raw_date, date) else date.fromisoformat(str(raw_date))
                month = day.replace(day=1)
                if not isinstance(code, str) or not code.strip() or len(code.strip()) > 160:
                    raise ValueError('код должен быть текстом длиной до 160 символов')
                if not isinstance(region, str) or not region.strip() or len(region.strip()) > 255:
                    raise ValueError('укажите регион')
                cost = Decimal(str(raw_cost).replace(' ', '').replace('\xa0', '').replace(',', '.'))
                if not cost.is_finite() or cost < 0 or cost >= Decimal('1e14') or cost != cost.quantize(Decimal('.0001')):
                    raise ValueError('некорректная закупочная цена без НДС')
                key = (code.strip(), region.strip().casefold())
                if key in keys:
                    raise ValueError('повтор товара и региона')
                keys.add(key)
                months.add(month)
                result.append(dict(month=month, code=code.strip(), region=region.strip(), purchase_cost=cost))
            except (ValueError, TypeError, InvalidOperation) as exc:
                raise ValueError(f'Строка {number}: {exc}') from exc
        if not result or len(months) != 1:
            raise ValueError('Загрузите полный файл закупочных цен за один месяц.')
        return result
    finally:
        book.close()


def load_purchase(file_obj, *, workspace):
    if workspace.code != 'select-market':
        raise ValueError('Источник доступен только Селект Маркету')
    rows = parse_purchase(file_obj)
    # The upload service owns the organization lock and audit transaction.
    # Keep user parameters when replacing the complete monthly purchase list.
    IPriceRegionalInput.objects.filter(month=rows[0]['month']).update(purchase_cost=None)
    existing = {(row.code, row.region.casefold()): row for row in
                IPriceRegionalInput.objects.filter(month=rows[0]['month'])}
    for row in rows:
        previous = existing.get((row['code'], row['region'].casefold()))
        if previous:
            previous.purchase_cost = row['purchase_cost']
            previous.save(update_fields=['purchase_cost', 'updated_at'])
        else:
            IPriceRegionalInput.objects.create(**row)
    return {'rows': len(rows), 'month': rows[0]['month'].isoformat()}
