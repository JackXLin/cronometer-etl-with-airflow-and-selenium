# 2026-03-20 - Garmin Historical Sync

## Summary

This update changes Garmin ingestion from a rolling 30-day snapshot into a historical CSV store with incremental refreshes. Garmin artifacts are now preserved between DAG runs, the first sync can backfill from a configured historical start date, and later syncs re-fetch a small overlap window before appending refreshed data back into the store.

## What Changed

### Historical Garmin storage

- Preserved `garmin_daily.csv`, `garmin_activities.csv`, and `garmin_heart_rate_detail.csv` during the DAG cleanup step so Garmin history survives reruns.
- Added `dags/garmin_sync_storage.py` to centralize Garmin sync configuration, existing-artifact loading, merge logic, weekly rollup recomputation, and atomic CSV writes.
- Added `dags/garmin_export_import.py` as a standalone historical-import CLI that can seed the mounted Garmin CSV store from exported Garmin JSON before live API syncs are used.
- Refactored `dags/fetch_garmin.py` to:
  - backfill from `GARMIN_HISTORICAL_START_DATE` on the first run,
  - resume from `last_stored_date - GARMIN_SYNC_OVERLAP_DAYS` on later runs,
  - support `GARMIN_FORCE_FULL_REFRESH=true` as a one-run rebuild option,
  - merge fresh Garmin rows with historical artifacts using stable deduplication keys,
  - recompute Garmin weekly rollups after the merged daily history is rebuilt.

### Artifact merge rules

- `garmin_daily.csv` deduplicates by `Date`, keeping the newest fetched row for overlapping dates.
- `garmin_activities.csv` deduplicates by `garmin_activity_id` when present, with a composite fallback key based on date, start time, name, type, and duration.
- `garmin_heart_rate_detail.csv` deduplicates by `Date` plus `garmin_hr_timestamp`.

### Configuration and docs

- Added `GARMIN_HISTORICAL_START_DATE`, `GARMIN_SYNC_OVERLAP_DAYS`, and `GARMIN_FORCE_FULL_REFRESH` to `.env.example` and `docker-compose.yaml`.
- Updated `readme.md` to explain first-run backfill, overlap-based incremental refreshes, the manual historical import CLI, and the operational cost of a full Garmin history sync.
- Clarified that `GARMIN_ENABLED=true` is still required for the DAG to merge Garmin data into `processed_data.csv` and the downstream report pages, even when the Garmin CSV store has already been pre-seeded manually.
- Clarified that `GARMIN_EMAIL` and `GARMIN_PASSWORD` are only required for the manual bootstrap flow or future token refreshes, while scheduled DAG runs restore the saved token session from `GARMINTOKENS`.

### Tests

- Added `tests/test_garmin_sync_storage.py` for historical start-date parsing, overlap-window resolution, merge and deduplication behavior, weekly rollup recomputation, and atomic CSV writes.
- Updated `tests/test_fetch_garmin.py` to cover initial backfill behavior and incremental merge behavior while preserving compatibility with monkeypatched `normalize_garmin_day()` test doubles.

## Operational Notes

- A full historical Garmin backfill may take significantly longer than a normal daily run because each day still queries multiple Garmin endpoint families.
- The manual `garmin_export_import.py` command is not scheduled by Airflow; it is intended for one-off historical seeding from exported Garmin JSON.
- After a manual historical seed, later DAG runs continue from the stored Garmin CSV artifacts using the normal overlap-based incremental refresh logic.
- After using `GARMIN_FORCE_FULL_REFRESH=true`, set it back to `false` so the next run returns to normal incremental sync behavior.
