from collections import defaultdict
from datetime import datetime, date, timedelta
from decimal import Decimal, getcontext
import math


def to_decimal(value):
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def to_float(value):
    if value is None:
        return None
    return float(value)


def date_to_str(value):
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value) if value else None


def get_default_purchases_filters(filters=None):
    filters = filters or {}

    yesterday = datetime.now().date() - timedelta(days=1)

    def values(key):
        value = filters.get(key, [])
        return [item for item in (value if isinstance(value, (list, tuple)) else [value]) if item not in ("", None)]

    return {
        "nomenclature_code": values("nomenclature_code"),
        "nomenclature": values("nomenclature"),
        "partner": values("partner"),
        "date_start": filters.get("date_start") or f"{yesterday.year}-01-01",
        "date_end": filters.get("date_end") or yesterday.isoformat(),
    }


def build_filter_values(rows):
    return {
        "nomenclature_code": sorted({
            r.get("nomenclature_code") for r in rows if r.get("nomenclature_code")
        }),
        "nomenclature": sorted({
            r.get("nomenclature") for r in rows if r.get("nomenclature")
        }),
        "partner": sorted({
            r.get("partner") for r in rows if r.get("partner")
        }),
    }


def build_indicator_map(indicator_rows):
    grouped = defaultdict(list)

    for row in indicator_rows:
        d = row.get("date_draft")
        indicator = row.get("indicator")

        if d and indicator is not None:
            grouped[date_to_str(d)].append(to_decimal(indicator))

    result = {}

    for d, values in grouped.items():
        result[d] = sum(values) / Decimal(len(values))

    return result


def group_purchases_by_month(rows):
    monthly_data = {}

    for row in rows:
        d = row.get("date_draft")

        if not d:
            continue

        month_year = date_to_str(d)[:7] + "-01"

        key = (
            month_year,
            row.get("nomenclature_code") or "",
            row.get("nomenclature") or "",
            row.get("partner") or "",
        )

        if key not in monthly_data:
            monthly_data[key] = {
                "month_year": month_year,
                "nomenclature_code": row.get("nomenclature_code") or "",
                "nomenclature": row.get("nomenclature") or "",
                "partner": row.get("partner") or "",
                "quantity_1C": Decimal("0"),
                "revenue_1C": Decimal("0"),
                "price": Decimal("0"),
            }

        quantity = to_decimal(row.get("quantity_1C"))
        revenue = to_decimal(row.get("revenue_1C"))
        vat = to_decimal(row.get("VAT_1C"))

        monthly_data[key]["quantity_1C"] += quantity
        monthly_data[key]["revenue_1C"] += revenue - vat

    result = []

    for item in monthly_data.values():
        qty = item["quantity_1C"]
        rev = item["revenue_1C"]

        item["price"] = (rev / qty).quantize(Decimal("0.01")) if qty else Decimal("0")
        result.append(item)

    result.sort(
        key=lambda x: (
            x["month_year"],
            x["nomenclature_code"],
            x["nomenclature"],
            x["partner"],
        ),
        reverse=True,
    )

    return result


def add_indicator_to_purchases(purchases_list, indicator_rows):
    indicator_map = build_indicator_map(indicator_rows)

    for item in purchases_list:
        item["indicator"] = indicator_map.get(item["month_year"])

    return purchases_list


def add_deviation_to_purchases(purchases_list):
    for item in purchases_list:
        price = item.get("price")
        indicator = item.get("indicator")

        if price is not None and indicator is not None:
            item["deviation"] = (price - indicator).quantize(Decimal("0.01"))
        else:
            item["deviation"] = None

    return purchases_list


def build_purchases_indicators(purchases_list, indicator_rows=None):
    total_quantity = Decimal("0")
    total_revenue = Decimal("0")

    for item in purchases_list:
        qty = to_decimal(item.get("quantity_1C"))
        rev = to_decimal(item.get("revenue_1C"))
        total_quantity += qty
        total_revenue += rev

    plan_values = [to_decimal(row.get("indicator")) for row in (indicator_rows or []) if row.get("indicator") is not None]

    fact = (total_revenue / total_quantity).quantize(Decimal("0.01")) if total_quantity else Decimal("0")
    plan = (sum(plan_values) / len(plan_values)).quantize(Decimal("0.01")) if plan_values else Decimal("0")
    deviation = (fact - plan).quantize(Decimal("0.01"))

    return {
        "fact": to_float(fact),
        "plan": to_float(plan),
        "deviation": to_float(deviation),
        "quantity": to_float(total_quantity),
        "cost": to_float(total_revenue),
    }


