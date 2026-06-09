from dashboards.widgets.base import BaseWidget


class TableWidget(BaseWidget):

    def build(self, rows: list[dict], params: dict):

        columns = list(rows[0].keys()) if rows else []

        return {
            "type": "table",
            "columns": columns,
            "rows": rows
        }