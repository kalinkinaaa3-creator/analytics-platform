from __future__ import annotations

import logging
import re
from collections import defaultdict
from urllib.parse import unquote, urlsplit, urlunsplit

from django.utils import timezone

from django.db import transaction

from datasets.models import (
    ParserPrefix,
    ParserProductMatch,
    ParserProductUrl,
    ParserProductClassification,
)

from datasets.services.parsers.product_classification_loader import (
    enrich_classification_urls_and_images,
)


logger = logging.getLogger(
    "parser_product_match.datasets"
)

CLASSIFICATION_COPY_FIELDS = (
    "category",
    "subcategory",
    "subcategory_type",
    "material",
    "color",
    "modification",
    "item_type",
)

# ============================================================
# BASIC CLEANING
# ============================================================


def clean_text(value):
    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    return value


# ============================================================
# URL NORMALIZATION
# ============================================================


def normalize_prefix(value):
    """
    Нормализует prefix из ParserProductUrl/ParserPrefix.

    Значения:
        None
        ""
        "-"

    считаются отсутствием префикса.
    """

    value = clean_text(value)

    if (
        value is None
        or value == "-"
    ):
        return None

    return value.casefold()


def is_without_prefix_marker(
    prefix,
):
    """
    Например:

        spb_withoutprefix

    означает, что региональный URL не содержит
    отдельного регионального префикса.
    """

    prefix = normalize_prefix(prefix)

    return bool(
        prefix
        and prefix.endswith(
            "_withoutprefix"
        )
    )


def get_real_prefix_value(
    prefix,
):
    """
    Возвращает фактическую строку префикса,
    которую можно искать в hostname/path.

    Для *_withoutprefix возвращает None.
    """

    prefix = normalize_prefix(prefix)

    if (
        not prefix
        or is_without_prefix_marker(
            prefix
        )
    ):
        return None

    return prefix


def normalize_hostname(
    hostname,
):
    hostname = clean_text(hostname)

    if not hostname:
        return ""

    hostname = hostname.casefold()

    if hostname.startswith("www."):
        hostname = hostname[4:]

    return hostname


def normalize_url_path(
    path,
):
    """
    Нормализует URL path:

    - URL decode;
    - повторные / заменяет одной;
    - гарантирует начальный /;
    - убирает завершающий /,
      кроме корневого пути.
    """

    path = unquote(
        path or "/"
    )

    path = re.sub(
        r"/+",
        "/",
        path,
    )

    if not path.startswith("/"):
        path = f"/{path}"

    if (
        len(path) > 1
        and path.endswith("/")
    ):
        path = path.rstrip("/")

    return path


def strip_regional_subdomain(
    *,
    hostname,
    prefixes,
):
    """
    Удаляет известный региональный поддомен.

    Например:

        moskva.tara.ru
        ->
        tara.ru

        ekaterinburg.tara.ru
        ->
        tara.ru

    Маркеры *_withoutprefix не участвуют.
    """

    hostname = normalize_hostname(
        hostname
    )

    real_prefixes = sorted(
        {
            real_prefix
            for prefix in prefixes
            for real_prefix in [
                get_real_prefix_value(
                    prefix
                )
            ]
            if real_prefix
        },
        key=len,
        reverse=True,
    )

    for prefix in real_prefixes:
        prefix_with_dot = (
            f"{prefix}."
        )

        if hostname.startswith(
            prefix_with_dot
        ):
            return hostname[
                len(prefix_with_dot):
            ]

    return hostname


def strip_regional_path_prefix(
    *,
    path,
    prefixes,
):
    """
    Дополнительная защита для источников,
    где регион может находиться первым
    сегментом URL path.

    Например:

        /msk/catalog/product
        ->
        /catalog/product

    Для текущих tara/ps чаще используется hostname,
    но поддержка path не мешает.
    """

    path = normalize_url_path(
        path
    )

    parts = [
        part
        for part in path.split("/")
        if part
    ]

    if not parts:
        return "/"

    real_prefixes = {
        real_prefix
        for prefix in prefixes
        for real_prefix in [
            get_real_prefix_value(
                prefix
            )
        ]
        if real_prefix
    }

    if parts[0].casefold() in real_prefixes:
        parts = parts[1:]

    if not parts:
        return "/"

    return "/" + "/".join(parts)


