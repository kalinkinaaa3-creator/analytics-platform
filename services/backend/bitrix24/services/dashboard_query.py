from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any


GROUP_EXPRESSIONS = {
    "day": "toDate(source_created_at)",
    "week": "toStartOfWeek(source_created_at, 1)",
    "month": "toStartOfMonth(source_created_at)",
    "year": "toStartOfYear(source_created_at)",
}
UNTRACKED_DEPARTMENT_NAME = "Неотслеживаемые"


def previous_year(value: date) -> date:
    try:
        return value.replace(year=value.year - 1)
    except ValueError:
        return value.replace(year=value.year - 1, day=28)


def iso_date_in_year(value: date, iso_year: int) -> date:
    """Return the same ISO week/weekday in another ISO year.

    ISO week 53 does not exist every year. In that case the last ISO week of
    the target year is the closest unambiguous comparison period.
    """
    iso = value.isocalendar()
    last_week = date(iso_year, 12, 28).isocalendar().week
    return date.fromisocalendar(iso_year, min(iso.week, last_week), iso.weekday)


def previous_comparison_date(value: date, group_by: str) -> date:
    if group_by == "week":
        return iso_date_in_year(value, value.isocalendar().year - 1)
    return previous_year(value)


def next_comparison_period(value: date, group_by: str) -> date:
    if group_by == "week":
        return iso_date_in_year(value, value.isocalendar().year + 1)
    try:
        return value.replace(year=value.year + 1)
    except ValueError:
        return value.replace(year=value.year + 1, day=28)


def previous_group_period(value: date, group_by: str) -> date:
    if group_by == "day":
        return value - timedelta(days=1)
    if group_by == "week":
        return value - timedelta(days=7)
    if group_by == "month":
        return value.replace(
            year=value.year - 1 if value.month == 1 else value.year,
            month=12 if value.month == 1 else value.month - 1,
            day=1,
        )
    return value.replace(year=value.year - 1, month=1, day=1)


def group_period_start(value: date, group_by: str) -> date:
    if group_by == "day":
        return value
    if group_by == "week":
        return value - timedelta(days=value.weekday())
    if group_by == "month":
        return value.replace(day=1)
    return value.replace(month=1, day=1)


def percent_change(current, previous):
    if previous in (None, 0):
        return None
    return (float(current) - float(previous)) / float(previous) * 100


@dataclass(frozen=True)
class LeadDashboardFilters:
    date_start: date
    date_end: date
    department_names: tuple[str, ...] = field(default_factory=tuple)
    manager_ids: tuple[int, ...] = field(default_factory=tuple)
    source_ids: tuple[str, ...] = field(default_factory=tuple)
    project_ids: tuple[str, ...] = field(default_factory=tuple)
    semantic_status_ids: tuple[str, ...] = field(default_factory=tuple)
    status_ids: tuple[str, ...] = field(default_factory=tuple)
    exclude_untracked_department: bool = True
    group_by: str = "month"

    def __post_init__(self):
        if self.date_end < self.date_start:
            raise ValueError("date_end must not be earlier than date_start.")
        if self.group_by not in GROUP_EXPRESSIONS:
            raise ValueError(f"Unsupported group_by: {self.group_by}.")


