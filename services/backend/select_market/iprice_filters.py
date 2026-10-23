"""Shared selection contract for Select Market tables and bulk operations."""
from django.db.models import Q

PRODUCT_FILTERS = {key: key for key in (
    'group_1', 'group_2', 'group_3', 'group_4', 'category', 'subcategory',
    'subcategory_type', 'color', 'material', 'modification', 'item_type', 'is_classified',
    'pricing_method', 'calculation_status', 'sale_region',
)}
EMPTY = '__empty__'


def query_filters(params):
    import json
    try:
        filters = json.loads(params.get('filters', '{}'))
        if not isinstance(filters, dict) or len(filters) > len(PRODUCT_FILTERS):
            raise ValueError()
        if any(not isinstance(values, list) or len(values) > 100 or
               any(not isinstance(value, str) or len(value) > 1000 for value in values)
               for values in filters.values()):
            raise ValueError()
        return filters
    except (ValueError, TypeError):
        raise ValueError('Некорректные фильтры') from None


def filter_products(queryset, filters, search='', *, skip=None, prefix=''):
    if set(filters) - set(PRODUCT_FILTERS):
        raise ValueError('Неизвестный фильтр')
    for key, values in filters.items():
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            raise ValueError('Значения фильтра должны быть списком строк')
        if key == skip or not values:
            continue
        if key == 'sale_region':
            if prefix:
                queryset = queryset.filter(sale_region__in=values)
            else:
                from .iprice_domain_models import IPriceSnapshotRegion
                matching = IPriceSnapshotRegion.objects.filter(sale_region__in=values)
                queryset = queryset.filter(pk__in=matching.values('snapshot_product_id'))
            continue
        field = prefix + key
        if key == 'is_classified':
            if set(values) - {'true', 'false'}:
                raise ValueError('Некорректный фильтр классификации')
            queryset = queryset.filter(**{field + '__in': [value == 'true' for value in values]})
        else:
            condition = Q(**{field + '__in': [value for value in values if value != EMPTY]})
            if EMPTY in values:
                condition |= Q(**{field + '__isnull': True}) | Q(**{field: ''})
            queryset = queryset.filter(condition)
    if search.strip():
        queryset = queryset.filter(Q(**{prefix + 'code_1c__icontains': search.strip()}) |
                                   Q(**{prefix + 'nom__icontains': search.strip()}))
    return queryset


def filter_options(queryset, filters, search=''):
    result = {}
    for field in PRODUCT_FILTERS:
        scoped = filter_products(queryset, filters, search, skip=field)
        if field == 'sale_region':
            from .iprice_domain_models import IPriceSnapshotRegion
            values = IPriceSnapshotRegion.objects.filter(snapshot_product_id__in=scoped.values('pk')).order_by().values_list(field, flat=True).distinct()
        else:
            values = scoped.order_by().values_list(field, flat=True).distinct()
        result[field] = sorted({('true' if value else 'false') if field == 'is_classified'
                                else value or EMPTY for value in values})
    return result


def comparison_products(*, base, comparison):
    """Current products plus the old side of genuinely removed regional rows."""
    from django.db.models import Exists, OuterRef
    from .iprice_domain_models import IPriceSnapshotRegion, IPriceSnapshotProduct
    newer = IPriceSnapshotRegion.objects.filter(snapshot_product__snapshot=comparison)
    matching = newer.filter(snapshot_product__code_1c=OuterRef('snapshot_product__code_1c'),
        sale_region=OuterRef('sale_region'), historical_variant=OuterRef('historical_variant'))
    removed = IPriceSnapshotRegion.objects.filter(snapshot_product__snapshot=base).annotate(
        has_newer=Exists(matching)).filter(has_newer=False)
    return IPriceSnapshotProduct.objects.filter(
        Q(pk__in=newer.values('snapshot_product_id')) | Q(pk__in=removed.values('snapshot_product_id')))
