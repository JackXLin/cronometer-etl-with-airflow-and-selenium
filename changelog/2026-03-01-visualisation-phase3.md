# Changelog — Visualisation Phase 3 Overhaul

**Date:** 2026-03-01  
**Scope:** Comprehensive improvements to the PDF report for weight management & fat loss insights.

---

## New Files

### `dags/visualisation_helpers_v2.py`
Phase 3 helper utilities split from `visualisation_helpers.py` to stay under the 500-line module limit.

- `compute_dynamic_ylim()` — Dynamic y-axis limits from actual weight data + target.
- `compute_healthy_bmi_range()` — Healthy weight range (BMI 18.5–24.9) for a given height.
- `compute_intake_consistency()` — Coefficient of variation (CV%) for calorie intake consistency.
- `build_weekly_summary_table()` — Week-by-week summary table (last N weeks) with intake, TDEE, deficit, weight delta, adherence.
- `compute_day_of_week_stats()` — Calorie intake stats grouped by day of the week (Mon–Sun).
- `build_strongest_driver_callout()` — Plain-language summary of the most significant nutrient–weight correlation, with water-retention mechanism detection.
- `build_tdee_summary_text()` — TDEE dashboard text block with quantitative recommendations (moved from `visualisation_pages.py`).

### `dags/visualisation_weekly.py`
New PDF page renderer for Page 7 — Weekly Summary & Rate of Change.

- **Rate of Weight Change chart:** Uses `Weight_velocity_7d` with green/red shading for losing/gaining, safe-rate guideline lines, and current-rate annotation.
- **Weekly Summary Table:** 8-week table with conditional coloring on weight delta column.

### `tests/test_visualisation_helpers_v2.py`
Comprehensive test suite covering all new helper functions (28 new tests).

---

## Modified Files

### `dags/visualisation_helpers.py`

**New features:**
- `Protein_per_kg` column added in `prepare_metrics()` — protein intake per kg body weight, a key fat-loss metric.

**Key figures table (`build_key_figures_table`) overhaul:**
- **Renamed:** "Predicted Wt Delta" → "Expected from Intake (kg/wk)" for clarity.
- **Renamed:** "Weight Trend" → "Actual Trend (kg/wk)".
- **Renamed:** "Est. TDEE" → "Est. TDEE vs Intake" and "Surplus/Deficit" → "Surplus/Deficit vs TDEE" to clarify sign convention.
- **Added rows:** Avg Weight (kg), Trend Discrepancy (kg/wk), Wknd-Wkday Diff (kcal), Intake Consistency (CV%).
- **Fixed:** All Time TDEE now shows "N/A" instead of a misleading mean across different activity levels.
- **Added:** Discrepancy row (actual trend minus predicted from energy balance) to flag tracking errors.

### `dags/visualisation_pages.py`

**Page 1 — Weight Trend & Prediction:**
- **Fixed:** Hardcoded `set_ylim(100, 140)` replaced with `compute_dynamic_ylim()` — axes now adapt to actual data range.
- **Added:** Healthy BMI zone shading (green band for normal weight range based on user height).
- **Added:** Segmented trend lines — all-time trend (dashed, faded) vs last 90 days (solid) for actionable context.
- **Added:** "Weight Lost/Gained" annotation box showing total change from start.
- **Changed:** Projection x-axis now uses **calendar dates** instead of abstract day indices.
- **Added:** "Target Date" column in the scenario inset table.

**Page 2 — TDEE Dashboard:**
- **Replaced:** Static 2-bar Intake vs TDEE chart → **time-series** showing 7-day rolling intake vs adaptive TDEE with green/red deficit/surplus shading.
- **Improved:** Recommendations are now **quantitative** (e.g., "Reduce by ~350 cal/day", "Expected loss: ~0.35 kg/wk", specific calorie targets for 0.25/0.5 kg/wk loss).
- **Added:** Weighted average TDEE horizontal line in method comparison chart.

**Page 3 — Energy & Macros:**
- **Replaced:** Macro pie chart → **stacked bar chart** with gram values and percentage labels on each bar.
- **Added:** Protein goal horizontal line on macro chart.
- **Replaced:** Daily deficit/surplus bar chart → **7-day rolling area chart** with green/red shading.
- **Added:** 80% adherence target line on adherence rate chart.
- **Fixed:** Weight overlay y-axis now uses dynamic limits instead of hardcoded 100–140.

### `dags/visualisation.py`

**Page 4 — Nutrient-Weight Correlations:**
- **Added:** "Strongest driver" callout at the bottom — a plain-language summary of the most significant finding, with water-retention vs energy-balance mechanism detection.
- **Changed:** Bar chart now shows **best-lag per nutrient** instead of only lag_0, eliminating redundancy with the heatmap's lag_0 column. Each bar label includes the lag (e.g., "[+2d]").

**Page 5 — Behavioural Patterns:**
- **Replaced:** Simple weight change histogram → **weekday vs weekend histogram overlay** with separate mean annotations.
- **Added:** **Day-of-week calorie distribution box plot** with weekend days colored differently and calorie target line.
- **Layout:** Changed from 2+1 layout to 2×2 grid (waterfall, histogram overlay, box plot, calendar).

**Page 6 — Key Figures & Summary:**
- **Improved:** Layout split into two subplots (text summary top, table bottom) for better readability.
- **Added:** Conditional cell coloring on the key figures table — green for favorable values, red for unfavorable (deficit/surplus, weight trend direction).
- **Updated:** Recommendations are now quantitative with expected kg/wk impact.
- **Updated:** Deficit label clarified to "Avg Deficit vs Target".

**New Page 7 — Weekly Summary & Rate of Change:**
- Report expanded from 7 to 8 pages.
- See `visualisation_weekly.py` above.

### `dags/visualisation_goals.py`

**Page 8 (formerly Page 7) — Goal Progress:**
- **Fixed:** Progress bar now supports **weight gain goals** (previously assumed weight loss direction only).
- **Added:** **Cumulative Weight Change Timeline** — new middle panel showing total weight change from start with target line and progress/regress shading.
- **Redesigned:** Burn-down chart now projects **forward from today** to the estimated target date, instead of retroactively from day 1 (which always showed "behind schedule").
- **Layout:** Changed from 2-panel to 3-panel (progress bar, cumulative timeline, forward burn-down).

### `tests/test_visualisation_helpers.py`

- **Updated:** `test_contains_key_metric_rows` to verify all new/renamed table rows.
- **Added:** `test_adds_protein_per_kg` for the new `Protein_per_kg` column.

---

## Bug Fixes

| Bug | Fix |
|-----|-----|
| Hardcoded y-axis `set_ylim(100, 140)` on Pages 1 and 3 | Replaced with `compute_dynamic_ylim()` |
| All Time TDEE showed misleading average | Now shows "N/A" for All Time window |
| Progress bar assumed weight loss direction | Added `wants_loss` direction detection |
| Projection x-axis showed day indices, not dates | Converted to calendar dates with `pd.date_range()` |
| Bar chart showed lag_0 redundant with heatmap | Now shows best-lag per nutrient |
| `Weight_velocity_7d` column computed but never used | Integrated into new Rate of Change chart |

---

## Test Results

**62 tests, all passing** (6.88s)

- `test_visualisation_helpers.py`: 34 tests (existing + 2 new)
- `test_visualisation_helpers_v2.py`: 28 tests (all new)
