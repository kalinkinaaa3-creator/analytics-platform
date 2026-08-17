from __future__ import annotations

from collections import defaultdict
from statistics import median

from datasets.models import (
    AnalyticsProductClassificationApplication,
    AnalyticsProductMatchCandidate,
    IPriceSnapshotProduct,
    IPriceSnapshotRegion,
)
from datasets.services.iprice_market_assortment import (
    clean_text,
)
from datasets.services.parsers.analytics_product_property_labels import (
    label_match_evidence,
)


class IPriceOwnAssortmentError(Exception):
    pass


def _validate(product):
    required = (
        "category",
        "subcategory",
        "subcategory_type",
        "item_type",
    )
    missing = [
        field
        for field in required
        if clean_text(getattr(product, field, None)) is None
    ]
    if missing:
        raise IPriceOwnAssortmentError(
            "Невозможно подобрать собственные аналоги: "
            "не заполнены поля " + ", ".join(missing)
        )


def build_iprice_own_assortment(
    *, snapshot_product: IPriceSnapshotProduct,
) -> dict:
    _validate(snapshot_product)
    candidates = list(
        IPriceSnapshotProduct.objects
        .filter(
            snapshot_id=snapshot_product.snapshot_id,
            category__iexact=clean_text(snapshot_product.category),
            subcategory__iexact=clean_text(snapshot_product.subcategory),
            subcategory_type__iexact=clean_text(
                snapshot_product.subcategory_type
            ),
            item_type__iexact=clean_text(snapshot_product.item_type),
        )
        .exclude(pk=snapshot_product.pk)
        .order_by("base_product_key", "id")
    )
    application = AnalyticsProductClassificationApplication.objects.filter(
        date_add__lte=snapshot_product.snapshot.created_at
    ).select_related("run").order_by("-date_add", "-id").first()
    weighted_by_key = {}
    if application is not None:
        weighted_by_key = {
            row["product_key_competitor"]: row
            for row in AnalyticsProductMatchCandidate.objects.filter(
                application=application,
                product_key_base=snapshot_product.base_product_key,
                competitor_source="base",
            ).values(
                "product_key_competitor", "match_score", "match_coverage",
                "is_eligible", "match_evidence",
            )
        }

    prices_by_product_region = defaultdict(lambda: defaultdict(list))
    for row in (
        IPriceSnapshotRegion.objects
        .filter(snapshot_product_id__in=[candidate.id for candidate in candidates])
        .values("snapshot_product_id", "sale_region", "current_retail")
    ):
        if row["current_retail"] is None:
            continue
        region = clean_text(row["sale_region"]) or "Регион не определён"
        prices_by_product_region[row["snapshot_product_id"]][region].append(
            row["current_retail"]
        )

    results = []
    for candidate in candidates:
        weighted = weighted_by_key.get(candidate.base_product_key) or {}
        score = weighted.get("match_score")
        coverage = weighted.get("match_coverage")
        similarity = label_match_evidence(weighted.get("match_evidence", {}))
        eligible = weighted.get("is_eligible", False)
        regional_prices = [
            {
                "region": region,
                "price": median(prices),
            }
            for region, prices in sorted(
                prices_by_product_region[candidate.id].items(),
                key=lambda item: item[0].casefold(),
            )
        ]
        regional_medians = [item["price"] for item in regional_prices]
        results.append({
            "group_key": f"own|{candidate.id}",
            "snapshot_product_id": candidate.id,
            "source": "iPrice",
            "product_key": candidate.base_product_key,
            "code_1c": candidate.code_1c,
            "name": candidate.nom,
            "category": candidate.category,
            "subcategory": candidate.subcategory,
            "subcategory_type": candidate.subcategory_type,
            "item_type": candidate.item_type,
            "material": candidate.material,
            "color": candidate.color,
            "modification": candidate.modification,
            "image": candidate.image,
            "url": candidate.url,
            "price": (
                median(regional_medians)
                if regional_medians
                else candidate.current_retail_median
            ),
            "regional_prices": regional_prices,
            "market_price": candidate.competitor_rrp_median,
            "pricing_method": candidate.pricing_method,
            "calculation_status": candidate.calculation_status,
            "similarity_score": score,
            "match_coverage": coverage,
            "match_eligible": eligible,
            "similarity": similarity,
        })

    results.sort(key=lambda item: (
        -(item["similarity_score"] or 0),
        str(item["name"] or "").casefold(),
        item["product_key"],
    ))
    return {
        "snapshot_id": snapshot_product.snapshot_id,
        "snapshot_product_id": snapshot_product.id,
        "base_product_key": snapshot_product.base_product_key,
        "counts": {
            "cards": len(results),
            "eligible": sum(item["match_eligible"] for item in results),
            "calculated": sum(item["similarity_score"] is not None for item in results),
        },
        "results": results,
    }