def build_purchases_tree(purchases_list):
    getcontext().prec = 28

    tree = {}

    for row in purchases_list:
        month = row["month_year"]
        code = row.get("nomenclature_code") or ""

        if month not in tree:
            tree[month] = {
                "month_year": month,
                "quantity_1C": Decimal("0"),
                "revenue_1C": Decimal("0"),
                "indicator_weighted_sum": Decimal("0"),
                "children": {},
            }

        month_node = tree[month]

        if code not in month_node["children"]:
            month_node["children"][code] = {
                "month_year": month,
                "nomenclature_code": code,
                "quantity_1C": Decimal("0"),
                "revenue_1C": Decimal("0"),
                "indicator_weighted_sum": Decimal("0"),
                "children": [],
            }

        code_node = month_node["children"][code]

        qty = to_decimal(row.get("quantity_1C"))
        revenue = to_decimal(row.get("revenue_1C"))
        indicator = to_decimal(row.get("indicator"))

        for node in (month_node, code_node):
            node["quantity_1C"] += qty
            node["revenue_1C"] += revenue
            node["indicator_weighted_sum"] += indicator * qty

        code_node["children"].append(row)

    result = []

    for month_node in tree.values():
        total_qty = month_node["quantity_1C"]
        total_revenue = month_node["revenue_1C"]

        month_node["price"] = total_revenue / total_qty if total_qty else Decimal("0")
        month_node["indicator"] = month_node["indicator_weighted_sum"] / total_qty if total_qty else Decimal("0")
        month_node["deviation"] = month_node["price"] - month_node["indicator"]

        children = []

        for code_node in month_node["children"].values():
            qty = code_node["quantity_1C"]
            revenue = code_node["revenue_1C"]

            code_node["price"] = revenue / qty if qty else Decimal("0")
            code_node["indicator"] = code_node["indicator_weighted_sum"] / qty if qty else Decimal("0")
            code_node["deviation"] = code_node["price"] - code_node["indicator"]

            code_node.pop("indicator_weighted_sum", None)

            code_node["children"] = [
                serialize_purchase_row(child)
                for child in code_node["children"]
            ]

            children.append(serialize_purchase_row(code_node))

        month_node["children"] = children
        month_node.pop("indicator_weighted_sum", None)

        result.append(serialize_purchase_row(month_node))

    result.sort(key=lambda x: x["month_year"], reverse=True)

    return result


def serialize_purchase_row(row):
    result = {}

    for key, value in row.items():
        if isinstance(value, Decimal):
            try:
                result[key] = float(value.quantize(Decimal("0.01")))
            except Exception:
                result[key] = float(value)
        elif isinstance(value, (datetime, date)):
            result[key] = value.isoformat()
        else:
            result[key] = value

    return result


