def build_table(rows):
    if not rows:
        return {"columns": [], "rows": []}

    columns = list(rows[0].keys())

    return {
        "columns": columns,
        "rows": rows
    }