"""
Shared helper utilities for the visualisation module.

Contains data preparation, metric computation, and BMI category logic
used across multiple PDF pages.
"""

import numpy as np
import pandas as pd
from scipy import stats


def get_bmi_category(bmi: float) -> str:
    """
    Return BMI category string based on WHO classification.

    Args:
        bmi (float): Body mass index value.

    Returns:
        str: Category label.
    """
    if bmi < 18.5:
        return "Underweight"
    elif bmi < 25:
        return "Normal"
    elif bmi < 30:
        return "Overweight"
    return "Obese"


def prepare_metrics(processed: pd.DataFrame, height_cm: float,
                    target_weight_kg: float, target_calories: int,
                    calorie_tolerance_pct: float) -> pd.DataFrame:
    """
    Compute all derived columns needed by the visualisation pages.

    Adds columns in-place: BMI, macro percentages, calorie deficit,
    on-track flag, weekday/weekend flags, weight velocity.

    Args:
        processed (pd.DataFrame): Merged nutrition + weight data.
        height_cm (float): User height in centimetres.
        target_weight_kg (float): Goal body weight.
        target_calories (int): Daily calorie target.
        calorie_tolerance_pct (float): Fraction tolerance for on-track.

    Returns:
        pd.DataFrame: The same DataFrame with new columns added.
    """
    height_m = height_cm / 100.0
    processed["BMI"] = processed["Weight (kg)"] / (height_m ** 2)

    # Weight velocity via linear slope over rolling windows
    processed["Weight_velocity_7d"] = (
        processed["Weight (kg)"]
        .rolling(7)
        .apply(lambda x: np.polyfit(range(len(x)), x, 1)[0] * 7
               if len(x) >= 3 else np.nan)
    )

    # Macro percentages (avoid div-by-zero)
    energy = processed["Energy (kcal)"]
    safe_energy = energy.replace(0, np.nan)
    processed["Protein_pct"] = (processed["Protein (g)"] * 4) / safe_energy * 100
    processed["Carbs_pct"] = (processed["Carbs (g)"] * 4) / safe_energy * 100
    processed["Fat_pct"] = (processed["Fat (g)"] * 9) / safe_energy * 100

    # Calorie deficit/surplus (positive = under target = deficit)
    processed["Calorie_deficit"] = target_calories - energy

    # On-track flag
    low = target_calories * (1 - calorie_tolerance_pct)
    high = target_calories * (1 + calorie_tolerance_pct)
    processed["On_track_calories"] = energy.between(low, high)

    # Temporal features
    processed["Month"] = processed["Date"].dt.month
    processed["Weekday"] = processed["Date"].dt.dayofweek
    processed["Is_weekend"] = processed["Weekday"].isin([5, 6])

    return processed


def compute_nutrient_correlations(processed: pd.DataFrame,
                                  nutrients: list) -> list:
    """
    Compute Pearson correlations between each nutrient and daily weight change,
    including p-values and significance flags.

    Args:
        processed (pd.DataFrame): Data with nutrient columns and
            'Daily Weight change (kg)'.
        nutrients (list): Column names of nutrients to test.

    Returns:
        list[dict]: Sorted by absolute correlation descending. Each dict has
            keys: nutrient, correlation, p_value, significant.
    """
    results = []
    wt_change = processed["Daily Weight change (kg)"]
    for nutrient in nutrients:
        valid = ~(processed[nutrient].isna() | wt_change.isna())
        if valid.sum() > 2:
            corr, p = stats.pearsonr(processed[nutrient][valid], wt_change[valid])
            results.append({
                "nutrient": nutrient,
                "correlation": corr,
                "p_value": p,
                "significant": p < 0.05,
            })
    results.sort(key=lambda x: abs(x["correlation"]), reverse=True)
    return results


def build_key_figures_table(processed: pd.DataFrame,
                            tdee_estimates: dict,
                            target_calories: int,
                            protein_goal_g: int,
                            fiber_goal_g: int) -> pd.DataFrame:
    """
    Build an actionable key-figures table comparing metrics across time windows.

    Replaces the old gain-day / loss-day nutrient comparison with numbers
    the user can actually act on.

    Args:
        processed (pd.DataFrame): Full processed data with TDEE columns.
        tdee_estimates (dict): Output of estimate_tdee().
        target_calories (int): Daily calorie target.
        protein_goal_g (int): Daily protein target in grams.
        fiber_goal_g (int): Daily fibre target in grams.

    Returns:
        pd.DataFrame: Table with rows=metrics, columns=time windows.
    """
    windows = {
        "Last 7 Days": processed.tail(7),
        "Last 30 Days": processed.tail(30),
        "All Time": processed,
    }

    rows = []
    for label, data in windows.items():
        valid = data.dropna(subset=["Energy (kcal)"])
        avg_intake = valid["Energy (kcal)"].mean() if len(valid) > 0 else np.nan

        # TDEE from adaptive column if available
        tdee_val = np.nan
        if "TDEE_adaptive" in data.columns:
            tdee_col = data["TDEE_adaptive"].dropna()
            if len(tdee_col) > 0:
                tdee_val = tdee_col.iloc[-1] if label != "All Time" else tdee_col.mean()

        surplus_deficit = avg_intake - tdee_val if not np.isnan(tdee_val) else np.nan

        # Smoothed weight trend (kg/week)
        if "Weight_smoothed" in data.columns and len(data) > 1:
            sm = data["Weight_smoothed"].dropna()
            if len(sm) >= 2:
                days_span = max((data["Date"].iloc[-1] - data["Date"].iloc[0]).days, 1)
                trend_per_week = (sm.iloc[-1] - sm.iloc[0]) / days_span * 7
            else:
                trend_per_week = np.nan
        else:
            trend_per_week = np.nan

        # Predicted weekly delta from intake vs TDEE
        predicted_weekly = surplus_deficit / 7000 * 7 if not np.isnan(surplus_deficit) else np.nan

        protein_avg = valid["Protein (g)"].mean() if len(valid) > 0 else np.nan
        fiber_avg = valid["Fiber (g)"].mean() if len(valid) > 0 else np.nan
        adherence = data["On_track_calories"].mean() * 100 if "On_track_calories" in data.columns else np.nan

        rows.append({
            "Time Window": label,
            "Avg Intake (kcal)": _fmt(avg_intake, 0),
            "Est. TDEE (kcal)": _fmt(tdee_val, 0),
            "Surplus/Deficit (kcal)": _fmt(surplus_deficit, 0, sign=True),
            "Weight Trend (kg/wk)": _fmt(trend_per_week, 2, sign=True),
            "Predicted Wt Delta (kg/wk)": _fmt(predicted_weekly, 2, sign=True),
            "Protein (g/day)": _fmt(protein_avg, 0),
            "Fiber (g/day)": _fmt(fiber_avg, 0),
            "Cal Adherence (%)": _fmt(adherence, 1),
        })

    return pd.DataFrame(rows).set_index("Time Window").T


def _fmt(val, decimals: int = 1, sign: bool = False) -> str:
    """
    Format a numeric value for display, returning '--' for NaN.

    Args:
        val: Numeric value or NaN.
        decimals (int): Decimal places.
        sign (bool): If True, prefix positive values with '+'.

    Returns:
        str: Formatted string.
    """
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "--"
    fmt = f"{{:+.{decimals}f}}" if sign else f"{{:.{decimals}f}}"
    return fmt.format(val)