class LeadDashboardQuery:
    def __init__(self, client=None):
        if client is None:
            from analytics.clickhouse.client import get_clickhouse_client

            client = get_clickhouse_client()
        self.client = client

    @staticmethod
    def _where(filters: LeadDashboardFilters) -> tuple[str, dict[str, Any]]:
        conditions = [
            "source_created_at >= %(date_start)s",
            "source_created_at < %(date_end_exclusive)s",
        ]
        params: dict[str, Any] = {
            "date_start": filters.date_start,
            "date_end_exclusive": filters.date_end + timedelta(days=1),
        }
        for field_name, values in (
            ("department_name", filters.department_names),
            ("manager_id", filters.manager_ids),
            ("source_id", filters.source_ids),
            ("project_id", filters.project_ids),
            ("status_semantic_id", filters.semantic_status_ids),
            ("status_id", filters.status_ids),
        ):
            if values:
                parameter = f"filter_{field_name}"
                conditions.append(f"{field_name} IN %({parameter})s")
                params[parameter] = tuple(values)
        if filters.exclude_untracked_department:
            conditions.append("department_name != %(untracked_department_name)s")
            params["untracked_department_name"] = UNTRACKED_DEPARTMENT_NAME
        return " AND ".join(conditions), params

    def _dict_rows(self, sql: str, params: dict[str, Any]) -> list[dict]:
        rows, columns = self.client.execute(
            sql,
            params,
            with_column_types=True,
        )
        names = [column[0] for column in columns]
        return [dict(zip(names, row)) for row in rows]

    def cards(self, filters: LeadDashboardFilters) -> dict:
        where, params = self._where(filters)
        rows = self._dict_rows(
            f"""
            SELECT
                count() AS total,
                countIf(is_apm = 0) AS total_excluding_apm,
                countIf(dashboard_status = 'target') AS target,
                countIf(is_apm = 1) AS apm,
                countIf(dashboard_status = 'in_progress') AS in_progress,
                countIf(is_low_quality = 1 AND is_apm = 0) AS low_quality,
                countIf(is_return_customer = 1) AS return_customers,
                countIf(is_unmapped = 1) AS unmapped,
                countIf(is_processed = 1) AS processed,
                countIf(dashboard_status = 'unprocessed') AS unprocessed,
                if(
                    countIf(dashboard_status IN ('target', 'low_quality')) = 0,
                    NULL,
                    countIf(dashboard_status = 'target') * 100.0 /
                    countIf(dashboard_status IN ('target', 'low_quality'))
                ) AS conversion
            FROM default.bitrix_lead_analytics
            WHERE {where}
            """,
            params,
        )
        return rows[0] if rows else {
            "total": 0,
            "total_excluding_apm": 0,
            "target": 0,
            "apm": 0,
            "in_progress": 0,
            "low_quality": 0,
            "return_customers": 0,
            "unmapped": 0,
            "processed": 0,
            "unprocessed": 0,
            "conversion": None,
        }

    def build(self, filters: LeadDashboardFilters) -> dict:
        comparison_filters = LeadDashboardFilters(
            date_start=previous_comparison_date(filters.date_start, filters.group_by),
            date_end=previous_comparison_date(filters.date_end, filters.group_by),
            department_names=filters.department_names,
            manager_ids=filters.manager_ids,
            source_ids=filters.source_ids,
            project_ids=filters.project_ids,
            semantic_status_ids=filters.semantic_status_ids,
            status_ids=filters.status_ids,
            exclude_untracked_department=filters.exclude_untracked_department,
            group_by=filters.group_by,
        )
        current = {
            "stages": self.dimension_dynamics(filters, "dashboard_status"),
            "sources": self.dimension_dynamics(filters, "source"),
            "managers": self.dimension_dynamics(filters, "manager"),
            "low_quality": self.dimension_dynamics(filters, "low_quality_status"),
        }
        current_period_start = group_period_start(
            filters.date_start,
            filters.group_by,
        )
        prior_period_filters = LeadDashboardFilters(
            date_start=previous_group_period(
                current_period_start,
                filters.group_by,
            ),
            date_end=current_period_start - timedelta(days=1),
            department_names=filters.department_names,
            manager_ids=filters.manager_ids,
            source_ids=filters.source_ids,
            project_ids=filters.project_ids,
            semantic_status_ids=filters.semantic_status_ids,
            status_ids=filters.status_ids,
            exclude_untracked_department=filters.exclude_untracked_department,
            group_by=filters.group_by,
        )
        prior = {
            "stages": self.dimension_dynamics(prior_period_filters, "dashboard_status"),
            "sources": self.dimension_dynamics(prior_period_filters, "source"),
            "managers": self.dimension_dynamics(prior_period_filters, "manager"),
            "low_quality": self.dimension_dynamics(
                prior_period_filters,
                "low_quality_status",
            ),
        }
        previous = {
            "stages": self.dimension_dynamics(comparison_filters, "dashboard_status"),
            "sources": self.dimension_dynamics(comparison_filters, "source"),
            "managers": self.dimension_dynamics(comparison_filters, "manager"),
            "low_quality": self.dimension_dynamics(comparison_filters, "low_quality_status"),
        }
        summaries = {
            key: self._summarize_dimensions(current[key], previous[key])
            for key in current
        }
        dynamics = {
            key: self._enrich_dynamics(
                current[key],
                previous[key],
                filters.group_by,
                prior[key],
            )
            for key in current
        }
        return {
            "cards": self.cards(filters),
            "dynamics": dynamics,
            "summaries": summaries,
            "comparison_period": {
                "date_start": comparison_filters.date_start,
                "date_end": comparison_filters.date_end,
            },
        }

    DIMENSIONS = {
        "dashboard_status": ("dashboard_status", "dashboard_status", "1", "1"),
        "source": ("source_id", "if(source_name = '', source_id, source_name)", "1", "1"),
        "manager": (
            "ifNull(toString(manager_id), '__unassigned__')",
            "if(manager_id IS NULL, 'Менеджер не назначен', "
            "if(manager_name = '', toString(manager_id), manager_name))",
            "1",
            "1",
        ),
        "low_quality_status": (
            "status_id",
            "if(status_name = '', status_id, status_name)",
            "is_low_quality = 1 AND is_apm = 0",
            "is_low_quality = 1 AND is_apm = 0",
        ),
    }

    def dimension_dynamics(self, filters: LeadDashboardFilters, dimension: str) -> list[dict]:
        (
            key_expression,
            name_expression,
            extra_condition,
            total_condition,
        ) = self.DIMENSIONS[dimension]
        where, params = self._where(filters)
        period = GROUP_EXPRESSIONS[filters.group_by]
        return self._dict_rows(
            f"""
            WITH grouped AS (
                SELECT
                    {period} AS period,
                    {key_expression} AS dimension_key,
                    {name_expression} AS dimension_name,
                    count() AS value,
                    countIf(is_return_customer = 1) AS return_customer_value,
                    countIf(dashboard_status = 'target') AS dimension_target,
                    countIf(dashboard_status = 'low_quality') AS dimension_low_quality
                FROM default.bitrix_lead_analytics
                WHERE {where} AND ({extra_condition})
                GROUP BY period, dimension_key, dimension_name
            ), totals AS (
                SELECT {period} AS period,
                    countIf({total_condition}) AS total
                FROM default.bitrix_lead_analytics
                WHERE {where}
                GROUP BY period
            )
            SELECT grouped.period, toString(grouped.dimension_key) AS dimension_key,
                grouped.dimension_name, grouped.value,
                grouped.return_customer_value,
                grouped.dimension_target,
                grouped.dimension_low_quality,
                totals.total,
                if(totals.total = 0, NULL, grouped.value * 100.0 / totals.total) AS share,
                if(grouped.dimension_target + grouped.dimension_low_quality = 0, NULL,
                   grouped.dimension_target * 100.0 /
                   (grouped.dimension_target + grouped.dimension_low_quality)) AS conversion
            FROM grouped INNER JOIN totals USING period
            ORDER BY period, dimension_name, dimension_key
            """,
            params,
        )

    @staticmethod
    def _summarize_dimensions(
        current: list[dict],
        previous: list[dict],
    ) -> list[dict]:
        def aggregate(rows):
            result = {}
            for row in rows:
                key = str(row["dimension_key"])
                item = result.setdefault(
                    key,
                    {
                        "dimension_key": key,
                        "dimension_name": row["dimension_name"],
                        "value": 0,
                        "return_customer_value": 0,
                        "dimension_target": 0,
                        "dimension_low_quality": 0,
                    },
                )
                item["value"] += int(row.get("value") or 0)
                item["return_customer_value"] += int(
                    row.get("return_customer_value") or 0
                )
                item["dimension_target"] += int(row.get("dimension_target") or 0)
                item["dimension_low_quality"] += int(
                    row.get("dimension_low_quality") or 0
                )
            return result

        current_by_key = aggregate(current)
        previous_by_key = aggregate(previous)
        current_total = sum(item["value"] for item in current_by_key.values())
        previous_total = sum(item["value"] for item in previous_by_key.values())
        result = []
        for key in current_by_key.keys() | previous_by_key.keys():
            previous_item = previous_by_key.get(key, {})
            item = current_by_key.get(
                key,
                {
                    "dimension_key": key,
                    "dimension_name": previous_item.get("dimension_name", key),
                    "value": 0,
                    "return_customer_value": 0,
                    "dimension_target": 0,
                    "dimension_low_quality": 0,
                },
            )
            result.append(
                {
                    **item,
                    "period": "__range__",
                    "total": current_total,
                    "previous_year_value": previous_item.get("value", 0),
                    "previous_year_total": previous_total,
                    "previous_year_dimension_target": previous_item.get(
                        "dimension_target", 0
                    ),
                    "previous_year_dimension_low_quality": previous_item.get(
                        "dimension_low_quality", 0
                    ),
                }
            )
        return sorted(
            result,
            key=lambda item: (-item["value"], item["dimension_name"], item["dimension_key"]),
        )

    @staticmethod
    def _enrich_dynamics(
        current: list[dict],
        previous_year_rows: list[dict],
        group_by: str = "month",
        previous_period_rows: list[dict] | None = None,
    ) -> list[dict]:
        previous_lookup = {
            (row["period"], str(row["dimension_key"])): row
            for row in previous_year_rows
        }
        previous_year_totals: dict[date, int] = {}
        for previous_total_row in previous_year_rows:
            previous_year_totals[previous_total_row["period"]] = (
                previous_year_totals.get(previous_total_row["period"], 0)
                + int(previous_total_row["value"] or 0)
            )
        current_lookup = {
            (row["period"], str(row["dimension_key"])): row["value"]
            for row in [*(previous_period_rows or []), *current]
        }
        period_totals: dict[date, int] = {}
        for total_row in [*(previous_period_rows or []), *current]:
            period_totals[total_row["period"]] = (
                period_totals.get(total_row["period"], 0)
                + int(total_row["value"] or 0)
            )
        current_rows = {
            (row["period"], str(row["dimension_key"])): row
            for row in current
        }
        # A dimension that existed only in the analogous period must still be
        # present on the chart as a zero current value (a visible fall to zero).
        # Mapping the previous rows forward also restores a completely empty
        # current bucket when its analogous period contained data.
        row_keys = set(current_rows)
        for previous_row in previous_year_rows:
            current_period = group_period_start(
                next_comparison_period(previous_row["period"], group_by),
                group_by,
            )
            row_keys.add((current_period, str(previous_row["dimension_key"])))

        result = []
        for period, dimension_key in row_keys:
            previous_year_period = group_period_start(
                previous_comparison_date(period, group_by),
                group_by,
            )
            previous_row = previous_lookup.get(
                (previous_year_period, dimension_key),
                {},
            )
            row = current_rows.get((period, dimension_key))
            if row is None:
                row = {
                    "period": period,
                    "dimension_key": dimension_key,
                    "dimension_name": previous_row.get("dimension_name", dimension_key),
                    "value": 0,
                    "return_customer_value": 0,
                    "dimension_target": 0,
                    "dimension_low_quality": 0,
                    "total": period_totals.get(period, 0),
                    "share": 0,
                    "conversion": None,
                }
            year_value = previous_row.get("value", 0)
            prior_period = previous_group_period(period, group_by)
            period_value = current_lookup.get(
                (prior_period, dimension_key),
                0,
            )
            item = dict(row)
            item["previous_year_value"] = year_value
            item["previous_year_total"] = previous_year_totals.get(
                previous_year_period,
                0,
            )
            item["previous_year_return_customer_value"] = previous_row.get(
                "return_customer_value",
                0,
            )
            item["previous_year_dimension_target"] = previous_row.get(
                "dimension_target",
                0,
            )
            item["previous_year_dimension_low_quality"] = previous_row.get(
                "dimension_low_quality",
                0,
            )
            item["year_change_percent"] = percent_change(row["value"], year_value)
            item["previous_period_value"] = period_value
            item["previous_period_total"] = period_totals.get(prior_period, 0)
            item["period_change_percent"] = percent_change(row["value"], period_value)
            item["period_total_change_percent"] = percent_change(
                period_totals.get(period, 0),
                period_totals.get(prior_period, 0),
            )
            result.append(item)
        return sorted(result, key=lambda item: (item["period"], item["dimension_name"], item["dimension_key"]))
