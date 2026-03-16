"""Garmin daily data extraction for the Airflow pipeline."""

import logging
import os
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd

from garmin_client import load_garmin_client_from_tokens
from garmin_daily_normalization import (
    _call_optional_api_method,
    _call_optional_api_method_variants,
    _extract_activity_count,
    _extract_body_battery_bounds,
    _extract_duration_minutes,
    _extract_nested_value,
)


LOGGER = logging.getLogger(__name__)
DEFAULT_GARMIN_LOOKBACK_DAYS = 30
DEFAULT_GARMIN_OUTPUT_PATH = "/opt/airflow/csvs/garmin_daily.csv"


def is_garmin_enabled() -> bool:
    """Return whether Garmin ingestion is enabled via environment configuration.

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
    """Resolve the Garmin fetch lookback window from the environment.

    Returns:
        int: Number of daily records to fetch.

    Raises:
        ValueError: If the configured lookback is not a positive integer.
    """
    raw_value = os.getenv("GARMIN_LOOKBACK_DAYS", str(DEFAULT_GARMIN_LOOKBACK_DAYS))
    lookback_days = int(raw_value)
    if lookback_days <= 0:
        raise ValueError("`GARMIN_LOOKBACK_DAYS` must be a positive integer.")
    return lookback_days


def build_date_range(
    lookback_days: int,
    end_date: Optional[date] = None,
) -> List[str]:
    """Build an inclusive list of ISO date strings for Garmin fetches.

    Args:
        lookback_days (int): Number of days to include.
        end_date (date | None): Optional end date override.

    Returns:
        list[str]: Ordered ISO date strings from oldest to newest.

    Raises:
        ValueError: If `lookback_days` is not positive.
    """
    if lookback_days <= 0:
        raise ValueError("`lookback_days` must be positive.")

    effective_end_date = end_date or date.today()
    start_date = effective_end_date - timedelta(days=lookback_days - 1)
    return [
        (start_date + timedelta(days=offset)).isoformat()
        for offset in range(lookback_days)
    ]


def normalize_garmin_day(client: Any, date_str: str) -> Dict[str, Any]:
    """Normalize Garmin API payloads into a single flat daily record.

    Args:
        client (Any): Authenticated Garmin client.
        date_str (str): ISO date string to fetch.

    Returns:
        dict[str, Any]: Flattened Garmin metrics for the requested day.
    """
    summary_payload = _call_optional_api_method(
        client,
        ["get_user_summary", "get_stats"],
        date_str,
    ) or {}
    sleep_payload = _call_optional_api_method(client, ["get_sleep_data"], date_str) or {}
    stress_payload = _call_optional_api_method(client, ["get_stress_data"], date_str) or {}
    heart_rate_payload = _call_optional_api_method(
        client,
        ["get_heart_rates", "get_rhr_day"],
        date_str,
    ) or {}
    intensity_payload = _call_optional_api_method(
        client,
        ["get_intensity_minutes_data"],
        date_str,
    ) or {}
    body_battery_payload = _call_optional_api_method_variants(
        client,
        ["get_body_battery"],
        ((date_str,), (date_str, date_str)),
        date_str,
    ) or {}
    activity_payload = _call_optional_api_method_variants(
        client,
        ["get_activities_by_date"],
        ((date_str,), (date_str, date_str)),
        date_str,
    ) or {}

    moderate_minutes = _extract_duration_minutes(
        intensity_payload or summary_payload,
        minute_paths=[
            ("moderateIntensityMinutes",),
            ("minutes", "moderate"),
            ("moderateIntensityMinutes", "value"),
        ],
        second_paths=[
            ("moderateIntensityDurationInSeconds",),
            ("moderateIntensityDuration",),
            ("durations", "moderateSeconds"),
        ],
    )
    vigorous_minutes = _extract_duration_minutes(
        intensity_payload or summary_payload,
        minute_paths=[
            ("vigorousIntensityMinutes",),
            ("minutes", "vigorous"),
            ("vigorousIntensityMinutes", "value"),
        ],
        second_paths=[
            ("vigorousIntensityDurationInSeconds",),
            ("vigorousIntensityDuration",),
            ("durations", "vigorousSeconds"),
        ],
    )
    body_battery_max, body_battery_min = _extract_body_battery_bounds(
        body_battery_payload
    )

    return {
        "Date": date_str,
        "garmin_steps": _extract_nested_value(
            summary_payload,
            [("totalSteps",), ("steps",), ("summary", "steps")],
        ),
        "garmin_distance_m": _extract_nested_value(
            summary_payload,
            [
                ("totalDistanceMeters",),
                ("distanceInMeters",),
                ("summary", "distanceMeters"),
            ],
        ),
        "garmin_active_calories_kcal": _extract_nested_value(
            summary_payload,
            [
                ("activeKilocalories",),
                ("activeCalories",),
                ("summary", "activeKilocalories"),
            ],
        ),
        "garmin_resting_hr_bpm": _extract_nested_value(
            heart_rate_payload,
            [
                ("restingHeartRate",),
                ("statistics", "restingHeartRate"),
                ("value",),
            ],
        ),
        "garmin_sleep_seconds": _extract_nested_value(
            sleep_payload,
            [
                ("sleepTimeSeconds",),
                ("dailySleepDTO", "sleepTimeSeconds"),
                ("summary", "sleepTimeSeconds"),
            ],
        ),
        "garmin_sleep_score": _extract_nested_value(
            sleep_payload,
            [
                ("overallSleepScore",),
                ("sleepScores", "overall", "value"),
                ("dailySleepDTO", "sleepScores", "overall", "value"),
            ],
        ),
        "garmin_avg_stress": _extract_nested_value(
            stress_payload,
            [
                ("avgStressLevel",),
                ("averageStressLevel",),
                ("overallAverageStressLevel",),
                ("summary", "averageStressLevel"),
            ],
        ),
        "garmin_body_battery_max": body_battery_max,
        "garmin_body_battery_min": body_battery_min,
        "garmin_intensity_moderate_min": moderate_minutes,
        "garmin_intensity_vigorous_min": vigorous_minutes,
        "garmin_activity_count": _extract_activity_count(
            summary_payload,
            activity_payload,
        ),
    }


def fetch_garmin_daily_data(
    lookback_days: Optional[int] = None,
    output_path: str = DEFAULT_GARMIN_OUTPUT_PATH,
) -> str:
    """Fetch and persist normalized Garmin daily metrics for the recent date range.

    Args:
        lookback_days (int | None): Optional override for lookback days.
        output_path (str): Destination CSV path.

    Returns:
        str: Path to the written Garmin daily CSV.

    Raises:
        GarminBootstrapRequiredError: If reusable tokens are unavailable.
        GarminRateLimitError: If Garmin rate limits the fetch.
        GarminServiceError: If Garmin data cannot be fetched reliably.
        ValueError: If the lookback window is invalid.
    """
    effective_lookback_days = lookback_days or get_garmin_lookback_days()
    client = load_garmin_client_from_tokens()
    date_strings = build_date_range(effective_lookback_days)
    rows = [normalize_garmin_day(client, current_date) for current_date in date_strings]
    garmin_daily = pd.DataFrame(rows)
    garmin_daily.to_csv(output_path, index=False)
    LOGGER.info(
        "Wrote %s Garmin daily rows to %s.",
        len(garmin_daily.index),
        output_path,
    )
    return output_path
