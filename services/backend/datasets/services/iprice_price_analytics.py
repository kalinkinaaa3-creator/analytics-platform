from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from statistics import median

from django.db import transaction
from django.db.models import DecimalField, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce

from dashboards.models import IPricePriceZoneConfig
from datasets.models import (
    IPriceSnapshot,
    IPriceSnapshotApproval,
    IPriceSnapshotProduct,
    IPriceSnapshotRegion,
)
from datasets.services.iprice_snapshot_filters import (
    apply_iprice_products_search,
    apply_iprice_regions_search,
    filter_iprice_products_queryset,
    filter_iprice_regions_queryset,
)


DEFAULT_BELOW_MARKET_THRESHOLD = Decimal("-0.03")
DEFAULT_ABOVE_MARKET_THRESHOLD = Decimal("0.03")
DEFAULT_CRITICAL_THRESHOLD = Decimal("0.10")

ZONE_BELOW = "below_market"
ZONE_MARKET = "in_market"
ZONE_ABOVE = "above_market"
ZONE_CRITICAL = "critical_above"
ZONE_NO_DATA = "no_market_data"

ZONE_ORDER = (
    ZONE_BELOW,
    ZONE_MARKET,
    ZONE_ABOVE,
    ZONE_CRITICAL,
    ZONE_NO_DATA,
)

ZONE_LABELS = {
    ZONE_BELOW: "Ниже рынка",
    ZONE_MARKET: "В рынке",
    ZONE_ABOVE: "Выше рынка",
    ZONE_CRITICAL: "Критически выше",
    ZONE_NO_DATA: "Нет данных",
}

DRILL_LEVELS = {
    "root": ("category", "Тип номенклатуры iPrice"),
    "category": ("subcategory", "Категория iPrice"),
    "subcategory": ("subcategory_type", "Подкатегория iPrice"),
    "subcategory_type": (None, "Товар"),
}

DRILL_PATH_FIELDS = (
    "category",
    "subcategory",
    "subcategory_type",
)

EMPTY_GROUP_KEY = "__empty__"


class IPricePriceAnalyticsError(ValueError):
    pass


def _as_decimal(value) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _median(values):
    normalized = [
        value
        for value in (_as_decimal(item) for item in values)
        if value is not None
    ]
    return median(normalized) if normalized else None


def _percent(value):
    if value is None:
        return None
    return value * Decimal("100")


def get_active_price_zone_config(*, workspace=None) -> dict:
    IPricePriceZoneConfig = workspace.model('IPricePriceZoneConfig') if workspace else globals()['IPricePriceZoneConfig']
    config = (
        IPricePriceZoneConfig.objects
        .filter(is_active=True)
        .order_by("-created_at", "-id")
        .first()
    )

    if config is None:
        return {
            "id": None,
            "below_market_threshold": DEFAULT_BELOW_MARKET_THRESHOLD,
            "above_market_threshold": DEFAULT_ABOVE_MARKET_THRESHOLD,
            "critical_threshold": DEFAULT_CRITICAL_THRESHOLD,
            "is_default": True,
            "created_at": None,
            "created_by": None,
        }

    return {
        "id": config.id,
        "below_market_threshold": config.below_market_threshold,
        "above_market_threshold": config.above_market_threshold,
        "critical_threshold": config.critical_threshold,
        "is_default": False,
        "created_at": config.created_at,
        "created_by": config.created_by_id,
    }


def serialize_price_zone_config(config: dict) -> dict:
    return {
        "id": config["id"],
        "below_market_percent": _percent(
            config["below_market_threshold"]
        ),
        "above_market_percent": _percent(
            config["above_market_threshold"]
        ),
        "critical_percent": _percent(config["critical_threshold"]),
        "is_default": config["is_default"],
        "created_at": config["created_at"],
        "created_by": config["created_by"],
    }


