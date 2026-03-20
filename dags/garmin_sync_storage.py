"""Helpers for Garmin historical sync, artifact merging, and atomic storage writes."""

from __future__ import annotations

import os
import tempfile
from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd
from pandas.errors import EmptyDataError

DEFAULT_GARMIN_LOOKBACK_DAYS = 30
DEFAULT_GARMIN_SYNC_OVERLAP_DAYS = 2
DEFAULT_GARMIN_OUTPUT_PATH = "/opt/airflow/csvs/garmin_daily.csv"
DEFAULT_GARMIN_ACTIVITY_OUTPUT_PATH = "/opt/airflow/csvs/garmin_activities.csv"
DEFAULT_GARMIN_HEART_RATE_OUTPUT_PATH = "/opt/airflow/csvs/garmin_heart_rate_detail.csv"

def is_garmin_enabled() -> bool:
    """Return whether Garmin ingestion is enabled.

    Returns:
        bool: True when Garmin ingestion is enabled.
    """
    return str(os.getenv("GARMIN_ENABLED", "false")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

def get_garmin_lookback_days() -> int:
    """Resolve the Garmin lookback window from environment configuration.

    Returns:
        int: Positive number of lookback days.

    Raises:
        ValueError: If the configured lookback is not a positive integer.
    """
    raw_value = os.getenv("GARMIN_LOOKBACK_DAYS", str(DEFAULT_GARMIN_LOOKBACK_DAYS))
    lookback_days = int(raw_value)
    if lookback_days <= 0:
        raise ValueError("`GARMIN_LOOKBACK_DAYS` must be a positive integer.")
    return lookback_days

def get_garmin_historical_start_date(
    end_date: Optional[date] = None,
    fallback_lookback_days: Optional[int] = None,
) -> date:
    """Resolve the Garmin historical start date.

    Args:
        end_date (Optional[date]): Optional upper bound for validation.
        fallback_lookback_days (Optional[int]): Backward-compatible fallback
            lookback window when no explicit historical start date is set.

    Returns:
        date: Historical sync start date.

    Raises:
        ValueError: If the configured date is invalid or in the future.
    """
    effective_end_date = end_date or date.today()
    raw_value = os.getenv("GARMIN_HISTORICAL_START_DATE")
    if raw_value:
        try:
            historical_start_date = date.fromisoformat(raw_value)
        except ValueError as exc:
            raise ValueError(
                "`GARMIN_HISTORICAL_START_DATE` must be a valid ISO date (YYYY-MM-DD)."
            ) from exc
        if historical_start_date > effective_end_date:
            raise ValueError(
                "`GARMIN_HISTORICAL_START_DATE` cannot be later than the sync end date."
            )
        return historical_start_date

    resolved_lookback_days = fallback_lookback_days or get_garmin_lookback_days()
    return effective_end_date - timedelta(days=resolved_lookback_days - 1)

def get_garmin_sync_overlap_days() -> int:
    """Resolve the Garmin overlap re-fetch window.

    Returns:
        int: Positive overlap window in days.

    Raises:
        ValueError: If the configured overlap is not a positive integer.
    """
    raw_value = os.getenv(
        "GARMIN_SYNC_OVERLAP_DAYS",
        str(DEFAULT_GARMIN_SYNC_OVERLAP_DAYS),
    )
    overlap_days = int(raw_value)
    if overlap_days <= 0:
        raise ValueError("`GARMIN_SYNC_OVERLAP_DAYS` must be a positive integer.")
    return overlap_days

def is_garmin_force_full_refresh() -> bool:
    """Return whether Garmin history should be rebuilt from scratch.

    Returns:
        bool: True when a full refresh was explicitly requested.
    """
    return str(os.getenv("GARMIN_FORCE_FULL_REFRESH", "false")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

def build_date_range(
    lookback_days: int,
    end_date: Optional[date] = None,
) -> list[str]:
    """Build an inclusive list of ISO date strings for Garmin fetches.

    Args:
        lookback_days (int): Number of days to include.
        end_date (Optional[date]): Optional end date override.

    Returns:
        list[str]: Ordered ISO date strings from oldest to newest.

    Raises:
        ValueError: If `lookback_days` is not positive.
    """
    if lookback_days <= 0:
        raise ValueError("`lookback_days` must be positive.")

    effective_end_date = end_date or date.today()
    start_date = effective_end_date - timedelta(days=lookback_days - 1)
    return build_date_range_from_bounds(start_date, effective_end_date)

def build_date_range_from_bounds(start_date: date, end_date: date) -> list[str]:
    """Build an inclusive list of ISO dates between two date bounds.

    Args:
        start_date (date): Inclusive start date.
        end_date (date): Inclusive end date.

    Returns:
        list[str]: Ordered ISO date strings from oldest to newest.

    Raises:
        ValueError: If the date bounds are invalid.
    """
    if start_date > end_date:
        raise ValueError("`start_date` cannot be later than `end_date`.")
    return [
        (start_date + timedelta(days=offset)).isoformat()
        for offset in range((end_date - start_date).days + 1)
    ]

def build_supporting_output_paths(output_path: str) -> dict[str, str]:
    """Resolve sibling output paths for Garmin detail artifacts.

    Args:
        output_path (str): Primary Garmin daily CSV path.

    Returns:
        dict[str, str]: Activity and heart-rate artifact paths.
    """
    output_dir = os.path.dirname(output_path) or os.path.dirname(DEFAULT_GARMIN_OUTPUT_PATH)
    return {
        "activities": os.path.join(
            output_dir,
            os.path.basename(DEFAULT_GARMIN_ACTIVITY_OUTPUT_PATH),
        ),
        "heart_rate": os.path.join(
            output_dir,
            os.path.basename(DEFAULT_GARMIN_HEART_RATE_OUTPUT_PATH),
        ),
    }

def load_existing_garmin_daily(file_path: str) -> Optional[pd.DataFrame]:
    """Load an existing Garmin daily artifact when present.

    Args:
        file_path (str): Garmin daily CSV path.

    Returns:
        Optional[pd.DataFrame]: Existing Garmin daily dataframe, if present.

    Raises:
        ValueError: If the existing artifact is malformed.
    """
    frame = _load_existing_csv(file_path)
    if frame is None:
        return None
    if frame.empty:
        return pd.DataFrame(columns=["Date"])
    if "Date" not in frame.columns:
        raise ValueError("Existing Garmin daily CSV must include a `Date` column.")
    _validate_iso_date_series(frame["Date"], "Existing Garmin daily CSV `Date`")
    return frame

def load_existing_garmin_detail_artifact(file_path: str) -> Optional[pd.DataFrame]:
    """Load an existing Garmin detail artifact when present.

    Args:
        file_path (str): Garmin detail CSV path.

    Returns:
        Optional[pd.DataFrame]: Existing detail dataframe, if present.
    """
    return _load_existing_csv(file_path)

def resolve_garmin_sync_start_date(
    existing_daily: Optional[pd.DataFrame],
    historical_start_date: date,
    overlap_days: int,
    force_full_refresh: bool = False,
) -> date:
    """Resolve the start date for the next Garmin sync window.

    Args:
        existing_daily (Optional[pd.DataFrame]): Existing Garmin daily history.
        historical_start_date (date): Lower bound for historical backfill.
        overlap_days (int): Overlap window for re-fetching recent days.
        force_full_refresh (bool): Whether to ignore existing history.

    Returns:
        date: Inclusive sync start date.

    Raises:
        ValueError: If the overlap is invalid or the existing history is malformed.
    """
    if overlap_days <= 0:
        raise ValueError("`overlap_days` must be positive.")
    if force_full_refresh or existing_daily is None or existing_daily.empty:
        return historical_start_date
    if "Date" not in existing_daily.columns:
        raise ValueError("Existing Garmin daily CSV must include a `Date` column.")

    parsed_dates = _validate_iso_date_series(
        existing_daily["Date"],
        "Existing Garmin daily CSV `Date`",
    )
    last_stored_date = parsed_dates.max().date()
    return max(historical_start_date, last_stored_date - timedelta(days=overlap_days))

def merge_garmin_daily(
    existing_df: Optional[pd.DataFrame],
    new_df: Optional[pd.DataFrame],
) -> pd.DataFrame:
    """Merge Garmin daily history and recompute weekly rollups.

    Args:
        existing_df (Optional[pd.DataFrame]): Existing Garmin daily history.
        new_df (Optional[pd.DataFrame]): Newly fetched Garmin daily rows.

    Returns:
        pd.DataFrame: Consolidated Garmin daily dataset.

    Raises:
        ValueError: If the merged artifact lacks a `Date` column.
    """
    combined = _concat_frames(existing_df, new_df)
    if combined.empty:
        return combined
    if "Date" not in combined.columns:
        raise ValueError("Merged Garmin daily CSV must include a `Date` column.")

    parsed_dates = _validate_iso_date_series(combined["Date"], "Garmin daily `Date`")
    combined = combined.copy()
    combined["Date"] = parsed_dates.dt.strftime("%Y-%m-%d")
    combined = combined.sort_values("Date").drop_duplicates(subset=["Date"], keep="last")
    combined = combined.reset_index(drop=True)
    return recompute_garmin_weekly_rollups(combined)

def merge_garmin_activities(
    existing_df: Optional[pd.DataFrame],
    new_df: Optional[pd.DataFrame],
) -> pd.DataFrame:
    """Merge Garmin activity-session artifacts using stable dedupe keys.

    Args:
        existing_df (Optional[pd.DataFrame]): Existing activity artifact.
        new_df (Optional[pd.DataFrame]): Newly fetched activity rows.

    Returns:
        pd.DataFrame: Consolidated Garmin activity artifact.

    Raises:
        ValueError: If the merged artifact lacks a `Date` column.
    """
    combined = _concat_frames(existing_df, new_df)
    if combined.empty:
        return combined
    if "Date" not in combined.columns:
        raise ValueError("Merged Garmin activities CSV must include a `Date` column.")

    combined = combined.copy()
    _validate_iso_date_series(combined["Date"], "Garmin activities `Date`")
    combined["Date"] = pd.Series(combined["Date"], copy=False).astype(str)
    combined["__merge_key"] = combined.apply(_build_activity_merge_key, axis=1)
    combined = combined.sort_values(
        by=[column for column in ["Date", "garmin_activity_start_time", "garmin_activity_id"] if column in combined.columns],
        na_position="last",
    )
    combined = combined.drop_duplicates(subset=["__merge_key"], keep="last")
    combined = combined.drop(columns=["__merge_key"]).reset_index(drop=True)
    return combined

def merge_garmin_heart_rate_detail(
    existing_df: Optional[pd.DataFrame],
    new_df: Optional[pd.DataFrame],
) -> pd.DataFrame:
    """Merge Garmin heart-rate detail artifacts using timestamp identity.

    Args:
        existing_df (Optional[pd.DataFrame]): Existing heart-rate artifact.
        new_df (Optional[pd.DataFrame]): Newly fetched heart-rate rows.

    Returns:
        pd.DataFrame: Consolidated Garmin heart-rate detail artifact.

    Raises:
        ValueError: If the merged artifact lacks required key columns.
    """
    combined = _concat_frames(existing_df, new_df)
    if combined.empty:
        return combined
    required_columns = {"Date", "garmin_hr_timestamp"}
    if not required_columns.issubset(set(combined.columns)):
        raise ValueError(
            "Merged Garmin heart-rate detail CSV must include `Date` and `garmin_hr_timestamp`."
        )

    combined = combined.copy()
    _validate_iso_date_series(combined["Date"], "Garmin heart-rate detail `Date`")
    combined["Date"] = pd.Series(combined["Date"], copy=False).astype(str)
    combined["__merge_key"] = (
        combined["Date"].fillna("")
        + "::"
        + combined["garmin_hr_timestamp"].fillna("").astype(str)
    )
    combined = combined.sort_values(
        by=[column for column in ["Date", "garmin_hr_timestamp"] if column in combined.columns],
        na_position="last",
    )
    combined = combined.drop_duplicates(subset=["__merge_key"], keep="last")
    combined = combined.drop(columns=["__merge_key"]).reset_index(drop=True)
    return combined

def recompute_garmin_weekly_rollups(garmin_daily: pd.DataFrame) -> pd.DataFrame:
    """Recompute rolling Garmin weekly summary fields for the full history.

    Args:
        garmin_daily (pd.DataFrame): Garmin daily history.

    Returns:
        pd.DataFrame: Daily history with refreshed weekly rollups.
    """
    if garmin_daily.empty:
        return garmin_daily

    recomputed = garmin_daily.copy()
    recomputed = recomputed.sort_values("Date").reset_index(drop=True)
    for column_name in [
        "garmin_steps",
        "garmin_avg_stress",
        "garmin_intensity_moderate_min",
        "garmin_intensity_vigorous_min",
    ]:
        if column_name not in recomputed.columns:
            recomputed[column_name] = np.nan
        recomputed[column_name] = pd.to_numeric(recomputed[column_name], errors="coerce")

    recomputed["garmin_weekly_steps"] = recomputed["garmin_steps"].rolling(7, min_periods=1).sum()
    recomputed["garmin_weekly_avg_stress"] = recomputed["garmin_avg_stress"].rolling(7, min_periods=1).mean()
    total_intensity = (
        recomputed["garmin_intensity_moderate_min"].fillna(0)
        + recomputed["garmin_intensity_vigorous_min"].fillna(0)
    )
    recomputed["garmin_weekly_intensity_min"] = total_intensity.rolling(7, min_periods=1).sum()
    return recomputed

def write_dataframe_atomically(frame: pd.DataFrame, file_path: str) -> None:
    """Write a dataframe to CSV atomically using a temporary file.

    Args:
        frame (pd.DataFrame): Dataframe to persist.
        file_path (str): Final CSV destination.

    Returns:
        None
    """
    parent_dir = os.path.dirname(file_path) or "."
    os.makedirs(parent_dir, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
        suffix=".csv",
        prefix=".garmin_tmp_",
        dir=parent_dir,
        delete=False,
    ) as temp_file:
        temp_path = temp_file.name
    try:
        frame.to_csv(temp_path, index=False)
        os.replace(temp_path, file_path)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise

def _load_existing_csv(file_path: str) -> Optional[pd.DataFrame]:
    """Load an existing CSV artifact when present.

    Args:
        file_path (str): CSV path.

    Returns:
        Optional[pd.DataFrame]: Parsed dataframe, empty dataframe, or None.
    """
    if not os.path.exists(file_path):
        return None
    try:
        return pd.read_csv(file_path)
    except EmptyDataError:
        return pd.DataFrame()

def _concat_frames(
    existing_df: Optional[pd.DataFrame],
    new_df: Optional[pd.DataFrame],
) -> pd.DataFrame:
    """Concatenate existing and new artifact frames while preserving all columns.

    Args:
        existing_df (Optional[pd.DataFrame]): Existing artifact dataframe.
        new_df (Optional[pd.DataFrame]): Newly fetched artifact dataframe.

    Returns:
        pd.DataFrame: Combined dataframe.
    """
    frames = [
        frame.copy()
        for frame in [existing_df, new_df]
        if frame is not None and not frame.empty
    ]
    if not frames:
        if new_df is not None:
            return new_df.copy()
        if existing_df is not None:
            return existing_df.copy()
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True, sort=False)

def _validate_iso_date_series(series: pd.Series, label: str) -> pd.Series:
    """Validate that a series contains parseable ISO-like dates.

    Args:
        series (pd.Series): Candidate date series.
        label (str): Human-readable label for error messages.

    Returns:
        pd.Series: Parsed datetime series.

    Raises:
        ValueError: If any values cannot be parsed as dates.
    """
    parsed = pd.to_datetime(series, errors="coerce")
    if parsed.isna().any():
        raise ValueError(f"{label} contains invalid date values.")
    return parsed

def _build_activity_merge_key(row: pd.Series) -> str:
    """Build a stable dedupe key for one Garmin activity row.

    Args:
        row (pd.Series): Activity row.

    Returns:
        str: Stable dedupe key.
    """
    activity_id = row.get("garmin_activity_id")
    if pd.notna(activity_id) and str(activity_id).strip() != "":
        return f"activity_id::{activity_id}"

    # Reason: Some Garmin summaries may lack a durable activity id, so we fall
    # back to a composite identity that remains stable across overlap re-fetches.
    return "::".join(
        [
            str(row.get("Date", "") or ""),
            str(row.get("garmin_activity_start_time", "") or ""),
            str(row.get("garmin_activity_name", "") or ""),
            str(row.get("garmin_activity_type", "") or ""),
            str(row.get("garmin_activity_duration_min", "") or ""),
        ]
    )
