# TASK

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
