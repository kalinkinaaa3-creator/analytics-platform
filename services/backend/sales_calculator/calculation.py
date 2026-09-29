from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, ROUND_CEILING, ROUND_FLOOR

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


def rounded(value, mode):
    if mode == "none":
        return value
    return value.quantize(Decimal(1), rounding={"half_up": ROUND_HALF_UP, "ceil": ROUND_CEILING, "floor": ROUND_FLOOR}[mode])


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
        if quantity <= 0 or quantity > 1000000000:
            raise ValueError("Количество должно быть больше нуля и не более 1 млрд")
        override = item.get("price_type", "auto")
        if override not in (*PRICE_TYPES, "auto"):
            raise ValueError("Некорректный тип цены")
        rows.append({**products[key], "quantity": quantity, "override": override})
    def price(row, tier):
        return rounded(number(row[tier]), config["rounding"])
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
    incomplete = {"weight": False, "pallets": False}
    for row in rows:
        for target, source in (("weight", "weight_value"), ("pallets", "pallet_value")):
            value = row.get(source)
            if value is None or number(value) == 0:
                incomplete[target] = True
                continue
            logistics[target] += (number(value) * row["quantity"] if target == "weight" else
                                    (row["quantity"] / number(value)).to_integral_value(rounding=ROUND_CEILING))
    return {"rows": rows, "automatic_type": automatic,
            "manual": any(r["override"] != "auto" for r in rows),
            "positions": len(rows), "quantity": sum((r["quantity"] for r in rows), Decimal(0)),
            "net": net, "vat": vat, "gross": net + vat,
            "warning": net > Decimal(config["warning_threshold"]),
            "next_type": PRICE_TYPES[tier_index + 1] if tier_index < 3 else None,
            "next_gap": max(Decimal(0), Decimal(config["thresholds"][tier_index]) - total(automatic)) if tier_index < 3 else None,
            "logistics": {k: None if incomplete[k] else v for k, v in logistics.items()}}
