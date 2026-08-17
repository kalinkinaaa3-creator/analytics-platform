from __future__ import annotations

from collections import Counter
from typing import Any

from django.core.paginator import Paginator
from django.core.cache import cache

from datasets.services.iprice_preparation_check import (
    ERROR,
    WARNING,
    run_iprice_preparation_check,
)


HEALTH_CACHE_KEY = (
    "iprice:data:health"
)

HEALTH_CACHE_TIMEOUT = 5 * 60


LEVEL_ALL = "all"
LEVEL_ERROR = "ERROR"
LEVEL_WARNING = "WARNING"


ALLOWED_LEVELS = {
    LEVEL_ALL,
    LEVEL_ERROR,
    LEVEL_WARNING,
}


SECTION_LABELS = {
    "parser_product_classification": (
        "Классификация"
    ),

    "parser_product_match": (
        "Product Match"
    ),

    "transport_cost": (
        "Транспортные расходы"
    ),

    "parser_prefix": (
        "Региональные префиксы"
    ),

    "departure_discount": (
        "Скидки по производствам"
    ),

    "iprice_calculation_config": (
        "Конфигурация расчёта"
    ),

    "product_cost": (
        "Себестоимость"
    ),

    "cross_checks": (
        "Межтабличные проверки"
    ),
}


SECTION_ORDER = (
    "parser_product_classification",
    "parser_product_match",
    "transport_cost",
    "parser_prefix",
    "departure_discount",
    "iprice_calculation_config",
    "product_cost",
    "cross_checks",
)


ISSUE_GROUPS = {
    # ========================================================
    # CLASSIFICATION
    # ========================================================

    "CLASSIFICATION_MISSING": (
        "Нет классификации"
    ),

    "CLASSIFICATION_NOT_FOUND": (
        "Нет классификации"
    ),

    "CLASSIFICATION_FIELD_EMPTY": (
        "Неполная классификация"
    ),

    "CLASSIFICATION_URL_NOT_FOUND": (
        "Классификация без товара"
    ),

    "CLASSIFICATION_URL_INACTIVE": (
        "Классификация неактивного товара"
    ),

    # ========================================================
    # PRODUCT MATCH
    # ========================================================

    "MATCH_NOT_FOUND": (
        "Нет Product Match"
    ),

    "MATCH_BASE_NOT_FOUND": (
        "Некорректный Product Match"
    ),

    "MATCH_COMPETITOR_NOT_FOUND": (
        "Некорректный Product Match"
    ),

    "MATCH_CLASSIFICATION_NOT_FOUND": (
        "Match без классификации"
    ),

    "MATCH_DUPLICATE": (
        "Дубли Product Match"
    ),

    # ========================================================
    # COST
    # ========================================================

    "PRODUCT_COST_MISSING": (
        "Нет себестоимости"
    ),

    "PRODUCT_COST_DATE_MISSING": (
        "Некорректная себестоимость"
    ),

    "PRODUCT_COST_VALUE_MISSING": (
        "Некорректная себестоимость"
    ),

    "PRODUCT_COST_VALUE_INVALID": (
        "Некорректная себестоимость"
    ),

    # ========================================================
    # TRANSPORT
    # ========================================================

    "TRANSPORT_ROUTE_MISSING": (
        "Нет транспортного маршрута"
    ),

    "TRANSPORT_COST_MISSING": (
        "Некорректный транспорт"
    ),

    "TRANSPORT_COST_INVALID": (
        "Некорректный транспорт"
    ),

    # ========================================================
    # DISCOUNTS
    # ========================================================

    "DEPARTURE_DISCOUNT_MISSING": (
        "Нет скидки"
    ),

    "DEPARTURE_NOT_FOUND": (
        "Некорректное производство"
    ),

    "DISCOUNT_VALUE_MISSING": (
        "Некорректная скидка"
    ),

    "DISCOUNT_VALUE_INVALID": (
        "Некорректная скидка"
    ),

    # ========================================================
    # PREFIXES
    # ========================================================

    "PREFIX_REGION_UNKNOWN": (
        "Неизвестный регион префикса"
    ),

    "PREFIX_SOURCE_UNKNOWN": (
        "Неизвестный источник префикса"
    ),

    "PREFIX_DUPLICATE": (
        "Дубли префиксов"
    ),

    # ========================================================
    # NOMENCLATURE
    # ========================================================

    "BASE_PRICE_NOT_FOUND": (
        "Нет актуальной цены нашего товара"
    ),

    "CODE_1C_EMPTY": (
        "Нет кода 1С"
    ),

    "NOMENCLATURE_NOT_FOUND": (
        "Нет номенклатуры"
    ),

    "NOMENCLATURE_DUPLICATE": (
        "Дубли номенклатуры"
    ),

    "NOMENCLATURE_PRICE_EMPTY": (
        "Нет цен номенклатуры"
    ),

    # ========================================================
    # EUROTRUCK
    # ========================================================

    "EUROTRUCK_CODE_1C_MISSING": (
        "Нет количества в еврофуре"
    ),

    "EUROTRUCK_NOMENCLATURE_NOT_FOUND": (
        "Нет количества в еврофуре"
    ),

    "EUROTRUCK_NOMENCLATURE_DUPLICATE": (
        "Неоднозначная номенклатура"
    ),

    "EUROTRUCK_QUANTITY_MISSING": (
        "Нет количества в еврофуре"
    ),

    "EUROTRUCK_QUANTITY_INVALID": (
        "Некорректное количество в еврофуре"
    ),

    "EUROTRUCK_QUANTITY_NOT_POSITIVE": (
        "Некорректное количество в еврофуре"
    ),

    # ========================================================
    # CONFIG
    # ========================================================

    "CONFIG_ITEM_TYPE_DUPLICATE": (
        "Дубли конфигурации"
    ),

    "CONFIG_ITEM_TYPE_MISSING": (
        "Неполная конфигурация"
    ),

    "CONFIG_VALUE_MISSING": (
        "Неполная конфигурация"
    ),

    "CONFIG_VALUE_INVALID": (
        "Некорректная конфигурация"
    ),

    # ========================================================
    # COMMON
    # ========================================================

    "TABLE_EMPTY": (
        "Пустой справочник"
    ),
}


