import re

from django.apps import apps

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from datasets.models import (
    ParserProductUrl,
    ParserProductProperty,
    ParserProductClassification,
)


PRICE_MODELS_BY_SOURCE = {
    "base": "BaseProductPrice",
    "tara": "TaraProductPrice",
    "ps": "PsProductPrice",
    "tt": "TtProductPrice",
}

NAME_FIELD_CANDIDATES = [
    "product_name",
    "name",
    "nomenclature",
    "title",
]

NAME_WEIGHT = 4
SOURCE_WEIGHT = 1
ADDITIONAL_PROPERTY_WEIGHT = 2


PROPERTY_GROUPS_BY_WEIGHT = {
    5: {
        "size": [
            "размер",
            "габарит",
            "длина",
            "ширина",
            "высота",
            "диаметр",
            "толщина",
            "площадк",
            "ячейк",
            "основан",
            "горловин",
            "обода",
            "борт",
            "пластин",
            "перегородк",
            "защитного слоя",
            "листов толщиной",
        ],
    },
    4: {
        "stackable": [
            "штабел",
            "складирование",
            "способ штабелирования",
            "высота штабелирования",
        ],
        "nestable": [
            "вкладыв",
            "возможность вкладывания",
            "высота вкладывания",
        ],
        "foldable": [
            "способ сложения",
            "тип сложения",
            "сложен",
            "сложенном",
            "разобранном",
        ],
        "wall_type": [
            "стенк",
            "тип стен",
            "перфорация стен",
        ],
        "bottom_type": [
            "дно",
            "тип дна",
            "перфорация дна",
        ],
        "lid": [
            "крышк",
            "тип крыш",
            "вес крышки",
        ],
        "wheels": [
            "колес",
            "колёс",
            "ролик",
            "тормоз",
            "диаметр кол",
            "тип кол",
            "материал кол",
            "количество кол",
            "поворотных кол",
        ],
        "supports": [
            "ножк",
            "полоз",
            "опорн",
            "тип опор",
            "наличие полоз",
            "количество полоз",
        ],
        "handles": [
            "ручк",
        ],
        "pedal": [
            "педал",
        ],
        "drain": [
            "сливн",
        ],
        "sealing": [
            "герметич",
            "опломб",
        ],
        "lattice": [
            "обрешет",
            "обрешетк",
            "шаг обрешетки",
        ],
        "platform": [
            "платформ",
        ],
        "configuration": [
            "комплектац",
            "количество отсек",
            "количество раздел",
            "разделител",
        ],
        "tier": [
            "ярус",
        ],
        "surface": [
            "поверхность",
            "покрытие",
        ],
        "shape": [
            "форма",
        ],
        "product_type": [
            "тип контейнера",
            "тип товара",
            "группа продукц",
            "тип",
        ],
        "food_contact": [
            "пищев",
            "контакт",
            "пригодность",
        ],
    },
    3: {
        "material": [
            "материал",
            "материал полок",
            "материал шинки",
        ],
        "volume": [
            "объем",
            "объём",
            "вместимость",
        ],
        "load": [
            "грузопод",
            "грузоподъ",
            "нагруз",
            "загрузка",
            "статическ",
            "динамическ",
            "стеллаж",
            "полк",
            "секц",
        ],
        "temperature": [
            "температур",
            "мороз",
            "термическ",
        ],
        "resistance": [
            "влаго",
            "уф",
            "антистат",
            "светопропуск",
            "плотность",
        ],
        "certification": [
            "маркировка un",
            "сертифицирован",
            "наличие знаков",
            "знаков",
            "обозначений",
        ],
        "technology": [
            "технология",
            "срок службы",
        ],
        "purpose": [
            "назначение",
        ],
        "series": [
            "серия",
        ],
        "features": [
            "особенности",
            "возможен вариант",
            "изготовления",
        ],
    },
    2: {
        "weight": [
            "вес",
        ],
        "color": [
            "цвет",
            "внешний вид",
        ],
        "brand": [
            "бренд",
            "производитель",
        ],
        "country": [
            "страна",
            "страна производства",
        ],
        "unit": [
            "базовая единица",
        ],
        "label_place": [
            "место под этикет",
        ],
        "location": [
            "расположение",
        ],
        "economy": [
            "экономия объема",
        ],
        "marketing": [
            "наши предложения",
            "номенклатура прайс",
            "наименование для сайта",
        ],
    },
}

IGNORED_PROPERTY_KEYWORDS = [
    "null",
    "артикул",
    "артикул товара",
    "артикул продукта",
    "код",
    "код товара",
    "код товара в ай-пласт",
    "sku",
    "штрихкод",
    "barcode",
    "продажи b2b",
    "продажи b2c",
    "статус ассортиментной матрицы",
    "сам",
    "похожие товары",
    "кол-во",
    "количество sk",
    "количество в 40",
    "количество в еврофуре",
    "количество в фуре",
    "количество в контейнере",
    "количество в стопке",
    "количество в упаковке",
    "количество на паллете",
    "количество на паллетоместе",
    "паллете",
    "паллета",
    "паллетоместе",
    "еврофуре",
    "фуре",
    "40 ft",
    "40 hc",
    "40 hq",
    "82 м3",
    "120 м3",
    "вместимость луковиц",
]


