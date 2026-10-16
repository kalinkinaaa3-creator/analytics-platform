from __future__ import annotations

from functools import partial

import traceback

from datetime import date

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Max
from django.utils import timezone


from decimal import Decimal, ROUND_HALF_UP
from statistics import median

from datasets.models import (
    DepartureDiscount,
    IPriceCalculationConfig,
    IPriceSnapshot,
    IPriceSnapshotCompetitor,
    IPriceSnapshotProduct,
    IPriceSnapshotRegion,
    Nomenclature,
    ParserProductProperty,
    ParserProductClassification,
    ParserProductMatch,
    ParserProductUrl,
)

from analytics.services.bitrix_notify import (
    send_bitrix_message,
)

from datasets.services.iprice_source_selector import (
    get_all_sale_regions,
    get_base_product_price,
    get_competitor_price_data,
    get_competitor_regions,
    get_departure_discount,
    get_iprice_config,
    get_nomenclature_price,
    get_product_cost,
    get_transport_cost,
)



User = get_user_model()


def _snapshot_workspace(snapshot):
    from datasets.services.iprice_workspace import IPriceWorkspace
    return IPriceWorkspace("select-market") if snapshot._meta.app_label == "select_market" else None


def _lock_snapshot_workspace(workspace):
    if workspace and workspace.code == "select-market":
        from organizations.models import Organization
        Organization.objects.select_for_update().get(code=workspace.code, postgres_schema="select_market")


def _publish_snapshot(snapshot, event, **kwargs):
    if _snapshot_workspace(snapshot):
        return
    from datasets.services.iprice_runtime import sync_snapshot_and_publish
    sync_snapshot_and_publish(snapshot.pk, event, **kwargs)



class IPriceSnapshotBuildError(Exception):
    """
    Ошибка создания snapshot iPrice.
    """


def decimal_median(
    values,
) -> Decimal | None:
    """
    Возвращает медиану Decimal.

    None исключаются.
    """

    clean_values = [
        Decimal(value)
        for value in values
        if value is not None
    ]

    if not clean_values:
        return None

    return Decimal(
        median(clean_values)
    )


def decimal_min(
    values,
) -> Decimal | None:
    clean_values = [
        Decimal(value)
        for value in values
        if value is not None
    ]

    return (
        min(clean_values)
        if clean_values
        else None
    )


def decimal_max(
    values,
) -> Decimal | None:
    clean_values = [
        Decimal(value)
        for value in values
        if value is not None
    ]

    return (
        max(clean_values)
        if clean_values
        else None
    )


ZERO = Decimal("0")
ONE = Decimal("1")
SAM_PROPERTY_NAME = (
    "Статус ассортиментной матрицы (САМ)"
)
OUR_OFFER_PROPERTY_NAME = (
    "Наши предложения"
)

def get_sam_by_product_key(
    product_keys,
    workspace=None,
) -> dict[int, str | None]:
    ParserProductProperty = workspace.model("ParserProductProperty") if workspace else globals()["ParserProductProperty"]

    if not product_keys:
        return {}

    rows = (
        ParserProductProperty.objects
        .filter(
            source="base",
            product_key__in=product_keys,
            properties__iexact=SAM_PROPERTY_NAME,
        )
        .order_by(
            "product_key",
            "-date_add",
            "-id",
        )
        .values(
            "product_key",
            "value",
        )
    )

    result = {}

    for row in rows:
        product_key = row["product_key"]

        if product_key in result:
            continue

        value = row["value"]
        value = (
            str(value).strip()
            if value is not None
            else ""
        )
        result[product_key] = value or None

    return result


def get_our_offer_by_product_key(
    product_keys,
    workspace=None,
) -> dict[int, str | None]:
    ParserProductProperty = workspace.model("ParserProductProperty") if workspace else globals()["ParserProductProperty"]

    if not product_keys:
        return {}

    rows = (
        ParserProductProperty.objects
        .filter(
            source="base",
            product_key__in=product_keys,
            properties__iexact=(
                OUR_OFFER_PROPERTY_NAME
            ),
        )
        .order_by(
            "product_key",
            "-date_add",
            "-id",
        )
        .values(
            "product_key",
            "value",
        )
    )

    result = {}

    for row in rows:
        product_key = row["product_key"]

        if product_key in result:
            continue

        value = row["value"]

        value = (
            str(value).strip()
            if value is not None
            else ""
        )

        result[product_key] = (
            value or None
        )

    return result


def round_price(
    value: Decimal | None,
) -> Decimal | None:
    """
    Округляет цену до целого рубля
    по математическому правилу ROUND_HALF_UP.
    """

    if value is None:
        return None

    return Decimal(value).quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP,
    )


def calculate_margin(
    *,
    price: Decimal | None,
    cost: Decimal | None,
) -> Decimal | None:
    """
    Маржа в долях.

    Например:
        0.25 = 25%.
    """

    if (
        price is None
        or cost is None
        or price == 0
    ):
        return None

    return (
        Decimal(price)
        - Decimal(cost)
    ) / Decimal(price)


def calculate_discount_price(
    *,
    rrp: Decimal | None,
    discount: Decimal | None,
) -> Decimal | None:
    """
    Цена по типу цены:

        price = RRP × (1 - discount)
    """

    if (
        rrp is None
        or discount is None
    ):
        return None

    return (
        Decimal(rrp)
        * (
            ONE
            - Decimal(discount)
        )
    )


def calculate_minimum_price(
    *,
    cost_with_logistics: Decimal | None,
    minimum_margin: Decimal | None,
) -> Decimal | None:
    """
    Минимальная цена, обеспечивающая
    минимальную маржинальность:

        cost / (1 - minimum_margin)
    """

    if (
        cost_with_logistics is None
        or minimum_margin is None
    ):
        return None

    denominator = (
        ONE
        - Decimal(minimum_margin)
    )

    if denominator <= 0:
        return None

    return (
        Decimal(cost_with_logistics)
        / denominator
    )


def calculate_minimum_allowed_rrp(
    *,
    minimum_price: Decimal | None,
    distr_discount: Decimal | None,
) -> Decimal | None:
    """
    Минимально допустимая РРЦ с учетом скидки distr.

    После скидки distr цена должна оставаться
    не ниже minimum_price:

        minimum_rrp =
            minimum_price / (1 - distr_discount)
    """

    if (
        minimum_price is None
        or distr_discount is None
    ):
        return None

    denominator = (
        ONE
        - Decimal(distr_discount)
    )

    if denominator <= 0:
        return None

    return (
        Decimal(minimum_price)
        / denominator
    )


def calculate_deviation(
    *,
    current_value: Decimal | None,
    reference_value: Decimal | None,
) -> tuple[
    Decimal | None,
    Decimal | None,
]:
    """
    Возвращает:
        отклонение в рублях;
        отклонение долей.

    Например:
        0.25 = текущая цена выше медианы на 25%.
    """

    if (
        current_value is None
        or reference_value is None
        or reference_value == 0
    ):
        return None, None

    amount = (
        current_value
        - reference_value
    )

    percent = (
        current_value
        / reference_value
        - Decimal("1")
    )

    return amount, percent


def create_iprice_snapshot(
    *,
    calculation_date: date,
    created_by: User | None = None,
    parameters: dict | None = None,
    workspace=None,
) -> IPriceSnapshot:
    """
    Создает новую техническую версию snapshot для calculation_date.

    Правила:

    1. version_number — глобальный последовательный номер версии.

    2. revision_for_date — последовательный номер пересчета
       для конкретной calculation_date.

    3. Новая запись сначала создается со status=building.

    4. Предыдущий успешный is_current snapshot за эту дату
       пока не отключается. Это будет сделано только после
       успешного завершения нового расчета.

       Поэтому при падении нового расчета старая рабочая версия
       остается текущей.

    5. is_active не переключается автоматически.
       Активный окончательный snapshot назначается отдельно
       пользователем.
    """
    IPriceSnapshot = workspace.model("IPriceSnapshot") if workspace else globals()["IPriceSnapshot"]


    if not isinstance(calculation_date, date):
        raise IPriceSnapshotBuildError(
            "calculation_date must be a date instance"
        )

    if parameters is None:
        parameters = {}

    with transaction.atomic():
        # Блокируем существующие snapshot, чтобы два параллельных
        # запуска не получили одинаковые номера версий.
        _lock_snapshot_workspace(workspace)
        if workspace and IPriceSnapshot.objects.filter(status=IPriceSnapshot.STATUS_BUILDING).exists():
            raise IPriceSnapshotBuildError("A Select Market calculation is already building")
        existing_snapshots = (
            IPriceSnapshot.objects
            .select_for_update()
            .all()
        )

        max_version_number = (
            existing_snapshots.aggregate(
                value=Max("version_number")
            )["value"]
            or 0
        )

        max_revision_for_date = (
            existing_snapshots
            .filter(
                calculation_date=calculation_date,
            )
            .aggregate(
                value=Max("revision_for_date")
            )["value"]
            or 0
        )

        snapshot = IPriceSnapshot.objects.create(
            calculation_date=calculation_date,
            version_number=max_version_number + 1,
            revision_for_date=max_revision_for_date + 1,
            status=IPriceSnapshot.STATUS_BUILDING,
            is_current=False,
            is_active=False,
            created_by=created_by,
            parameters=parameters,
        )

    return snapshot


