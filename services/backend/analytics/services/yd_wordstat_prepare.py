from datetime import datetime
from itertools import groupby
from statistics import median, mean


MONTH_FIELDS = [
    "month_1", "month_2", "month_3", "month_4",
    "month_5", "month_6", "month_7", "month_8",
    "month_9", "month_10", "month_11", "month_12",
]

MONTHS_FIELDS = [
    "monthS_1", "monthS_2", "monthS_3", "monthS_4",
    "monthS_5", "monthS_6", "monthS_7", "monthS_8",
    "monthS_9", "monthS_10", "monthS_11", "monthS_12",
]

DEVICE_FIELDS = [
    "desktop",
    "phone",
    "tablet",
    "other_device",
]

REGION_FIELDS = [
    "ekb_macroregion",
    "kras_macroregion",
    "mos_macroregion",
    "nign_macroregion",
    "novos_macroregion",
    "spb_macroregion",
    "sng_macroregion",
    "other_macroregion",
]

QUARTER_FIELDS = [
    "quarter1",
    "quarter2",
    "quarter3",
    "quarter4",
]


def get_default_wordstat_filters(filters: dict | None = None) -> dict:
    filters = filters or {}

    return {
        "feature": filters.get("feature", []),
        "category": filters.get("category", []),
        "phrase": filters.get("phrase", []),
    }


def normalize_filter_list(value):
    if not value:
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, tuple):
        return list(value)

    return [value]


def normalize_wordstat_filters(filters: dict | None = None) -> dict:
    filters = get_default_wordstat_filters(filters)

    return {
        "feature": normalize_filter_list(filters.get("feature")),
        "category": normalize_filter_list(filters.get("category")),
        "phrase": normalize_filter_list(filters.get("phrase")),
    }


def format_wordstat_values(wordstat_list: list[dict]) -> list[dict]:
    thousand_sep_cols = [
        *MONTH_FIELDS,
        "total",
        "average",
        *DEVICE_FIELDS,
        *REGION_FIELDS,
    ]

    float_cols = [
        "growth",
        *MONTHS_FIELDS,
        *QUARTER_FIELDS,
    ]

    for obj in wordstat_list:
        for col in thousand_sep_cols:
            value = obj.get(col)

            if value is not None and value != "":
                try:
                    obj[col] = "{:,}".format(int(value)).replace(",", " ")
                except (ValueError, TypeError):
                    pass

        for col in float_cols:
            value = obj.get(col)

            if value is not None and value != "":
                obj[col] = str(value).replace(".", ",")

    return wordstat_list


def interp_color(value, min_value, max_value, median_value):
    if value <= median_value:
        ratio = (value - min_value) / (median_value - min_value or 1)
        color = [
            round(248 + (255 - 248) * ratio),
            round(105 + (235 - 105) * ratio),
            round(107 + (132 - 107) * ratio),
        ]
    else:
        ratio = (value - median_value) / (max_value - median_value or 1)
        color = [
            round(255 + (99 - 255) * ratio),
            round(235 + (190 - 235) * ratio),
            round(132 + (123 - 132) * ratio),
        ]

    return f"rgb({color[0]},{color[1]},{color[2]})"


