from __future__ import annotations

from decimal import Decimal

from django.db import transaction

from datasets.models import (
    IPriceCompetitorSelectionOverride,
    IPriceCompetitorSelectionChange,
    IPriceSnapshot,
    IPriceSnapshotCompetitor,
    IPriceSnapshotProduct,
    ParserProductClassification,
    ParserProductMatch,
    ParserProductUrl,
)
from datasets.services.iprice_parameter_changes import (
    _approval_snapshot,
    _restore_approvals,
)
from datasets.services.iprice_snapshot_builder import (
    build_iprice_snapshot_regions,
    calculate_deviation,
    decimal_max,
    decimal_median,
    decimal_min,
)
from datasets.services.iprice_source_selector import (
    get_competitor_price_data,
    get_competitor_regions,
)
class IPriceCompetitorSelectionError(ValueError):
    pass


def ensure_selection_editable(snapshot: IPriceSnapshot) -> None:
    from datasets.services.iprice_snapshot_builder import _snapshot_workspace
    workspace = _snapshot_workspace(snapshot)
    IPriceSnapshot = workspace.model('IPriceSnapshot') if workspace else globals()['IPriceSnapshot']
    if workspace and IPriceSnapshot.objects.filter(status='building').exists():
        raise IPriceCompetitorSelectionError('Дождитесь завершения текущего расчёта перед изменением аналогов.')
    if snapshot.status != IPriceSnapshot.STATUS_SUCCESS:
        raise IPriceCompetitorSelectionError(
            "Состав конкурентов можно менять только в успешно рассчитанном снапшоте"
        )
    if not snapshot.is_current:
        raise IPriceCompetitorSelectionError(
            "Состав конкурентов можно менять только в текущей версии снапшота"
        )
    if snapshot.is_active or snapshot.was_active:
        raise IPriceCompetitorSelectionError(
            "Состав конкурентов зафиксирован после активации снапшота"
        )
    latest_id = IPriceSnapshot.objects.filter(
        status=IPriceSnapshot.STATUS_SUCCESS,
    ).order_by("-created_at", "-id").values_list("id", flat=True).first()
    if snapshot.id != latest_id:
        raise IPriceCompetitorSelectionError(
            "Состав конкурентов можно менять только в последнем успешном снапшоте"
        )


def is_selection_editable(snapshot: IPriceSnapshot) -> bool:
    from datasets.services.iprice_snapshot_builder import _snapshot_workspace
    workspace = _snapshot_workspace(snapshot)
    IPriceSnapshot = workspace.model('IPriceSnapshot') if workspace else globals()['IPriceSnapshot']
    try:
        ensure_selection_editable(snapshot)
    except IPriceCompetitorSelectionError:
        return False
    return True


def _same_class(left, right) -> bool:
    return all(
        (getattr(left, field, "") or "").strip().casefold()
        == (getattr(right, field, "") or "").strip().casefold()
        for field in ("item_type", "category", "subcategory", "subcategory_type")
    )


def _automatic_keys(base_product_key: int, *, workspace=None) -> set[int]:
    ParserProductMatch = workspace.model('ParserProductMatch') if workspace else globals()['ParserProductMatch']
    if workspace:
        from django.db.models import Q
        Override = workspace.model('IPriceCompetitorSelectionOverride')
        overridden = Override.objects.filter(product_key_base=base_product_key).values('product_key_competitor')
        return set(ParserProductMatch.objects.filter(product_key_base=base_product_key).filter(
            Q(match_type=ParserProductMatch.MATCH_TYPE_AUTO) |
            (Q(status=ParserProductMatch.STATUS_ACTIVE) & ~Q(product_key_competitor__in=overridden))
        ).values_list('product_key_competitor', flat=True))
    return set(
        ParserProductMatch.objects.filter(
            product_key_base=base_product_key,
            status=ParserProductMatch.STATUS_ACTIVE,
        ).values_list("product_key_competitor", flat=True)
    )


