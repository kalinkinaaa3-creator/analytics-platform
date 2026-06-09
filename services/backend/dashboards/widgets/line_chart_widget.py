from dashboards.widgets.base import BaseWidget


class LineChartWidget(BaseWidget):

    def build(self, rows: list[dict], params: dict):

        x_field = params.get("x")
        y_field = params.get("y")

        return {
            "type": "line_chart",
            "x": x_field,
            "y": y_field,
            "points": [
                {
                    "x": r.get(x_field),
                    "y": r.get(y_field),
                }
                for r in rows
            ]
        }