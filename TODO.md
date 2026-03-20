# TODO

## In Progress (2026-03-20)


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

- [ ] Configure pytest to skip non-test runtime folders (e.g. `logs/`) in this workspace on Windows.
- [ ] Identify a Garmin export source for historical intraday heart-rate detail seeding; the current JSON importer writes an empty `garmin_heart_rate_detail.csv`.
- [x] Reduce matplotlib layout warnings on Garmin analytics pages that use tables, colorbars, and twin axes.
