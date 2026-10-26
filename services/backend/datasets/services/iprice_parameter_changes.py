from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from dashboards.models import IPriceParameterChangeLog
from datasets.models import (
    DepartureDiscount,
    IPriceCalculationConfig,
    IPriceSnapshot,
    IPriceSnapshotApproval,
    IPriceSnapshotProduct,
    IPriceSnapshotRegion,
)
from datasets.services.iprice_snapshot_approval import (
    calculate_discount_price,
    refresh_iprice_product_approval_summary,
)
from datasets.services.iprice_snapshot_builder import (
    build_iprice_snapshot_regions,
)
from datasets.services.iprice_snapshot_filters import (
    apply_iprice_products_search,
    apply_iprice_regions_search,
    filter_iprice_products_queryset,
    filter_iprice_regions_queryset,
)


COEFFICIENT_FIELDS = (
    "base_analog",
    "base_exclusive",
    "minimum_margin",
)
DISCOUNT_FIELDS = (
    "distr",
    "distr_1",
    "small",
    "medium",
    "large",
)


class IPriceParameterChangeError(ValueError):
    pass


def normalize_key(value):
    return str(value or "").strip().casefold()


def route_key(product_key, departure, arrival):
    return (
        int(product_key),
        normalize_key(departure),
        normalize_key(arrival),
    )


def parse_changes(values, fields):
    result = {}
    for field in fields:
        value = values.get(field)
        if value in (None, ""):
            continue
        try:
            value = Decimal(str(value).replace(",", "."))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise IPriceParameterChangeError(
                f"Поле {field} должно быть числом"
            ) from exc
        if not value.is_finite() or abs(value) >= Decimal('1000000'):
            raise IPriceParameterChangeError(f'Недопустимое значение {field}')
        result[field] = value
    return result


def validate_changes(coefficients, discounts):
    if "base_analog" in coefficients and coefficients["base_analog"] < 0:
        raise IPriceParameterChangeError(
            "Коэффициент к цене аналога должен быть не меньше 0"
        )
    if "base_exclusive" in coefficients and not (
        Decimal("0") < coefficients["base_exclusive"] < Decimal("1")
    ):
        raise IPriceParameterChangeError(
            "Базовая маржа должна быть больше 0 и меньше 1"
        )
    if "minimum_margin" in coefficients and not (
        Decimal("0") <= coefficients["minimum_margin"] < Decimal("1")
    ):
        raise IPriceParameterChangeError(
            "Минимальная маржа должна быть от 0 до 1"
        )
    for field, value in discounts.items():
        if not Decimal("0") <= value < Decimal("1"):
            raise IPriceParameterChangeError(
                f"Скидка {field} должна быть от 0 до 1"
            )
    if not coefficients and not discounts:
        raise IPriceParameterChangeError(
            "Не выбраны параметры для изменения"
        )


def ensure_snapshot_parameters_editable(snapshot):
    from datasets.services.iprice_snapshot_builder import _snapshot_workspace
    workspace = _snapshot_workspace(snapshot)
    IPriceSnapshot = workspace.model('IPriceSnapshot') if workspace else globals()['IPriceSnapshot']
    if workspace and IPriceSnapshot.objects.filter(status='building').exists():
        raise IPriceParameterChangeError('Дождитесь завершения текущего расчёта перед изменением параметров.')
    if snapshot.is_active or (workspace and snapshot.was_active):
        raise IPriceParameterChangeError(
            "Настройки ценообразования активированной версии изменять нельзя"
        )
    latest_id = IPriceSnapshot.objects.filter(
        status=IPriceSnapshot.STATUS_SUCCESS,
    ).order_by("-created_at", "-id").values_list("id", flat=True).first()
    if snapshot.id != latest_id:
        raise IPriceParameterChangeError(
            "Параметры можно менять только в последней успешной версии"
        )


