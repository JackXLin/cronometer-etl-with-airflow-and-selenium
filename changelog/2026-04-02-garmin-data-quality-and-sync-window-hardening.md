# 2026-04-02 - Garmin Data Quality and Sync Window Hardening

## Summary

This update improves Garmin data quality across both the reporting layer and the ingestion pipeline. The TDEE dashboard was narrowed to a 6-month view for better readability, recent Garmin lag heatmaps were adjusted so sparse recent HRV still renders, Garmin HRV extraction was hardened for newer nested payload shapes, and the daily sync was extended with a bounded historical gap-repair pass. The gap repair now covers a broader set of Garmin daily metrics and the scheduled daily sync no longer fetches the current in-progress day, preventing partial-day Garmin rows from being written into the historical CSV store.

## What Changed

### Report-side readability and sparse-HRV handling

- Updated `dags/visualisation_pages.py` so the `Intake vs TDEE Over Time` chart on the TDEE dashboard only shows the last 6 months of data instead of the full available history.
- Updated the same TDEE panel formatting so the narrower time window remains readable in PDF output.
- Updated `dags/garmin_report_helpers.py` so `build_lag_correlation_result()` accepts a configurable `min_samples` threshold instead of always requiring the previous hard-coded overlap count.
- Updated `dags/visualisation_garmin_analytics.py` so the recent 30-day Garmin lag heatmaps use `min_samples=5`, allowing sparse recent HRV observations to render instead of dropping the metric entirely.

### Garmin HRV extraction hardening

- Updated `dags/fetch_garmin.py` to harden HRV extraction for newer Garmin payload shapes, including nested and list-based summary formats.
- Added `_extract_hrv_value()` so `garmin_hrv` can be resolved from more than one Garmin payload structure rather than assuming a single flat field layout.
- Preserved compatibility with the older payload shapes already handled by the pipeline.

### Bounded historical gap detection and backfill

- Added `dags/garmin_gap_backfill.py` to detect likely historical gaps in `garmin_daily.csv` that merit selective re-fetching.
- Integrated the gap detector into `dags/fetch_garmin.py` so normal incremental syncs now fetch:
  - the standard overlap-refresh window, and
  - a bounded set of older detected gap dates outside that window.
- Kept the gap-repair logic intentionally conservative so it does not turn a normal daily run into a full historical rebuild.
- Limited the repair scope using dedicated configuration values:
  - `GARMIN_GAP_SCAN_DAYS`
  - `GARMIN_GAP_BACKFILL_MAX_DATES`
  - `GARMIN_GAP_MIN_MISSING_METRICS`

### Broader Garmin metric repair coverage

- Expanded gap detection beyond HRV-focused holes so historical backfill can also repair interior gaps across a broader set of normally present Garmin daily metrics.
- Included fields such as steps, distance, active calories, resting heart rate, sleep metrics, stress, body battery, respiration, SpO2, training readiness, training status, heart-rate summary fields, and related daily activity-count metrics.
- Kept naturally sparse session-only fields out of the single-field priority trigger list so days without a recorded workout session do not create false-positive backfill requests.
- Preserved multi-metric gap detection so dates with several missing Garmin fields at once are still treated as likely repair candidates.

### Excluding the current in-progress day from daily syncs

- Updated `dags/fetch_garmin.py` so scheduled Garmin daily syncs now end at `today - 1 day` instead of including the current calendar day.
- This prevents partial-day Garmin values from being written into `garmin_daily.csv` while the day is still in progress.
- Historical backfill dates remain eligible for re-fetching; the change only affects the inclusive upper bound of the normal daily sync window.

### Tests and project tracking

- Updated `tests/test_visualisation_pages.py` to cover the 6-month TDEE dashboard window.
- Updated `tests/test_garmin_report_helpers.py` to cover sparse recent HRV rendering with a reduced minimum sample threshold.
- Updated `tests/test_fetch_garmin.py` to cover:
  - nested/list-based HRV payload extraction,
  - incremental overlap-window merges,
  - bounded historical gap-date unioning into the fetch list, and
  - exclusion of the current in-progress day from scheduled sync windows.
- Added `tests/test_garmin_gap_backfill.py` for bounded historical gap detection, broader multi-metric repair coverage, and conservative exclusions for session-only sparse fields.
- Verified focused Garmin tests after the sync-window hardening and gap-backfill work with:
  - `pytest tests/test_fetch_garmin.py tests/test_garmin_gap_backfill.py tests/test_garmin_sync_storage.py -q`
- Updated `TASK.md` and `TODO.md` to record completion of the 2026-04-02 Garmin data-quality work.

## Operational Notes

- Normal Garmin daily syncs now fetch only completed days. If the DAG runs on `2026-04-02`, the normal upper bound of the sync window is `2026-04-01`.
- Historical Garmin repairs remain bounded and selective; they are intended to fix incomplete historical rows without forcing a full historical refresh on every DAG run.
- If additional historical gaps remain after normal runs, the bounded gap-backfill settings can be widened by increasing the scan window or the maximum number of repaired dates per run.
- The mounted Garmin artifacts still live in the CSV output location used by the pipeline, so repeated daily runs will continue refining the same persisted Garmin history rather than rebuilding it from scratch.
