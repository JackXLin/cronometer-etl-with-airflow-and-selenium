"""Garmin daily data extraction for the Airflow pipeline."""

import logging
from datetime import date
from time import perf_counter
from typing import Any, Dict, Optional

import pandas as pd

from garmin_activity_normalization import (
    build_activity_daily_summary,
    extract_heart_rate_detail_rows,
    fetch_activity_rows_for_date,
    summarize_heart_rate_detail_rows,
)
from garmin_client import load_garmin_client_from_tokens
from garmin_daily_normalization import (
    _call_optional_api_method,
    _call_optional_api_method_variants,
    _extract_activity_count,
    _extract_body_battery_bounds,
    _extract_duration_minutes,
    _extract_nested_value,
)
from garmin_sync_storage import (
    build_date_range,
    build_date_range_from_bounds,
    build_supporting_output_paths,
    get_garmin_historical_start_date,
    get_garmin_lookback_days,
    get_garmin_sync_overlap_days,
    is_garmin_enabled,
    is_garmin_force_full_refresh,
    load_existing_garmin_daily,
    load_existing_garmin_detail_artifact,
    merge_garmin_activities,
    merge_garmin_daily,
    merge_garmin_heart_rate_detail,
    resolve_garmin_sync_start_date,
    write_dataframe_atomically,
)


LOGGER = logging.getLogger(__name__)
DEFAULT_GARMIN_OUTPUT_PATH = "/opt/airflow/csvs/garmin_daily.csv"

def _extract_text_value(
    payload: Any,
    candidate_paths: list[tuple[str, ...]],
) -> Optional[str]:
    """Extract the first non-empty string-like value from a nested payload.

    Args:
        payload (Any): Nested Garmin payload.
        candidate_paths (list[tuple[str, ...]]): Candidate key paths.

    Returns:
        Optional[str]: Cleaned string value when available.
    """
    value = _extract_nested_value(payload, candidate_paths)
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return str(value)

def _collect_garmin_day_payloads(client: Any, date_str: str) -> Dict[str, Any]:
    """Fetch the Garmin endpoint payloads used by daily normalization.

    Args:
        client (Any): Authenticated Garmin client.
        date_str (str): ISO date string to fetch.

    Returns:
        dict[str, Any]: Raw endpoint payloads keyed by logical metric name.
    """
    return {
        "summary": _call_optional_api_method(
            client,
            ["get_user_summary", "get_stats"],
            date_str,
        )
        or {},
        "sleep": _call_optional_api_method(client, ["get_sleep_data"], date_str) or {},
        "stress": _call_optional_api_method(client, ["get_stress_data"], date_str) or {},
        "heart_rate": _call_optional_api_method(
            client,
            ["get_heart_rates", "get_rhr_day"],
            date_str,
        )
        or {},
        "intensity": _call_optional_api_method(
            client,
            ["get_intensity_minutes_data"],
            date_str,
        )
        or {},
        "body_battery": _call_optional_api_method_variants(
            client,
            ["get_body_battery"],
            ((date_str,), (date_str, date_str)),
            date_str,
        )
        or {},
        "activity": _call_optional_api_method_variants(
            client,
            ["get_activities_by_date"],
            ((date_str,), (date_str, date_str)),
            date_str,
        )
        or {},
        "respiration": _call_optional_api_method(
            client,
            ["get_respiration_data"],
            date_str,
        )
        or {},
        "spo2": _call_optional_api_method(
            client,
            ["get_spo2_data"],
            date_str,
        )
        or {},
        "hrv": _call_optional_api_method(
            client,
            ["get_hrv_data"],
            date_str,
        )
        or {},
        "training_readiness": _call_optional_api_method(
            client,
            ["get_morning_training_readiness"],
            date_str,
        )
        or {},
        "training_status": _call_optional_api_method_variants(
            client,
            ["get_training_status"],
            ((date_str,), tuple()),
            date_str,
        )
        or {},
    }

