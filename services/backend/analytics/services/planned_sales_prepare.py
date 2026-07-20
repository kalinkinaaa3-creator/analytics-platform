from collections import defaultdict
from datetime import date, datetime
from calendar import monthrange


def to_float(value):
    try:
        return float(value) if value not in (None, "") else 0.0
    except Exception:
        return 0.0


def get_color(v):
    if v >= 99:
        return "green"
    elif v >= 80:
        return "orange"
    return "red"


def normalize_rows(rows):
    result = []

    for row in rows:
        item = dict(row)

        if isinstance(item.get("date"), str):
            item["date"] = datetime.strptime(item["date"], "%Y-%m-%d").date()

        item["projection"] = item.get("projection_s")

        result.append(item)

    return result


def sum_raw_data(rows, period):
    def s(field):
        return sum(to_float(r.get(field)) for r in rows)

    if period == "month":
        return {
            "plan": s("plan"),
            "fact": s("fact"),
            "appg": s("appg"),
            "appg_slice": s("appg_slice"),
            "projection": s("projection"),
        }

    if period == "quarter":
        return {
            "plan": s("plan_quarter"),
            "fact": s("fact_quarter"),
            "appg": s("year_SPLY_quarter"),
            "appg_slice": s("yoy_SPLY_quarter"),
            "projection": s("projection_quarter"),
        }

    if period == "year":
        return {
            "plan": s("plan_year"),
            "fact": s("fact_year"),
            "appg": s("year_SPLY_year"),
            "appg_slice": s("yoy_SPLY_year"),
            "projection": s("projection_year"),
        }

    return {}


def calc_metrics(base):
    base["fact_vs_plan"] = round(base["fact"] - base["plan"], 0)
    base["vs_plan_pct"] = round((base["fact"] / base["plan"] * 100) if base["plan"] else 0, 0)
    base["plan_vs_SPLY"] = round((base["plan"] / base["appg"] * 100) if base["appg"] else 0, 0)
    base["fact_vs_SPLY"] = round((base["fact"] / base["appg"] * 100) if base["appg"] else 0, 0)
    base["yoy"] = round((base["fact"] / base["appg_slice"] * 100) if base["appg_slice"] else 0, 0)

    base["proj_vs_plan_1"] = round((base["projection"] / base["plan"] * 100) if base["plan"] else 0, 0)
    base["proj_vs_plan_2"] = round(base["projection"] - base["plan"], 0)
    base["proj_vs_SPLY"] = round((base["projection"] / base["appg"] * 100) if base["appg"] else 0, 0)

    return base


PERCENT_FIELDS = [
    "vs_plan_pct",
    "plan_vs_SPLY",
    "fact_vs_SPLY",
    "yoy",
    "proj_vs_plan_1",
    "proj_vs_SPLY",
    "vs_plan_pct_quarter",
    "plan_vs_SPLY_quarter",
    "fact_vs_SPLY_quarter",
    "yoy_quarter",
    "proj_vs_plan_q1",
    "proj_vs_SPLY_quarter",
    "vs_plan_pct_year",
    "plan_vs_SPLY_year",
    "fact_vs_SPLY_year",
    "yoy_year",
    "proj_vs_plan_y1",
    "proj_vs_SPLY_year",
]


def add_colors(row):
    for field in PERCENT_FIELDS:
        row[f"{field}_color"] = get_color(row.get(field, 0))
    return row




