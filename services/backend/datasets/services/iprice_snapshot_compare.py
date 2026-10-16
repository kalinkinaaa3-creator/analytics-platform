from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable

from django.db.models import Prefetch, QuerySet
from django.core.paginator import Paginator

from datasets.models import (
    IPriceSnapshot,
    IPriceSnapshotApproval,
    IPriceSnapshotProduct,
    IPriceSnapshotRegion,
)


MODE_PRODUCTS = "products"
MODE_REGIONS = "regions"

CHANGE_ALL = "all"
CHANGE_ADDED = "added"
CHANGE_REMOVED = "removed"
CHANGE_CHANGED = "changed"
CHANGE_UNCHANGED = "unchanged"
CHANGE_PRICE_INCREASED = "price_increased"
CHANGE_PRICE_DECREASED = "price_decreased"
CHANGE_FINAL_RRP_INCREASED = "final_rrp_increased"
CHANGE_FINAL_RRP_DECREASED = "final_rrp_decreased"
CHANGE_NEW_ERROR = "new_error"
CHANGE_RESOLVED_ERROR = "resolved_error"
CHANGE_STATUS_CHANGED = "status_changed"

ALLOWED_CHANGE_TYPES = {
    CHANGE_ALL,
    CHANGE_ADDED,
    CHANGE_REMOVED,
    CHANGE_CHANGED,
    CHANGE_UNCHANGED,
    CHANGE_PRICE_INCREASED,
    CHANGE_PRICE_DECREASED,
    CHANGE_FINAL_RRP_INCREASED,
    CHANGE_FINAL_RRP_DECREASED,
    CHANGE_NEW_ERROR,
    CHANGE_RESOLVED_ERROR,
    CHANGE_STATUS_CHANGED,
}


PRODUCT_COMPARE_FIELDS = (
    "code_1c",
    "nom",
    "nom_hier_code",
    "nom_hier",
    "nom_view",
    "nom_category",
    "nom_group",
    "category",
    "subcategory",
    "subcategory_type",
    "color",
    "material",
    "modification",
    "item_type",
    "pricing_method",
    "base_analog_median",
    "base_exclusive_median",
    "minimum_margin_median",
    "discount_distr_median",
    "discount_distr_1_median",
    "discount_small_median",
    "discount_medium_median",
    "discount_large_median",
    "effective_distr_median",
    "effective_distr_1_median",
    "effective_small_median",
    "effective_medium_median",
    "effective_large_median",
    "competitor_count",
    "competitor_rrp_min",
    "competitor_rrp_max",
    "competitor_rrp_median",
    "current_retail_min",
    "current_retail_max",
    "current_retail_median",
    "current_vs_competitor_amount",
    "current_vs_competitor_percent",
    "effective_approved_rrp_median",
    "current_vs_approved_amount",
    "calculation_status",
    "warning_codes",
    "error_codes",
)

PRODUCT_PRICE_FIELDS = (
    "current_retail_median",
)

PRODUCT_FINAL_RRP_FIELDS = (
    "effective_approved_rrp_median",
)

REGION_COMPARE_FIELDS = (
    "sale_region",
    "departure",
    "product_cost_month",
    "nomenclature_price_date",
    "current_retail",
    "current_distr",
    "current_distr_1",
    "current_small",
    "current_medium",
    "current_large",
    "product_cost",
    "transport_cost",
    "quantity_eurotruck",
    "logistics_unit",
    "cost_with_logistics",
    "regional_competitor_count",
    "regional_competitor_rrp_min",
    "regional_competitor_rrp_max",
    "regional_competitor_rrp_median",
    "base_analog",
    "base_exclusive",
    "minimum_margin",
    "discount_distr",
    "discount_distr_1",
    "discount_small",
    "discount_medium",
    "discount_large",
    "preliminary_rrp",
    "minimum_price",
    "calculated_rrp",
    "default_approved_rrp",
    "calculated_distr",
    "calculated_distr_1",
    "calculated_small",
    "calculated_medium",
    "calculated_large",
    "margin_current",
    "margin_calculated",
    "current_vs_calculated_percent",
    "calculation_status",
    "warning_codes",
    "error_codes",
)

