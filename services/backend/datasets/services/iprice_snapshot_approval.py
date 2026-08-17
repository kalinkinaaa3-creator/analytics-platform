from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from statistics import median

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Max

from datasets.models import (
    IPriceSnapshot,
    IPriceSnapshotApproval,
    IPriceSnapshotProduct,
    IPriceSnapshotRegion,
)


User = get_user_model()

ZERO = Decimal("0")
ONE = Decimal("1")


class IPriceSnapshotApprovalError(Exception):
    pass


def round_price(
    value: Decimal | None,
) -> Decimal | None:
    if value is None:
        return None

    return Decimal(value).quantize(
        Decimal("0.0001"),
        rounding=ROUND_HALF_UP,
    )


def calculate_discount_price(
    *,
    rrp: Decimal,
    discount: Decimal | None,
) -> Decimal | None:
    if discount is None:
        return None

    discount = Decimal(discount)

    if discount < ZERO or discount >= ONE:
        return None

    return round_price(
        Decimal(rrp)
        * (
            ONE
            - discount
        )
    )


def refresh_iprice_product_approval_summary(
    product_id: int,
) -> IPriceSnapshotProduct:
    product = IPriceSnapshotProduct.objects.get(
        pk=product_id,
    )
    regions = list(
        IPriceSnapshotRegion.objects.filter(
            snapshot_product_id=product_id,
        ).values(
            "id",
            "default_approved_rrp",
            "discount_distr",
            "discount_distr_1",
            "discount_small",
            "discount_medium",
            "discount_large",
        )
    )
    approval_by_region = dict(
        IPriceSnapshotApproval.objects.filter(
            snapshot_region_id__in=[
                region["id"]
                for region in regions
            ],
            is_current=True,
        ).values_list(
            "snapshot_region_id",
            "approved_rrp",
        )
    )
    values = [
        Decimal(
            approval_by_region.get(
                region["id"],
                region["default_approved_rrp"],
            )
        )
        for region in regions
        if approval_by_region.get(
            region["id"],
            region["default_approved_rrp"],
        ) is not None
    ]
    approved_median = (
        round_price(Decimal(median(values)))
        if values
        else None
    )
    delta = (
        round_price(
            Decimal(product.current_retail_median)
            - approved_median
        )
        if (
            product.current_retail_median is not None
            and approved_median is not None
        )
        else None
    )
    product.effective_approved_rrp_median = (
        approved_median
    )
    product.current_vs_approved_amount = delta
    details = dict(product.calculation_details or {})
    for suffix, field in (
        ("distr", "discount_distr"),
        ("distr_1", "discount_distr_1"),
        ("small", "discount_small"),
        ("medium", "discount_medium"),
        ("large", "discount_large"),
    ):
        discounts = [
            region[field]
            for region in regions
            if region[field] is not None
        ]
        derived = [
            calculate_discount_price(
                rrp=approval_by_region.get(
                    region["id"],
                    region["default_approved_rrp"],
                ),
                discount=region[field],
            )
            for region in regions
            if (
                approval_by_region.get(
                    region["id"],
                    region["default_approved_rrp"],
                ) is not None
                and region[field] is not None
            )
        ]
        details[f"discount_{suffix}_median"] = (
            str(round_price(Decimal(median(discounts))))
            if discounts else None
        )
        details[f"effective_{suffix}_median"] = (
            str(round_price(Decimal(median(derived))))
            if derived else None
        )
    product.calculation_details = details
    product.save(
        update_fields=[
            "effective_approved_rrp_median",
            "current_vs_approved_amount",
            "calculation_details",
        ]
    )
    return product


def create_iprice_snapshot_approval(
    *,
    snapshot_region: IPriceSnapshotRegion,
    approved_rrp: Decimal,
    approved_by: User | None = None,
    comment: str = "",
) -> IPriceSnapshotApproval:
    """
    Создаёт новую версию ручного утверждения цены.

    Правила:

    1. Утверждать можно только строки успешного snapshot.
    2. Snapshot должен быть текущей технической версией
       своей calculation_date.
    3. approved_rrp должно быть больше нуля.
    4. Предыдущее утверждение строки деактивируется.
    5. Типы цен рассчитываются от утверждённой РРЦ
       через скидки, сохранённые в snapshot_region.
    """

    approved_rrp = Decimal(
        approved_rrp
    )

    if approved_rrp <= ZERO:
        raise IPriceSnapshotApprovalError(
            "Утверждённая РРЦ должна быть больше 0"
        )

    with transaction.atomic():
        locked_region = (
            IPriceSnapshotRegion.objects
            .select_for_update()
            .select_related(
                "snapshot_product__snapshot",
            )
            .get(
                pk=snapshot_region.pk,
            )
        )

        snapshot = (
            locked_region
            .snapshot_product
            .snapshot
        )

        if (
            snapshot.status
            != IPriceSnapshot.STATUS_SUCCESS
        ):
            raise IPriceSnapshotApprovalError(
                (
                    "Нельзя утверждать цену: "
                    "snapshot не завершён успешно"
                )
            )

        if not snapshot.is_current:
            raise IPriceSnapshotApprovalError(
                (
                    "Нельзя утверждать цену "
                    "в устаревшей технической версии snapshot"
                )
            )

        max_revision = (
            IPriceSnapshotApproval.objects
            .filter(
                snapshot_region=locked_region,
            )
            .aggregate(
                value=Max("revision")
            )["value"]
            or 0
        )

        (
            IPriceSnapshotApproval.objects
            .select_for_update()
            .filter(
                snapshot_region=locked_region,
                is_current=True,
            )
            .update(
                is_current=False,
            )
        )

        approved_rrp = round_price(
            approved_rrp
        )

        approval = (
            IPriceSnapshotApproval.objects
            .create(
                snapshot_region=locked_region,
                revision=max_revision + 1,
                approved_rrp=approved_rrp,
                approved_distr=(
                    calculate_discount_price(
                        rrp=approved_rrp,
                        discount=(
                            locked_region
                            .discount_distr
                        ),
                    )
                ),
                approved_distr_1=(
                    calculate_discount_price(
                        rrp=approved_rrp,
                        discount=(
                            locked_region
                            .discount_distr_1
                        ),
                    )
                ),
                approved_small=(
                    calculate_discount_price(
                        rrp=approved_rrp,
                        discount=(
                            locked_region
                            .discount_small
                        ),
                    )
                ),
                approved_medium=(
                    calculate_discount_price(
                        rrp=approved_rrp,
                        discount=(
                            locked_region
                            .discount_medium
                        ),
                    )
                ),
                approved_large=(
                    calculate_discount_price(
                        rrp=approved_rrp,
                        discount=(
                            locked_region
                            .discount_large
                        ),
                    )
                ),
                approved_by=approved_by,
                comment=comment or "",
                is_current=True,
            )
        )

    return approval
