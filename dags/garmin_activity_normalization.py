"""Helpers for Garmin activity-detail and heart-rate-detail normalization."""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd
from pydantic import BaseModel, ConfigDict

from garmin_daily_normalization import (
    _call_optional_api_method_variants,
    _extract_duration_minutes,
    _extract_nested_value,
    _extract_numeric_values,
)


class GarminActivityRow(BaseModel):
    """Validated Garmin activity-session row."""

    model_config = ConfigDict(extra="ignore")

    Date: str
    garmin_activity_id: Optional[int] = None
    garmin_activity_name: Optional[str] = None
    garmin_activity_type: Optional[str] = None
    garmin_activity_group: Optional[str] = None
    garmin_activity_start_time: Optional[str] = None
    garmin_activity_duration_min: Optional[float] = None
    garmin_activity_calories_kcal: Optional[float] = None
    garmin_activity_distance_m: Optional[float] = None
    garmin_activity_avg_hr_bpm: Optional[float] = None
    garmin_activity_max_hr_bpm: Optional[float] = None
    garmin_activity_training_effect: Optional[float] = None
    garmin_activity_training_load: Optional[float] = None


class GarminHeartRateDetailRow(BaseModel):
    """Validated Garmin heart-rate detail row."""

    model_config = ConfigDict(extra="ignore")

    Date: str
    garmin_hr_timestamp: str
    garmin_hr_bpm: float


ACTIVITY_LIST_PATHS = [
    ("activities",),
    ("activityList",),
    ("items",),
    ("data",),
]


ACTIVITY_NAME_PATHS = [
    ("activityName",),
    ("summaryDTO", "activityName"),
    ("metadataDTO", "activityName"),
]


ACTIVITY_TYPE_PATHS = [
    ("activityType", "typeKey"),
    ("activityType", "typeKeyLocale", "key"),
    ("activityTypeDTO", "typeKey"),
    ("activityTypeDTO", "typeKeyLocale", "key"),
    ("activityType",),
    ("activityTypeDTO",),
]


def _extract_text_value(
    payload: Any,
    candidate_paths: list[tuple[str, ...]],
) -> Optional[str]:
    """Extract the first non-empty text value across candidate paths.

    Args:
        payload (Any): Nested Garmin payload.
        candidate_paths (list[tuple[str, ...]]): Candidate text paths.

    Returns:
        Optional[str]: Cleaned text value when available.
    """
    value = _extract_nested_value(payload, candidate_paths)
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return str(value)


def _coerce_float(value: Any) -> Optional[float]:
    """Convert a value into a float when possible.

    Args:
        value (Any): Candidate numeric value.

    Returns:
        Optional[float]: Parsed float or None.
    """
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> Optional[int]:
    """Convert a value into an int when possible.

    Args:
        value (Any): Candidate integer value.

    Returns:
        Optional[int]: Parsed int or None.
    """
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _infer_activity_group(activity_type: Optional[str]) -> str:
    """Map a Garmin activity type into a report-friendly group.

    Args:
        activity_type (Optional[str]): Garmin activity type key or label.

    Returns:
        str: One of walk, run, cycling, gym/resistance training, or other.
    """
    normalized = (activity_type or "").strip().lower()
    if "walk" in normalized or normalized in {"walking", "hiking"}:
        return "walks"
    if "run" in normalized or normalized in {"trail_running", "running"}:
        return "runs"
    if "cycl" in normalized or normalized in {"road_biking", "indoor_cycling"}:
        return "cycling"
    if any(
        token in normalized
        for token in ["strength", "gym", "resistance", "weight", "cardio"]
    ):
        return "gym/resistance training"
    return "other"


def extract_activity_list(activity_payload: Any) -> list[dict[str, Any]]:
    """Extract a list of Garmin activity summaries from mixed payload shapes.

    Args:
        activity_payload (Any): Garmin activity list payload.

    Returns:
        list[dict[str, Any]]: Normalized activity summary objects.
    """
    if isinstance(activity_payload, list):
        return [item for item in activity_payload if isinstance(item, dict)]

    extracted_list = _extract_nested_value(activity_payload, ACTIVITY_LIST_PATHS)
    if isinstance(extracted_list, list):
        return [item for item in extracted_list if isinstance(item, dict)]
    return []


