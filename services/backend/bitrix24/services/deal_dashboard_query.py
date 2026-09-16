"""Aggregate deal reports in ClickHouse; fetch detailed records only on demand."""
from collections import defaultdict
from datetime import timedelta

from .dashboard_query import (
    GROUP_EXPRESSIONS, LeadDashboardQuery, group_period_start,
    previous_comparison_date, previous_group_period,
)
from .deal_metrics import RESULT_NAMES, ratio


PARTS = ("results", "sources", "managers", "loss-reasons")
SUM_FIELDS = ("total", "success", "lost", "in_progress", "unknown", "amount",
              "success_amount", "return_customers", "missing_history")
METRIC_SQL = """
    count() AS total,
    countIf(result = 'S') AS success,
    countIf(result = 'F') AS lost,
    countIf(result = 'P') AS in_progress,
    countIf(result = '?') AS unknown,
    sum(d.amount) AS amount,
    sumIf(d.amount, result = 'S') AS success_amount,
    countIf(is_return_customer = 1) AS return_customers,
    sum(history_missing) AS missing_history
"""
DIMENSIONS = {
    "results": ("result", "result_name"),
    "sources": (
        "if(source_id = '' OR source_name = '', '__missing_source__', source_id)",
        "if(source_id = '' OR source_name = '', 'Источник не указан', source_name)",
    ),
    "managers": ("if(assigned_by_id = 0, '__unassigned__', toString(assigned_by_id))", "manager_name"),
    "stages": ("stage_key", "concat(category_name, ' · ', stage_name)"),
    "loss-reasons": ("stage_key", "concat(category_name, ' · ', stage_name)"),
}
DETAIL_FIELDS = (
    "entity_id", "lead_id", "title", "is_return_customer", "deal_type_name",
    "manager_id", "manager_name", "department_name", "category_name", "stage_name",
    "source_name", "activity_name", "source_created_at", "speed_calculated_at",
    "amount", "processing_duration_days",
)
SORT_FIELDS = {
    **{key: key for key in DETAIL_FIELDS}, "deal_id": "entity_id",
}


def combined(rows):
    values = {key: sum(row[key] for row in rows) for key in SUM_FIELDS}
    values["conversion"] = ratio(values["success"], values["success"] + values["lost"])
    values["average_check"] = values["success_amount"] / values["success"] if values["success"] else None
    return values


def aggregate_panel(current, previous, prior, kind, group_by):
    def groups(rows):
        result = defaultdict(list)
        for row in rows:
            result[(row["dimension_key"], row["dimension_name"])].append(row)
        return result

    def dynamics(rows):
        totals = defaultdict(int)
        for row in rows:
            totals[row["period"]] += row["total"]
        return [{"period": row["period"], "dimension_key": row["dimension_key"],
                 "dimension_name": row["dimension_name"], "value": row["total"],
                 "total": totals[row["period"]], "return_customer_value": row["return_customers"],
                 "dimension_target": row["success"], "dimension_low_quality": row["lost"],
                 "share": ratio(row["total"], totals[row["period"]]),
                 "conversion": ratio(row["success"], row["success"] + row["lost"])} for row in rows]

    current_groups, previous_groups = groups(current), groups(previous)
    total, old_total = combined(current), combined(previous)
    summary = []
    for key, name in dict.fromkeys([*current_groups, *previous_groups]):
        rows, old_rows = current_groups.get((key, name), []), previous_groups.get((key, name), [])
        item, old = combined(rows), combined(old_rows)
        share, old_share = ratio(item["total"], total["total"]), ratio(old["total"], old_total["total"])
        summary.append({**item, "key": key, "name": name, "share": share,
                        "category_id": (rows or old_rows)[0]["category_id"],
                        "previous_success": old["success"], "previous_conversion": old["conversion"],
                        "delta_count": item["total"] - old["total"],
                        "delta_amount": item["amount"] - old["amount"],
                        "delta_share": share - old_share if share is not None and old_share is not None else None})
    if kind == "results":
        summary.sort(key=lambda row: list(RESULT_NAMES).index(row["key"]))
    else:
        summary.sort(key=lambda row: (-row["total"], row["name"]))
    return {
        "rows": LeadDashboardQuery._enrich_dynamics(dynamics(current), dynamics(previous), group_by, dynamics(prior)),
        "summary": summary,
        "total": {**total, "key": "", "name": "Итого", "share": 100 if total["total"] else None,
                  "previous_success": old_total["success"], "previous_conversion": old_total["conversion"],
                  "delta_count": total["total"] - old_total["total"],
                  "delta_amount": total["amount"] - old_total["amount"],
                  "delta_share": 0 if total["total"] and old_total["total"] else None},
    }


