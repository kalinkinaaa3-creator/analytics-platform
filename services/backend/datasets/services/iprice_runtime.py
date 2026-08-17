import logging

from dashboards.cache.iprice_cache import (
    invalidate_iprice_cache,
)
from dashboards.realtime import (
    notify_dashboard_updated,
)
from datasets.services.iprice_health import (
    invalidate_iprice_health_cache,
)
from datasets.services.iprice_snapshot_approval import (
    refresh_iprice_product_approval_summary,
)


logger = logging.getLogger("datasets")

def publish_iprice_update(
    change_type: str,
    *,
    invalidate_health: bool = False,
    **payload,
):
    cache_invalidated = True
    websocket_published = True

    try:
        invalidate_iprice_cache()
    except Exception:
        cache_invalidated = False
        logger.exception(
            "Failed to invalidate iPrice response cache"
        )

    if invalidate_health:
        try:
            invalidate_iprice_health_cache()
        except Exception:
            cache_invalidated = False
            logger.exception(
                "Failed to invalidate iPrice health cache"
            )

    try:
        notify_dashboard_updated(
            "IPrice",
            change_type=change_type,
            **payload,
        )
    except Exception:
        websocket_published = False
        logger.exception(
            "Failed to publish iPrice WebSocket event: %s",
            change_type,
        )

    return {
        "cache_invalidated": cache_invalidated,
        "websocket_published": websocket_published,
    }


def sync_snapshot_and_publish(
    snapshot_id: int,
    change_type: str,
    *,
    metadata_only: bool = False,
    publish: bool = True,
    **payload,
):
    if publish:
        publish_iprice_update(
            change_type,
            snapshot_id=snapshot_id,
            **payload,
        )
    return True


def sync_activation_and_publish(
    snapshot_id: int,
    *,
    change_type: str = "snapshot_activated",
):
    publish_iprice_update(
        change_type,
        snapshot_id=snapshot_id,
    )
    return True


def sync_approval_and_publish(
    *,
    snapshot_id: int,
    product_id: int,
    region_id: int,
):
    refresh_iprice_product_approval_summary(
        product_id
    )

    publish_iprice_update(
        "approval_saved",
        snapshot_id=snapshot_id,
        product_id=product_id,
        region_id=region_id,
    )
    return True
