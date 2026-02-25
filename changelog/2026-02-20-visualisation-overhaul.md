# Changelog

All notable changes to the Cronometer ETL visualisation module are documented here.

---

## [2.0.0] — 2026-02-20

### Summary

Major refactoring of the visualisation pipeline. The monolithic `visualisation.py`
(958 lines) was decomposed into four focused modules, the TDEE estimation was
replaced with an adaptive EMA-based algorithm, weight prediction gained
calorie-aware multi-scenario projections, and five redundant PDF pages were
removed to produce a streamlined 6-page report.

---

### Architecture & Module Split

| File | Lines | Role |
|------|-------|------|
| `dags/visualisation.py` | 434 | Main entry-point (`visualise_data`) + PDF pages 4-6 |
| `dags/visualisation_pages.py` | 389 | PDF pages 1-3 (weight prediction, TDEE dashboard, energy & macros) |
| `dags/visualisation_helpers.py` | 205 | Shared utilities: `prepare_metrics`, `build_key_figures_table`, `compute_nutrient_correlations`, `get_bmi_category`, `_fmt` |
| `dags/tdee_calculator.py` | 262 | Adaptive TDEE estimation engine (5 methods + weighted average) |

Every module stays under the 500-line limit defined in the project coding rules.

---

### TDEE Calculation — Complete Rewrite

**Problem (old approach):**
- Used raw daily weight change with the 7700 kcal/kg fat constant.
- Daily weight fluctuations are ~80 % water, glycogen, and gut content — not fat.
- Short windows (7-day) produced TDEE swings of ±1000+ kcal, rendering estimates
  unreliable.
- Stable-weight period detection used a ±0.2 kg tolerance over 7 days — too tight
  given normal daily water fluctuations of ±0.5–2.0 kg.

**New approach — `tdee_calculator.py`:**

1. **Adaptive EMA TDEE** (`compute_adaptive_tdee`)
   - Smooths raw weight with an exponential moving average (span = 10 days)
     *before* computing daily deltas.
   - Derives daily TDEE = calorie intake − (smoothed Δweight × 7000 kcal/kg).
   - Smooths the TDEE estimate itself with a second EMA (span = 14 days) for
     convergence.

2. **Rolling-window TDEE** (`compute_rolling_tdee`)
   - 14-day and 30-day windows (7-day window dropped — too noisy).
   - Also operates on EMA-smoothed weight, not raw.

3. **Stable Weight Periods** (`find_stable_weight_tdee`)
   - Window widened from 7 → 14 days.
   - Tolerance widened from ±0.2 kg → ±0.5 kg.
   - Operates on smoothed weight to avoid false negatives from water noise.

4. **Regression** (`regression_tdee`)
   - Linear model of calories vs *smoothed* weight delta (previously used raw).
   - Finds the calorie level where predicted weight change = 0.

5. **Recent 30-day energy balance** — uses smoothed weight delta.

6. **Weighted average** — combines all methods with confidence weights:
   - Adaptive: 0.35, Rolling 30d: 0.25, Stable periods: 0.15,
     Regression: 0.15, Recent 30d: 0.10.

**Other constants changed:**
- `KCAL_PER_KG` changed from 7700 (pure fat) to **7000** (mixed tissue —
  body composition changes include lean mass, not just fat).

---

### Weight Prediction — Upgraded

**Old (Page 8, subplot 4):**
- Simple linear extrapolation of raw (noisy) weight over 30 days.
- No confidence interval. Ignored calorie intake entirely.

**New (Page 1, bottom panel):**
- Uses **EMA-smoothed weight** for trend detection.
- **Multi-scenario projection** over 90 days:
  - *Current trend*: linear extrapolation of smoothed weight with **95 % confidence
    band** (±1.96 × SE of regression residuals).
  - *At target calories*: "If you eat at your calorie target, where does TDEE
    predict your weight will be?" Uses `deficit / KCAL_PER_KG` per day.
- Target weight horizontal reference line retained.

---

### Summary Table — Replaced

**Old table:**
Compared average nutrients on "weight gain days" vs "weight loss days" across
all-time and 3-month windows. This was **misleading** because daily weight
gain/loss is dominated by water retention (sodium, carbs, hydration) and gut
content — not fat metabolism from the previous day's calories.

**New table (`build_key_figures_table`):**
An actionable key-figures table comparing metrics across three time windows
(Last 7 Days, Last 30 Days, All Time):