REGION_PRICE_FIELDS = (
    "current_retail",
)

REGION_FINAL_RRP_FIELDS = (
    "effective_approved_rrp",
)

PRODUCT_FILTER_FIELDS = {
    "base_product_key",
    "code_1c",
    "nom",
    "pricing_method",
    "calculation_status",
    "assortment_matrix_status",
    "our_offer",
    "nom_hier_code",
    "nom_hier",
    "nom_view",
    "nom_category",
    "nom_group",
    "category",
    "subcategory",
    "subcategory_type",
    "color",
    "material",
    "modification",
}

REGION_FILTER_FIELDS = PRODUCT_FILTER_FIELDS | {
    "sale_region",
    "departure",
}


class IPriceSnapshotCompareError(ValueError):
    """Business validation error for snapshot comparison."""


@dataclass(frozen=True)
class ComparePage:
    page: int
    page_size: int
    count: int
    total_pages: int
    has_next: bool
    has_previous: bool
    results: list[dict[str, Any]]


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().casefold()


def _normalize_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple, set)):
        return ()

    normalized = {
        str(item).strip()
        for item in value
        if item is not None and str(item).strip()
    }

    return tuple(sorted(normalized, key=str.casefold))


def _normalize_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return value

    if isinstance(value, (list, tuple, set)):
        return _normalize_list(value)

    if isinstance(value, str):
        return value.strip()

    return value


def _values_equal(left: Any, right: Any) -> bool:
    return _normalize_value(left) == _normalize_value(right)


def _decimal_direction(
    base_value: Any,
    comparison_value: Any,
) -> int:
    if base_value is None or comparison_value is None:
        return 0

    try:
        base_decimal = Decimal(str(base_value))
        comparison_decimal = Decimal(str(comparison_value))
    except Exception:
        return 0

    if comparison_decimal > base_decimal:
        return 1

    if comparison_decimal < base_decimal:
        return -1

    return 0


def _serialize_snapshot(snapshot: IPriceSnapshot) -> dict[str, Any]:
    return {
        "id": snapshot.id,
        "calculation_date": snapshot.calculation_date,
        "version_number": snapshot.version_number,
        "revision_for_date": snapshot.revision_for_date,
        "display_version": snapshot.display_version,
        "status": snapshot.status,
        "is_current": snapshot.is_current,
        "is_active": snapshot.is_active,
        "created_at": snapshot.created_at,
        "finished_at": snapshot.finished_at,
    }


def _get_snapshot(snapshot_id: int, *, workspace=None) -> IPriceSnapshot:
    IPriceSnapshot = workspace.model('IPriceSnapshot') if workspace else globals()['IPriceSnapshot']
    try:
        snapshot = IPriceSnapshot.objects.get(pk=snapshot_id)
    except IPriceSnapshot.DoesNotExist as exc:
        raise IPriceSnapshotCompareError(
            f"Snapshot {snapshot_id} not found."
        ) from exc

    if snapshot.status != IPriceSnapshot.STATUS_SUCCESS:
        raise IPriceSnapshotCompareError(
            f"Snapshot {snapshot.display_version} is not successful."
        )

    return snapshot


def _validate_snapshots(
    base_snapshot_id: int,
    comparison_snapshot_id: int,
    *, workspace=None,
) -> tuple[IPriceSnapshot, IPriceSnapshot]:
    if base_snapshot_id == comparison_snapshot_id:
        raise IPriceSnapshotCompareError(
            "Base and comparison snapshots must be different."
        )

    return (
        _get_snapshot(base_snapshot_id, workspace=workspace),
        _get_snapshot(comparison_snapshot_id, workspace=workspace),
    )


def _current_approval(region: IPriceSnapshotRegion):
    approvals = getattr(region, "current_approvals", None) or []
    return approvals[0] if approvals else None