def normalize_product_url(
    *,
    url,
    source_prefixes,
):
    """
    Формирует URL-ключ для поиска региональных копий товара.

    Правила:

    1. схема не влияет на сравнение;
    2. hostname приводится к нижнему регистру;
    3. www удаляется;
    4. известный региональный поддомен удаляется;
    5. известный региональный первый path-сегмент удаляется;

    """

    url = clean_text(url)

    if not url:
        return None

    # urlsplit не распознает hostname без схемы.
    parsed_value = url

    if "://" not in parsed_value:
        parsed_value = (
            f"https://{parsed_value}"
        )

    try:
        parsed = urlsplit(
            parsed_value
        )

    except ValueError:
        return None

    hostname = normalize_hostname(
        parsed.hostname
    )

    if not hostname:
        return None

    hostname = strip_regional_subdomain(
        hostname=hostname,
        prefixes=source_prefixes,
    )

    path = strip_regional_path_prefix(
        path=parsed.path,
        prefixes=source_prefixes,
    )

    # Схему намеренно не используем в ключе.
    normalized = urlunsplit(
        (
            "",
            hostname,
            path.casefold(),
            parsed.query,
            "",
        )
    )

    # urlunsplit с пустой схемой возвращает //host/path.
    return normalized.lstrip("/")


# ============================================================
# PREFIX CONFIGURATION
# ============================================================


def get_prefixes_by_source():
    """
    Возвращает prefix-конфигурацию по source.

    Если source вообще отсутствует в ParserPrefix,
    автоматическое размножение для него не выполняется.

    Это покрывает TT:
        если строк TT в ParserPrefix нет,
        TT match остается только ручным.
    """

    result = defaultdict(set)

    rows = (
        ParserPrefix.objects
        .exclude(
            source__isnull=True,
        )
        .exclude(
            source="",
        )
        .exclude(
            prefix__isnull=True,
        )
        .exclude(
            prefix="",
        )
        .values(
            "source",
            "prefix",
        )
    )

    for row in rows:
        source = clean_text(
            row["source"]
        )

        prefix = clean_text(
            row["prefix"]
        )

        if (
            not source
            or not prefix
        ):
            continue

        result[
            source.casefold()
        ].add(
            prefix.casefold()
        )

    return result


# ============================================================
# URL GROUP BUILDING
# ============================================================


def build_competitor_url_groups(
    *,
    prefixes_by_source,
):
    """
    Группирует ACTIVE конкурентные ParserProductUrl:

        source
        +
        нормализованный URL
        ->
        набор региональных product_key

    Для source, которого нет в ParserPrefix,
    группы не формируются.

    Поэтому TT без записей ParserPrefix
    автоматически не размножается.
    """

    groups = defaultdict(set)
    url_group_key_by_product = {}

    configured_sources = set(
        prefixes_by_source
    )

    if not configured_sources:
        return (
            groups,
            url_group_key_by_product,
        )

    competitor_urls = (
        ParserProductUrl.objects
        .filter(
            status=(
                ParserProductUrl
                .STATUS_ACTIVE
            ),
            source__in=(
                configured_sources
            ),
        )
        .exclude(
            source="base",
        )
        .only(
            "id",
            "source",
            "url",
            "prefix",
        )
        .order_by(
            "source",
            "id",
        )
    )

    for url_obj in competitor_urls.iterator(chunk_size=1000):
        source = clean_text(
            url_obj.source
        )

        if not source:
            continue

        source_key = source.casefold()

        source_prefixes = (
            prefixes_by_source.get(
                source_key,
                set(),
            )
        )

        if not source_prefixes:
            continue

        normalized_url = (
            normalize_product_url(
                url=url_obj.url,
                source_prefixes=(
                    source_prefixes
                ),
            )
        )

        if not normalized_url:
            continue

        group_key = (
            source_key,
            normalized_url,
        )

        groups[group_key].add(
            url_obj.id
        )

        url_group_key_by_product[
            url_obj.id
        ] = group_key

    return (
        groups,
        url_group_key_by_product,
    )


# ============================================================
# DESIRED ACTIVE MATCHES
# ============================================================