def resolve_regions(snapshot, mode, filters, search):
    from datasets.services.iprice_snapshot_builder import _snapshot_workspace
    workspace = _snapshot_workspace(snapshot)
    IPriceSnapshotProduct = workspace.model('IPriceSnapshotProduct') if workspace else globals()['IPriceSnapshotProduct']
    IPriceSnapshotRegion = workspace.model('IPriceSnapshotRegion') if workspace else globals()['IPriceSnapshotRegion']
    if not filters and not str(search or "").strip():
        raise IPriceParameterChangeError(
            "Перед применением выберите хотя бы один фильтр"
        )
    if mode == "products":
        products = filter_iprice_products_queryset(
            queryset=IPriceSnapshotProduct.objects.filter(snapshot=snapshot),
            filters=filters,
        )
        products = apply_iprice_products_search(
            queryset=products,
            search=search,
        )
        return IPriceSnapshotRegion.objects.filter(
            snapshot_product_id__in=products.values("id"),
        ).select_related("snapshot_product")
    regions = filter_iprice_regions_queryset(
        queryset=IPriceSnapshotRegion.objects.filter(
            snapshot_product__snapshot=snapshot,
        ).select_related("snapshot_product"),
        filters=filters,
    )
    return apply_iprice_regions_search(
        queryset=regions,
        search=search,
    )


def preview_iprice_parameter_changes(*, snapshot, mode, filters, search):
    if snapshot._meta.app_label == 'select_market':
        from select_market.iprice_regional_edits import preview
        return preview(snapshot, filters, search)
    ensure_snapshot_parameters_editable(snapshot)
    regions = resolve_regions(snapshot, mode, filters, search)
    routes = {
        route_key(
            row["snapshot_product__base_product_key"],
            row["departure"],
            row["sale_region"],
        )
        for row in regions.values(
            "snapshot_product__base_product_key",
            "departure",
            "sale_region",
        )
    }
    return {
        "products": regions.values("snapshot_product_id").distinct().count(),
        "regions": regions.count(),
        "routes": len(routes),
        "pricing_methods": sorted(
            set(
                regions.values_list(
                    "snapshot_product__pricing_method",
                    flat=True,
                )
            )
        ),
    }


def _approval_snapshot(snapshot, *, product_ids=None):
    from datasets.services.iprice_snapshot_builder import _snapshot_workspace
    workspace = _snapshot_workspace(snapshot)
    IPriceSnapshotApproval = workspace.model('IPriceSnapshotApproval') if workspace else globals()['IPriceSnapshotApproval']
    result = []
    approvals = IPriceSnapshotApproval.objects.filter(
        snapshot_region__snapshot_product__snapshot=snapshot,
    ).select_related("snapshot_region__snapshot_product")
    if product_ids is not None:
        approvals = approvals.filter(
            snapshot_region__snapshot_product_id__in=set(product_ids),
        )
    for item in approvals:
        region = item.snapshot_region
        result.append({
            "key": route_key(
                region.snapshot_product.base_product_key,
                region.departure,
                region.sale_region,
            ),
            "revision": item.revision,
            "approved_rrp": item.approved_rrp,
            "approved_distr": item.approved_distr,
            "approved_distr_1": item.approved_distr_1,
            "approved_small": item.approved_small,
            "approved_medium": item.approved_medium,
            "approved_large": item.approved_large,
            "approved_by_id": item.approved_by_id,
            "approved_at": item.approved_at,
            "comment": item.comment,
            "is_current": item.is_current,
            "date_add": item.date_add,
        })
    return result