def _effective_region_values(
    region: IPriceSnapshotRegion,
) -> dict[str, Any]:
    approval = _current_approval(region)

    return {
        "current_approval": (
            {
                "id": approval.id,
                "revision": approval.revision,
                "approved_rrp": approval.approved_rrp,
                "approved_distr": getattr(approval, 'approved_distr', None),
                "approved_distr_1": getattr(approval, 'approved_distr_1', None),
                "approved_small": approval.approved_small,
                "approved_medium": approval.approved_medium,
                "approved_large": approval.approved_large,
                "approved_at": approval.approved_at,
                "comment": approval.comment,
            }
            if approval is not None
            else None
        ),
        "effective_approved_rrp": (
            approval.approved_rrp
            if approval is not None
            else (
                region.default_approved_rrp
                if region.default_approved_rrp is not None
                else region.calculated_rrp
            )
        ),
        "effective_distr": (
            getattr(approval, 'approved_distr', None)
            if approval is not None
            else getattr(region, 'calculated_distr', None)
        ),
        "effective_distr_1": (
            getattr(approval, 'approved_distr_1', None)
            if approval is not None
            else getattr(region, 'calculated_distr_1', None)
        ),
        "effective_small": (
            approval.approved_small
            if approval is not None
            else region.calculated_small
        ),
        "effective_medium": (
            approval.approved_medium
            if approval is not None
            else region.calculated_medium
        ),
        "effective_large": (
            approval.approved_large
            if approval is not None
            else region.calculated_large
        ),
    }


def _serialize_product(
    product: IPriceSnapshotProduct,
) -> dict[str, Any]:
    details = product.calculation_details or {}
    return {
        "id": product.id,
        "snapshot_id": product.snapshot_id,
        "base_product_key": product.base_product_key,
        "code_1c": product.code_1c,
        "nom": product.nom,
        "nom_hier_code": product.nom_hier_code,
        "nom_hier": product.nom_hier,
        "nom_view": product.nom_view,
        "nom_category": product.nom_category,
        "nom_group": product.nom_group,
        "assortment_matrix_status": (
            product.assortment_matrix_status
        ),
        "our_offer": product.our_offer,
        "category": product.category,
        "subcategory": product.subcategory,
        "subcategory_type": product.subcategory_type,
        "color": product.color,
        "material": product.material,
        "modification": product.modification,
        "image": product.image,
        "url": product.url,
        "item_type": product.item_type,
        "pricing_method": product.pricing_method,
        **{
            field_name: details.get(field_name)
            for field_name in (
                "base_analog_median",
                "base_exclusive_median",
                "minimum_margin_median",
                "discount_distr_median",
                "discount_distr_1_median",
                "discount_small_median",
                "discount_medium_median",
                "discount_large_median",
                "effective_distr_median",
                "effective_distr_1_median",
                "effective_small_median",
                "effective_medium_median",
                "effective_large_median",
            )
        },
        "competitor_count": product.competitor_count,
        "competitor_rrp_min": product.competitor_rrp_min,
        "competitor_rrp_max": product.competitor_rrp_max,
        "competitor_rrp_median": product.competitor_rrp_median,
        "current_retail_min": product.current_retail_min,
        "current_retail_max": product.current_retail_max,
        "current_retail_median": product.current_retail_median,
        "current_vs_competitor_amount": (
            product.current_vs_competitor_amount
        ),
        "current_vs_competitor_percent": (
            product.current_vs_competitor_percent
        ),
        "effective_approved_rrp_median": (
            product.effective_approved_rrp_median
        ),
        "current_vs_approved_amount": (
            product.current_vs_approved_amount
        ),
        "calculation_status": product.calculation_status,
        "warning_codes": product.warning_codes or [],
        "error_codes": product.error_codes or [],
    }


def _serialize_region(
    region: IPriceSnapshotRegion,
) -> dict[str, Any]:
    product = region.snapshot_product

    result = {
        "id": region.id,
        "snapshot_product_id": region.snapshot_product_id,
        "snapshot_id": product.snapshot_id,
        "base_product_key": product.base_product_key,
        "code_1c": product.code_1c,
        "nom": product.nom,
        "nom_hier_code": product.nom_hier_code,
        "nom_hier": product.nom_hier,
        "nom_view": product.nom_view,
        "nom_category": product.nom_category,
        "nom_group": product.nom_group,
        "assortment_matrix_status": (
            product.assortment_matrix_status
        ),
        "our_offer": product.our_offer,
        "category": product.category,
        "subcategory": product.subcategory,
        "subcategory_type": product.subcategory_type,
        "color": product.color,
        "material": product.material,
        "modification": product.modification,
        "image": product.image,
        "item_type": product.item_type,
        "pricing_method": product.pricing_method,
    }

    for field_name in REGION_COMPARE_FIELDS:
        result[field_name] = getattr(region, field_name, None)

    result.update(_effective_region_values(region))
    return result