def complete_iprice_snapshot(
    *,
    snapshot: IPriceSnapshot,
) -> IPriceSnapshot:
    """
    Успешно завершает построение snapshot.

    Только на этом этапе:

    1. предыдущая текущая версия этой calculation_date
       получает is_current=False;

    2. новый snapshot получает:
       status=success,
       is_current=True,
       finished_at=текущее время.

    Активный окончательный snapshot не меняется.
    """
    workspace = _snapshot_workspace(snapshot)
    IPriceSnapshot = workspace.model("IPriceSnapshot") if workspace else globals()["IPriceSnapshot"]


    with transaction.atomic():
        _lock_snapshot_workspace(workspace)
        locked_snapshot = (
            IPriceSnapshot.objects
            .select_for_update()
            .get(pk=snapshot.pk)
        )

        if (
            locked_snapshot.status
            != IPriceSnapshot.STATUS_BUILDING
        ):
            raise IPriceSnapshotBuildError(
                (
                    "Snapshot cannot be completed because "
                    f"its status is {locked_snapshot.status}"
                )
            )

        (
            IPriceSnapshot.objects
            .select_for_update()
            .filter(
                calculation_date=(
                    locked_snapshot.calculation_date
                ),
                is_current=True,
            )
            .exclude(
                pk=locked_snapshot.pk,
            )
            .update(
                is_current=False,
            )
        )

        locked_snapshot.status = (
            IPriceSnapshot.STATUS_SUCCESS
        )

        locked_snapshot.is_current = True
        locked_snapshot.finished_at = timezone.now()
        locked_snapshot.error = ""

        locked_snapshot.save(
            update_fields=[
                "status",
                "is_current",
                "finished_at",
                "error",
            ]
        )

    return locked_snapshot


def fail_iprice_snapshot(
    *,
    snapshot: IPriceSnapshot,
    error: Exception | str,
) -> IPriceSnapshot:
    """
    Помечает новый snapshot как failed.

    Предыдущий успешный is_current snapshot за эту дату
    не изменяется.
    """
    workspace = _snapshot_workspace(snapshot)
    IPriceSnapshot = workspace.model("IPriceSnapshot") if workspace else globals()["IPriceSnapshot"]


    error_text = str(error)

    with transaction.atomic():
        locked_snapshot = (
            IPriceSnapshot.objects
            .select_for_update()
            .get(pk=snapshot.pk)
        )

        locked_snapshot.status = (
            IPriceSnapshot.STATUS_FAILED
        )

        locked_snapshot.is_current = False
        locked_snapshot.finished_at = timezone.now()
        locked_snapshot.error = error_text

        locked_snapshot.save(
            update_fields=[
                "status",
                "is_current",
                "finished_at",
                "error",
            ]
        )

    return locked_snapshot


def activate_iprice_snapshot(
    *,
    snapshot: IPriceSnapshot,
    activated_by: User | None = None,
    expected_revision: int | None = None,
) -> IPriceSnapshot:
    """
    Назначает snapshot единственным активным окончательным
    расчетом iPrice.

    Активировать можно только успешно рассчитанный snapshot.
    Он необязательно должен быть последним по дате расчета,
    но должен быть текущей технической версией своей даты.
    """
    workspace = _snapshot_workspace(snapshot)
    IPriceSnapshot = workspace.model("IPriceSnapshot") if workspace else globals()["IPriceSnapshot"]


    with transaction.atomic():
        _lock_snapshot_workspace(workspace)
        locked_snapshot = (
            IPriceSnapshot.objects
            .select_for_update()
            .get(pk=snapshot.pk)
        )

        if (
            locked_snapshot.status
            != IPriceSnapshot.STATUS_SUCCESS
        ):
            raise IPriceSnapshotBuildError(
                (
                    "Only a successful snapshot can be "
                    "activated"
                )
            )

        if not locked_snapshot.is_current:
            raise IPriceSnapshotBuildError(
                (
                    "Only the current revision for the "
                    "calculation date can be activated"
                )
            )

        if workspace:
            from select_market.iprice_activation import validate_activation
            if expected_revision is not None and locked_snapshot.parameters.get('edit_revision', 0) != expected_revision:
                raise IPriceSnapshotBuildError('Расчёт изменён другим пользователем. Обновите данные перед утверждением.')
            validate_activation(locked_snapshot)
            if locked_snapshot.is_active:
                return locked_snapshot
            previous_ids = list(IPriceSnapshot.objects.filter(is_active=True).values_list('pk', flat=True))

        (
            IPriceSnapshot.objects
            .select_for_update()
            .filter(
                is_active=True,
            )
            .exclude(
                pk=locked_snapshot.pk,
            )
            .update(
                is_active=False,
                activated_by=None,
                activated_at=None,
            )
        )

        locked_snapshot.is_active = True
        locked_snapshot.was_active = True
        locked_snapshot.activated_by = activated_by
        locked_snapshot.activated_at = timezone.now()

        locked_snapshot.save(
            update_fields=[
                "is_active",
                "was_active",
                "activated_by",
                "activated_at",
            ]
        )

        if workspace:
            parameters = dict(locked_snapshot.parameters or {})
            history = list(parameters.get('activation_history', []))
            history.append({'at': locked_snapshot.activated_at.isoformat(),
                'user_id': activated_by.pk if activated_by else None,
                'username': activated_by.get_username() if activated_by else None,
                'previous_snapshot_ids': previous_ids})
            parameters['activation_history'] = history
            locked_snapshot.parameters = parameters
            locked_snapshot.save(update_fields=['parameters'])

    return locked_snapshot


def deactivate_iprice_snapshot(
    *,
    snapshot: IPriceSnapshot,
    deactivated_by: User | None = None,
) -> IPriceSnapshot:
    """Снимает с snapshot признак окончательной активной версии."""
    workspace = _snapshot_workspace(snapshot)
    IPriceSnapshot = workspace.model("IPriceSnapshot") if workspace else globals()["IPriceSnapshot"]


    with transaction.atomic():
        _lock_snapshot_workspace(workspace)
        locked_snapshot = (
            IPriceSnapshot.objects
            .select_for_update()
            .get(pk=snapshot.pk)
        )

        if not locked_snapshot.is_active:
            raise IPriceSnapshotBuildError(
                "Деактивировать можно только активную версию"
            )

        locked_snapshot.is_active = False
        locked_snapshot.activated_by = None
        locked_snapshot.activated_at = None
        locked_snapshot.save(
            update_fields=[
                "is_active",
                "activated_by",
                "activated_at",
            ]
        )

        if workspace:
            parameters = dict(locked_snapshot.parameters or {})
            history = list(parameters.get('activation_history', []))
            history.append({'action': 'deactivate', 'at': timezone.now().isoformat(),
                'user_id': deactivated_by.pk if deactivated_by else None,
                'username': deactivated_by.get_username() if deactivated_by else None,
                'previous_snapshot_ids': [locked_snapshot.pk]})
            locked_snapshot.parameters = {**parameters, 'activation_history': history}
            locked_snapshot.save(update_fields=['parameters'])

    return locked_snapshot


