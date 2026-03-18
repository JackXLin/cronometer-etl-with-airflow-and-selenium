# Changelog — Garmin Analytics Expansion & Airflow Log Streaming Fix

**Date:** 2026-03-18  
**Scope:** Expand Garmin ingestion and PDF analytics reporting, add supporting Garmin detail artifacts and tests, document the new behavior, and fix misleading Airflow task-log streaming failures caused by mismatched webserver log-signing secrets.

---

## Summary

Today’s work significantly expanded the Garmin side of the Cronometer Airflow pipeline.

The project moved beyond a basic Garmin daily-summary export and a single Garmin context page into a broader PDF-first Garmin analytics section with supporting helper modules, new normalized artifacts, expanded tests, and runtime observability improvements.

A separate runtime issue was also investigated in the Airflow environment: the `fetch_garmin_data` task appeared to be “stuck” in the UI, but worker logs showed the task was still progressing and eventually succeeded. The underlying issue was that Airflow’s log-serving request signatures were failing because the webserver and worker were not guaranteed to share the same `secret_key` after rebuild/restart cycles. A compose-level fix was added so all Airflow services use the same webserver secret.

Main outcomes:

- Garmin daily extraction was expanded with additional recovery, readiness, and activity-related fields.
- Supporting Garmin artifacts were added for activity sessions and detailed heart-rate rows.
- A new Garmin analytics helper module was added to centralize data preparation and table-building logic.
- A new Garmin analytics PDF module was added with eight dedicated report pages.
- The main report flow now renders a broader Garmin analytics section after the existing Garmin context page.
- Cleanup logic was updated so Garmin detail artifacts are removed before a fresh run.
- `pydantic` was added to project dependencies because Garmin activity/detail normalization now relies on structured validation models.
- New Garmin analytics tests were added and the focused Garmin/report suite was verified successfully.
- Airflow log streaming was fixed by pinning a shared `AIRFLOW__WEBSERVER__SECRET_KEY` across services.
- Garmin fetch logging was improved so long-running fetches now expose progress per date in Airflow logs.

---

## Runtime Investigation: Why `fetch_garmin_data` Looked Stuck

### Observed behavior

During a manual DAG run after rebuilding the Airflow image:

- `remove_files` completed
- `fetch_cronometer_data` completed
- `fetch_garmin_data` appeared to stall in the Airflow UI
- the Airflow log viewer showed a `403 FORBIDDEN`
- the worker log stream reported JWT signature failures while serving task logs

The UI-side error looked like:

- `Could not read served logs: Client error '403 FORBIDDEN'`
- `InvalidSignatureError: Signature verification failed`

### What the worker logs showed

Inspection of the live worker container logs showed that the Garmin task was not frozen permanently:

- `fetch_garmin_data` ran for roughly 459 seconds
- the Celery worker reported the task as succeeded
- `process_csv` began immediately afterward

### Root cause

The main user-visible problem was not Garmin task execution itself. The main issue was Airflow log serving:

- the webserver and worker were not reliably sharing the same Airflow log-signing secret
- this caused pre-signed task-log requests to fail validation
- the UI therefore could not stream the live task output even while the worker continued executing normally

### Fix applied

`docker-compose.yaml` was updated to define a shared secret across the Airflow services:

- `AIRFLOW__WEBSERVER__SECRET_KEY: ${AIRFLOW__WEBSERVER__SECRET_KEY:-airflow-local-dev-secret-key}`

This makes the log-serving behavior deterministic for local development and avoids the misleading 403 log-viewer failure after rebuilds.

### Additional observability improvement

`dags/fetch_garmin.py` now logs:

- fetch start and lookback window
- Garmin client restoration success
- per-day fetch progress (`n/N`)
- per-day elapsed time

This makes long Garmin runs much easier to observe and debug from Airflow logs.

---

## Garmin Extraction Expansion

### Primary file updated

- `dags/fetch_garmin.py`

### New daily fields and endpoint support

The Garmin fetch path was expanded so daily normalization can attempt and flatten additional Garmin endpoints where available.

The expanded daily record now supports fields including:

- `garmin_steps`
- `garmin_distance_m`
- `garmin_active_calories_kcal`
- `garmin_resting_hr_bpm`
- `garmin_sleep_seconds`
- `garmin_sleep_score`
- `garmin_avg_stress`
- `garmin_body_battery_max`
- `garmin_body_battery_min`
- `garmin_intensity_moderate_min`
- `garmin_intensity_vigorous_min`
- `garmin_activity_count`
- `garmin_floors_climbed`
- `garmin_respiration_avg`
- `garmin_spo2_avg`
- `garmin_hrv`
- `garmin_training_readiness`
- `garmin_training_status`
- activity-derived summary fields from normalized session rows
- heart-rate-detail-derived summary fields from intraday detail rows

### Supporting artifact outputs

The Garmin fetch step now writes three artifacts instead of only the flat daily CSV:

- `garmin_daily.csv`
- `garmin_activities.csv`
- `garmin_heart_rate_detail.csv`

These artifacts are written under `/opt/airflow/csvs` in the Airflow runtime.

### Rolling weekly Garmin fields

Weekly rollups were also added in the daily Garmin output so report-side analysis has ready-to-use aggregate context.

These include fields such as:

- `garmin_weekly_steps`
- `garmin_weekly_avg_stress`
- `garmin_weekly_intensity_min`

### Compatibility fix during test verification

While verifying the updated Garmin fetch path, a regression appeared in the existing daily CSV generation test.

Root cause:

- older tests patched `normalize_garmin_day()` directly
- the expanded fetch path had started to bypass that seam during internal helper orchestration

Fix applied:

- the runtime fetch flow now preserves backward compatibility when `normalize_garmin_day()` is monkeypatched
- sparse rows are also tolerated safely when weekly rollups are computed

This ensured both the new multi-artifact flow and the existing test contract continued to work.

---

## New Garmin Activity and Heart-Rate Normalization Support

### New module added

- `dags/garmin_activity_normalization.py`

This module was created to avoid overloading the daily normalization logic with activity-session and heart-rate-detail flattening.

Responsibilities added there include:

- activity-session row extraction
- intraday heart-rate-detail row extraction
- daily aggregation of activity session data
- daily aggregation of heart-rate detail data
- structured validation using `pydantic`

This keeps the Garmin extraction layer modular and makes the report/analytics stack easier to maintain.

---

## New Garmin Analytics Helper Layer

### New module added

- `dags/garmin_report_helpers.py`

A dedicated helper module was introduced to support the broader Garmin analytics PDF section.

This module centralizes:

- Garmin report input preparation
- derived Garmin helper columns
- lag-correlation analysis tables
- outlier diagnostic tables
- weekly Garmin summary tables
- activity contribution summaries
- detailed activity session tables
- recovery regime comparison tables
- monthly coverage tables

### Why this was needed

Without a shared helper layer, the new report pages would have pushed too much business logic into the renderer functions. This separation keeps rendering code focused on layout while analysis logic remains testable in isolation.

---

## Garmin PDF Analytics Expansion

### New module added

- `dags/visualisation_garmin_analytics.py`

### Main report wiring updated

- `dags/visualisation.py`

The report now renders a new Garmin analytics section after the existing Garmin context page whenever Garmin report data is present.

### New Garmin analytics pages added

The new PDF-first Garmin analytics section includes eight dedicated pages:

1. Garmin-adjusted TDEE context
2. Garmin lag heatmaps
3. Weight spike attribution
4. Recovery vs scale-noise scatter
5. Weekly energy balance dashboard
6. Activity-type contribution
7. Recovery regime comparison
8. Monthly calendar and coverage

### Page capabilities

These pages add report features such as:

- lag heatmaps comparing Garmin metrics against daily and 7-day trend-based weight change
- weight-spike attribution diagnostics using nutrition, hydration, recovery, and activity markers
- weekly energy/activity/recovery dashboards
- activity-type contribution summaries and detailed session tables
- regime comparisons for sleep, stress, HRV, and step-based buckets
- month-style heatmap views and Garmin coverage/missingness summaries

### Output strategy

This work continued the approved PDF-first reporting strategy rather than building the feature around standalone CSV exports. Supporting CSVs were still added for Garmin detail artifacts, but the core user-facing output remains the PDF analytics report.

---

## Cleanup and Runtime Artifact Management

### Updated file

- `dags/remove_old_file.py`

The cleanup task was expanded so it now removes the additional Garmin artifacts created during the fetch step:

- `garmin_activities.csv`
- `garmin_heart_rate_detail.csv`

