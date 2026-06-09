from analytics.clickhouse.repository import ClickHouseRepository

from analytics.cache.dashboard_cache import (
    get_dashboard_cache,
    set_dashboard_cache,
)

from analytics.services.tables.table_builder import build_table
from analytics.services.charts.line import build_line_chart


class DashboardEngineV3:

    def __init__(self):
        self.repo = ClickHouseRepository()

    def build_widget(self, widget: dict, rows: list[dict]):

        widget_type = widget.get("type")
        config = widget.get("config") or {}

        if widget_type == "table":
            return {
                "type": "table",
                "data": build_table(rows),
            }

        if widget_type == "line_chart":
            return {
                "type": "line_chart",
                "data": build_line_chart(
                    rows,
                    config.get("x", "id"),
                    config.get("y", "amount"),
                ),
            }

        return {
            "type": widget_type,
            "error": f"Unknown widget type: {widget_type}",
        }

    def build_dashboard(self, dashboard: dict):

        dashboard_id = dashboard["id"]
        dataset_id = dashboard.get("dataset_id", 1)

        cached = get_dashboard_cache(dashboard_id)

        if cached:
            return cached

        rows = self.repo.fetch_dataset_rows(dataset_id)

        result = {
            "dashboard_id": dashboard_id,
            "dataset_id": dataset_id,
            "widgets": [
                self.build_widget(widget, rows)
                for widget in dashboard.get("widgets", [])
            ],
        }

        set_dashboard_cache(dashboard_id, result)

        return result