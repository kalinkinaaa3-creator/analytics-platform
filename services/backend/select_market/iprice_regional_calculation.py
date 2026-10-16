"""Select Market purchase economics; shared iPrice arithmetic, no departure."""
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from .iprice_prices import whole_rubles, price_with_vat

INPUT_FIELDS = ('purchase_cost', 'include_transport', 'logistics_unit', 'base_analog',
                'base_exclusive', 'minimum_margin', 'small', 'medium', 'large')


def prices_meet_margin(row, prices):
    """Compare exact money, without rounding the margin threshold down."""
    if row.cost_with_logistics is None or row.minimum_margin is None:
        return False
    return all(price is not None and price > 0
               and price * (1 - row.minimum_margin) >= row.cost_with_logistics
               for price in prices)


def calculate_region(*, inputs, market_prices=()):
    from datasets.services.iprice_snapshot_builder import (
        calculate_minimum_price, calculate_minimum_allowed_rrp,
        decimal_median,
    )
    errors = []
    def number(field, *, fractional=False):
        value = getattr(inputs, field, None)
        try:
            value = Decimal(str(value))
            if not value.is_finite() or value < 0 or (fractional and value >= 1):
                raise ValueError()
            return value
        except (ValueError, InvalidOperation):
            errors.append('INVALID_' + field.upper())
            return None

    purchase = number('purchase_cost')
    enabled = bool(getattr(inputs, 'include_transport', False))
    logistics = number('logistics_unit') if enabled else Decimal(0)
    cost = purchase + logistics if purchase is not None and logistics is not None else None
    margin = number('minimum_margin', fractional=True)
    discounts = {field: number(field, fractional=True) for field in ('small', 'medium', 'large')}
    market = [Decimal(str(value)) for value in market_prices
              if value is not None and Decimal(str(value)).is_finite() and Decimal(str(value)) > 0]
    median = decimal_median(market)
    preliminary = None
    if median is not None:
        coefficient = number('base_analog')
        if coefficient is not None:
            preliminary = median * coefficient
    else:
        coefficient = number('base_exclusive', fractional=True)
        if coefficient is not None and cost is not None:
            preliminary = cost / (Decimal(1) - coefficient)
    floor = calculate_minimum_price(cost_with_logistics=cost, minimum_margin=margin)
    minimum_rrp = None
    if floor is not None and all(value is not None for value in discounts.values()):
        # Protect every actual price tier; Select Market has no distributor tier.
        minimum_rrp = calculate_minimum_allowed_rrp(minimum_price=floor, distr_discount=max(discounts.values()))
    prices = {}
    if not errors and preliminary is not None and minimum_rrp is not None:
        rrp = whole_rubles(max(preliminary, minimum_rrp))
        # The rounded wholesale prices must still satisfy the margin floor.
        floor_integer = floor.to_integral_value(rounding=ROUND_CEILING)
        required_rrp = ((floor_integer - Decimal('.5')) / (1 - max(discounts.values()))).to_integral_value(rounding=ROUND_CEILING)
        rrp = max(rrp, floor_integer, required_rrp)
        prices = {'retail': rrp, **{key: whole_rubles(rrp * (1 - value))
                                  for key, value in discounts.items()}}
        if any(value <= 0 for value in prices.values()):
            errors.append('NON_POSITIVE_PRICE')
            prices = {}
    return {'purchase_cost': purchase, 'include_transport': enabled, 'logistics_unit': logistics,
            'cost_with_logistics': cost, 'market_median': median, 'preliminary_rrp': preliminary,
            'minimum_price': floor, 'prices_net': prices,
            'prices_gross': {key: price_with_vat(value) for key, value in prices.items()},
            'error_codes': errors}