YES_VALUES = {"да", "yes", "true", "1", "+"}
NO_VALUES = {"нет", "no", "false", "0", "-"}

DIMENSION_PATTERN = re.compile(
    r"(\d{3,4})\s*[xх×]\s*(\d{3,4})(?:\s*[xх×]\s*(\d{3,4}))?",
    re.IGNORECASE,
)


def clean_text(value):
    if value is None:
        return ""

    return str(value).strip().lower().replace("ё", "е")


def normalize_token(value):
    value = clean_text(value)
    value = re.sub(r"[^a-zа-я0-9]+", "_", value)
    value = re.sub(r"_+", "_", value)
    return value.strip("_")


def repeat_append(parts, value, weight):
    value = clean_text(value)

    if not value:
        return

    for _ in range(max(int(weight), 1)):
        parts.append(value)


def is_ignored_property(prop_name):
    prop_name = clean_text(prop_name)

    if not prop_name:
        return True

    return any(keyword in prop_name for keyword in IGNORED_PROPERTY_KEYWORDS)


def get_canonical_property(prop_name):
    prop_name = clean_text(prop_name)

    for groups in PROPERTY_GROUPS_BY_WEIGHT.values():
        for canonical_name, keywords in groups.items():
            if any(keyword in prop_name for keyword in keywords):
                return canonical_name

    return normalize_token(prop_name)


def get_property_weight(prop_name):
    prop_name = clean_text(prop_name)

    for weight, groups in PROPERTY_GROUPS_BY_WEIGHT.items():
        for keywords in groups.values():
            if any(keyword in prop_name for keyword in keywords):
                return weight

    return 1


def build_property_tokens(prop_name, prop_value):
    prop_name_clean = clean_text(prop_name)
    prop_value_clean = clean_text(prop_value)

    if not prop_name_clean and not prop_value_clean:
        return []

    canonical_property = get_canonical_property(prop_name_clean)

    tokens = [
        f"{canonical_property}: {prop_value_clean}",
    ]

    prop_token = normalize_token(canonical_property)
    value_token = normalize_token(prop_value_clean)

    if prop_token and value_token:
        tokens.append(f"property_{prop_token}_{value_token}")

    if prop_value_clean in YES_VALUES and prop_token:
        tokens.append(f"property_{prop_token}_yes")

    if prop_value_clean in NO_VALUES and prop_token:
        tokens.append(f"property_{prop_token}_no")

    return tokens


def get_price_model(source):
    model_name = PRICE_MODELS_BY_SOURCE.get(source)

    if not model_name:
        return None

    try:
        return apps.get_model("datasets", model_name)
    except LookupError:
        return None


def get_name_field(model):
    model_fields = {field.name for field in model._meta.fields}

    for field_name in NAME_FIELD_CANDIDATES:
        if field_name in model_fields:
            return field_name

    return None


def get_product_name(product_url):
    model = get_price_model(product_url.source)

    if model is None:
        return None

    name_field = get_name_field(model)

    if not name_field:
        return None

    row = (
        model.objects
        .filter(product_key=product_url.id)
        .order_by("-date_add")
        .values(name_field)
        .first()
    )

    if not row:
        return None

    return row.get(name_field)


def build_product_text(product_url):
    product_name = get_product_name(product_url)

    properties = ParserProductProperty.objects.filter(
        source=product_url.source,
        product_key=product_url.id,
    ).values_list("properties", "value")

    parts = []

    repeat_append(parts, product_url.source, SOURCE_WEIGHT)
    repeat_append(parts, product_url.additional_property, ADDITIONAL_PROPERTY_WEIGHT)
    repeat_append(parts, product_name, NAME_WEIGHT)

    for prop_name, prop_value in properties:
        if is_ignored_property(prop_name):
            continue

        weight = get_property_weight(prop_name)

        for token in build_property_tokens(prop_name, prop_value):
            repeat_append(parts, token, weight)

    return " ".join(parts)


def build_rule_text(product_url, product_text, product_name):
    return " ".join([
        clean_text(product_text),
        clean_text(product_name),
        clean_text(product_url.url),
        clean_text(product_url.additional_property),
    ])


def extract_dimensions(text):
    text = clean_text(text)

    match = DIMENSION_PATTERN.search(text)

    if not match:
        return None

    width = int(match.group(1))
    length = int(match.group(2))
    height = int(match.group(3)) if match.group(3) else None

    first_two = sorted([width, length], reverse=True)

    return {
        "width": width,
        "length": length,
        "height": height,
        "base_size": f"{first_two[0]}х{first_two[1]}",
        "full_size": (
            f"{width}х{length}х{height}"
            if height
            else f"{width}х{length}"
        ),
    }


def has_door(text):
    text = clean_text(text)
    return "двер" in text or "door" in text


