"""
TDEE (Total Daily Energy Expenditure) Calculator Module.

Provides adaptive TDEE estimation using exponential moving average (EMA)
smoothing on weight data before computing energy balance. This eliminates
the noise from daily water/glycogen fluctuations that plague naive approaches.

Methods:
    1. Adaptive EMA: Smooths weight, computes delta, derives TDEE daily, then
       smooths the TDEE estimate itself for a convergent signal.
    2. Stable Weight Periods: Finds windows where smoothed weight is flat and
       averages calorie intake during those periods.
    3. Regression: Linear model of calories vs smoothed weight change to find
       the calorie level producing zero change.
"""

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression


# Reason: Mixed tissue changes (not pure fat) have a caloric density of
# ~5500-7700 kcal/kg. We use 7000 as a pragmatic midpoint.
KCAL_PER_KG = 7000


def smooth_weight(weight_series: pd.Series, span: int = 10) -> pd.Series:
    """
    Apply exponential moving average to raw weight data.

    Args:
        weight_series (pd.Series): Raw daily weight measurements.
        span (int): EMA span in days (higher = smoother).

    Returns:
        pd.Series: Smoothed weight series.
    """
    return weight_series.ewm(span=span, min_periods=3).mean()


def compute_adaptive_tdee(
    calorie_series: pd.Series,
    weight_series: pd.Series,
    weight_ema_span: int = 10,
    tdee_ema_span: int = 14,
) -> pd.Series:
    """
    Compute adaptive TDEE using EMA-smoothed weight deltas.

    The algorithm:
        1. Smooth raw weight with EMA to remove water noise.
        2. Compute daily smoothed weight delta.
        3. Convert delta to caloric equivalent (delta * KCAL_PER_KG).
        4. Estimate daily TDEE = calorie_intake - caloric_equivalent.
        5. Smooth the TDEE estimate with a second EMA for stability.

    Args:
        calorie_series (pd.Series): Daily calorie intake.
        weight_series (pd.Series): Raw daily weight measurements.
        weight_ema_span (int): Span for weight smoothing.
        tdee_ema_span (int): Span for TDEE estimate smoothing.

    Returns:
        pd.Series: Adaptive TDEE estimates (one per day).
    """
    smoothed = smooth_weight(weight_series, span=weight_ema_span)
    daily_delta = smoothed.diff()
    caloric_cost = daily_delta * KCAL_PER_KG
    raw_tdee = calorie_series - caloric_cost
    adaptive_tdee = raw_tdee.ewm(span=tdee_ema_span, min_periods=7).mean()
    return adaptive_tdee


def compute_rolling_tdee(
    calorie_series: pd.Series,
    weight_series: pd.Series,
    window: int = 14,
    min_periods: int = 7,
    weight_ema_span: int = 10,
) -> pd.Series:
    """
    Compute rolling-window TDEE using smoothed weight.

    Args:
        calorie_series (pd.Series): Daily calorie intake.
        weight_series (pd.Series): Raw daily weight measurements.
        window (int): Rolling window size in days.
        min_periods (int): Minimum observations required.
        weight_ema_span (int): Span for weight smoothing.

    Returns:
        pd.Series: Rolling TDEE estimates.
    """
    smoothed = smooth_weight(weight_series, span=weight_ema_span)
    smoothed_delta = smoothed.diff()

    tdee_values = []
    for i in range(len(calorie_series)):
        start = max(0, i - window + 1)
        if i - start + 1 < min_periods:
            tdee_values.append(np.nan)
            continue

        window_cal = calorie_series.iloc[start : i + 1]
        window_delta = smoothed_delta.iloc[start : i + 1]

        avg_cal = window_cal.mean()
        avg_delta = window_delta.mean()
        tdee = avg_cal - (avg_delta * KCAL_PER_KG)
        tdee_values.append(tdee)

    return pd.Series(tdee_values, index=calorie_series.index)


def find_stable_weight_tdee(
    processed: pd.DataFrame,
    window: int = 14,
    tolerance_kg: float = 0.5,
    weight_ema_span: int = 10,
) -> dict:
    """
    Estimate TDEE from periods where smoothed weight is stable.

    Args:
        processed (pd.DataFrame): Must contain 'Energy (kcal)' and 'Weight (kg)'.
        window (int): Window size in days to check stability.
        tolerance_kg (float): Max range of smoothed weight to qualify as stable.
        weight_ema_span (int): Span for weight smoothing.

    Returns:
        dict: Keys 'estimate' (float or None) and 'period_count' (int).
    """
    smoothed = smooth_weight(processed["Weight (kg)"], span=weight_ema_span)
    stable_intakes = []

    for i in range(len(processed) - window + 1):
        w = smoothed.iloc[i : i + window]
        if w.max() - w.min() <= tolerance_kg:
            avg_cal = processed["Energy (kcal)"].iloc[i : i + window].mean()
            if not np.isnan(avg_cal) and avg_cal > 0:
                stable_intakes.append(avg_cal)

    if stable_intakes:
        return {"estimate": float(np.mean(stable_intakes)), "period_count": len(stable_intakes)}
    return {"estimate": None, "period_count": 0}


