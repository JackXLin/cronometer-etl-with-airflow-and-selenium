"""Helpers for detecting bounded Garmin daily metric gaps that merit re-fetching."""

from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Optional

import pandas as pd

DEFAULT_GARMIN_GAP_SCAN_DAYS = 180
DEFAULT_GARMIN_GAP_BACKFILL_MAX_DATES = 30
DEFAULT_GARMIN_GAP_MIN_MISSING_METRICS = 2
DEFAULT_GARMIN_GAP_MONITORED_COLUMNS = [
    "garmin_steps",
    "garmin_distance_m",
    "garmin_active_calories_kcal",
    "garmin_resting_hr_bpm",
    "garmin_floors_climbed",
    "garmin_sleep_seconds",
    "garmin_sleep_score",
    "garmin_avg_stress",
    "garmin_body_battery_max",
    "garmin_body_battery_min",
    "garmin_intensity_moderate_min",
    "garmin_intensity_vigorous_min",
    "garmin_activity_count",
    "garmin_hr_min_bpm",
    "garmin_hr_max_bpm",
    "garmin_hr_avg_bpm",
    "garmin_hrv",
    "garmin_respiration_avg",
    "garmin_spo2_avg",
    "garmin_training_readiness",
    "garmin_training_status",
]
DEFAULT_GARMIN_GAP_PRIORITY_COLUMNS = [
    "garmin_steps",
    "garmin_distance_m",
    "garmin_active_calories_kcal",
    "garmin_resting_hr_bpm",
    "garmin_sleep_seconds",
    "garmin_sleep_score",
    "garmin_avg_stress",
    "garmin_body_battery_max",
    "garmin_body_battery_min",
    "garmin_intensity_moderate_min",
    "garmin_intensity_vigorous_min",
    "garmin_activity_count",
    "garmin_hr_min_bpm",
    "garmin_hr_max_bpm",
    "garmin_hr_avg_bpm",
    "garmin_hrv",
    "garmin_respiration_avg",
    "garmin_spo2_avg",
    "garmin_training_readiness",
    "garmin_training_status",
]


def get_garmin_gap_scan_days() -> int:
    """Resolve how many recent days should be scanned for Garmin gaps.

    Returns:
        int: Positive number of days to inspect for missing metrics.

    Raises:
        ValueError: If the configured scan window is not positive.
    """
    raw_value = os.getenv(
        "GARMIN_GAP_SCAN_DAYS",
        str(DEFAULT_GARMIN_GAP_SCAN_DAYS),
    )
    scan_days = int(raw_value)
    if scan_days <= 0:
        raise ValueError("`GARMIN_GAP_SCAN_DAYS` must be a positive integer.")
    return scan_days



def get_garmin_gap_backfill_max_dates() -> int:
    """Resolve the maximum number of gap dates to re-fetch per sync run.

    Returns:
        int: Positive cap on historical gap dates to backfill.

    Raises:
        ValueError: If the configured cap is not positive.
    """
    raw_value = os.getenv(
        "GARMIN_GAP_BACKFILL_MAX_DATES",
        str(DEFAULT_GARMIN_GAP_BACKFILL_MAX_DATES),
    )
    max_dates = int(raw_value)
    if max_dates <= 0:
        raise ValueError("`GARMIN_GAP_BACKFILL_MAX_DATES` must be a positive integer.")
    return max_dates



def get_garmin_gap_min_missing_metrics() -> int:
    """Resolve how many missing core metrics constitute a likely gap.

    Returns:
        int: Positive threshold for missing monitored metrics on one day.

    Raises:
        ValueError: If the configured threshold is not positive.
    """
    raw_value = os.getenv(
        "GARMIN_GAP_MIN_MISSING_METRICS",
        str(DEFAULT_GARMIN_GAP_MIN_MISSING_METRICS),
    )
    min_missing_metrics = int(raw_value)
    if min_missing_metrics <= 0:
        raise ValueError(
            "`GARMIN_GAP_MIN_MISSING_METRICS` must be a positive integer."
        )
    return min_missing_metrics



