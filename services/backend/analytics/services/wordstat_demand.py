"""Read-only demand analysis over monthly facts. Missing/duplicate facts are not zeroes."""
from calendar import monthrange
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from statistics import median
import hashlib
import json

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone


def shift(month, offset):
    index = month.year * 12 + month.month - 1 + offset
    return date(index // 12, index % 12 + 1, 1)


def complete_sum(values):
    values = list(values)
    return sum(values) if values and all(v is not None for v in values) else None


def metrics(current, previous, threshold=2):
    delta = current - previous if current is not None and previous is not None else None
    growth = delta * 100 / previous if delta is not None and previous > 0 else None
    status = ("missing" if delta is None else "new" if previous == 0 else
              "growth" if growth > threshold else "decline" if growth < -threshold else "stable")
    return dict(current_volume=current, previous_volume=previous, absolute_change=delta,
                growth_percent=growth, status=status)


def distribution(items):
    total = complete_sum(item["current_volume"] for item in items)
    result = {}
    for status in ("growth", "decline", "stable", "new", "missing"):
        members = [item for item in items if item["status"] == status]
        volume = complete_sum(item["current_volume"] for item in members) if members else 0
        result[status] = dict(count=len(members), share=len(members) * 100 / len(items) if items else None,
                              volume_share=volume * 100 / total if total and volume is not None else None)
    return result


def season_profile(monthly, today, year=None):
    """Match the per-query annual coefficients in the statistics table."""
    year = year or today.year
    values = [monthly.get(date(year, m, 1)) if date(year, m, 1) < today.replace(day=1)
              else None for m in range(1, 13)]
    known = [Decimal(v) for v in values if v is not None]
    average = sum(known) / len(known) if known else None
    coefficients = [
        None if value is None or average is None else
        float((Decimal(value) / average if average else Decimal(0)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP))
        for value in values
    ]
    return dict(years=[year] if known else [], coefficients=coefficients)


def grouped_seasonality(phrases, facts, today, year):
    # Statistics summaries average individual query coefficients, not volumes.
    profiles = [season_profile(facts.get(p, {}), today, year) for p in phrases]
    coefficients = []
    for month in range(12):
        values = [p["coefficients"][month] for p in profiles]
        total = complete_sum(values)
        coefficients.append(round(total / len(values), 2) if total is not None else None)
    return dict(years=[year] if any(v is not None for v in coefficients) else [],
                coefficients=coefficients)


def read_facts(today):
    from analytics.clickhouse.client import get_clickhouse_client
    client = get_clickhouse_client()
    try:
        if not client.execute("EXISTS TABLE default.yd_wordstat_demand")[0][0]:
            return {}, {}, ""
        rows = client.execute("SELECT feature, category, phrase, date, count, snapshot "
                              "FROM default.yd_wordstat_demand WHERE source = 'all' AND date < %(until)s ORDER BY date",
                              {"until": today.replace(day=1)})
    finally:
        client.disconnect()
    return unpack_facts(rows, today)


def unpack_facts(rows, today):
    refs, facts = {}, defaultdict(dict)
    snapshot = ""
    for feature, category, phrase, day, value, snapshot in rows:
        if not phrase:
            continue
        refs[phrase] = dict(phrase=phrase, feature=feature or "Без категории",
                            category=category or "Без подкатегории")
        if day >= today.replace(day=1) or day.day != 1:
            continue
        facts[phrase][day] = None if day in facts[phrase] or value is None or value < 0 else value
    return refs, facts, snapshot


def aggregate_months(phrases, facts):
    days = {day for phrase in phrases for day in facts.get(phrase, {})}
    return {day: complete_sum(facts.get(phrase, {}).get(day) for phrase in phrases) for day in days}


def demand_snapshot():
    from analytics.clickhouse.client import get_clickhouse_client
    client = get_clickhouse_client()
    try:
        if not client.execute("EXISTS TABLE default.yd_wordstat_demand")[0][0]:
            return ""
        rows = client.execute("SELECT snapshot FROM default.yd_wordstat_demand LIMIT 1")
        return rows[0][0] if rows else ""
    finally:
        client.disconnect()


def cached_demand(params):
    """Permissions are checked by the caller. Publication IDs make old caches unreachable."""
    today = timezone.localdate()
    digest = hashlib.sha256(json.dumps(params, sort_keys=True, default=str).encode()).hexdigest()
    for _ in range(2):
        snapshot = demand_snapshot()
        key = f"wordstat:demand:v7:{snapshot}:{today}:{digest}"
        result = cache.get(key) if snapshot else None
        if result is not None:
            return result
        result = build_demand(params, today)
        if result["snapshot"] == snapshot == demand_snapshot():
            if snapshot:
                cache.set(key, result, timeout=24 * 3600)
            return result
    raise RuntimeError("Wordstat publication changed during reading; retry the request")


def build_demand(params, today=None, source=None):
    today = today or timezone.localdate()
    refs, facts, snapshot = source if source is not None else read_facts(today)
    global_months = aggregate_months(list(refs), facts)
    feature, category, phrase = (params.get(k, "") for k in ("feature", "category", "phrase"))
    level = params.get("level", "feature")
    periods = params.get("period_months", 12)
    comparison = params.get("comparison", "year_over_year")
    threshold = float(getattr(settings, "WORDSTAT_DEMAND_NEUTRAL_PERCENT", 2))
    minimum = int(getattr(settings, "WORDSTAT_DEMAND_MIN_BASE", 100))
    selected = [p for p, r in refs.items() if (not feature or r["feature"] == feature)
                and (not category or r["category"] == category)]
    scope_ids = set(params.get("scope_ids") or [])
    element_ids = set(params.get("element_ids") or [])
    def phrase_identity(p):
        r = refs[p]
        return (r["feature"], r["category"], p)
    if scope_ids:
        selected = [p for p in selected if any(
            "\x1f".join(phrase_identity(p)[:depth]) in scope_ids for depth in (1, 2))]
    scope = list(selected)
    depth = {"feature": 1, "category": 2, "phrase": 3}[level]
    option_groups = {}
    for p in scope:
        parts = phrase_identity(p)[:depth]
        option_groups.setdefault("\x1f".join(parts), dict(
            id="\x1f".join(parts), name=parts[-1], feature=parts[0],
            category=parts[1] if depth > 1 else "", phrase=p if depth == 3 else ""))
    if element_ids:
        selected = [p for p in selected if "\x1f".join(phrase_identity(p)[:depth]) in element_ids]
    if phrase:
        selected = [p for p in selected if p == phrase]
    monthly = aggregate_months(selected, facts)
    last = shift(today.replace(day=1), -1)
    first = min(global_months, default=last)
    available = [shift(first, n) for n in range((last.year - first.year) * 12 + last.month - first.month + 1)]
    complete = sorted(d for d, value in monthly.items() if value is not None)
    observed = sorted({d for p in selected for d, value in facts.get(p, {}).items() if value is not None})
    published = sorted({d for days in facts.values() for d, value in days.items()
                        if value is not None and d < today.replace(day=1)})
    end = params.get("end_month") or (published[-1] if published else None)
    options = dict(features=sorted({r["feature"] or "Без категории" for r in refs.values()}),
                   categories=sorted({refs[p]["category"] or "Без подкатегории" for p in selected}))
    response = dict(context=dict(feature=feature, category=category, phrase=phrase, level=level),
                    available_months=[d.strftime("%Y-%m") for d in published], options=options,
                    element_options=sorted(option_groups.values(), key=lambda i: (i["name"], i["id"])),
                    snapshot=snapshot,
                    latest_month=complete[-1].strftime("%Y-%m") if complete else None,
                    month_coverage={d.strftime("%Y-%m"): "complete" if monthly.get(d) is not None else
                                    "partial" if d in observed else "missing" for d in available},
                    neutral_percent=threshold, minimum_base=minimum, items=[], seasonality=[],
                    regions={}, devices={}, summary={}, period=None)
    if end is None:
        return response
    current = [shift(end, offset) for offset in range(1 - periods, 1)]
    previous = [shift(day, -periods if comparison == "previous_period" else -12) for day in current]
    response["period"] = dict(period_months=periods, comparison=comparison, end_month=end.strftime("%Y-%m"),
        current_start=current[0].isoformat(), current_end=end.replace(day=monthrange(end.year, end.month)[1]).isoformat(),
        previous_start=previous[0].isoformat(),
        previous_end=previous[-1].replace(day=monthrange(previous[-1].year, previous[-1].month)[1]).isoformat())

    def measure(phrases):
        monthly = aggregate_months(phrases, facts)
        return metrics(complete_sum(monthly.get(d) for d in current),
                       complete_sum(monthly.get(d) for d in previous), threshold)

    grouped = defaultdict(list)
    for p in selected:
        r = refs[p]
        identity = (r["feature"] or "Без категории", r["category"] or "Без подкатегории", p)
        key = identity[:{"feature": 1, "category": 2, "phrase": 3}[level]]
        grouped[key].append(p)
    items, profiles = [], []
    for key, phrases in grouped.items():
        item = dict(id="\x1f".join(key), name=key[-1], feature=key[0],
                    category=key[1] if len(key) > 1 else "", phrase=key[2] if len(key) > 2 else "",
                    query_count=len(phrases), **measure(phrases))
        item["children"] = distribution([measure([p]) for p in phrases])
        items.append(item)
        profiles.append(dict(id=item["id"], name=item["name"], **grouped_seasonality(phrases, facts, today, end.year)))
    items.sort(key=lambda item: (-(item["current_volume"] or 0), item["id"]))
    focus = selected
    query_items = [dict(id="\x1f".join(phrase_identity(p)), phrase=p, name=p, **measure([p])) for p in selected]
    total = measure(selected)
    response.update(items=items, query_items=query_items, seasonality=profiles, summary=dict(**total, count=len(selected),
                    distribution=distribution(items)),
                    median_volume=median([i["current_volume"] for i in items if i["current_volume"] is not None])
                    if any(i["current_volume"] is not None for i in items) else None)
    parent = (scope if element_ids or phrase else [p for p in refs if refs[p]["feature"] == feature]
              if category else list(refs) if feature else [])
    slices = read_slices(focus, parent, current, previous, snapshot) if source is None else {}
    for label, kind, names in (
        ("devices", "device", [("phone", "Телефоны"), ("desktop", "ПК"), ("tablet", "Планшеты")]),
        ("regions", "region", [(name, name) for name in ("ЕКАТЕРИНБУРГ", "КРАСНОДАР", "МОСКВА", "НИЖНЕКАМСК", "НОВОСИБИРСК", "СПБ", "СНГ")]),
    ):
        response[label] = describe_slices(slices, kind, names, measure(focus), measure(parent), current, previous, minimum)
    return response


def read_slices(focus, parent, current, previous, snapshot):
    from analytics.clickhouse.client import get_clickhouse_client
    if not focus or not snapshot:
        return {}
    client = get_clickhouse_client()
    result = {}
    try:
        # Pin to the same publication as the totals. A concurrent EXCHANGE may yield
        # no slices, but never mixes devices from one generation with demand from another.
        for scope, phrases in (("focus", focus), ("parent", parent)):
            if not phrases:
                continue
            rows = client.execute("""
                SELECT source, dimension, date, sum(count), count(), count(count), uniqExact(phrase)
                FROM default.yd_wordstat_demand
                WHERE source IN ('device', 'region') AND phrase IN %(phrases)s
                  AND date IN %(dates)s AND snapshot = %(snapshot)s
                GROUP BY source, dimension, date
            """, {"phrases": tuple(phrases), "dates": tuple(current + previous), "snapshot": snapshot})
            for kind, dimension, day, value, count, valid, distinct in rows:
                if count == valid == distinct == len(phrases):
                    result[scope, kind, dimension, day] = value
    finally:
        client.disconnect()
    return result


def describe_slices(values, kind, names, total, parent_total, current, previous, minimum):
    items = []
    for dimension, name in names:
        item = dict(id=dimension, name=name, **metrics(
            complete_sum(values.get(("focus", kind, dimension, d)) for d in current),
            complete_sum(values.get(("focus", kind, dimension, d)) for d in previous)))
        item["share"] = item["current_volume"] * 100 / total["current_volume"] if total["current_volume"] and item["current_volume"] is not None else None
        old_share = item["previous_volume"] * 100 / total["previous_volume"] if total["previous_volume"] and item["previous_volume"] is not None else None
        item["change_pp"] = item["share"] - old_share if item["share"] is not None and old_share is not None else None
        parent_volume = complete_sum(values.get(("parent", kind, dimension, d)) for d in current)
        parent_share = parent_volume * 100 / parent_total["current_volume"] if parent_total["current_volume"] and parent_volume is not None else None
        item["difference_vs_parent_pp"] = item["share"] - parent_share if item["share"] is not None and parent_share is not None else None
        item["missing_months"] = [d.strftime("%Y-%m") for d in current
                                  if values.get(("focus", kind, dimension, d)) is None]
        items.append(item)
    complete = all(item["share"] is not None for item in items)
    share_sum = sum(item["share"] for item in items) if complete else None
    # Independently requested dimensions need not form a disjoint partition.
    consistent = complete
    ranked = sorted(items, key=lambda p: -(p["share"] or 0)) if complete and consistent else []
    reason = ("missing_total" if total["current_volume"] is None else
              "zero_total" if total["current_volume"] == 0 else
              "missing_slices" if not complete else None)
    return dict(items=items, complete=complete, consistent=consistent, reason=reason,
        leader=ranked[0] if ranked else None,
        top=ranked[:3], top3_share=sum(p["share"] for p in ranked[:3]) if ranked else None,
        other_share=max(0, 100 - share_sum) if complete else None,
        fastest_growing=max((p for p in items if p["status"] == "growth" and p["previous_volume"] >= minimum),
                            key=lambda p: p["growth_percent"], default=None))