def get_month_colors(wordstat_list: list[dict]) -> list[dict]:
    current_year = datetime.now().year
    current_month = datetime.now().month

    wordstat_list_sorted = sorted(
        wordstat_list,
        key=lambda row: row.get("phrase") or "",
    )

    for phrase, rows in groupby(
        wordstat_list_sorted,
        key=lambda row: row.get("phrase") or "",
    ):
        rows = list(rows)

        months_pool = []

        for row in rows:
            year = row.get("year")
            months = [row.get(f"month_{i}") or 0 for i in range(1, 13)]

            if year == current_year:
                months_pool.extend(months[:current_month - 1])
            else:
                months_pool.extend(months)

        if months_pool:
            min_value = min(months_pool)
            max_value = max(months_pool)
            median_value = median(months_pool)
        else:
            min_value = max_value = median_value = 0

        for row in rows:
            year = row.get("year")
            months = [row.get(f"month_{i}") or 0 for i in range(1, 13)]
            month_colors = []

            for i in range(1, 13):
                if year == current_year and i >= current_month:
                    month_colors.append("")
                else:
                    month_colors.append(
                        interp_color(
                            months[i - 1],
                            min_value,
                            max_value,
                            median_value,
                        )
                    )

            row["month_colors"] = month_colors

        months_s_pool = []

        for row in rows:
            year = row.get("year")
            months_s = [
                float(row.get(f"monthS_{i}") or 0)
                for i in range(1, 13)
            ]

            if year == current_year:
                months_s_pool.extend(months_s[:current_month - 1])
            else:
                months_s_pool.extend(months_s)

        if months_s_pool:
            min_value = min(months_s_pool)
            max_value = max(months_s_pool)
            median_value = median(months_s_pool)
        else:
            min_value = max_value = median_value = 0

        for row in rows:
            year = row.get("year")
            months_s = [
                float(row.get(f"monthS_{i}") or 0)
                for i in range(1, 13)
            ]

            month_s_colors = []

            for i in range(1, 13):
                if year == current_year and i >= current_month:
                    month_s_colors.append("")
                else:
                    month_s_colors.append(
                        interp_color(
                            months_s[i - 1],
                            min_value,
                            max_value,
                            median_value,
                        )
                    )

            row["monthS_colors"] = month_s_colors

        quarters_pool = []

        for row in rows:
            year = row.get("year")
            quarters = [
                float(row.get(field) or 0)
                for field in QUARTER_FIELDS
            ]

            if year == current_year:
                current_quarter = (current_month - 1) // 3
                quarters_pool.extend(quarters[:current_quarter])
            else:
                quarters_pool.extend(quarters)

        if quarters_pool:
            min_value = min(quarters_pool)
            max_value = max(quarters_pool)
            median_value = median(quarters_pool)
        else:
            min_value = max_value = median_value = 0

        for row in rows:
            year = row.get("year")
            quarters = [
                float(row.get(field) or 0)
                for field in QUARTER_FIELDS
            ]

            quarter_colors = []

            for i in range(4):
                if year == current_year:
                    current_quarter = (current_month - 1) // 3
                    if i >= current_quarter:
                        quarter_colors.append("")
                        continue

                quarter_colors.append(
                    interp_color(
                        quarters[i],
                        min_value,
                        max_value,
                        median_value,
                    )
                )

            row["quarter_colors"] = quarter_colors

        growth_pool = [
            float(row.get("growth") or 0)
            for row in rows[1:]
        ]

        if growth_pool:
            min_growth = min(growth_pool)
            max_growth = max(growth_pool)
            median_growth = median(growth_pool)
        else:
            min_growth = max_growth = median_growth = 0

        for index, row in enumerate(rows):
            if index == 0:
                row["growth_color"] = ""
            else:
                value = float(row.get("growth") or 0)
                row["growth_color"] = interp_color(
                    value,
                    min_growth,
                    max_growth,
                    median_growth,
                )

        devices_pool = []

        for row in rows:
            devices_pool.extend([
                float(row.get(field) or 0)
                for field in DEVICE_FIELDS
            ])

        if devices_pool:
            min_value = min(devices_pool)
            max_value = max(devices_pool)
            median_value = median(devices_pool)
        else:
            min_value = max_value = median_value = 0

        for row in rows:
            row["device_colors"] = {
                field: interp_color(
                    float(row.get(field) or 0),
                    min_value,
                    max_value,
                    median_value,
                )
                for field in DEVICE_FIELDS
            }

        regions_pool = []

        for row in rows:
            regions_pool.extend([
                float(row.get(field) or 0)
                for field in REGION_FIELDS
            ])

        if regions_pool:
            min_value = min(regions_pool)
            max_value = max(regions_pool)
            median_value = median(regions_pool)
        else:
            min_value = max_value = median_value = 0

        for row in rows:
            row["region_colors"] = {
                field: interp_color(
                    float(row.get(field) or 0),
                    min_value,
                    max_value,
                    median_value,
                )
                for field in REGION_FIELDS
            }

    return wordstat_list