@transaction.atomic
def activate_price_zone_config(
    *,
    below_market_threshold: Decimal,
    above_market_threshold: Decimal,
    critical_threshold: Decimal,
    user,
    workspace=None,
) -> tuple[dict, bool]:
    IPricePriceZoneConfig = workspace.model('IPricePriceZoneConfig') if workspace else globals()['IPricePriceZoneConfig']
    if workspace:
        from datasets.services.iprice_snapshot_builder import _lock_snapshot_workspace
        _lock_snapshot_workspace(workspace)
    active = (
        IPricePriceZoneConfig.objects
        .select_for_update()
        .filter(is_active=True)
        .order_by("-created_at", "-id")
        .first()
    )

    current = get_active_price_zone_config(workspace=workspace) if active is None else {
        "id": active.id,
        "below_market_threshold": active.below_market_threshold,
        "above_market_threshold": active.above_market_threshold,
        "critical_threshold": active.critical_threshold,
        "is_default": False,
        "created_at": active.created_at,
        "created_by": active.created_by_id,
    }

    values = (
        below_market_threshold,
        above_market_threshold,
        critical_threshold,
    )
    current_values = (
        current["below_market_threshold"],
        current["above_market_threshold"],
        current["critical_threshold"],
    )

    if values == current_values:
        return current, False

    if active is not None:
        active.is_active = False
        active.save(update_fields=("is_active",))

    created = IPricePriceZoneConfig.objects.create(
        below_market_threshold=below_market_threshold,
        above_market_threshold=above_market_threshold,
        critical_threshold=critical_threshold,
        is_active=True,
        created_by=user if getattr(user, "is_authenticated", False) else None,
    )

    return {
        "id": created.id,
        "below_market_threshold": created.below_market_threshold,
        "above_market_threshold": created.above_market_threshold,
        "critical_threshold": created.critical_threshold,
        "is_default": False,
        "created_at": created.created_at,
        "created_by": created.created_by_id,
    }, True


def _deviation(final_rrp, market_price):
    final_rrp = _as_decimal(final_rrp)
    market_price = _as_decimal(market_price)
    if final_rrp is None or market_price in (None, Decimal("0")):
        return None
    return (final_rrp - market_price) / market_price


def classify_price_zone(deviation, config):
    if deviation is None:
        return ZONE_NO_DATA
    if deviation < config["below_market_threshold"]:
        return ZONE_BELOW
    if deviation <= config["above_market_threshold"]:
        return ZONE_MARKET
    if deviation <= config["critical_threshold"]:
        return ZONE_ABOVE
    return ZONE_CRITICAL


def _empty_zone_counts():
    return {key: 0 for key in ZONE_ORDER}


def _summarize_rows(rows, config):
    zone_counts = _empty_zone_counts()
    deviations = []
    final_prices = []
    market_prices = []
    retail_prices = []
    errors = 0
    competitor_count = 0

    for row in rows:
        deviation = row["deviation"]
        zone_counts[classify_price_zone(deviation, config)] += 1
        if deviation is not None:
            deviations.append(deviation)
        if row["final_rrp"] is not None:
            final_prices.append(row["final_rrp"])
        if row["market_price"] is not None:
            market_prices.append(row["market_price"])
        if row.get("retail_price") is not None:
            retail_prices.append(row["retail_price"])
        if row["calculation_status"] == IPriceSnapshotProduct.STATUS_ERROR:
            errors += 1
        competitor_count += int(row.get("competitor_count") or 0)

    total = len(rows)
    covered = total - zone_counts[ZONE_NO_DATA]

    median_retail_price = _median(retail_prices)
    median_final_rrp = _median(final_prices)
    return {
        "total_products": total,
        "market_covered": covered,
        "market_coverage_percent": (
            Decimal(covered) / Decimal(total) * Decimal("100")
            if total
            else Decimal("0")
        ),
        "calculation_errors": errors,
        "competitor_count": competitor_count,
        "median_final_rrp": median_final_rrp,
        "median_retail_price": median_retail_price,
        "retail_delta": (
            median_retail_price - median_final_rrp
            if median_retail_price is not None and median_final_rrp is not None
            else None
        ),
        "retail_delta_percent": _percent(
            _deviation(median_retail_price, median_final_rrp)
        ),
        "median_market_price": _median(market_prices),
        "median_deviation_percent": _percent(_median(deviations)),
        "final_market_delta": (
            median_final_rrp - _median(market_prices)
            if median_final_rrp is not None and _median(market_prices) is not None
            else None
        ),
        "final_market_delta_percent": _percent(
            _deviation(median_final_rrp, _median(market_prices))
        ),
        "retail_market_delta": (
            median_retail_price - _median(market_prices)
            if median_retail_price is not None and _median(market_prices) is not None
            else None
        ),
        "retail_market_delta_percent": _percent(
            _deviation(median_retail_price, _median(market_prices))
        ),
        "zone_counts": zone_counts,
    }


