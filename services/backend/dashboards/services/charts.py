def build_table(rows):
    if not rows:
        return {
            "columns": [],
            "rows": [],
        }

    return {
        "columns": list(rows[0].keys()),
        "rows": rows,
    }


def build_line_chart(rows, x_field, y_field):
    return {
        "type": "line",
        "data": [
            {
                "x": row.get(x_field),
                "y": row.get(y_field),
            }
            for row in rows
        ]
    }