# TODO

## In Progress (2026-04-02)





## Completed (2026-04-02)

- [x] Limit the TDEE intake-vs-TDEE chart to the last 6 months and investigate/fix missing HRV in the recent 30-day Garmin lag heatmaps.
- [x] Add a bounded Garmin gap-detection and backfill mechanism for missing historical daily metrics.
- [x] Expand bounded Garmin gap backfill to cover additional daily Garmin fields beyond HRV-focused gaps.
- [x] Exclude the current in-progress day from Garmin daily sync windows so only completed days are fetched.
- [x] Write a detailed changelog entry for the 2026-04-02 Garmin data-quality and sync-window hardening work.

## In Progress (2026-03-23)


## In Progress (2026-03-20)


## Completed (2026-03-23)

- [x] Improve Garmin analytics visual clarity and layout for the TDEE context, activity regimes, lag heatmaps, recovery scatter, activity-type contribution, and coverage table.
- [x] Write a changelog entry for the 2026-03-23 Garmin visualization refinement work.

## Completed (2026-03-20)

- [x] Implement Garmin historical backfill and incremental sync storage.
- [x] Inspect Garmin FIT export files for usefulness in historical import.
- [x] Harden Cronometer export download detection and canonical CSV output handling.
- [x] Complete Garmin export import workflow.
- [x] Review Garmin export import run mode and whether it is manual or scheduled.
- [x] Review and update documentation and changelog for Garmin historical import, env guidance, and daily sync behavior.

## In Progress (2026-03-18)


## Completed (2026-03-18)

- [x] Expand Garmin Connect extraction and PDF reporting to support advanced activity, recovery, lag-analysis, and weekly analytics.
- [x] Write a detailed changelog entry for the 2026-03-18 Garmin analytics expansion and Airflow log-streaming fix.
- [x] Refactor Garmin analytics PDF layouts to prevent overlapping charts/tables and improve report legibility.

## Completed (2026-03-16)

- [x] Review Garmin Connect integration status and complete remaining implementation without editing `.env`.
- [x] Run manual one-time Garmin token bootstrap in the Airflow environment.

## In Progress (2026-03-16)


## Completed (2026-03-01)

- [x] Adjust TDEE dashboard panel spacing and text sizing to prevent overlap/clipping.
- [x] Add regression tests for `page_tdee_dashboard` layout and fallback behavior.

## Discovered During Work

- [ ] Tune Garmin bounded gap-backfill settings if historical repairs need a wider scan window or more dates per sync run.
- [ ] Re-run Garmin daily sync and confirm recent `garmin_hrv` values repopulate after the HRV payload extraction hardening; if not, inspect post-2026-03-17 Garmin API coverage.
- [ ] Configure pytest to skip non-test runtime folders (e.g. `logs/`) in this workspace on Windows.
- [ ] Identify a Garmin export source for historical intraday heart-rate detail seeding; the current JSON importer writes an empty `garmin_heart_rate_detail.csv`.
- [x] Reduce matplotlib layout warnings on Garmin analytics pages that use tables, colorbars, and twin axes.
