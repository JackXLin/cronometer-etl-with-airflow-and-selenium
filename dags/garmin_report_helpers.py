"""Shared analytics helpers for Garmin-focused report pages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats


GARMIN_LAG_METRICS = {
    "steps": "garmin_steps",
    "distance": "garmin_distance_m",
    "active calories": "garmin_active_calories_kcal",
    "resting HR": "garmin_resting_hr_bpm",
    "sleep duration": "garmin_sleep_seconds",
    "sleep score": "garmin_sleep_score",
    "avg stress": "garmin_avg_stress",
    "body battery min": "garmin_body_battery_min",
    "body battery max": "garmin_body_battery_max",
    "HRV": "garmin_hrv",
    "respiration": "garmin_respiration_avg",
    "intensity minutes": "garmin_total_intensity_min",
}


OUTLIER_COLUMNS = {
    "carbs": "Carbs (g)",
    "sodium": "Sodium (mg)",
    "water": "Water (g)",
    "sleep score": "garmin_sleep_score",
    "avg stress": "garmin_avg_stress",
    "steps": "garmin_steps",
    "active kcal": "garmin_active_calories_kcal",
    "resting HR": "garmin_resting_hr_bpm",
    "body battery": "garmin_body_battery_min",
    "HRV": "garmin_hrv",
}


RECOVERY_SCATTER_COLUMNS = {
    "sleep duration": "garmin_sleep_hours",
    "sleep score": "garmin_sleep_score",
    "stress": "garmin_avg_stress",
    "HRV": "garmin_hrv",
    "resting HR": "garmin_resting_hr_bpm",
    "body battery min": "garmin_body_battery_min",
}


@dataclass
class LagTableResult:
    """Container for lag-correlation matrix and summary table."""

    correlation_matrix: pd.DataFrame
    summary_table: pd.DataFrame



def _safe_numeric(series: pd.Series) -> pd.Series:
    """Convert a pandas series into numeric values.

    Args:
        series (pd.Series): Source series.

    Returns:
        pd.Series: Numeric series with invalid values coerced to NaN.
    """
    return pd.to_numeric(series, errors="coerce")



def _zscore_series(series: pd.Series) -> pd.Series:
    """Compute z-scores while tolerating constant or sparse series.

    Args:
        series (pd.Series): Source numeric series.

    Returns:
        pd.Series: Z-score series.
    """
    clean = _safe_numeric(series)
    std = clean.std(ddof=0)
    if np.isnan(std) or std == 0:
        return pd.Series(np.nan, index=series.index)
    return (clean - clean.mean()) / std



def _categorize_activity_group(activity_type: Optional[str]) -> str:
    """Map a Garmin activity type into a stable activity group.

    Args:
        activity_type (Optional[str]): Raw Garmin activity type.

    Returns:
        str: Activity group label.
    """
    normalized = (activity_type or "").strip().lower()
    if "walk" in normalized or normalized in {"walking", "hiking"}:
        return "walks"
    if "run" in normalized or normalized in {"running", "trail_running"}:
        return "runs"
    if "cycl" in normalized or normalized in {"road_biking", "indoor_cycling"}:
        return "cycling"
    if any(token in normalized for token in ["strength", "gym", "resistance", "weight"]):
        return "gym/resistance training"
    return "other"



def _derive_activity_proxy(processed: pd.DataFrame) -> pd.Series:
    """Create a Garmin activity proxy emphasizing active calories when present.

    Args:
        processed (pd.DataFrame): Processed dataset.

    Returns:
        pd.Series: Activity proxy series.
    """
    active = _safe_numeric(processed.get("garmin_active_calories_kcal", pd.Series(np.nan, index=processed.index)))
    if active.notna().sum() > 0:
        return active

    steps = _safe_numeric(processed.get("garmin_steps", pd.Series(np.nan, index=processed.index))).fillna(0)
    intensity = _safe_numeric(processed.get("garmin_total_intensity_min", pd.Series(np.nan, index=processed.index))).fillna(0)
    duration = _safe_numeric(processed.get("garmin_activity_duration_min", pd.Series(np.nan, index=processed.index))).fillna(0)
    return (steps * 0.04) + (intensity * 5.0) + (duration * 3.0)



def prepare_garmin_report_inputs(
    processed: pd.DataFrame,
    activity_df: Optional[pd.DataFrame] = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Prepare Garmin-enriched daily and activity datasets for reporting.

    Args:
        processed (pd.DataFrame): Main processed dataset.
        activity_df (Optional[pd.DataFrame]): Optional Garmin activity sessions.

    Returns:
        tuple[pd.DataFrame, pd.DataFrame]: Enriched daily and activity datasets.
    """
    report_df = processed.copy()
    report_df["Date"] = pd.to_datetime(report_df["Date"])
    report_df = report_df.sort_values("Date").reset_index(drop=True)

    if "Weight_smoothed" not in report_df.columns:
        report_df["Weight_smoothed"] = report_df["Weight (kg)"].ewm(span=10, min_periods=3).mean()

    report_df["garmin_sleep_hours"] = _safe_numeric(
        report_df.get("garmin_sleep_seconds", pd.Series(np.nan, index=report_df.index))
    ) / 3600.0
    report_df["garmin_total_intensity_min"] = _safe_numeric(
        report_df.get("garmin_intensity_moderate_min", pd.Series(np.nan, index=report_df.index))
    ).fillna(0) + _safe_numeric(
        report_df.get("garmin_intensity_vigorous_min", pd.Series(np.nan, index=report_df.index))
    ).fillna(0)

    if activity_df is None or activity_df.empty:
        activities = pd.DataFrame(
            columns=[
                "Date",
                "garmin_activity_type",
                "garmin_activity_group",
                "garmin_activity_duration_min",
                "garmin_activity_calories_kcal",
                "garmin_activity_avg_hr_bpm",
                "garmin_activity_max_hr_bpm",
                "garmin_activity_training_effect",
                "garmin_activity_training_load",
            ]
        )
    else:
        activities = activity_df.copy()
        if "Date" in activities.columns:
            activities["Date"] = pd.to_datetime(activities["Date"])
        if "garmin_activity_group" not in activities.columns and "garmin_activity_type" in activities.columns:
            activities["garmin_activity_group"] = activities["garmin_activity_type"].apply(_categorize_activity_group)

    if not activities.empty:
        daily_activity = (
            activities.groupby("Date", dropna=False)
            .agg(
                garmin_activity_duration_min=("garmin_activity_duration_min", "sum"),
                garmin_activity_calories_from_sessions_kcal=("garmin_activity_calories_kcal", "sum"),
                garmin_activity_avg_hr_bpm=("garmin_activity_avg_hr_bpm", "mean"),
                garmin_activity_max_hr_bpm=("garmin_activity_max_hr_bpm", "max"),
            )
            .reset_index()
        )
        report_df = report_df.merge(daily_activity, on="Date", how="left", suffixes=("", "_from_activities"))
        for column_name in [
            "garmin_activity_duration_min",
            "garmin_activity_calories_from_sessions_kcal",
            "garmin_activity_avg_hr_bpm",
            "garmin_activity_max_hr_bpm",
        ]:
            fallback_column = f"{column_name}_from_activities"
            if fallback_column in report_df.columns:
                report_df[column_name] = _safe_numeric(report_df[column_name]).combine_first(
                    _safe_numeric(report_df[fallback_column])
                )
                report_df = report_df.drop(columns=[fallback_column])

    report_df["garmin_activity_proxy_kcal"] = _derive_activity_proxy(report_df)
    report_df["garmin_activity_proxy_7d"] = report_df["garmin_activity_proxy_kcal"].rolling(7, min_periods=1).mean()
    report_df["Weight_trend_change_7d"] = report_df["Weight_smoothed"].shift(-7) - report_df["Weight_smoothed"]
    report_df["Week"] = report_df["Date"].dt.to_period("W")
    report_df["WeekStart"] = report_df["Week"].dt.start_time

    return report_df, activities