def get_current_retail_summary(
    *,
    code_1c: int | str,
    calculation_date: date,
    workspace=None,
) -> dict:
    """
    Берет retail только для регионов продажи,
    существующих в ParserPrefix.

    Для каждого региона:
        последняя nomenclature_price.date
        <= calculation_date.

    Возвращает min/max/median и исходные значения.
    """
    get_all_sale_regions = partial(globals()["get_all_sale_regions"], workspace=workspace)
    get_nomenclature_price = partial(globals()["get_nomenclature_price"], workspace=workspace)


    sale_regions = get_all_sale_regions()

    values = []
    rows = []

    for sale_region in sale_regions:
        price_row = get_nomenclature_price(
            code=code_1c,
            shipp_region=sale_region,
            calculation_date=calculation_date,
        )

        if price_row is None:
            continue

        rows.append({
            "id": price_row.id,
            "sale_region": sale_region,
            "date": (
                price_row.date.isoformat()
                if price_row.date
                else None
            ),
            "retail": (
                str(price_row.retail)
                if price_row.retail is not None
                else None
            ),
        })

        if price_row.retail is not None:
            values.append(
                price_row.retail
            )

    return {
        "minimum": decimal_min(values),
        "maximum": decimal_max(values),
        "median": decimal_median(values),
        "rows": rows,
        "sale_region_count": len(sale_regions),
        "price_region_count": len(values),
    }


def build_iprice_snapshot_products(
    *,
    snapshot: IPriceSnapshot,
) -> dict:
    """
    Заполняет нерегиональную часть snapshot:

    IPriceSnapshotProduct
    IPriceSnapshotCompetitor

    Региональные строки здесь не создаются.
    """
    workspace = _snapshot_workspace(snapshot)
    if workspace and workspace.code == 'select-market':
        from select_market.iprice_catalog import build_products
        return build_products(snapshot)
    IPriceSnapshot = workspace.model("IPriceSnapshot") if workspace else globals()["IPriceSnapshot"]
    IPriceSnapshotCompetitor = workspace.model("IPriceSnapshotCompetitor") if workspace else globals()["IPriceSnapshotCompetitor"]
    IPriceSnapshotProduct = workspace.model("IPriceSnapshotProduct") if workspace else globals()["IPriceSnapshotProduct"]
    Nomenclature = workspace.model("Nomenclature") if workspace else globals()["Nomenclature"]
    ParserProductClassification = workspace.model("ParserProductClassification") if workspace else globals()["ParserProductClassification"]
    ParserProductMatch = workspace.model("ParserProductMatch") if workspace else globals()["ParserProductMatch"]
    ParserProductUrl = workspace.model("ParserProductUrl") if workspace else globals()["ParserProductUrl"]
    get_base_product_price = partial(globals()["get_base_product_price"], workspace=workspace)
    get_competitor_price_data = partial(globals()["get_competitor_price_data"], workspace=workspace)
    get_competitor_regions = partial(globals()["get_competitor_regions"], workspace=workspace)
    get_current_retail_summary = partial(globals()["get_current_retail_summary"], workspace=workspace)
    get_our_offer_by_product_key = partial(globals()["get_our_offer_by_product_key"], workspace=workspace)
    get_sam_by_product_key = partial(globals()["get_sam_by_product_key"], workspace=workspace)


    if (
        snapshot.status
        != IPriceSnapshot.STATUS_BUILDING
    ):
        raise IPriceSnapshotBuildError(
            (
                "Products can be built only for "
                "a snapshot with status=building"
            )
        )

    calculation_date = (
        snapshot.calculation_date
    )

    classifications = list(
        ParserProductClassification.objects
        .filter(
            status=(
                ParserProductClassification
                .STATUS_ACTIVE
            ),
        )
        .order_by(
            "product_key",
        )
    )

    if not classifications:
        raise IPriceSnapshotBuildError(
            "No active product classifications found"
        )

    classification_keys = {
        row.product_key
        for row in classifications
    }

    base_urls = {
        row.id: row
        for row in (
            ParserProductUrl.objects
            .filter(
                id__in=classification_keys,
                source="base",
                status=(
                    ParserProductUrl
                    .STATUS_ACTIVE
                ),
            )
            .only(
                "id",
                "source",
                "url",
            )
        )
    }

    active_matches = list(
        ParserProductMatch.objects
        .filter(
            product_key_base__in=(
                classification_keys
            ),
            status=(
                ParserProductMatch
                .STATUS_ACTIVE
            ),
        )
        .order_by(
            "product_key_base",
            "product_key_competitor",
        )
    )

    matches_by_base = {}

    for match in active_matches:
        matches_by_base.setdefault(
            match.product_key_base,
            [],
        ).append(
            match.product_key_competitor
        )

    competitor_keys = {
        match.product_key_competitor
        for match in active_matches
    }

    active_competitor_urls = {
        row.id: row
        for row in (
            ParserProductUrl.objects
            .filter(
                id__in=competitor_keys,
                status=(
                    ParserProductUrl
                    .STATUS_ACTIVE
                ),
            )
            .exclude(
                source="base",
            )
            .only(
                "id",
                "source",
                "prefix",
                "url",
            )
        )
    }

    sam_by_product_key = get_sam_by_product_key(
        set(base_urls)
    )

    our_offer_by_product_key = (
        get_our_offer_by_product_key(
            set(base_urls)
        )
    )

    product_objects = []
    prepared_products = []

    skipped_not_base = 0
    missing_base_price = 0
    missing_code_1c = 0
    missing_nomenclature = 0
    missing_config = 0

    for classification in classifications:
        product_key = (
            classification.product_key
        )

        if product_key not in base_urls:
            skipped_not_base += 1
            continue

        base_price = get_base_product_price(
            product_key=product_key,
            calculation_date=calculation_date,
        )

        if base_price is None:
            missing_base_price += 1
            continue

        code_1c = base_price.code_1c

        if code_1c is None:
            missing_code_1c += 1
            continue

        nomenclature = (
            Nomenclature.objects
            .filter(
                nom_code=code_1c,
            )
            .order_by(
                "-id",
            )
            .first()
        )

        if nomenclature is None:
            missing_nomenclature += 1
            continue

        warning_codes = []
        error_codes = []

        matched_competitor_keys = [
            competitor_key
            for competitor_key in (
                matches_by_base.get(
                    product_key,
                    [],
                )
            )
            if competitor_key
            in active_competitor_urls
        ]

        pricing_method = (
            IPriceSnapshotProduct
            .PRICING_METHOD_ANALOG
            if matched_competitor_keys
            else
            IPriceSnapshotProduct
            .PRICING_METHOD_EXCLUSIVE
        )

        retail_summary = (
            get_current_retail_summary(
                code_1c=code_1c,
                calculation_date=(
                    calculation_date
                ),
            )
        )

        nom_hier = nomenclature.nom_hier

        if (
            nom_hier is None
            or str(nom_hier).strip() in {"", "-"}
        ):
            nom_hier = nomenclature.nom

        nom_hier_code = (
            nomenclature.nom_hier_code
        )

        if nom_hier_code in {None, 0}:
            nom_hier_code = nomenclature.nom_code

        product_object = (
            IPriceSnapshotProduct(
                snapshot=snapshot,
                base_product_key=product_key,
                code_1c=code_1c,
                nom=nomenclature.nom,
                nom_hier_code=(
                    str(nom_hier_code)
                    if nom_hier_code is not None
                    else None
                ),
                nom_hier=nom_hier,
                nom_view=nomenclature.nom_view,
                nom_category=(
                    nomenclature.nom_category
                ),
                nom_group=nomenclature.nom_group,
                assortment_matrix_status=(
                    sam_by_product_key.get(
                        product_key
                    )
                ),
                our_offer=(
                    our_offer_by_product_key.get(
                        product_key
                    )
                ),
                category=classification.category,
                subcategory=(
                    classification.subcategory
                ),
                subcategory_type=(
                    classification
                    .subcategory_type
                ),
                color=classification.color,
                material=classification.material,
                modification=(
                    classification.modification
                ),
                image=classification.image,
                url=classification.url,
                item_type=(
                    classification.item_type
                ),
                pricing_method=pricing_method,
                current_retail_min=(
                    retail_summary["minimum"]
                ),
                current_retail_max=(
                    retail_summary["maximum"]
                ),
                current_retail_median=(
                    retail_summary["median"]
                ),
                calculation_status=(
                    IPriceSnapshotProduct
                    .STATUS_ERROR
                    if error_codes
                    else
                    IPriceSnapshotProduct
                    .STATUS_SUCCESS
                ),
                warning_codes=warning_codes,
                error_codes=error_codes,
                calculation_details={
                    "base_product_price_id": (
                        base_price.id
                    ),
                    "current_retail_rows": (
                        retail_summary["rows"]
                    ),
                    "sale_region_count": (
                        retail_summary[
                            "sale_region_count"
                        ]
                    ),
                    "price_region_count": (
                        retail_summary[
                            "price_region_count"
                        ]
                    ),
                },
            )
        )

        product_objects.append(
            product_object
        )

        prepared_products.append({
            "product_key": product_key,
            "product_object": (
                product_object
            ),
            "classification": (
                classification
            ),
            "competitor_keys": (
                matched_competitor_keys
            ),
        })

    with transaction.atomic():
        # Повторный вызов для ещё строящегося snapshot
        # не должен размножить строки.
        IPriceSnapshotProduct.objects.filter(
            snapshot=snapshot,
        ).delete()

        created_products = (
            IPriceSnapshotProduct.objects
            .bulk_create(
                product_objects,
                batch_size=1000,
            )
        )

        product_by_key = {
            row.base_product_key: row
            for row in created_products
        }

        competitor_objects = []

        product_rrp_values = {}

        missing_competitor_price = 0

        for prepared in prepared_products:
            product_key = prepared[
                "product_key"
            ]

            snapshot_product = (
                product_by_key[product_key]
            )

            rrp_values = []

            for competitor_key in prepared[
                "competitor_keys"
            ]:
                competitor_url = (
                    active_competitor_urls[
                        competitor_key
                    ]
                )

                price_data = (
                    get_competitor_price_data(
                        product_key=(
                            competitor_key
                        ),
                        calculation_date=(
                            calculation_date
                        ),
                    )
                )

                region_data = (
                    get_competitor_regions(
                        source=(
                            competitor_url.source
                        ),
                        prefix=(
                            competitor_url.prefix
                        ),
                    )
                )

                warning_codes = []
                error_codes = []

                calculation_price = None
                preliminary_rrp = None

                if price_data is None:
                    missing_competitor_price += 1
                    warning_codes.append(
                        "MISSING_COMPETITOR_PRICE"
                    )

                else:
                    calculation_price = (
                        price_data[
                            "calculation_price"
                        ]
                    )

                    if calculation_price is None:
                        warning_codes.append(
                            "MISSING_FINAL_PRICE"
                        )

                if calculation_price is not None:
                    rrp_values.append(
                        Decimal(calculation_price)
                    )

                competitor_objects.append(
                    IPriceSnapshotCompetitor(
                        snapshot_product=(
                            snapshot_product
                        ),
                        competitor_product_key=(
                            competitor_key
                        ),
                        source=(
                            competitor_url.source
                        ),
                        url=competitor_url.url,
                        prefix=(
                            competitor_url.prefix
                        ),
                        competitor_price_date=(
                            price_data["price_date"]
                            if price_data
                            else None
                        ),
                        competitor_final_price_max=(
                            calculation_price
                        ),
                        source_price_row_id=(
                            price_data[
                                "calculation_row_id"
                            ]
                            if price_data
                            else None
                        ),
                        price_variants=(
                            [
                                {
                                    **variant,
                                    "market_regions": region_data[
                                        "region_groups"
                                    ],
                                }
                                for variant in price_data["variants"]
                            ]
                            if price_data
                            else []
                        ),
                        is_all_regions=(
                            region_data[
                                "is_all_regions"
                            ]
                        ),
                        applicable_regions=(
                            region_data["regions"]
                        ),
                        base_analog=(
                            None
                        ),
                        preliminary_rrp=(
                            None
                        ),
                        calculation_status=(
                            "error"
                            if error_codes
                            else (
                                "warning"
                                if warning_codes
                                else "success"
                            )
                        ),
                        warning_codes=(
                            warning_codes
                        ),
                        error_codes=error_codes,
                    )
                )

            product_rrp_values[
                product_key
            ] = rrp_values

        if competitor_objects:
            (
                IPriceSnapshotCompetitor
                .objects
                .bulk_create(
                    competitor_objects,
                    batch_size=1000,
                )
            )

        products_to_update = []

        for snapshot_product in (
            created_products
        ):
            rrp_values = (
                product_rrp_values.get(
                    snapshot_product
                    .base_product_key,
                    [],
                )
            )

            snapshot_product.competitor_count = (
                len(rrp_values)
            )

            snapshot_product.competitor_rrp_min = (
                decimal_min(rrp_values)
            )

            snapshot_product.competitor_rrp_max = (
                decimal_max(rrp_values)
            )

            snapshot_product.competitor_rrp_median = (
                decimal_median(rrp_values)
            )

            (
                deviation_amount,
                deviation_percent,
            ) = calculate_deviation(
                current_value=(
                    snapshot_product
                    .current_retail_median
                ),
                reference_value=(
                    snapshot_product
                    .competitor_rrp_median
                ),
            )

            snapshot_product.current_vs_competitor_amount = (
                deviation_amount
            )

            snapshot_product.current_vs_competitor_percent = (
                deviation_percent
            )

            if (
                snapshot_product.pricing_method
                == IPriceSnapshotProduct
                .PRICING_METHOD_ANALOG
                and not rrp_values
            ):
                snapshot_product.pricing_method = (
                    IPriceSnapshotProduct.PRICING_METHOD_EXCLUSIVE
                )
                snapshot_product.calculation_status = (
                    IPriceSnapshotProduct.STATUS_WARNING
                )
                warning_codes = list(snapshot_product.warning_codes or [])
                if "NO_VALID_COMPETITOR_PRICES" not in warning_codes:
                    warning_codes.append("NO_VALID_COMPETITOR_PRICES")
                snapshot_product.warning_codes = warning_codes
                snapshot_product.error_codes = [
                    code for code in (snapshot_product.error_codes or [])
                    if code != "NO_VALID_COMPETITOR_PRICES"
                ]

            products_to_update.append(
                snapshot_product
            )

        if products_to_update:
            (
                IPriceSnapshotProduct.objects
                .bulk_update(
                    products_to_update,
                    fields=[
                        "competitor_count",
                        "competitor_rrp_min",
                        "competitor_rrp_max",
                        "competitor_rrp_median",
                        (
                            "current_vs_"
                            "competitor_amount"
                        ),
                        (
                            "current_vs_"
                            "competitor_percent"
                        ),
                        "calculation_status",
                        "pricing_method",
                        "warning_codes",
                        "error_codes",
                    ],
                    batch_size=1000,
                )
            )

    result = {
        "snapshot_id": snapshot.id,
        "active_classifications": len(
            classifications
        ),
        "products_created": len(
            product_objects
        ),
        "competitors_created": len(
            competitor_objects
        ),
        "skipped_not_base": (
            skipped_not_base
        ),
        "missing_base_price": (
            missing_base_price
        ),
        "missing_code_1c": (
            missing_code_1c
        ),
        "missing_nomenclature": (
            missing_nomenclature
        ),
        "missing_config": missing_config,
        "missing_competitor_price": (
            missing_competitor_price
        ),
    }

    return result


