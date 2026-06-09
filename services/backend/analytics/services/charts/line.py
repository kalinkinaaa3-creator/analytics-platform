def build_line_chart(
    rows: list[dict],
    x_field: str,
    y_field: str,
):

    points = []

    for row in rows:
        points.append({
            "x": row.get(x_field),
            "y": row.get(y_field),
        })

    return {
        "type": "line_chart",
        "x_field": x_field,
        "y_field": y_field,
        "points": points,
    }