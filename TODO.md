# TODO

## In Progress (2026-03-18)


## Completed (2026-03-18)

- [x] Expand Garmin Connect extraction and PDF reporting to support advanced activity, recovery, lag-analysis, and weekly analytics.
- [x] Write a detailed changelog entry for the 2026-03-18 Garmin analytics expansion and Airflow log-streaming fix.

## Completed (2026-03-16)

- [x] Review Garmin Connect integration status and complete remaining implementation without editing `.env`.
- [x] Run manual one-time Garmin token bootstrap in the Airflow environment.

## In Progress (2026-03-16)


## Completed (2026-03-01)

- [x] Adjust TDEE dashboard panel spacing and text sizing to prevent overlap/clipping.
- [x] Add regression tests for `page_tdee_dashboard` layout and fallback behavior.

## Discovered During Work

- [ ] Configure pytest to skip non-test runtime folders (e.g. `logs/`) in this workspace on Windows.
- [ ] Reduce matplotlib layout warnings on Garmin analytics pages that use tables, colorbars, and twin axes.