def _restore_approvals(snapshot, saved, *, invalidate_current=False):
    from datasets.services.iprice_snapshot_builder import _snapshot_workspace
    workspace = _snapshot_workspace(snapshot)
    IPriceSnapshotApproval = workspace.model('IPriceSnapshotApproval') if workspace else globals()['IPriceSnapshotApproval']
    IPriceSnapshotRegion = workspace.model('IPriceSnapshotRegion') if workspace else globals()['IPriceSnapshotRegion']
    saved_keys = {values["key"] for values in saved}
    regions = {
        route_key(
            row.snapshot_product.base_product_key,
            row.departure,
            row.sale_region,
        ): row
        for row in IPriceSnapshotRegion.objects.filter(
            snapshot_product__snapshot=snapshot,
        ).select_related("snapshot_product")
        if not saved_keys or route_key(
            row.snapshot_product.base_product_key,
            row.departure,
            row.sale_region,
        ) in saved_keys
    }
    restored = []
    timestamps = []
    for values in saved:
        region = regions.get(values["key"])
        if region is None:
            raise IPriceParameterChangeError(
                "После пересчёта не найдена строка ручного утверждения"
            )
        derived = {}
        restore_as_current = values["is_current"] and not invalidate_current
        if restore_as_current:
            for target, discount_field in (
                ("approved_distr", "discount_distr"),
                ("approved_distr_1", "discount_distr_1"),
                ("approved_small", "discount_small"),
                ("approved_medium", "discount_medium"),
                ("approved_large", "discount_large"),
            ):
                derived[target] = calculate_discount_price(
                    rrp=values["approved_rrp"],
                    discount=getattr(region, discount_field),
                )
        else:
            derived = {
                field: values[field]
                for field in (
                    "approved_distr",
                    "approved_distr_1",
                    "approved_small",
                    "approved_medium",
                    "approved_large",
                )
            }
        restored.append(IPriceSnapshotApproval(
            snapshot_region=region,
            revision=values["revision"],
            approved_rrp=values["approved_rrp"],
            approved_by_id=values["approved_by_id"],
            comment=values["comment"],
            is_current=restore_as_current,
            **derived,
        ))
        timestamps.append((values["approved_at"], values["date_add"]))
    created = IPriceSnapshotApproval.objects.bulk_create(restored, batch_size=1000)
    for item, (approved_at, date_add) in zip(created, timestamps):
        IPriceSnapshotApproval.objects.filter(pk=item.pk).update(
            approved_at=approved_at,
            date_add=date_add,
        )
    for product_id in regions_for_products(regions.values()):
        refresh_iprice_product_approval_summary(product_id, workspace=workspace)


def regions_for_products(regions):
    return {row.snapshot_product_id for row in regions}


