# Changelog — Garmin Integration Completion & Bootstrap Stabilisation

**Date:** 2026-03-16  
**Scope:** Finalise Garmin Connect integration for the Airflow ETL pipeline, add missing report-side Garmin context, stabilise the manual token bootstrap flow, and verify non-interactive token reuse.

---

## Summary

Today’s work completed the Garmin Connect integration across configuration, pipeline wiring, reporting context, tests, and runtime bootstrap behavior.

The main outcomes were:

- Garmin configuration support was completed in project docs and container environment passthrough.
- Garmin data ingestion remained wired into the Airflow DAG without requiring `.env` edits from code.
- Weekly report summaries were enhanced to show optional Garmin context when Garmin columns are present.
- Garmin daily normalization was later expanded so `garmin_daily.csv` includes body battery and activity-count fields in addition to the original daily metrics.
- Garmin reporting was later extended with a dedicated Garmin activity/recovery context page and wider weekly-summary support.
- The manual one-time Garmin bootstrap flow was debugged and fixed so tokens can be created reliably in the Airflow environment.
- Saved Garmin token files were successfully created and verified for reuse on later DAG runs.

---

## Configuration and Documentation Updates

### `.env.example`
Added optional Garmin configuration examples:

- `GARMIN_ENABLED`
- `GARMIN_EMAIL`
- `GARMIN_PASSWORD`
- `GARMIN_LOOKBACK_DAYS`
- `GARMINTOKENS`

This makes the expected Garmin configuration explicit without editing the user’s real `.env` file.

### `docker-compose.yaml`
Added Garmin environment variable passthrough for the Airflow services:

- `GARMIN_ENABLED`
- `GARMIN_EMAIL`
- `GARMIN_PASSWORD`
- `GARMIN_LOOKBACK_DAYS`
- `GARMINTOKENS`

This ensures Airflow containers can access Garmin settings during DAG runs and during the bootstrap helper run.

### `readme.md`
Expanded Garmin-related documentation with:

- optional Garmin integration setup instructions
- explanation of the manual one-time token bootstrap model
- bootstrap command documentation
- reminder that scheduled DAG runs reuse the saved Garmin session non-interactively
- DAG step documentation describing optional Garmin fetch behavior

---

## Pipeline and Integration Status

The Garmin ingestion path was reviewed and confirmed across the following modules:

- `dags/garmin_client.py`
- `dags/garmin_auth_bootstrap.py`
- `dags/fetch_garmin.py`
- `dags/csv_processing_dag.py`
- `dags/process_csv.py`
- `dags/remove_old_file.py`

### Confirmed behavior

- The DAG supports optional Garmin ingestion when `GARMIN_ENABLED=true`.
- Garmin daily data is fetched into a CSV output path.
- Garmin metrics are merged into processed output when the Garmin CSV is present.
- The file cleanup task removes prior Garmin output before new runs.
- The runtime fetch path uses the persisted token store rather than re-running interactive authentication.

Note: The cleanup behavior above was later superseded by the 2026-03-20 historical-sync update, which preserves Garmin artifacts between runs so the mounted CSV directory can act as the long-lived Garmin history store.

### Follow-up extraction fix after report review

During follow-up review against a real `garmin_daily.csv` sample, it became clear that the CSV header still stopped at:

- `garmin_steps`
- `garmin_distance_m`
- `garmin_active_calories_kcal`
- `garmin_resting_hr_bpm`
- `garmin_sleep_seconds`
- `garmin_sleep_score`
- `garmin_avg_stress`
- `garmin_intensity_moderate_min`
- `garmin_intensity_vigorous_min`

This showed that the extraction path was not dynamically omitting data at write time; instead, `normalize_garmin_day()` was only flattening that original subset of daily metrics.

### Root cause

- the Garmin fetch path in `dags/fetch_garmin.py` only wrote a fixed 9-field normalization schema
- optional Garmin endpoints for body battery and activity lists were not yet included in the daily row builder

### Fix applied

Normalization support was split into a dedicated helper module:

- `dags/garmin_daily_normalization.py`