class DealDashboardQuery:
    def __init__(self, mart):
        self.mart = mart

    def execute(self, sql, args):
        rows, columns = self.mart.client.execute(sql, args, with_column_types=True)
        names = [column[0] for column in columns]
        return [dict(zip(names, row)) for row in rows]

    def where(self, filters):
        parts, args = self.mart.deal_conditions(filters)
        if self.mart.legacy:
            parts.append("entity_type = 'deal'")
        return parts, args

    def aggregates(self, filters, kind):
        parts, args = self.where(filters)
        if kind == "loss-reasons":
            parts.append("result = 'F'")
        key, name = DIMENSIONS[kind]
        period = GROUP_EXPRESSIONS[filters["group_by"]]
        rows = self.execute(f"""
            SELECT {period} AS period, {key} AS dimension_key, {name} AS dimension_name,
                   min(category_id) AS group_category_id, {METRIC_SQL}
            FROM {self.mart.table} AS d
            WHERE {' AND '.join(parts)}
            GROUP BY period, dimension_key, dimension_name
            ORDER BY period, dimension_name, dimension_key
        """, args)
        for row in rows:
            row["category_id"] = row.pop("group_category_id")
            row["dimension_key"] = str(row["dimension_key"])
            row["amount"] = float(row["amount"])
            row["success_amount"] = float(row["success_amount"])
        return rows

    def build(self, filters):
        previous = {**filters,
                    "date_start": previous_comparison_date(filters["date_start"], filters["group_by"]),
                    "date_end": previous_comparison_date(filters["date_end"], filters["group_by"])}
        start = group_period_start(filters["date_start"], filters["group_by"])
        prior = {**filters, "date_start": previous_group_period(start, filters["group_by"]),
                 "date_end": start - timedelta(days=1)}
        comparison = {"date_start": previous["date_start"], "date_end": previous["date_end"]}
        report = {"comparison_period": comparison}
        for kind in PARTS:
            current, old, prior_rows = [self.aggregates(scope, kind) for scope in (filters, previous, prior)]
            report[kind] = {**aggregate_panel(current, old, prior_rows, kind, filters["group_by"]),
                            "comparison_period": comparison}
            if kind == "results":
                report["cards"] = combined(current)
        return report

    def detail_where(self, filters):
        parts, args = self.where(filters)
        kind = filters.get("segment_type")
        keys = filters.get("segment_keys") or ([filters["segment_key"]] if filters.get("segment_key") else [])
        if kind == "loss-reasons":
            parts.append("result = 'F'")
        if kind in DIMENSIONS and keys:
            parts.append(f"({DIMENSIONS[kind][0]}) IN %(segment_keys)s")
            args["segment_keys"] = tuple(keys)
        if filters.get("period"):
            parts.append(f"{GROUP_EXPRESSIONS[filters['group_by']]} = %(period)s")
            args["period"] = filters["period"]
        return parts, args

    def detail_summary(self, filters):
        parts, args = self.detail_where(filters)
        row = self.execute(f"""
            SELECT count() AS total, sum(d.amount) AS amount,
                   countIf(is_return_customer = 1) AS return_customers,
                   avgOrNull(processing_duration_days) AS processing_duration_days
            FROM {self.mart.table} AS d WHERE {' AND '.join(parts)}
        """, args)[0]
        row["amount"] = float(row["amount"])
        return row

    def detail_rows(self, filters, *, limit=None, offset=0):
        parts, args = self.detail_where(filters)
        order = SORT_FIELDS[filters["sort_by"]]
        if order == "department_name" and "personal_departments" in filters:
            from .personal_departments import department_expression
            order = department_expression(filters["personal_departments"], args)
        elif order == "department_name" and "tracked_manager_ids" in filters:
            from .dashboard_query import UNTRACKED_DEPARTMENT_NAME
            order = "if(manager_id IN %(sort_tracked)s, department_name, %(sort_untracked)s)"
            args["sort_tracked"] = tuple(filters["tracked_manager_ids"]) or (-1,)
            args["sort_untracked"] = UNTRACKED_DEPARTMENT_NAME
        direction = "DESC" if filters["sort_direction"] == "desc" else "ASC"
        sql = f"""SELECT {', '.join(DETAIL_FIELDS)} FROM {self.mart.table} AS d
                  WHERE {' AND '.join(parts)}
                  ORDER BY {order} {direction} NULLS LAST, entity_id ASC"""
        if limit is not None:
            sql += " LIMIT %(limit)s OFFSET %(offset)s"
            args.update(limit=limit, offset=offset)
        rows = self.execute(sql, args)
        for row in rows:
            row["deal_id"] = row.pop("entity_id")
            row["amount"] = float(row["amount"])
            row["is_return_customer"] = None if row["is_return_customer"] is None else bool(row["is_return_customer"])
        return rows

    def export_rows(self, filters, *, batch_size=2000):
        offset = 0
        while True:
            rows = self.detail_rows(filters, limit=batch_size, offset=offset)
            self.mart.check()
            yield from rows
            if len(rows) < batch_size:
                break
            offset += batch_size