def _product_queryset(snapshot: IPriceSnapshot) -> QuerySet:
    from datasets.services.iprice_snapshot_builder import _snapshot_workspace
    workspace = _snapshot_workspace(snapshot)
    IPriceSnapshotProduct = workspace.model('IPriceSnapshotProduct') if workspace else globals()['IPriceSnapshotProduct']
    return (
        IPriceSnapshotProduct.objects
        .filter(snapshot=snapshot)
        .order_by("base_product_key")
    )


def _region_queryset(snapshot: IPriceSnapshot) -> QuerySet:
    from datasets.services.iprice_snapshot_builder import _snapshot_workspace
    workspace = _snapshot_workspace(snapshot)
    IPriceSnapshotApproval = workspace.model('IPriceSnapshotApproval') if workspace else globals()['IPriceSnapshotApproval']
    IPriceSnapshotRegion = workspace.model('IPriceSnapshotRegion') if workspace else globals()['IPriceSnapshotRegion']
    current_approval_queryset = (
        IPriceSnapshotApproval.objects
        .filter(is_current=True)
        .order_by("-revision", "-id")
    )

    return (
        IPriceSnapshotRegion.objects
        .filter(snapshot_product__snapshot=snapshot)
        .select_related("snapshot_product")
        .prefetch_related(
            Prefetch(
                "approvals",
                queryset=current_approval_queryset,
                to_attr="current_approvals",
            )
        )
        .order_by(
            "snapshot_product__base_product_key",
            "sale_region",
            "historical_variant" if workspace else "departure",
        )
    )


def _build_product_index(
    snapshot: IPriceSnapshot,
) -> dict[int, dict[str, Any]]:
    return {
        (product.code_1c if product._meta.app_label == 'select_market' else product.base_product_key): _serialize_product(product)
        for product in _product_queryset(snapshot)
    }


def _build_region_index(
    snapshot: IPriceSnapshot,
) -> dict[tuple[int, str, str], dict[str, Any]]:
    index = {}

    for region in _region_queryset(snapshot):
        key = (
            region.snapshot_product.code_1c if region._meta.app_label == 'select_market' else region.snapshot_product.base_product_key,
            region.sale_region,
            region.historical_variant if region._meta.app_label == 'select_market' else region.departure,
        )
        index[key] = _serialize_region(region)

    return index


def _changed_fields(
    base: dict[str, Any],
    comparison: dict[str, Any],
    fields: Iterable[str],
) -> list[str]:
    return [
        field_name
        for field_name in fields
        if not _values_equal(
            base.get(field_name),
            comparison.get(field_name),
        )
    ]


def _issue_flags(
    base: dict[str, Any] | None,
    comparison: dict[str, Any] | None,
) -> dict[str, bool]:
    base_errors = set(_normalize_list((base or {}).get("error_codes")))
    comparison_errors = set(
        _normalize_list((comparison or {}).get("error_codes"))
    )

    return {
        "has_new_error": bool(comparison_errors - base_errors),
        "has_resolved_error": bool(base_errors - comparison_errors),
    }


def _price_direction(
    base: dict[str, Any] | None,
    comparison: dict[str, Any] | None,
    price_fields: Iterable[str],
) -> int:
    if base is None or comparison is None:
        return 0

    for field_name in price_fields:
        direction = _decimal_direction(
            base.get(field_name),
            comparison.get(field_name),
        )
        if direction:
            return direction

    return 0