The Garmin daily export now attempts the additional daily endpoints and normalizes:

- `garmin_body_battery_max`
- `garmin_body_battery_min`
- `garmin_activity_count`

The resulting intended Garmin daily schema now includes:

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

---

## Report / Visualisation Enhancement

### `dags/visualisation_helpers_v2.py`
The weekly summary table was extended to include optional Garmin context when Garmin columns exist in the processed dataset.

New optional summary columns:

- `Steps`
- `Sleep h`
- `Stress`

These are derived from:

- `garmin_steps`
- `garmin_sleep_seconds`
- `garmin_avg_stress`

### Why this was added

Earlier review showed that Garmin ingestion had been added to the ETL pipeline, but the report still did not surface Garmin metrics in a user-facing summary. The weekly summary table now closes that gap while remaining optional and backward-compatible for runs without Garmin data.

### Follow-up reporting enhancement after review

The initial report-side Garmin improvement only surfaced a small amount of Garmin context inside the weekly summary table. Follow-up review showed this did not satisfy the planned Phase 6 reporting goal of using Garmin as a visible contextual layer in the PDF output.

Additional reporting work completed:

- added `dags/visualisation_garmin.py`
- wired an optional Garmin page into `dags/visualisation.py`
- expanded weekly summary support to include Garmin activity minutes and activity counts
- adjusted weekly table sizing logic in `dags/visualisation_weekly.py` so wider Garmin summaries remain readable

### New Garmin report page

The dedicated Garmin page now provides:

- weekly activity summary
- sleep and stress trend panels
- body battery and resting heart-rate context
- simple adherence insights such as sleep vs calorie adherence and stress vs over-target days

---

## Test Coverage Added and Updated

### New Garmin test files

#### `tests/test_garmin_client.py`
Added coverage for:

- Garmin token store path resolution
- token-based client restoration
- missing token store bootstrap-required failure
- manual bootstrap flow with MFA handling
- bootstrap credential validation
- empty token-store bootstrap behavior
- profile hydration before bootstrap verification

#### `tests/test_fetch_garmin.py`
Added coverage for:

- Garmin date range construction
- Garmin payload normalization
- Garmin CSV generation behavior
- expected output handling for Garmin daily data fetches

#### `tests/test_process_csv.py`
Added coverage for:

- optional Garmin CSV loading
- Garmin/Cronometer merge behavior
- handling of missing Garmin files
- preservation of expected processed output structure

### Updated visualisation test coverage

#### `tests/test_visualisation_helpers_v2.py`
Extended coverage so the weekly summary helper now verifies that Garmin-derived columns appear when Garmin metrics are present.

#### `tests/test_visualisation_garmin.py`
Added coverage for:

- Garmin report-data detection
- Garmin page rendering with full Garmin context
- rendering with partial Garmin context
- failure behavior when no Garmin report metrics are available

### Test verification

Targeted pytest verification was run successfully for:

- `tests/test_visualisation_helpers_v2.py`
- `tests/test_garmin_client.py`
- `tests/test_fetch_garmin.py`
- `tests/test_process_csv.py`
- `tests/test_visualisation_garmin.py`

A targeted Garmin auth test rerun also passed after bootstrap fixes:

- `tests/test_garmin_client.py`

---

## Bootstrap Debugging and Fixes

The most substantial runtime work today involved stabilising the manual one-time Garmin bootstrap helper.

### Initial failure: empty token directory caused restore attempt

**Observed error:**

- `FileNotFoundError` for `/opt/airflow/config/garmin_tokens/oauth1_token.json`

**Root cause:**

- The bootstrap helper created the token directory before login.
- The `garminconnect` library interpreted the existing token directory as a restore target.
- Because the directory was empty, the library attempted to load token files that did not exist.

**Fix applied in `dags/garmin_client.py`:**

- Added `_prepare_bootstrap_tokenstore()`
- ensured the parent directory exists
- removed an empty existing token directory before interactive bootstrap login

### Second failure: `GARMINTOKENS` forced restore inside library login

**Observed behavior:**

