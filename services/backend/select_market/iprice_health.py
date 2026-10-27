"""Read-only coverage of the latest price file and saved calculation issues."""
from collections import Counter

from django.db.models import Exists, OuterRef, Q

from .iprice_models import IPricePriceImport, NomenclaturePrice, IPriceRegionalInput
from .iprice_domain_models import IPriceSnapshot, IPriceSnapshotRegion, ParserProductUrl, ParserProductClassification


def missing_analog_prices(price_rows, calculation_date):
    from collections import defaultdict
    from types import SimpleNamespace
    from .iprice_domain_models import ParserProductMatch, IPriceCompetitorSelectionOverride
    from .iprice_regional_calculation import competitor_matches_region
    from datasets.services.iprice_workspace import IPriceWorkspace
    from datasets.services.iprice_market_assortment import build_market_group_key_map
    from datasets.services.iprice_source_selector import get_competitor_price_data, get_competitor_regions
    workspace = IPriceWorkspace('select-market')
    classified = set(ParserProductClassification.objects.filter(status='active').values_list('product_key', flat=True))
    own = dict(ParserProductUrl.objects.filter(source='base', own_code__in=[row['code'] for row in price_rows]).values_list('own_code', 'pk'))
    excluded = set(IPriceCompetitorSelectionOverride.objects.filter(selection_mode='exclude').values_list('product_key_base', 'product_key_competitor'))
    pairs = [(base, competitor) for base, competitor in ParserProductMatch.objects.filter(
        status='active', product_key_base__in=own.values(), product_key_competitor__in=classified).values_list('product_key_base', 'product_key_competitor')
        if (base, competitor) not in excluded]
    keys = {competitor for _, competitor in pairs}
    urls = {row.pk: row for row in ParserProductUrl.objects.filter(pk__in=keys, status='active').exclude(source='base')}
    groups = build_market_group_key_map(competitor_product_keys=set(urls), workspace=workspace)
    analogs = defaultdict(lambda: defaultdict(list))
    for base, competitor in pairs:
        if competitor in urls:
            analogs[base][groups.get(competitor, (urls[competitor].source, competitor))].append(competitor)
    price_data, regions = {}, {}
    for key, url in urls.items():
        price_data[key] = get_competitor_price_data(product_key=key, calculation_date=calculation_date, workspace=workspace)
        info = get_competitor_regions(source=url.source, prefix=url.prefix, workspace=workspace)
        regions[key] = SimpleNamespace(is_all_regions=info['is_all_regions'], applicable_regions=info['regions'])
    labels = {'tara': 'Тара', 'tt': 'Топаз', 'ps': 'Пластик Систем'}
    entries = []
    for row in price_rows:
        for group_keys in analogs.get(own.get(row['code']), {}).values():
            if any(competitor_matches_region(regions[key], row['shipp_region']) and price_data[key]
                   and price_data[key]['calculation_price'] is not None and price_data[key]['calculation_price'] > 0 for key in group_keys):
                continue
            key = group_keys[0]
            entries.append({'id': f"source-competitor-price-{row['pk']}-{key}", 'severity': 'warning',
                'section': 'sources', 'code': 'competitor_price', 'code_1c': row['code'], 'nom': row['nom'], 'region': row['shipp_region'],
                'message': f"Нет цены актуального аналога в регионе: {labels.get(urls[key].source, urls[key].source)} · ключи {', '.join(map(str, group_keys))}",
                'fix': 'Проверьте загрузку положительных цен, регионы конкурента и актуальность связи с аналогом.'})
    return entries


def health_report(*, page=1, search='', level='', section='', code='', page_size=50):
    latest = IPricePriceImport.objects.order_by('-date').first()
    source_checks = []
    entries = []
    if latest:
        inputs = IPriceRegionalInput.objects.filter(month=latest.date.replace(day=1),
            code=OuterRef('code'), region__iexact=OuterRef('shipp_region'))
        classified_products = ParserProductUrl.objects.filter(source='base', own_code=OuterRef('code'),
            pk__in=ParserProductClassification.objects.filter(status='active').values('product_key'))
        valid_parameters = inputs.filter(base_analog__gte=0)
        for field in ('base_exclusive', 'minimum_margin', 'small', 'medium', 'large'):
            valid_parameters = valid_parameters.filter(**{field + '__gte': 0, field + '__lt': 1})
        prices = NomenclaturePrice.objects.filter(batch=latest).annotate(
            has_classification=Exists(classified_products),
            has_parameters=Exists(valid_parameters),
            has_purchase=Exists(inputs.filter(purchase_cost__gt=0)),
            invalid_delivery=Exists(inputs.filter(include_transport=True).filter(Q(logistics_unit__isnull=True) | Q(logistics_unit__lt=0))))
        source_checks = [
            {'key': 'purchase', 'label': 'Нет положительной закупочной цены за месяц прайса', 'count': prices.filter(has_purchase=False).count()},
            {'key': 'delivery', 'label': 'Доставка включена, но её стоимость не заполнена или отрицательна', 'count': prices.filter(invalid_delivery=True).count()},
            {'key': 'retail', 'label': 'Не заполнена положительная розничная цена', 'count': prices.filter(Q(retail__isnull=True) | Q(retail__lte=0)).count()},
            {'key': 'classification', 'label': 'Товар не классифицирован', 'count': prices.filter(has_classification=False).count()},
            {'key': 'parameters', 'label': 'Не заполнены или некорректны параметры расчёта', 'count': prices.filter(has_parameters=False).count()},
        ]
        for key, condition, fix in [
            ('purchase', Q(has_purchase=False), 'Загрузите закупочную цену без НДС для этого кода, региона и месяца.'),
            ('delivery', Q(invalid_delivery=True), 'Введите расходы на единицу или выключите учёт доставки.'),
            ('retail', Q(retail__isnull=True) | Q(retail__lte=0), 'Исправьте розничную цену в полном Excel-прайсе.'),
            ('classification', Q(has_classification=False), 'Загрузите действующую классификацию для товара с этим кодом 1С.'),
            ('parameters', Q(has_parameters=False), 'Заполните коэффициент по рынку, маржу по себестоимости, минимальную маржу и три оптовые скидки для этого кода 1С, региона и месяца прайса.'),
        ]:
            label = next(item['label'] for item in source_checks if item['key'] == key)
            for item in prices.filter(condition).values('pk', 'code', 'nom', 'shipp_region').iterator(chunk_size=1000):
                entries.append({'id': f"source-{key}-{item['pk']}", 'severity': 'warning' if key == 'classification' else 'error', 'section': 'sources', 'code': key,
                                'message': label, 'code_1c': item['code'], 'nom': item['nom'], 'region': item['shipp_region'], 'fix': fix})
        competitor_issues = missing_analog_prices(list(prices.values('pk', 'code', 'nom', 'shipp_region')), latest.date)
        source_checks.append({'key': 'competitor_price', 'label': 'Нет цены актуального аналога в регионе', 'count': len(competitor_issues)})
        entries.extend(competitor_issues)
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