def _serialize_zones(summary):
    total = summary["total_products"]
    return [
        {
            "key": key,
            "label": ZONE_LABELS[key],
            "count": summary["zone_counts"][key],
            "percent": (
                Decimal(summary["zone_counts"][key])
                / Decimal(total)
                * Decimal("100")
                if total
                else Decimal("0")
            ),
        }
        for key in ZONE_ORDER
    ]


def _validate_drill(level, path):
    if level not in DRILL_LEVELS:
        raise IPricePriceAnalyticsError("Неизвестный уровень детализации")

    normalized_path = {}
    for field in DRILL_PATH_FIELDS:
        value = str((path or {}).get(field) or "").strip()
        if value:
            normalized_path[field] = value

    required_by_level = {
        "root": (),
        "category": ("category",),
        "subcategory": ("category", "subcategory"),
        "subcategory_type": (
            "category",
            "subcategory",
            "subcategory_type",
        ),
    }
    required = required_by_level[level]
    if any(field not in normalized_path for field in required):
        raise IPricePriceAnalyticsError(
            "Путь детализации не соответствует выбранному уровню"
        )

    return {
        field: normalized_path[field]
        for field in required
    }


def _normalize_optional_drill_path(path):
    return {
        field: str((path or {}).get(field) or "").strip()
        for field in DRILL_PATH_FIELDS
        if str((path or {}).get(field) or "").strip()
    }


def _apply_drill_path(queryset, path, prefix=""):
    for field, value in path.items():
        model_field = f"{prefix}{field}"
        if value == EMPTY_GROUP_KEY:
            queryset = queryset.filter(
                Q(**{f"{model_field}__isnull": True})
                | Q(**{model_field: ""})
            )
        else:
            queryset = queryset.filter(**{model_field: value})
    return queryset


def _product_rows(queryset, regional_metrics=None, extra_fields=()):
    values = queryset.values(
        *extra_fields,
        "id",
        "base_product_key",
        "code_1c",
        "nom",
        "image",
        "category",
        "subcategory",
        "subcategory_type",
        "pricing_method",
        "calculation_status",
        "competitor_count",
        "competitor_rrp_median",
        "current_retail_median",
        "effective_approved_rrp_median",
    )

    rows = []
    for item in values:
        metrics = (regional_metrics or {}).get(item["id"], {})
        final_rrp = _as_decimal(
            metrics.get("final_rrp", item["effective_approved_rrp_median"])
        )
        market_price = _as_decimal(
            metrics.get("market_price", item["competitor_rrp_median"])
        )
        retail_price = _as_decimal(
            metrics.get("retail_price", item["current_retail_median"])
        )
        rows.append({
            **item,
            "final_rrp": final_rrp,
            "market_price": market_price,
            "retail_price": retail_price,
            "deviation": _deviation(retail_price, market_price),
            "final_market_delta": (
                final_rrp - market_price
                if final_rrp is not None and market_price is not None
                else None
            ),
            "final_market_delta_percent": _deviation(final_rrp, market_price),
            "retail_market_delta": (
                retail_price - market_price
                if retail_price is not None and market_price is not None
                else None
            ),
            "retail_delta": (
                retail_price - final_rrp
                if retail_price is not None and final_rrp is not None
                else None
            ),
            "retail_delta_percent": _deviation(retail_price, final_rrp),
        })
    return rows