- `Garmin.login()` still tried token restore even after the helper-side directory fix

**Root cause:**

- The `garminconnect` library reads `GARMINTOKENS` internally during `login()`.
- Because `GARMINTOKENS` was set in the environment, the library still attempted token restore instead of pure credential login.

**Fix applied in `dags/garmin_client.py`:**

- temporarily removed `GARMINTOKENS` from `os.environ`
- called `client.login(tokenstore=None)` during bootstrap
- restored the original environment variable afterward
- dumped fresh tokens to the configured token store after successful login

### Third failure: verification called Garmin summary endpoint with `/daily/None`

**Observed error:**

- Garmin summary verification attempted `/usersummary-service/usersummary/daily/None`
- this returned `403 Forbidden`

**Root cause:**

- post-login verification relied on `client.display_name`
- after the login / resume flow, `display_name` was not always populated on the client object

**Fix applied in `dags/garmin_client.py`:**

- added `_ensure_profile_loaded()`
- hydrates the user profile from the Garmin session when `display_name` is missing
- sets `display_name` and `full_name` before calling `get_user_summary()`

### Regression tests added for bootstrap fixes

Bootstrap regressions are now covered for:

- empty token-store handling
- no token restore during bootstrap login
- profile hydration before verification

---

## Successful Bootstrap Outcome

After the bootstrap fixes, the manual Garmin bootstrap completed successfully.

### Verified runtime result

The bootstrap helper returned:

- `tokenstore: /opt/airflow/config/garmin_tokens`
- `verified_date: 2026-03-16`
- a valid Garmin daily summary payload key set

### Token files confirmed

The token store now contains:

- `oauth1_token.json`
- `oauth2_token.json`

This confirms the Garmin session has been persisted successfully for later DAG reuse.

---

## Operational Outcome

### What happens on future DAG runs

No further code change is required for token reuse.

The current implementation already supports:

- loading the saved Garmin token files from `GARMINTOKENS`
- reusing the Garmin session non-interactively
- avoiding repeat manual Garmin login during ordinary DAG execution

### Expected next operational steps

- ensure `GARMIN_LOOKBACK_DAYS` is present in `.env`
- recreate the relevant Airflow runtime services so they pick up the latest environment values
- trigger the DAG
- verify Garmin data lands in `garmin_daily.csv` and merged processed output

---

## Files Added or Modified Today

### Added

- `changelog/2026-03-16-garmin-integration-and-bootstrap.md`
- `dags/garmin_daily_normalization.py`
- `dags/visualisation_garmin.py`
- `tests/test_garmin_client.py`
- `tests/test_fetch_garmin.py`
- `tests/test_process_csv.py`
- `tests/test_visualisation_garmin.py`

### Modified

- `.env.example`
- `docker-compose.yaml`
- `readme.md`
- `TASK.md`
- `TODO.md`
- `dags/garmin_client.py`
- `dags/fetch_garmin.py`
- `dags/visualisation.py`
- `dags/visualisation_weekly.py`
- `dags/visualisation_helpers_v2.py`
- `tests/test_fetch_garmin.py`
- `tests/test_visualisation_helpers_v2.py`

---

## Tracker Notes

Today’s tracker updates covered:

- Garmin integration review and completion
- manual one-time Garmin bootstrap completion
- changelog documentation for today’s work

A pre-existing discovered task remains open:

- configure pytest to skip runtime folders such as `logs/` during Windows test discovery

---

## Final Status

### Completed today

- Garmin integration reviewed and completed
- Garmin environment examples and container passthrough documented
- Garmin report-side summary context added
- Garmin daily export schema expanded to include body battery and activity count metrics
- Garmin report output expanded with a dedicated Garmin context page
- Garmin test coverage added and extended
- Garmin bootstrap helper debugged and stabilised
- manual bootstrap run completed successfully
- persistent token files created and verified
- changelog entry written for today’s work

### Result

The project is now set up so that Garmin authentication is bootstrapped once manually, and subsequent Airflow DAG runs can reuse the saved Garmin token JSON files without another interactive login.
