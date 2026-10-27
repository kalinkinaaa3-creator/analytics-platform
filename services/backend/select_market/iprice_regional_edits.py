"""Atomic edits of regional inputs and snapshot rows, preserving price history."""
from decimal import Decimal
from hashlib import sha256
from types import SimpleNamespace
from django.db import transaction
from django.utils import timezone
from .iprice_models import IPriceRegionalInput
from .iprice_domain_models import IPriceSnapshot, IPriceSnapshotRegion, IPriceParameterChangeLog
from .iprice_filters import PRODUCT_FILTERS, filter_products
from .iprice_regional_calculation import INPUT_FIELDS, build_regions


def resolve(snapshot, filters, search='', list_scope=None):
    from datasets.services.iprice_parameter_changes import IPriceParameterChangeError
    if list_scope is None and not any(filters.values()) and not search.strip():
        raise IPriceParameterChangeError('Выберите хотя бы один фильтр.')
    if set(filters) - set(PRODUCT_FILTERS) - {'code_1c', 'sale_region'}:
        raise IPriceParameterChangeError('Неизвестный фильтр.')
    rows = IPriceSnapshotRegion.objects.filter(snapshot_product__snapshot=snapshot).select_related('snapshot_product')
    if rows.exclude(historical_variant='').exists():
        raise IPriceParameterChangeError('Историческая версия с маршрутами доступна только для просмотра. Создайте новый расчёт.')
    for key, path in (('code_1c', 'snapshot_product__code_1c'), ('sale_region', 'sale_region')):
        if filters.get(key):
            rows = rows.filter(**{path + '__in': filters[key]})
    rows = filter_products(rows, {key: value for key, value in filters.items() if key in PRODUCT_FILTERS}, search, prefix='snapshot_product__')
    if list_scope is not None:
        from .iprice_row_controls import filter_rows, regional_product_summaries
        summaries = regional_product_summaries(rows) if list_scope['mode'] == 'products' and filters.get('sale_region') else None
        rows = filter_rows(rows, list_scope, summaries=summaries)
    return rows


def scope_signature(row_ids):
    return sha256(','.join(str(pk) for pk in sorted(row_ids)).encode('ascii')).hexdigest()


def describe_affected_products(rows):
    products = {}
    for row in rows:
        item = products.setdefault(row.snapshot_product_id, {
            'id': row.snapshot_product_id, 'name': row.snapshot_product.nom,
            'code_1c': row.snapshot_product.code_1c, 'regions': [],
        })
        if row.sale_region not in item['regions']:
            item['regions'].append(row.sale_region)
    for item in products.values():
        item['regions'].sort()
    return sorted(products.values(), key=lambda item: (item['name'] or '', item['code_1c'] or '', item['id']))


def parameter_change_products(snapshot_id, affected):
    if 'product_details' in affected:
        return affected['product_details']
    if 'row_ids' not in affected:
        return None
    rows = IPriceSnapshotRegion.objects.filter(snapshot_product__snapshot_id=snapshot_id,
        pk__in=affected['row_ids']).select_related('snapshot_product')
    if rows.count() != len(set(affected['row_ids'])):
        return None
    return describe_affected_products(rows)


def preview(snapshot, filters, search='', list_scope=None):
    from datasets.services.iprice_parameter_changes import ensure_snapshot_parameters_editable
    ensure_snapshot_parameters_editable(snapshot)
    rows = resolve(snapshot, filters, search, list_scope)
    selected = list(rows.values_list('pk', 'snapshot_product_id'))
    return {'products': len({product for _, product in selected}), 'regions': len(selected), 'routes': len(selected),
            'scope_signature': scope_signature(pk for pk, _ in selected)}


