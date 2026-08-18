from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any


GROUP_EXPRESSIONS = {
    "day": "toDate(source_created_at)",
    "week": "toStartOfWeek(source_created_at, 1)",
    "month": "toStartOfMonth(source_created_at)",
    "quarter": "toStartOfQuarter(source_created_at)",
    "year": "toStartOfYear(source_created_at)",
}


def previous_year(value: date) -> date:
    try:
        return value.replace(year=value.year - 1)
    except ValueError:
        return value.replace(year=value.year - 1, day=28)


def percent_change(current, previous):
    if previous in (None, 0):
        return None
    return (float(current) - float(previous)) / float(previous) * 100


@dataclass(frozen=True)
class LeadDashboardFilters:
    date_start: date
    date_end: date
    department_ids: tuple[int, ...] = field(default_factory=tuple)
    manager_ids: tuple[int, ...] = field(default_factory=tuple)
    source_ids: tuple[str, ...] = field(default_factory=tuple)
    status_ids: tuple[str, ...] = field(default_factory=tuple)
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
            ("primary_department_id", filters.department_ids),
            ("manager_id", filters.manager_ids),
            ("source_id", filters.source_ids),
            ("status_id", filters.status_ids),
        ):
            if values:
                parameter = f"filter_{field_name}"
                conditions.append(f"{field_name} IN %({parameter})s")
                params[parameter] = tuple(values)
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
                countIf(is_apm = 1) AS apm,
                countIf(is_low_quality = 1 AND is_apm = 0) AS low_quality,
                countIf(is_unmapped = 1) AS unmapped,
                countIf(is_processed = 1) AS processed,
                countIf(dashboard_status = 'unprocessed') AS unprocessed
            FROM default.bitrix_lead_analytics
            WHERE {where}
            """,
            params,
        )
        return rows[0] if rows else {
            "total": 0,
            "apm": 0,
            "low_quality": 0,
            "unmapped": 0,
            "processed": 0,
            "unprocessed": 0,
        }

    def lead_dynamics(self, filters: LeadDashboardFilters) -> list[dict]:
        where, params = self._where(filters)
        period = GROUP_EXPRESSIONS[filters.group_by]
        return self._dict_rows(
            f"""
            SELECT {period} AS period, count() AS value
            FROM default.bitrix_lead_analytics
            WHERE {where}
            GROUP BY period
            ORDER BY period
            """,
            params,
        )

    def status_dynamics(self, filters: LeadDashboardFilters) -> list[dict]:
        where, params = self._where(filters)
        period = GROUP_EXPRESSIONS[filters.group_by]
        return self._dict_rows(
            f"""
            SELECT
                {period} AS period,
                dashboard_status,
                count() AS value
            FROM default.bitrix_lead_analytics
            WHERE {where}
            GROUP BY period, dashboard_status
            ORDER BY period, dashboard_status
            """,
            params,
        )

    def low_quality_dynamics(self, filters: LeadDashboardFilters) -> list[dict]:
        where, params = self._where(filters)
        period = GROUP_EXPRESSIONS[filters.group_by]
        return self._dict_rows(
            f"""
            SELECT {period} AS period, count() AS value
            FROM default.bitrix_lead_analytics
            WHERE {where} AND is_low_quality = 1 AND is_apm = 0
            GROUP BY period
            ORDER BY period
            """,
            params,
        )

    def processing_speed(self, filters: LeadDashboardFilters) -> dict:
        where, params = self._where(filters)
        rows = self._dict_rows(
            f"""
            SELECT
                count() AS sample_size,
                avg(processing_duration_days) AS average_days,
                quantileExact(0.5)(processing_duration_days) AS median_days,
                quantileExact(0.75)(processing_duration_days) AS p75_days,
                quantileExact(0.9)(processing_duration_days) AS p90_days
            FROM default.bitrix_lead_analytics
            WHERE {where}
              AND processing_state = 'completed'
              AND processing_duration_days IS NOT NULL
            """,
            params,
        )
        return rows[0] if rows else {
            "sample_size": 0,
            "average_days": None,
            "median_days": None,
            "p75_days": None,
            "p90_days": None,
        }

    def build(self, filters: LeadDashboardFilters) -> dict:
        comparison_filters = LeadDashboardFilters(
            date_start=previous_year(filters.date_start),
            date_end=previous_year(filters.date_end),
            department_ids=filters.department_ids,
            manager_ids=filters.manager_ids,
            source_ids=filters.source_ids,
            status_ids=filters.status_ids,
            group_by=filters.group_by,
        )
        cards = self.cards(filters)
        comparison_cards = self.cards(comparison_filters)
        return {
            "cards": cards,
            "lead_dynamics": self.lead_dynamics(filters),
            "status_dynamics": self.status_dynamics(filters),
            "low_quality_dynamics": self.low_quality_dynamics(filters),
            "processing_speed": self.processing_speed(filters),
            "comparison": {
                "date_start": comparison_filters.date_start,
                "date_end": comparison_filters.date_end,
                "cards": comparison_cards,
                "lead_dynamics": self.lead_dynamics(comparison_filters),
                "low_quality_dynamics": self.low_quality_dynamics(
                    comparison_filters
                ),
                "total_change_percent": percent_change(
                    cards["total"],
                    comparison_cards["total"],
                ),
                "low_quality_change_percent": percent_change(
                    cards["low_quality"],
                    comparison_cards["low_quality"],
                ),
            },
        }