def normalize_text(
    value: Any,
) -> str:
    return str(
        value or ""
    ).strip()


def normalize_level(
    value: Any,
) -> str:
    normalized_value = (
        normalize_text(value)
        .upper()
    )

    if normalized_value in {
        LEVEL_ERROR,
        LEVEL_WARNING,
    }:
        return normalized_value

    return LEVEL_ALL


def normalize_string_list(
    values: Any,
) -> list[str]:
    if values is None:
        return []

    if isinstance(
        values,
        (
            str,
            bytes,
        ),
    ):
        values = [values]

    if not isinstance(
        values,
        (
            list,
            tuple,
            set,
        ),
    ):
        return []

    result = []
    seen = set()

    for value in values:
        normalized_value = (
            normalize_text(value)
        )

        if not normalized_value:
            continue

        value_key = (
            normalized_value.casefold()
        )

        if value_key in seen:
            continue

        seen.add(value_key)
        result.append(
            normalized_value
        )

    return result


def get_issue_group(
    error_code: str,
) -> str:
    normalized_code = (
        normalize_text(error_code)
        .upper()
    )

    if normalized_code in ISSUE_GROUPS:
        return ISSUE_GROUPS[
            normalized_code
        ]

    if "CLASSIFICATION" in normalized_code:
        return "Классификация"

    if "MATCH" in normalized_code:
        return "Product Match"

    if (
        "TRANSPORT" in normalized_code
        or "ROUTE" in normalized_code
    ):
        return "Транспортные расходы"

    if "COST" in normalized_code:
        return "Себестоимость"

    if (
        "DISCOUNT" in normalized_code
        or "DEPARTURE" in normalized_code
    ):
        return "Скидки по производствам"

    if "PREFIX" in normalized_code:
        return "Региональные префиксы"

    if (
        "NOMENCLATURE" in normalized_code
        or "CODE_1C" in normalized_code
    ):
        return "Номенклатура"

    if "EUROTRUCK" in normalized_code:
        return "Количество в еврофуре"

    if "CONFIG" in normalized_code:
        return "Конфигурация расчёта"

    return "Прочие ошибки"


