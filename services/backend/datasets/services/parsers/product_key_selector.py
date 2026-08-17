import logging

from datasets.models import (
    ParserProductClassification,
    ParserProductUrl,
)


logger = logging.getLogger("parsers.product_key_selector")


VALID_SOURCES = {
    "base",
    "tt",
    "ps",
    "tara",
}


def get_active_classified_product_keys(
    source: str,
) -> set[int]:
    """
    Возвращает product_key для указанного источника, которые:

    1. присутствуют в активной классификации;
    2. существуют в ParserProductUrl;
    3. относятся к указанному source;
    4. имеют status=active в ParserProductUrl.

    ParserProductUrl.id является product_key.
    """

    source = str(source or "").strip().casefold()

    if source not in VALID_SOURCES:
        raise ValueError(
            "Неизвестный источник: "
            f"{source!r}. "
            "Допустимые значения: "
            f"{', '.join(sorted(VALID_SOURCES))}"
        )

    product_keys = set(
        ParserProductUrl.objects.filter(
            source=source,
            status=ParserProductUrl.STATUS_ACTIVE,
            id__in=(
                ParserProductClassification.objects.filter(
                    status=(
                        ParserProductClassification
                        .STATUS_ACTIVE
                    ),
                ).values_list(
                    "product_key",
                    flat=True,
                )
            ),
        ).values_list(
            "id",
            flat=True,
        )
    )

    logger.info(
        "Active classified product keys selected: "
        "source=%s count=%s",
        source,
        len(product_keys),
    )

    return product_keys