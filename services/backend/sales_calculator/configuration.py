from copy import deepcopy
from decimal import Decimal, InvalidOperation

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
WAREHOUSES = [
    'Склад "Склад комплектации мусорных контейнеров"', "Склад цеха №2",
    "Склад готовой продукции №2", "Склад готовой продукции №4",
    "Склад сырья №3 Ставрово с 01.10.2014", 'Склад "Цех "Ставрово"',
    "Склад готовой продукции №3 Ставрово с 01.10.2014", "Склад готовой продукции №5",
    "Склад №36", "Склад №24 НОВ (Москва)",
]
BASE_COLUMNS = {"image": "Фото", "product_key": "Код", "code": "Код 1С / Артикул",
                "name": "Наименование", "price_list": "Номенклатура прайс-листа",
                "characteristics": "Характеристики", "logistics": "Логистика", "quantity": "Количество"}
FULL_COLUMNS = {**BASE_COLUMNS, "price_type": "Тип цены", "unit_net": "Цена без НДС, ₽",
                "sum_net": "Сумма без НДС, ₽", "unit_gross": "Цена с НДС, ₽",
                "sum_gross": "Сумма с НДС, ₽", "url": "На сайте"}
SIMPLE_COLUMNS = {**BASE_COLUMNS, **{f"{t}_{tax}": f"{label} {'без НДС' if tax == 'net' else 'с НДС'}, ₽"
                  for t, label in PRICE_LABELS.items() for tax in ("net", "gross")}, "url": "На сайте"}
DEFAULTS = {
    "region": "", "vat": 22, "rounding": "half_up",
    "thresholds": [50000, 300000, 800000], "warning_threshold": 2200000,
    "characteristics": list(CHARACTERISTICS), "logistics": [k for k in LOGISTICS if k != "truck"],
    "warehouses": WAREHOUSES, "full_columns": list(FULL_COLUMNS), "simple_columns": list(SIMPLE_COLUMNS),
}


def validate_config(data):
    if not isinstance(data, dict) or set(data) - set(DEFAULTS):
        raise ValueError("Некорректные настройки калькулятора")
    result = deepcopy(DEFAULTS)
    result.update(data)
    if result["vat"] not in (0, 22) or isinstance(result["vat"], bool):
        raise ValueError("Выберите НДС 0% или 22%")
    if result["rounding"] not in ("none", "half_up", "ceil", "floor"):
        raise ValueError("Некорректное округление")
    for key, choices in (("characteristics", CHARACTERISTICS), ("logistics", LOGISTICS),
                         ("warehouses", WAREHOUSES), ("full_columns", FULL_COLUMNS), ("simple_columns", SIMPLE_COLUMNS)):
        value = result[key]
        if not isinstance(value, list) or any(not isinstance(x, str) or x not in choices for x in value):
            raise ValueError(f"Некорректный список: {key}")
        result[key] = list(dict.fromkeys(value))
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
