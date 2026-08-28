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


def get_default_accreceiv_filters(filters=None):
    filters = filters or {}

    yesterday = datetime.now().date() - timedelta(days=1)

    return {
        "partner": normalize_filter_list(filters.get("partner")),
        "contract_partner": normalize_filter_list(filters.get("contract_partner")),
        "manager_name": normalize_filter_list(filters.get("manager_name")),
        "date_start": filters.get("date_start") or f"{yesterday.year}-01-01",
        "date_end": filters.get("date_end") or yesterday.isoformat(),
    }


def build_filter_values(rows):
    return {
        "partner": sorted({
            row.get("partner")
            for row in rows
            if row.get("partner")
        }),
        "contract_partner": sorted({
            row.get("contract_partner")
            for row in rows
            if row.get("contract_partner")
        }),
        "manager_name": sorted({
            row.get("manager_name")
            for row in rows
            if row.get("manager_name")
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


def build_accreceiv_chart_data(rows, date_start, date_end):
    if not rows:
        return None

    date_start_dt = datetime.strptime(date_start, "%Y-%m-%d").date()
    date_end_dt = datetime.strptime(date_end, "%Y-%m-%d").date()

    delta_days = (date_end_dt - date_start_dt).days
    same_month = (
        date_start_dt.year == date_end_dt.year
        and date_start_dt.month == date_end_dt.month
    )

    group_by_day = same_month or (
        date_start_dt.year == date_end_dt.year
        and delta_days < 30
    )

    grouped = defaultdict(lambda: {
        "final_stock_values": [],
        "mutual_finstock_values": [],
        "date_start_list": [],
    })

    for row in rows:
        d = row.get("date_start")

        if not d:
            continue

        key = (
            d.strftime("%Y-%m-%d")
            if group_by_day
            else d.strftime("%Y-%m")
        )

        grouped[key]["final_stock_values"].append(
            to_decimal(row.get("final_stock"))
        )
        grouped[key]["mutual_finstock_values"].append(
            to_decimal(row.get("mutual_finstock"))
        )
        grouped[key]["date_start_list"].append(d)

    points_data = {}

    for key, item in grouped.items():
        final_stocks = item["final_stock_values"]
        mutual_finstocks = item["mutual_finstock_values"]
        date_list = item["date_start_list"]

        if group_by_day:
            total_final_stock = sum(final_stocks)
            total_mutual_finstock = sum(mutual_finstocks)
        else:
            last_date_in_month = max(date_list)

            month_final_stocks = [
                value
                for value, dt in zip(final_stocks, date_list)
                if dt == last_date_in_month
            ]

            month_mutual_finstocks = [
                value
                for value, dt in zip(mutual_finstocks, date_list)
                if dt == last_date_in_month
            ]

            total_final_stock = (
                sum(month_final_stocks)
                if month_final_stocks
                else Decimal("0")
            )
            total_mutual_finstock = (
                sum(month_mutual_finstocks)
                if month_mutual_finstocks
                else Decimal("0")
            )

        points_data[key] = {
            "final_stock": total_final_stock,
            "mutual_finstock": total_mutual_finstock,
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
        for value in (
            point["final_stock"],
            point["mutual_finstock"],
        )
    ]

    if not all_values or all(value == 0 for value in all_values):
        return None

    y_min = min(all_values)
    y_max = max(all_values)
    y_range = y_max - y_min if y_max - y_min != 0 else Decimal("1")

    step = nice_step(float(y_range), num_ticks=5)

    y_min_axis = math.floor(float(y_min) / float(step)) * float(step)
    y_max_axis = math.ceil(float(y_max) / float(step)) * float(step)
    y_axis_range = y_max_axis - y_min_axis or 1

    final_stock_coords = []
    mutual_finstock_coords = []

    n_points = len(points) or 1

    for index, point in enumerate(points):
        x_norm = (index + 0.5) / n_points

        final_value = float(point["final_stock"])
        mutual_value = float(point["mutual_finstock"])

        final_stock_coords.append({
            "x": round(x_norm, 4),
            "y": round((final_value - y_min_axis) / y_axis_range, 4),
            "value": final_value,
        })

        mutual_finstock_coords.append({
            "x": round(x_norm, 4),
            "y": round((mutual_value - y_min_axis) / y_axis_range, 4),
            "value": mutual_value,
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
        "title": "Динамика ДЗ, руб",
        "x_labels": x_labels,
        "y_axis": {
            "min": float(y_min_axis),
            "max": float(y_max_axis),
            "ticks": y_ticks,
        },
        "final_stock": final_stock_coords,
        "mutual_finstock": mutual_finstock_coords,
    }


def group_accreceiv_monthly(rows):
    yesterday = datetime.now().date() - timedelta(days=1)

    month_last_dates = {}

    for row in rows:
        d = row.get("date_start")

        if not d:
            continue

        if d > yesterday:
            continue

        month = d.strftime("%Y-%m")

        if month not in month_last_dates or d > month_last_dates[month]:
            month_last_dates[month] = d

    monthly_groups = {}

    for row in rows:
        d = row.get("date_start")

        if not d:
            continue

        month = d.strftime("%Y-%m")

        if month not in month_last_dates:
            continue

        last_date = month_last_dates[month]

        if d != last_date:
            continue

        key = (
            month,
            row.get("partner") or "",
            row.get("contract_partner") or "",
            row.get("manager_name") or "",
        )

        if key not in monthly_groups:
            monthly_groups[key] = {
                "month_year": last_date.strftime("%Y-%m-%d"),
                "partner": row.get("partner") or "",
                "contract_partner": row.get("contract_partner") or "",
                "manager_name": row.get("manager_name") or "",
                "mutual_finstock": Decimal("0"),
                "final_stock": Decimal("0"),
                "last_date": last_date.strftime("%Y-%m-%d"),
            }

        monthly_groups[key]["mutual_finstock"] += to_decimal(
            row.get("mutual_finstock")
        )
        monthly_groups[key]["final_stock"] += to_decimal(
            row.get("final_stock")
        )

    result = list(monthly_groups.values())

    result.sort(
        key=lambda item: (
            datetime.strptime(item["month_year"], "%Y-%m-%d"),
            float(item["final_stock"] or 0),
            float(item["mutual_finstock"] or 0),
        ),
        reverse=True,
    )

    return result


def build_accreceiv_tree(accreceiv_list):
    getcontext().prec = 28

    grouped = defaultdict(
        lambda: defaultdict(
            lambda: defaultdict(
                lambda: defaultdict(list)
            )
        )
    )

    for row in accreceiv_list:
        month = row["month_year"]
        partner = row.get("partner") or ""
        contract = row.get("contract_partner") or ""
        manager = row.get("manager_name") or ""

        grouped[month][partner][contract][manager].append(row)

    result = []

    for month, partners in grouped.items():
        month_mutual = Decimal("0")
        month_final = Decimal("0")

        partner_nodes = []

        for partner, contracts in partners.items():
            partner_mutual = Decimal("0")
            partner_final = Decimal("0")

            contract_nodes = []

            for contract, managers in contracts.items():
                contract_mutual = Decimal("0")
                contract_final = Decimal("0")
                contract_manager_names = []

                contract_node = {
                    "month_year": month,
                    "partner": partner,
                    "contract_partner": contract,
                    "mutual_finstock": Decimal("0"),
                    "final_stock": Decimal("0"),
                    "children": [],
                    "manager_name": "",
                }

                for manager, manager_rows in managers.items():
                    manager_mutual = sum(
                        to_decimal(row.get("mutual_finstock"))
                        for row in manager_rows
                    )
                    manager_final = sum(
                        to_decimal(row.get("final_stock"))
                        for row in manager_rows
                    )

                    contract_mutual += manager_mutual
                    contract_final += manager_final

                    manager_node = {
                        "month_year": month,
                        "partner": partner,
                        "contract_partner": contract,
                        "manager_name": manager,
                        "mutual_finstock": manager_mutual,
                        "final_stock": manager_final,
                        "children": [
                            serialize_row(child)
                            for child in manager_rows
                        ],
                    }

                    contract_node["children"].append(
                        serialize_row(manager_node)
                    )

                    if manager:
                        contract_manager_names.append(manager)

                contract_node["manager_name"] = (
                    ", ".join(contract_manager_names)
                    if contract_manager_names
                    else "—"
                )
                contract_node["mutual_finstock"] = contract_mutual
                contract_node["final_stock"] = contract_final

                contract_nodes.append(
                    serialize_row(contract_node)
                )

                partner_mutual += contract_mutual
                partner_final += contract_final

            contract_nodes.sort(
                key=lambda item: (
                    float(item.get("final_stock") or 0),
                    float(item.get("mutual_finstock") or 0),
                ),
                reverse=True,
            )

            partner_node = {
                "month_year": month,
                "partner": partner,
                "mutual_finstock": partner_mutual,
                "final_stock": partner_final,
                "children": contract_nodes,
            }

            partner_nodes.append(
                serialize_row(partner_node)
            )

            month_mutual += partner_mutual
            month_final += partner_final

        partner_nodes.sort(
            key=lambda item: (
                float(item.get("final_stock") or 0),
                float(item.get("mutual_finstock") or 0),
                item.get("partner") or "",
            ),
            reverse=True,
        )

        month_node = {
            "month_year": month,
            "mutual_finstock": month_mutual,
            "final_stock": month_final,
            "children": partner_nodes,
        }

        result.append(
            serialize_row(month_node)
        )

    result.sort(key=lambda item: item["month_year"], reverse=True)

    return result


def build_accreceiv_indicators(chart_data):
    if (
        not chart_data
        or not chart_data.get("final_stock")
        or not chart_data.get("mutual_finstock")
    ):
        return {
            "quantity": 0,
            "cost": 0,
        }

    last_final_stock = chart_data["final_stock"][-1]["value"]
    last_mutual_finstock = chart_data["mutual_finstock"][-1]["value"]

    return {
        "quantity": last_mutual_finstock,
        "cost": last_final_stock,
    }


def prepare_fb_accreceiv_dashboard(rows, indicator_rows=None, filters=None, filter_options=None):
    filters = get_default_accreceiv_filters(filters)

    filter_values = filter_options or build_filter_values(rows)

    chart = build_accreceiv_chart_data(
        rows=rows,
        date_start=filters["date_start"],
        date_end=filters["date_end"],
    )

    indicators = build_accreceiv_indicators(chart)

    accreceiv_list = group_accreceiv_monthly(rows)
    accreceiv_tree = build_accreceiv_tree(accreceiv_list)

    return {
        "filters": filters,
        "filter_values": filter_values,
        "indicators": indicators,
        "chart": chart,
        "accreceiv_tree": accreceiv_tree,
        "total_rows": len(rows),
    }
