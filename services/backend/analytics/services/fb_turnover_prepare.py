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
        return 0
    return float(value)


def date_to_str(value):
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value) if value else None


def serialize_value(value):
    if isinstance(value, Decimal):
        try:
            return float(value.quantize(Decimal("0.01")))
        except Exception:
            return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def serialize_row(row):
    return {
        key: serialize_value(value)
        for key, value in row.items()
    }


def normalize_filter_list(value):
    if value in ("", None, [], ()):
        return []

    if isinstance(value, tuple):
        value = list(value)

    if isinstance(value, list):
        return [
            item
            for item in value
            if item not in ("", None)
        ]

    return [value]


def get_default_turnover_filters(filters=None):
    filters = filters or {}

    today_minus_one = datetime.now().date() - timedelta(days=1)

    return {
        "nomenclature": normalize_filter_list(filters.get("nomenclature")),
        "warehouse_group": normalize_filter_list(filters.get("warehouse_group")),
        "warehouse": normalize_filter_list(filters.get("warehouse")),
        "quantity": normalize_filter_list(filters.get("quantity")),
        "date_start": filters.get("date_start") or f"{today_minus_one.year}-01-01",
        "date_end": filters.get("date_end") or today_minus_one.isoformat(),
    }


def build_filter_values(rows):
    return {
        "nomenclature": sorted({
            r.get("nomenclature") for r in rows if r.get("nomenclature")
        }),
        "warehouse_group": sorted({
            r.get("warehouse_group") for r in rows if r.get("warehouse_group")
        }),
        "warehouse": sorted({
            r.get("warehouse") for r in rows if r.get("warehouse")
        }),
        "quantity": sorted({
            r.get("quantity") for r in rows if r.get("quantity")
        }),
    }


def format_currency(value):
    value = float(value or 0)

    if abs(value) >= 1_000_000_000:
        return f"{value / 1_000_000_000:.0f} млрд"
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.0f} млн"
    if abs(value) >= 1_000:
        return f"{value / 1_000:.0f} тыс"

    return str(round(value, 2))


def nice_step(y_range, num_ticks=5):
    if y_range == 0:
        return 1

    raw_step = y_range / num_ticks
    magnitude = 10 ** math.floor(math.log10(raw_step))
    normalized = raw_step / magnitude

    if normalized <= 1:
        nice = 1
    elif normalized <= 2:
        nice = 2
    elif normalized <= 5:
        nice = 5
    else:
        nice = 10

    return nice * magnitude


def build_indicator_map(indicator_rows):
    result = {}

    for row in indicator_rows:
        d = row.get("date_start")
        indicator = row.get("indicator")

        if not d or indicator is None:
            continue

        result[date_to_str(d)] = to_decimal(indicator)

    return result


def get_indicator_for_date(indicator_map, target_date):
    d = date_to_str(target_date)
    return indicator_map.get(d, Decimal("0"))


