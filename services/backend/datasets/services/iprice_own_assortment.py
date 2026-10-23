from __future__ import annotations

from collections import defaultdict
from statistics import median

from django.db.models import OuterRef, Subquery

from datasets.models import (
    IPriceSnapshotProduct,
    IPriceSnapshotRegion,
    BaseProductPrice,
    ParserProductClassification,
)
from datasets.services.iprice_market_assortment import (
    clean_text,
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
    *, snapshot_product: IPriceSnapshotProduct, workspace=None,
) -> dict:
    _validate(snapshot_product)
    product_model = workspace.model('IPriceSnapshotProduct') if workspace else IPriceSnapshotProduct
    region_model = workspace.model('IPriceSnapshotRegion') if workspace else IPriceSnapshotRegion
    site_model = workspace.model('BaseProductPrice') if workspace else BaseProductPrice
    classification_model = workspace.model('ParserProductClassification') if workspace else ParserProductClassification
    candidates = list(
        product_model.objects
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
        .annotate(
            site_name=Subquery(
                site_model.objects.filter(
                    product_key=OuterRef("base_product_key"),
                ).exclude(name__isnull=True).exclude(name="").order_by(
                    "-date_add", "-id",
                ).values("name")[:1]
            )
        )
        .order_by("base_product_key", "id")
    )
    prices_by_product_region = defaultdict(lambda: defaultdict(list))
    articles_by_product = dict(
        classification_model.objects.filter(
            product_key__in=[candidate.base_product_key for candidate in candidates],
            status=ParserProductClassification.STATUS_ACTIVE,
        ).values_list("product_key", "article_number_analogs")
    )
    for row in (
        region_model.objects
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
            "site_name": candidate.site_name,
            "category": candidate.category,
            "subcategory": candidate.subcategory,
            "subcategory_type": candidate.subcategory_type,
            "item_type": candidate.item_type,
            "material": candidate.material,
            "color": candidate.color,
            "modification": candidate.modification,
            "article_number_analogs": articles_by_product.get(candidate.base_product_key),
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
            **({'final_price': candidate.effective_approved_rrp_median} if workspace else {}),
            "calculation_status": candidate.calculation_status,
        })

    results.sort(key=lambda item: (
        str(item["name"] or "").casefold(), item["product_key"] if item["product_key"] is not None else -1, item["snapshot_product_id"],
    ))
    return {
        "snapshot_id": snapshot_product.snapshot_id,
        "snapshot_product_id": snapshot_product.id,
        "base_product_key": snapshot_product.base_product_key,
        "counts": {
            "cards": len(results),
        },
        "results": results,
    }