This keeps reruns deterministic and avoids stale Garmin detail artifacts from contaminating later report generations.

---

## Dependency and Documentation Updates

### Updated dependency file

- `requirements.txt`

Added:

- `pydantic==2.12.5`

### Updated documentation

- `readme.md`

The README was extended to document:

- the broader Garmin daily metric set
- the new Garmin detail artifacts
- the `pydantic` dependency
- the expanded Garmin PDF analytics section
- the continued manual bootstrap token model and non-interactive token reuse

---

## Test Coverage Added and Verification Performed

### New tests added

- `tests/test_garmin_report_helpers.py`
- `tests/test_visualisation_garmin_analytics.py`

### Existing tests exercised

Focused Garmin/report verification included:

- `tests/test_fetch_garmin.py`
- `tests/test_visualisation_garmin.py`
- `tests/test_visualisation_pages.py`
- `tests/test_visualisation_helpers_v2.py`
- `tests/test_process_csv.py`

### Targeted test results

The focused suite passed successfully.

Verified runs included:

```bash
python -m pytest tests/test_garmin_report_helpers.py tests/test_visualisation_garmin_analytics.py tests/test_fetch_garmin.py tests/test_visualisation_garmin.py tests/test_visualisation_pages.py tests/test_visualisation_helpers_v2.py tests/test_process_csv.py -q
```

Result:

- `56 passed`

A later focused Garmin fetch verification also passed:

```bash
python -m pytest tests/test_fetch_garmin.py -q
```

Result:

- `6 passed`

### Notes from verification

The Garmin analytics rendering tests surfaced Matplotlib layout warnings caused by a mix of:

- tables
- colorbars
- twin axes
- `tight_layout()` usage

These are not failing the tests, but they were recorded as follow-up cleanup work.

---

## Files Added or Modified Today

### Added

- `changelog/2026-03-18-garmin-analytics-expansion-and-airflow-log-fix.md`
- `dags/garmin_activity_normalization.py`
- `dags/garmin_report_helpers.py`
- `dags/visualisation_garmin_analytics.py`
- `tests/test_garmin_report_helpers.py`
- `tests/test_visualisation_garmin_analytics.py`

### Modified

- `docker-compose.yaml`
- `requirements.txt`
- `readme.md`
- `TASK.md`
- `TODO.md`
- `dags/fetch_garmin.py`
- `dags/remove_old_file.py`
- `dags/visualisation.py`

---

## Tracker Updates

Tracker files were updated to reflect the work completed today.

### Completed

- expanded Garmin Connect extraction and PDF reporting to support advanced activity, recovery, lag analysis, and weekly analytics

### Discovered during work

- reduce Matplotlib layout warnings on Garmin analytics pages that use tables, colorbars, and twin axes
- configure pytest to skip runtime folders such as `logs/` during Windows discovery

---

## Operational Notes

### What to expect on the next Airflow run

After restarting the Airflow services so all containers pick up the shared webserver secret:

- the Airflow UI should be able to stream live task logs without the misleading `403 FORBIDDEN`
- Garmin fetch logs should now show visible per-day progress
- long Garmin runs should be easier to diagnose if Garmin Connect is slow or rate-limiting

### Garmin runtime characteristic

The expanded Garmin fetch is now heavier than the earlier implementation because multiple endpoint families are queried per day. With a 30-day lookback, multi-minute runtimes are expected.

If faster debugging is needed, temporarily reducing `GARMIN_LOOKBACK_DAYS` remains the simplest operational lever.

---

## Final Status

### Completed today

- Garmin extraction expanded beyond the earlier daily summary subset
- Garmin activity-session and heart-rate-detail normalization introduced
- Garmin analytics helper layer added
- Garmin PDF analytics section expanded with eight new pages
- cleanup updated for new Garmin artifacts
- README and dependency metadata updated
- focused Garmin/report tests added and verified
- Airflow worker/webserver log-streaming issue investigated and fixed in compose configuration
- Garmin task runtime logging improved for long-running fetches
- today’s changelog entry written

### Result

The project now has a much broader Garmin analytics implementation across ingestion, normalization, artifact generation, PDF reporting, runtime observability, and local Airflow operations. The pipeline remains aligned with the manual token-bootstrap model, while the PDF report now presents substantially richer Garmin activity, recovery, lag, and coverage analysis.
