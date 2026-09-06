# Wordstat v2: IPLAST aggregates

The API pipeline uses Yandex Search API REST v2. The `region` source now sends
one GetDynamics request per phrase and IPLAST group, with the group's complete
region list. The seven names come from `yd_wordstat_ref_iplast` and must match
the dashboard: ЕКАТЕРИНБУРГ, КРАСНОДАР, МОСКВА, НИЖНЕКАМСК, НОВОСИБИРСК, СПБ, СНГ.
All and device requests retain their existing scope.

For 1,433 phrases, three devices and seven groups: 15,763 GetDynamics calls
per complete pass before retries/skips (formerly 140,434 for 94 individual
regions). At a quota of 100/hour, budget approximately 158 hours (6.6 days),
plus service delays and retries. The actual quota belongs to the Cloud folder;
other applications sharing it can also consume requests.

## Storage and restart behavior

- `yd_wordstat_iplast_api` stores API aggregates and supplies the regional
  dashboard columns directly. The former per-region storage and intermediate
  macroregion table are removed by migration 0065.
- `yd_wordstat_api_checkpoint` records each successfully committed combination
  and interval. Only a complete monthly response can replace its interval.
  Empty/malformed/incomplete responses fail without deleting statistics.
- Group membership fingerprints invalidate checkpoints and trigger a history
  reload if a group's region set changes. No synthetic region IDs are used.
- Initial history starts in January 2018, as before. Subsequent runs reload
  the last 12 months. The probe must confirm that the requested historical
  range is available; dates are not silently shortened and missing months
  are not filled with zero.
- The target month is fixed at the beginning of each invocation. A restart
  in a different calendar month targets the new previous month.
- PostgreSQL stores the shared sliding second/hour quota and server cooldowns.
  Retries consume quota reservations too. The quota is keyed by folder ID,
  or by a hash of the API key if folder ID is absent. Configure folder ID when
  multiple keys use the same folder. External clients are accounted for through
  HTTP 429 handling, not through local reservations.
- A PostgreSQL advisory lock prevents overlapping API pipelines. The loader
  processes requests sequentially and fails after bounded retries for temporary
  errors; 400/401/403 fail immediately. Restart the command after resolving errors.
- Publication validates all expected combinations and their saved intervals,
  then rebuilds the existing dashboard schema directly from the IPLAST table.
  Individual regions are not added to the aggregates again.
- Legacy statistics CSV imports, their HTTP endpoints, the stored region-tree
  reference and the v1 compatibility client are removed. Excel imports for
  phrases, devices and the IPLAST mapping remain, as does dashboard Excel export.
- The active models are PhraseRef, DeviceRef, IplastRegionRef, AllRaw, DeviceRaw,
  IplastRaw, ApiCheckpoint, ApiQuota and For (all with the YdWordstat prefix).

## Server rollout (performed by the operator)

No server commands or paid Wordstat calls were executed while developing this
change. The following commands are instructions, not a record of execution.

1. Stop/finish any existing Wordstat loader before replacing its code. Pull
   `dev-current` in `/opt/analytics-platform` using the established deployment
   account. Leave `YD_WORDSTAT_V2_LOAD_ENABLED=false` while checking the migration.
2. Inspect the migration plan:

   ```sh
   docker exec analytics-django python manage.py migrate --plan
   ```

   Migration 0063 adds the three tables above. Migration 0064 widens the used
   counters to bigint and the final average's decimal precision. Existing rows
   are preserved. On PostgreSQL widening integer columns can rewrite and lock
   large tables: apply this in a maintenance window with the usual DB backup.
   ClickHouse counters are already Int64; its schema is unchanged.

   Migration 0065 permanently drops these tables and their local contents:
   `yd_wordstat_region`, `yd_wordstat_ref_region`, `yd_wordstat_macroregion_label`.
   The operator has confirmed that historical data exists on another server.
   That other server is not contacted or modified by this migration. Only the
   database where `migrate` is run is affected. Historical migrations 0025/0064
   remain in Git so existing installations can upgrade normally; reversing
   DeleteModel recreates empty tables, not the deleted records.

   ```sh
   docker exec analytics-django python manage.py migrate
   docker exec analytics-django python manage.py check
   docker exec analytics-django python manage.py load_yd_wordstat_api --plan
   ```

   The plan only reads PostgreSQL references/checkpoints/statistics. It makes
   no API calls, reserves no quota and sends no notifications. It requires
   migration 0063. Check that it reports 1,433 phrases, 3 devices, 7 groups and
   15,763 full-pass requests; group sizes must match the established mapping.