def build_turnover_chart_data(rows, indicator_rows, date_start, date_end):
    if not rows:
        return None

    date_start_dt = datetime.strptime(date_start, "%Y-%m-%d").date()
    date_end_dt = datetime.strptime(date_end, "%Y-%m-%d").date()

    yesterday = date.today() - timedelta(days=1)

    delta_days = (date_end_dt - date_start_dt).days
    same_month = (
        date_start_dt.year == date_end_dt.year
        and date_start_dt.month == date_end_dt.month
    )
    group_by_day = same_month or (
        date_start_dt.year == date_end_dt.year
        and delta_days < 30
    )

    indicator_map = build_indicator_map(indicator_rows)

    grouped = defaultdict(lambda: {
        "middle_rubstock_values": [],
        "indicator_values": [],
        "date_end_list": [],
    })

    for row in rows:
        d = row.get("date_end")

        if not d:
            continue

        if d.month == yesterday.month and d.year == yesterday.year:
            d_for_key = min(d, yesterday)
        else:
            d_for_key = d

        key = (
            d_for_key.strftime("%Y-%m-%d")
            if group_by_day
            else d_for_key.strftime("%Y-%m")
        )

        middle_rubstock = to_decimal(row.get("middle_rubstock"))
        indicator_value = get_indicator_for_date(indicator_map, d)

        grouped[key]["middle_rubstock_values"].append(middle_rubstock)
        grouped[key]["indicator_values"].append(indicator_value)
        grouped[key]["date_end_list"].append(d)

    points_data = {}

    for key, item in grouped.items():
        middle_rubstocks = item["middle_rubstock_values"]
        indicators = item["indicator_values"]
        date_list = item["date_end_list"]

        valid_dates = [dt for dt in date_list if dt <= date_end_dt]

        if not valid_dates:
            continue

        max_date_in_group = max(valid_dates)
        max_date_idx = date_list.index(max_date_in_group)

        if group_by_day:
            selected_rubstocks = [
                value
                for value, dt in zip(middle_rubstocks, date_list)
                if dt == max_date_in_group
            ]
        else:
            selected_rubstocks = [
                value
                for value, dt in zip(middle_rubstocks, date_list)
                if dt == max_date_in_group
            ]

        total_middle_rubstock = sum(selected_rubstocks) if selected_rubstocks else Decimal("0")
        total_indicator = (
            indicators[max_date_idx]
            if max_date_idx < len(indicators)
            else Decimal("0")
        )

        points_data[key] = {
            "final_stock": total_middle_rubstock,
            "mutual_finstock": total_indicator,
        }

    keys_sorted = sorted(points_data.keys())

    points = [
        {
            "key": key,
            "final_stock": points_data[key]["final_stock"],
            "mutual_finstock": points_data[key]["mutual_finstock"],
        }
        for key in keys_sorted
    ]

    all_values = [
        value
        for point in points
        for value in (point["final_stock"], point["mutual_finstock"])
    ]

    if not all_values or all(value == 0 for value in all_values):
        return None

    y_min = min(all_values)
    y_max = max(all_values)
    y_range = y_max - y_min if y_max - y_min != 0 else Decimal("1")

    step = nice_step(float(y_range), num_ticks=5)

    padding = float(y_range) * 0.05
    y_min_axis = math.floor((float(y_min) - padding) / float(step)) * float(step)
    y_max_axis = math.ceil((float(y_max) + padding) / float(step)) * float(step)
    y_axis_range = y_max_axis - y_min_axis or 1

    final_stock_coords = []
    mutual_finstock_coords = []

    n_points = len(points) or 1

    for index, point in enumerate(points):
        x_norm = (index + 0.5) / n_points

        final_value = float(point["final_stock"])
        plan_value = float(point["mutual_finstock"])

        final_stock_coords.append({
            "x": round(x_norm, 4),
            "y": round((final_value - y_min_axis) / y_axis_range, 4),
            "value": final_value,
        })

        mutual_finstock_coords.append({
            "x": round(x_norm, 4),
            "y": round((plan_value - y_min_axis) / y_axis_range, 4),
            "value": plan_value,
        })

    y_ticks = []
    tick = y_min_axis

    while tick <= y_max_axis:
        y_ticks.append({
            "value": float(tick),
            "pos": round((tick - y_min_axis) / y_axis_range, 4),
            "label": format_currency(tick),
        })

        tick += float(step)

    x_labels = [
        {
            "pos": round((index + 0.5) / n_points, 4),
            "label": point["key"],
        }
        for index, point in enumerate(points)
    ]

    return {
        "title": "Динамика стоимости остатков, руб",
        "x_labels": x_labels,
        "y_axis": {
            "min": float(y_min_axis),
            "max": float(y_max_axis),
            "ticks": y_ticks,
        },
        "final_stock": final_stock_coords,
        "mutual_finstock": mutual_finstock_coords,
    }


