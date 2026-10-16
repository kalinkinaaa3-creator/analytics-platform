from .queue_execution import standalone
from collections.abc import Iterable

from django.db import transaction
from django.db.models import Case, F, TextField, Value, When, Window
from django.db.models.functions import RowNumber, TruncDate

from datasets.models import (
    BaseProductPrice,
    IPriceSnapshotProduct,
    ParserProductClassification,
    ParserProductUrl,
    PsProductPrice,
    TaraProductPrice,
    TtProductPrice,
)


PRICE_MODELS = {
    "base": BaseProductPrice,
    "tt": TtProductPrice,
    "ps": PsProductPrice,
    "tara": TaraProductPrice,
}

UPDATE_BATCH_SIZE = 300


def _chunks(values, size=UPDATE_BATCH_SIZE):
    values = list(values)
    for index in range(0, len(values), size):
        yield values[index:index + size]


def _selected_images(model, product_keys):
    """Select image by the runtime iPrice price-row rule."""
    product_keys = set(product_keys)
    if not product_keys:
        return {}

    selected = {}
    positive_rows = (
        model.objects.filter(
            product_key__in=product_keys,
            final_price__gt=0,
        )
        .annotate(price_day=TruncDate("date_add"))
        .annotate(
            selected_row=Window(
                expression=RowNumber(),
                partition_by=(F("product_key"),),
                order_by=(
                    F("price_day").desc(),
                    F("final_price").desc(),
                    F("id").asc(),
                ),
            )
        )
        .filter(selected_row=1)
        .values("product_key", "image")
    )
    for row in positive_rows.iterator(chunk_size=1000):
        selected[row["product_key"]] = row["image"]

    missing_keys = product_keys - set(selected)
    if not missing_keys:
        return selected

    fallback_rows = (
        model.objects.filter(product_key__in=missing_keys)
        .annotate(price_day=TruncDate("date_add"))
        .annotate(
            selected_row=Window(
                expression=RowNumber(),
                partition_by=(F("product_key"),),
                order_by=(
                    F("price_day").desc(),
                    F("id").asc(),
                ),
            )
        )
        .filter(selected_row=1)
        .values("product_key", "image")
    )
    for row in fallback_rows.iterator(chunk_size=1000):
        selected[row["product_key"]] = row["image"]

    return selected


def _update_image_mapping(model, key_field, images):
    updated = 0
    image_field = model._meta.get_field("image")
    for product_keys in _chunks(sorted(images)):
        image_case = Case(
            *(
                When(
                    **{
                        key_field: product_key,
                        "then": Value(
                            images[product_key]
                            if image_field.null
                            else (images[product_key] or "")
                        ),
                    }
                )
                for product_key in product_keys
            ),
            output_field=TextField(),
        )
        updated += model.objects.filter(
            **{f"{key_field}__in": product_keys}
        ).update(image=image_case)
    return updated


def sync_iprice_product_images(
    *,
    source: str | None = None,
    product_keys: Iterable[int] | None = None,
    workspace=None,
):
    """
    Refresh mutable image links without changing product URLs or product keys.

    Selection per product key:
      latest available calendar day with a positive final_price;
      MAX(final_price); MIN(id). If no positive final_price exists,
      use MIN(id) from the latest available calendar day.
    """
    ParserProductUrl = workspace.model("ParserProductUrl") if workspace else globals()["ParserProductUrl"]
    ParserProductClassification = workspace.model("ParserProductClassification") if workspace else globals()["ParserProductClassification"]
    IPriceSnapshotProduct = workspace.model("IPriceSnapshotProduct") if workspace else globals()["IPriceSnapshotProduct"]
    price_models = {source: workspace.model(model.__name__) for source, model in PRICE_MODELS.items()} if workspace else PRICE_MODELS
    requested_keys = set(product_keys or ())
    url_rows = ParserProductUrl.objects.all()
    if source is not None:
        source = str(source).strip().casefold()
        if source not in price_models:
            raise ValueError(f"Unsupported parser source: {source}")
        url_rows = url_rows.filter(source=source)
    if requested_keys:
        url_rows = url_rows.filter(id__in=requested_keys)

    keys_by_source = {}
    for row_source, product_key in url_rows.values_list("source", "id").iterator(
        chunk_size=1000
    ):
        source_key = str(row_source or "").strip().casefold()
        if source_key in price_models:
            keys_by_source.setdefault(source_key, set()).add(product_key)

    images = {}
    for source_key, source_keys in keys_by_source.items():
        images.update(_selected_images(price_models[source_key], source_keys))

    if not images:
        return {
            "selected": 0,
            "without_price_rows": sum(len(keys) for keys in keys_by_source.values()),
            "classifications_updated": 0,
            "snapshot_products_updated": 0,
        }

    with transaction.atomic():
        classifications_updated = _update_image_mapping(
            ParserProductClassification,
            "product_key",
            images,
        )
        snapshot_products_updated = _update_image_mapping(
            IPriceSnapshotProduct,
            "base_product_key",
            images,
        )

    total_requested = sum(len(keys) for keys in keys_by_source.values())
    return {
        "selected": len(images),
        "without_price_rows": total_requested - len(images),
        "classifications_updated": classifications_updated,
        "snapshot_products_updated": snapshot_products_updated,
    }


@standalone("images")
def sync_parser_source_images(source):
    """Synchronize one completed parser source and refresh iPrice clients."""
    from datasets.services.iprice_runtime import publish_iprice_update

    result = sync_iprice_product_images(source=source)
    publish_result = publish_iprice_update(
        "parser_images_updated",
        invalidate_health=True,
        source=source,
        image_sync=result,
    )
    return {
        **result,
        **publish_result,
    }
