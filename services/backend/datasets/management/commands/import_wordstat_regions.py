"""Stream the legacy regional CSV into temporary PG tables; no API/CH calls."""
import csv
import io
import json
from datetime import date
from pathlib import Path
from zipfile import ZipFile

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from analytics.services.yd_wordstat_api_pipeline import wordstat_pipeline_lock
from datasets.services.external_api.yd_wordstat_api_loader import get_configuration

HEADER = ["id", "phrase", "region_label", "region_value", "date", "count", "feature",
          "category", "country_label", "macroregion_label", "macroregion_iplast", "date_add"]


def archive_member(archive):
    members = [m for m in archive.infolist() if not m.is_dir()]
    if len(members) != 1 or not members[0].filename.lower().endswith(".csv"):
        raise CommandError("ZIP must contain exactly one CSV file")
    with archive.open(members[0]) as raw, io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as stream:
        if next(csv.reader(stream), None) != HEADER:
            raise CommandError("Unexpected CSV columns; expected: " + ", ".join(HEADER))
    return members[0]


class Command(BaseCommand):
    help = "Validate/import legacy regional ZIP into IPLAST aggregates. Default: rollback (dry run)."

    def add_arguments(self, parser):
        parser.add_argument("archive", type=Path)
        parser.add_argument("--through", required=True, help="Last month to consider, YYYY-MM")
        parser.add_argument("--apply", action="store_true", help="Commit missing aggregates; existing values are preserved")

    def handle(self, *args, **options):
        try:
            through = date.fromisoformat(options["through"] + "-01")
        except ValueError as exc:
            raise CommandError("--through must be YYYY-MM") from exc
        if through >= timezone.localdate().replace(day=1):
            raise CommandError("Only closed calendar months may be imported")
        if connection.vendor != "postgresql":
            raise CommandError("This import requires PostgreSQL")
        with ZipFile(options["archive"]) as archive:
            member = archive_member(archive)
            with wordstat_pipeline_lock(), transaction.atomic(), connection.cursor() as cursor:
                config = get_configuration()
                cursor.execute("""CREATE TEMP TABLE ws_import_raw (
                    id bigint, phrase text, region_label text, region_value integer,
                    date date, count bigint, feature text, category text, country_label text,
                    macroregion_label text, macroregion_iplast text, date_add text
                ) ON COMMIT DROP""")
                self.stdout.write("Streaming CSV to a temporary PostgreSQL table (no extraction)...")
                with archive.open(member) as raw, io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as stream:
                    cursor.copy_expert("COPY ws_import_raw FROM STDIN WITH (FORMAT CSV, HEADER TRUE)", stream)
                cursor.execute("ANALYZE ws_import_raw")
                cursor.execute("""SELECT count(*), min(date), max(date), count(*) FILTER (
                    WHERE phrase IS NULL OR phrase = '' OR region_value IS NULL OR date IS NULL
                       OR date <> date_trunc('month', date)::date OR count IS NULL OR count < 0)
                    FROM ws_import_raw""")
                rows, first, last, invalid = cursor.fetchone()
                if not rows or invalid or first > through:
                    raise CommandError(f"Empty/invalid archive or invalid period: rows={rows}, invalid={invalid}")
                cursor.execute("""SELECT 1 FROM ws_import_raw GROUP BY phrase, region_value, date
                                  HAVING count(*) > 1 LIMIT 1""")
                if cursor.fetchone():
                    raise CommandError("Duplicate phrase/region/month in CSV; nothing imported")
                cursor.execute("""CREATE TEMP TABLE ws_import_map (
                    region_value integer PRIMARY KEY, label text, fingerprint text
                ) ON COMMIT DROP""")
                cursor.executemany("INSERT INTO ws_import_map VALUES (%s, %s, %s)", [
                    (region, group["name"], group["fingerprint"])
                    for group in config["groups"] for region in group["regions"]])
                cursor.execute("""SELECT count(*) FROM ws_import_raw r
                    LEFT JOIN ws_import_map m USING (region_value)
                    WHERE m.region_value IS NULL OR r.macroregion_iplast IS DISTINCT FROM m.label""")
                if cursor.fetchone()[0]:
                    raise CommandError("Archive regional mapping differs from current IPLAST reference; nothing imported")
                cursor.execute("""CREATE TEMP TABLE ws_import_phrases (
                    phrase text PRIMARY KEY, feature text, category text
                ) ON COMMIT DROP""")
                cursor.executemany("INSERT INTO ws_import_phrases VALUES (%s, %s, %s)", [
                    (p["phrase"], p["feature"], p["category"]) for p in config["phrases"]])
                cursor.execute("""SELECT count(DISTINCT r.phrase) FROM ws_import_raw r
                    LEFT JOIN ws_import_phrases p USING (phrase) WHERE p.phrase IS NULL""")
                if cursor.fetchone()[0]:
                    raise CommandError("Archive contains phrases absent from the current reference; nothing imported")
                # Each month must include every region of the group, even zero-valued ones.
                cursor.execute("""CREATE TEMP TABLE ws_import_groups ON COMMIT DROP AS
                    SELECT label, fingerprint, count(*) AS size FROM ws_import_map GROUP BY label, fingerprint""")
                cursor.execute("""CREATE TEMP TABLE ws_import_months ON COMMIT DROP AS
                    SELECT r.phrase, m.label, r.date, sum(r.count)::bigint AS count
                    FROM ws_import_raw r JOIN ws_import_map m USING (region_value)
                    JOIN ws_import_groups g ON g.label = m.label
                    WHERE r.date <= %s GROUP BY r.phrase, m.label, r.date
                    HAVING count(*) = max(g.size)""", [through])
                cursor.execute("CREATE UNIQUE INDEX ON ws_import_months (phrase, label, date)")
                cursor.execute("ANALYZE ws_import_months")
                # Keep a continuous prefix. A missing region in June must not be hidden
                # by a later August row when the API loader calculates its start date.
                cursor.execute("""CREATE TEMP TABLE ws_import_cutoffs ON COMMIT DROP AS
                    SELECT p.phrase, g.label, min(d.day)::date AS first_gap
                    FROM ws_import_phrases p CROSS JOIN ws_import_groups g
                    CROSS JOIN generate_series(%s::date, %s::date, interval '1 month') d(day)
                    LEFT JOIN ws_import_months m ON m.phrase=p.phrase AND m.label=g.label AND m.date=d.day
                    WHERE m.date IS NULL GROUP BY p.phrase, g.label""", [first, through])
                cursor.execute("""CREATE TEMP TABLE ws_import_ready ON COMMIT DROP AS
                    SELECT m.*, g.fingerprint, p.feature, p.category FROM ws_import_months m
                    JOIN ws_import_groups g USING (label) JOIN ws_import_phrases p USING (phrase)
                    LEFT JOIN ws_import_cutoffs c USING (phrase, label)
                    WHERE c.first_gap IS NULL OR m.date < c.first_gap""")
                cursor.execute("""SELECT count(*) FROM ws_import_ready r JOIN yd_wordstat_iplast_api t
                    ON t.phrase=r.phrase AND t.macroregion_label=r.label AND t.date=r.date
                    WHERE t.group_fingerprint IS DISTINCT FROM r.fingerprint""")
                if cursor.fetchone()[0]:
                    raise CommandError("Existing aggregates have a different fingerprint; nothing imported")
                cursor.execute("SELECT count(*) FROM ws_import_cutoffs")
                incomplete_pairs = cursor.fetchone()[0]
                cursor.execute("SELECT count(*) FROM ws_import_ready")
                eligible = cursor.fetchone()[0]
                cursor.execute("""SELECT count(*) FROM ws_import_ready r JOIN yd_wordstat_iplast_api t
                    ON t.phrase=r.phrase AND t.macroregion_label=r.label AND t.date=r.date
                    WHERE t.count IS DISTINCT FROM r.count""")
                preserved_differences = cursor.fetchone()[0]
                if options["apply"]:
                    cursor.execute("""INSERT INTO yd_wordstat_iplast_api
                        (phrase, macroregion_label, group_fingerprint, date, count, feature, category, date_add)
                        SELECT phrase, label, fingerprint, date, count, feature, category, CURRENT_TIMESTAMP
                        FROM ws_import_ready ON CONFLICT (phrase, macroregion_label, date) DO NOTHING""")
                    inserted = cursor.rowcount
                else:
                    # Do not consume permanent sequence IDs during a dry run.
                    cursor.execute("""SELECT count(*) FROM ws_import_ready r WHERE NOT EXISTS (
                        SELECT 1 FROM yd_wordstat_iplast_api t WHERE t.phrase=r.phrase
                        AND t.macroregion_label=r.label AND t.date=r.date)""")
                    inserted = cursor.fetchone()[0]
                if config != get_configuration():
                    raise CommandError("Wordstat references changed during import; nothing imported")
                result = dict(mode="apply" if options["apply"] else "dry_run_rollback", csv_rows=rows,
                              first_month=str(first), last_csv_month=str(last), through=str(through),
                              eligible_aggregates=eligible, inserted=inserted,
                              incomplete_phrase_groups=incomplete_pairs,
                              existing_different_counts_preserved=preserved_differences)
                if not options["apply"]:
                    transaction.set_rollback(True)
                self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