def _with_effective_approved_rrp(queryset):
    IPriceSnapshotApproval = queryset.model._meta.get_field('approvals').related_model
    decimal_output = DecimalField(max_digits=24, decimal_places=8)
    current_approval = (
        IPriceSnapshotApproval.objects
        .filter(snapshot_region_id=OuterRef("pk"), is_current=True)
        .order_by("-revision", "-id")
        .values("approved_rrp")[:1]
    )
    return queryset.annotate(
        effective_approved_rrp=Coalesce(
            Subquery(current_approval, output_field=decimal_output),
            "default_approved_rrp",
            output_field=decimal_output,
        )
    )


def _build_regional_product_metrics(queryset):
    values_by_product = defaultdict(lambda: {
        "retail_price": [],
        "final_rrp": [],
        "market_price": [],
    })
    for item in _with_effective_approved_rrp(queryset).values(
        "snapshot_product_id",
        "current_retail",
        "effective_approved_rrp",
        "regional_competitor_rrp_median",
    ):
        target = values_by_product[item["snapshot_product_id"]]
        target["retail_price"].append(item["current_retail"])
        target["final_rrp"].append(item["effective_approved_rrp"])
        target["market_price"].append(
            item["regional_competitor_rrp_median"]
        )

    return {
        product_id: {
            field: _median(values)
            for field, values in metrics.items()
        }
        for product_id, metrics in values_by_product.items()
    }


def _breadcrumb(path):
    labels = {
        "category": "Тип номенклатуры iPrice",
        "subcategory": "Категория iPrice",
        "subcategory_type": "Подкатегория iPrice",
    }
    result = [{"level": "root", "label": "Все товары", "value": None}]
    for field in DRILL_PATH_FIELDS:
        if field in path:
            result.append({
                "level": field,
                "label": labels[field],
                "value": (
                    "Не указано"
                    if path[field] == EMPTY_GROUP_KEY
                    else path[field]
                ),
            })
    return result