def build_regions(*, snapshot, snapshot_product_ids=None, input_overrides=None):
    """Write a row for every price-list pair, including rows with missing inputs."""
    from django.db import transaction
    from .iprice_models import IPriceRegionalInput
    from .iprice_prices import prices_as_of
    from .iprice_domain_models import IPriceSnapshotRegion, ParserProductProperty
    from datasets.services.iprice_snapshot_builder import (
        competitor_applies_to_region, decimal_min, decimal_max,
        calculate_margin, calculate_deviation, IPriceSnapshotBuildError,
    )
    if snapshot.status != 'building' and input_overrides is None:
        raise IPriceSnapshotBuildError('Regional rows require a building snapshot')
    if IPriceSnapshotRegion.objects.filter(snapshot_product__snapshot=snapshot).exclude(historical_variant='').exists():
        raise IPriceSnapshotBuildError('Историческая версия с маршрутами доступна только для просмотра. Создайте новый расчёт.')
    month = snapshot.calculation_date.replace(day=1)
    products = snapshot.products.all().prefetch_related('competitors')
    if snapshot_product_ids is not None:
        products = products.filter(pk__in=snapshot_product_ids)
    products = {product.code_1c: product for product in products}
    inputs = {(row.code, row.region.casefold()): row for row in IPriceRegionalInput.objects.filter(month=month, code__in=products)}
    truck = {}
    for prop in ParserProductProperty.objects.filter(source='base',
            product_key__in=[product.base_product_key for product in products.values() if product.base_product_key],
            properties='Количество в еврофуре 82 м3, шт.').order_by('-date_add', '-id'):
        if prop.product_key in truck:
            continue
        try:
            value = Decimal(str(prop.value).replace(' ', '').replace(',', '.'))
            truck[prop.product_key] = value if value.is_finite() and 0 < value < Decimal('1e14') else None
        except InvalidOperation:
            truck[prop.product_key] = None
    count = 0
    pending_approvals = set()
    price_rows = prices_as_of(snapshot.calculation_date).filter(code__in=products)
    if snapshot.status != 'building':
        from types import SimpleNamespace
        price_rows = []
        for saved in IPriceSnapshotRegion.objects.filter(snapshot_product__in=products.values()).select_related('snapshot_product'):
            if 'REAPPROVAL_REQUIRED' in saved.warning_codes:
                pending_approvals.add((saved.snapshot_product.code_1c, saved.sale_region.casefold()))
            price_rows.append(SimpleNamespace(pk=saved.nomenclature_price_source_id, date=saved.nomenclature_price_date,
                code=saved.snapshot_product.code_1c, shipp_region=saved.sale_region,
                **{tier: getattr(saved, 'current_' + tier) for tier in ('retail', 'small', 'medium', 'large')},
                **{tier + '_gross': saved.calculation_details.get('original_prices_gross', {}).get(tier)
                   for tier in ('retail', 'small', 'medium', 'large')}))
            frozen = saved.calculation_details.get('regional_input', {})
            inputs[(saved.snapshot_product.code_1c, saved.sale_region.casefold())] = SimpleNamespace(pk=saved.product_cost_source_id, **frozen)
    with transaction.atomic():
        for price in price_rows:
            product = products[price.code]
            source = inputs.get((price.code, price.shipp_region.casefold()))
            if input_overrides is not None:
                source = input_overrides.get((price.code, price.shipp_region.casefold()), source)
            competitors = [row.competitor_final_price_max for row in product.competitors.all()
                           if row.calculation_status == 'success' and competitor_applies_to_region(competitor=row, sale_region=price.shipp_region)
                           and row.competitor_final_price_max is not None and row.competitor_final_price_max > 0]
            result = calculate_region(inputs=source, market_prices=competitors)
            net = result['prices_net']
            warnings = list(product.warning_codes)
            if (price.code, price.shipp_region.casefold()) in pending_approvals:
                warnings.append('REAPPROVAL_REQUIRED')
            values = dict(
                nomenclature_price_source_id=price.pk, nomenclature_price_date=price.date,
                product_cost_month=month, product_cost_source_id=source.pk if source else None,
                product_cost=result['purchase_cost'], logistics_unit=result['logistics_unit'],
                cost_with_logistics=result['cost_with_logistics'], quantity_eurotruck=truck.get(product.base_product_key),
                regional_competitor_count=len(competitors), regional_competitor_rrp_min=decimal_min(competitors),
                regional_competitor_rrp_max=decimal_max(competitors), regional_competitor_rrp_median=result['market_median'],
                preliminary_rrp=whole_rubles(result['preliminary_rrp']) if result['preliminary_rrp'] is not None else None,
                minimum_price=result['minimum_price'].to_integral_value(rounding=ROUND_CEILING) if result['minimum_price'] is not None else None,
                calculated_rrp=net.get('retail'), default_approved_rrp=net.get('retail'),
                warning_codes=warnings, error_codes=result['error_codes'],
                calculation_status='error' if result['error_codes'] else 'warning' if warnings else 'success',
                calculation_details={'regional_input_id': source.pk if source else None,
                    'regional_input': {field: (getattr(source, field, None) if field == 'include_transport'
                                              else str(getattr(source, field)) if getattr(source, field, None) is not None else None)
                                       for field in INPUT_FIELDS},
                    'include_transport': result['include_transport'],
                    'entered_logistics_unit': str(source.logistics_unit) if source and source.logistics_unit is not None else None,
                    'prices_gross': {key: str(value) for key, value in result['prices_gross'].items()},
                    'original_prices_gross': {key: str(getattr(price, key + '_gross')) if getattr(price, key + '_gross') is not None else None
                                              for key in ('retail', 'small', 'medium', 'large')}},
            )
            for tier in ('retail', 'small', 'medium', 'large'):
                values['current_' + tier] = getattr(price, tier)
                if tier != 'retail':
                    values['calculated_' + tier] = net.get(tier)
                    values['discount_' + tier] = getattr(source, tier, None)
            for field in ('base_analog', 'base_exclusive', 'minimum_margin'):
                values[field] = getattr(source, field, None)
            values['margin_current'] = calculate_margin(price=price.retail, cost=result['cost_with_logistics'])
            values['margin_calculated'] = calculate_margin(price=net.get('retail'), cost=result['cost_with_logistics'])
            values['current_vs_calculated_percent'] = calculate_deviation(current_value=price.retail, reference_value=net.get('retail'))[1]
            # Historical variants are read-only; new calculations use the single default variant.
            IPriceSnapshotRegion.objects.update_or_create(snapshot_product=product, sale_region=price.shipp_region,
                                                          historical_variant='', defaults=values)
            count += 1
        from datasets.services.iprice_snapshot_approval import refresh_iprice_product_approval_summary
        from datasets.services.iprice_workspace import IPriceWorkspace
        for product in products.values():
            refresh_iprice_product_approval_summary(product.pk, workspace=IPriceWorkspace('select-market'))
    return {'regions_created': count, 'snapshot_id': snapshot.pk}