def normalize_classification_value(value):
    value = clean_text(value)

    if value is None:
        return None

    return " ".join(
        value.casefold().split()
    )


def classification_match_signature(row):
    signature = tuple(
        normalize_classification_value(
            row[field_name]
        )
        for field_name
        in CLASSIFICATION_COPY_FIELDS
    )

    if any(value is None for value in signature):
        return None

    return signature


def build_classification_match_set(
    *,
    prefixes_by_source=None,
    competitor_groups=None,
    competitor_group_key_by_product=None,
):
    """Формирует ожидаемые связи из активной классификации."""

    prefixes_by_source = (
        prefixes_by_source
        if prefixes_by_source is not None
        else get_prefixes_by_source()
    )

    if (
        competitor_groups is None
        or competitor_group_key_by_product is None
    ):
        (
            competitor_groups,
            competitor_group_key_by_product,
        ) = build_competitor_url_groups(
            prefixes_by_source=prefixes_by_source,
        )

    classification_rows = list(
        ParserProductClassification.objects
        .filter(
            status=(
                ParserProductClassification
                .STATUS_ACTIVE
            ),
        )
        .values(
            "product_key",
            *CLASSIFICATION_COPY_FIELDS,
        )
        .order_by("product_key")
    )

    product_keys = {
        row["product_key"]
        for row in classification_rows
    }

    url_rows = {
        row["id"]: row
        for row in (
            ParserProductUrl.objects
            .filter(
                id__in=product_keys,
                status=(
                    ParserProductUrl
                    .STATUS_ACTIVE
                ),
            )
            .values(
                "id",
                "source",
            )
        )
    }

    base_by_signature = defaultdict(set)
    competitors_by_signature = defaultdict(set)
    incomplete_classifications = 0
    classifications_without_active_url = 0

    for row in classification_rows:
        url_row = url_rows.get(
            row["product_key"]
        )

        if url_row is None:
            classifications_without_active_url += 1
            continue

        signature = classification_match_signature(
            row
        )

        if signature is None:
            incomplete_classifications += 1
            continue

        source = normalize_classification_value(
            url_row["source"]
        )

        if source == "base":
            base_by_signature[signature].add(
                row["product_key"]
            )
        elif source:
            competitors_by_signature[
                signature
            ].add(row["product_key"])

    primary_pairs = set()

    for signature in (
        set(base_by_signature)
        & set(competitors_by_signature)
    ):
        for base_key in base_by_signature[signature]:
            for competitor_key in (
                competitors_by_signature[signature]
            ):
                primary_pairs.add(
                    (base_key, competitor_key)
                )

    desired_pairs = set(primary_pairs)

    for base_key, competitor_key in primary_pairs:
        group_key = (
            competitor_group_key_by_product.get(
                competitor_key
            )
        )

        if group_key is None:
            continue

        for regional_key in competitor_groups.get(
            group_key,
            set(),
        ):
            desired_pairs.add(
                (base_key, regional_key)
            )

    return {
        "desired_types": {
            pair: ParserProductMatch.MATCH_TYPE_AUTO
            for pair in sorted(desired_pairs)
        },
        "desired_pairs": desired_pairs,
        "primary_pairs": primary_pairs,
        "active_classifications": len(
            classification_rows
        ),
        "active_base_classifications": sum(
            len(values)
            for values in base_by_signature.values()
        ),
        "active_competitor_classifications": sum(
            len(values)
            for values in competitors_by_signature.values()
        ),
        "incomplete_classifications": (
            incomplete_classifications
        ),
        "classifications_without_active_url": (
            classifications_without_active_url
        ),
        "competitor_groups": competitor_groups,
        "competitor_group_key_by_product": (
            competitor_group_key_by_product
        ),
    }


# ============================================================
# DATABASE SYNCHRONIZATION
# ============================================================


