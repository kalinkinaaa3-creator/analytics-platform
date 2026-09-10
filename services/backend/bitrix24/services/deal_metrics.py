"""Pure calculations shared by deal reports, cohort reports and their exports."""
from collections import defaultdict
from statistics import mean

from bitrix24.services.dashboard_query import (
    LeadDashboardQuery, group_period_start,
)


RESULT_NAMES = {"S": "Успешно", "F": "Проиграно", "P": "В работе", "?": "Статус не определён"}


def ratio(value, total):
    return value * 100 / total if total else None


def average(values):
    values = [value for value in values if value is not None]
    return mean(values) if values else None


def stage_key(category_id, stage_id):
    return f"{category_id}:{stage_id}"


def enrich_deal(row, histories, stages, now):
    """Never substitute the planned close date or infer unobserved stage visits."""
    row = dict(row)
    category = row["category_id"]
    current_key = stage_key(category, row["stage_id"])
    stage = stages.get(current_key, {})
    semantic = row.get("stage_semantic_id") or stage.get("semantics") or ("P" if stage else "?")
    row["result"] = semantic if semantic in RESULT_NAMES else "?"
    row["stage_key"] = current_key
    row["stage_name"] = stage.get("name") or row["stage_id"] or "Стадия не указана"
    row["result_name"] = RESULT_NAMES[row["result"]]
    visits = {}
    histories = sorted(histories, key=lambda h: (h["created_at"], h["history_id"]))
    for index, event in enumerate(histories):
        key = stage_key(event["category_id"], event["stage_id"])
        end = histories[index + 1]["created_at"] if index + 1 < len(histories) else now
        visit = visits.setdefault(key, {"entered_at": event["created_at"], "days": 0})
        visit["days"] += max(0, (end - event["created_at"]).total_seconds() / 86400)
    # Current stage is known even when its entry timestamp is missing.
    visits.setdefault(current_key, {"entered_at": None, "days": None})
    for key, visit in visits.items():
        visit["semantics"] = stages.get(key, {}).get("semantics", "")
    row["visits"] = visits
    row["stage_days"] = None
    # Reopening a deal invalidates its previous closure. Only the final run of
    # terminal history events matching the current outcome can close it now.
    closed_at = None
    latest_matches = bool(histories and stage_key(histories[-1]["category_id"], histories[-1]["stage_id"]) == current_key)
    if latest_matches:
        entered_at = histories[-1]["created_at"]
        for event in reversed(histories):
            if stage_key(event["category_id"], event["stage_id"]) != current_key:
                break
            entered_at = event["created_at"]
        row["stage_days"] = max(0, (now - entered_at).total_seconds() / 86400)
    if row["result"] in ("S", "F") and latest_matches:
        for event in reversed(histories):
            event_stage = stages.get(stage_key(event["category_id"], event["stage_id"]), {})
            result = event.get("stage_semantic_id") or event_stage.get("semantics") or "P"
            if result != row["result"]:
                break
            closed_at = event["created_at"]
    created = row.get("source_created_at")
    row["closed_at"] = closed_at if created and closed_at and closed_at >= created else None
    row["cycle_days"] = ((row["closed_at"] - created).total_seconds() / 86400) if row["closed_at"] else None
    row["calculated_at"] = now
    row["speed_calculated_at"] = row["closed_at"] if row["result"] in ("S", "F") else now
    row["processing_duration_days"] = row["cycle_days"] if row["result"] in ("S", "F") else (
        max(0, (now - created).total_seconds() / 86400) if created else None
    )
    row["amount"] = float(row.get("opportunity") or 0)
    row["history_missing"] = not histories
    return row


def metrics(rows):
    successful = [row for row in rows if row["result"] == "S"]
    lost = sum(row["result"] == "F" for row in rows)
    return {
        "total": len(rows), "success": len(successful), "lost": lost,
        "in_progress": sum(row["result"] == "P" for row in rows),
        "unknown": sum(row["result"] == "?" for row in rows),
        "amount": sum(row["amount"] for row in rows),
        "success_amount": sum(row["amount"] for row in successful),
        "conversion": ratio(len(successful), len(successful) + lost),
        "average_check": average([row["amount"] for row in successful]),
        "cycle_days": average([row["cycle_days"] for row in rows]),
        "stage_days": average([row["stage_days"] for row in rows]),
        "missing_history": sum(row["history_missing"] for row in rows),
    }


def dimension(row, kind):
    if kind in ("stages", "loss-reasons"):
        return row["stage_key"], f"{row['category_name']} · {row['stage_name']}"
    if kind == "managers":
        return str(row.get("assigned_by_id") or "__unassigned__"), row["manager_name"]
    if kind == "sources":
        return row.get("source_id") or "", row.get("source_name") or "Источник не указан"
    return row["result"], row["result_name"]


def panel(current, previous, prior, kind, group_by, stages):
    def selected(rows):
        return [row for row in rows if kind != "loss-reasons" or row["result"] == "F"]
    current, previous, prior = map(selected, (current, previous, prior))

    def grouped(rows):
        result = defaultdict(list)
        if kind == "results":
            for key in ("S", "F", "P"):
                result[(key, RESULT_NAMES[key])] = []
        for row in rows:
            key, name = dimension(row, kind)
            result[(key, name)].append(row)
        return result

    def dynamics(rows):
        by_period = defaultdict(list)
        for row in rows:
            by_period[group_period_start(row["source_created_at"].date(), group_by)].append(row)
        result = []
        for period, period_rows in by_period.items():
            for (key, name), group in grouped(period_rows).items():
                values = metrics(group)
                result.append({"period": period, "dimension_key": key, "dimension_name": name,
                               "value": len(group), "total": len(period_rows), "return_customer_value": 0,
                               "dimension_target": values["success"], "dimension_low_quality": values["lost"],
                               "share": ratio(len(group), len(period_rows)), "conversion": values["conversion"]})
        return result

    current_groups, previous_groups = grouped(current), grouped(previous)
    summary = []
    for key, name in dict.fromkeys([*current_groups, *previous_groups]):
        rows, old_rows = current_groups.get((key, name), []), previous_groups.get((key, name), [])
        item, old = metrics(rows), metrics(old_rows)
        share, old_share = ratio(len(rows), len(current)), ratio(len(old_rows), len(previous))
        summary.append({**item, "key": key, "name": name, "share": share,
                        "category_id": rows[0]["category_id"] if rows else old_rows[0]["category_id"] if old_rows else None,
                        "delta_count": len(rows) - len(old_rows), "delta_amount": item["amount"] - old["amount"],
                        "delta_share": share - old_share if share is not None and old_share is not None else None})
    if kind == "stages":
        summary.sort(key=lambda r: (stages.get(r["key"], {}).get("category_sort", 999),
                                    r["category_id"] or 0, stages.get(r["key"], {}).get("sort") or 0, r["key"]))
    elif kind == "results":
        summary.sort(key=lambda r: list(RESULT_NAMES).index(r["key"]))
    else:
        summary.sort(key=lambda r: (-r["total"], r["name"]))
    total, old = metrics(current), metrics(previous)
    return {"rows": LeadDashboardQuery._enrich_dynamics(dynamics(current), dynamics(previous), group_by, dynamics(prior)),
            "summary": summary, "total": {**total, "key": "", "name": "Итого", "share": 100 if current else None,
            "delta_count": len(current) - len(previous), "delta_amount": total["amount"] - old["amount"],
            "delta_share": 0 if current and previous else None}}