def build_planned_sales_tree(rows):
    rows = normalize_rows(rows)

    if not rows:
        return []

    max_date = max(r["date"] for r in rows if r.get("date"))

    def get_quarter(dt):
        return (dt.month - 1) // 3 + 1

    last_year = max_date.year
    last_month = max_date.month
    last_quarter = get_quarter(max_date)

    def is_last_month(row):
        d = row.get("date")
        return d and d.year == last_year and d.month == last_month

    def is_quarter(row):
        d = row.get("date")
        return (
            d
            and d.year == last_year
            and get_quarter(d) == last_quarter
            and d <= max_date
        )

    def is_year(row):
        d = row.get("date")
        return d and d.year == last_year and d <= max_date

    def sum_rows(source_rows):
        return {
            "plan": round(sum(to_float(r.get("plan")) for r in source_rows), 0),
            "fact": round(sum(to_float(r.get("fact")) for r in source_rows), 0),
            "appg": round(sum(to_float(r.get("appg")) for r in source_rows), 0),
            "appg_slice": round(sum(to_float(r.get("appg_slice")) for r in source_rows), 0),
            "projection": round(sum(to_float(r.get("projection")) for r in source_rows), 0),
        }

    tree = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

    for row in rows:
        level1 = row.get("level1") or ""
        level2 = row.get("level2") or ""
        level3 = row.get("level3") or ""

        tree[level1][level2][level3].append(row)

    result = []

    for level1, level2_dict in tree.items():
        level1_detail_rows = []

        for level2, level3_dict in level2_dict.items():
            level2_detail_rows = []
            level2_block = []

            has_level3 = any(
                level3 not in ("", "-")
                for level3 in level3_dict.keys()
            )

            for level3, group_rows in level3_dict.items():
                month = calc_metrics(sum_rows([r for r in group_rows if is_last_month(r)]))
                quarter = calc_metrics(sum_rows([r for r in group_rows if is_quarter(r)]))
                year = calc_metrics(sum_rows([r for r in group_rows if is_year(r)]))

                detail_row = {
                    "date": max_date.strftime("%Y-%m-01"),
                    "id_directory": group_rows[0].get("id_directory"),
                    "level1": level1,
                    "level2": level2,
                    "level3": level3,

                    **month,

                    "plan_quarter": quarter["plan"],
                    "fact_quarter": quarter["fact"],
                    "fact_vs_plan_quarter": quarter["fact_vs_plan"],
                    "vs_plan_pct_quarter": quarter["vs_plan_pct"],
                    "year_SPLY_quarter": quarter["appg"],
                    "yoy_SPLY_quarter": quarter["appg_slice"],
                    "yoy_quarter": quarter["yoy"],
                    "plan_vs_SPLY_quarter": quarter["plan_vs_SPLY"],
                    "fact_vs_SPLY_quarter": quarter["fact_vs_SPLY"],
                    "projection_quarter": quarter["projection"],
                    "proj_vs_plan_q1": quarter["proj_vs_plan_1"],
                    "proj_vs_plan_q2": quarter["proj_vs_plan_2"],
                    "proj_vs_SPLY_quarter": quarter["proj_vs_SPLY"],

                    "plan_year": year["plan"],
                    "fact_year": year["fact"],
                    "fact_vs_plan_year": year["fact_vs_plan"],
                    "vs_plan_pct_year": year["vs_plan_pct"],
                    "year_SPLY_year": year["appg"],
                    "yoy_SPLY_year": year["appg_slice"],
                    "yoy_year": year["yoy"],
                    "plan_vs_SPLY_year": year["plan_vs_SPLY"],
                    "fact_vs_SPLY_year": year["fact_vs_SPLY"],
                    "projection_year": year["projection"],
                    "proj_vs_plan_y1": year["proj_vs_plan_1"],
                    "proj_vs_plan_y2": year["proj_vs_plan_2"],
                    "proj_vs_SPLY_year": year["proj_vs_SPLY"],

                    "is_summary": False,
                    "level": 3 if level3 and level3 != "-" else 2,
                }

                detail_row = add_colors(detail_row)

                level2_block.append(detail_row)
                level2_detail_rows.append(detail_row)

            if has_level3 and level2_detail_rows:
                level2_total_month = calc_metrics(sum_raw_data(level2_detail_rows, "month"))
                level2_total_quarter = calc_metrics(sum_raw_data(level2_detail_rows, "quarter"))
                level2_total_year = calc_metrics(sum_raw_data(level2_detail_rows, "year"))

                level2_total = {
                    "date": max_date.strftime("%Y-%m-01"),
                    "id_directory": None,
                    "level1": level1,
                    "level2": level2,
                    "level3": "ИТОГО",

                    **level2_total_month,

                    "plan_quarter": level2_total_quarter["plan"],
                    "fact_quarter": level2_total_quarter["fact"],
                    "fact_vs_plan_quarter": level2_total_quarter["fact_vs_plan"],
                    "vs_plan_pct_quarter": level2_total_quarter["vs_plan_pct"],
                    "year_SPLY_quarter": level2_total_quarter["appg"],
                    "yoy_SPLY_quarter": level2_total_quarter["appg_slice"],
                    "yoy_quarter": level2_total_quarter["yoy"],
                    "plan_vs_SPLY_quarter": level2_total_quarter["plan_vs_SPLY"],
                    "fact_vs_SPLY_quarter": level2_total_quarter["fact_vs_SPLY"],
                    "projection_quarter": level2_total_quarter["projection"],
                    "proj_vs_plan_q1": level2_total_quarter["proj_vs_plan_1"],
                    "proj_vs_plan_q2": level2_total_quarter["proj_vs_plan_2"],
                    "proj_vs_SPLY_quarter": level2_total_quarter["proj_vs_SPLY"],

                    "plan_year": level2_total_year["plan"],
                    "fact_year": level2_total_year["fact"],
                    "fact_vs_plan_year": level2_total_year["fact_vs_plan"],
                    "vs_plan_pct_year": level2_total_year["vs_plan_pct"],
                    "year_SPLY_year": level2_total_year["appg"],
                    "yoy_SPLY_year": level2_total_year["appg_slice"],
                    "yoy_year": level2_total_year["yoy"],
                    "plan_vs_SPLY_year": level2_total_year["plan_vs_SPLY"],
                    "fact_vs_SPLY_year": level2_total_year["fact_vs_SPLY"],
                    "projection_year": level2_total_year["projection"],
                    "proj_vs_plan_y1": level2_total_year["proj_vs_plan_1"],
                    "proj_vs_plan_y2": level2_total_year["proj_vs_plan_2"],
                    "proj_vs_SPLY_year": level2_total_year["proj_vs_SPLY"],

                    "is_summary": True,
                    "level": 2,
                }

                level2_block.insert(0, add_colors(level2_total))

            result.extend(level2_block)
            level1_detail_rows.extend(level2_detail_rows)

        if level1_detail_rows:
            level1_total_month = calc_metrics(sum_raw_data(level1_detail_rows, "month"))
            level1_total_quarter = calc_metrics(sum_raw_data(level1_detail_rows, "quarter"))
            level1_total_year = calc_metrics(sum_raw_data(level1_detail_rows, "year"))

            level1_total = {
                "date": max_date.strftime("%Y-%m-01"),
                "id_directory": None,
                "level1": level1,
                "level2": "ИТОГО",
                "level3": "",

                **level1_total_month,

                "plan_quarter": level1_total_quarter["plan"],
                "fact_quarter": level1_total_quarter["fact"],
                "fact_vs_plan_quarter": level1_total_quarter["fact_vs_plan"],
                "vs_plan_pct_quarter": level1_total_quarter["vs_plan_pct"],
                "year_SPLY_quarter": level1_total_quarter["appg"],
                "yoy_SPLY_quarter": level1_total_quarter["appg_slice"],
                "yoy_quarter": level1_total_quarter["yoy"],
                "plan_vs_SPLY_quarter": level1_total_quarter["plan_vs_SPLY"],
                "fact_vs_SPLY_quarter": level1_total_quarter["fact_vs_SPLY"],
                "projection_quarter": level1_total_quarter["projection"],
                "proj_vs_plan_q1": level1_total_quarter["proj_vs_plan_1"],
                "proj_vs_plan_q2": level1_total_quarter["proj_vs_plan_2"],
                "proj_vs_SPLY_quarter": level1_total_quarter["proj_vs_SPLY"],

                "plan_year": level1_total_year["plan"],
                "fact_year": level1_total_year["fact"],
                "fact_vs_plan_year": level1_total_year["fact_vs_plan"],
                "vs_plan_pct_year": level1_total_year["vs_plan_pct"],
                "year_SPLY_year": level1_total_year["appg"],
                "yoy_SPLY_year": level1_total_year["appg_slice"],
                "yoy_year": level1_total_year["yoy"],
                "plan_vs_SPLY_year": level1_total_year["plan_vs_SPLY"],
                "fact_vs_SPLY_year": level1_total_year["fact_vs_SPLY"],
                "projection_year": level1_total_year["projection"],
                "proj_vs_plan_y1": level1_total_year["proj_vs_plan_1"],
                "proj_vs_plan_y2": level1_total_year["proj_vs_plan_2"],
                "proj_vs_SPLY_year": level1_total_year["proj_vs_SPLY"],

                "is_summary": True,
                "level": 1,
            }

            result.append(add_colors(level1_total))

    all_detail_rows = [
        row
        for row in result
        if not row.get("is_summary", False)
    ]

    if all_detail_rows:
        grand_month = calc_metrics(sum_raw_data(all_detail_rows, "month"))
        grand_quarter = calc_metrics(sum_raw_data(all_detail_rows, "quarter"))
        grand_year = calc_metrics(sum_raw_data(all_detail_rows, "year"))

        grand_total = {
            "date": max_date.strftime("%Y-%m-01"),
            "id_directory": None,
            "level1": "ВСЕГО",
            "level2": "",
            "level3": "",

            **grand_month,

            "plan_quarter": grand_quarter["plan"],
            "fact_quarter": grand_quarter["fact"],
            "fact_vs_plan_quarter": grand_quarter["fact_vs_plan"],
            "vs_plan_pct_quarter": grand_quarter["vs_plan_pct"],
            "year_SPLY_quarter": grand_quarter["appg"],
            "yoy_SPLY_quarter": grand_quarter["appg_slice"],
            "yoy_quarter": grand_quarter["yoy"],
            "plan_vs_SPLY_quarter": grand_quarter["plan_vs_SPLY"],
            "fact_vs_SPLY_quarter": grand_quarter["fact_vs_SPLY"],
            "projection_quarter": grand_quarter["projection"],
            "proj_vs_plan_q1": grand_quarter["proj_vs_plan_1"],
            "proj_vs_plan_q2": grand_quarter["proj_vs_plan_2"],
            "proj_vs_SPLY_quarter": grand_quarter["proj_vs_SPLY"],

            "plan_year": grand_year["plan"],
            "fact_year": grand_year["fact"],
            "fact_vs_plan_year": grand_year["fact_vs_plan"],
            "vs_plan_pct_year": grand_year["vs_plan_pct"],
            "year_SPLY_year": grand_year["appg"],
            "yoy_SPLY_year": grand_year["appg_slice"],
            "yoy_year": grand_year["yoy"],
            "plan_vs_SPLY_year": grand_year["plan_vs_SPLY"],
            "fact_vs_SPLY_year": grand_year["fact_vs_SPLY"],
            "projection_year": grand_year["projection"],
            "proj_vs_plan_y1": grand_year["proj_vs_plan_1"],
            "proj_vs_plan_y2": grand_year["proj_vs_plan_2"],
            "proj_vs_SPLY_year": grand_year["proj_vs_SPLY"],

            "is_summary": True,
            "is_grand": True,
            "level": 0,
        }

        result.append(add_colors(grand_total))

    return result