def _normalize_gap_candidate_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize empty-string placeholders so missing-value checks are reliable.

    Args:
        frame (pd.DataFrame): Candidate Garmin daily frame slice.

    Returns:
        pd.DataFrame: Frame with blank strings converted to pandas missing values.
    """
    return frame.replace(r"^\s*$", pd.NA, regex=True)


def _find_interior_missing_mask(series: pd.Series) -> pd.Series:
    """Find missing values that sit between observed values in one series.

    Args:
        series (pd.Series): Candidate metric series.

    Returns:
        pd.Series: Boolean mask for interior missing values.
    """
    present = series.notna()
    has_prior_value = present.cumsum().shift(fill_value=0) > 0
    has_future_value = (
        present.iloc[::-1].cumsum().iloc[::-1].shift(-1, fill_value=0) > 0
    )
    return (~present) & has_prior_value & has_future_value



def find_garmin_daily_gap_dates(
    existing_daily: Optional[pd.DataFrame],
    historical_start_date: date,
    end_date: date,
    overlap_start_date: Optional[date] = None,
    monitored_columns: Optional[list[str]] = None,
    priority_columns: Optional[list[str]] = None,
    scan_days: Optional[int] = None,
    max_dates: Optional[int] = None,
    min_missing_metrics: Optional[int] = None,
) -> list[str]:
    """Find bounded historical Garmin dates that should be re-fetched.

    The detector is intentionally conservative: it scans only a bounded recent
    window, ignores the current overlap-refresh window, and prioritizes dates
    that are either missing a normally present Garmin daily metric or missing
    several monitored metrics together.

    Args:
        existing_daily (Optional[pd.DataFrame]): Existing Garmin daily artifact.
        historical_start_date (date): Lower bound for valid backfill dates.
        end_date (date): Inclusive upper bound for scanning.
        overlap_start_date (Optional[date]): Start date of the normal overlap
            refresh window. Dates on or after this boundary are skipped because
            they will already be re-fetched by the incremental sync.
        monitored_columns (Optional[list[str]]): Columns to inspect for gaps.
        priority_columns (Optional[list[str]]): Columns where even a single
            interior gap should be backfilled.
        scan_days (Optional[int]): Bounded lookback window for gap detection.
        max_dates (Optional[int]): Maximum number of gap dates to return.
        min_missing_metrics (Optional[int]): Threshold of missing monitored
            metrics required to treat a day as a likely gap.

    Returns:
        list[str]: ISO date strings that should be re-fetched, oldest to newest.

    Raises:
        ValueError: If the existing artifact lacks a `Date` column.
    """
    if existing_daily is None or existing_daily.empty:
        return []
    if "Date" not in existing_daily.columns:
        raise ValueError("Existing Garmin daily CSV must include a `Date` column.")

    resolved_scan_days = scan_days or get_garmin_gap_scan_days()
    resolved_max_dates = max_dates or get_garmin_gap_backfill_max_dates()
    resolved_min_missing_metrics = (
        min_missing_metrics or get_garmin_gap_min_missing_metrics()
    )
    resolved_monitored_columns = monitored_columns or DEFAULT_GARMIN_GAP_MONITORED_COLUMNS
    resolved_priority_columns = priority_columns or DEFAULT_GARMIN_GAP_PRIORITY_COLUMNS

    parsed_dates = pd.to_datetime(existing_daily["Date"], errors="coerce")
    if parsed_dates.isna().any():
        raise ValueError("Existing Garmin daily CSV `Date` contains invalid date values.")

    scan_start_date = max(
        historical_start_date,
        end_date - timedelta(days=resolved_scan_days - 1),
    )
    candidate_mask = parsed_dates.dt.date.between(scan_start_date, end_date)
    if overlap_start_date is not None:
        candidate_mask &= parsed_dates.dt.date < overlap_start_date

    available_columns = [
        column_name
        for column_name in resolved_monitored_columns
        if column_name in existing_daily.columns
    ]
    if not available_columns:
        return []
    available_priority_columns = [
        column_name
        for column_name in resolved_priority_columns
        if column_name in available_columns
    ]

    normalized_existing = _normalize_gap_candidate_frame(
        existing_daily.loc[:, ["Date", *available_columns]].copy()
    )
    gap_flags = pd.DataFrame(index=normalized_existing.index)
    for column_name in available_columns:
        gap_flags[column_name] = _find_interior_missing_mask(
            normalized_existing[column_name]
        )

    gap_counts = gap_flags.sum(axis=1)
    likely_gap_mask = gap_counts >= resolved_min_missing_metrics
    if available_priority_columns:
        likely_gap_mask |= gap_flags[available_priority_columns].any(axis=1)
    likely_gap_mask &= candidate_mask

    candidate_dates = normalized_existing.loc[:, "Date"]
    if candidate_dates.empty:
        return []

    # Reason: prioritize the newest gaps first so repeated daily runs can repair
    # recent history quickly without turning every sync into a full backfill.
    selected_dates = (
        candidate_dates.loc[likely_gap_mask]
        .drop_duplicates()
        .sort_values(ascending=False)
        .head(resolved_max_dates)
        .sort_values()
        .tolist()
    )
    return [str(value) for value in selected_dates]