def build_lag_correlation_result(
    processed: pd.DataFrame,
    metric_map: dict[str, str],
    target_column: str,
    max_lag: int = 7,
) -> LagTableResult:
    """Compute lagged correlations for Garmin metrics against a target series.

    Args:
        processed (pd.DataFrame): Enriched processed dataset.
        metric_map (dict[str, str]): Display labels to source columns.
        target_column (str): Target column to correlate against.
        max_lag (int): Maximum lag in days.

    Returns:
        LagTableResult: Heatmap matrix plus summary table.
    """
    target = _safe_numeric(processed[target_column])
    matrix_rows: list[list[float]] = []
    summary_rows: list[dict[str, object]] = []

    for label, column_name in metric_map.items():
        if column_name not in processed.columns:
            matrix_rows.append([np.nan] * (max_lag + 1))
            summary_rows.append(
                {
                    "metric": label,
                    **{f"lag_{lag}": np.nan for lag in range(max_lag + 1)},
                    "best_lag": np.nan,
                    "best_correlation": np.nan,
                    "sign": "na",
                    "sample_size": 0,
                }
            )
            continue

        metric = _safe_numeric(processed[column_name])
        correlations: list[float] = []
        counts: list[int] = []
        for lag in range(max_lag + 1):
            shifted_metric = metric.shift(lag)
            valid = ~(shifted_metric.isna() | target.isna())
            if valid.sum() > 10:
                correlations.append(float(stats.pearsonr(shifted_metric[valid], target[valid])[0]))
                counts.append(int(valid.sum()))
            else:
                correlations.append(np.nan)
                counts.append(int(valid.sum()))
        matrix_rows.append(correlations)
        valid_pairs = [(lag, value) for lag, value in enumerate(correlations) if not np.isnan(value)]
        if valid_pairs:
            best_lag, best_corr = max(valid_pairs, key=lambda item: abs(item[1]))
            sign = "positive" if best_corr >= 0 else "negative"
            sample_size = counts[best_lag]
        else:
            best_lag = np.nan
            best_corr = np.nan
            sign = "na"
            sample_size = 0
        summary_rows.append(
            {
                "metric": label,
                **{f"lag_{lag}": correlations[lag] for lag in range(max_lag + 1)},
                "best_lag": best_lag,
                "best_correlation": best_corr,
                "sign": sign,
                "sample_size": sample_size,
            }
        )

    matrix = pd.DataFrame(matrix_rows, index=list(metric_map.keys()), columns=[f"lag_{lag}" for lag in range(max_lag + 1)])
    summary = pd.DataFrame(summary_rows)
    return LagTableResult(correlation_matrix=matrix, summary_table=summary)



