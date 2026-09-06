"""Read-only Wordstat checks: saved downloads and the two published ClickHouse views."""
from collections import defaultdict
from datetime import date, timedelta

from django.db.models import Count, Q, Sum
from django.utils import timezone

from analytics.services.wordstat_demand import shift
from datasets.models import YdWordstatApiCheckpoint, YdWordstatAllRaw, YdWordstatDeviceRaw, YdWordstatIplastRaw
from datasets.services.external_api.yd_wordstat_api_loader import get_configuration, make_jobs


def inspect_wordstat(today=None, deep=False):
    from analytics.clickhouse.client import get_clickhouse_client
    today = today or timezone.localdate()
    until = today.replace(day=1)
    months = [shift(until, n) for n in range(-24, 0)]
    config = get_configuration()  # Local references only; never calls the paid API.
    phrases = [r["phrase"] for r in config["phrases"]]
    expected = len(phrases)
    report = {"target_month": months[-1].strftime("%Y-%m"), "phrases": expected,
              "window_start": months[0].isoformat(), "problems": [], "coverage": {}, "checkpoints": {}}
    problems = report["problems"]
    raw = {}
    dimensions = [("all", "", YdWordstatAllRaw, {})]
    dimensions += [("device", d, YdWordstatDeviceRaw, {"device": d}) for d in config["devices"]]
    dimensions += [("region", g["name"], YdWordstatIplastRaw,
                    {"macroregion_label": g["name"], "group_fingerprint": g["fingerprint"]}) for g in config["groups"]]
    for source, dimension, model, filters in dimensions:
        rows = model.objects.filter(phrase__in=phrases, date__gte=months[0], date__lt=until, **filters).values("date").annotate(
            rows=Count("pk"), valid=Count("pk", filter=Q(count__gte=0)), phrases=Count("phrase", distinct=True), total=Sum("count"))
        for row in rows:
            raw[source, dimension, row["date"]] = (row["rows"], row["valid"], row["phrases"], row["total"])

    def check_coverage(label, facts, compare=None):
        missing, mismatched = {}, {}
        allowed = {(s, d) for s, d, _, _ in dimensions}
        invalid = sum(1 for s, d, day in facts if (s, d) not in allowed or day not in months)
        if invalid:
            problems.append(f"{label}: {invalid} unexpected dimensions/month dates")
        for source, dimension, _, _ in dimensions:
            key = f"{source}:{dimension or 'all'}"
            bad, different = [], []
            for day in months:
                value = facts.get((source, dimension, day))
                if value is None or value[:3] != (expected, expected, expected):
                    bad.append(day.strftime("%Y-%m"))
                if compare is not None and value != compare.get((source, dimension, day)):
                    different.append(day.strftime("%Y-%m"))
            if bad:
                missing[key] = bad
            if different:
                mismatched[key] = different
        report["coverage"][label] = {"incomplete_months": missing, "different_from_postgres": mismatched}
        if missing:
            problems.append(f"{label}: incomplete monthly coverage in {len(missing)} dimensions")
        if mismatched:
            problems.append(f"{label}: published values differ from PostgreSQL in {len(mismatched)} dimensions")
        inconsistent = {}
        for source in ("device", "region"):
            bad = []
            for day in months:
                total = facts.get(("all", "", day))
                parts = [facts.get((s, d, day)) for s, d, _, _ in dimensions if s == source]
                if total and total[:3] == (expected, expected, expected) and all(
                        p and p[:3] == (expected, expected, expected) for p in parts):
                    if sum(p[3] for p in parts) > total[3]:
                        bad.append(day.strftime("%Y-%m"))
            if bad:
                inconsistent[source] = bad
        report["coverage"][label]["slices_exceed_total"] = inconsistent
        if inconsistent:
            problems.append(f"{label}: device/region sums exceed total demand")

    check_coverage("postgres", raw)
    checkpoints = {(r["source"], r["phrase"], r["dimension"]): r for r in YdWordstatApiCheckpoint.objects.values()}
    missing_cp = 0
    for job in make_jobs(config):
        cp = checkpoints.get((job.source, job.phrase, job.dimension))
        if cp is None or cp["fingerprint"] != job.fingerprint or cp["date_finish"] != until - timedelta(days=1):
            missing_cp += 1
    report["checkpoints"] = {"missing_or_stale": missing_cp, "expected": expected * len(dimensions)}
    if missing_cp:
        problems.append(f"PostgreSQL: {missing_cp} missing/stale download checkpoints (imported data may have no checkpoints)")
    valid_groups = Q(pk__in=[])
    for group in config["groups"]:
        valid_groups |= Q(macroregion_label=group["name"], group_fingerprint=group["fingerprint"])
    report["excluded_region_rows"] = YdWordstatIplastRaw.objects.filter(
        phrase__in=phrases, date__gte=months[0], date__lt=until).exclude(valid_groups).count()
    if report["excluded_region_rows"]:
        problems.append("PostgreSQL: region rows have an obsolete/unknown IPLAST group fingerprint; they cannot enter the mart")

    client = get_clickhouse_client()
    try:
        table = "default.yd_wordstat_demand"
        if not client.execute(f"EXISTS TABLE {table}")[0][0]:
            problems.append(f"ClickHouse: {table} does not exist; run sync_wordstat_demand")
        else:
            rows = client.execute(f"""SELECT source, dimension, date, count(), countIf(count >= 0),
                uniqExact(phrase), sum(count) FROM {table}
                WHERE phrase IN %(phrases)s AND date >= %(start)s AND date < %(until)s
                GROUP BY source, dimension, date""", {"phrases": tuple(phrases), "start": months[0], "until": until})
            facts = {(s, d, day): (n, valid, unique, total) for s, d, day, n, valid, unique, total in rows}
            check_coverage("clickhouse_demand", facts, raw)
            report["snapshot_count"] = client.execute(f"SELECT uniqExact(snapshot) FROM {table}")[0][0]
            if report["snapshot_count"] != 1:
                problems.append("ClickHouse demand: expected exactly one publication snapshot")
        table = "default.yd_wordstat_for"
        if not client.execute(f"EXISTS TABLE {table}")[0][0]:
            problems.append(f"ClickHouse: {table} does not exist")
        else:
            columns = ", ".join(f"month_{m}" for m in range(1, 13))
            rows = client.execute(f"SELECT phrase, year, {columns} FROM {table} WHERE phrase IN %(phrases)s AND year >= %(year)s",
                                  {"phrases": tuple(phrases), "year": months[0].year})
            grouped = defaultdict(list)
            for phrase, year, *values in rows:
                for m, value in enumerate(values, 1):
                    day = date(year, m, 1)
                    if day in months:
                        grouped[day].append((phrase, value))
            different = []
            for day in months:
                values = grouped[day]
                summary = (len(values), sum(v is not None and v >= 0 for _, v in values), len({p for p, _ in values}),
                           sum(v for _, v in values if v is not None) if any(v is not None for _, v in values) else None)
                if summary[:3] != (expected, expected, expected) or summary != raw.get(("all", "", day)):
                    different.append(day.strftime("%Y-%m"))
            report["coverage"]["clickhouse_statistics"] = {"incomplete_or_different_months": different}
            if different:
                problems.append(f"ClickHouse statistics: incomplete/different months: {', '.join(different)}")
    finally:
        client.disconnect()
    if deep:
        from datasets.services.external_api.yd_wordstat_api_loader import validate_download
        report["deep_download_validation"] = validate_download(config, today)
        if not report["deep_download_validation"]["ok"]:
            problems.append("Deep validation: saved downloads do not match their checkpoints")
    report["ok"] = not problems
    return report