def sync_product_matches(
    *,
    desired_types,
):
    """
    Синхронизирует ParserProductMatch с ожидаемым набором.

    Присутствующая пара активируется, отсутствующая
    деактивируется. Существующие строки не удаляются.
    """

    existing_objects = {
        (
            obj.product_key_base,
            obj.product_key_competitor,
        ): obj
        for obj in (
            ParserProductMatch.objects
            .all()
            .order_by(
                "id"
            )
        )
    }

    created_manual = 0
    created_auto = 0
    reactivated_manual = 0
    reactivated_auto = 0
    changed_to_manual = 0
    changed_to_auto = 0
    unchanged_manual = 0
    unchanged_auto = 0
    inactivated = 0

    objects_to_create = []
    objects_to_update = []

    for pair, match_type in sorted(
        desired_types.items()
    ):
        existing = (
            existing_objects.get(
                pair
            )
        )

        if existing is None:
            objects_to_create.append(
                ParserProductMatch(
                    product_key_base=pair[0],
                    product_key_competitor=pair[1],
                    status=(
                        ParserProductMatch
                        .STATUS_ACTIVE
                    ),
                    match_type=match_type,
                )
            )

            if (
                match_type
                == ParserProductMatch
                .MATCH_TYPE_MANUAL
            ):
                created_manual += 1
            else:
                created_auto += 1

            continue

        changed_fields = []

        if (
            existing.status
            != ParserProductMatch.STATUS_ACTIVE
        ):
            existing.status = (
                ParserProductMatch
                .STATUS_ACTIVE
            )

            changed_fields.append(
                "status"
            )

            if (
                match_type
                == ParserProductMatch
                .MATCH_TYPE_MANUAL
            ):
                reactivated_manual += 1
            else:
                reactivated_auto += 1

        if (
            existing.match_type
            != match_type
        ):
            previous_match_type = (
                existing.match_type
            )

            existing.match_type = (
                match_type
            )

            changed_fields.append(
                "match_type"
            )

            if (
                match_type
                == ParserProductMatch
                .MATCH_TYPE_MANUAL
            ):
                changed_to_manual += 1

            elif (
                previous_match_type
                == ParserProductMatch
                .MATCH_TYPE_MANUAL
            ):
                changed_to_auto += 1

        if changed_fields:
            objects_to_update.append(
                existing
            )

        elif (
            match_type
            == ParserProductMatch
            .MATCH_TYPE_MANUAL
        ):
            unchanged_manual += 1

        else:
            unchanged_auto += 1

    desired_pairs = set(
        desired_types
    )

    for pair, existing in (
        existing_objects.items()
    ):
        if pair in desired_pairs:
            continue

        if (
            existing.status
            == ParserProductMatch
            .STATUS_INACTIVE
        ):
            continue

        existing.status = (
            ParserProductMatch
            .STATUS_INACTIVE
        )

        objects_to_update.append(
            existing
        )

        inactivated += 1

    if objects_to_create:
        ParserProductMatch.objects.bulk_create(
            objects_to_create,
            batch_size=1000,
        )

    if objects_to_update:
        ParserProductMatch.objects.bulk_update(
            objects_to_update,
            fields=[
                "status",
                "match_type",
            ],
            batch_size=1000,
        )

    return {
        "created_manual": created_manual,
        "created_auto": created_auto,
        "reactivated_manual": (
            reactivated_manual
        ),
        "reactivated_auto": (
            reactivated_auto
        ),
        "changed_to_manual": (
            changed_to_manual
        ),
        "changed_to_auto": (
            changed_to_auto
        ),
        "unchanged_manual": (
            unchanged_manual
        ),
        "unchanged_auto": (
            unchanged_auto
        ),
        "inactivated": inactivated,
    }


def classification_signature(
    classification,
):
    """
    Значения классификации, которые должны
    совпадать у региональных копий товара.
    """

    return tuple(
        getattr(
            classification,
            field_name,
        )
        for field_name
        in CLASSIFICATION_COPY_FIELDS
    )


