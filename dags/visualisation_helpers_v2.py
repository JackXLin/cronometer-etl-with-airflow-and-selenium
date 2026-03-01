"""
Phase 3 helper utilities for the visualisation module.

Contains dynamic axis limits, BMI range, intake consistency,
weekly summary tables, day-of-week stats, and correlation callouts.
"""

import numpy as np
import pandas as pd

from visualisation_helpers import _fmt


def compute_dynamic_ylim(processed: pd.DataFrame,
                         target_weight_kg: float,
                         padding: float = 2.0) -> tuple:
    """
    Compute dynamic y-axis limits from actual weight data and target.

    Args:
        processed (pd.DataFrame): Data with 'Weight (kg)' column.
        target_weight_kg (float): Goal weight.
        padding (float): Padding in kg above/below data range.

    Returns:
        tuple: (y_min, y_max) for axis limits.
    """
    wt = processed["Weight (kg)"].dropna()
    if len(wt) == 0:
        return (target_weight_kg - 10, target_weight_kg + 10)
    y_min = min(wt.min(), target_weight_kg) - padding
    y_max = wt.max() + padding
    return (y_min, y_max)


def compute_healthy_bmi_range(height_cm: float) -> tuple:
    """
    Compute healthy weight range (BMI 18.5-24.9) for a given height.

    Args:
        height_cm (float): User height in centimetres.

    Returns:
        tuple: (weight_low_kg, weight_high_kg) for the normal BMI band.
    """
    height_m = height_cm / 100.0
    return (18.5 * height_m ** 2, 24.9 * height_m ** 2)


def compute_intake_consistency(calorie_series: pd.Series) -> float:
    """
    Compute intake consistency as coefficient of variation (CV%).

    Lower CV = more consistent intake. Research shows consistency
    matters as much as average intake for fat loss outcomes.

    Args:
        calorie_series (pd.Series): Daily calorie intake values.

    Returns:
        float: CV as a percentage, or NaN if insufficient data.
    """
    clean = calorie_series.dropna()
    if len(clean) < 2 or clean.mean() == 0:
        return np.nan
    return (clean.std() / clean.mean()) * 100


def build_weekly_summary_table(processed: pd.DataFrame,
                               n_weeks: int = 8) -> pd.DataFrame:
    """
    Build a week-by-week summary table for the last N weeks.

    Args:
        processed (pd.DataFrame): Full dataset with TDEE and adherence cols.
        n_weeks (int): Number of recent weeks to include.

    Returns:
        pd.DataFrame: One row per week with intake, TDEE, deficit,
            weight start/end, delta, and adherence.
    """
    wt = processed[["Date", "Weight (kg)", "Energy (kcal)",
                     "On_track_calories"]].copy()
    if "TDEE_adaptive" in processed.columns:
        wt["TDEE_adaptive"] = processed["TDEE_adaptive"]
    wt["Week"] = wt["Date"].dt.to_period("W")

    weeks = sorted(wt["Week"].unique())[-n_weeks:]
    rows = []
    for week in weeks:
        w = wt[wt["Week"] == week]
        avg_intake = w["Energy (kcal)"].mean()
        avg_tdee = (w["TDEE_adaptive"].mean()
                    if "TDEE_adaptive" in w.columns else np.nan)
        deficit = (avg_intake - avg_tdee
                   if not np.isnan(avg_tdee) else np.nan)
        wt_start = w["Weight (kg)"].iloc[0]
        wt_end = w["Weight (kg)"].iloc[-1]
        delta = wt_end - wt_start
        adh = w["On_track_calories"].mean() * 100

        rows.append({
            "Week": str(week)[-5:],
            "Avg Intake": _fmt(avg_intake, 0),
            "Avg TDEE": _fmt(avg_tdee, 0),
            "Deficit": _fmt(deficit, 0, sign=True),
            "Wt Start": _fmt(wt_start, 1),
            "Wt End": _fmt(wt_end, 1),
            "Wt Delta": _fmt(delta, 2, sign=True),
            "Adh %": _fmt(adh, 0),
        })

    return pd.DataFrame(rows)


def compute_day_of_week_stats(processed: pd.DataFrame) -> pd.DataFrame:
    """
    Compute calorie intake statistics grouped by day of the week.

    Args:
        processed (pd.DataFrame): Data with Date and Energy (kcal) columns.

    Returns:
        pd.DataFrame: One row per weekday (Mon-Sun) with mean, median,
            std, and count.
    """
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    df = processed[["Date", "Energy (kcal)"]].copy()
    df["DayOfWeek"] = df["Date"].dt.dayofweek

    stats_rows = []
    for i, name in enumerate(day_names):
        day_data = df[df["DayOfWeek"] == i]["Energy (kcal)"]
        stats_rows.append({
            "Day": name,
            "DayNum": i,
            "Mean": day_data.mean(),
            "Median": day_data.median(),
            "Std": day_data.std(),
            "Count": len(day_data),
        })
    return pd.DataFrame(stats_rows)