def get_wordstat_summary(wordstat_list: list[dict]) -> list[dict]:
    summary_rows = []
    years = sorted({
        item.get("year")
        for item in wordstat_list
        if item.get("year") is not None
    })

    first = True

    for year in years:
        rows_for_year = [
            row
            for row in wordstat_list
            if row.get("year") == year
        ]

        if not rows_for_year:
            continue

        summary = {
            "phrase": "СВОД",
            "show_phrase": first,
            "year": year,
            "total": sum(row.get("total") or 0 for row in rows_for_year),
            "average": 0,
            "growth": 0,
            "growth_color": "#fff",
            "is_summary": True,
        }

        for field in MONTH_FIELDS:
            summary[field] = sum(row.get(field) or 0 for row in rows_for_year)

        for field in DEVICE_FIELDS:
            summary[field] = sum(row.get(field) or 0 for row in rows_for_year)

        for field in REGION_FIELDS:
            summary[field] = sum(row.get(field) or 0 for row in rows_for_year)

        for field in MONTHS_FIELDS:
            summary[field] = round(
                sum(row.get(field) or 0 for row in rows_for_year)
                / len(rows_for_year),
                2,
            )

        month_values = [
            summary[field]
            for field in MONTH_FIELDS
        ]

        current_month = datetime.now().month

        if year == datetime.now().year:
            last_month = current_month - 1 if current_month > 1 else 12
        else:
            last_month = 12

        relevant_values = month_values[:last_month]

        summary["average"] = (
            round(sum(relevant_values) / len(relevant_values))
            if relevant_values
            else 0
        )

        summary_rows.append(summary)

        first = False

    for i in range(1, len(summary_rows)):
        previous_average = summary_rows[i - 1]["average"]
        current_average = summary_rows[i]["average"]

        summary_rows[i]["growth"] = (
            round(
                (current_average - previous_average)
                / previous_average
                * 100,
                2,
            )
            if previous_average
            else 0
        )

        summary_rows[i]["growth_color"] = (
            "#afa"
            if summary_rows[i]["growth"] >= 0
            else "#faa"
        )

    return summary_rows


def add_quarters(wordstat_list: list[dict]) -> list[dict]:
    for row in wordstat_list:
        q1 = sum(row.get(f"monthS_{i}") or 0 for i in range(1, 4))
        q2 = sum(row.get(f"monthS_{i}") or 0 for i in range(4, 7))
        q3 = sum(row.get(f"monthS_{i}") or 0 for i in range(7, 10))
        q4 = sum(row.get(f"monthS_{i}") or 0 for i in range(10, 13))

        row["quarter1"] = round((q1 / 12) * 100, 2)
        row["quarter2"] = round((q2 / 12) * 100, 2)
        row["quarter3"] = round((q3 / 12) * 100, 2)
        row["quarter4"] = round((q4 / 12) * 100, 2)

    return wordstat_list


def add_monthS_colors_for_avg_row(avg_row: dict) -> dict:
    months_s = [
        float(avg_row.get(f"monthS_{i}") or 0)
        for i in range(1, 13)
    ]

    if months_s:
        min_value = min(months_s)
        max_value = max(months_s)
        median_value = median(months_s)
    else:
        min_value = max_value = median_value = 0

    avg_row["monthS_colors"] = [
        interp_color(value, min_value, max_value, median_value)
        for value in months_s
    ]

    return avg_row


def build_summary_extra_rows(summary_rows: list[dict]) -> list[dict]:
    current_year = datetime.now().year

    rows = [
        row
        for row in summary_rows
        if row.get("year") != current_year
    ]

    if not rows:
        return []

    avg_row = {
        "phrase": "Усредненный коэффициент (без текущего года)",
        "show_phrase": True,
        "year": "—",
        "is_summary": False,
    }

    for key in rows[0].keys():
        if (
            key.startswith("month_")
            or key in (
                "total",
                "average",
                "growth",
                *DEVICE_FIELDS,
                *REGION_FIELDS,
                *QUARTER_FIELDS,
            )
        ):
            avg_row[key] = ""

    for i in range(1, 13):
        values = [
            float(row.get(f"monthS_{i}") or 0)
            for row in rows
        ]

        avg_row[f"monthS_{i}"] = (
            round(mean(values), 2)
            if values
            else 0
        )

    avg_row = add_monthS_colors_for_avg_row(avg_row)

    qsum_row = {
        "phrase": "Сумма квартала (без текущего года)",
        "show_phrase": True,
        "year": "—",
        "is_summary": False,
        "monthS_2": 0,
        "monthS_5": 0,
        "monthS_8": 0,
        "monthS_11": 0,
    }

    q1 = avg_row["monthS_1"] + avg_row["monthS_2"] + avg_row["monthS_3"]
    q2 = avg_row["monthS_4"] + avg_row["monthS_5"] + avg_row["monthS_6"]
    q3 = avg_row["monthS_7"] + avg_row["monthS_8"] + avg_row["monthS_9"]
    q4 = avg_row["monthS_10"] + avg_row["monthS_11"] + avg_row["monthS_12"]

    qsum_row["monthS_2"] = round(q1, 2)
    qsum_row["monthS_5"] = round(q2, 2)
    qsum_row["monthS_8"] = round(q3, 2)
    qsum_row["monthS_11"] = round(q4, 2)

    qshare_row = {
        "phrase": "Доля квартала от года, % (без текущего года)",
        "show_phrase": True,
        "year": "—",
        "is_summary": False,
        "monthS_2": f"{round((qsum_row['monthS_2'] / 12) * 100, 2)}%",
        "monthS_5": f"{round((qsum_row['monthS_5'] / 12) * 100, 2)}%",
        "monthS_8": f"{round((qsum_row['monthS_8'] / 12) * 100, 2)}%",
        "monthS_11": f"{round((qsum_row['monthS_11'] / 12) * 100, 2)}%",
    }

    return [
        avg_row,
        qsum_row,
        qshare_row,
    ]