def _effective_keys(base_product_key: int, *, workspace=None) -> tuple[set[int], dict[int, str]]:
    IPriceCompetitorSelectionOverride = workspace.model('IPriceCompetitorSelectionOverride') if workspace else globals()['IPriceCompetitorSelectionOverride']
    automatic = _automatic_keys(base_product_key, workspace=workspace)
    modes = dict(
        IPriceCompetitorSelectionOverride.objects.filter(
            product_key_base=base_product_key,
        ).values_list("product_key_competitor", "selection_mode")
    )
    effective = set(automatic)
    effective.update(
        key for key, mode in modes.items()
        if mode == IPriceCompetitorSelectionOverride.MODE_INCLUDE
    )
    effective.difference_update(
        key for key, mode in modes.items()
        if mode == IPriceCompetitorSelectionOverride.MODE_EXCLUDE
    )
    return effective, modes


def _replace_operational_matches(
    *, base_product_key: int, competitor_keys: set[int], modes: dict[int, str],
    manual_keys: set[int] | None = None,
    workspace=None,
) -> None:
    IPriceCompetitorSelectionOverride = workspace.model('IPriceCompetitorSelectionOverride') if workspace else globals()['IPriceCompetitorSelectionOverride']
    ParserProductMatch = workspace.model('ParserProductMatch') if workspace else globals()['ParserProductMatch']
    manual_keys = manual_keys or set()
    automatic_keys = set(ParserProductMatch.objects.filter(
        product_key_base=base_product_key, match_type=ParserProductMatch.MATCH_TYPE_AUTO,
    ).values_list('product_key_competitor', flat=True)) if workspace else set()
    ParserProductMatch.objects.filter(
        product_key_base=base_product_key,
        status=ParserProductMatch.STATUS_ACTIVE,
    ).update(status=ParserProductMatch.STATUS_INACTIVE)
    rows = [
        ParserProductMatch(
            product_key_base=base_product_key,
            product_key_competitor=key,
            status=ParserProductMatch.STATUS_ACTIVE,
            match_type=(
                ParserProductMatch.MATCH_TYPE_MANUAL
                if (
                    (key in manual_keys
                    or modes.get(key) == IPriceCompetitorSelectionOverride.MODE_INCLUDE
                    ) and key not in automatic_keys
                )
                else ParserProductMatch.MATCH_TYPE_AUTO
            ),
        )
        for key in sorted(competitor_keys)
    ]
    if rows:
        ParserProductMatch.objects.bulk_create(
            rows,
            update_conflicts=True,
            update_fields=("status", "match_type"),
            unique_fields=("product_key_base", "product_key_competitor"),
            batch_size=500,
        )


def _replace_snapshot_competitors(
    *, product: IPriceSnapshotProduct, competitor_keys: set[int], workspace=None,
) -> list[Decimal]:
    IPriceSnapshotCompetitor = workspace.model('IPriceSnapshotCompetitor') if workspace else globals()['IPriceSnapshotCompetitor']
    IPriceSnapshotProduct = workspace.model('IPriceSnapshotProduct') if workspace else globals()['IPriceSnapshotProduct']
    ParserProductUrl = workspace.model('ParserProductUrl') if workspace else globals()['ParserProductUrl']
    urls = {
        row.id: row
        for row in ParserProductUrl.objects.filter(
            id__in=competitor_keys,
            status=ParserProductUrl.STATUS_ACTIVE,
        ).exclude(source="base")
    }
    rows = []
    prices = []
    for key in sorted(competitor_keys):
        url = urls.get(key)
        if url is None:
            continue
        price_data = get_competitor_price_data(
            product_key=key,
            calculation_date=product.snapshot.calculation_date,
            workspace=workspace,
        )
        region_data = get_competitor_regions(source=url.source, prefix=url.prefix, workspace=workspace)
        calculation_price = price_data["calculation_price"] if price_data else None
        error_codes = []
        warning_codes = []
        if price_data is None:
            warning_codes.append("MISSING_COMPETITOR_PRICE")
        elif calculation_price is None:
            warning_codes.append("MISSING_FINAL_PRICE")
        if calculation_price is not None:
            prices.append(Decimal(calculation_price))
        rows.append(IPriceSnapshotCompetitor(
            snapshot_product=product,
            competitor_product_key=key,
            source=url.source,
            url=url.url,
            prefix=url.prefix,
            competitor_price_date=price_data["price_date"] if price_data else None,
            competitor_final_price_max=calculation_price,
            source_price_row_id=price_data["calculation_row_id"] if price_data else None,
            price_variants=[
                {**variant, "market_regions": region_data["region_groups"]}
                for variant in price_data["variants"]
            ] if price_data else [],
            is_all_regions=region_data["is_all_regions"],
            applicable_regions=region_data["regions"],
            calculation_status=(
                "error" if error_codes
                else ("warning" if warning_codes else "success")
            ),
            warning_codes=warning_codes,
            error_codes=error_codes,
        ))
    IPriceSnapshotCompetitor.objects.filter(snapshot_product=product).delete()
    if rows:
        IPriceSnapshotCompetitor.objects.bulk_create(rows, batch_size=500)
    return prices