@transaction.atomic
def apply(*, snapshot, filters, search='', list_scope=None, expected_scope=None, coefficients=None, discounts=None, delivery=None, user=None, expected_revision=None, reason=''):
    from datasets.services.iprice_snapshot_builder import _lock_snapshot_workspace
    from datasets.services.iprice_workspace import IPriceWorkspace
    from datasets.services.iprice_parameter_changes import ensure_snapshot_parameters_editable, IPriceParameterChangeError
    if not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > 2000:
        raise IPriceParameterChangeError('Укажите причину изменения (до 2000 символов).')
    workspace = IPriceWorkspace('select-market')
    _lock_snapshot_workspace(workspace)
    snapshot = IPriceSnapshot.objects.select_for_update().get(pk=snapshot.pk)
    ensure_snapshot_parameters_editable(snapshot)
    if expected_revision is not None and expected_revision != snapshot.parameters.get('edit_revision', 0):
        raise IPriceParameterChangeError('Расчёт изменён другим пользователем. Повторите предварительный просмотр.')
    changes = {**(coefficients or {}), **(discounts or {}), **(delivery or {})}
    if not changes or set(changes) - set(INPUT_FIELDS):
        raise IPriceParameterChangeError('Укажите поддерживаемые параметры.')
    for field, value in changes.items():
        try:
            if field == 'include_transport':
                if not isinstance(value, bool):
                    raise ValueError()
                continue
            value = Decimal(str(value))
            if not value.is_finite() or value < 0 or (field in ('small', 'medium', 'large', 'base_exclusive', 'minimum_margin') and value >= 1):
                raise ValueError()
            IPriceRegionalInput._meta.get_field(field).clean(value, None)
            changes[field] = value
        except Exception as exc:
            raise IPriceParameterChangeError(f'Некорректный параметр {field}') from exc
    rows = list(resolve(snapshot, filters, search, list_scope))
    if list_scope is not None and expected_scope != scope_signature(row.pk for row in rows):
        raise IPriceParameterChangeError('Состав списка изменился. Повторите предварительный просмотр и подтверждение.')
    if not rows:
        raise IPriceParameterChangeError('Нет строк для изменения.')
    overrides = {}
    for row in rows:
        values = {**row.calculation_details.get('regional_input', {}), **changes}
        if values.get('include_transport') and values.get('logistics_unit') is None:
            raise IPriceParameterChangeError('Укажите расходы на доставку на единицу.')
        pair = (row.snapshot_product.code_1c, row.sale_region.casefold())
        source = IPriceRegionalInput.objects.filter(month=snapshot.calculation_date.replace(day=1),
            code=pair[0], region__iexact=row.sale_region).first()
        if source is None:
            source = IPriceRegionalInput(month=snapshot.calculation_date.replace(day=1),
                code=pair[0], region=row.sale_region)
        for field, value in changes.items():
            setattr(source, field, value)
        source.save()
        overrides[pair] = SimpleNamespace(pk=source.pk, **values)
    # Keep the old monetary decision intact; a new decision gets a new revision.
    for row in rows:
        if row.approvals.filter(is_current=True).update(is_current=False):
            row.warning_codes = list(dict.fromkeys([*row.warning_codes, 'REAPPROVAL_REQUIRED']))
            row.save(update_fields=['warning_codes'])
    build_regions(snapshot=snapshot, snapshot_product_ids={row.snapshot_product_id for row in rows}, input_overrides=overrides)
    snapshot.parameters = {**snapshot.parameters, 'edit_revision': snapshot.parameters.get('edit_revision', 0) + 1}
    snapshot.save(update_fields=['parameters'])
    affected = {'products': len({row.snapshot_product_id for row in rows}), 'regions': len(rows), 'routes': len(rows),
                'row_ids': [row.pk for row in rows], 'product_details': describe_affected_products(rows)}
    IPriceParameterChangeLog.objects.create(snapshot_id=snapshot.pk, user=user, mode=(list_scope or {}).get('mode', 'regions'),
        filters={**filters, **({'_list_scope': list_scope} if list_scope is not None else {})}, search=search,
        changes={field: value if isinstance(value, bool) else str(value) for field, value in changes.items()},
        affected=affected, status='success', reason=reason.strip(), finished_at=timezone.now())
    return affected
