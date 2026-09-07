"""Wordstat v2 wire format and IPLAST grouping, without network or DB access."""
import calendar
import hashlib
import json
from datetime import date, datetime


IPLAST_GROUPS = frozenset({
    "ЕКАТЕРИНБУРГ", "КРАСНОДАР", "МОСКВА", "НИЖНЕКАМСК",
    "НОВОСИБИРСК", "СПБ", "СНГ",
})
DEVICES = {name: f"DEVICE_{name.upper()}" for name in ("all", "desktop", "phone", "tablet")}


def month_dates(start, finish):
    current = start.replace(day=1)
    while current <= finish:
        yield current
        current = date(current.year + (current.month == 12), current.month % 12 + 1, 1)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def dynamics_body(phrase, date_start, date_finish, devices=None, regions=None):
    if not isinstance(phrase, str) or not phrase.strip() or len(phrase) > 400 or len(phrase.split()) > 40:
        raise ValueError("Wordstat phrase must contain 1–400 characters and at most 40 words")
    if not isinstance(date_start, date) or not isinstance(date_finish, date):
        raise ValueError("Wordstat dates must be date objects")
    if date_start.day != 1 or date_finish.day != calendar.monthrange(date_finish.year, date_finish.month)[1]:
        raise ValueError("Monthly dynamics requires full calendar months")
    if date_start > date_finish:
        raise ValueError("Invalid Wordstat date range")
    selected = devices if devices is not None else ["all"]
    if not selected or len(selected) > 3 or any(item not in DEVICES for item in selected):
        raise ValueError("Unsupported Wordstat devices")
    if "all" in selected and len(selected) != 1:
        raise ValueError("The all device cannot be combined with other devices")
    body = {
        "phrase": phrase, "period": "PERIOD_MONTHLY",
        "fromDate": date_start.isoformat() + "T00:00:00Z",
        "toDate": date_finish.isoformat() + "T00:00:00Z",
        "devices": [DEVICES[item] for item in selected],
    }
    if regions is not None:
        if not regions or len(regions) > 100 or any(not str(item).isdigit() for item in regions):
            raise ValueError("Wordstat requires 1–100 numeric region IDs")
        body["regions"] = [str(item) for item in regions]
    return body


def parse_monthly_results(data, start, finish):
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise ValueError("Wordstat response has no results array")
    expected = set(month_dates(start, finish))
    rows = {}
    for item in data["results"]:
        if not isinstance(item, dict):
            raise ValueError("Invalid Wordstat result row")
        try:
            stamp = datetime.fromisoformat(item["date"].replace("Z", "+00:00"))
            row_date = stamp.date()
            # Protobuf JSON omits scalar defaults: a returned month without
            # count represents zero. An absent month is still incomplete.
            raw_count = item.get("count", 0)
            if isinstance(raw_count, bool) or not isinstance(raw_count, (str, int)):
                raise ValueError("Invalid count type")
            count = int(raw_count)
        except (KeyError, ValueError, TypeError, AttributeError) as exc:
            raise ValueError("Invalid Wordstat date or count") from exc
        if stamp.tzinfo is None or row_date not in expected or row_date in rows or not 0 <= count <= 2**63 - 1:
            raise ValueError("Wordstat returned duplicate/out-of-range months or count")
        rows[row_date] = {"date": row_date, "count": count}
    missing = expected - rows.keys()
    if missing:
        raise ValueError(f"Wordstat response is incomplete: {len(missing)} months missing; first={min(missing)}")
    return [rows[key] for key in sorted(rows)]


def build_iplast_groups(mappings):
    groups = {}
    seen = set()
    for item in mappings:
        name = item["macroregion_label"]
        region_id = item["region_value"]
        if name not in IPLAST_GROUPS or not str(region_id).isdigit() or region_id in seen:
            raise ValueError("Invalid or duplicate IPLAST mapping")
        seen.add(region_id)
        groups.setdefault(name, []).append(int(region_id))
    if set(groups) != IPLAST_GROUPS:
        raise ValueError("IPLAST mapping must contain all seven dashboard groups")
    result = []
    for name, ids in sorted(groups.items()):
        ids.sort()
        if len(ids) > 100:
            raise ValueError(f"IPLAST group {name} exceeds the 100-region API limit")
        result.append({"name": name, "regions": ids, "fingerprint": fingerprint(ids)})
    return result


def validate_group_tree(groups, data):
    from .yd_wordstat_regions_v2_diagnostic import flatten_regions_tree

    rows, malformed = flatten_regions_tree(data)
    by_id = {row["id"]: row for row in rows}
    if malformed or not rows or len(by_id) != len(rows):
        raise ValueError("Malformed or duplicate Wordstat region tree")
    selected = {str(region) for group in groups for region in group["regions"]}
    missing = selected - by_id.keys()
    if missing:
        raise ValueError(f"IPLAST regions missing in Wordstat v2: {sorted(missing)}")
    for region_id in selected:
        overlap = selected.intersection(by_id[region_id]["ancestor_ids"])
        if overlap:
            raise ValueError(f"Overlapping IPLAST regions: {region_id}, ancestors={sorted(overlap)}")
    return {"nodes": len(rows), "groups": len(groups), "regions": len(selected)}