def add_percentage_fields(
    wordstat_list: list[dict],
    percentage_fields: list[str] | None = None,
    condition_func=None,
) -> list[dict]:
    if percentage_fields is None:
        percentage_fields = [
            *QUARTER_FIELDS,
            "growth",
        ]

    if condition_func is None:
        condition_func = lambda row: True

    for row in wordstat_list:
        if condition_func(row):
            for field in percentage_fields:
                value = row.get(field)

                if value is not None and value != "":
                    row[field] = f"{value}%"

    return wordstat_list


def add_show_phrase(wordstat_list: list[dict]) -> list[dict]:
    grouped_list = []

    wordstat_list = sorted(
        wordstat_list,
        key=lambda row: (
            row.get("category") or "",
            row.get("feature") or "",
            row.get("phrase") or "",
            row.get("year") or 0,
        ),
    )

    for phrase, items in groupby(
        wordstat_list,
        key=lambda row: row.get("phrase"),
    ):
        items_list = list(items)

        for index, item in enumerate(items_list):
            item["show_phrase"] = index == 0
            item["is_summary"] = False
            grouped_list.append(item)

    return grouped_list


def build_filter_values(rows: list[dict]) -> dict:
    return {
        "feature": sorted({
            row.get("feature")
            for row in rows
            if row.get("feature")
        }),
        "category": sorted({
            row.get("category")
            for row in rows
            if row.get("category")
        }),
        "phrase": sorted({
            row.get("phrase")
            for row in rows
            if row.get("phrase")
        }),
    }


def paginate_rows(rows: list[dict], page: int, page_size: int) -> dict:
    total_rows = len(rows)

    start = (page - 1) * page_size
    end = start + page_size

    page_rows = rows[start:end]

    has_next = end < total_rows
    next_page = page + 1 if has_next else None

    return {
        "rows": page_rows,
        "page": page,
        "page_size": page_size,
        "total_rows": total_rows,
        "has_next": has_next,
        "next_page": next_page,
    }


def prepare_yd_wordstat_table(
    rows: list[dict],
    filters: dict | None = None,
    page: int = 1,
    page_size: int = 100,
) -> dict:
    filters = normalize_wordstat_filters(filters)

    filter_values = build_filter_values(rows)

    for row in rows:
        if row.get("average") is not None:
            row["average"] = round(row["average"])

    rows = add_show_phrase(rows)

    summary_rows = get_wordstat_summary(rows)

    rows = add_quarters(rows)
    summary_rows = add_quarters(summary_rows)

    summary_extra_rows = build_summary_extra_rows(summary_rows)

    rows = get_month_colors(rows)
    summary_rows = get_month_colors(summary_rows)

    rows = add_percentage_fields(rows)
    summary_rows = add_percentage_fields(summary_rows)

    rows = format_wordstat_values(rows)
    summary_rows = format_wordstat_values(summary_rows)
    summary_extra_rows = format_wordstat_values(summary_extra_rows)

    pagination = paginate_rows(
        rows,
        page=page,
        page_size=page_size,
    )

    if page == 1:
        combined_rows = (
            summary_rows
            + summary_extra_rows
            + pagination["rows"]
        )
    else:
        combined_rows = pagination["rows"]

    return {
        "rows": combined_rows,
        "detail_rows": rows,
        "summary_rows": summary_rows,
        "summary_extra_rows": summary_extra_rows,
        "filters": filters,
        "filter_values": filter_values,
        "pagination": {
            "page": pagination["page"],
            "page_size": pagination["page_size"],
            "total_rows": pagination["total_rows"],
            "has_next": pagination["has_next"],
            "next_page": pagination["next_page"],
        },
    }