3. Configure the root `.env` used by the Django container:

   ```dotenv
   YD_WORDSTAT_API_KEY=<service-account API key>
   YD_WORDSTAT_FOLDER_ID=<Yandex Cloud folder ID>
   YD_WORDSTAT_API_BASE_URL=https://searchapi.api.cloud.yandex.net/v2/wordstat
   YD_WORDSTAT_REQUESTS_PER_SECOND=10
   YD_WORDSTAT_REQUESTS_PER_HOUR=100
   YD_WORDSTAT_API_MAX_ATTEMPTS=5
   YD_WORDSTAT_V2_LOAD_ENABLED=false
   ```

   Recreate the Django Compose service to pick up changed environment values
   (`docker compose up -d --no-deps --force-recreate django`). A plain container
   restart does not reread `env_file`. Never print the full Compose configuration
   or `.env` to share diagnostics, as they contain credentials.

4. Run the existing read-only tree diagnostic:

   ```sh
   docker exec analytics-django python manage.py inspect_yd_wordstat_regions_v2
   ```

5. Explicit paid probe, using an actual phrase from the reference:

   ```sh
   docker exec analytics-django python manage.py probe_yd_wordstat_v2 \
     --phrase '<actual phrase>' --group 'КРАСНОДАР' \
     --from-date 2026-08-01 --to-date 2026-08-31
   ```

   This requests one dynamics series (retries can add requests). It saves quota
   accounting only, not statistics or checkpoints, and does not publish anything.
   Compare the output with the old regional sums held on the other server.
   There is no automatic lookup of that server or dependency on the removed
   regional tables. Differences must be investigated, including acquisition
   dates: Wordstat can revise historical counts. Also probe the full
   January-2018-to-previous-month interval and samples from other groups/devices
   before the first full run.

6. After reviewing probes, set `YD_WORDSTAT_V2_LOAD_ENABLED=true` and recreate
   the Django container to apply it. The full command loads and publishes:

   ```sh
   docker exec analytics-django python manage.py load_yd_wordstat_api
   ```

   For downloading only groups without publishing:

   ```sh
   docker exec analytics-django python manage.py load_yd_wordstat_api --source region
   ```

   Keep a long-lived terminal/session for manual runs. Airflow's monthly DAG
   still has a 10-day timeout and no automatic retries. Its external-load flag
   now actually excludes the load task when disabled. Do not run Airflow and
   manual loading concurrently. HTTP load endpoints execute synchronously;
   use the management command or Airflow for long loads.

## Local verification

From `services/backend`, with Django and requests installed:

```sh
python -m unittest tests.test_wordstat_v2 -v
python manage.py check --settings=tests.wordstat_settings
python manage.py makemigrations --check --dry-run --settings=tests.wordstat_settings
```

Tests force isolated in-memory SQLite, mock API calls, exercise migration data
preservation of active data, removal of obsolete tables, retries, quota
accounting, membership changes, resumability and rollback on failures. PostgreSQL lock/concurrency behavior, full PostgreSQL SQL
rebuild, ClickHouse publication and real API responses require server validation.

Official contracts:
- https://aistudio.yandex.ru/ru/docs/search-api/api-ref/Wordstat/getDynamics
- https://aistudio.yandex.ru/ru/docs/search-api/api-ref/Wordstat/getRegionsTree
- https://aistudio.yandex.ru/ru/docs/search-api/concepts/limits