def apply_competitor_selection(
    *, snapshot_id: int, product_id: int, competitor_product_keys: list[int],
    selection_mode: str, user=None, reason: str = "",
    workspace=None, expected_revision=None,
) -> dict:
    IPriceCompetitorSelectionChange = workspace.model('IPriceCompetitorSelectionChange') if workspace else globals()['IPriceCompetitorSelectionChange']
    IPriceCompetitorSelectionOverride = workspace.model('IPriceCompetitorSelectionOverride') if workspace else globals()['IPriceCompetitorSelectionOverride']
    IPriceSnapshot = workspace.model('IPriceSnapshot') if workspace else globals()['IPriceSnapshot']
    IPriceSnapshotProduct = workspace.model('IPriceSnapshotProduct') if workspace else globals()['IPriceSnapshotProduct']
    ParserProductClassification = workspace.model('ParserProductClassification') if workspace else globals()['ParserProductClassification']
    ParserProductMatch = workspace.model('ParserProductMatch') if workspace else globals()['ParserProductMatch']
    ParserProductUrl = workspace.model('ParserProductUrl') if workspace else globals()['ParserProductUrl']
    allowed_modes = {
        IPriceCompetitorSelectionOverride.MODE_AUTO,
        IPriceCompetitorSelectionOverride.MODE_INCLUDE,
        IPriceCompetitorSelectionOverride.MODE_EXCLUDE,
    }
    if selection_mode not in allowed_modes:
        raise IPriceCompetitorSelectionError("Неизвестный режим участия конкурента")
    target_keys = {int(value) for value in competitor_product_keys if int(value) > 0}
    if not target_keys:
        raise IPriceCompetitorSelectionError("Не переданы товары конкурента")

    with transaction.atomic():
        from datasets.services.iprice_snapshot_builder import _lock_snapshot_workspace
        _lock_snapshot_workspace(workspace)
        snapshot = IPriceSnapshot.objects.select_for_update().get(pk=snapshot_id)
        ensure_selection_editable(snapshot)
        if workspace and expected_revision is not None and snapshot.parameters.get('edit_revision', 0) != expected_revision:
            raise IPriceCompetitorSelectionError('Расчёт изменён. Обновите карточку товара.')
        product = IPriceSnapshotProduct.objects.select_for_update().select_related(
            "snapshot"
        ).get(pk=product_id, snapshot=snapshot)
        base_classification = ParserProductClassification.objects.filter(
            product_key=product.base_product_key, status="active"
        ).first()
        targets = list(ParserProductClassification.objects.filter(
            product_key__in=target_keys, status="active"
        ))
        if base_classification is None or len(targets) != len(target_keys):
            raise IPriceCompetitorSelectionError(
                "Для части товаров отсутствует активная классификация"
            )
        manual_keys = set(ParserProductMatch.objects.filter(
            product_key_base=product.base_product_key,
            match_type=ParserProductMatch.MATCH_TYPE_MANUAL,
        ).values_list("product_key_competitor", flat=True))
        if any(not _same_class(base_classification, target) for target in targets):
            raise IPriceCompetitorSelectionError(
                "В расчёт можно включать только товары той же полной классификации"
            )

        for key in target_keys:
            existing_override = IPriceCompetitorSelectionOverride.objects.filter(
                product_key_base=product.base_product_key,
                product_key_competitor=key,
            ).first()
            override, _ = IPriceCompetitorSelectionOverride.objects.update_or_create(
                product_key_base=product.base_product_key,
                product_key_competitor=key,
                defaults={
                    "selection_mode": selection_mode,
                    "reason": (reason or "").strip(),
                    "updated_by": user if getattr(user, "is_authenticated", False) else None,
                },
            )
            IPriceCompetitorSelectionChange.objects.create(
                override=override,
                snapshot=snapshot,
                previous_mode=(
                    existing_override.selection_mode if existing_override else ""
                ),
                selection_mode=selection_mode,
                reason=(reason or "").strip(),
                changed_by=(
                    user if getattr(user, "is_authenticated", False) else None
                ),
            )

        effective_keys, modes = _effective_keys(product.base_product_key, workspace=workspace)
        effective_classifications = {
            row.product_key: row
            for row in ParserProductClassification.objects.filter(
                product_key__in=effective_keys,
                status="active",
            )
        }
        effective_keys = {
            key for key in effective_keys
            if key in effective_classifications
            and _same_class(base_classification, effective_classifications[key])
        }
        active_target_keys = set(ParserProductUrl.objects.filter(
            id__in=effective_keys,
            status=ParserProductUrl.STATUS_ACTIVE,
        ).exclude(source="base").values_list("id", flat=True))
        effective_keys &= active_target_keys
        _replace_operational_matches(
            base_product_key=product.base_product_key,
            competitor_keys=effective_keys,
            modes=modes,
            manual_keys=manual_keys,
            workspace=workspace,
        )

        if workspace and workspace.code == 'select-market':
            saved_approvals = list(workspace.model('IPriceSnapshotApproval').objects.filter(
                snapshot_region__snapshot_product=product).values('is_current'))
        else:
            saved_approvals = _approval_snapshot(snapshot, product_ids={product.id})
        prices = _replace_snapshot_competitors(
            product=product,
            competitor_keys=effective_keys,
            workspace=workspace,
        )
        previous_method = product.pricing_method
        product.pricing_method = (
            IPriceSnapshotProduct.PRICING_METHOD_ANALOG
            if prices
            else IPriceSnapshotProduct.PRICING_METHOD_EXCLUSIVE
        )
        product.competitor_count = len(prices)
        product.competitor_rrp_min = decimal_min(prices)
        product.competitor_rrp_max = decimal_max(prices)
        product.competitor_rrp_median = decimal_median(prices)
        (
            product.current_vs_competitor_amount,
            product.current_vs_competitor_percent,
        ) = calculate_deviation(
            current_value=product.current_retail_median,
            reference_value=product.competitor_rrp_median,
        )
        product.error_codes = [
            code for code in (product.error_codes or [])
            if code != "NO_VALID_COMPETITOR_PRICES"
        ]
        product.warning_codes = [
            code for code in (product.warning_codes or [])
            if code != "NO_VALID_COMPETITOR_PRICES"
        ]
        if effective_keys and not prices:
            product.warning_codes.append("NO_VALID_COMPETITOR_PRICES")
        product.save(update_fields=(
            "pricing_method", "competitor_count", "competitor_rrp_min",
            "competitor_rrp_max", "competitor_rrp_median",
            "current_vs_competitor_amount", "current_vs_competitor_percent",
            "warning_codes", "error_codes",
        ))

        if workspace and workspace.code == 'select-market':
            from select_market.iprice_regional_calculation import build_regions
            from datasets.services.iprice_snapshot_approval import refresh_iprice_product_approval_summary
            build_regions(snapshot=snapshot, snapshot_product_ids={product.id}, input_overrides={})
            workspace.model('IPriceSnapshotApproval').objects.filter(
                snapshot_region__snapshot_product=product, is_current=True).update(is_current=False)
            refresh_iprice_product_approval_summary(product.id, workspace=workspace)
        else:
            original_status = snapshot.status
            snapshot.status = IPriceSnapshot.STATUS_BUILDING
            snapshot.save(update_fields=("status",))
            build_iprice_snapshot_regions(
                snapshot=snapshot,
                snapshot_product_ids={product.id},
            )
            if saved_approvals:
                _restore_approvals(
                    snapshot,
                    saved_approvals,
                    invalidate_current=True,
                )
            snapshot.status = original_status
            snapshot.save(update_fields=("status",))

        if workspace:
            snapshot.parameters = {**snapshot.parameters, 'edit_revision': snapshot.parameters.get('edit_revision', 0) + 1}
            snapshot.save(update_fields=['parameters'])

    return {
        "snapshot_id": snapshot.id,
        "product_id": product.id,
        "base_product_key": product.base_product_key,
        "selection_mode": selection_mode,
        "competitor_product_keys": sorted(target_keys),
        "effective_competitor_count": len(effective_keys),
        "priced_competitor_count": len(prices),
        "previous_pricing_method": previous_method,
        "pricing_method": product.pricing_method,
        "approvals_invalidated": sum(1 for row in saved_approvals if row["is_current"]),
    }
