# Changelog — Visualisation Phase 2

## [2.1.0] — 2026-02-25

### Summary

Five targeted improvements to the PDF report focused on weight management
clarity: replaced the noisy rolling correlation chart, added a goal progress
page with burn-down chart, expanded weight projections to multi-scenario,
replaced weekday/weekend bars with a waterfall chart, and fixed the
surplus/deficit colour logic.

---

### Page 4 Rework — "What Drives Your Weight Change?"

**Problem (old):**
Rolling 14-day Pearson correlations plotted as 7 overlapping time-series lines.
Noisy, unreadable, and uninformative — 14-day windows give unreliable
correlations on daily weight change data dominated by water fluctuations.

**New:**
- **Top panel: Lagged Correlation Heatmap** — Rows = 7 nutrients,
  columns = lag 0/1/2/3 days. Each cell shows Pearson *r* with significance
  asterisk (* = p < 0.05). Uses diverging RdBu colormap centred on zero.
  Answers: "does eating nutrient X on day T affect weight on day T+N?"
- **Bottom panel: Enhanced Bar Chart with 95% CI** — Horizontal bars sorted
  by |r|, with Fisher z-transform confidence interval whiskers. Non-significant
  bars faded (alpha 0.35), significant bars bold. Each bar annotated with
  r value and sample size.

**New helpers in `visualisation_helpers.py`:**
- `compute_lagged_correlations()` — Pearson r at multiple lag offsets.
- `compute_correlation_ci()` — Fisher z-transform confidence intervals.

---

### New Page 7 — Goal Progress & Calorie Budget Burn-down

**Top panel: Weight Milestone Progress Bar**
- Horizontal bar from start weight → current → target.
- Shows % complete, kg remaining, projected completion date.
- Colour-coded status badge: green (On Track), amber (Stalled), red (Off Track).

**Bottom panel: Cumulative Calorie Deficit Burn-down**
- Sprint burn-down style chart: plots actual cumulative deficit (TDEE − intake)
  vs the linear pace required to reach the total deficit needed.
- Green/red shading shows periods ahead or behind schedule.
- Total deficit target line marked.

**New module:** `dags/visualisation_goals.py` (194 lines).

---

### Page 1 Expansion — Multi-Scenario Projections

**Old:** Two projection lines (current trend + target calories).

**New:** Four TDEE-based calorie scenarios:
- Aggressive (TDEE − 750)
- Standard (TDEE − 500)
- Slow (TDEE − 250)
- Current average intake

Plus an **inset table** showing kcal/day and estimated days to reach target
weight for each scenario. Current trend line with 95% CI retained.

---

### Page 5 Rework — Weekly Weight Change Waterfall

**Old (top-left):** Weekday vs weekend intake bar chart — only shows averages,
no temporal context.

**New (top-left):** Weekly weight change waterfall chart (last 16 weeks):
- Each bar = one week's net weight change (green = loss, red = gain).
- Cumulative progress line on secondary axis.
- Immediately shows whether recent weeks are trending in the right direction.

Histogram (top-right) and adherence calendar (bottom) unchanged.

---

### Bug Fix — Surplus/Deficit Colour Logic (Page 2)

**Old:** Green if surplus, red if deficit — misleading when the goal is weight
loss (a deficit is desirable).

**New:** Colour is **goal-aware**:
- If `current_weight > target_weight`: deficit = green (good), surplus = red.
- If `current_weight < target_weight`: surplus = green, deficit = red.

`page_tdee_dashboard` now accepts `target_weight_kg` parameter.

---

### Architecture — File Rebalance

Drawing helpers (`draw_weekly_waterfall`, `draw_adherence_calendar`) moved from
`visualisation.py` to `visualisation_helpers.py`. Goal progress page extracted
to new `visualisation_goals.py`.

| File | Lines | Role |
|------|-------|------|
| `visualisation.py` | 403 | Main entry + Pages 4-6 |
| `visualisation_pages.py` | 441 | Pages 1-3 |
| `visualisation_helpers.py` | 442 | Shared utilities + drawing helpers |
| `visualisation_goals.py` | 194 | Page 7 (goal progress) |
| `tdee_calculator.py` | 263 | TDEE estimation engine |

All modules under 500-line limit.

---

### Tests Added

**12 new tests** in `test_visualisation_helpers.py`:

- `TestComputeLaggedCorrelations` (6 tests): DataFrame structure, lag columns,
  dict cell keys, r-value range, insufficient data NaN, max_lag=0.
- `TestComputeCorrelationCI` (6 tests): dict keys including CI bounds,
  CI brackets correlation, sort order, sample size, insufficient data,
  wider CI at higher confidence.

**Total: 50 tests pass** (14 TDEE + 36 helpers).

---

### PDF Report Structure (Updated)

| Page | Content |
|------|---------|
| 1 | **Weight Trend & Multi-Scenario Projection** — smoothed weight + trend + BMI; 4 calorie scenarios with days-to-target table |
| 2 | **TDEE Dashboard** — method comparison; TDEE over time; goal-aware intake vs TDEE; text summary |
| 3 | **Energy & Macros** — rolling averages + weight overlay; macro pie; deficit/surplus bar; adherence rate |
| 4 | **What Drives Your Weight Change?** — lagged correlation heatmap; bar chart with 95% CI |
| 5 | **Behavioural Patterns** — weekly weight waterfall; weight change distribution; adherence calendar |
| 6 | **Key Figures & Summary** — text summary; actionable key-figures table |
| 7 | **Goal Progress & Burn-down** — milestone progress bar; cumulative deficit burn-down |