| Metric | Description |
|--------|-------------|
| Avg Intake (kcal) | Mean daily calorie intake |
| Est. TDEE (kcal) | Adaptive TDEE estimate |
| Surplus/Deficit (kcal) | Intake − TDEE (signed) |
| Weight Trend (kg/wk) | Smoothed weight slope × 7 |
| Predicted Wt Delta (kg/wk) | From surplus/deficit ÷ 7000 × 7 |
| Protein (g/day) | Average daily protein |
| Fiber (g/day) | Average daily fibre |
| Cal Adherence (%) | % of days within calorie tolerance |

---

### Redundant Graphs Removed (11 pages → 6 pages)

| Removed | Reason |
|---------|--------|
| **BMI Tracking** (old page 1, top panel) | BMI = weight / height² where height is constant — just a rescaled duplicate of the weight chart. BMI category is now shown as an **annotation** on the weight trend chart. |
| **Correlation Heatmap + bar chart** (old page 7) | Fully redundant with the consolidated nutrient analysis page (rolling + static correlations with p-values). |
| **Average Weight by Month** (old page 4, top-left) | Averaging by calendar month conflates different years; weight has a temporal trend so monthly averaging destroys it. Misleading. |
| **Estimated Days to Target Weight** (old page 2, bottom) | Based on raw 7-day velocity — extremely noisy, often infinite or wildly oscillating. Not actionable. |
| **Weight Goal Progress Pie Chart** (old page 8, top-left) | Pie charts are a poor way to show progress toward a goal; the weight vs target line already covers this. |

---

### Bug Fixes

1. **Days-to-goal sign error** (old line 77-79):
   - Previously divided by `abs(velocity)`, always producing a positive number.
   - If the user was gaining weight but wanted to lose, it still showed positive
     "days to goal."
   - **Fix**: Now computes direction explicitly — reports `"Moving away from goal"`
     when the weight trend opposes the target direction.

2. **Summary string concatenation bug** (page 6 text block):
   - Inline `if est_tdee else ""` ternary inside Python's implicit string
     concatenation caused the entire expression to short-circuit.
   - **Fix**: TDEE line extracted to a separate variable before concatenation.

---

### Code Quality

- **Unused import removed**: `seaborn` was imported but no longer used after
  removing the correlation heatmap page.
- **All modules under 500 lines** per project coding rules.
- **Google-style docstrings** on every public and private function.
- **Type hints** added to all function signatures.
- **`# Reason:` comments** added for non-obvious decisions (e.g. KCAL_PER_KG
  choice, sign check in days-to-goal).

---

### Tests Added

**`tests/test_tdee_calculator.py`** — 14 tests covering:
- `smooth_weight`: constant input, noise reduction, output length.
- `compute_adaptive_tdee`: convergence on stable weight, output shape.
- `compute_rolling_tdee`: stable weight estimate, early NaN behaviour.
- `find_stable_weight_tdee`: detection of stable periods, rapid-change rejection.
- `regression_tdee`: sufficient data returns estimate, insufficient returns None.
- `estimate_tdee` (integration): return type, in-place column creation,
  realistic weighted average, losing-weight TDEE above intake.

**`tests/test_visualisation_helpers.py`** — 24 tests covering:
- `get_bmi_category`: all four WHO categories + three boundary values.
- `prepare_metrics`: BMI, macro %, calorie deficit sign, on-track flag,
  weekend flag, in-place return.
- `compute_nutrient_correlations`: dict structure, sort order, insufficient data.
- `build_key_figures_table`: return type, column names, key metric rows.
- `_fmt`: NaN handling, signed formatting, zero-decimal rounding.

**All 38 tests pass.**

---

### PDF Report Structure (New)

| Page | Content |
|------|---------|
| 1 | **Weight Trend & Prediction** — smoothed weight + overall linear trend + BMI annotation; 90-day multi-scenario projection with 95 % CI |
| 2 | **TDEE Dashboard** — method comparison bars; adaptive + rolling TDEE over time; intake vs TDEE bar; text summary with recommendations |
| 3 | **Energy & Macros** — energy rolling averages with weight overlay; macro % pie; calorie deficit/surplus bar; 7-day adherence rate |
| 4 | **Nutrient-Weight Correlations** — rolling 14-day correlations; static bar chart with p-value significance borders |
| 5 | **Behavioural Patterns** — weekday vs weekend intake; weight change distribution; calorie adherence calendar heatmap (last 6 months) |
| 6 | **Key Figures & Summary** — text summary (status, insights, recommendations); actionable key-figures table |

---

### Preserved (User Preference)

- **Hardcoded y-axis limits (100–140 kg)** on weight charts — kept per user
  request, as body weight is unlikely to change beyond those limits for this user.