def build_outlier_diagnostic_table(
    processed: pd.DataFrame,
    threshold_kg: float = 0.6,
) -> pd.DataFrame:
    """Build a diagnostic table for large daily scale moves.

    Args:
        processed (pd.DataFrame): Enriched processed dataset.
        threshold_kg (float): Absolute daily weight-change threshold.

    Returns:
        pd.DataFrame: Outlier-day diagnostics sorted by magnitude.
    """
    report_df = processed.copy()
    report_df["weight_delta"] = _safe_numeric(report_df["Daily Weight change (kg)"])
    mask = report_df["weight_delta"].abs() >= threshold_kg
    if mask.sum() == 0:
        return pd.DataFrame(
            columns=[
                "date",
                "weight delta",
                "carbs z-score",
                "sodium z-score",
                "sleep score z-score",
                "stress z-score",
                "resting HR delta",
                "body battery min",
                "HRV delta",
                "activity kcal",
                "likely explanation tag",
            ]
        )

    z_scores = {
        label: _zscore_series(report_df[column_name])
        for label, column_name in OUTLIER_COLUMNS.items()
        if column_name in report_df.columns
    }
    if "garmin_resting_hr_bpm" in report_df.columns:
        report_df["garmin_resting_hr_delta"] = _safe_numeric(report_df["garmin_resting_hr_bpm"]).diff()
    else:
        report_df["garmin_resting_hr_delta"] = np.nan
    if "garmin_hrv" in report_df.columns:
        report_df["garmin_hrv_delta"] = _safe_numeric(report_df["garmin_hrv"]).diff()
    else:
        report_df["garmin_hrv_delta"] = np.nan

    def tag_row(row: pd.Series) -> str:
        """Assign a likely explanation tag to an outlier row.

        Args:
            row (pd.Series): Outlier-day row.

        Returns:
            str: Explanation tag.
        """
        sodium_z = abs(row.get("sodium z-score", np.nan))
        carbs_z = abs(row.get("carbs z-score", np.nan))
        water_z = abs(row.get("water z-score", np.nan))
        recovery_signal = np.nanmax(
            [
                abs(row.get("sleep score z-score", np.nan)),
                abs(row.get("stress z-score", np.nan)),
                abs(row.get("HRV delta", np.nan)),
                abs(row.get("resting HR delta", np.nan)),
            ]
        )
        activity_signal = np.nanmax(
            [
                abs(row.get("steps z-score", np.nan)),
                abs(row.get("active kcal z-score", np.nan)),
            ]
        )
        hydration_signal = np.nanmax([sodium_z, carbs_z, water_z])
        if hydration_signal >= recovery_signal and hydration_signal >= activity_signal:
            return "glycogen / sodium / hydration"
        if recovery_signal >= activity_signal:
            return "recovery / sleep / stress"
        return "activity load"

    rows = []
    outliers = report_df.loc[mask].copy()
    for idx, row in outliers.iterrows():
        diagnostic = {
            "date": row["Date"].strftime("%Y-%m-%d"),
            "weight delta": row["weight_delta"],
            "carbs z-score": z_scores.get("carbs", pd.Series(np.nan, index=report_df.index)).iloc[idx],
            "sodium z-score": z_scores.get("sodium", pd.Series(np.nan, index=report_df.index)).iloc[idx],
            "water z-score": z_scores.get("water", pd.Series(np.nan, index=report_df.index)).iloc[idx],
            "sleep score z-score": z_scores.get("sleep score", pd.Series(np.nan, index=report_df.index)).iloc[idx],
            "stress z-score": z_scores.get("avg stress", pd.Series(np.nan, index=report_df.index)).iloc[idx],
            "steps z-score": z_scores.get("steps", pd.Series(np.nan, index=report_df.index)).iloc[idx],
            "active kcal z-score": z_scores.get("active kcal", pd.Series(np.nan, index=report_df.index)).iloc[idx],
            "resting HR delta": row.get("garmin_resting_hr_delta", np.nan),
            "body battery min": row.get("garmin_body_battery_min", np.nan),
            "HRV delta": row.get("garmin_hrv_delta", np.nan),
            "activity kcal": row.get("garmin_active_calories_kcal", np.nan),
        }
        diagnostic["likely explanation tag"] = tag_row(pd.Series(diagnostic))
        rows.append(diagnostic)

    result = pd.DataFrame(rows)
    return result.sort_values("weight delta", key=lambda series: series.abs(), ascending=False).reset_index(drop=True)