def get_period_labels(date_range):
    if not date_range:
        return {
            "month": "Месяц",
            "quarter": "Квартал",
            "year": "Год",
        }

    max_date = max(
        datetime.strptime(item, "%Y-%m-01")
        for item in date_range
    )

    month_names = [
        "Январь",
        "Февраль",
        "Март",
        "Апрель",
        "Май",
        "Июнь",
        "Июль",
        "Август",
        "Сентябрь",
        "Октябрь",
        "Ноябрь",
        "Декабрь",
    ]

    quarter = (max_date.month - 1) // 3 + 1

    return {
        "month": month_names[max_date.month - 1],
        "quarter": str(quarter),
        "year": str(max_date.year),
    }


def get_performance_indicators(sales_tree, period_labels, selected_date_str):
    grand_total = next(
        (row for row in sales_tree if row.get("is_grand")),
        None,
    )

    if not grand_total:
        return {
            "month": {"time_passed": 0},
            "quarter": {"time_passed": 0},
            "year": {"time_passed": 0},
        }

    if selected_date_str:
        selected_date = datetime.strptime(
            selected_date_str,
            "%Y-%m-01",
        ).date()
    else:
        selected_date = date.today().replace(day=1)

    today = date.today()

    def time_passed_pct(period_start, period_end):
        total_days = (period_end - period_start).days + 1
        passed_days = min((today - period_start).days + 1, total_days)

        if total_days <= 0:
            return 0

        return max(0, round((passed_days / total_days) * 100, 0))

    def safe_pct(value, default=0):
        try:
            return int(round(value if value is not None else default))
        except Exception:
            return int(default)

    def safe_div(numerator, denominator):
        try:
            numerator = to_float(numerator)
            denominator = to_float(denominator)

            if denominator == 0:
                return 0

            return int(round((numerator / denominator) * 100))
        except Exception:
            return 0

    month_days = monthrange(selected_date.year, selected_date.month)[1]
    month_start = selected_date
    month_end = date(selected_date.year, selected_date.month, month_days)

    quarter_month = selected_date.month - 1
    quarter_start_month = (quarter_month // 3) * 3 + 1
    quarter_start = date(selected_date.year, quarter_start_month, 1)

    quarter_end_month = min(quarter_start_month + 2, 12)
    quarter_end = date(
        selected_date.year,
        quarter_end_month,
        monthrange(selected_date.year, quarter_end_month)[1],
    )

    year_start = date(selected_date.year, 1, 1)
    year_end = date(selected_date.year, 12, 31)

    return {
        "month": {
            "label": period_labels["month"],
            "time_passed": time_passed_pct(month_start, month_end),
            "vs_plan": safe_pct(grand_total.get("vs_plan_pct")),
            "vs_sply": safe_pct(grand_total.get("fact_vs_SPLY")),
            "proj_plan": safe_pct(grand_total.get("proj_vs_plan_1")),
            "fact_proj": safe_div(
                grand_total.get("fact"),
                grand_total.get("projection"),
            ),
            "proj_vs_sply": safe_pct(grand_total.get("proj_vs_SPLY")),
            "vs_plan_color": grand_total.get("vs_plan_pct_color"),
            "vs_sply_color": grand_total.get("fact_vs_SPLY_color"),
            "proj_plan_color": grand_total.get("proj_vs_plan_1_color"),
            "fact_proj_color": grand_total.get("proj_vs_plan_1_color"),
            "proj_vs_sply_color": grand_total.get("proj_vs_SPLY_color"),
        },
        "quarter": {
            "label": period_labels["quarter"],
            "time_passed": time_passed_pct(quarter_start, quarter_end),
            "vs_plan": safe_pct(grand_total.get("vs_plan_pct_quarter")),
            "vs_sply": safe_pct(grand_total.get("fact_vs_SPLY_quarter")),
            "proj_plan": safe_pct(grand_total.get("proj_vs_plan_q1")),
            "fact_proj": safe_div(
                grand_total.get("fact_quarter"),
                grand_total.get("projection_quarter"),
            ),
            "proj_vs_sply": safe_pct(grand_total.get("proj_vs_SPLY_quarter")),
            "vs_plan_color": grand_total.get("vs_plan_pct_quarter_color"),
            "vs_sply_color": grand_total.get("fact_vs_SPLY_quarter_color"),
            "proj_plan_color": grand_total.get("proj_vs_plan_q1_color"),
            "fact_proj_color": grand_total.get("proj_vs_plan_q1_color"),
            "proj_vs_sply_color": grand_total.get("proj_vs_SPLY_quarter_color"),
        },
        "year": {
            "label": period_labels["year"],
            "time_passed": time_passed_pct(year_start, year_end),
            "vs_plan": safe_pct(grand_total.get("vs_plan_pct_year")),
            "vs_sply": safe_pct(grand_total.get("fact_vs_SPLY_year")),
            "proj_plan": safe_pct(grand_total.get("proj_vs_plan_y1")),
            "fact_proj": safe_div(
                grand_total.get("fact_year"),
                grand_total.get("projection_year"),
            ),
            "proj_vs_sply": safe_pct(grand_total.get("proj_vs_SPLY_year")),
            "vs_plan_color": grand_total.get("vs_plan_pct_year_color"),
            "vs_sply_color": grand_total.get("fact_vs_SPLY_year_color"),
            "proj_plan_color": grand_total.get("proj_vs_plan_y1_color"),
            "fact_proj_color": grand_total.get("proj_vs_plan_y1_color"),
            "proj_vs_sply_color": grand_total.get("proj_vs_SPLY_year_color"),
        },
    }


def aggregate_level2_month(rows):
    rows = normalize_rows(rows)

    agg = defaultdict(
        lambda: {
            "fact": 0.0,
            "appg": 0.0,
            "plan": 0.0,
        }
    )

    for row in rows:
        if row.get("level1") != "-":
            continue

        row_date = row.get("date")
        level2 = row.get("level2")

        if not row_date or not level2:
            continue

        if not isinstance(row_date, str):
            row_date = row_date.strftime("%Y-%m-01")

        key = (row_date, level2)

        agg[key]["fact"] += to_float(row.get("fact"))
        agg[key]["appg"] += to_float(row.get("appg"))
        agg[key]["plan"] += to_float(row.get("plan"))

    result = []

    for (row_date, level2), values in agg.items():
        result.append({
            "date": row_date,
            "level2": level2,
            "fact": values["fact"],
            "appg": values["appg"],
            "plan": values["plan"],
        })

    result.sort(key=lambda item: (item["date"], item["level2"]))

    return result


def build_date_range(selected_date_str):
    if selected_date_str:
        selected = datetime.strptime(selected_date_str, "%Y-%m-01")
    else:
        selected = datetime.now()

    current = datetime(selected.year, 1, 1)
    result = []

    while current <= selected:
        result.append(current.strftime("%Y-%m-01"))

        if current.month == 12:
            current = datetime(current.year + 1, 1, 1)
        else:
            current = datetime(current.year, current.month + 1, 1)

    return result




def prepare_planned_sales_dashboard(
    rows,
    filters=None,
    available_dates=None,
    last_update=None,
):
    filters = filters or {}

    selected_date = filters.get("date_end") or filters.get("date")

    date_range = build_date_range(selected_date)

    period_labels = get_period_labels(date_range)

    date_set = set(date_range)

    filtered_rows = []
    for row in rows:
        row_date = row.get("date")

        if hasattr(row_date, "strftime"):
            row_date = row_date.strftime("%Y-%m-01")
        else:
            row_date = str(row_date)[:7] + "-01"

        if row_date in date_set:
            filtered_rows.append(row)

    sales_tree = build_planned_sales_tree(filtered_rows)

    indicators = get_performance_indicators(
        sales_tree,
        period_labels,
        selected_date,
    )

    level2_month_agg = aggregate_level2_month(filtered_rows)

    return {
        "filters": {
            "date": selected_date or "",
        },
        "filter_values": {
            "date": available_dates or [],
        },
        "last_update": last_update.strftime("%Y-%m-%d %H:%M") if last_update else None,
        "period_labels": period_labels,
        "indicators": indicators,
        "level2_month_agg": level2_month_agg,
        "sales_tree": sales_tree,
        "total_rows": len(sales_tree),
    }