def serialize_issue(
    *,
    section_name: str,
    issue: dict,
    issue_number: int,
) -> dict:
    error_code = normalize_text(
        issue.get(
            "error_code"
        )
    )

    level = normalize_text(
        issue.get(
            "level"
        )
    ).upper()

    if level not in {
        ERROR,
        WARNING,
    }:
        level = WARNING

    reserved_fields = {
        "level",
        "error_code",
        "business_key",
        "message",
    }

    details = {
        key: value
        for key, value in issue.items()
        if key not in reserved_fields
    }

    return {
        "id": issue_number,

        "section": section_name,

        "section_label": (
            SECTION_LABELS.get(
                section_name,
                section_name,
            )
        ),

        "level": level,

        "error_code": error_code,

        "issue_group": (
            get_issue_group(
                error_code
            )
        ),

        "business_key": (
            normalize_text(
                issue.get(
                    "business_key"
                )
            )
        ),

        "message": (
            normalize_text(
                issue.get(
                    "message"
                )
            )
        ),

        "product_key": (
            issue.get(
                "product_key"
            )
            or issue.get(
                "product_key_base"
            )
        ),

        "competitor_product_key": (
            issue.get(
                "competitor_product_key"
            )
            or issue.get(
                "product_key_competitor"
            )
        ),

        "code_1c": (
            issue.get(
                "code_1c"
            )
            or issue.get(
                "code"
            )
        ),

        "departure": (
            issue.get(
                "departure"
            )
        ),

        "arrival": (
            issue.get(
                "arrival"
            )
        ),

        "source": (
            issue.get(
                "source"
            )
        ),

        "details": details,
    }


def flatten_check_results(
    check_results: dict,
) -> tuple[
    list[dict],
    list[dict],
]:
    issues = []
    sections = []

    issue_number = 1

    section_names = [
        *SECTION_ORDER,
        *[
            section_name
            for section_name in check_results
            if section_name not in (
                SECTION_ORDER
            )
        ],
    ]

    seen_sections = set()

    for section_name in section_names:
        if section_name in seen_sections:
            continue

        seen_sections.add(
            section_name
        )

        section_data = (
            check_results.get(
                section_name
            )
            or {}
        )

        section_issues = (
            section_data.get(
                "issues"
            )
            or []
        )

        serialized_section_issues = []

        for raw_issue in section_issues:
            if not isinstance(
                raw_issue,
                dict,
            ):
                continue

            serialized_issue = (
                serialize_issue(
                    section_name=(
                        section_name
                    ),
                    issue=raw_issue,
                    issue_number=(
                        issue_number
                    ),
                )
            )

            issue_number += 1

            issues.append(
                serialized_issue
            )

            serialized_section_issues.append(
                serialized_issue
            )

        level_counts = Counter(
            issue["level"]
            for issue in (
                serialized_section_issues
            )
        )

        sections.append({
            "name": section_name,

            "label": (
                SECTION_LABELS.get(
                    section_name,
                    section_name,
                )
            ),

            "checked": int(
                section_data.get(
                    "checked"
                )
                or 0
            ),

            "issues_count": len(
                serialized_section_issues
            ),

            "errors_count": (
                level_counts.get(
                    ERROR,
                    0,
                )
            ),

            "warnings_count": (
                level_counts.get(
                    WARNING,
                    0,
                )
            ),

            "status": (
                "error"
                if level_counts.get(
                    ERROR,
                    0,
                ) > 0
                else (
                    "warning"
                    if level_counts.get(
                        WARNING,
                        0,
                    ) > 0
                    else "success"
                )
            ),
        })

    return issues, sections