def _build_row(
    *,
    key: Any,
    base: dict[str, Any] | None,
    comparison: dict[str, Any] | None,
    compare_fields: Iterable[str],
    price_fields: Iterable[str],
    final_rrp_fields: Iterable[str],
) -> dict[str, Any]:
    if base is None:
        changed_fields = list(compare_fields)
        row_change_type = CHANGE_ADDED
    elif comparison is None:
        changed_fields = list(compare_fields)
        row_change_type = CHANGE_REMOVED
    else:
        changed_fields = _changed_fields(
            base,
            comparison,
            compare_fields,
        )
        row_change_type = (
            CHANGE_CHANGED
            if changed_fields
            else CHANGE_UNCHANGED
        )

    issue_flags = _issue_flags(base, comparison)
    price_direction = _price_direction(
        base,
        comparison,
        price_fields,
    )
    final_rrp_direction = _price_direction(
        base,
        comparison,
        final_rrp_fields,
    )

    status_changed = bool(
        base is not None
        and comparison is not None
        and not _values_equal(
            base.get("calculation_status"),
            comparison.get("calculation_status"),
        )
    )

    return {
        "key": key,
        "change_type": row_change_type,
        "changed_fields": changed_fields,
        "price_direction": price_direction,
        "final_rrp_direction": final_rrp_direction,
        "status_changed": status_changed,
        **issue_flags,
        "base": base,
        "comparison": comparison,
    }


def _compare_indexes(
    *,
    base_index: dict[Any, dict[str, Any]],
    comparison_index: dict[Any, dict[str, Any]],
    compare_fields: Iterable[str],
    price_fields: Iterable[str],
    final_rrp_fields: Iterable[str],
) -> list[dict[str, Any]]:
    all_keys = sorted(
        set(base_index) | set(comparison_index),
        key=lambda value: str(value).casefold(),
    )

    return [
        _build_row(
            key=key,
            base=base_index.get(key),
            comparison=comparison_index.get(key),
            compare_fields=compare_fields,
            price_fields=price_fields,
            final_rrp_fields=final_rrp_fields,
        )
        for key in all_keys
    ]


def _row_matches_search(row: dict[str, Any], search: str) -> bool:
    normalized_search = _normalize_text(search)
    if not normalized_search:
        return True

    values = []
    for side_name in ("comparison", "base"):
        side = row.get(side_name) or {}
        values.extend(
            [
                side.get("code_1c"),
                side.get("nom"),
            ]
        )

    searchable_text = " ".join(
        str(value)
        for value in values
        if value is not None
    ).casefold()

    return normalized_search in searchable_text


def _row_matches_filters(
    row: dict[str, Any],
    filters: dict[str, list[str]] | None,
    allowed_fields: set[str],
) -> bool:
    if not filters:
        return True

    preferred_side = row.get("comparison") or row.get("base") or {}

    for field_name, raw_values in filters.items():
        if field_name not in allowed_fields:
            continue

        values = {
            _normalize_text(value)
            for value in (raw_values or [])
            if _normalize_text(value)
        }

        if not values:
            continue

        field_value = _normalize_text(preferred_side.get(field_name))
        if field_value not in values:
            return False

    return True


def _row_matches_change_type(
    row: dict[str, Any],
    change_type: str,
) -> bool:
    if change_type == CHANGE_ALL:
        return True

    if change_type in {
        CHANGE_ADDED,
        CHANGE_REMOVED,
        CHANGE_CHANGED,
        CHANGE_UNCHANGED,
    }:
        return row["change_type"] == change_type

    if change_type == CHANGE_PRICE_INCREASED:
        return row["price_direction"] > 0

    if change_type == CHANGE_PRICE_DECREASED:
        return row["price_direction"] < 0

    if change_type == CHANGE_FINAL_RRP_INCREASED:
        return row["final_rrp_direction"] > 0

    if change_type == CHANGE_FINAL_RRP_DECREASED:
        return row["final_rrp_direction"] < 0

    if change_type == CHANGE_NEW_ERROR:
        return row["has_new_error"]

    if change_type == CHANGE_RESOLVED_ERROR:
        return row["has_resolved_error"]

    if change_type == CHANGE_STATUS_CHANGED:
        return row["status_changed"]

    return True