def group_turnover_monthly(rows):
    month_last_dates = {}

    for row in rows:
        d = row.get("date_end")

        if not d:
            continue

        month = d.strftime("%Y-%m")

        if month not in month_last_dates or d > month_last_dates[month]:
            month_last_dates[month] = d

    monthly_groups = {}

    for row in rows:
        d = row.get("date_end")

        if not d:
            continue

        month = d.strftime("%Y-%m")
        last_date = month_last_dates.get(month)

        if not last_date or d != last_date:
            continue

        key = (
            month,
            row.get("nomenclature") or "",
            row.get("warehouse_group") or "",
            row.get("warehouse") or "",
            row.get("quantity") or "",
        )

        if key not in monthly_groups:
            monthly_groups[key] = {
                "month_year": last_date.strftime("%Y-%m-%d"),
                "nomenclature": row.get("nomenclature") or "",
                "warehouse_group": row.get("warehouse_group") or "",
                "warehouse": row.get("warehouse") or "",
                "quantity": row.get("quantity") or "",
                "middle_stock": Decimal("0"),
                "middle_rubstock": Decimal("0"),
                "last_date": last_date.strftime("%Y-%m-%d"),
            }

        monthly_groups[key]["middle_stock"] += to_decimal(row.get("middle_stock"))
        monthly_groups[key]["middle_rubstock"] += to_decimal(row.get("middle_rubstock"))

    grouped_list = list(monthly_groups.values())

    grouped_list.sort(
        key=lambda x: (
            datetime.strptime(x["month_year"], "%Y-%m-%d"),
            float(x["middle_rubstock"] or 0),
            float(x["middle_stock"] or 0),
        ),
        reverse=True,
    )

    return grouped_list