def normalize_activity_entry(
    date_str: str,
    summary_payload: dict[str, Any],
    detail_payload: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Flatten an activity summary/detail pair into a single session row.

    Args:
        date_str (str): ISO date for the activity session.
        summary_payload (dict[str, Any]): Activity summary payload.
        detail_payload (Optional[dict[str, Any]]): Optional activity detail payload.

    Returns:
        dict[str, Any]: Validated session row.
    """
    merged_payload = {
        **summary_payload,
        **(detail_payload or {}),
    }
    activity_type = _extract_text_value(merged_payload, ACTIVITY_TYPE_PATHS)
    row = GarminActivityRow(
        Date=date_str,
        garmin_activity_id=_coerce_int(
            _extract_nested_value(
                merged_payload,
                [("activityId",), ("summaryId",), ("id",)],
            )
        ),
        garmin_activity_name=_extract_text_value(merged_payload, ACTIVITY_NAME_PATHS),
        garmin_activity_type=activity_type,
        garmin_activity_group=_infer_activity_group(activity_type),
        garmin_activity_start_time=_extract_text_value(
            merged_payload,
            [
                ("startTimeLocal",),
                ("startTimeGMT",),
                ("summaryDTO", "startTimeLocal"),
                ("summaryDTO", "startTimeGMT"),
            ],
        ),
        garmin_activity_duration_min=_extract_duration_minutes(
            merged_payload,
            minute_paths=[
                ("duration",),
                ("durationInMinutes",),
                ("summaryDTO", "duration"),
                ("summaryDTO", "durationInMinutes"),
            ],
            second_paths=[
                ("durationInSeconds",),
                ("movingDuration",),
                ("elapsedDuration",),
                ("summaryDTO", "durationInSeconds"),
                ("summaryDTO", "movingDuration"),
            ],
        ),
        garmin_activity_calories_kcal=_coerce_float(
            _extract_nested_value(
                merged_payload,
                [
                    ("calories",),
                    ("summaryDTO", "calories"),
                    ("activityCalories",),
                ],
            )
        ),
        garmin_activity_distance_m=_coerce_float(
            _extract_nested_value(
                merged_payload,
                [
                    ("distance",),
                    ("distanceInMeters",),
                    ("summaryDTO", "distance"),
                    ("summaryDTO", "distanceInMeters"),
                ],
            )
        ),
        garmin_activity_avg_hr_bpm=_coerce_float(
            _extract_nested_value(
                merged_payload,
                [
                    ("averageHR",),
                    ("averageHeartRate",),
                    ("summaryDTO", "averageHR"),
                    ("summaryDTO", "averageHeartRate"),
                ],
            )
        ),
        garmin_activity_max_hr_bpm=_coerce_float(
            _extract_nested_value(
                merged_payload,
                [
                    ("maxHR",),
                    ("maxHeartRate",),
                    ("summaryDTO", "maxHR"),
                    ("summaryDTO", "maxHeartRate"),
                ],
            )
        ),
        garmin_activity_training_effect=_coerce_float(
            _extract_nested_value(
                merged_payload,
                [
                    ("aerobicTrainingEffect",),
                    ("trainingEffect",),
                    ("summaryDTO", "aerobicTrainingEffect"),
                ],
            )
        ),
        garmin_activity_training_load=_coerce_float(
            _extract_nested_value(
                merged_payload,
                [
                    ("activityTrainingLoad",),
                    ("trainingLoad",),
                    ("summaryDTO", "activityTrainingLoad"),
                ],
            )
        ),
    )
    return row.model_dump()


def fetch_activity_rows_for_date(
    client: Any,
    date_str: str,
    activity_payload: Any,
) -> list[dict[str, Any]]:
    """Fetch normalized Garmin activity rows for one date.

    Args:
        client (Any): Authenticated Garmin client.
        date_str (str): ISO date string.
        activity_payload (Any): Activity list payload already fetched for the date.

    Returns:
        list[dict[str, Any]]: Validated session rows.
    """
    rows: list[dict[str, Any]] = []
    for activity_summary in extract_activity_list(activity_payload):
        activity_id = _extract_nested_value(
            activity_summary,
            [("activityId",), ("summaryId",), ("id",)],
        )
        detail_payload = None
        if activity_id is not None:
            detail_payload = _call_optional_api_method_variants(
                client,
                ["get_activity_details", "get_activity"],
                ((str(activity_id),), (int(activity_id),), (int(activity_id), 0)),
                date_str,
            )
        rows.append(normalize_activity_entry(date_str, activity_summary, detail_payload))
    return rows


def build_activity_daily_summary(activity_rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Aggregate session rows into daily Garmin activity summary metrics.

    Args:
        activity_rows (list[dict[str, Any]]): Normalized activity session rows.

    Returns:
        pd.DataFrame: Daily summary keyed by Date.
    """
    if not activity_rows:
        return pd.DataFrame(columns=["Date"])

    activity_df = pd.DataFrame(activity_rows)
    if activity_df.empty:
        return pd.DataFrame(columns=["Date"])

    aggregated = (
        activity_df.groupby("Date", dropna=False)
        .agg(
            garmin_activity_duration_min=("garmin_activity_duration_min", "sum"),
            garmin_activity_calories_from_sessions_kcal=(
                "garmin_activity_calories_kcal",
                "sum",
            ),
            garmin_activity_avg_hr_bpm=("garmin_activity_avg_hr_bpm", "mean"),
            garmin_activity_max_hr_bpm=("garmin_activity_max_hr_bpm", "max"),
        )
        .reset_index()
    )
    return aggregated


def extract_heart_rate_detail_rows(
    date_str: str,
    heart_rate_payload: Any,
) -> list[dict[str, Any]]:
    """Flatten Garmin heart-rate detail payloads into timestamped rows.

    Args:
        date_str (str): ISO date string.
        heart_rate_payload (Any): Garmin heart-rate payload.

    Returns:
        list[dict[str, Any]]: Validated heart-rate detail rows.
    """
    rows: list[dict[str, Any]] = []
    if not heart_rate_payload:
        return rows

    samples = _extract_nested_value(
        heart_rate_payload,
        [
            ("heartRateValues",),
            ("heartRateValuesArray",),
            ("allMetrics",),
            ("samples",),
        ],
    )

    if isinstance(samples, list):
        for sample in samples:
            if not isinstance(sample, dict):
                continue
            timestamp = _extract_text_value(
                sample,
                [
                    ("timestampGMT",),
                    ("timestampLocal",),
                    ("calendarDate",),
                    ("time",),
                ],
            )
            bpm = _coerce_float(
                _extract_nested_value(
                    sample,
                    [
                        ("value",),
                        ("heartRate",),
                        ("bpm",),
                    ],
                )
            )
            if timestamp and bpm is not None:
                rows.append(
                    GarminHeartRateDetailRow(
                        Date=date_str,
                        garmin_hr_timestamp=timestamp,
                        garmin_hr_bpm=bpm,
                    ).model_dump()
                )
        return rows

    if isinstance(heart_rate_payload, dict):
        numeric_key_values = []
        for key, value in heart_rate_payload.items():
            if isinstance(key, str) and key.isdigit() and isinstance(value, (int, float)):
                numeric_key_values.append((key, float(value)))
        for timestamp, bpm in numeric_key_values:
            rows.append(
                GarminHeartRateDetailRow(
                    Date=date_str,
                    garmin_hr_timestamp=timestamp,
                    garmin_hr_bpm=bpm,
                ).model_dump()
            )
    return rows


def summarize_heart_rate_detail_rows(
    heart_rate_rows: list[dict[str, Any]],
) -> dict[str, Optional[float]]:
    """Summarize timestamped Garmin heart-rate rows into daily metrics.

    Args:
        heart_rate_rows (list[dict[str, Any]]): Daily heart-rate rows.

    Returns:
        dict[str, Optional[float]]: Daily min, max, and average heart rate.
    """
    if not heart_rate_rows:
        return {
            "garmin_hr_min_bpm": None,
            "garmin_hr_max_bpm": None,
            "garmin_hr_avg_bpm": None,
        }

    values = [row["garmin_hr_bpm"] for row in heart_rate_rows if row.get("garmin_hr_bpm") is not None]
    if not values:
        values = [
            value
            for value in _extract_numeric_values(heart_rate_rows, {"garmin_hr_bpm"})
            if value > 0
        ]
    if not values:
        return {
            "garmin_hr_min_bpm": None,
            "garmin_hr_max_bpm": None,
            "garmin_hr_avg_bpm": None,
        }
    return {
        "garmin_hr_min_bpm": float(min(values)),
        "garmin_hr_max_bpm": float(max(values)),
        "garmin_hr_avg_bpm": float(sum(values) / len(values)),
    }