def build_summary(
    *,
    issues: list[dict],
    sections: list[dict],
) -> dict:
    level_counts = Counter(
        issue["level"]
        for issue in issues
    )

    group_counts = Counter(
        issue["issue_group"]
        for issue in issues
    )

    code_counts = Counter(
        issue["error_code"]
        for issue in issues
    )

    return {
        "sections_count": len(
            sections
        ),

        "checked_total": sum(
            section["checked"]
            for section in sections
        ),

        "issues_total": len(
            issues
        ),

        "errors_total": (
            level_counts.get(
                ERROR,
                0,
            )
        ),

        "warnings_total": (
            level_counts.get(
                WARNING,
                0,
            )
        ),

        "healthy_sections": sum(
            section["status"]
            == "success"
            for section in sections
        ),

        "problem_sections": sum(
            section["status"]
            != "success"
            for section in sections
        ),

        "issue_groups": [
            {
                "value": group_name,
                "label": group_name,
                "count": count,
            }
            for (
                group_name,
                count,
            ) in sorted(
                group_counts.items(),
                key=lambda item: (
                    -item[1],
                    item[0].casefold(),
                ),
            )
        ],

        "error_codes": [
            {
                "value": error_code,
                "label": error_code,
                "count": count,
            }
            for (
                error_code,
                count,
            ) in sorted(
                code_counts.items(),
                key=lambda item: (
                    -item[1],
                    item[0].casefold(),
                ),
            )
        ],
    }


def issue_matches_search(
    issue: dict,
    search: str,
) -> bool:
    normalized_search = (
        normalize_text(search)
        .casefold()
    )

    if not normalized_search:
        return True

    search_values = [
        issue.get(
            "section_label"
        ),
        issue.get(
            "level"
        ),
        issue.get(
            "error_code"
        ),
        issue.get(
            "issue_group"
        ),
        issue.get(
            "business_key"
        ),
        issue.get(
            "message"
        ),
        issue.get(
            "product_key"
        ),
        issue.get(
            "competitor_product_key"
        ),
        issue.get(
            "code_1c"
        ),
        issue.get(
            "departure"
        ),
        issue.get(
            "arrival"
        ),
        issue.get(
            "source"
        ),
    ]

    return any(
        normalized_search in (
            normalize_text(value)
            .casefold()
        )
        for value in search_values
    )


def filter_issues(
    *,
    issues: list[dict],
    level: str,
    sections: list[str],
    issue_groups: list[str],
    error_codes: list[str],
    search: str,
) -> list[dict]:
    normalized_level = (
        normalize_level(
            level
        )
    )

    section_keys = {
        value.casefold()
        for value in sections
    }

    group_keys = {
        value.casefold()
        for value in issue_groups
    }

    code_keys = {
        value.casefold()
        for value in error_codes
    }

    result = []

    for issue in issues:
        if (
            normalized_level
            != LEVEL_ALL
            and issue["level"]
            != normalized_level
        ):
            continue

        if (
            section_keys
            and issue["section"].casefold()
            not in section_keys
        ):
            continue

        if (
            group_keys
            and issue[
                "issue_group"
            ].casefold()
            not in group_keys
        ):
            continue

        if (
            code_keys
            and issue[
                "error_code"
            ].casefold()
            not in code_keys
        ):
            continue

        if not issue_matches_search(
            issue,
            search,
        ):
            continue

        result.append(
            issue
        )

    return result