def _paginate(items, page, page_size):
    total = len(items)
    pages = max(1, (total + page_size - 1) // page_size)
    normalized_page = min(page, pages)
    start = (normalized_page - 1) * page_size
    return items[start:start + page_size], {
        "page": normalized_page,
        "page_size": page_size,
        "pages": pages,
        "count": total,
    }


def _group_rows(rows, field, config):
    grouped = defaultdict(list)
    for row in rows:
        value = row.get(field)
        grouped[
            str(value) if value else EMPTY_GROUP_KEY
        ].append(row)

    result = []
    for key, group in grouped.items():
        summary = _summarize_rows(group, config)
        label = "Не указано" if key == EMPTY_GROUP_KEY else key
        result.append({
            "key": key,
            "label": label,
            "product_count": summary["total_products"],
            "market_covered": summary["market_covered"],
            "competitor_count": summary["competitor_count"],
            "market_coverage_percent": summary["market_coverage_percent"],
            "median_final_rrp": summary["median_final_rrp"],
            "median_retail_price": summary["median_retail_price"],
            "retail_delta": summary["retail_delta"],
            "retail_delta_percent": summary["retail_delta_percent"],
            "median_market_price": summary["median_market_price"],
            "median_deviation_percent": summary["median_deviation_percent"],
            "final_market_delta": summary["final_market_delta"],
            "final_market_delta_percent": summary["final_market_delta_percent"],
            "retail_market_delta": summary["retail_market_delta"],
            "retail_market_delta_percent": summary["retail_market_delta_percent"],
            "calculation_errors": summary["calculation_errors"],
            "zones": _serialize_zones(summary),
        })

    return result


def _sort_items(items, ordering):
    descending = str(ordering or "").startswith("-")
    field = str(ordering or "").lstrip("-")
    allowed = {
        "label",
        "product_count",
        "competitor_count",
        "market_coverage_percent",
        "median_final_rrp",
        "median_retail_price",
        "retail_delta",
        "median_market_price",
        "median_deviation_percent",
        "final_market_delta", "final_market_delta_percent",
        "retail_market_delta", "retail_market_delta_percent",
        "calculation_errors",
    }
    if field not in allowed:
        field = "product_count"
        descending = True

    def key(item):
        value = item.get(field)
        if field == "label":
            return (value or "").casefold()
        return value if value is not None else Decimal("-Infinity")

    return sorted(items, key=key, reverse=descending)


def _sort_product_items(items, ordering):
    descending = str(ordering or "").startswith("-")
    field = str(ordering or "").lstrip("-")
    allowed = {
        "code_1c", "nom", "pricing_method", "competitor_count",
        "median_retail_price", "median_final_rrp", "median_market_price",
        "retail_delta", "deviation_percent", "final_market_delta",
        "final_market_delta_percent", "retail_market_delta",
        "retail_market_delta_percent", "calculation_status", "zone",
    }
    if field not in allowed:
        field = "nom"
        descending = False

    text_fields = {"nom", "pricing_method", "calculation_status", "zone"}

    def key(item):
        value = item.get(field)
        normalized = (
            str(value or "").casefold()
            if field in text_fields
            else value if value is not None else Decimal("-Infinity")
        )
        return value is not None, normalized

    return sorted(items, key=key, reverse=descending)


def build_iprice_price_analytics(
    *,
    snapshot: IPriceSnapshot,
    filters: dict,
    search: str,
    drill_level: str,
    drill_path: dict,
    page: int,
    page_size: int,
    ordering: str,
    selected_zones: list[str] | None = None,
    hierarchy: str = 'classification',
) -> dict:
    from datasets.services.iprice_snapshot_builder import _snapshot_workspace
    workspace = _snapshot_workspace(snapshot)
    IPriceSnapshotProduct = workspace.model('IPriceSnapshotProduct') if workspace else globals()['IPriceSnapshotProduct']
    IPriceSnapshotRegion = workspace.model('IPriceSnapshotRegion') if workspace else globals()['IPriceSnapshotRegion']
    group_fields = tuple(f'group_{i}' for i in range(1, 5)) if hierarchy == '1c' and workspace and workspace.code == 'select-market' else ()
    if group_fields:
        levels = ('root', *group_fields)
        if drill_level not in levels or set(drill_path) != set(group_fields[:levels.index(drill_level)]):
            raise IPricePriceAnalyticsError('Некорректный путь групп 1С.')
        path = drill_path
    else:
        path = _validate_drill(drill_level, drill_path)
    queryset = IPriceSnapshotProduct.objects.filter(snapshot=snapshot)
    queryset = filter_iprice_products_queryset(
        queryset=queryset,
        filters=filters,
    )
    regional_metrics = None
    if filters.get("sale_region") or filters.get("departure"):
        regional_queryset = filter_iprice_regions_queryset(
            queryset=IPriceSnapshotRegion.objects.filter(
                snapshot_product__snapshot=snapshot,
            ),
            filters=filters,
        )
        queryset = queryset.filter(
            id__in=regional_queryset.values("snapshot_product_id"),
        )
        regional_metrics = _build_regional_product_metrics(
            regional_queryset,
        )
    queryset = apply_iprice_products_search(
        queryset=queryset,
        search=search,
    )
    if path:
        queryset = _apply_drill_path(queryset, path)

    config = get_active_price_zone_config(workspace=workspace)
    rows = _product_rows(queryset, regional_metrics=regional_metrics, extra_fields=group_fields)
    summary = _summarize_rows(rows, config)
    normalized_zones = [
        zone for zone in (selected_zones or []) if zone in ZONE_ORDER
    ]
    display_rows = (
        [
            row for row in rows
            if classify_price_zone(row["deviation"], config)
            in normalized_zones
        ]
        if normalized_zones else rows
    )
    if group_fields:
        index = levels.index(drill_level)
        next_field = group_fields[index] if index < 4 else None
        next_label = f'Группа {index + 1}' if next_field else 'Товар'
    else:
        next_field, next_label = DRILL_LEVELS[drill_level]

    if next_field is None:
        items = []
        for row in display_rows:
            items.append({
                "id": row["id"],
                "base_product_key": row["base_product_key"],
                "code_1c": row["code_1c"],
                "nom": row["nom"],
                "image": row["image"],
                "pricing_method": row["pricing_method"],
                "calculation_status": row["calculation_status"],
                "competitor_count": row["competitor_count"],
                "median_final_rrp": row["final_rrp"],
                "median_retail_price": row["retail_price"],
                "retail_delta": row["retail_delta"],
                "retail_delta_percent": _percent(
                    row["retail_delta_percent"]
                ),
                "median_market_price": row["market_price"],
                "deviation_percent": _percent(row["deviation"]),
                "final_market_delta": row["final_market_delta"],
                "final_market_delta_percent": _percent(
                    row["final_market_delta_percent"]
                ),
                "retail_market_delta": row["retail_market_delta"],
                "retail_market_delta_percent": _percent(row["deviation"]),
                "zone": classify_price_zone(row["deviation"], config),
            })
        items = _sort_product_items(items, ordering)
        result_type = "products"
    else:
        items = _sort_items(
            _group_rows(display_rows, next_field, config),
            ordering,
        )
        result_type = "groups"

    paginated, pagination = _paginate(items, page, page_size)
    return {
        "snapshot_id": snapshot.id,
        "drill_level": drill_level,
        "drill_path": path,
        "breadcrumb": ([{'field': field, 'value': value, 'label': value} for field, value in path.items()] if group_fields else _breadcrumb(path)),
        "next_level": next_field,
        "next_level_label": next_label,
        "result_type": result_type,
        "selected_zones": normalized_zones,
        "price_zones": serialize_price_zone_config(config),
        "summary": {
            **summary,
            "zones": _serialize_zones(summary),
        },
        "results": paginated,
        "pagination": pagination,
    }


def resolve_iprice_analytics_product_keys(
    *,
    snapshot: IPriceSnapshot,
    filters: dict,
    search: str,
    drill_level: str,
    drill_path: dict,
    selected_zones: list[str] | None = None,
) -> list[int]:
    from datasets.services.iprice_snapshot_builder import _snapshot_workspace
    workspace = _snapshot_workspace(snapshot)
    IPriceSnapshotProduct = workspace.model('IPriceSnapshotProduct') if workspace else globals()['IPriceSnapshotProduct']
    IPriceSnapshotRegion = workspace.model('IPriceSnapshotRegion') if workspace else globals()['IPriceSnapshotRegion']
    """Return the exact product scope currently selected in analytics."""
    path = _validate_drill(drill_level, drill_path)
    queryset = IPriceSnapshotProduct.objects.filter(snapshot=snapshot)
    queryset = filter_iprice_products_queryset(
        queryset=queryset,
        filters=filters,
    )
    regional_metrics = None
    if filters.get("sale_region") or filters.get("departure"):
        regional_queryset = filter_iprice_regions_queryset(
            queryset=IPriceSnapshotRegion.objects.filter(
                snapshot_product__snapshot=snapshot,
            ),
            filters=filters,
        )
        queryset = queryset.filter(
            id__in=regional_queryset.values("snapshot_product_id"),
        )
        regional_metrics = _build_regional_product_metrics(regional_queryset)
    queryset = apply_iprice_products_search(queryset=queryset, search=search)
    if path:
        queryset = _apply_drill_path(queryset, path)

    config = get_active_price_zone_config(workspace=workspace)
    normalized_zones = {
        zone for zone in (selected_zones or []) if zone in ZONE_ORDER
    }
    rows = _product_rows(queryset, regional_metrics=regional_metrics)
    return sorted({
        int(row["base_product_key"])
        for row in rows
        if (
            not normalized_zones
            or classify_price_zone(row["deviation"], config)
            in normalized_zones
        )
    })


def build_iprice_regional_price_analytics(
    *,
    snapshot: IPriceSnapshot,
    filters: dict,
    search: str,
    drill_path: dict,
    page: int,
    page_size: int,
    ordering: str = "",
    selected_zones: list[str] | None = None,
) -> dict:
    from datasets.services.iprice_snapshot_builder import _snapshot_workspace
    workspace = _snapshot_workspace(snapshot)
    IPriceSnapshotRegion = workspace.model('IPriceSnapshotRegion') if workspace else globals()['IPriceSnapshotRegion']
    path = _normalize_optional_drill_path(drill_path)
    queryset = (
        IPriceSnapshotRegion.objects
        .filter(snapshot_product__snapshot=snapshot)
        .select_related("snapshot_product")
    )
    queryset = _with_effective_approved_rrp(queryset)
    queryset = filter_iprice_regions_queryset(
        queryset=queryset,
        filters=filters,
    )
    queryset = apply_iprice_regions_search(
        queryset=queryset,
        search=search,
    )
    queryset = _apply_drill_path(
        queryset,
        path,
        prefix="snapshot_product__",
    )

    config = get_active_price_zone_config(workspace=workspace)
    items = []
    for row in queryset.order_by(
        "sale_region",
        "historical_variant" if workspace else "departure",
        "snapshot_product__code_1c",
        "id",
    ):
        final_rrp = _as_decimal(row.effective_approved_rrp)
        market_price = _as_decimal(row.regional_competitor_rrp_median)
        retail_price = _as_decimal(row.current_retail)
        deviation = _deviation(retail_price, market_price)
        items.append({
            "id": row.id,
            "product_id": row.snapshot_product_id,
            "base_product_key": row.snapshot_product.base_product_key,
            "code_1c": row.snapshot_product.code_1c,
            "nom": row.snapshot_product.nom,
            "image": row.snapshot_product.image,
            "pricing_method": row.snapshot_product.pricing_method,
            "sale_region": row.sale_region,
            "departure": getattr(row, "departure", None),
            "final_rrp": final_rrp,
            "retail_price": retail_price,
            "market_price": market_price,
            "retail_delta": (
                _as_decimal(row.current_retail) - final_rrp
                if row.current_retail is not None and final_rrp is not None
                else None
            ),
            "retail_delta_percent": _percent(
                _deviation(row.current_retail, final_rrp)
            ),
            "deviation_percent": _percent(deviation),
            "final_market_delta": (
                final_rrp - market_price
                if final_rrp is not None and market_price is not None
                else None
            ),
            "final_market_delta_percent": _percent(
                _deviation(final_rrp, market_price)
            ),
            "retail_market_delta": (
                retail_price - market_price
                if retail_price is not None and market_price is not None
                else None
            ),
            "retail_market_delta_percent": _percent(deviation),
            "zone": classify_price_zone(deviation, config),
            "calculation_status": row.calculation_status,
        })

    normalized_zones = [
        zone for zone in (selected_zones or []) if zone in ZONE_ORDER
    ]
    if normalized_zones:
        items = [item for item in items if item["zone"] in normalized_zones]
    allowed_ordering = {
        "code_1c", "nom", "sale_region", "departure", "retail_price",
        "final_rrp", "market_price", "deviation_percent",
        "final_market_delta", "final_market_delta_percent",
        "retail_market_delta", "retail_market_delta_percent",
        "calculation_status",
    }
    descending = str(ordering or "").startswith("-")
    order_field = str(ordering or "").lstrip("-")
    if order_field in allowed_ordering:
        items.sort(
            key=lambda item: (
                item.get(order_field) is not None,
                str(item.get(order_field) or "").casefold()
                if order_field in {
                    "nom", "sale_region", "departure", "calculation_status"
                }
                else item.get(order_field) or Decimal("-Infinity")
            ),
            reverse=descending,
        )

    paginated, pagination = _paginate(items, page, page_size)
    return {
        "snapshot_id": snapshot.id,
        "view": "regions",
        "drill_path": path,
        "price_zones": serialize_price_zone_config(config),
        "selected_zones": normalized_zones,
        "results": paginated,
        "pagination": pagination,
    }
