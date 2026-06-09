def build_table(rows: list[dict]):

    if not rows:
        return {
            "columns": [],
            "rows": []
        }

    return {
        "columns": list(rows[0].keys()),
        "rows": rows
    }