from copy import deepcopy
from decimal import Decimal, InvalidOperation
from .properties import EXTRA_CHARACTERISTICS

PRICE_TYPES = ("retail", "small", "medium", "large")
PRICE_LABELS = dict(zip(PRICE_TYPES, ("Розница", "Мелкий опт", "Средний опт", "Крупный опт")))
CHARACTERISTICS = {
    "dimensions": "Габариты Д×Ш×В, мм", "color": "Цвет", "bottom": "Тип дна",
    "walls": "Тип стенок", "perforation": "Стенки", "lid": "Тип крышки",
    "equipment": "Комплектация", "loading": "Макс. загрузка, кг",
    "load": "Макс. нагрузка, кг", "dynamic_load": "Макс. динамическая нагрузка, кг",
    "shelf_load": "Макс. нагрузка на полку, кг", "volume": "Объем, л", "weight": "Вес, кг",
}
LOGISTICS = {"pallet": "Паллето-место, шт", "truck": "Еврофура, шт",
             "truck82": "Еврофура 82 м³, шт", "pallet_size": "Паллета, мм",
             "packing": "Вложение", "tnved": "ТН ВЭД"}
DEFAULT_CHARACTERISTICS = list(CHARACTERISTICS)
DEFAULT_LOGISTICS = [key for key in LOGISTICS if key != "truck"]
CHARACTERISTICS.update(EXTRA_CHARACTERISTICS)
LOGISTICS["truck82_no_pallet"] = "Еврофура 82 м³, шт (без паллеты)"
WAREHOUSES = [
    'Склад "Склад комплектации мусорных контейнеров"', "Склад цеха №2",
    "Склад готовой продукции №2", "Склад готовой продукции №4",
    "Склад сырья №3 Ставрово с 01.10.2014", 'Склад "Цех "Ставрово"',
    "Склад готовой продукции №3 Ставрово с 01.10.2014", "Склад готовой продукции №5",
    "Склад №36", "Склад №24 НОВ (Москва)",
]
BASE_COLUMNS = {"image": "Изображение", "code": "Артикул",
                "name": "Номенклатура прайс-листа", "name_1c": "Номенклатура (артикул)",
                "characteristics": "Характеристики", "logistics": "Логистика", "quantity": "Количество"}
FULL_COLUMNS = {**BASE_COLUMNS, "price_type": "Тип цены", "unit_net": "Цена руб. без НДС",
                "sum_net": "Сумма руб. без НДС", "unit_gross": "Цена руб. с НДС",
                "sum_gross": "Сумма руб. с НДС", "url": "На сайте"}
SIMPLE_COLUMNS = {**BASE_COLUMNS, **{f"{t}_{tax}": f"{label} руб. {'без НДС' if tax == 'net' else 'с НДС'}"
                  for t, label in PRICE_LABELS.items() for tax in ("net", "gross")}, "url": "На сайте"}
DEFAULTS = {
    "region": "", "vat": 22,
    "thresholds": [50000, 300000, 800000], "warning_threshold": 2200000,
    "characteristics": DEFAULT_CHARACTERISTICS, "logistics": DEFAULT_LOGISTICS,
    "warehouses": WAREHOUSES, "full_columns": list(FULL_COLUMNS), "simple_columns": list(SIMPLE_COLUMNS),
    "full_column_order": list(FULL_COLUMNS), "simple_column_order": list(SIMPLE_COLUMNS),
}


def validate_config(data):
    # Ignore legacy rounding preferences: whole-ruble rounding is now mandatory.
    if isinstance(data, dict):
        data = {key: value for key, value in data.items() if key != "rounding"}
    if not isinstance(data, dict) or set(data) - set(DEFAULTS):
        raise ValueError("Некорректные настройки калькулятора")
    result = deepcopy(DEFAULTS)
    result.update(data)
    if result["vat"] not in (0, 22) or isinstance(result["vat"], bool):
        raise ValueError("Выберите НДС 0% или 22%")
    for key, choices in (("characteristics", CHARACTERISTICS), ("logistics", LOGISTICS),
                         ("warehouses", WAREHOUSES), ("full_columns", FULL_COLUMNS), ("simple_columns", SIMPLE_COLUMNS)):
        value = result[key]
        if key.endswith("_columns") and isinstance(value, list):
            # Preferences saved before removal of the internal product key remain valid.
            value = ["name_1c" if x == "price_list" else x for x in value if x != "product_key"]
        if not isinstance(value, list) or any(not isinstance(x, str) or (not x.strip() or len(x) > 255 if key == "warehouses" else x not in choices) for x in value):
            raise ValueError(f"Некорректный список: {key}")
        result[key] = list(dict.fromkeys(value))
    for mode, choices in (("full", FULL_COLUMNS), ("simple", SIMPLE_COLUMNS)):
        key = mode + "_column_order"
        order = result[key]
        if not isinstance(order, list) or any(not isinstance(x, str) or x not in choices for x in order):
            raise ValueError(f"Некорректный список: {key}")
        # Keep positions of hidden columns; append future columns in default order.
        result[key] = list(dict.fromkeys([*order, *choices]))
        result[mode + "_columns"] = [x for x in result[key] if x in result[mode + "_columns"]]
    try:
        thresholds = [Decimal(str(x)) for x in result["thresholds"]]
        warning = Decimal(str(result["warning_threshold"]))
        if len(thresholds) != 3 or not all(x.is_finite() for x in thresholds + [warning]):
            raise ValueError()
        if not (0 < thresholds[0] < thresholds[1] < thresholds[2] < warning):
            raise ValueError()
    except (ValueError, TypeError, InvalidOperation):
        raise ValueError("Пороги должны быть положительными и строго возрастать")
    result["thresholds"] = [str(x) for x in thresholds]
    result["warning_threshold"] = str(warning)
    if not isinstance(result["region"], str) or len(result["region"]) > 255:
        raise ValueError("Некорректный регион")
    return result