def competitor_applies_to_region(
    *,
    competitor: IPriceSnapshotCompetitor,
    sale_region: str,
) -> bool:
    """
    Проверяет, относится ли конкурент
    к конкретному региону продажи.
    """

    if competitor.is_all_regions:
        return True

    normalized_region = (
        sale_region.strip().casefold()
    )

    applicable_regions = (
        competitor.applicable_regions
        or []
    )

    return any(
        str(region).strip().casefold()
        == normalized_region
        for region in applicable_regions
        if region
    )


def get_product_departures(
    *,
    product_key: int,
    calculation_date: date,
    workspace=None,
) -> list[str]:
    """
    Возвращает производства товара из конфигураций,
    применимых на дату расчёта.
    """
    IPriceCalculationConfig = workspace.model("IPriceCalculationConfig") if workspace else globals()["IPriceCalculationConfig"]


    queryset = IPriceCalculationConfig.objects.filter(
        product_key=product_key,
    )

    if calculation_date == timezone.localdate():
        queryset = queryset.filter(is_active=True)
    else:
        queryset = queryset.filter(
            date_add__date__lte=calculation_date,
        )

    values = (
        queryset
        .exclude(
            departure__isnull=True,
        )
        .exclude(
            departure="",
        )
        .values_list(
            "departure",
            flat=True,
        )
        .distinct()
    )

    result_by_key = {}

    for value in values:
        departure = str(value).strip()

        if not departure:
            continue

        result_by_key[
            departure.casefold()
        ] = departure

    return sorted(
        result_by_key.values(),
        key=str.casefold,
    )


