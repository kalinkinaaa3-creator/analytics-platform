from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from fractions import Fraction
from math import ceil

from .configuration import PRICE_TYPES, validate_config

CENT = Decimal("0.01")


def number(value):
    try:
        result = Decimal(str(value))
        if not result.is_finite() or result < 0:
            raise ValueError()
        return result
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Отсутствует цена или указано некорректное число")


def calculate(products, items, config):
    config = validate_config(config)
    if not isinstance(items, list) or len(items) > 3000:
        raise ValueError("Допускается не более 3000 позиций")
    rows, seen = [], set()
    for item in items:
        key = str(item["product_key"])
        if key in seen or key not in products:
            raise ValueError("Товар повторяется или отсутствует в выбранном регионе")
        seen.add(key)
        quantity = number(item.get("quantity", 1))
        if quantity <= 0 or quantity > 1000000000 or quantity != quantity.to_integral_value():
            raise ValueError("Количество должно быть целым числом от 1 до 1 млрд")
        override = item.get("price_type", "auto")
        if override not in (*PRICE_TYPES, "auto"):
            raise ValueError("Некорректный тип цены")
        rows.append({**products[key], "quantity": quantity, "override": override})
    def price(row, tier):
        return number(row[tier]).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    def total(tier):
        return sum(((price(r, tier) * r["quantity"]).quantize(CENT, rounding=ROUND_HALF_UP) for r in rows), Decimal(0))
    tier_index = 0
    for index, boundary in enumerate(config["thresholds"]):
        if total(PRICE_TYPES[index]) > Decimal(boundary):
            tier_index = index + 1
        else:
            break
    automatic = PRICE_TYPES[tier_index]
    factor = 1 + Decimal(config["vat"]) / 100
    for row in rows:
        row["price_type"] = automatic if row["override"] == "auto" else row["override"]
        row["unit_net"] = price(row, row["price_type"])
        row["unit_gross"] = (row["unit_net"] * factor).quantize(CENT, rounding=ROUND_HALF_UP)
        row["sum_net"] = (row["unit_net"] * row["quantity"]).quantize(CENT, rounding=ROUND_HALF_UP)
        row["vat_amount"] = (row["sum_net"] * (factor - 1)).quantize(CENT, rounding=ROUND_HALF_UP)
        row["sum_gross"] = row["sum_net"] + row["vat_amount"]
        for tier in PRICE_TYPES:
            row[tier + "_net"] = price(row, tier)
            row[tier + "_gross"] = (price(row, tier) * factor).quantize(CENT, rounding=ROUND_HALF_UP)
    net = sum((r["sum_net"] for r in rows), Decimal(0))
    vat = sum((r["vat_amount"] for r in rows), Decimal(0))
    logistics = {"weight": Decimal(0), "pallets": Decimal(0)}
    pallet_share = Fraction(0)
    missing = {"weight": 0, "pallets": 0}
    for row in rows:
        for target, source in (("weight", "weight_value"), ("pallets", "pallet_value")):
            value = row.get(source)
            try:
                parsed = number(value)
            except ValueError:
                parsed = None
            if parsed is None or (target == "pallets" and parsed == 0):
                missing[target] += 1
                continue
            if target == "weight":
                logistics[target] += parsed * row["quantity"]
            else:
                pallet_share += Fraction(row["quantity"]) / Fraction(parsed)
    logistics["pallets"] = Decimal(ceil(pallet_share))
    return {"rows": rows, "automatic_type": automatic,
            "manual": any(r["override"] != "auto" for r in rows),
            "positions": len(rows), "quantity": sum((r["quantity"] for r in rows), Decimal(0)),
            "net": net, "vat": vat, "gross": net + vat,
            "warning": net > Decimal(config["warning_threshold"]),
            "next_type": PRICE_TYPES[tier_index + 1] if tier_index < 3 else None,
            "next_gap": max(Decimal(0), Decimal(config["thresholds"][tier_index]) - total(automatic)) if tier_index < 3 else None,
            "logistics": {k: None if rows and missing[k] == len(rows) else v for k, v in logistics.items()},
            "logistics_missing": missing}
