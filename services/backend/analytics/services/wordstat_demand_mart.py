"""Publish an independent, atomically replaced ClickHouse mart; never call Wordstat."""
import logging
from collections import defaultdict
from datetime import date
from uuid import uuid4

from django.db import transaction
from django.utils import timezone

from datasets.models import YdWordstatDeviceRaw, YdWordstatIplastRaw, YdWordstatPhraseRef, YdWordstatIplastRegionRef
from datasets.services.external_api.yd_wordstat_contract import build_iplast_groups

TABLE = "default.yd_wordstat_demand"
MONTH_COLUMNS = [f"month_{month}" for month in range(1, 13)]
COLUMNS = ["source", "dimension", "feature", "category", "phrase", "date", "count", "snapshot"]
logger = logging.getLogger("external_api.yd_wordstat")


def publish_rows(client, rows):
    """Stage and verify every batch before exposing it to dashboard readers."""
    engine = client.execute("SELECT engine FROM system.databases WHERE name = 'default'")[0][0]
    if engine not in ("Atomic", "Shared"):
        raise RuntimeError("Wordstat demand publication requires an Atomic/Shared ClickHouse database")
    definition = ", ".join(["source String", "dimension String", "feature String", "category String",
                            "phrase String", "date Date", "count Nullable(Int64)", "snapshot String"])
    client.execute(f"CREATE TABLE IF NOT EXISTS {TABLE} ({definition}) ENGINE = MergeTree ORDER BY (source, phrase, dimension, date)")
    staging = f"{TABLE}_stage_{uuid4().hex}"
    client.execute(f"CREATE TABLE {staging} AS {TABLE}")
    counts, expected, valid, valid_all = defaultdict(int), 0, 0, 0
    snapshot = uuid4().hex
    batch = []
    try:
        for row in rows:
            counts[row[0]] += 1
            if row[5] is None or row[5].day != 1 or (row[6] is not None and row[6] < 0):
                raise ValueError("Invalid monthly fact; mart was not published")
            if row[6] is not None:
                expected += row[6]
                valid += 1
                valid_all += row[0] == "all"
            batch.append((*row, snapshot))
            if len(batch) >= 10000:
                client.execute(f"INSERT INTO {staging} ({', '.join(COLUMNS)}) VALUES", batch)
                batch = []
        if batch:
            client.execute(f"INSERT INTO {staging} ({', '.join(COLUMNS)}) VALUES", batch)
        if not valid_all:
            raise ValueError("No total demand history; refusing to publish an empty mart")
        actual = client.execute(f"SELECT count(), sum(count), count(count) FROM {staging}")[0]
        if actual[0] != sum(counts.values()) or (actual[1] or 0) != expected or actual[2] != valid:
            raise RuntimeError("ClickHouse staging row/month totals do not match the source")
        duplicate = client.execute(f"SELECT count() FROM (SELECT source, phrase, dimension, date FROM {staging} GROUP BY source, phrase, dimension, date HAVING count() > 1)")[0][0]
        if duplicate:
            raise ValueError("Duplicate monthly facts; mart was not published")
        client.execute(f"EXCHANGE TABLES {TABLE} AND {staging}")
        return dict(rows=sum(counts.values()), by_source=dict(counts))
    finally:
        # After EXCHANGE, this is the previous version of this mart only.
        try:
            client.execute(f"DROP TABLE IF EXISTS {staging}")
        except Exception:
            logger.exception("Could not remove Wordstat demand staging table %s", staging)


def sync_wordstat_demand():
    """Caller holds the shared pipeline lock. Read-only on PG and the legacy CH table."""
    from analytics.clickhouse.client import get_clickhouse_client
    today = timezone.localdate()
    client = get_clickhouse_client()
    try:
        with transaction.atomic():
            refs = {r["phrase"]: r for r in YdWordstatPhraseRef.objects.values("phrase", "feature", "category")}
            mappings = list(YdWordstatIplastRegionRef.objects.values("macroregion_label", "region_value"))
            groups = build_iplast_groups(mappings) if mappings else []
            fingerprints = {g["name"]: g["fingerprint"] for g in groups}

            def rows():
                # Preserve the existing month-column values; do not reconstruct monthly demand from annual totals.
                totals = client.execute(f"SELECT phrase, year, {', '.join(MONTH_COLUMNS)} FROM default.yd_wordstat_for WHERE year <= %(year)s ORDER BY phrase, year", {"year": today.year})
                seen = set()
                for phrase, year, *months in totals:
                    if phrase not in refs:
                        continue
                    if (phrase, year) in seen or any(v is not None and v < 0 for v in months):
                        raise ValueError("Invalid/duplicate legacy monthly history; mart was not published")
                    seen.add((phrase, year))
                    for month, count in enumerate(months, 1):
                        day = date(year, month, 1)
                        if day < today.replace(day=1):
                            yield ("all", "", refs[phrase]["feature"] or "", refs[phrase]["category"] or "", phrase, day, count)
                # Keep references with no history visible as missing, not silently absent.
                for phrase in refs.keys() - {p for p, _ in seen}:
                    from analytics.services.wordstat_demand import shift
                    yield ("all", "", refs[phrase]["feature"] or "", refs[phrase]["category"] or "", phrase, shift(today.replace(day=1), -1), None)
                devices = YdWordstatDeviceRaw.objects.filter(phrase__in=refs, device__in=["desktop", "phone", "tablet"], date__lt=today.replace(day=1)).order_by("phrase", "device", "date").values_list("phrase", "device", "date", "count")
                for p, dimension, day, count in devices.iterator(chunk_size=5000):
                    yield ("device", dimension, refs[p]["feature"] or "", refs[p]["category"] or "", p, day, count)
                regions = YdWordstatIplastRaw.objects.filter(phrase__in=refs, date__lt=today.replace(day=1)).order_by("phrase", "macroregion_label", "date").values_list("phrase", "macroregion_label", "date", "count", "group_fingerprint")
                valid_regions = ((p, d, day, count) for p, d, day, count, fp in regions.iterator(chunk_size=5000) if fingerprints.get(d) == fp)
                for p, dimension, day, count in valid_regions:
                    yield ("region", dimension, refs[p]["feature"] or "", refs[p]["category"] or "", p, day, count)
                if refs != {r["phrase"]: r for r in YdWordstatPhraseRef.objects.values("phrase", "feature", "category")} or mappings != list(YdWordstatIplastRegionRef.objects.values("macroregion_label", "region_value")):
                    raise RuntimeError("Wordstat references changed while building the mart")

            return publish_rows(client, rows())
    finally:
        client.disconnect()