def build_filter_options(
    *,
    issues: list[dict],
    sections: list[dict],
) -> dict:
    group_counts = Counter(
        issue["issue_group"]
        for issue in issues
    )

    code_counts = Counter(
        issue["error_code"]
        for issue in issues
    )

    return {
        "levels": [
            {
                "value": LEVEL_ERROR,
                "label": "Ошибки",
                "count": sum(
                    issue["level"]
                    == LEVEL_ERROR
                    for issue in issues
                ),
            },
            {
                "value": LEVEL_WARNING,
                "label": "Предупреждения",
                "count": sum(
                    issue["level"]
                    == LEVEL_WARNING
                    for issue in issues
                ),
            },
        ],

        "sections": [
            {
                "value": section["name"],
                "label": section["label"],
                "count": (
                    section[
                        "issues_count"
                    ]
                ),
            }
            for section in sections
            if section[
                "issues_count"
            ] > 0
        ],

        "issue_groups": [
            {
                "value": group_name,
                "label": group_name,
                "count": count,
            }
            for (
                group_name,
                count,
            ) in sorted(
                group_counts.items(),
                key=lambda item: (
                    item[0].casefold()
                ),
            )
        ],

        "error_codes": [
            {
                "value": error_code,
                "label": error_code,
                "count": count,
            }
            for (
                error_code,
                count,
            ) in sorted(
                code_counts.items(),
                key=lambda item: (
                    item[0].casefold()
                ),
            )
        ],
    }


def get_health_check_data(
    *,
    force_refresh: bool = False,
) -> dict:
    if not force_refresh:
        cached_result = cache.get(
            HEALTH_CACHE_KEY
        )

        if isinstance(
            cached_result,
            dict,
        ):
            return cached_result

    check_results = (
        run_iprice_preparation_check()
    )

    issues, sections = (
        flatten_check_results(
            check_results
        )
    )

    result = {
        "summary": build_summary(
            issues=issues,
            sections=sections,
        ),

        "sections": sections,

        "issues": issues,

        "filter_options": (
            build_filter_options(
                issues=issues,
                sections=sections,
            )
        ),
    }

    cache.set(
        HEALTH_CACHE_KEY,
        result,
        timeout=(
            HEALTH_CACHE_TIMEOUT
        ),
    )

    return result


def build_iprice_health_response(
    *,
    page: int = 1,
    page_size: int = 50,
    level: str = LEVEL_ALL,
    sections: Any = None,
    issue_groups: Any = None,
    error_codes: Any = None,
    search: str = "",
    force_refresh: bool = False,
) -> dict:
    health_data = (
        get_health_check_data(
            force_refresh=(
                force_refresh
            )
        )
    )

    normalized_sections = (
        normalize_string_list(
            sections
        )
    )

    normalized_issue_groups = (
        normalize_string_list(
            issue_groups
        )
    )

    normalized_error_codes = (
        normalize_string_list(
            error_codes
        )
    )

    filtered_issues = filter_issues(
        issues=health_data[
            "issues"
        ],
        level=level,
        sections=normalized_sections,
        issue_groups=(
            normalized_issue_groups
        ),
        error_codes=(
            normalized_error_codes
        ),
        search=search,
    )

    paginator = Paginator(
        filtered_issues,
        page_size,
    )

    page_object = paginator.get_page(
        page
    )

    return {
        "summary": (
            health_data[
                "summary"
            ]
        ),

        "sections": (
            health_data[
                "sections"
            ]
        ),

        "filter_options": (
            health_data[
                "filter_options"
            ]
        ),

        "selected": {
            "level": normalize_level(
                level
            ),

            "sections": (
                normalized_sections
            ),

            "issue_groups": (
                normalized_issue_groups
            ),

            "error_codes": (
                normalized_error_codes
            ),

            "search": normalize_text(
                search
            ),
        },

        "count": paginator.count,

        "page": page_object.number,

        "page_size": page_size,

        "total_pages": (
            paginator.num_pages
            if paginator.count > 0
            else 0
        ),

        "has_next": (
            page_object.has_next()
        ),

        "has_previous": (
            page_object.has_previous()
        ),

        "results": list(
            page_object.object_list
        ),
    }


def invalidate_iprice_health_cache():
    cache.delete(
        HEALTH_CACHE_KEY
    )