def has_skids(text):
    text = clean_text(text)
    return "лыж" in text or "полоз" in text or "skid" in text


def is_bigbox_product(text):
    text = clean_text(text)

    bigbox_markers = [
        "bigbox",
        "big box",
        "boxpallet",
        "box pallet",
        "box-pallet",
        "konteynery box pallet",
        "konteynery-box-pallet",
        "крупногабаритный контейнер",
    ]

    return any(marker in text for marker in bigbox_markers)


def build_dimension_subcategory(product_text):
    dimensions = extract_dimensions(product_text)

    if not dimensions:
        return None

    text = clean_text(product_text)

    if is_bigbox_product(text):
        parts = [
            f"Контейнеры типа BigBox {dimensions['base_size']}",
        ]

        if has_skids(text):
            parts.append("на лыжах")

        if has_door(text):
            parts.append("с дверцей")

        return " ".join(parts)

    return None


def get_existing_values(field_name):
    return set(
        ParserProductClassification.objects
        .filter(status=ParserProductClassification.STATUS_ACTIVE)
        .exclude(**{f"{field_name}__isnull": True})
        .exclude(**{field_name: ""})
        .values_list(field_name, flat=True)
    )


def build_training_dataset(target_field):
    classifications = (
        ParserProductClassification.objects
        .filter(status=ParserProductClassification.STATUS_ACTIVE)
        .exclude(**{f"{target_field}__isnull": True})
        .exclude(**{target_field: ""})
    )

    product_urls_by_id = {
        item.id: item
        for item in ParserProductUrl.objects.filter(
            id__in=classifications.values_list("product_key", flat=True)
        )
    }

    texts = []
    labels = []

    for classification in classifications:
        product_url = product_urls_by_id.get(classification.product_key)

        if not product_url:
            continue

        text = build_product_text(product_url)
        label = getattr(classification, target_field)

        if not text or not label:
            continue

        texts.append(text)
        labels.append(label)

    return texts, labels


def train_classifier(target_field):
    texts, labels = build_training_dataset(target_field)

    unique_labels = set(labels)

    if len(texts) < 5 or len(unique_labels) < 2:
        return None

    model = Pipeline([
        (
            "tfidf",
            TfidfVectorizer(
                analyzer="char_wb",
                ngram_range=(3, 5),
                min_df=1,
                sublinear_tf=True,
            ),
        ),
        (
            "clf",
            LogisticRegression(
                max_iter=1000,
                class_weight="balanced",
            ),
        ),
    ])

    model.fit(texts, labels)

    return model


def predict_one(model, text):
    if model is None or not text:
        return None, None

    prediction = model.predict([text])[0]

    probability = None

    if hasattr(model.named_steps["clf"], "predict_proba"):
        probability = model.predict_proba([text])[0].max()

    return prediction, probability


def build_suggested_classification_rows(product_urls):
    category_model = train_classifier("category")
    subcategory_model = train_classifier("subcategory")
    subcategory_type_model = train_classifier("subcategory_type")

    existing_subcategories = get_existing_values("subcategory")

    rows = []

    for product_url in product_urls:
        text = build_product_text(product_url)
        product_name = get_product_name(product_url)

        category, category_confidence = predict_one(category_model, text)
        subcategory, subcategory_confidence = predict_one(subcategory_model, text)
        subcategory_type, subcategory_type_confidence = predict_one(
            subcategory_type_model,
            text,
        )

        rule_text = build_rule_text(
            product_url=product_url,
            product_text=text,
            product_name=product_name,
        )
        rule_subcategory = build_dimension_subcategory(rule_text)

        auto_created_subcategory = False
        suggestion_note = None

        if rule_subcategory:
            subcategory = rule_subcategory
            subcategory_confidence = 0.99

            if rule_subcategory not in existing_subcategories:
                auto_created_subcategory = True
                suggestion_note = "subcategory_created_by_dimension_rule"
            else:
                suggestion_note = "subcategory_overridden_by_dimension_rule"

        confidences = [
            value
            for value in [
                category_confidence,
                subcategory_confidence,
                subcategory_type_confidence,
            ]
            if value is not None
        ]

        confidence = min(confidences) if confidences else None

        rows.append({
            "product_key": product_url.id,
            "source": product_url.source,
            "url": product_url.url,
            "additional_property": product_url.additional_property,
            "product_name": product_name,
            "suggested_category": category,
            "suggested_subcategory": subcategory,
            "suggested_subcategory_type": subcategory_type,
            "classification_source": "auto",
            "confidence": round(float(confidence), 4) if confidence is not None else None,
            "category_confidence": round(float(category_confidence), 4) if category_confidence is not None else None,
            "subcategory_confidence": round(float(subcategory_confidence), 4) if subcategory_confidence is not None else None,
            "subcategory_type_confidence": round(float(subcategory_type_confidence), 4) if subcategory_type_confidence is not None else None,
            "status": ParserProductClassification.STATUS_ACTIVE,
            "auto_created_subcategory": auto_created_subcategory,
            "suggestion_note": suggestion_note,
        })

    return rows