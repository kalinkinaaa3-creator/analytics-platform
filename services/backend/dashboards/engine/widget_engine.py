from dashboards.widgets.table_widget import TableWidget
from dashboards.widgets.line_chart_widget import LineChartWidget


class WidgetEngine:

    WIDGETS = {
        "table": TableWidget(),
        "line_chart": LineChartWidget(),
    }

    def render(self, widget_type: str, rows: list[dict], params: dict):

        widget = self.WIDGETS.get(widget_type)

        if not widget:
            raise ValueError(f"Unknown widget type: {widget_type}")

        return widget.build(rows, params)