def build_weekly_summary_table_garmin(processed: pd.DataFrame) -> pd.DataFrame:
    """Build the Garmin-focused weekly decision table.

    Args:
        processed (pd.DataFrame): Enriched processed dataset.

    Returns:
        pd.DataFrame: Weekly Garmin summary table.
    """
    if processed.empty:
        return pd.DataFrame()

    weekly = (
        processed.groupby("WeekStart", dropna=False)
        .agg(
            avg_weight=("Weight (kg)", "mean"),
            week_start_weight=("Weight (kg)", "first"),
            week_end_weight=("Weight (kg)", "last"),
            avg_intake=("Energy (kcal)", "mean"),
            avg_protein=("Protein (g)", "mean"),
            avg_carbs=("Carbs (g)", "mean"),
            avg_sodium=("Sodium (mg)", "mean"),
            avg_steps=("garmin_steps", "mean"),
            total_active_kcal=("garmin_active_calories_kcal", "sum"),
            avg_sleep_hours=("garmin_sleep_hours", "mean"),
            avg_sleep_score=("garmin_sleep_score", "mean"),
            avg_stress=("garmin_avg_stress", "mean"),
            avg_resting_hr=("garmin_resting_hr_bpm", "mean"),
            avg_body_battery_min=("garmin_body_battery_min", "mean"),
            avg_hrv=("garmin_hrv", "mean"),
            avg_adherence=("On_track_calories", "mean"),
            start_smoothed=("Weight_smoothed", "first"),
            end_smoothed=("Weight_smoothed", "last"),
        )
        .reset_index()
    )
    if weekly.empty:
        return weekly
    weekly["7d weight delta"] = weekly["week_end_weight"] - weekly["week_start_weight"]
    weekly["weight trend slope"] = weekly["end_smoothed"] - weekly["start_smoothed"]
    weekly["adherence flags"] = np.where(weekly["avg_adherence"] >= 0.8, "on track", "watch")
    weekly["week start"] = weekly["WeekStart"].dt.strftime("%Y-%m-%d")
    return weekly[
        [
            "week start",
            "avg_weight",
            "week_start_weight",
            "week_end_weight",
            "7d weight delta",
            "avg_intake",
            "avg_protein",
            "avg_carbs",
            "avg_sodium",
            "avg_steps",
            "total_active_kcal",
            "avg_sleep_hours",
            "avg_sleep_score",
            "avg_stress",
            "avg_resting_hr",
            "avg_body_battery_min",
            "avg_hrv",
            "weight trend slope",
            "adherence flags",
        ]
    ].tail(8).reset_index(drop=True)



