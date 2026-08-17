from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation


DIMENSION_SEPARATOR_RE = re.compile(r"\s*[xх×]\s*", re.IGNORECASE)
NUMBER_RE = re.compile(r"(?<![\w])[-+]?\d+(?:[\s\u00a0]\d{3})*(?:[.,]\d+)?")

UNIT_ALIASES = {
    "millimeters": {
        "мм": Decimal("1"), "mm": Decimal("1"),
        "см": Decimal("10"), "cm": Decimal("10"),
        "м": Decimal("1000"), "m": Decimal("1000"),
    },
    "liters": {
        "л": Decimal("1"), "l": Decimal("1"),
        "литр": Decimal("1"), "литра": Decimal("1"), "литров": Decimal("1"),
        "мл": Decimal("0.001"), "ml": Decimal("0.001"),
        "м3": Decimal("1000"), "м³": Decimal("1000"),
    },
    "kilograms": {
        "кг": Decimal("1"), "kg": Decimal("1"),
        "г": Decimal("0.001"), "гр": Decimal("0.001"), "g": Decimal("0.001"),
        "т": Decimal("1000"),
    },
    "grams": {
        "г": Decimal("1"), "гр": Decimal("1"), "g": Decimal("1"),
        "кг": Decimal("1000"), "kg": Decimal("1000"),
    },
    "pieces": {
        "шт": Decimal("1"), "шт.": Decimal("1"),
    },
}


def normalize_text(value):
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    text = text.replace("\u00a0", " ").replace("ё", "е").casefold().strip()
    text = re.sub(r"\s+", " ", text)
    # Only dimension-like separators between digits are normalized.  Letters
    # inside ordinary words are never replaced.
    text = re.sub(r"(?<=\d)\s*[xх×]\s*(?=\d)", "x", text, flags=re.IGNORECASE)
    return text


def split_or(value):
    return [part.strip() for part in str(value).split("//") if part.strip()]


def split_and(value):
    return [part.strip() for part in str(value).split("///") if part.strip()]


def contains_phrase(haystack, phrase):
    haystack = normalize_text(haystack)
    phrase = normalize_text(phrase)
    if not haystack or not phrase:
        return False
    # Word boundaries protect short rules from matching inside unrelated words.
    # A rule may intentionally contain only the leading dimensions, for example
    # ``1200x800`` for an actual value ``1200x800x920``.  In that one case the
    # following ``x`` is a dimension separator rather than a word continuation.
    trailing_boundary = r"(?=$|[^\w]|x(?=\d))" if phrase[-1].isdigit() else r"(?!\w)"
    return re.search(
        rf"(?<!\w){re.escape(phrase)}{trailing_boundary}", haystack
    ) is not None


def _detect_unit(text, canonical_unit):
    aliases = UNIT_ALIASES.get(canonical_unit, {})
    matches = []
    for alias, coefficient in aliases.items():
        match = re.search(rf"(?<![a-zа-я]){re.escape(alias)}(?![a-zа-я])", text)
        if match:
            matches.append((match.start(), -len(alias), coefficient))
    return sorted(matches)[0][2] if matches else Decimal("1")


def normalize_numeric(value, *, canonical_unit, number_format):
    text = normalize_text(value).replace("≈", " ").replace("~", " ")
    match = NUMBER_RE.search(text)
    if not match:
        return None
    raw_number = match.group(0).replace(" ", "").replace("\u00a0", "")
    try:
        number = Decimal(raw_number.replace(",", "."))
    except InvalidOperation:
        return None
    number *= _detect_unit(text, canonical_unit)
    if number_format == "integer":
        if number != number.to_integral_value():
            return None
        return number.to_integral_value()
    return number.normalize()


def extract_dimension(value, index, *, canonical_unit="millimeters", number_format="integer"):
    text = normalize_text(value)
    parts = DIMENSION_SEPARATOR_RE.split(text)
    if len(parts) <= index:
        return None
    return normalize_numeric(
        parts[index], canonical_unit=canonical_unit, number_format=number_format
    )