def regression_tdee(processed: pd.DataFrame, weight_ema_span: int = 10) -> dict:
    """
    Estimate TDEE via linear regression of calorie intake vs smoothed weight change.

    Finds the calorie level where predicted weight change = 0.

    Args:
        processed (pd.DataFrame): Must contain 'Energy (kcal)' and 'Weight (kg)'.
        weight_ema_span (int): Span for weight smoothing.

    Returns:
        dict: Keys 'estimate' (float or None) and 'r_squared' (float or None).
    """
    smoothed = smooth_weight(processed["Weight (kg)"], span=weight_ema_span)
    smoothed_delta = smoothed.diff()

    valid = ~(processed["Energy (kcal)"].isna() | smoothed_delta.isna())
    if valid.sum() < 14:
        return {"estimate": None, "r_squared": None}

    X = processed.loc[valid, "Energy (kcal)"].values.reshape(-1, 1)
    y = smoothed_delta[valid].values

    model = LinearRegression()
    model.fit(X, y)

    if abs(model.coef_[0]) < 1e-8:
        return {"estimate": None, "r_squared": None}

    tdee = -model.intercept_ / model.coef_[0]
    r2 = model.score(X, y)

    if 1000 < tdee < 5000:
        return {"estimate": float(tdee), "r_squared": float(r2)}
    return {"estimate": None, "r_squared": None}


def estimate_tdee(processed: pd.DataFrame) -> dict:
    """
    Estimate TDEE using multiple methods and produce a weighted average.

    Adds rolling TDEE columns to the DataFrame in-place:
        - 'TDEE_adaptive': Adaptive EMA TDEE
        - 'TDEE_14d': 14-day rolling TDEE
        - 'TDEE_30d': 30-day rolling TDEE
        - 'Weight_smoothed': EMA-smoothed weight

    Args:
        processed (pd.DataFrame): Processed nutrition + weight data.

    Returns:
        dict: TDEE estimates from each method plus 'weighted_average'.
    """
    estimates = {}
    cal = processed["Energy (kcal)"]
    wt = processed["Weight (kg)"]

    # Smoothed weight (used by multiple consumers)
    processed["Weight_smoothed"] = smooth_weight(wt, span=10)

    # Method 1: Adaptive EMA TDEE
    processed["TDEE_adaptive"] = compute_adaptive_tdee(cal, wt)
    adaptive_mean = processed["TDEE_adaptive"].dropna().mean()
    if 1200 < adaptive_mean < 4000:
        estimates["adaptive"] = adaptive_mean

    # Method 2: Rolling-window TDEE (14d and 30d)
    processed["TDEE_14d"] = compute_rolling_tdee(cal, wt, window=14, min_periods=7)
    processed["TDEE_30d"] = compute_rolling_tdee(cal, wt, window=30, min_periods=14)

    rolling_14_mean = processed["TDEE_14d"].dropna().mean()
    rolling_30_mean = processed["TDEE_30d"].dropna().mean()
    if 1200 < rolling_14_mean < 4000:
        estimates["rolling_14d"] = rolling_14_mean
    if 1200 < rolling_30_mean < 4000:
        estimates["rolling_30d"] = rolling_30_mean

    # Method 3: Stable weight periods
    stable = find_stable_weight_tdee(processed)
    if stable["estimate"] and 1200 < stable["estimate"] < 4000:
        estimates["stable_periods"] = stable["estimate"]
        estimates["stable_periods_count"] = stable["period_count"]

    # Method 4: Regression
    reg = regression_tdee(processed)
    if reg["estimate"]:
        estimates["regression"] = reg["estimate"]
        estimates["regression_r2"] = reg["r_squared"]

    # Method 5: Recent 30-day energy balance (using smoothed weight)
    recent = processed.tail(30).dropna(subset=["Energy (kcal)"])
    if len(recent) > 7:
        smoothed_delta = processed["Weight_smoothed"].diff()
        recent_delta_mean = smoothed_delta.tail(30).mean()
        recent_cal_mean = recent["Energy (kcal)"].mean()
        recent_tdee = recent_cal_mean - (recent_delta_mean * KCAL_PER_KG)
        if 1200 < recent_tdee < 4000:
            estimates["recent_30d"] = recent_tdee

    # Weighted average across methods
    method_weights = {
        "adaptive": 0.35,
        "rolling_30d": 0.25,
        "stable_periods": 0.15,
        "regression": 0.15,
        "recent_30d": 0.10,
    }

    realistic = {k: v for k, v in estimates.items() if k in method_weights and 1200 < v < 4000}
    if realistic:
        w_sum = sum(realistic[k] * method_weights[k] for k in realistic)
        w_total = sum(method_weights[k] for k in realistic)
        estimates["weighted_average"] = w_sum / w_total

    return estimates