def sync_auto_classifications(
    *,
    desired_types,
    competitor_groups,
    competitor_group_key_by_product,
):
    """
    Синхронизирует автоматические региональные
    классификации конкурентных товаров.

    Источниками классификации являются:

    1. Конкурентные product_key, участвующие
       в активном наборе ParserProductMatch.

    2. Активные ручные классификации конкурентов,
       даже если для них пока нет ни одной записи
       в ParserProductMatch.

    Для каждого такого товара:

    - определяется URL-группа региональных копий;
    - выбирается классификация-шаблон;
    - для остальных product_key группы создаются
      или обновляются auto-классификации.

    При этом:

    - новые ParserProductMatch не создаются;
    - ручная классификация не перезаписывается;
    - url и image берутся отдельно для каждого
      собственного product_key;
    - для source без ParserPrefix региональное
      размножение не выполняется.
    """

    now = timezone.now()

    # --------------------------------------------------------
    # Product key конкурентов, участвующих в match
    # --------------------------------------------------------

    matched_competitor_keys = {
        product_key_competitor
        for (
            _,
            product_key_competitor,
        ) in desired_types
    }

    # --------------------------------------------------------
    # Все активные ручные классификации конкурентов
    #
    # Они могут пока не иметь ни одного match, но их
    # региональные URL-копии также должны получить
    # автоматическую классификацию.
    # --------------------------------------------------------

    manual_classification_keys = set(
        ParserProductClassification.objects
        .filter(
            status=(
                ParserProductClassification
                .STATUS_ACTIVE
            ),
            match_type=(
                ParserProductClassification
                .MATCH_TYPE_MANUAL
            ),
        )
        .filter(
            product_key__in=(
                ParserProductUrl.objects
                .filter(
                    status=(
                        ParserProductUrl
                        .STATUS_ACTIVE
                    ),
                )
                .exclude(
                    source="base",
                )
                .values_list(
                    "id",
                    flat=True,
                )
            ),
        )
        .values_list(
            "product_key",
            flat=True,
        )
    )

    # --------------------------------------------------------
    # Определяем URL-группы, которые должны иметь
    # полную региональную классификацию.
    # --------------------------------------------------------

    source_product_keys = (
        matched_competitor_keys
        | manual_classification_keys
    )

    managed_group_keys = {
        group_key
        for product_key in source_product_keys
        for group_key in [
            competitor_group_key_by_product.get(
                product_key
            )
        ]
        if group_key is not None
    }

    # Все product_key внутри найденных URL-групп.
    regional_target_keys = set()

    for group_key in managed_group_keys:
        regional_target_keys.update(
            competitor_groups.get(
                group_key,
                set(),
            )
        )

    # Match-товары сохраняем в наборе отдельно:
    # например, TT может не иметь ParserPrefix и,
    # следовательно, не войти в regional_target_keys.
    target_product_keys = (
        matched_competitor_keys
        | manual_classification_keys
        | regional_target_keys
    )

    if not target_product_keys:
        return {
            "classification_created_auto": 0,
            "classification_updated_auto": 0,
            "classification_reactivated_auto": 0,
            "classification_manual_unchanged": 0,
            "classification_missing_template": 0,
            "classification_conflicts": 0,
            "classification_inactivated_auto": 0,
            "classification_enriched": 0,
            "classification_manual_sources": 0,
            (
                "classification_regional_"
                "targets"
            ): 0,
            (
                "classification_targets_"
                "without_match"
            ): 0,
            "classification_issues": [],
        }

    # --------------------------------------------------------
    # Загружаем существующие классификации
    # --------------------------------------------------------

    all_relevant_product_keys = set(
        target_product_keys
    )

    for group_key in managed_group_keys:
        all_relevant_product_keys.update(
            competitor_groups.get(
                group_key,
                set(),
            )
        )

    existing_classifications = {
        obj.product_key: obj
        for obj in (
            ParserProductClassification
            .objects
            .select_for_update()
            .filter(
                product_key__in=(
                    all_relevant_product_keys
                ),
            )
        )
    }

    # --------------------------------------------------------
    # Выбираем классификацию-шаблон для каждой URL-группы
    # --------------------------------------------------------

    template_by_group = {}

    conflicts = 0
    issues = []

    for group_key in sorted(
        managed_group_keys
    ):
        group_product_keys = (
            competitor_groups.get(
                group_key,
                set(),
            )
        )

        candidates = [
            existing_classifications[
                product_key
            ]
            for product_key
            in sorted(group_product_keys)
            if (
                product_key
                in existing_classifications
                and existing_classifications[
                    product_key
                ].status
                == ParserProductClassification
                .STATUS_ACTIVE
            )
        ]

        if not candidates:
            continue

        # Приоритет:
        #
        # 1. manual;
        # 2. auto;
        # 3. минимальный product_key.
        candidates.sort(
            key=lambda obj: (
                0
                if (
                    obj.match_type
                    == ParserProductClassification
                    .MATCH_TYPE_MANUAL
                )
                else 1,
                obj.product_key,
            )
        )

        template = candidates[0]

        manual_signatures = {
            classification_signature(
                candidate
            )
            for candidate in candidates
            if (
                candidate.match_type
                == ParserProductClassification
                .MATCH_TYPE_MANUAL
            )
        }

        if len(manual_signatures) > 1:
            conflicts += 1

            issues.append({
                "code": (
                    "CLASSIFICATION_GROUP_CONFLICT"
                ),
                "message": (
                    "В одной URL-группе найдены "
                    "разные ручные классификации"
                ),
                "source": group_key[0],
                "normalized_url": group_key[1],
                "product_keys": sorted(
                    group_product_keys
                ),
                (
                    "selected_template_"
                    "product_key"
                ): template.product_key,
            })

        template_by_group[
            group_key
        ] = template

    # --------------------------------------------------------
    # Создание и обновление региональных классификаций
    # --------------------------------------------------------

    created = 0
    updated = 0
    reactivated = 0
    manual_unchanged = 0
    missing_template = 0

    objects_to_create = []
    objects_to_update = []
    enriched_product_keys = set()

    for product_key in sorted(
        target_product_keys
    ):
        existing = (
            existing_classifications.get(
                product_key
            )
        )

        # Ручная классификация всегда имеет приоритет.
        if (
            existing is not None
            and existing.match_type
            == ParserProductClassification
            .MATCH_TYPE_MANUAL
        ):
            manual_unchanged += 1
            continue

        group_key = (
            competitor_group_key_by_product
            .get(
                product_key
            )
        )

        template = (
            template_by_group.get(
                group_key
            )
            if group_key is not None
            else None
        )

        # Для source без ParserPrefix, например TT,
        # URL-группы нет. Если классификация уже есть,
        # её не изменяем. Новую создать неоткуда.
        if template is None:
            if existing is None:
                missing_template += 1

                issues.append({
                    "code": (
                        "CLASSIFICATION_TEMPLATE_MISSING"
                    ),
                    "message": (
                        "Для competitor product_key "
                        "не найдена классификация-шаблон "
                        "среди региональных URL-копий"
                    ),
                    "product_key": product_key,
                    "group_key": group_key,
                    "is_matched": (
                        product_key
                        in matched_competitor_keys
                    ),
                })

            continue

        values = {
            field_name: getattr(
                template,
                field_name,
            )
            for field_name
            in CLASSIFICATION_COPY_FIELDS
        }

        if existing is None:
            objects_to_create.append(
                ParserProductClassification(
                    product_key=product_key,
                    **values,
                    status=(
                        ParserProductClassification
                        .STATUS_ACTIVE
                    ),
                    match_type=(
                        ParserProductClassification
                        .MATCH_TYPE_AUTO
                    ),
                    date_update=now,
                )
            )

            created += 1

            enriched_product_keys.add(
                product_key
            )

            continue

        changed = False

        if (
            existing.status
            == ParserProductClassification
            .STATUS_INACTIVE
        ):
            reactivated += 1

        for (
            field_name,
            field_value,
        ) in values.items():
            if (
                getattr(
                    existing,
                    field_name,
                )
                != field_value
            ):
                setattr(
                    existing,
                    field_name,
                    field_value,
                )

                changed = True

        if (
            existing.status
            != ParserProductClassification
            .STATUS_ACTIVE
        ):
            existing.status = (
                ParserProductClassification
                .STATUS_ACTIVE
            )

            changed = True

        if (
            existing.match_type
            != ParserProductClassification
            .MATCH_TYPE_AUTO
        ):
            existing.match_type = (
                ParserProductClassification
                .MATCH_TYPE_AUTO
            )

            changed = True

        if changed:
            existing.date_update = now

            objects_to_update.append(
                existing
            )

            updated += 1

            enriched_product_keys.add(
                product_key
            )

    if objects_to_create:
        (
            ParserProductClassification
            .objects
            .bulk_create(
                objects_to_create,
                batch_size=1000,
            )
        )

    if objects_to_update:
        (
            ParserProductClassification
            .objects
            .bulk_update(
                objects_to_update,
                fields=[
                    *CLASSIFICATION_COPY_FIELDS,
                    "status",
                    "match_type",
                    "date_update",
                ],
                batch_size=1000,
            )
        )

    # --------------------------------------------------------
    # Деактивация устаревших auto-классификаций
    #
    # Auto-строка остаётся активной, если она нужна:
    #
    # - для активного match;
    # - либо для региональной группы хотя бы одной
    #   активной manual-классификации без match.
    # --------------------------------------------------------

    inactivated = (
        ParserProductClassification
        .objects
        .filter(
            match_type=(
                ParserProductClassification
                .MATCH_TYPE_AUTO
            ),
            status=(
                ParserProductClassification
                .STATUS_ACTIVE
            ),
        )
        .exclude(
            product_key__in=(
                target_product_keys
            ),
        )
        .update(
            status=(
                ParserProductClassification
                .STATUS_INACTIVE
            ),
            date_update=now,
        )
    )

    # --------------------------------------------------------
    # У каждого регионального product_key должны быть
    # собственные url и image.
    # --------------------------------------------------------

    enriched = (
        enrich_classification_urls_and_images(
            enriched_product_keys
        )
        if enriched_product_keys
        else 0
    )

    targets_without_match = (
        target_product_keys
        - matched_competitor_keys
    )

    return {
        "classification_created_auto": (
            created
        ),
        "classification_updated_auto": (
            updated
        ),
        "classification_reactivated_auto": (
            reactivated
        ),
        "classification_manual_unchanged": (
            manual_unchanged
        ),
        "classification_missing_template": (
            missing_template
        ),
        "classification_conflicts": (
            conflicts
        ),
        "classification_inactivated_auto": (
            inactivated
        ),
        "classification_enriched": (
            enriched
        ),
        "classification_manual_sources": (
            len(
                manual_classification_keys
            )
        ),
        "classification_regional_targets": (
            len(
                regional_target_keys
            )
        ),
        (
            "classification_targets_"
            "without_match"
        ): (
            len(
                targets_without_match
            )
        ),
        "classification_issues": issues,
    }


