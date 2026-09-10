"""Lead-created cohorts with all subsequent linked deals (including 1:N)."""
from collections import defaultdict

from .deal_metrics import average, ratio


def visited_stage(row, key):
    visit = row["visits"].get(key)
    if visit is None:
        return False
    # A historical win followed by reopening is not a currently successful deal.
    return visit.get("semantics") != "S" or (row["result"] == "S" and row["stage_key"] == key)


def summary(leads, deals):
    lead_map = {row["lead_id"]: row for row in leads}
    converted = {row["lead_id"] for row in deals}
    success = [row for row in deals if row["result"] == "S"]
    durations = [(row["closed_at"] - lead_map[row["lead_id"]]["source_created_at"]).total_seconds() / 86400
                 for row in success if row["closed_at"] and row["closed_at"] >= lead_map[row["lead_id"]]["source_created_at"]]
    return {"leads": len(leads), "converted_leads": len(converted), "deals": len(deals),
            "success": len(success), "lost": sum(row["result"] == "F" for row in deals),
            "in_progress": sum(row["result"] == "P" for row in deals),
            "lead_to_deal": ratio(len(converted), len(leads)),
            "deal_to_success": ratio(len(success), len(deals)),
            "lead_to_success": ratio(len(success), len(leads)),
            "full_cycle_days": average(durations), "completed_cycles": len(durations),
            "success_amount": sum(row["amount"] for row in success),
            "missing_history": sum(row["history_missing"] for row in leads) + sum(row["history_missing"] for row in deals)}


def funnel(leads, deals, refs):
    def transitions(stages):
        for index, stage in enumerate(stages):
            if index:
                previous = stages[index - 1]
                stage["transition_share"] = ratio(len(stage["_ids"] & previous["_ids"]), previous["count"])
            if index + 1 < len(stages):
                stage["loss_to_next"] = len(stage["_ids"] - stages[index + 1]["_ids"])
        for stage in stages:
            stage.pop("_ids")
        return stages

    def lead_stage(key, name, rows):
        return {"key": key, "name": name, "count": len(rows), "unit": "leads",
                "share": ratio(len(rows), len(leads)), "amount": sum(float(row.get("opportunity") or 0) for row in rows),
                "days": average([row.get("visit_days", {}).get(key) for row in rows]),
                "_ids": {row["lead_id"] for row in rows}}
    stages = [lead_stage("all", "Все лиды", leads)]
    # Real lead stages only; no invented "qualified" stage or synthetic timestamps.
    for stage in refs["lead_stages"]:
        if stage["semantics"] == "F":
            continue
        rows = [row for row in leads if stage["status_id"] in row["visited"]]
        stages.append(lead_stage(stage["status_id"], stage["name"], rows))
    converted = {row["lead_id"] for row in deals}
    stages.append(lead_stage("converted", "Конвертированы в сделки", [row for row in leads if row["lead_id"] in converted]))
    branches = []
    for category in refs["categories"]:
        rows = [row for row in deals if row["category_id"] == category["category_id"]]
        if not rows:
            continue
        branch_stages = [{"key": "all", "name": "Созданные сделки", "count": len(rows), "unit": "deals",
                          "share": ratio(len(rows), len(leads)), "amount": sum(row["amount"] for row in rows), "days": None,
                          "_ids": {row["deal_id"] for row in rows}}]
        category_stages = sorted([s for s in refs["stages"].values() if s["category_id"] == category["category_id"] and s["semantics"] != "F"], key=lambda s: s["sort"] or 0)
        for stage in category_stages:
            visited = [row for row in rows if visited_stage(row, stage["key"])]
            branch_stages.append({"key": stage["key"], "name": stage["name"], "count": len(visited), "unit": "deals",
                                  "share": ratio(len(visited), len(leads)), "amount": sum(row["amount"] for row in visited),
                                  "_ids": {row["deal_id"] for row in visited},
                                  "days": average([row["visits"][stage["key"]]["days"] for row in visited])})
        branches.append({**category, "count": len(rows), "leads": len({row["lead_id"] for row in rows}),
                         "success": sum(row["result"] == "S" for row in rows), "share": ratio(len(rows), len(deals)),
                         "stages": transitions(branch_stages)})
    branches.sort(key=lambda row: (-row["count"], row["category_id"]))
    return {"lead_stages": transitions(stages), "branches": branches}


def managers(leads, deals):
    groups = defaultdict(list)
    linked = defaultdict(list)
    for row in deals:
        linked[row["lead_id"]].append(row)
    for row in leads:
        groups[(row["manager_id"], row["manager_name"])].append(row)
    return sorted([{"manager_id": key, "name": name, **summary(rows, [deal for row in rows for deal in linked[row["lead_id"]]])}
                   for (key, name), rows in groups.items()], key=lambda row: (-row["leads"], row["name"]))


def detail_rows(leads, deals, standalone, filters):
    kind, key = filters.get("segment_type"), filters.get("segment_key", "")
    category = filters.get("detail_category_id")
    if kind == "standalone":
        return [{**row, "lead_created_at": None, "link_state": "Лид не найден или удалён" if row.get("lead_id") else "Сделка без лида"} for row in standalone]
    if kind == "lead-stage":
        converted = {row["lead_id"] for row in deals}
        leads = [row for row in leads if key == "all" or (key == "converted" and row["lead_id"] in converted) or key in row["visited"]]
    if kind == "deal-stage":
        deals = [row for row in deals if (category is None or row["category_id"] == category) and (key == "all" or visited_stage(row, key))]
        ids = {row["lead_id"] for row in deals}
        leads = [row for row in leads if row["lead_id"] in ids]
    linked = defaultdict(list)
    for row in deals:
        linked[row["lead_id"]].append(row)
    result = []
    for lead in leads:
        for deal in linked[lead["lead_id"]] or [None]:
            result.append({**(deal or {}), "lead_id": lead["lead_id"], "lead_title": lead["title"],
                           "lead_created_at": lead["source_created_at"], "lead_manager": lead["manager_name"],
                           "lead_department": lead["department_name"], "source_name": lead["source_name"],
                           "selected_stage_days": deal["visits"].get(key, {}).get("days") if deal and kind == "deal-stage" else None,
                           "link_state": "Лид → сделка" if deal else "Лид без сделки",
                           "full_cycle_days": (deal["closed_at"] - lead["source_created_at"]).total_seconds() / 86400
                           if deal and deal["result"] == "S" and deal["closed_at"] and deal["closed_at"] >= lead["source_created_at"] else None})
    return result