def _filter_rows(
    *,
    rows: list[dict[str, Any]],
    search: str,
    filters: dict[str, list[str]] | None,
    change_type: str,
    allowed_fields: set[str],
) -> list[dict[str, Any]]:
    normalized_change_type = str(change_type or CHANGE_ALL).strip()
    if normalized_change_type not in ALLOWED_CHANGE_TYPES:
        raise IPriceSnapshotCompareError(
            f"Unsupported change_type: {normalized_change_type}."
        )

    return [
        row
        for row in rows
        if _row_matches_change_type(row, normalized_change_type)
        and _row_matches_search(row, search)
        and _row_matches_filters(row, filters, allowed_fields)
    ]


def _build_summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(rows),
        "added": sum(
            row["change_type"] == CHANGE_ADDED
            for row in rows
        ),
        "removed": sum(
            row["change_type"] == CHANGE_REMOVED
            for row in rows
        ),
        "changed": sum(
            row["change_type"] == CHANGE_CHANGED
            for row in rows
        ),
        "unchanged": sum(
            row["change_type"] == CHANGE_UNCHANGED
            for row in rows
        ),
        "price_increased": sum(
            row["price_direction"] > 0
            for row in rows
        ),
        "price_decreased": sum(
            row["price_direction"] < 0
            for row in rows
        ),
        "final_rrp_increased": sum(
            row["final_rrp_direction"] > 0
            for row in rows
        ),
        "final_rrp_decreased": sum(
            row["final_rrp_direction"] < 0
            for row in rows
        ),
        "status_changed": sum(
            row["status_changed"]
            for row in rows
        ),
        "new_errors": sum(
            row["has_new_error"]
            for row in rows
        ),
        "resolved_errors": sum(
            row["has_resolved_error"]
            for row in rows
        ),
    }


def _paginate(
    rows: list[dict[str, Any]],
    *,
    page: int,
    page_size: int,
) -> ComparePage:
    paginator = Paginator(rows, page_size)
    page_obj = paginator.get_page(page)

    return ComparePage(
        page=page_obj.number,
        page_size=page_size,
        count=paginator.count,
        total_pages=paginator.num_pages,
        has_next=page_obj.has_next(),
        has_previous=page_obj.has_previous(),
        results=list(page_obj.object_list),
    )


def compare_iprice_snapshots(
    *,
    base_snapshot_id: int,
    comparison_snapshot_id: int,
    mode: str = MODE_PRODUCTS,
    page: int = 1,
    page_size: int = 50,
    search: str = "",
    filters: dict[str, list[str]] | None = None,
    change_type: str = CHANGE_ALL,
    workspace=None,
) -> dict[str, Any]:
    """
    Compare two successful iPrice snapshots by stable business keys.

    Product key:
        base_product_key

    Region key:
        base_product_key + sale_region + departure
    """

    normalized_mode = str(mode or MODE_PRODUCTS).strip().casefold()
    if normalized_mode not in {MODE_PRODUCTS, MODE_REGIONS}:
        raise IPriceSnapshotCompareError(
            "mode must be 'products' or 'regions'."
        )

    base_snapshot, comparison_snapshot = _validate_snapshots(
        base_snapshot_id,
        comparison_snapshot_id,
        workspace=workspace,
    )

    if normalized_mode == MODE_PRODUCTS:
        rows = _compare_indexes(
            base_index=_build_product_index(base_snapshot),
            comparison_index=_build_product_index(comparison_snapshot),
            compare_fields=PRODUCT_COMPARE_FIELDS,
            price_fields=PRODUCT_PRICE_FIELDS,
            final_rrp_fields=PRODUCT_FINAL_RRP_FIELDS,
        )
        allowed_filter_fields = PRODUCT_FILTER_FIELDS
    else:
        rows = _compare_indexes(
            base_index=_build_region_index(base_snapshot),
            comparison_index=_build_region_index(comparison_snapshot),
            compare_fields=(
                *REGION_COMPARE_FIELDS,
                "pricing_method",
                "effective_approved_rrp",
                "effective_distr",
                "effective_distr_1",
                "effective_small",
                "effective_medium",
                "effective_large",
            ),
            price_fields=REGION_PRICE_FIELDS,
            final_rrp_fields=REGION_FINAL_RRP_FIELDS,
        )
        allowed_filter_fields = REGION_FILTER_FIELDS

    summary = _build_summary(rows)

    if workspace and workspace.code == 'select-market':
        from select_market.iprice_filters import PRODUCT_FILTERS, filter_products
        source_filters = {key: value for key, value in (filters or {}).items() if key in PRODUCT_FILTERS}
        if any(source_filters.values()):
            products = workspace.model('IPriceSnapshotProduct').objects.filter(snapshot_id__in=[base_snapshot.pk, comparison_snapshot.pk])
            selected_ids = set(filter_products(products, source_filters).values_list('pk', flat=True))
            product_key = 'snapshot_product_id' if normalized_mode == MODE_REGIONS else 'id'
            rows = [row for row in rows if (row.get('comparison') or row.get('base') or {}).get(product_key) in selected_ids]
        filters = {key: value for key, value in (filters or {}).items() if key not in PRODUCT_FILTERS}

    filtered_rows = _filter_rows(
        rows=rows,
        search=search,
        filters=filters,
        change_type=change_type,
        allowed_fields=allowed_filter_fields,
    )

    page_result = _paginate(
        filtered_rows,
        page=page,
        page_size=page_size,
    )

    return {
        "mode": normalized_mode,
        "base_snapshot": _serialize_snapshot(base_snapshot),
        "comparison_snapshot": _serialize_snapshot(
            comparison_snapshot
        ),
        "summary": summary,
        "filtered_count": page_result.count,
        "page": page_result.page,
        "page_size": page_result.page_size,
        "total_pages": page_result.total_pages,
        "has_next": page_result.has_next,
        "has_previous": page_result.has_previous,
        "results": page_result.results,
    }