def build_iprice_snapshot_regions(
    *,
    snapshot: IPriceSnapshot,
    config_overrides: dict | None = None,
    discount_overrides: dict | None = None,
    snapshot_product_ids: set[int] | None = None,
) -> dict:
    """
    Создает региональные строки snapshot.

    Гранулярность:

        snapshot_product
        + sale_region
        + departure

    Для каждой строки:

    1. Получаем себестоимость соответствующего месяца.
    2. Получаем цену 1С на calculation_date или ближайшую
       предыдущую дату.
    3. Получаем транспорт.
    4. Получаем количество в еврофуре.
    5. Рассчитываем себестоимость с логистикой.
    6. Определяем применимых конкурентов региона.
    7. Рассчитываем региональную медиану.
    8. Рассчитываем предварительную и итоговую РРЦ.
    9. Рассчитываем типы цен.
    """
    workspace = _snapshot_workspace(snapshot)
    if workspace and workspace.code == 'select-market':
        from select_market.iprice_regional_calculation import build_regions
        return build_regions(snapshot=snapshot, snapshot_product_ids=snapshot_product_ids)
    IPriceSnapshot = workspace.model("IPriceSnapshot") if workspace else globals()["IPriceSnapshot"]
    IPriceSnapshotCompetitor = workspace.model("IPriceSnapshotCompetitor") if workspace else globals()["IPriceSnapshotCompetitor"]
    IPriceSnapshotProduct = workspace.model("IPriceSnapshotProduct") if workspace else globals()["IPriceSnapshotProduct"]
    IPriceSnapshotRegion = workspace.model("IPriceSnapshotRegion") if workspace else globals()["IPriceSnapshotRegion"]
    Nomenclature = workspace.model("Nomenclature") if workspace else globals()["Nomenclature"]
    get_all_sale_regions = partial(globals()["get_all_sale_regions"], workspace=workspace)
    get_departure_discount = partial(globals()["get_departure_discount"], workspace=workspace)
    get_iprice_config = partial(globals()["get_iprice_config"], workspace=workspace)
    get_nomenclature_price = partial(globals()["get_nomenclature_price"], workspace=workspace)
    get_product_cost = partial(globals()["get_product_cost"], workspace=workspace)
    get_product_departures = partial(globals()["get_product_departures"], workspace=workspace)
    get_transport_cost = partial(globals()["get_transport_cost"], workspace=workspace)


    if (
        snapshot.status
        != IPriceSnapshot.STATUS_BUILDING
    ):
        raise IPriceSnapshotBuildError(
            (
                "Regions can be built only for "
                "a snapshot with status=building"
            )
        )

    config_overrides = config_overrides or {}
    discount_overrides = discount_overrides or {}

    calculation_date = (
        snapshot.calculation_date
    )

    snapshot_products_queryset = (
        IPriceSnapshotProduct.objects
        .filter(snapshot=snapshot)
        .prefetch_related(
            "competitors",
        )
        .order_by(
            "base_product_key",
        )
    )
    if snapshot_product_ids is not None:
        snapshot_products_queryset = snapshot_products_queryset.filter(
            id__in=set(snapshot_product_ids),
        )
    snapshot_products = list(snapshot_products_queryset)

    if not snapshot_products:
        raise IPriceSnapshotBuildError(
            (
                "Snapshot products are missing. "
                "Run build_iprice_snapshot_products first."
            )
        )

    sale_regions = get_all_sale_regions()

    if not sale_regions:
        raise IPriceSnapshotBuildError(
            "No sale regions found in ParserPrefix"
        )

    region_objects = []

    products_without_departures = 0
    missing_product_cost = 0
    missing_nomenclature_price = 0
    missing_transport_cost = 0
    missing_quantity_eurotruck = 0
    missing_discount = 0
    missing_config = 0
    no_regional_competitors = 0

    for snapshot_product in snapshot_products:
        product_key = (
            snapshot_product.base_product_key
        )

        code_1c = (
            snapshot_product.code_1c
        )

        nomenclature = (
            Nomenclature.objects
            .filter(
                nom_code=code_1c,
            )
            .order_by(
                "-id",
            )
            .first()
        )

        quantity_eurotruck = (
            nomenclature.quantity_eurotruck
            if nomenclature
            else None
        )

        departures = get_product_departures(
            product_key=product_key,
            calculation_date=calculation_date,
        )

        if not departures:
            products_without_departures += 1

            error_codes = list(
                snapshot_product.error_codes
                or []
            )

            if (
                "MISSING_DEPARTURE_DISCOUNT"
                not in error_codes
            ):
                error_codes.append(
                    "MISSING_DEPARTURE_DISCOUNT"
                )

            snapshot_product.error_codes = (
                error_codes
            )

            snapshot_product.calculation_status = (
                IPriceSnapshotProduct
                .STATUS_ERROR
            )

            snapshot_product.save(
                update_fields=[
                    "error_codes",
                    "calculation_status",
                ]
            )

            continue

        competitors = list(
            snapshot_product.competitors.all()
        )

        for departure in departures:
            for sale_region in sale_regions:
                warning_codes = []
                error_codes = []
                calculation_details = {}
                if "NO_VALID_COMPETITOR_PRICES" in (
                    snapshot_product.warning_codes or []
                ):
                    warning_codes.append("NO_VALID_COMPETITOR_PRICES")

                route_key = (
                    int(product_key),
                    str(departure).strip().casefold(),
                    str(sale_region).strip().casefold(),
                )

                config = config_overrides.get(
                    route_key,
                ) or get_iprice_config(
                    product_key=product_key,
                    departure=departure,
                    arrival=sale_region,
                    calculation_date=calculation_date,
                )
                discount = discount_overrides.get(
                    route_key,
                ) or get_departure_discount(
                    product_key=product_key,
                    departure=departure,
                    arrival=sale_region,
                    calculation_date=calculation_date,
                )

                product_cost_row = get_product_cost(
                    code=code_1c,
                    departure=departure,
                    calculation_date=calculation_date,
                )

                nomenclature_price_row = (
                    get_nomenclature_price(
                        code=code_1c,
                        shipp_region=sale_region,
                        calculation_date=calculation_date,
                    )
                )

                same_region = (
                    departure.strip().casefold()
                    == sale_region.strip().casefold()
                )

                transport_row = None
                transport_value = None

                if same_region:
                    transport_value = ZERO

                else:
                    transport_row = get_transport_cost(
                        departure=departure,
                        arrival=sale_region,
                        calculation_date=calculation_date,
                    )

                    if transport_row is not None:
                        transport_value = (
                            transport_row.cost
                        )

                if product_cost_row is None:
                    missing_product_cost += 1
                    error_codes.append(
                        "MISSING_PRODUCT_COST"
                    )

                if nomenclature_price_row is None:
                    missing_nomenclature_price += 1
                    warning_codes.append(
                        "MISSING_NOMENCLATURE_PRICE"
                    )

                if (
                    not same_region
                    and transport_row is None
                ):
                    missing_transport_cost += 1
                    error_codes.append(
                        "MISSING_TRANSPORT_COST"
                    )

                if (
                    quantity_eurotruck is None
                    or quantity_eurotruck <= 0
                ):
                    missing_quantity_eurotruck += 1
                    error_codes.append(
                        "MISSING_QUANTITY_EUROTRUCK"
                    )

                if discount is None:
                    missing_discount += 1
                    error_codes.append(
                        "MISSING_DEPARTURE_DISCOUNT"
                    )

                if config is None:
                    missing_config += 1
                    error_codes.append(
                        "MISSING_CALCULATION_CONFIG"
                    )

                product_cost_value = (
                    product_cost_row.cost
                    if product_cost_row
                    else None
                )

                logistics_unit = None
                cost_with_logistics = None

                if (
                    transport_value is not None
                    and quantity_eurotruck is not None
                    and quantity_eurotruck > 0
                ):
                    logistics_unit = (
                        Decimal(transport_value)
                        / Decimal(
                            quantity_eurotruck
                        )
                    )

                if (
                    product_cost_value is not None
                    and logistics_unit is not None
                ):
                    cost_with_logistics = (
                        Decimal(
                            product_cost_value
                        )
                        + Decimal(
                            logistics_unit
                        )
                    )

                applicable_competitors = [
                    competitor
                    for competitor in competitors
                    if (
                        competitor.calculation_status
                        == "success"
                        and competitor.competitor_final_price_max
                        is not None
                        and competitor_applies_to_region(
                            competitor=competitor,
                            sale_region=sale_region,
                        )
                    )
                ]

                competitor_rrps = [
                    Decimal(
                        competitor.competitor_final_price_max
                    )
                    for competitor
                    in applicable_competitors
                ]

                regional_competitor_min = (
                    decimal_min(
                        competitor_rrps
                    )
                )

                regional_competitor_max = (
                    decimal_max(
                        competitor_rrps
                    )
                )

                regional_competitor_median = (
                    decimal_median(
                        competitor_rrps
                    )
                )

                if (
                    snapshot_product.pricing_method
                    == IPriceSnapshotProduct
                    .PRICING_METHOD_ANALOG
                    and not competitor_rrps
                ):
                    no_regional_competitors += 1
                    warning_codes.append(
                        "NO_REGIONAL_COMPETITORS"
                    )

                preliminary_rrp = None

                if (
                    snapshot_product.pricing_method
                    == IPriceSnapshotProduct
                    .PRICING_METHOD_ANALOG
                    and regional_competitor_median
                    is not None
                    and config is not None
                ):
                    preliminary_rrp = (
                        Decimal(
                            regional_competitor_median
                        )
                        * Decimal(config.base_analog)
                    )

                elif (
                    (
                        snapshot_product.pricing_method
                        == IPriceSnapshotProduct.PRICING_METHOD_EXCLUSIVE
                        or not competitor_rrps
                    )
                    and cost_with_logistics is not None
                    and config is not None
                ):
                    exclusive_denominator = (
                        ONE
                        - Decimal(
                            config.base_exclusive
                        )
                    )

                    if exclusive_denominator > 0:
                        preliminary_rrp = (
                            Decimal(
                                cost_with_logistics
                            )
                            / exclusive_denominator
                        )

                minimum_price = None
                minimum_allowed_rrp = None

                if (
                    cost_with_logistics is not None
                    and config is not None
                ):
                    minimum_price = (
                        calculate_minimum_price(
                            cost_with_logistics=(
                                cost_with_logistics
                            ),
                            minimum_margin=(
                                config.minimum_margin
                            ),
                        )
                    )

                if (
                    minimum_price is not None
                    and discount is not None
                ):
                    minimum_allowed_rrp = (
                        calculate_minimum_allowed_rrp(
                            minimum_price=(
                                minimum_price
                            ),
                            distr_discount=(
                                discount.distr
                            ),
                        )
                    )

                calculated_rrp_raw = None

                if (
                    preliminary_rrp is not None
                    and minimum_allowed_rrp
                    is not None
                ):
                    calculated_rrp_raw = max(
                        Decimal(
                            preliminary_rrp
                        ),
                        Decimal(
                            minimum_allowed_rrp
                        ),
                    )

                elif preliminary_rrp is not None:
                    calculated_rrp_raw = Decimal(
                        preliminary_rrp
                    )

                calculated_rrp = round_price(
                    calculated_rrp_raw
                )

                minimum_price_rounded = round_price(
                    minimum_price
                )

                preliminary_rrp_rounded = (
                    round_price(
                        preliminary_rrp
                    )
                )

                default_approved_rrp = (
                    calculated_rrp
                )

                calculated_distr = None
                calculated_distr_1 = None
                calculated_small = None
                calculated_medium = None
                calculated_large = None

                if (
                    default_approved_rrp
                    is not None
                    and discount is not None
                ):
                    calculated_distr = (
                        calculate_discount_price(
                            rrp=(
                                default_approved_rrp
                            ),
                            discount=discount.distr,
                        )
                    )

                    calculated_distr_1 = (
                        calculate_discount_price(
                            rrp=(
                                default_approved_rrp
                            ),
                            discount=(
                                discount.distr_1
                            ),
                        )
                    )

                    calculated_small = (
                        calculate_discount_price(
                            rrp=(
                                default_approved_rrp
                            ),
                            discount=discount.small,
                        )
                    )

                    calculated_medium = (
                        calculate_discount_price(
                            rrp=(
                                default_approved_rrp
                            ),
                            discount=(
                                discount.medium
                            ),
                        )
                    )

                    calculated_large = (
                        calculate_discount_price(
                            rrp=(
                                default_approved_rrp
                            ),
                            discount=discount.large,
                        )
                    )

                current_retail = (
                    nomenclature_price_row.retail
                    if nomenclature_price_row
                    else None
                )

                margin_current = (
                    calculate_margin(
                        price=current_retail,
                        cost=cost_with_logistics,
                    )
                )

                margin_calculated = (
                    calculate_margin(
                        price=calculated_rrp,
                        cost=cost_with_logistics,
                    )
                )

                (
                    _,
                    current_vs_calculated_percent,
                ) = calculate_deviation(
                    current_value=current_retail,
                    reference_value=(
                        calculated_rrp
                    ),
                )

                if error_codes:
                    calculation_status = (
                        IPriceSnapshotRegion
                        .STATUS_ERROR
                    )

                elif warning_codes:
                    calculation_status = (
                        IPriceSnapshotRegion
                        .STATUS_WARNING
                    )

                else:
                    calculation_status = (
                        IPriceSnapshotRegion
                        .STATUS_SUCCESS
                    )

                calculation_details.update({
                    "same_region_transport_zero": (
                        same_region
                    ),
                    "minimum_allowed_rrp": (
                        str(minimum_allowed_rrp)
                        if minimum_allowed_rrp
                        is not None
                        else None
                    ),
                    "applicable_competitor_ids": [
                        competitor.id
                        for competitor
                        in applicable_competitors
                    ],
                    "applicable_competitor_keys": [
                        competitor
                        .competitor_product_key
                        for competitor
                        in applicable_competitors
                    ],
                })

                region_objects.append(
                    IPriceSnapshotRegion(
                        snapshot_product=(
                            snapshot_product
                        ),
                        sale_region=sale_region,
                        departure=departure,

                        product_cost_source_id=(
                            product_cost_row.id
                            if product_cost_row
                            else None
                        ),
                        transport_cost_source_id=(
                            transport_row.id
                            if transport_row
                            else None
                        ),
                        nomenclature_price_source_id=(
                            nomenclature_price_row.id
                            if nomenclature_price_row
                            else None
                        ),
                        departure_discount_source_id=(
                            discount.id
                            if discount
                            else None
                        ),
                        calculation_config_source_id=(
                            config.id
                            if config
                            else None
                        ),

                        product_cost_month=(
                            product_cost_row.date
                            if product_cost_row
                            else calculation_date.replace(
                                day=1
                            )
                        ),
                        nomenclature_price_date=(
                            nomenclature_price_row.date
                            if nomenclature_price_row
                            else None
                        ),

                        current_retail=(
                            current_retail
                        ),
                        current_distr=(
                            nomenclature_price_row.distr
                            if nomenclature_price_row
                            else None
                        ),
                        current_distr_1=(
                            nomenclature_price_row.distr_1
                            if nomenclature_price_row
                            else None
                        ),
                        current_small=(
                            nomenclature_price_row.small
                            if nomenclature_price_row
                            else None
                        ),
                        current_medium=(
                            nomenclature_price_row.medium
                            if nomenclature_price_row
                            else None
                        ),
                        current_large=(
                            nomenclature_price_row.large
                            if nomenclature_price_row
                            else None
                        ),

                        product_cost=(
                            product_cost_value
                        ),
                        transport_cost=(
                            transport_value
                        ),
                        quantity_eurotruck=(
                            quantity_eurotruck
                        ),
                        logistics_unit=(
                            logistics_unit
                        ),
                        cost_with_logistics=(
                            cost_with_logistics
                        ),

                        regional_competitor_count=(
                            len(
                                applicable_competitors
                            )
                        ),
                        regional_competitor_rrp_min=(
                            regional_competitor_min
                        ),
                        regional_competitor_rrp_max=(
                            regional_competitor_max
                        ),
                        regional_competitor_rrp_median=(
                            regional_competitor_median
                        ),

                        base_analog=(
                            config.base_analog
                            if config
                            else None
                        ),
                        base_exclusive=(
                            config.base_exclusive
                            if config
                            else None
                        ),
                        minimum_margin=(
                            config.minimum_margin
                            if config
                            else None
                        ),

                        discount_distr=(
                            discount.distr
                            if discount
                            else None
                        ),
                        discount_distr_1=(
                            discount.distr_1
                            if discount
                            else None
                        ),
                        discount_small=(
                            discount.small
                            if discount
                            else None
                        ),
                        discount_medium=(
                            discount.medium
                            if discount
                            else None
                        ),
                        discount_large=(
                            discount.large
                            if discount
                            else None
                        ),

                        preliminary_rrp=(
                            preliminary_rrp_rounded
                        ),
                        minimum_price=(
                            minimum_price_rounded
                        ),
                        calculated_rrp=(
                            calculated_rrp
                        ),
                        default_approved_rrp=(
                            default_approved_rrp
                        ),

                        calculated_distr=(
                            calculated_distr
                        ),
                        calculated_distr_1=(
                            calculated_distr_1
                        ),
                        calculated_small=(
                            calculated_small
                        ),
                        calculated_medium=(
                            calculated_medium
                        ),
                        calculated_large=(
                            calculated_large
                        ),

                        margin_current=(
                            margin_current
                        ),
                        margin_calculated=(
                            margin_calculated
                        ),
                        current_vs_calculated_percent=(
                            current_vs_calculated_percent
                        ),

                        calculation_status=(
                            calculation_status
                        ),
                        warning_codes=(
                            warning_codes
                        ),
                        error_codes=error_codes,
                        calculation_details=(
                            calculation_details
                        ),
                    )
                )

    competitor_prices_by_product = {}
    seen_competitors_by_product = {}
    for competitor in (
        IPriceSnapshotCompetitor.objects
        .filter(snapshot_product__snapshot=snapshot)
        .values(
            "snapshot_product_id",
            "source",
            "competitor_product_key",
            "competitor_final_price_max",
        )
    ):
        price = competitor["competitor_final_price_max"]
        if price is None:
            continue
        product_id = competitor["snapshot_product_id"]
        identity = (
            str(competitor["source"] or "").strip().casefold(),
            competitor["competitor_product_key"],
        )
        seen = seen_competitors_by_product.setdefault(product_id, set())
        if identity in seen:
            continue
        seen.add(identity)
        competitor_prices_by_product.setdefault(product_id, []).append(price)

    with transaction.atomic():
        regions_to_replace = IPriceSnapshotRegion.objects.filter(
            snapshot_product__snapshot=snapshot,
        )
        if snapshot_product_ids is not None:
            regions_to_replace = regions_to_replace.filter(
                snapshot_product_id__in=set(snapshot_product_ids),
            )
        regions_to_replace.delete()

        if region_objects:
            IPriceSnapshotRegion.objects.bulk_create(
                region_objects,
                batch_size=1000,
            )

        regions_by_product = {}
        for region in region_objects:
            regions_by_product.setdefault(
                region.snapshot_product_id,
                [],
            ).append(region)

        products_to_update = []
        for snapshot_product in snapshot_products:
            product_regions = regions_by_product.get(
                snapshot_product.id,
                [],
            )
            if not product_regions:
                continue

            competitor_prices = competitor_prices_by_product.get(
                snapshot_product.id,
                [],
            )
            calculated_rrps = [
                row.calculated_rrp
                for row in product_regions
                if row.calculated_rrp is not None
            ]
            base_analogs = [
                row.base_analog
                for row in product_regions
                if row.base_analog is not None
            ]
            base_exclusives = [
                row.base_exclusive
                for row in product_regions
                if row.base_exclusive is not None
            ]
            minimum_margins = [
                row.minimum_margin
                for row in product_regions
                if row.minimum_margin is not None
            ]
            effective_approved_rrps = [
                row.default_approved_rrp
                for row in product_regions
                if row.default_approved_rrp is not None
            ]
            parameter_medians = {}
            for detail_name, region_field in (
                ("discount_distr_median", "discount_distr"),
                ("discount_distr_1_median", "discount_distr_1"),
                ("discount_small_median", "discount_small"),
                ("discount_medium_median", "discount_medium"),
                ("discount_large_median", "discount_large"),
                ("effective_distr_median", "calculated_distr"),
                ("effective_distr_1_median", "calculated_distr_1"),
                ("effective_small_median", "calculated_small"),
                ("effective_medium_median", "calculated_medium"),
                ("effective_large_median", "calculated_large"),
            ):
                values = [
                    getattr(row, region_field)
                    for row in product_regions
                    if getattr(row, region_field) is not None
                ]
                parameter_medians[detail_name] = (
                    str(decimal_median(values)) if values else None
                )

            snapshot_product.competitor_rrp_min = decimal_min(
                competitor_prices
            )
            snapshot_product.competitor_rrp_max = decimal_max(
                competitor_prices
            )
            snapshot_product.competitor_rrp_median = decimal_median(
                competitor_prices
            )
            (
                snapshot_product.current_vs_competitor_amount,
                snapshot_product.current_vs_competitor_percent,
            ) = calculate_deviation(
                current_value=snapshot_product.current_retail_median,
                reference_value=snapshot_product.competitor_rrp_median,
            )

            details = dict(snapshot_product.calculation_details or {})
            details.update({
                "calculated_rrp_median": (
                    str(decimal_median(calculated_rrps))
                    if calculated_rrps else None
                ),
                "base_analog_median": (
                    str(decimal_median(base_analogs))
                    if base_analogs else None
                ),
                "base_exclusive_median": (
                    str(decimal_median(base_exclusives))
                    if base_exclusives else None
                ),
                "minimum_margin_median": (
                    str(decimal_median(minimum_margins))
                    if minimum_margins else None
                ),
                "calculation_config_region_count": len(
                    base_analogs
                ),
                **parameter_medians,
            })
            snapshot_product.calculation_details = details
            snapshot_product.effective_approved_rrp_median = (
                decimal_median(effective_approved_rrps)
            )
            snapshot_product.current_vs_approved_amount = (
                Decimal(snapshot_product.current_retail_median)
                - Decimal(
                    snapshot_product.effective_approved_rrp_median
                )
                if (
                    snapshot_product.current_retail_median is not None
                    and snapshot_product.effective_approved_rrp_median
                    is not None
                )
                else None
            )

            if any(
                row.calculation_status == IPriceSnapshotRegion.STATUS_ERROR
                for row in product_regions
            ):
                snapshot_product.calculation_status = (
                    IPriceSnapshotProduct.STATUS_ERROR
                )
            elif any(
                row.calculation_status == IPriceSnapshotRegion.STATUS_WARNING
                for row in product_regions
            ):
                snapshot_product.calculation_status = (
                    IPriceSnapshotProduct.STATUS_WARNING
                )
            else:
                snapshot_product.calculation_status = (
                    IPriceSnapshotProduct.STATUS_SUCCESS
                )
            products_to_update.append(snapshot_product)

        if products_to_update:
            IPriceSnapshotProduct.objects.bulk_update(
                products_to_update,
                fields=[
                    "competitor_rrp_min",
                    "competitor_rrp_max",
                    "competitor_rrp_median",
                    "current_vs_competitor_amount",
                    "current_vs_competitor_percent",
                    "calculation_status",
                    "calculation_details",
                    "effective_approved_rrp_median",
                    "current_vs_approved_amount",
                ],
                batch_size=1000,
            )

    return {
        "snapshot_id": snapshot.id,
        "products": len(
            snapshot_products
        ),
        "sale_regions": len(
            sale_regions
        ),
        "region_rows_created": len(
            region_objects
        ),
        "products_without_departures": (
            products_without_departures
        ),
        "missing_product_cost": (
            missing_product_cost
        ),
        "missing_nomenclature_price": (
            missing_nomenclature_price
        ),
        "missing_transport_cost": (
            missing_transport_cost
        ),
        "missing_quantity_eurotruck": (
            missing_quantity_eurotruck
        ),
        "missing_discount": (
            missing_discount
        ),
        "missing_config": missing_config,
        "no_regional_competitors": (
            no_regional_competitors
        ),
    }


