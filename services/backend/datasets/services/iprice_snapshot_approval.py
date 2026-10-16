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
    *, workspace=None,
) -> IPriceSnapshotProduct:
    IPriceSnapshotProduct = workspace.model('IPriceSnapshotProduct') if workspace else globals()['IPriceSnapshotProduct']
    IPriceSnapshotRegion = workspace.model('IPriceSnapshotRegion') if workspace else globals()['IPriceSnapshotRegion']
    IPriceSnapshotApproval = workspace.model('IPriceSnapshotApproval') if workspace else globals()['IPriceSnapshotApproval']
    product = IPriceSnapshotProduct.objects.get(
        pk=product_id,
    )
    tiers = ('small', 'medium', 'large') if workspace else ('distr', 'distr_1', 'small', 'medium', 'large')
    regions = list(
        IPriceSnapshotRegion.objects.filter(
            snapshot_product_id=product_id,
        ).values(
            "id",
            "default_approved_rrp",
            *('discount_' + tier for tier in tiers),
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
    for suffix in tiers:
        field = 'discount_' + suffix
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
        if workspace:
            from select_market.iprice_prices import whole_rubles
            derived = [whole_rubles(Decimal(approval_by_region.get(region['id'], region['default_approved_rrp'])) * (1 - region[field]))
                       for region in regions if approval_by_region.get(region['id'], region['default_approved_rrp']) is not None
                       and region[field] is not None]
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
    expected_revision: int | None = None,
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

    from datasets.services.iprice_snapshot_builder import _snapshot_workspace, _lock_snapshot_workspace
    workspace = _snapshot_workspace(snapshot_region.snapshot_product.snapshot)
    if workspace and snapshot_region.historical_variant:
        raise IPriceSnapshotApprovalError('Историческая строка с маршрутом доступна только для просмотра. Создайте новый расчёт.')
    IPriceSnapshotRegion = workspace.model('IPriceSnapshotRegion') if workspace else globals()['IPriceSnapshotRegion']
    IPriceSnapshotApproval = workspace.model('IPriceSnapshotApproval') if workspace else globals()['IPriceSnapshotApproval']
    approved_rrp = Decimal(
        approved_rrp
    )

    if not approved_rrp.is_finite() or approved_rrp <= ZERO or approved_rrp >= Decimal('100000000000000'):
        raise IPriceSnapshotApprovalError(
            "Утверждённая РРЦ должна быть больше 0"
        )

    with transaction.atomic():
        _lock_snapshot_workspace(workspace)
        if workspace and workspace.model('IPriceSnapshot').objects.filter(status='building').exists():
            raise IPriceSnapshotApprovalError('Дождитесь завершения текущего расчёта перед изменением цены.')
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

        if workspace and (snapshot.is_active or snapshot.was_active):
            raise IPriceSnapshotApprovalError('Утверждённую версию менять нельзя. Создайте новый расчёт.')
        if workspace and (locked_region.error_codes or locked_region.calculation_status == 'error'):
            raise IPriceSnapshotApprovalError('Сначала устраните ошибки исходных данных и пересчитайте цены.')

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

        if expected_revision is not None and max_revision != expected_revision:
            raise IPriceSnapshotApprovalError('Цена уже изменена другим пользователем. Обновите строку.')

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
        if workspace:
            from select_market.iprice_prices import whole_rubles
            approved_rrp = whole_rubles(approved_rrp)
            if approved_rrp <= 0:
                raise IPriceSnapshotApprovalError('После округления цена должна быть больше нуля.')

        approval = (
            IPriceSnapshotApproval.objects
            .create(
                snapshot_region=locked_region,
                revision=max_revision + 1,
                approved_rrp=approved_rrp,
                **{'approved_' + tier: calculate_discount_price(rrp=approved_rrp, discount=getattr(locked_region, 'discount_' + tier))
                   for tier in (('small', 'medium', 'large') if workspace else ('distr', 'distr_1', 'small', 'medium', 'large'))},
                approved_by=approved_by,
                comment=comment or "",
                is_current=True,
            )
        )

        if workspace:
            for tier in ('small', 'medium', 'large'):
                discount = getattr(locked_region, 'discount_' + tier)
                value = whole_rubles(approved_rrp * (1 - discount)) if discount is not None else None
                if value is None or value <= 0:
                    raise IPriceSnapshotApprovalError('После округления все оптовые цены должны быть больше нуля.')
                setattr(approval, 'approved_' + tier, value)
            from select_market.iprice_regional_calculation import prices_meet_margin
            if not prices_meet_margin(locked_region, [approval.approved_rrp, approval.approved_small, approval.approved_medium, approval.approved_large]):
                raise IPriceSnapshotApprovalError('После округления цена нарушает минимальную маржу.')
            approval.save(update_fields=['approved_small', 'approved_medium', 'approved_large'])
            if 'REAPPROVAL_REQUIRED' in locked_region.warning_codes:
                locked_region.warning_codes = [code for code in locked_region.warning_codes if code != 'REAPPROVAL_REQUIRED']
                locked_region.calculation_status = 'warning' if locked_region.warning_codes else 'success'
                locked_region.save(update_fields=['warning_codes', 'calculation_status'])
            snapshot.parameters = {**snapshot.parameters,
                'edit_revision': snapshot.parameters.get('edit_revision', 0) + 1}
            snapshot.save(update_fields=['parameters'])
            refresh_iprice_product_approval_summary(locked_region.snapshot_product_id, workspace=workspace)

    return approval