COUNT_FORMS = {
    "runner": (
        r"полоз(?:а|ов|ья|ьев|ах|ами)?",
        r"полозь(?:я|ев|ях|ями)",
        r"полозн(?:ый|ая|ое|ые|ого|ых|ому|ым)",
    ),
    "wheel": (
        r"колес(?:о|а|у|ом|е|ах|ами)?",
        r"колесн(?:ый|ая|ое|ые|ого|ых|ому|ым)",
    ),
}

DIAMETER_FORMS = (r"колес(?:о|а|у|ом|е|ах|ами)?",)


def extract_named_count(value, kind):
    """Extract a count only when grammatically tied to the target noun.

    Supported examples include ``4 колеса``, ``на 4-х колесах``,
    ``трехполозный`` is deliberately not guessed because it has no numeric
    token. A bare ``-х`` suffix is accepted only between the number and an
    allowed target word. Dimensions such as ``1200x800`` therefore cannot be
    interpreted as counts.
    """
    text = normalize_text(value)
    forms = COUNT_FORMS[kind]
    noun = "(?:" + "|".join(forms) + ")"
    patterns = (
        rf"(?<![\d\w])(\d{{1,2}})(?:\s*-?\s*х)?\s*{noun}(?!\w)",
        rf"(?<!\w){noun}\s*[-:–—]?\s*(\d{{1,2}})(?![\d\w])",
    )
    values = []
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            number = int(match.group(1))
            if 1 <= number <= 20:
                values.append(number)
    return Decimal(values[0]) if values else None


def extract_wheel_diameter(value):
    text = normalize_text(value)
    wheel = "(?:" + "|".join(DIAMETER_FORMS) + ")"
    patterns = (
        rf"{wheel}[^\d]{{0,20}}(?:диаметр|ø|d)\s*[:=]?\s*(\d{{2,4}})(?:\s*мм)?",
        rf"(?:диаметр|ø|d)\s*{wheel}?\s*[:=]?\s*(\d{{2,4}})(?:\s*мм)?",
        rf"{wheel}[\s,:;–—-]*(\d{{2,4}})\s*мм(?!\w)",
        rf"(\d{{2,4}})\s*мм\s*{wheel}(?!\w)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            value = int(match.group(1))
            if 20 <= value <= 1000:
                return Decimal(value)
    return None


def extract_volume_from_name(value):
    """Extract a litre value only when the number is tied to a litre unit."""
    text = normalize_text(value)
    match = re.search(
        r"(?<![\d\w])(\d+(?:[.,]\d+)?)\s*"
        r"(?:литр(?:а|ов)?|л\.?|lit(?:er|re)s?|l\.?)"
        r"(?![a-zа-я])",
        text,
    )
    if not match:
        return None
    try:
        volume = Decimal(match.group(1).replace(",", "."))
    except InvalidOperation:
        return None
    return volume.normalize() if volume > 0 else None


def run_many_to_many_handler(
    handler_name,
    *,
    raw_value,
    property_name,
    canonical_unit="millimeters",
    number_format="integer",
):
    if handler_name == "match_any_color":
        return "__ANY__"
    if handler_name == "color_missing":
        return None
    if handler_name == "default_tt_material_pe_pp":
        return "PE/PP"
    if handler_name == "extract_dimension_length":
        return extract_dimension(
            raw_value, 0,
            canonical_unit=canonical_unit,
            number_format=number_format,
        )
    if handler_name == "extract_dimension_width":
        return extract_dimension(
            raw_value, 1,
            canonical_unit=canonical_unit,
            number_format=number_format,
        )
    if handler_name == "extract_dimension_height":
        return extract_dimension(
            raw_value, 2,
            canonical_unit=canonical_unit,
            number_format=number_format,
        )
    if handler_name == "extract_runner_number_from_name":
        return extract_named_count(raw_value, "runner")
    if handler_name == "extract_wheel_number_from_name":
        return extract_named_count(raw_value, "wheel")
    if handler_name == "extract_wheel_diameter_from_name":
        return extract_wheel_diameter(raw_value)
    if handler_name == "extract_volume_from_name":
        return extract_volume_from_name(raw_value)
    raise ValueError(f"Unknown MANY-TO-MANY handler: {handler_name}")