def validate_iprice_snapshot_result(
    *,
    snapshot: IPriceSnapshot,
) -> dict:
    """
    Проверяет, что построенный snapshot содержит данные.

    Ошибки отдельных товаров и регионов не прерывают
    построение всего snapshot: такие строки сохраняются
    со своими error_codes.

    Критической ошибкой считается отсутствие:
    - товаров snapshot;
    - региональных строк snapshot.
    """
    workspace = _snapshot_workspace(snapshot)
    IPriceSnapshot = workspace.model("IPriceSnapshot") if workspace else globals()["IPriceSnapshot"]
    IPriceSnapshotRegion = workspace.model("IPriceSnapshotRegion") if workspace else globals()["IPriceSnapshotRegion"]


    products_count = (
        snapshot.products.count()
    )

    regions_queryset = (
        IPriceSnapshotRegion.objects
        .filter(
            snapshot_product__snapshot=snapshot,
        )
    )

    regions_count = (
        regions_queryset.count()
    )

    successful_regions = (
        regions_queryset
        .filter(
            calculation_status=(
                IPriceSnapshotRegion
                .STATUS_SUCCESS
            ),
        )
        .count()
    )

    warning_regions = (
        regions_queryset
        .filter(
            calculation_status=(
                IPriceSnapshotRegion
                .STATUS_WARNING
            ),
        )
        .count()
    )

    error_regions = (
        regions_queryset
        .filter(
            calculation_status=(
                IPriceSnapshotRegion
                .STATUS_ERROR
            ),
        )
        .count()
    )

    critical_errors = []

    if products_count == 0:
        critical_errors.append(
            "SNAPSHOT_PRODUCTS_EMPTY"
        )

    if regions_count == 0:
        critical_errors.append(
            "SNAPSHOT_REGIONS_EMPTY"
        )

    return {
        "is_valid": not critical_errors,
        "critical_errors": critical_errors,
        "products_count": products_count,
        "regions_count": regions_count,
        "successful_regions": (
            successful_regions
        ),
        "warning_regions": warning_regions,
        "error_regions": error_regions,
    }