def build_strongest_driver_callout(corrs_ci: list,
                                   lagged: pd.DataFrame,
                                   nutrients: list) -> str:
    """
    Build a plain-language callout summarising the strongest correlation
    finding from the nutrient-weight analysis.

    Args:
        corrs_ci (list): Output of compute_correlation_ci().
        lagged (pd.DataFrame): Output of compute_lagged_correlations().
        nutrients (list): Nutrient column names.

    Returns:
        str: Human-readable summary string.
    """
    if not corrs_ci:
        return "Insufficient data for correlation analysis."

    best = corrs_ci[0]
    nutrient = best["nutrient"]
    r = best["correlation"]
    p = best["p_value"]
    sig = best["significant"]

    # Find best lag for this nutrient
    best_lag = 0
    best_lag_r = abs(r)
    if nutrient in lagged.index:
        for col in lagged.columns:
            cell = lagged.loc[nutrient, col]
            if isinstance(cell, dict) and not np.isnan(cell["r"]):
                if abs(cell["r"]) > best_lag_r:
                    best_lag_r = abs(cell["r"])
                    best_lag = int(col.split("_")[1])

    # Reason: sodium/carbs correlations with weight change are typically
    # water retention effects, not fat metabolism.
    water_nutrients = {"Sodium (mg)", "Carbs (g)", "Water (g)"}
    mechanism = ("likely reflecting water retention rather than fat gain"
                 if nutrient in water_nutrients
                 else "suggesting a link to energy balance")

    direction = "positively" if r > 0 else "negatively"
    sig_text = f"p={p:.3f}" if sig else "not statistically significant"
    lag_text = (f"with the strongest effect at {best_lag}-day lag"
                if best_lag > 0 else "with strongest same-day effect")

    return (
        f"{nutrient} is {direction} correlated with weight change "
        f"(r={r:.3f}, {sig_text}), {lag_text}, {mechanism}."
    )


# Reason: moved here from visualisation_pages.py to keep that module
# under the 500-line limit.
KCAL_PER_KG_CONST = 7000


def build_tdee_summary_text(tdee_estimates: dict,
                            avg_intake: float,
                            target_weight_kg: float = 70) -> str:
    """
    Build the TDEE summary text block with quantitative recommendations.

    Args:
        tdee_estimates (dict): All TDEE method results.
        avg_intake (float): Recent average calorie intake.
        target_weight_kg (float): Goal weight for context.

    Returns:
        str: Formatted multi-line summary.
    """
    lines = ["TDEE ESTIMATION SUMMARY\n"]

    if "weighted_average" in tdee_estimates:
        lines.append(
            f"Best Estimate: {tdee_estimates['weighted_average']:.0f} cal/day\n"
        )

    lines.append("Method Results:")
    label_map = {
        "adaptive": "Adaptive EMA",
        "rolling_30d": "Rolling 30d",
        "rolling_14d": "Rolling 14d",
        "stable_periods": "Stable Periods",
        "regression": "Regression",
        "recent_30d": "Recent 30d",
    }
    for key, label in label_map.items():
        val = tdee_estimates.get(key)
        if val and isinstance(val, (int, float)) and 1200 < val < 4000:
            lines.append(f"  {label}: {val:.0f} cal")

    if "stable_periods_count" in tdee_estimates:
        lines.append("\nData Quality:")
        lines.append(
            f"  Stable periods found: {tdee_estimates['stable_periods_count']}"
        )
    if "regression_r2" in tdee_estimates:
        lines.append(f"  Regression R2: {tdee_estimates['regression_r2']:.3f}")

    est = tdee_estimates.get("weighted_average")
    if est:
        gap = avg_intake - est
        lines.append("\nQuantitative Recommendations:")
        if gap > 200:
            reduction = gap
            expected_loss = reduction / KCAL_PER_KG_CONST * 7
            lines.append(
                f"  Reduce by ~{reduction:.0f} cal/day to maintain")
            lines.append(
                f"  Current surplus => ~{expected_loss:+.2f} kg/wk")
        elif gap < -200:
            expected_loss = abs(gap) / KCAL_PER_KG_CONST * 7
            lines.append(
                f"  In deficit of ~{abs(gap):.0f} cal/day")
            lines.append(
                f"  Expected loss: ~{expected_loss:.2f} kg/wk")
        else:
            lines.append("  Intake is near TDEE (maintenance)")

        lines.append(f"\n  For 0.5 kg/wk loss: ~{est - 500:.0f} cal/day")
        lines.append(f"  For 0.25 kg/wk loss: ~{est - 250:.0f} cal/day")
        lines.append(f"  For maintenance:     ~{est:.0f} cal/day")

    return "\n".join(lines)
