# 2026-03-23 - Garmin Visualization Refinements

## Summary

This update improves the clarity and readability of the Garmin analytics PDF section. Several charts were reworked to reduce overlapping elements, color legends were moved out of the plotting area, the lag analysis page now includes a recent 30-day view alongside the all-time view, and the compressed coverage table was split onto its own full page.

## What Changed

### Garmin-adjusted TDEE and activity context

- Refactored `page_garmin_adjusted_tdee_panel()` in `dags/visualisation_garmin_analytics.py` from a more crowded dual-axis layout into three stacked panels.
- Separated intake-vs-TDEE context from Garmin activity context so the main calorie comparison is easier to read.
- Added clearer fill regions between intake and TDEE to show surplus/deficit context without overwhelming the chart.
- Reworked the activity-regime presentation so the smoothed weight trend is shown against clearer high-activity and low-activity background regimes.

### Lag heatmaps and recovery scatter layout

- Updated `page_garmin_lag_heatmap()` in `dags/visualisation_garmin_analytics.py` to move the colorbar into a dedicated side axis instead of overlaying the heatmap area.
- Expanded the lag page from the original all-time view into four heatmaps:
  - all-time lag vs daily weight change,
  - all-time lag vs 7-day trend weight change,
  - recent 30-day lag vs daily weight change,
  - recent 30-day lag vs 7-day trend weight change.
- Extended the lag summary table so it compares all-time and recent-30-day best lag/correlation results side by side.
- Updated `page_recovery_vs_scale_noise()` so the color gradient legend is placed on a dedicated side axis and no longer obscures the scatter plots.

### Activity-type contribution and coverage readability

- Reworked `page_activity_type_contribution()` in `dags/visualisation_garmin_analytics_sections.py` so the weekly stacked calorie-by-type bar chart no longer crowds the summary content below it.
- Split the lower half of that page into separate side-by-side table regions for:
  - `Activity-Type Summary`, and
  - `Activity Session Table`.
- Adjusted legend placement, chart margins, and table bounding boxes to improve readability in PDF output.
- Refactored `page_calendar_and_coverage()` so the monthly calendar heatmaps and the `Data Coverage / Missingness Table` are now rendered on separate PDF pages.
- Enlarged the dedicated coverage page and increased table rendering space/font sizing so monthly missingness data is legible.

### Tests and project tracking

- Updated `tests/test_visualisation_garmin_analytics.py` to reflect the revised Garmin analytics page bundle.
- Verified the focused Garmin analytics rendering suite with:
  - `python -m pytest tests/test_visualisation_garmin_analytics.py -q`
- Confirmed the updated bundle now renders nine figures/pages instead of the previous eight because coverage now has a dedicated page.
- Updated `TASK.md` and `TODO.md` to record completion of the Garmin visualization refinement work.

## Operational Notes

- The Garmin analytics PDF section now produces an additional page because the coverage table has been separated from the calendar heatmaps.
- These changes are presentation-focused; they improve report clarity without changing the underlying Garmin ingestion pipeline or the higher-level report generation flow.