def apply_iprice_parameter_changes(
    *, snapshot, mode, filters, search, coefficient_values,
    discount_values, user, expected_revision=None, reason='',
):
    from datasets.services.iprice_snapshot_builder import _snapshot_workspace
    workspace = _snapshot_workspace(snapshot)
    if workspace and workspace.code == 'select-market':
        from select_market.iprice_regional_edits import apply
        return apply(snapshot=snapshot, filters=filters, search=search, coefficients=coefficient_values,
                     discounts=discount_values, user=user, expected_revision=expected_revision, reason=reason)

    DepartureDiscount = workspace.model('DepartureDiscount') if workspace else globals()['DepartureDiscount']
    IPriceCalculationConfig = workspace.model('IPriceCalculationConfig') if workspace else globals()['IPriceCalculationConfig']
    IPriceParameterChangeLog = workspace.model('IPriceParameterChangeLog') if workspace else globals()['IPriceParameterChangeLog']
    IPriceSnapshot = workspace.model('IPriceSnapshot') if workspace else globals()['IPriceSnapshot']
    coefficients = parse_changes(coefficient_values, COEFFICIENT_FIELDS)
    discounts = parse_changes(discount_values, DISCOUNT_FIELDS)
    validate_changes(coefficients, discounts)
    ensure_snapshot_parameters_editable(snapshot)

    log = IPriceParameterChangeLog.objects.create(
        user=user,
        snapshot_id=snapshot.id,
        mode=mode,
        filters=filters,
        search=search or "",
        changes={
            "coefficients": {key: str(value) for key, value in coefficients.items()},
            "discounts": {key: str(value) for key, value in discounts.items()},
        },
    )
    try:
        with transaction.atomic():
            from datasets.services.iprice_snapshot_builder import _lock_snapshot_workspace
            _lock_snapshot_workspace(workspace)
            locked_snapshot = IPriceSnapshot.objects.select_for_update().get(pk=snapshot.pk)
            ensure_snapshot_parameters_editable(locked_snapshot)
            if workspace and expected_revision is not None and locked_snapshot.parameters.get('edit_revision', 0) != expected_revision:
                raise IPriceParameterChangeError('Расчёт изменён другим пользователем. Обновите предварительный просмотр.')
            selected = list(resolve_regions(
                locked_snapshot, mode, filters, search,
            ))
            if not selected:
                raise IPriceParameterChangeError("По фильтрам не найдено строк")
            routes = {
                route_key(
                    row.snapshot_product.base_product_key,
                    row.departure,
                    row.sale_region,
                ): row.snapshot_product.pricing_method
                for row in selected
            }
            product_keys = {key[0] for key in routes}
            configs = {
                route_key(row.product_key, row.departure, row.arrival): row
                for row in IPriceCalculationConfig.objects.select_for_update().filter(
                    is_active=True,
                    product_key__in=product_keys,
                )
                if route_key(row.product_key, row.departure, row.arrival) in routes
            }
            source_discounts = {
                route_key(row.product_key, row.departure, row.arrival): row
                for row in DepartureDiscount.objects.select_for_update().filter(
                    is_active=True,
                    arrival__isnull=False,
                    product_key__in=product_keys,
                )
                if route_key(row.product_key, row.departure, row.arrival) in routes
            }
            if set(configs) != set(routes) or set(source_discounts) != set(routes):
                raise IPriceParameterChangeError(
                    "Для части выбранных строк отсутствуют активные параметры"
                )
            config_overrides = {}
            discount_overrides = {}
            configs_changed = 0
            discounts_changed = 0
            for key, method in routes.items():
                current = configs[key]
                updates = {field: getattr(current, field) for field in COEFFICIENT_FIELDS}
                if method == "analog" and "base_analog" in coefficients:
                    updates["base_analog"] = coefficients["base_analog"]
                if method == "exclusive" and "base_exclusive" in coefficients:
                    updates["base_exclusive"] = coefficients["base_exclusive"]
                if "minimum_margin" in coefficients:
                    updates["minimum_margin"] = coefficients["minimum_margin"]
                if any(Decimal(getattr(current, field)) != updates[field] for field in COEFFICIENT_FIELDS):
                    current.is_active = False
                    current.save(update_fields=["is_active"])
                    current = IPriceCalculationConfig.objects.create(
                        product_key=current.product_key,
                        departure=current.departure,
                        arrival=current.arrival,
                        is_active=True,
                        **updates,
                    )
                    configs_changed += 1
                config_overrides[key] = current

                current_discount = source_discounts[key]
                discount_updates = {
                    field: discounts.get(field, getattr(current_discount, field))
                    for field in DISCOUNT_FIELDS
                }
                if any(Decimal(getattr(current_discount, field)) != discount_updates[field] for field in DISCOUNT_FIELDS):
                    current_discount.is_active = False
                    current_discount.save(update_fields=["is_active"])
                    current_discount = DepartureDiscount.objects.create(
                        product_key=current_discount.product_key,
                        departure=current_discount.departure,
                        arrival=current_discount.arrival,
                        is_active=True,
                        **discount_updates,
                    )
                    discounts_changed += 1
                discount_overrides[key] = current_discount

            saved_approvals = []
            if configs_changed or discounts_changed:
                saved_approvals = _approval_snapshot(locked_snapshot)
                original_status = locked_snapshot.status
                locked_snapshot.status = IPriceSnapshot.STATUS_BUILDING
                locked_snapshot.save(update_fields=["status"])
                build_iprice_snapshot_regions(
                    snapshot=locked_snapshot,
                    config_overrides=config_overrides,
                    discount_overrides=discount_overrides,
                )
                _restore_approvals(locked_snapshot, saved_approvals)
                locked_snapshot.status = original_status
                locked_snapshot.save(update_fields=["status"])
            affected = {
                "products": len({row.snapshot_product_id for row in selected}),
                "regions": len(selected),
                "routes": len(routes),
                "configs_changed": configs_changed,
                "discounts_changed": discounts_changed,
                "approvals_preserved": len(saved_approvals),
            }
            if workspace:
                locked_snapshot.parameters = {**locked_snapshot.parameters,
                    'edit_revision': locked_snapshot.parameters.get('edit_revision', 0) + 1}
                locked_snapshot.save(update_fields=['parameters'])
        log.affected = affected
        log.status = IPriceParameterChangeLog.STATUS_SUCCESS
        log.finished_at = timezone.now()
        log.save(update_fields=["affected", "status", "finished_at"])
        return affected
    except Exception as exc:
        log.status = IPriceParameterChangeLog.STATUS_ERROR
        log.error = str(exc)
        log.finished_at = timezone.now()
        log.save(update_fields=["status", "error", "finished_at"])
        raise