# ============================================================
# MAIN LOADER
# ============================================================


def sync_product_matches_from_classification() -> dict:
    """
    Синхронизирует связи по семи полям активной классификации
    и сохраняет существующее региональное URL-расширение.
    """

    prefixes_by_source = get_prefixes_by_source()
    (
        competitor_groups,
        competitor_group_key_by_product,
    ) = build_competitor_url_groups(
        prefixes_by_source=prefixes_by_source,
    )

    with transaction.atomic():
        classification_result = (
            sync_auto_classifications(
                desired_types={},
                competitor_groups=competitor_groups,
                competitor_group_key_by_product=(
                    competitor_group_key_by_product
                ),
            )
        )

        desired_result = (
            build_classification_match_set(
                prefixes_by_source=(
                    prefixes_by_source
                ),
                competitor_groups=(
                    competitor_groups
                ),
                competitor_group_key_by_product=(
                    competitor_group_key_by_product
                ),
            )
        )

        sync_result = sync_product_matches(
            desired_types=(
                desired_result["desired_types"]
            ),
        )

    classification_issues = (
        classification_result.pop(
            "classification_issues",
            [],
        )
    )

    result = {
        **sync_result,
        **classification_result,
        "active_classifications": (
            desired_result[
                "active_classifications"
            ]
        ),
        "active_base_classifications": (
            desired_result[
                "active_base_classifications"
            ]
        ),
        "active_competitor_classifications": (
            desired_result[
                "active_competitor_classifications"
            ]
        ),
        "incomplete_classifications": (
            desired_result[
                "incomplete_classifications"
            ]
        ),
        "classifications_without_active_url": (
            desired_result[
                "classifications_without_active_url"
            ]
        ),
        "primary_pairs": len(
            desired_result["primary_pairs"]
        ),
        "active_pairs_expected": len(
            desired_result["desired_pairs"]
        ),
        "issues": classification_issues,
    }

    logger.info(
        "Product matches synchronized from classification: %s",
        result,
    )

    return result