def build_price_chart_data(rows, indicator_rows):
    if not rows and not indicator_rows:
        return None

    indicator_map = build_indicator_map(indicator_rows)

    grouped = defaultdict(lambda: {
        "revenue": Decimal("0"),
        "quantity": Decimal("0"),
        "indicator_sum": Decimal("0"),
        "indicator_count": 0,
    })

    dates = [r.get("date_draft") for r in [*rows, *indicator_rows] if r.get("date_draft")]

    if not dates:
        return None

    dates_str = [date_to_str(d) for d in dates]
    date_start = min(dates_str)
    date_end = max(dates_str)

    start_dt = datetime.strptime(date_start, "%Y-%m-%d").date()
    end_dt = datetime.strptime(date_end, "%Y-%m-%d").date()

    delta_days = (end_dt - start_dt).days
    same_month = start_dt.year == end_dt.year and start_dt.month == end_dt.month
    group_by_day = same_month or (start_dt.year == end_dt.year and delta_days < 30)

    for row in rows:
        d = row.get("date_draft")

        if not d:
            continue

        d_str = date_to_str(d)
        key = d_str if group_by_day else d_str[:7]

        qty = to_decimal(row.get("quantity_1C"))
        revenue = to_decimal(row.get("revenue_1C")) - to_decimal(row.get("VAT_1C"))
        grouped[key]["revenue"] += revenue
        grouped[key]["quantity"] += qty

    monthly_indicators = defaultdict(list)
    for indicator_date, indicator in indicator_map.items():
        monthly_indicators[indicator_date[:7]].append(indicator)
    for key in list(grouped):
        values = monthly_indicators.get(key[:7], [])
        if values:
            grouped[key]["indicator_sum"] = sum(values)
            grouped[key]["indicator_count"] = len(values)
    for month, values in monthly_indicators.items():
        key = f"{month}-01" if group_by_day else month
        if key not in grouped:
            grouped[key]["indicator_sum"] = sum(values)
            grouped[key]["indicator_count"] = len(values)

    keys_sorted = sorted(grouped.keys())

    points = []

    for key in keys_sorted:
        item = grouped[key]

        fact = item["revenue"] / item["quantity"] if item["quantity"] else None
        plan = item["indicator_sum"] / item["indicator_count"] if item["indicator_count"] else None

        points.append({
            "key": key,
            "fact": float(fact.quantize(Decimal("0.01"))) if fact is not None else None,
            "plan": float(plan.quantize(Decimal("0.01"))) if plan is not None else None,
        })

    all_prices = [
        p
        for item in points
        for p in (item["fact"], item["plan"])
        if p is not None
    ]

    if not all_prices:
        return None

    y_min = min(all_prices)
    y_max = max(all_prices)

    step = 5
    while True:
        y_min_axis = math.floor((y_min - step) / step) * step
        y_max_axis = math.ceil((y_max + step) / step) * step
        if (y_max_axis - y_min_axis) // step + 1 <= 8:
            break
        # Keep a readable 1/2/5 progression instead of thousands of 5-ruble ticks.
        magnitude = 10 ** int(math.floor(math.log10(step)))
        multiple = step // magnitude
        step = (2 if multiple < 2 else 5 if multiple < 5 else 10) * magnitude

    y_range = y_max_axis - y_min_axis or 1
    n_points = len(points) or 1

    fact_coords = []
    plan_coords = []

    for i, item in enumerate(points):
        x_norm = (i + 0.5) / n_points

        if item["fact"] is not None:
            fact_coords.append({
                "x": round(x_norm, 4),
                "y": round((item["fact"] - y_min_axis) / y_range, 4),
                "value": item["fact"],
            })

        if item["plan"] is not None:
            plan_coords.append({
                "x": round(x_norm, 4),
                "y": round((item["plan"] - y_min_axis) / y_range, 4),
                "value": item["plan"],
            })

    y_ticks = []

    for value in range(y_min_axis, y_max_axis + step, step):
        y_ticks.append({
            "value": value,
            "pos": round((value - y_min_axis) / y_range, 4),
        })

    x_labels = [
        {
            "pos": round((i + 0.5) / n_points, 4),
            "label": item["key"],
        }
        for i, item in enumerate(points)
    ]

    return {
        "title": "Динамика цены, руб/кг",
        "x_labels": x_labels,
        "y_axis": {
            "min": y_min_axis,
            "max": y_max_axis,
            "ticks": y_ticks,
        },
        "fact": fact_coords,
        "plan": plan_coords,
    }


def prepare_fb_purchases_dashboard(rows, indicator_rows, filters=None, filter_options=None):
    filters = get_default_purchases_filters(filters)

    filter_values = filter_options or build_filter_values(rows)

    purchases_list = group_purchases_by_month(rows)
    purchases_list = add_indicator_to_purchases(purchases_list, indicator_rows)
    purchases_list = add_deviation_to_purchases(purchases_list)

    indicators = build_purchases_indicators(purchases_list, indicator_rows)
    purchases_tree = build_purchases_tree(purchases_list)
    chart = build_price_chart_data(rows, indicator_rows)

    return {
        "filters": filters,
        "filter_values": filter_values,
        "indicators": indicators,
        "chart": chart,
        "purchases_tree": purchases_tree,
        "total_rows": len(rows),
    }
