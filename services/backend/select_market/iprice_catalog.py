"""The complete dated price list defines membership, never website classification."""
from django.db import transaction

from .iprice_prices import prices_as_of
from .iprice_domain_models import (
    BaseProductPrice, ParserProductUrl, ParserProductClassification,
    ParserProductMatch, IPriceSnapshotProduct,
)


@transaction.atomic
def build_products(snapshot):
    from datasets.services.iprice_workspace import IPriceWorkspace
    from datasets.services.iprice_snapshot_builder import (
        IPriceSnapshotBuildError, decimal_min, decimal_max, decimal_median, calculate_deviation,
    )
    from datasets.services.iprice_competitor_selection import _replace_snapshot_competitors
    if snapshot.status != 'building':
        raise IPriceSnapshotBuildError('Products can be built only for a building snapshot')
    prices = list(prices_as_of(snapshot.calculation_date).order_by('code', 'shipp_region', 'id'))
    if not prices:
        raise IPriceSnapshotBuildError('Нет полного прайса на дату расчёта')
    by_code = {}
    for row in prices:
        by_code.setdefault(row.code, []).append(row)
    registry = {row.own_code: row for row in ParserProductUrl.objects.filter(source='base', own_code__isnull=False)}
    active_urls = set(ParserProductUrl.objects.filter(source='base', status='active').values_list('pk', flat=True))
    website = {}
    for row in BaseProductPrice.objects.filter(code_1c__in=by_code, date_add__date__lte=snapshot.calculation_date).order_by('-date_add', '-id'):
        identity = registry.get(row.code_1c)
        if row.product_key in active_urls and (identity is None or (identity.on_website and identity.pk == row.product_key)):
            website.setdefault(row.code_1c, row)
    classifications = {row.product_key: row for row in ParserProductClassification.objects.filter(status='active')}
    matches = {}
    for match in ParserProductMatch.objects.filter(status='active'):
        matches.setdefault(match.product_key_base, set()).add(match.product_key_competitor)
    IPriceSnapshotProduct.objects.filter(snapshot=snapshot).delete()
    workspace = IPriceWorkspace('select-market')
    competitors_created = 0
    for code, regional_prices in by_code.items():
        source = regional_prices[0]
        base = website.get(code)
        identity = registry.get(code)
        product_key = identity.pk if identity else base.product_key if base else None
        classification = classifications.get(product_key)
        warnings = []
        if not base:
            warnings.append('MISSING_WEBSITE_PRODUCT')
        if not classification:
            warnings.append('MISSING_CLASSIFICATION')
        retail = [row.retail for row in regional_prices if row.retail is not None]
        groups = {f'group_{level}': getattr(source, f'group_{level}') for level in range(1, 5)}
        if any(any(getattr(row, field) != value for field, value in groups.items()) or row.nom != source.nom for row in regional_prices):
            raise IPriceSnapshotBuildError(f'Различаются наименование или группы товара {code} между регионами')
        if any(row.assortment_matrix_status != source.assortment_matrix_status for row in regional_prices):
            raise IPriceSnapshotBuildError(f'Различается САМ товара {code} между регионами')
        product = IPriceSnapshotProduct.objects.create(
            snapshot=snapshot, code_1c=code, nom=source.nom,
            assortment_matrix_status=source.assortment_matrix_status,
            base_product_key=product_key,
            is_classified=classification is not None, **groups,
            nom_hier_code=code, nom_hier=source.nom,
            item_type=classification.item_type if classification else 'product',
            **{field: getattr(classification, field, None) for field in ('category', 'subcategory', 'subcategory_type', 'color', 'material', 'modification', 'article_number_analogs')},
            url=base.url if base else None, image=base.image if base else None,
            pricing_method='exclusive', warning_codes=warnings,
            calculation_status='warning' if warnings else 'success',
            current_retail_min=decimal_min(retail), current_retail_max=decimal_max(retail),
            current_retail_median=decimal_median(retail),
            calculation_details={'price_import_id': source.batch_id, 'price_rows': [row.pk for row in regional_prices],
                                 'base_product_price_id': base.pk if base else None},
        )
        keys = matches.get(product_key, set()) if classification else set()
        market_prices = _replace_snapshot_competitors(product=product, competitor_keys=keys, workspace=workspace)
        competitors_created += product.competitors.count()
        product.competitor_count = len(market_prices)
        product.competitor_rrp_min = decimal_min(market_prices)
        product.competitor_rrp_max = decimal_max(market_prices)
        product.competitor_rrp_median = decimal_median(market_prices)
        product.pricing_method = 'analog' if market_prices else 'exclusive'
        product.current_vs_competitor_amount, product.current_vs_competitor_percent = calculate_deviation(
            current_value=product.current_retail_median, reference_value=product.competitor_rrp_median)
        product.save()
    return {'snapshot_id': snapshot.pk, 'products_created': len(by_code), 'competitors_created': competitors_created}
