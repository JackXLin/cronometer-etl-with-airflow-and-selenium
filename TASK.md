# TASK

## 2026-03-23

- [x] Improve Garmin analytics visual clarity and layout for TDEE context, activity regimes, lag heatmaps, recovery scatter, activity-type contribution, and coverage tables.
- [x] Write a changelog entry for the 2026-03-23 Garmin visualization refinement work.

## 2026-03-20

- [x] Implement Garmin historical backfill and incremental sync storage.
- [x] Inspect Garmin FIT export files for usefulness in historical import.
- [x] Harden Cronometer export download detection and canonical CSV output handling.
- [x] Review Garmin export import run mode and whether it is manual or scheduled.
- [x] Review and update documentation and changelog for Garmin historical import, env guidance, and daily sync behavior.

## 2026-03-18

- [x] Expand Garmin Connect extraction and PDF reporting to support advanced activity, recovery, lag-analysis, and weekly analytics.
- [x] Write a detailed changelog entry for the 2026-03-18 Garmin analytics expansion and Airflow log-streaming fix.
- [x] Refactor Garmin analytics PDF layouts to prevent overlapping charts/tables and improve report legibility.

## 2026-03-01

- [x] Fix Page 2 TDEE dashboard layout for:
  - TDEE estimate by method chart
  - TDEE estimation summary block
  - Intake vs TDEE over-time chart

## 2026-03-16

- [x] Review Garmin Connect integration status and complete remaining implementation without editing `.env`.
- [x] Run manual one-time Garmin token bootstrap in the Airflow environment.
- [x] Write a detailed changelog entry for Garmin integration and bootstrap work completed on 2026-03-16.
- [x] Expand Garmin daily extraction to include additional supported metrics and add Garmin-driven report visualisations.

## Discovered During Work

- [ ] Add pytest collection ignore rules for `logs/scheduler/latest` on Windows (WinError 1920 during full test discovery).
- [ ] Identify a Garmin export source for historical intraday heart-rate detail seeding; the current JSON importer writes an empty `garmin_heart_rate_detail.csv`.
- [x] Reduce matplotlib layout warnings on Garmin analytics pages that use tables, colorbars, and twin axes.