def build_activity_contribution_summary(
    activity_df: pd.DataFrame,
    processed: pd.DataFrame,
) -> pd.DataFrame:
    """Build an activity-type contribution summary table.

    Args:
        activity_df (pd.DataFrame): Garmin activity sessions.
        processed (pd.DataFrame): Enriched processed dataset.

    Returns:
        pd.DataFrame: Summary table by activity group.
    """
    if activity_df.empty:
        return pd.DataFrame(
            columns=[
                "type",
                "sessions",
                "total duration",
                "total calories",
                "average HR",
                "next-day average scale change",
            ]
        )

    sessions = activity_df.copy()
    sessions["Date"] = pd.to_datetime(sessions["Date"])
    if "garmin_activity_group" not in sessions.columns:
        sessions["garmin_activity_group"] = sessions.get("garmin_activity_type", pd.Series(dtype=str)).apply(_categorize_activity_group)
    next_day_lookup = processed.set_index(processed["Date"].dt.strftime("%Y-%m-%d"))["Daily Weight change (kg)"]
    sessions["next_day_weight_change"] = sessions["Date"].dt.strftime("%Y-%m-%d").map(next_day_lookup)

    return (
        sessions.groupby("garmin_activity_group", dropna=False)
        .agg(
            sessions=("garmin_activity_id", "count"),
            total_duration=("garmin_activity_duration_min", "sum"),
            total_calories=("garmin_activity_calories_kcal", "sum"),
            average_hr=("garmin_activity_avg_hr_bpm", "mean"),
            next_day_average_scale_change=("next_day_weight_change", "mean"),
        )
        .reset_index()
        .rename(columns={"garmin_activity_group": "type"})
    )



def build_activity_session_table(
    activity_df: pd.DataFrame,
    processed: pd.DataFrame,
    limit: int = 12,
) -> pd.DataFrame:
    """Build the activity session detail table for the report.

    Args:
        activity_df (pd.DataFrame): Garmin activity sessions.
        processed (pd.DataFrame): Enriched processed dataset.
        limit (int): Maximum number of rows to include.

    Returns:
        pd.DataFrame: Activity session table.
    """
    if activity_df.empty:
        return pd.DataFrame()

    sessions = activity_df.copy()
    sessions["Date"] = pd.to_datetime(sessions["Date"])
    same_day_intake = processed.set_index(processed["Date"].dt.strftime("%Y-%m-%d"))["Energy (kcal)"]
    next_day_change = processed.set_index(processed["Date"].dt.strftime("%Y-%m-%d"))["Daily Weight change (kg)"]
    sessions["same-day intake"] = sessions["Date"].dt.strftime("%Y-%m-%d").map(same_day_intake)
    sessions["next-day weight change"] = sessions["Date"].dt.strftime("%Y-%m-%d").map(next_day_change)

    table = sessions[
        [
            "Date",
            "garmin_activity_group",
            "garmin_activity_duration_min",
            "garmin_activity_calories_kcal",
            "garmin_activity_avg_hr_bpm",
            "garmin_activity_max_hr_bpm",
            "garmin_activity_training_effect",
            "garmin_activity_training_load",
            "same-day intake",
            "next-day weight change",
        ]
    ].copy()
    table = table.rename(
        columns={
            "Date": "date",
            "garmin_activity_group": "type",
            "garmin_activity_duration_min": "duration",
            "garmin_activity_calories_kcal": "calories",
            "garmin_activity_avg_hr_bpm": "avg HR",
            "garmin_activity_max_hr_bpm": "max HR",
            "garmin_activity_training_effect": "training effect",
            "garmin_activity_training_load": "training load",
        }
    )
    table["date"] = pd.to_datetime(table["date"]).dt.strftime("%Y-%m-%d")
    return table.sort_values("date", ascending=False).head(limit).reset_index(drop=True)



