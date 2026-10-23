"""Read-only coverage of the latest price file and saved calculation issues."""
from collections import Counter

from django.db.models import Exists, OuterRef, Q

from .iprice_models import IPricePriceImport, NomenclaturePrice, IPriceRegionalInput
from .iprice_domain_models import IPriceSnapshot, IPriceSnapshotRegion


def health_report(*, page=1, search='', level='', section='', code='', page_size=50):
    latest = IPricePriceImport.objects.order_by('-date').first()
    source_checks = []
    entries = []
    if latest:
        inputs = IPriceRegionalInput.objects.filter(month=latest.date.replace(day=1),
            code=OuterRef('code'), region__iexact=OuterRef('shipp_region'))
        prices = NomenclaturePrice.objects.filter(batch=latest).annotate(
            has_purchase=Exists(inputs.filter(purchase_cost__gt=0)),
            invalid_delivery=Exists(inputs.filter(include_transport=True).filter(Q(logistics_unit__isnull=True) | Q(logistics_unit__lt=0))))
        source_checks = [
            {'key': 'purchase', 'label': 'Нет положительной закупочной цены за месяц прайса', 'count': prices.filter(has_purchase=False).count()},
            {'key': 'delivery', 'label': 'Доставка включена, но её стоимость не заполнена или отрицательна', 'count': prices.filter(invalid_delivery=True).count()},
            {'key': 'retail', 'label': 'Не заполнена положительная розничная цена', 'count': prices.filter(Q(retail__isnull=True) | Q(retail__lte=0)).count()},
        ]
        for key, condition, fix in [
            ('purchase', Q(has_purchase=False), 'Загрузите закупочную цену без НДС для этого кода, региона и месяца.'),
            ('delivery', Q(invalid_delivery=True), 'Введите расходы на единицу или выключите учёт доставки.'),
            ('retail', Q(retail__isnull=True) | Q(retail__lte=0), 'Исправьте розничную цену в полном Excel-прайсе.'),
        ]:
            label = next(item['label'] for item in source_checks if item['key'] == key)
            for item in prices.filter(condition).values('pk', 'code', 'nom', 'shipp_region').iterator(chunk_size=1000):
                entries.append({'id': f"source-{key}-{item['pk']}", 'severity': 'error', 'section': 'sources', 'code': key,
                                'message': label, 'code_1c': item['code'], 'nom': item['nom'], 'region': item['shipp_region'], 'fix': fix})
    snapshot = IPriceSnapshot.objects.filter(status='success').order_by('-version_number', '-id').first()
    errors, warnings = Counter(), Counter()
    if snapshot:
        for row in IPriceSnapshotRegion.objects.filter(snapshot_product__snapshot=snapshot).values('pk', 'error_codes', 'warning_codes', 'sale_region', 'snapshot_product__code_1c', 'snapshot_product__nom').iterator(chunk_size=1000):
            error_codes, warning_codes = row['error_codes'], row['warning_codes']
            errors.update(set(error_codes or []))
            warnings.update(set(warning_codes or []))
            for severity, codes in [('error', error_codes), ('warning', warning_codes)]:
                for issue in sorted(set(codes or [])):
                    entries.append({'id': f"snapshot-{row['pk']}-{severity}-{issue}", 'severity': severity, 'section': 'snapshot', 'code': issue,
                        'message': '', 'code_1c': row['snapshot_product__code_1c'], 'nom': row['snapshot_product__nom'], 'region': row['sale_region'],
                        'fix': 'Проверьте исходные данные и параметры товара. После исправления выполните новый расчёт.'})
    summary = {'errors': sum(item['severity'] == 'error' for item in entries), 'warnings': sum(item['severity'] == 'warning' for item in entries)}
    options = sorted(set(item['code'] for item in entries))
    query = search.casefold().strip()
    selected = [item for item in entries if (not level or item['severity'] == level) and (not section or item['section'] in section.split(','))
                and (not code or item['code'] in code.split(',')) and (not query or query in ' '.join(str(v or '') for v in item.values()).casefold())]
    from django.core.paginator import Paginator
    pagination = Paginator(selected, page_size or max(1, len(selected)))
    current = pagination.get_page(page)
    return {
        'price_date': latest.date if latest else None,
        'source_checks': source_checks,
        'summary': summary, 'filter_codes': options, 'results': list(current), 'count': pagination.count, 'page': current.number, 'pages': pagination.num_pages,
        'snapshot': {'id': snapshot.pk, 'date': snapshot.calculation_date, 'version': snapshot.version_number} if snapshot else None,
        'issues': [{'code': code, 'count': count, 'severity': severity} for severity, counts in [('error', errors), ('warning', warnings)] for code, count in sorted(counts.items())],
    }