def send_iprice_snapshot_success_message(
    *,
    snapshot: IPriceSnapshot,
    result: dict,
):
    """
    Отправляет итог успешного построения snapshot.
    """
    if _snapshot_workspace(snapshot):
        return
    workspace = _snapshot_workspace(snapshot)
    IPriceSnapshot = workspace.model("IPriceSnapshot") if workspace else globals()["IPriceSnapshot"]


    validation = result["validation"]

    message = (
        "iPrice snapshot рассчитан\n"
        f"Версия: {snapshot.display_version}\n"
        f"Дата расчета: "
        f"{snapshot.calculation_date:%d.%m.%Y}\n"
        f"Техническая версия за дату: "
        f"{snapshot.revision_for_date}\n"
        f"Товаров: "
        f"{validation['products_count']}\n"
        f"Региональных строк: "
        f"{validation['regions_count']}\n"
        f"Успешно: "
        f"{validation['successful_regions']}\n"
        f"С предупреждениями: "
        f"{validation['warning_regions']}\n"
        f"С ошибками: "
        f"{validation['error_regions']}"
    )

    send_bitrix_message(
        message,
    )


def send_iprice_snapshot_error_message(
    *,
    snapshot: IPriceSnapshot,
    error: Exception | str,
):
    """
    Отправляет сообщение об ошибке построения snapshot.
    """
    if _snapshot_workspace(snapshot):
        return
    workspace = _snapshot_workspace(snapshot)
    IPriceSnapshot = workspace.model("IPriceSnapshot") if workspace else globals()["IPriceSnapshot"]


    message = (
        "Ошибка построения iPrice snapshot\n"
        f"Версия: {snapshot.display_version}\n"
        f"Дата расчета: "
        f"{snapshot.calculation_date:%d.%m.%Y}\n"
        f"Этап: "
        f"{snapshot.parameters.get('current_step', 'unknown')}\n"
        f"Ошибка: {str(error)[:1500]}"
    )

    send_bitrix_message(
        message,
    )


