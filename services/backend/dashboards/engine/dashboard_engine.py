from analytics.clickhouse.repository import ClickHouseRepository
from dashboards.engine.widget_engine import WidgetEngine
from analytics.cache.dashboard_cache import (
    get_dashboard_cache,
    set_dashboard_cache,
)


class DashboardEngine:

    def __init__(self):
        self.repo = ClickHouseRepository()
        self.widget_engine = WidgetEngine()

    def get_dashboard(self, dataset_id: int):

        cached = get_dashboard_cache(dataset_id)
        if cached:
            return cached

        rows = self.repo.fetch_dataset_rows(dataset_id)

        dashboard = {
            "widgets": [
                self.widget_engine.render(
                    "table",
                    rows,
                    {}
                ),
                self.widget_engine.render(
                    "line_chart",
                    rows,
                    {"x": "id", "y": "amount"}
                ),
            ]
        }

        set_dashboard_cache(dataset_id, dashboard)

        return dashboard