def _build_normalized_garmin_day(
    date_str: str,
    payloads: Dict[str, Any],
    activity_rows: list[dict[str, Any]],
    heart_rate_rows: list[dict[str, Any]],
) -> Dict[str, Any]:
    """Build a flat Garmin daily row from raw payloads and detail summaries.

    Args:
        date_str (str): ISO Garmin date.
        payloads (Dict[str, Any]): Endpoint payloads for the date.
        activity_rows (list[dict[str, Any]]): Activity-session rows for the day.
        heart_rate_rows (list[dict[str, Any]]): Heart-rate detail rows for the day.

    Returns:
        dict[str, Any]: Flattened daily Garmin record.
    """
    summary_payload = payloads.get("summary", {})
    sleep_payload = payloads.get("sleep", {})
    stress_payload = payloads.get("stress", {})
    heart_rate_payload = payloads.get("heart_rate", {})
    intensity_payload = payloads.get("intensity", {})
    body_battery_payload = payloads.get("body_battery", {})
    activity_payload = payloads.get("activity", {})
    respiration_payload = payloads.get("respiration", {})
    spo2_payload = payloads.get("spo2", {})
    hrv_payload = payloads.get("hrv", {})
    training_readiness_payload = payloads.get("training_readiness", {})
    training_status_payload = payloads.get("training_status", {})

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
    activity_daily_summary = build_activity_daily_summary(activity_rows)
    heart_rate_summary = summarize_heart_rate_detail_rows(heart_rate_rows)

    session_duration = None
    session_calories = None
    session_avg_hr = None
    session_max_hr = None
    if not activity_daily_summary.empty:
        summary_row = activity_daily_summary.iloc[0]
        session_duration = summary_row.get("garmin_activity_duration_min")
        session_calories = summary_row.get("garmin_activity_calories_from_sessions_kcal")
        session_avg_hr = summary_row.get("garmin_activity_avg_hr_bpm")
        session_max_hr = summary_row.get("garmin_activity_max_hr_bpm")

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
        "garmin_floors_climbed": _extract_nested_value(
            summary_payload,
            [
                ("floorsClimbed",),
                ("floorsAscended",),
                ("summary", "floorsClimbed"),
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
        "garmin_activity_duration_min": session_duration,
        "garmin_activity_calories_from_sessions_kcal": session_calories,
        "garmin_activity_avg_hr_bpm": session_avg_hr,
        "garmin_activity_max_hr_bpm": session_max_hr,
        "garmin_hr_min_bpm": heart_rate_summary.get("garmin_hr_min_bpm"),
        "garmin_hr_max_bpm": heart_rate_summary.get("garmin_hr_max_bpm"),
        "garmin_hr_avg_bpm": heart_rate_summary.get("garmin_hr_avg_bpm"),
        "garmin_hrv": _extract_nested_value(
            hrv_payload,
            [
                ("lastNightAvg",),
                ("weeklyAvg",),
                ("avgOvernightHrv",),
                ("hrvValue",),
                ("value",),
            ],
        ),
        "garmin_respiration_avg": _extract_nested_value(
            respiration_payload,
            [
                ("avgWakingRespirationValue",),
                ("avgSleepRespirationValue",),
                ("averageRespiration",),
                ("value",),
            ],
        ),
        "garmin_spo2_avg": _extract_nested_value(
            spo2_payload,
            [
                ("averageSpO2",),
                ("avgSpo2",),
                ("spo2Value",),
                ("value",),
            ],
        ),
        "garmin_training_readiness": _extract_nested_value(
            training_readiness_payload,
            [
                ("score",),
                ("value",),
                ("trainingReadinessScore",),
            ],
        ),
        "garmin_training_status": _extract_text_value(
            training_status_payload,
            [
                ("mostRecentTrainingStatus", "trainingStatusType"),
                ("trainingStatusType",),
                ("status",),
                ("value",),
            ],
        ),
    }

def normalize_garmin_day(client: Any, date_str: str) -> Dict[str, Any]:
    """Normalize Garmin API payloads into a single flat daily record.

    Args:
        client (Any): Authenticated Garmin client.
        date_str (str): ISO date string to fetch.

    Returns:
        dict[str, Any]: Flattened Garmin metrics for the requested day.
    """
    payloads = _collect_garmin_day_payloads(client, date_str)
    activity_rows = fetch_activity_rows_for_date(
        client,
        date_str,
        payloads.get("activity", {}),
    )
    heart_rate_rows = extract_heart_rate_detail_rows(
        date_str,
        payloads.get("heart_rate", {}),
    )
    return _build_normalized_garmin_day(
        date_str,
        payloads,
        activity_rows,
        heart_rate_rows,
    )

_ORIGINAL_NORMALIZE_GARMIN_DAY = normalize_garmin_day

def fetch_garmin_daily_data(
    lookback_days: Optional[int] = None,
    output_path: str = DEFAULT_GARMIN_OUTPUT_PATH,
) -> str:
    """Fetch and persist Garmin history using backfill and incremental sync.

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
    effective_end_date = date.today()
    effective_lookback_days = lookback_days or get_garmin_lookback_days()
    historical_start_date = get_garmin_historical_start_date(
        end_date=effective_end_date,
        fallback_lookback_days=effective_lookback_days,
    )
    overlap_days = get_garmin_sync_overlap_days()
    force_full_refresh = is_garmin_force_full_refresh()
    supporting_paths = build_supporting_output_paths(output_path)
    existing_daily = None
    existing_activities = None
    existing_heart_rate = None
    if not force_full_refresh:
        existing_daily = load_existing_garmin_daily(output_path)
        existing_activities = load_existing_garmin_detail_artifact(
            supporting_paths["activities"]
        )
        existing_heart_rate = load_existing_garmin_detail_artifact(
            supporting_paths["heart_rate"]
        )
    sync_start_date = resolve_garmin_sync_start_date(
        existing_daily,
        historical_start_date,
        overlap_days,
        force_full_refresh=force_full_refresh,
    )
    sync_mode = "incremental sync"
    if force_full_refresh:
        sync_mode = "forced full refresh"
    elif existing_daily is None or existing_daily.empty:
        sync_mode = "initial backfill"
    date_strings = build_date_range_from_bounds(sync_start_date, effective_end_date)
    LOGGER.info(
        "Starting Garmin %s from %s to %s into %s.",
        sync_mode,
        sync_start_date.isoformat(),
        effective_end_date.isoformat(),
        output_path,
    )
    client = load_garmin_client_from_tokens()
    LOGGER.info(
        "Garmin client restored successfully. Fetching %s date(s).",
        len(date_strings),
    )
    rows: list[dict[str, Any]] = []
    activity_rows: list[dict[str, Any]] = []
    heart_rate_rows: list[dict[str, Any]] = []
    for current_index, current_date in enumerate(date_strings, start=1):
        day_started_at = perf_counter()
        LOGGER.info(
            "Fetching Garmin data for %s (%s/%s).",
            current_date,
            current_index,
            len(date_strings),
        )
        if normalize_garmin_day is _ORIGINAL_NORMALIZE_GARMIN_DAY:
            payloads = _collect_garmin_day_payloads(client, current_date)
            current_activity_rows = fetch_activity_rows_for_date(
                client,
                current_date,
                payloads.get("activity", {}),
            )
            current_heart_rate_rows = extract_heart_rate_detail_rows(
                current_date,
                payloads.get("heart_rate", {}),
            )
            rows.append(
                _build_normalized_garmin_day(
                    current_date,
                    payloads,
                    current_activity_rows,
                    current_heart_rate_rows,
                )
            )
            activity_rows.extend(current_activity_rows)
            heart_rate_rows.extend(current_heart_rate_rows)
        else:
            rows.append(normalize_garmin_day(client, current_date))
        LOGGER.info(
            "Finished Garmin data for %s (%s/%s) in %.1f seconds.",
            current_date,
            current_index,
            len(date_strings),
            perf_counter() - day_started_at,
        )

    fetched_daily = pd.DataFrame(rows)
    fetched_activities = pd.DataFrame(activity_rows)
    fetched_heart_rate = pd.DataFrame(heart_rate_rows)
    garmin_daily = merge_garmin_daily(existing_daily, fetched_daily)
    garmin_activities = merge_garmin_activities(existing_activities, fetched_activities)
    garmin_heart_rate = merge_garmin_heart_rate_detail(
        existing_heart_rate,
        fetched_heart_rate,
    )
    write_dataframe_atomically(garmin_daily, output_path)
    write_dataframe_atomically(garmin_activities, supporting_paths["activities"])
    write_dataframe_atomically(garmin_heart_rate, supporting_paths["heart_rate"])
    LOGGER.info(
        "Wrote %s Garmin daily rows, %s Garmin activity rows, and %s Garmin heart-rate rows to %s / %s / %s.",
        len(garmin_daily.index),
        len(garmin_activities.index),
        len(garmin_heart_rate.index),
        output_path,
        supporting_paths["activities"],
        supporting_paths["heart_rate"],
    )
    return output_path