def build_created_iprice_snapshot(
    *,
    snapshot: IPriceSnapshot,
) -> dict:
    """
    Выполняет полный расчет для уже созданного snapshot.

    Snapshot должен находиться в статусе building.
    """
    workspace = _snapshot_workspace(snapshot)
    IPriceSnapshot = workspace.model("IPriceSnapshot") if workspace else globals()["IPriceSnapshot"]


    if (
        snapshot.status
        != IPriceSnapshot.STATUS_BUILDING
    ):
        raise IPriceSnapshotBuildError(
            (
                "Snapshot must have status=building, "
                f"current status={snapshot.status}"
            )
        )

    try:
        snapshot.parameters = {
            **snapshot.parameters,
            "current_step": (
                "building_products"
            ),
        }

        snapshot.save(
            update_fields=[
                "parameters",
            ]
        )

        products_result = (
            build_iprice_snapshot_products(
                snapshot=snapshot,
            )
        )

        snapshot.parameters = {
            **snapshot.parameters,
            "current_step": (
                "building_regions"
            ),
            "products_result": (
                products_result
            ),
        }

        snapshot.save(
            update_fields=[
                "parameters",
            ]
        )

        regions_result = (
            build_iprice_snapshot_regions(
                snapshot=snapshot,
            )
        )

        snapshot.parameters = {
            **snapshot.parameters,
            "current_step": "validating",
            "regions_result": regions_result,
        }

        snapshot.save(
            update_fields=[
                "parameters",
            ]
        )

        validation_result = (
            validate_iprice_snapshot_result(
                snapshot=snapshot,
            )
        )

        if not validation_result["is_valid"]:
            raise IPriceSnapshotBuildError(
                (
                    "Snapshot validation failed: "
                    + ", ".join(
                        validation_result[
                            "critical_errors"
                        ]
                    )
                )
            )

        snapshot.parameters = {
            **snapshot.parameters,
            "current_step": "completed",
            "products_result": (
                products_result
            ),
            "regions_result": (
                regions_result
            ),
            "validation": (
                validation_result
            ),
        }

        snapshot.save(
            update_fields=[
                "parameters",
            ]
        )

        snapshot = complete_iprice_snapshot(
            snapshot=snapshot,
        )

        _publish_snapshot(
            snapshot,
            "snapshot_finished",
        )

        result = {
            "status": "success",
            "snapshot_id": snapshot.id,
            "version_number": (
                snapshot.version_number
            ),
            "revision_for_date": (
                snapshot.revision_for_date
            ),
            "display_version": (
                snapshot.display_version
            ),
            "calculation_date": (
                snapshot
                .calculation_date
                .isoformat()
            ),
            "products": products_result,
            "regions": regions_result,
            "validation": validation_result,
        }

        try:
            send_iprice_snapshot_success_message(
                snapshot=snapshot,
                result=result,
            )
        except Exception:
            # Ошибка Битрикса не должна превращать
            # успешно рассчитанный snapshot в failed.
            pass

        return result

    except Exception as exc:
        error_traceback = (
            traceback.format_exc()
        )

        snapshot.parameters = {
            **snapshot.parameters,
            "failed_step": (
                snapshot.parameters.get(
                    "current_step",
                    "unknown",
                )
            ),
            "traceback": error_traceback,
        }

        snapshot.save(
            update_fields=[
                "parameters",
            ]
        )

        snapshot = fail_iprice_snapshot(
            snapshot=snapshot,
            error=exc,
        )

        _publish_snapshot(
            snapshot,
            "snapshot_failed",
            metadata_only=True,
        )

        try:
            send_iprice_snapshot_error_message(
                snapshot=snapshot,
                error=exc,
            )
        except Exception:
            pass

        raise IPriceSnapshotBuildError(
            (
                "iPrice snapshot build failed: "
                f"{exc}"
            )
        ) from exc


def build_iprice_snapshot(
    *,
    calculation_date: date,
    created_by=None,
    parameters: dict | None = None,
    workspace=None,
) -> dict:
    """
    Создает snapshot и выполняет полный расчет.

    Используется management-командой при ручном запуске
    только по дате.
    """
    create_iprice_snapshot = partial(globals()["create_iprice_snapshot"], workspace=workspace)


    if parameters is None:
        parameters = {}

    snapshot = create_iprice_snapshot(
        calculation_date=calculation_date,
        created_by=created_by,
        parameters={
            **parameters,
            "current_step": "created",
        },
    )

    return build_created_iprice_snapshot(
        snapshot=snapshot,
    )