COMPARE_PRODUCT_FILTER_ORDER = (
    "code_1c",
    "nom",
    "base_product_key",
    "pricing_method",
    "calculation_status",
    "assortment_matrix_status",
    "our_offer",

    "nom_hier_code",
    "nom_hier",
    "nom_view",
    "nom_category",
    "nom_group",

    "category",
    "subcategory",
    "subcategory_type",

    "color",
    "material",
    "modification",
)


COMPARE_REGION_FILTER_ORDER = (
    "code_1c",
    "nom",
    "base_product_key",
    "pricing_method",
    "calculation_status",
    "assortment_matrix_status",
    "our_offer",

    "sale_region",
    "departure",

    "nom_hier_code",
    "nom_hier",
    "nom_view",
    "nom_category",
    "nom_group",

    "category",
    "subcategory",
    "subcategory_type",

    "color",
    "material",
    "modification",
)


def _normalize_compare_filters(
    *,
    filters: dict | None,
    allowed_fields: set[str],
) -> dict[str, list[str]]:
    if not isinstance(
        filters,
        dict,
    ):
        return {}

    result = {}

    for field_name in allowed_fields:
        raw_values = filters.get(
            field_name,
            [],
        )

        if isinstance(
            raw_values,
            (
                str,
                bytes,
            ),
        ):
            raw_values = [raw_values]

        if not isinstance(
            raw_values,
            (
                list,
                tuple,
                set,
            ),
        ):
            continue

        values = []
        seen = set()

        for raw_value in raw_values:
            value = str(
                raw_value or ""
            ).strip()

            if not value:
                continue

            value_key = value.casefold()

            if value_key in seen:
                continue

            seen.add(value_key)
            values.append(value)

        if values:
            result[field_name] = values

    return result


def _compare_row_filter_value(
    row: dict[str, Any],
    field_name: str,
):
    preferred_side = (
        row.get("comparison")
        or row.get("base")
        or {}
    )

    return preferred_side.get(
        field_name
    )


def _compare_row_matches_other_filters(
    *,
    row: dict[str, Any],
    filters: dict[str, list[str]],
    excluded_filter: str,
) -> bool:
    for field_name, raw_values in (
        filters.items()
    ):
        if field_name == excluded_filter:
            continue

        allowed_values = {
            _normalize_text(value)
            for value in raw_values
            if _normalize_text(value)
        }

        if not allowed_values:
            continue

        row_value = _normalize_text(
            _compare_row_filter_value(
                row,
                field_name,
            )
        )

        if row_value not in allowed_values:
            return False

    return True


