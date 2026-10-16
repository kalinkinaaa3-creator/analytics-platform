"""Parameters for text SKU + region + month; no website/plant prerequisite."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from openpyxl import load_workbook
from .iprice_models import IPriceRegionalInput

HEADERS = ('date', 'code', 'region', 'base_analog', 'base_exclusive', 'minimum_margin',
           'small', 'medium', 'large', 'include_transport', 'logistics_unit')


def parse_parameters(file_obj):
    book = load_workbook(file_obj, read_only=True, data_only=False)
    result, keys = [], set()
    try:
        if len(book.worksheets) != 1:
            raise ValueError('В файле должен быть один лист.')
        rows = book.active.iter_rows(values_only=True)
        if tuple(next(rows, ())) != HEADERS:
            raise ValueError('Ожидаются столбцы: ' + ', '.join(HEADERS))
        for index, values in enumerate(rows, 2):
            if index > 100001:
                raise ValueError('Допускается не более 100 000 строк.')
            if all(value in (None, '') for value in values):
                continue
            try:
                if any(isinstance(value, str) and value.startswith('=') for value in values):
                    raise ValueError('формулы не допускаются')
                row = dict(zip(HEADERS, values))
                day = row.pop('date')
                day = day.date() if isinstance(day, datetime) else day if isinstance(day, date) else date.fromisoformat(str(day))
                row['month'] = day.replace(day=1)
                for field, limit in (('code', 160), ('region', 255)):
                    value = row[field]
                    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
                        raise ValueError(f'некорректное поле {field}')
                    row[field] = value.strip()
                raw = row['include_transport']
                if raw in (None, '', False, 0, '0', 'Нет', 'нет'):
                    row['include_transport'] = False
                elif raw in (True, 1, '1', 'Да', 'да'):
                    row['include_transport'] = True
                else:
                    raise ValueError('include_transport: укажите 1 или 0')
                for field in ('base_analog', 'base_exclusive', 'minimum_margin', 'small', 'medium', 'large', 'logistics_unit'):
                    value = row[field]
                    if field == 'logistics_unit' and value in (None, '') and not row['include_transport']:
                        row[field] = None
                        continue
                    value = Decimal(str(value).replace(' ', '').replace('\xa0', '').replace(',', '.'))
                    if not value.is_finite() or value < 0 or (field not in ('base_analog', 'logistics_unit') and value >= 1):
                        raise ValueError(f'некорректное значение {field}')
                    IPriceRegionalInput._meta.get_field(field).clean(value, None)
                    row[field] = value
                key = (row['month'], row['code'], row['region'].casefold())
                if key in keys:
                    raise ValueError('повтор кода и региона за месяц')
                keys.add(key)
                result.append(row)
            except (ValueError, TypeError, InvalidOperation) as exc:
                raise ValueError(f'Строка {index}: {exc}') from exc
            except Exception as exc:
                from django.core.exceptions import ValidationError
                if isinstance(exc, ValidationError):
                    raise ValueError(f'Строка {index}: {"; ".join(exc.messages)}') from exc
                raise
        if not result:
            raise ValueError('Файл параметров пуст.')
        return result
    finally:
        book.close()


def load_parameters(file_obj, *, workspace):
    if workspace.code != 'select-market':
        raise ValueError('Источник доступен только Селект Маркету')
    rows = parse_parameters(file_obj)
    for row in rows:
        previous = IPriceRegionalInput.objects.filter(month=row['month'], code=row['code'], region__iexact=row['region']).first()
        if previous:
            for field, value in row.items():
                setattr(previous, field, value)
            previous.save()
        else:
            IPriceRegionalInput.objects.create(**row)
    return {'rows': len(rows)}