def build_turnover_tree(turnover_list):
    getcontext().prec = 28

    grouped = defaultdict(
        lambda: defaultdict(
            lambda: defaultdict(
                lambda: defaultdict(list)
            )
        )
    )

    for row in turnover_list:
        month = row["month_year"]
        nomenclature = row.get("nomenclature") or ""
        warehouse_group = row.get("warehouse_group") or ""
        warehouse = row.get("warehouse") or ""

        grouped[month][nomenclature][warehouse_group][warehouse].append(row)

    result = []

    for month, nomenclatures in grouped.items():
        month_middle_stock = Decimal("0")
        month_middle_rubstock = Decimal("0")
        nomenclature_nodes = []

        for nomenclature, warehouse_groups in nomenclatures.items():
            nomenclature_middle_stock = Decimal("0")
            nomenclature_middle_rubstock = Decimal("0")
            warehouse_group_nodes = []

            for warehouse_group, warehouses in warehouse_groups.items():
                warehouse_group_middle_stock = Decimal("0")
                warehouse_group_middle_rubstock = Decimal("0")

                warehouse_names = set()
                quantities = set()

                warehouse_group_node = {
                    "month_year": month,
                    "partner": nomenclature,
                    "contract_partner": warehouse_group,
                    "manager_name": "",
                    "quantity": "",
                    "mutual_finstock": Decimal("0"),
                    "final_stock": Decimal("0"),
                    "children": [],
                }

                for warehouse, rows in warehouses.items():
                    warehouse_middle_stock = sum(
                        to_decimal(r.get("middle_stock")) for r in rows
                    )
                    warehouse_middle_rubstock = sum(
                        to_decimal(r.get("middle_rubstock")) for r in rows
                    )

                    warehouse_group_middle_stock += warehouse_middle_stock
                    warehouse_group_middle_rubstock += warehouse_middle_rubstock

                    warehouse_names.add(warehouse)

                    warehouse_quantities = {
                        str(r.get("quantity") or "")
                        for r in rows
                        if r.get("quantity")
                    }

                    quantities.update(warehouse_quantities)

                    warehouse_node = {
                        "month_year": month,
                        "partner": nomenclature,
                        "contract_partner": warehouse_group,
                        "manager_name": warehouse,
                        "quantity": ", ".join(sorted(warehouse_quantities)) if warehouse_quantities else "—",
                        "mutual_finstock": warehouse_middle_stock,
                        "final_stock": warehouse_middle_rubstock,
                        "children": [
                            serialize_row(child)
                            for child in rows
                        ],
                    }

                    warehouse_group_node["children"].append(
                        serialize_row(warehouse_node)
                    )

                warehouse_group_node["manager_name"] = (
                    ", ".join(sorted(warehouse_names))
                    if warehouse_names
                    else "—"
                )
                warehouse_group_node["quantity"] = (
                    ", ".join(sorted(quantities))
                    if quantities
                    else "—"
                )
                warehouse_group_node["mutual_finstock"] = warehouse_group_middle_stock
                warehouse_group_node["final_stock"] = warehouse_group_middle_rubstock

                warehouse_group_nodes.append(
                    serialize_row(warehouse_group_node)
                )

                nomenclature_middle_stock += warehouse_group_middle_stock
                nomenclature_middle_rubstock += warehouse_group_middle_rubstock

            warehouse_group_nodes.sort(
                key=lambda x: (
                    float(x.get("final_stock") or 0),
                    float(x.get("mutual_finstock") or 0),
                ),
                reverse=True,
            )

            nomenclature_node = {
                "month_year": month,
                "partner": nomenclature,
                "mutual_finstock": nomenclature_middle_stock,
                "final_stock": nomenclature_middle_rubstock,
                "children": warehouse_group_nodes,
            }

            nomenclature_nodes.append(
                serialize_row(nomenclature_node)
            )

            month_middle_stock += nomenclature_middle_stock
            month_middle_rubstock += nomenclature_middle_rubstock

        nomenclature_nodes.sort(
            key=lambda x: (
                float(x.get("final_stock") or 0),
                float(x.get("mutual_finstock") or 0),
                x.get("partner") or "",
            ),
            reverse=True,
        )

        month_node = {
            "month_year": month,
            "mutual_finstock": month_middle_stock,
            "final_stock": month_middle_rubstock,
            "children": nomenclature_nodes,
        }

        result.append(
            serialize_row(month_node)
        )

    result.sort(key=lambda x: x["month_year"], reverse=True)

    return result


def build_turnover_indicators(chart_data):
    if (
        not chart_data
        or not chart_data.get("final_stock")
        or not chart_data.get("mutual_finstock")
    ):
        return {
            "quantity": 0,
            "cost": 0,
            "indicator": 0,
            "deviation": 0,
            "deviation_color": "",
        }

    last_final_stock = Decimal(str(chart_data["final_stock"][-1]["value"]))
    last_mutual_finstock = Decimal(str(chart_data["mutual_finstock"][-1]["value"]))

    deviation = last_final_stock - last_mutual_finstock

    return {
        "quantity": 0,
        "cost": to_float(last_final_stock),
        "indicator": to_float(last_mutual_finstock),
        "deviation": to_float(deviation),
        "deviation_color": "red" if deviation > 0 else "",
    }


def prepare_fb_turnover_dashboard(rows, indicator_rows, filters=None):
    filters = get_default_turnover_filters(filters)

    filter_values = build_filter_values(rows)

    chart = build_turnover_chart_data(
        rows=rows,
        indicator_rows=indicator_rows,
        date_start=filters["date_start"],
        date_end=filters["date_end"],
    )

    indicators = build_turnover_indicators(chart)

    turnover_list = group_turnover_monthly(rows)
    turnover_tree = build_turnover_tree(turnover_list)

    return {
        "filters": filters,
        "filter_values": filter_values,
        "indicators": indicators,
        "chart": chart,
        "turnover_tree": turnover_tree,
        "total_rows": len(rows),
    }