def _build_compare_filter_options(
    *,
    rows: list[dict[str, Any]],
    filters: dict[str, list[str]],
    filter_name: str,
) -> list[dict[str, Any]]:
    counts = {}
    labels = {}

    for row in rows:
        if not (
            _compare_row_matches_other_filters(
                row=row,
                filters=filters,
                excluded_filter=(
                    filter_name
                ),
            )
        ):
            continue

        raw_value = (
            _compare_row_filter_value(
                row,
                filter_name,
            )
        )

        if (
            raw_value is None
            or raw_value == ""
        ):
            continue

        value = str(
            raw_value
        ).strip()

        if not value:
            continue

        value_key = value.casefold()

        counts[value_key] = (
            counts.get(
                value_key,
                0,
            )
            + 1
        )

        labels.setdefault(
            value_key,
            value,
        )

    return [
        {
            "value": labels[value_key],
            "label": labels[value_key],
            "count": counts[value_key],
        }
        for value_key in sorted(
            counts,
            key=lambda key: (
                labels[key].casefold()
            ),
        )
    ]


def build_iprice_snapshot_compare_filters(
    *,
    base_snapshot_id: int,
    comparison_snapshot_id: int,
    mode: str = MODE_PRODUCTS,
    filters: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    normalized_mode = str(
        mode or MODE_PRODUCTS
    ).strip().casefold()

    if normalized_mode not in {
        MODE_PRODUCTS,
        MODE_REGIONS,
    }:
        raise IPriceSnapshotCompareError(
            (
                "mode must be "
                "'products' or 'regions'."
            )
        )

    base_snapshot, comparison_snapshot = (
        _validate_snapshots(
            base_snapshot_id,
            comparison_snapshot_id,
        )
    )

    if normalized_mode == MODE_PRODUCTS:
        rows = _compare_indexes(
            base_index=(
                _build_product_index(
                    base_snapshot
                )
            ),
            comparison_index=(
                _build_product_index(
                    comparison_snapshot
                )
            ),
            compare_fields=(
                PRODUCT_COMPARE_FIELDS
            ),
            price_fields=(
                PRODUCT_PRICE_FIELDS
            ),
            final_rrp_fields=(
                PRODUCT_FINAL_RRP_FIELDS
            ),
        )

        allowed_fields = (
            PRODUCT_FILTER_FIELDS
        )

        filter_order = (
            COMPARE_PRODUCT_FILTER_ORDER
        )

    else:
        rows = _compare_indexes(
            base_index=(
                _build_region_index(
                    base_snapshot
                )
            ),
            comparison_index=(
                _build_region_index(
                    comparison_snapshot
                )
            ),
            compare_fields=(
                *REGION_COMPARE_FIELDS,
                "pricing_method",
                "effective_approved_rrp",
                "effective_distr",
                "effective_distr_1",
                "effective_small",
                "effective_medium",
                "effective_large",
            ),
            price_fields=(
                REGION_PRICE_FIELDS
            ),
            final_rrp_fields=(
                REGION_FINAL_RRP_FIELDS
            ),
        )

        allowed_fields = (
            REGION_FILTER_FIELDS
        )

        filter_order = (
            COMPARE_REGION_FILTER_ORDER
        )

    normalized_filters = (
        _normalize_compare_filters(
            filters=filters,
            allowed_fields=(
                allowed_fields
            ),
        )
    )

    options = {}

    for filter_name in filter_order:
        options[filter_name] = (
            _build_compare_filter_options(
                rows=rows,
                filters=normalized_filters,
                filter_name=filter_name,
            )
        )

    return {
        "mode": normalized_mode,

        "base_snapshot": (
            _serialize_snapshot(
                base_snapshot
            )
        ),

        "comparison_snapshot": (
            _serialize_snapshot(
                comparison_snapshot
            )
        ),

        "selected": (
            normalized_filters
        ),

        "options": options,
    }