def build_regime_comparison_table(processed: pd.DataFrame) -> pd.DataFrame:
    """Build the regime comparison table requested for recovery analysis.

    Args:
        processed (pd.DataFrame): Enriched processed dataset.

    Returns:
        pd.DataFrame: Regime comparison table.
    """
    if processed.empty:
        return pd.DataFrame()

    report_df = processed.copy()
    rows = []
    sleep_hours = report_df.get("garmin_sleep_hours", pd.Series(np.nan, index=report_df.index))
    stress = report_df.get("garmin_avg_stress", pd.Series(np.nan, index=report_df.index))
    steps = report_df.get("garmin_steps", pd.Series(np.nan, index=report_df.index))
    hrv = report_df.get("garmin_hrv", pd.Series(np.nan, index=report_df.index))

    regime_masks = {
        "sleep <6h": sleep_hours < 6,
        "sleep 6 to 8h": sleep_hours.between(6, 8, inclusive="left"),
        "sleep >8h": sleep_hours >= 8,
        "high stress days": stress >= stress.median(),
        "low stress days": stress < stress.median(),
        "high step days": steps >= steps.median(),
        "low step days": steps < steps.median(),
        "high HRV days": hrv >= hrv.median(),
        "low HRV days": hrv < hrv.median(),
    }

    for label, mask in regime_masks.items():
        subset = report_df.loc[mask.fillna(False)]
        rows.append(
            {
                "regime": label,
                "mean intake": subset["Energy (kcal)"].mean(),
                "mean weight change": subset["Daily Weight change (kg)"].mean(),
                "mean active kcal": subset.get("garmin_active_calories_kcal", pd.Series(dtype=float)).mean(),
                "mean resting HR": subset.get("garmin_resting_hr_bpm", pd.Series(dtype=float)).mean(),
                "mean HRV": subset.get("garmin_hrv", pd.Series(dtype=float)).mean(),
                "count of days": len(subset.index),
            }
        )
    return pd.DataFrame(rows)



def build_coverage_table(
    processed: pd.DataFrame,
    activity_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build the monthly data coverage / missingness table.

    Args:
        processed (pd.DataFrame): Enriched processed dataset.
        activity_df (pd.DataFrame): Garmin activity sessions.

    Returns:
        pd.DataFrame: Monthly coverage percentages.
    """
    if processed.empty:
        return pd.DataFrame()

    report_df = processed.copy()
    report_df["month"] = report_df["Date"].dt.to_period("M").astype(str)
    activity_days = set()
    if not activity_df.empty and "Date" in activity_df.columns:
        activity_days = set(pd.to_datetime(activity_df["Date"]).dt.strftime("%Y-%m-%d"))

    rows = []
    for month, subset in report_df.groupby("month"):
        total_days = max(len(subset.index), 1)
        date_keys = subset["Date"].dt.strftime("%Y-%m-%d")
        rows.append(
            {
                "month": month,
                "% days with weight": subset["Weight (kg)"].notna().mean() * 100,
                "% days with sleep": subset.get("garmin_sleep_seconds", pd.Series(dtype=float)).notna().mean() * 100,
                "% days with HRV": subset.get("garmin_hrv", pd.Series(dtype=float)).notna().mean() * 100,
                "% days with body battery": subset.get("garmin_body_battery_min", pd.Series(dtype=float)).notna().mean() * 100,
                "% days with activity details": (date_keys.isin(activity_days).sum() / total_days) * 100,
                "% days with body composition": subset["Weight (kg)"].notna().mean() * 100,
            }
        )
    return pd.DataFrame(rows)
