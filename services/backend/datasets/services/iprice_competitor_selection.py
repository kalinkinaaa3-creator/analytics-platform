from __future__ import annotations

from decimal import Decimal

from django.db import transaction

from datasets.models import (
    AnalyticsProductClassificationApplication,
    AnalyticsProductMatchCandidate,
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
from datasets.services.parsers.product_match_loader import (
    build_competitor_url_groups,
    get_prefixes_by_source,
)


class IPriceCompetitorSelectionError(ValueError):
    pass


def ensure_selection_editable(snapshot: IPriceSnapshot) -> None:
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


def _automatic_keys(base_product_key: int) -> set[int]:
    application = AnalyticsProductClassificationApplication.objects.order_by(
        "-date_add", "-id"
    ).first()
    if application is None:
        return set()
    eligible_keys = set(
        AnalyticsProductMatchCandidate.objects.filter(
            application=application,
            product_key_base=base_product_key,
            is_eligible=True,
        ).exclude(competitor_source="base").values_list(
            "product_key_competitor", flat=True
        )
    )
    groups, group_by_product = build_competitor_url_groups(
        prefixes_by_source=get_prefixes_by_source(),
    )
    result = set()
    for competitor_key in eligible_keys:
        group_key = group_by_product.get(competitor_key)
        result.update(groups.get(group_key, {competitor_key}))
        result.add(competitor_key)
    return result


def _effective_keys(base_product_key: int) -> tuple[set[int], dict[int, str]]:
    automatic = _automatic_keys(base_product_key)
    modes = dict(
        IPriceCompetitorSelectionOverride.objects.filter(
            product_key_base=base_product_key,
        ).values_list("product_key_competitor", "selection_mode")
    )
    # Сохраняем совместимость с активными связями, созданными до Product
    # Control. Как только для пары появляется явный override, источником
    # решения становится override/актуальный weighted candidate.
    automatic.update(
        key
        for key in ParserProductMatch.objects.filter(
            product_key_base=base_product_key,
            status=ParserProductMatch.STATUS_ACTIVE,
        ).values_list("product_key_competitor", flat=True)
        if key not in modes
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
    *, base_product_key: int, competitor_keys: set[int], modes: dict[int, str]
) -> None:
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
                if modes.get(key) == IPriceCompetitorSelectionOverride.MODE_INCLUDE
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
    *, product: IPriceSnapshotProduct, competitor_keys: set[int]
) -> list[Decimal]:
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
        )
        region_data = get_competitor_regions(source=url.source, prefix=url.prefix)
        calculation_price = price_data["calculation_price"] if price_data else None
        error_codes = []
        if price_data is None:
            error_codes.append("MISSING_COMPETITOR_PRICE")
        elif calculation_price is None:
            error_codes.append("MISSING_FINAL_PRICE")
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
            calculation_status="error" if error_codes else "success",
            warning_codes=[],
            error_codes=error_codes,
        ))
    IPriceSnapshotCompetitor.objects.filter(snapshot_product=product).delete()
    if rows:
        IPriceSnapshotCompetitor.objects.bulk_create(rows, batch_size=500)
    return prices


def apply_competitor_selection(
    *, snapshot_id: int, product_id: int, competitor_product_keys: list[int],
    selection_mode: str, user=None, reason: str = "",
) -> dict:
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
        snapshot = IPriceSnapshot.objects.select_for_update().get(pk=snapshot_id)
        ensure_selection_editable(snapshot)
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

        effective_keys, modes = _effective_keys(product.base_product_key)
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
        )

        saved_approvals = _approval_snapshot(snapshot, product_ids={product.id})
        prices = _replace_snapshot_competitors(
            product=product,
            competitor_keys=effective_keys,
        )
        previous_method = product.pricing_method
        product.pricing_method = (
            IPriceSnapshotProduct.PRICING_METHOD_ANALOG
            if effective_keys
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
        product.save(update_fields=(
            "pricing_method", "competitor_count", "competitor_rrp_min",
            "competitor_rrp_max", "competitor_rrp_median",
            "current_vs_competitor_amount", "current_vs_competitor_percent",
            "error_codes",
        ))

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
