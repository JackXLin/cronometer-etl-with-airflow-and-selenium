"""Build Garmin historical CSV artifacts from exported JSON files."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from pydantic import BaseModel, ConfigDict

from garmin_activity_normalization import (
    build_activity_daily_summary,
    normalize_activity_entry,
)
from garmin_daily_normalization import _extract_body_battery_bounds, _extract_nested_value
from garmin_sync_storage import (
    DEFAULT_GARMIN_OUTPUT_PATH,
    build_supporting_output_paths,
    load_existing_garmin_daily,
    load_existing_garmin_detail_artifact,
    merge_garmin_activities,
    merge_garmin_daily,
    merge_garmin_heart_rate_detail,
    write_dataframe_atomically,
)


GARMIN_ACTIVITY_COLUMNS = [
    "Date",
    "garmin_activity_id",
    "garmin_activity_name",
    "garmin_activity_type",
    "garmin_activity_group",
    "garmin_activity_start_time",
    "garmin_activity_duration_min",
    "garmin_activity_calories_kcal",
    "garmin_activity_distance_m",
    "garmin_activity_avg_hr_bpm",
    "garmin_activity_max_hr_bpm",
    "garmin_activity_training_effect",
    "garmin_activity_training_load",
]

GARMIN_HEART_RATE_DETAIL_COLUMNS = [
    "Date",
    "garmin_hr_timestamp",
    "garmin_hr_bpm",
]

GARMIN_DAILY_COLUMNS = [
    "Date",
    "garmin_steps",
    "garmin_distance_m",
    "garmin_active_calories_kcal",
    "garmin_floors_climbed",
    "garmin_resting_hr_bpm",
    "garmin_sleep_seconds",
    "garmin_sleep_score",
    "garmin_avg_stress",
    "garmin_body_battery_max",
    "garmin_body_battery_min",
    "garmin_intensity_moderate_min",
    "garmin_intensity_vigorous_min",
    "garmin_activity_count",
    "garmin_activity_duration_min",
    "garmin_activity_calories_from_sessions_kcal",
    "garmin_activity_avg_hr_bpm",
    "garmin_activity_max_hr_bpm",
    "garmin_hr_min_bpm",
    "garmin_hr_max_bpm",
    "garmin_hr_avg_bpm",
    "garmin_hrv",
    "garmin_respiration_avg",
    "garmin_spo2_avg",
    "garmin_training_readiness",
    "garmin_training_status",
]


class GarminHistoricalDailyRow(BaseModel):
    """Validated daily Garmin row built from exported Garmin JSON files."""

    model_config = ConfigDict(extra="ignore")

    Date: str
    garmin_steps: Optional[float] = None
    garmin_distance_m: Optional[float] = None
    garmin_active_calories_kcal: Optional[float] = None
    garmin_floors_climbed: Optional[float] = None
    garmin_resting_hr_bpm: Optional[float] = None
    garmin_sleep_seconds: Optional[float] = None
    garmin_sleep_score: Optional[float] = None
    garmin_avg_stress: Optional[float] = None
    garmin_body_battery_max: Optional[float] = None
    garmin_body_battery_min: Optional[float] = None
    garmin_intensity_moderate_min: Optional[float] = None
    garmin_intensity_vigorous_min: Optional[float] = None
    garmin_activity_count: Optional[int] = None
    garmin_activity_duration_min: Optional[float] = None
    garmin_activity_calories_from_sessions_kcal: Optional[float] = None
    garmin_activity_avg_hr_bpm: Optional[float] = None
    garmin_activity_max_hr_bpm: Optional[float] = None
    garmin_hr_min_bpm: Optional[float] = None
    garmin_hr_max_bpm: Optional[float] = None
    garmin_hr_avg_bpm: Optional[float] = None
    garmin_hrv: Optional[float] = None
    garmin_respiration_avg: Optional[float] = None
    garmin_spo2_avg: Optional[float] = None
    garmin_training_readiness: Optional[float] = None
    garmin_training_status: Optional[str] = None


def _read_json_file(file_path: Path) -> Any:
    """Read one JSON export file.

    Args:
        file_path (Path): JSON file path.

    Returns:
        Any: Parsed JSON payload.
    """
    return json.loads(file_path.read_text(encoding="utf-8"))


def _sorted_export_files(export_root: Path, pattern: str) -> list[Path]:
    """Resolve matching export files in deterministic order.

    Args:
        export_root (Path): Garmin export root folder.
        pattern (str): Glob pattern relative to the export root.

    Returns:
        list[Path]: Sorted matching files.
    """
    return sorted(path for path in export_root.glob(pattern) if path.is_file())


def _coerce_float(value: Any) -> Optional[float]:
    """Convert supported values into floats.

    Args:
        value (Any): Candidate numeric value.

    Returns:
        Optional[float]: Float value when conversion succeeds.
    """
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> Optional[int]:
    """Convert supported values into integers.

    Args:
        value (Any): Candidate integer value.

    Returns:
        Optional[int]: Integer value when conversion succeeds.
    """
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_datetime(value: Any) -> Optional[datetime]:
    """Convert Garmin timestamps into timezone-aware UTC datetimes.

    Args:
        value (Any): ISO string, epoch milliseconds, or epoch seconds.

    Returns:
        Optional[datetime]: Parsed UTC datetime.
    """
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if abs(timestamp) > 1_000_000_000_000:
            timestamp /= 1000.0
        return datetime.fromtimestamp(timestamp, tz=UTC)
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        iso_candidate = cleaned.replace("Z", "+00:00")
        if iso_candidate.endswith(".0"):
            iso_candidate = f"{iso_candidate[:-2]}+00:00"
        elif "T" in iso_candidate and "+" not in iso_candidate[10:] and not iso_candidate.endswith("00:00"):
            iso_candidate = f"{iso_candidate}+00:00"
        try:
            parsed = datetime.fromisoformat(iso_candidate)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    return None


def _coerce_iso_timestamp(value: Any) -> Optional[str]:
    """Convert Garmin timestamps into ISO strings.

    Args:
        value (Any): Timestamp candidate.

    Returns:
        Optional[str]: ISO-8601 timestamp when conversion succeeds.
    """
    parsed = _coerce_datetime(value)
    return parsed.isoformat() if parsed is not None else None


def _resolve_activity_date(activity_payload: dict[str, Any]) -> Optional[str]:
    """Resolve the local activity date from export payload timestamps.

    Args:
        activity_payload (dict[str, Any]): Garmin activity export payload.

    Returns:
        Optional[str]: ISO calendar date.
    """
    for key in ["startTimeLocal", "beginTimestamp", "startTimeGmt"]:
        parsed = _coerce_datetime(activity_payload.get(key))
        if parsed is not None:
            return parsed.date().isoformat()
    return None


def _extract_total_stress(record: dict[str, Any]) -> Optional[float]:
    """Extract the all-day average stress level from one UDS record.

    Args:
        record (dict[str, Any]): Aggregated Garmin wellness record.

    Returns:
        Optional[float]: All-day average stress.
    """
    aggregators = (
        record.get("allDayStress", {}).get("aggregatorList", [])
        if isinstance(record.get("allDayStress"), dict)
        else []
    )
    for aggregator in aggregators:
        if aggregator.get("type") == "TOTAL":
            return _coerce_float(aggregator.get("averageStressLevel"))
    if aggregators:
        return _coerce_float(aggregators[0].get("averageStressLevel"))
    return None


def _extract_export_body_battery_bounds(record: Optional[dict[str, Any]]) -> tuple[Optional[float], Optional[float]]:
    """Extract body battery bounds from Garmin export-specific payload shapes.

    Args:
        record (Optional[dict[str, Any]]): UDS daily record.

    Returns:
        tuple[Optional[float], Optional[float]]: Daily max and min body battery.
    """
    body_battery_payload = (record or {}).get("bodyBattery", {})
    max_value, min_value = _extract_body_battery_bounds(body_battery_payload)
    if max_value is not None or min_value is not None:
        return max_value, min_value

    stat_values = [
        _coerce_float(stat.get("statsValue"))
        for stat in body_battery_payload.get("bodyBatteryStatList", [])
        if isinstance(stat, dict)
    ]
    filtered_values = [value for value in stat_values if value is not None]
    if not filtered_values:
        return None, None
    return max(filtered_values), min(filtered_values)


def _extract_metric_value(record: Optional[dict[str, Any]], metric_type: str) -> Optional[float]:
    """Extract one typed value from a health-status export record.

    Args:
        record (Optional[dict[str, Any]]): Health-status record.
        metric_type (str): Metric type label.

    Returns:
        Optional[float]: Metric value when present.
    """
    if not record:
        return None
    for metric in record.get("metrics", []):
        if metric.get("type") == metric_type:
            return _coerce_float(metric.get("value"))
    return None


def _extract_wellness_summary_value(
    record: Optional[dict[str, Any]],
    summary_type: str,
    value_key: str = "avgValue",
) -> Optional[float]:
    """Extract one summary value from a wellness snapshot export record.

    Args:
        record (Optional[dict[str, Any]]): Wellness snapshot record.
        summary_type (str): Summary type label.
        value_key (str): Summary field to read.

    Returns:
        Optional[float]: Summary value when present.
    """
    if not record:
        return None
    for item in record.get("summaryTypeDataList", []):
        if item.get("summaryType") == summary_type:
            return _coerce_float(item.get(value_key))
    return None


def _extract_sleep_seconds(record: Optional[dict[str, Any]]) -> Optional[float]:
    """Extract total sleep seconds from one Garmin sleep export record.

    Args:
        record (Optional[dict[str, Any]]): Sleep export record.

    Returns:
        Optional[float]: Total measured sleep seconds.
    """
    if not record:
        return None
    sleep_time_seconds = _coerce_float(record.get("sleepTimeSeconds"))
    if sleep_time_seconds is not None:
        return sleep_time_seconds

    staged_values = [
        _coerce_float(record.get("deepSleepSeconds")),
        _coerce_float(record.get("lightSleepSeconds")),
        _coerce_float(record.get("remSleepSeconds")),
    ]
    if any(value is not None for value in staged_values):
        return float(sum(value or 0.0 for value in staged_values))
    return None


def _extract_respiration_from_uds(record: Optional[dict[str, Any]]) -> Optional[float]:
    """Extract daily respiration from a UDS record when available.

    Args:
        record (Optional[dict[str, Any]]): UDS export record.

    Returns:
        Optional[float]: Average respiration value.
    """
    if not record:
        return None
    respiration = record.get("respiration")
    if isinstance(respiration, (int, float, str)):
        return _coerce_float(respiration)
    if isinstance(respiration, dict):
        return _coerce_float(
            _extract_nested_value(
                respiration,
                [
                    ("averageRespiration",),
                    ("avgRespiration",),
                    ("value",),
                ],
            )
        )
    return None


def _load_uds_records(export_root: Path) -> dict[str, dict[str, Any]]:
    """Load UDS daily summary records keyed by calendar date.

    Args:
        export_root (Path): Garmin export root folder.

    Returns:
        dict[str, dict[str, Any]]: UDS records keyed by date.
    """
    records_by_date: dict[str, dict[str, Any]] = {}
    for file_path in _sorted_export_files(export_root, "DI-Connect-Aggregator/UDSFile_*.json"):
        for record in _read_json_file(file_path):
            if isinstance(record, dict) and record.get("calendarDate"):
                records_by_date[str(record["calendarDate"])] = record
    return records_by_date


def _load_sleep_records(export_root: Path) -> dict[str, dict[str, Any]]:
    """Load Garmin sleep export records keyed by calendar date.

    Args:
        export_root (Path): Garmin export root folder.

    Returns:
        dict[str, dict[str, Any]]: Sleep records keyed by date.
    """
    records_by_date: dict[str, dict[str, Any]] = {}
    for file_path in _sorted_export_files(export_root, "DI-Connect-Wellness/*_sleepData.json"):
        for record in _read_json_file(file_path):
            if isinstance(record, dict) and record.get("calendarDate"):
                records_by_date[str(record["calendarDate"])] = record
    return records_by_date


def _load_fitness_age_records(export_root: Path) -> dict[str, dict[str, Any]]:
    """Load Garmin fitness-age history keyed by date.

    Args:
        export_root (Path): Garmin export root folder.

    Returns:
        dict[str, dict[str, Any]]: Fitness-age records keyed by date.
    """
    records_by_date: dict[str, dict[str, Any]] = {}
    for file_path in _sorted_export_files(export_root, "DI-Connect-Wellness/*_fitnessAgeData.json"):
        for record in _read_json_file(file_path):
            if not isinstance(record, dict):
                continue
            as_of_date = record.get("asOfDateGmt") or record.get("rhrLastEntryDate")
            parsed = _coerce_datetime(as_of_date)
            if parsed is not None:
                records_by_date[parsed.date().isoformat()] = record
    return records_by_date


def _load_health_status_records(export_root: Path) -> dict[str, dict[str, Any]]:
    """Load Garmin health-status records keyed by date.

    Args:
        export_root (Path): Garmin export root folder.

    Returns:
        dict[str, dict[str, Any]]: Health-status records keyed by date.
    """
    records_by_date: dict[str, dict[str, Any]] = {}
    for file_path in _sorted_export_files(export_root, "DI-Connect-Wellness/*_healthStatusData.json"):
        for record in _read_json_file(file_path):
            if isinstance(record, dict) and record.get("calendarDate"):
                records_by_date[str(record["calendarDate"])] = record
    return records_by_date


def _load_wellness_snapshot_records(export_root: Path) -> dict[str, dict[str, Any]]:
    """Load daily wellness snapshot records keyed by date.

    Args:
        export_root (Path): Garmin export root folder.

    Returns:
        dict[str, dict[str, Any]]: Snapshot records keyed by date.
    """
    records_by_date: dict[str, dict[str, Any]] = {}
    for file_path in _sorted_export_files(export_root, "DI-Connect-Wellness/*_wellnessActivities.json"):
        for record in _read_json_file(file_path):
            if not isinstance(record, dict) or not record.get("calendarDate"):
                continue
            record_date = str(record["calendarDate"])
            existing_record = records_by_date.get(record_date)
            if existing_record is None:
                records_by_date[record_date] = record
                continue
            if len(record.get("summaryTypeDataList", [])) >= len(
                existing_record.get("summaryTypeDataList", [])
            ):
                records_by_date[record_date] = record
    return records_by_date


def build_export_activity_rows(export_root: Path) -> list[dict[str, Any]]:
    """Build Garmin activity rows from exported summarized-activity files.

    Args:
        export_root (Path): Garmin export root folder.

    Returns:
        list[dict[str, Any]]: Normalized Garmin activity rows.
    """
    rows: list[dict[str, Any]] = []
    for file_path in _sorted_export_files(export_root, "DI-Connect-Fitness/*_summarizedActivities.json"):
        payload = _read_json_file(file_path)
        container_list = payload if isinstance(payload, list) else [payload]
        for container in container_list:
            if not isinstance(container, dict):
                continue
            for activity in container.get("summarizedActivitiesExport", []):
                if not isinstance(activity, dict):
                    continue
                date_str = _resolve_activity_date(activity)
                if date_str is None:
                    continue
                duration_seconds = None
                if activity.get("duration") is not None:
                    duration_seconds = _coerce_float(activity.get("duration"))
                    if duration_seconds is not None:
                        duration_seconds /= 1000.0
                normalized_activity = {
                    **{
                        key: value
                        for key, value in activity.items()
                        if key not in {"duration"}
                    },
                    "activityName": activity.get("name"),
                    "averageHR": activity.get("avgHr"),
                    "maxHR": activity.get("maxHr"),
                    "startTimeLocal": _coerce_iso_timestamp(activity.get("startTimeLocal")),
                    "startTimeGMT": _coerce_iso_timestamp(activity.get("startTimeGmt")),
                    "durationInSeconds": duration_seconds,
                }
                rows.append(normalize_activity_entry(date_str, normalized_activity))
    if not rows:
        return []
    frame = pd.DataFrame(rows)
    frame = frame.reindex(columns=GARMIN_ACTIVITY_COLUMNS)
    return frame.to_dict(orient="records")


def build_garmin_daily_from_export(export_root: Path) -> pd.DataFrame:
    """Build Garmin daily history from exported Garmin JSON files.

    Args:
        export_root (Path): Garmin export root folder.

    Returns:
        pd.DataFrame: Garmin daily history.
    """
    uds_by_date = _load_uds_records(export_root)
    sleep_by_date = _load_sleep_records(export_root)
    fitness_age_by_date = _load_fitness_age_records(export_root)
    health_status_by_date = _load_health_status_records(export_root)
    wellness_by_date = _load_wellness_snapshot_records(export_root)
    activity_rows = build_export_activity_rows(export_root)
    activity_daily_summary = build_activity_daily_summary(activity_rows)
    activity_daily_map = {
        str(row["Date"]): row
        for row in activity_daily_summary.to_dict(orient="records")
        if row.get("Date")
    }
    activity_count_by_date = (
        pd.DataFrame(activity_rows).groupby("Date").size().to_dict() if activity_rows else {}
    )

    all_dates = sorted(
        set(uds_by_date)
        | set(sleep_by_date)
        | set(fitness_age_by_date)
        | set(health_status_by_date)
        | set(wellness_by_date)
        | set(activity_daily_map)
    )
    rows: list[dict[str, Any]] = []
    for date_str in all_dates:
        uds_record = uds_by_date.get(date_str)
        sleep_record = sleep_by_date.get(date_str)
        fitness_age_record = fitness_age_by_date.get(date_str)
        health_status_record = health_status_by_date.get(date_str)
        wellness_record = wellness_by_date.get(date_str)
        activity_daily_record = activity_daily_map.get(date_str, {})
        body_battery_max, body_battery_min = _extract_export_body_battery_bounds(
            uds_record
        )

        # Reason: `healthStatusData` only exists for the later export window, so we
        # fall back to older sleep and wellness snapshot sources where needed.
        row = GarminHistoricalDailyRow(
            Date=date_str,
            garmin_steps=_coerce_float((uds_record or {}).get("totalSteps")),
            garmin_distance_m=_coerce_float((uds_record or {}).get("totalDistanceMeters")),
            garmin_active_calories_kcal=_coerce_float(
                (uds_record or {}).get("activeKilocalories")
            ),
            garmin_resting_hr_bpm=_coerce_float(
                (uds_record or {}).get("restingHeartRate")
                or (uds_record or {}).get("currentDayRestingHeartRate")
                or (fitness_age_record or {}).get("rhr")
            ),
            garmin_sleep_seconds=_extract_sleep_seconds(sleep_record),
            garmin_sleep_score=_coerce_float(
                _extract_nested_value(
                    sleep_record or {},
                    [("sleepScores", "overallScore"), ("overallSleepScore",)],
                )
            ),
            garmin_avg_stress=_extract_total_stress(uds_record)
            or _extract_wellness_summary_value(wellness_record, "STRESS"),
            garmin_body_battery_max=body_battery_max,
            garmin_body_battery_min=body_battery_min,
            garmin_intensity_moderate_min=_coerce_float(
                (uds_record or {}).get("moderateIntensityMinutes")
            ),
            garmin_intensity_vigorous_min=_coerce_float(
                (uds_record or {}).get("vigorousIntensityMinutes")
            ),
            garmin_activity_count=_coerce_int(activity_count_by_date.get(date_str)),
            garmin_activity_duration_min=_coerce_float(
                activity_daily_record.get("garmin_activity_duration_min")
            ),
            garmin_activity_calories_from_sessions_kcal=_coerce_float(
                activity_daily_record.get("garmin_activity_calories_from_sessions_kcal")
            ),
            garmin_activity_avg_hr_bpm=_coerce_float(
                activity_daily_record.get("garmin_activity_avg_hr_bpm")
            ),
            garmin_activity_max_hr_bpm=_coerce_float(
                activity_daily_record.get("garmin_activity_max_hr_bpm")
            ),
            garmin_hr_min_bpm=_coerce_float((uds_record or {}).get("minHeartRate"))
            or _extract_wellness_summary_value(wellness_record, "HEART_RATE", "minValue"),
            garmin_hr_max_bpm=_coerce_float((uds_record or {}).get("maxHeartRate"))
            or _extract_wellness_summary_value(wellness_record, "HEART_RATE", "maxValue"),
            garmin_hr_avg_bpm=_extract_metric_value(health_status_record, "HR")
            or _extract_wellness_summary_value(wellness_record, "HEART_RATE"),
            garmin_hrv=_extract_metric_value(health_status_record, "HRV")
            or _extract_wellness_summary_value(wellness_record, "RMSSD_HRV"),
            garmin_respiration_avg=_extract_metric_value(health_status_record, "RESPIRATION")
            or _coerce_float((sleep_record or {}).get("averageRespiration"))
            or _extract_wellness_summary_value(wellness_record, "RESPIRATION")
            or _extract_respiration_from_uds(uds_record),
            garmin_spo2_avg=_extract_metric_value(health_status_record, "SPO2")
            or _coerce_float(
                _extract_nested_value(
                    sleep_record or {},
                    [("spo2SleepSummary", "averageSPO2"), ("averageSPO2",)],
                )
            )
            or _coerce_float((uds_record or {}).get("averageSpo2Value"))
            or _extract_wellness_summary_value(wellness_record, "SPO2"),
        )
        rows.append(row.model_dump())

    if not rows:
        return pd.DataFrame(columns=GARMIN_DAILY_COLUMNS)
    return pd.DataFrame(rows).reindex(columns=GARMIN_DAILY_COLUMNS)


def build_garmin_heart_rate_detail_from_export() -> pd.DataFrame:
    """Build Garmin heart-rate detail history from exported Garmin files.

    Returns:
        pd.DataFrame: Heart-rate detail artifact.
    """
    # Reason: The current Garmin JSON export sample does not contain intraday
    # timestamped heart-rate samples compatible with `garmin_heart_rate_detail.csv`.
    return pd.DataFrame(columns=GARMIN_HEART_RATE_DETAIL_COLUMNS)


def build_garmin_historical_artifacts(
    export_root: str | Path,
    output_path: str = DEFAULT_GARMIN_OUTPUT_PATH,
    merge_existing: bool = True,
) -> str:
    """Build and persist Garmin historical artifacts from exported Garmin JSON.

    Args:
        export_root (str | Path): Export root directory containing Garmin JSON folders.
        output_path (str): Destination path for `garmin_daily.csv`.
        merge_existing (bool): Whether to merge with existing artifacts before writing.

    Returns:
        str: Written daily artifact path.

    Raises:
        FileNotFoundError: If the Garmin export root does not exist.
    """
    export_root_path = Path(export_root)
    if not export_root_path.exists():
        raise FileNotFoundError(
            f"Garmin export root `{export_root_path}` does not exist."
        )

    supporting_paths = build_supporting_output_paths(output_path)
    imported_daily = build_garmin_daily_from_export(export_root_path)
    imported_activities = pd.DataFrame(build_export_activity_rows(export_root_path)).reindex(
        columns=GARMIN_ACTIVITY_COLUMNS
    )
    imported_heart_rate = build_garmin_heart_rate_detail_from_export()

    existing_daily = None
    existing_activities = None
    existing_heart_rate = None
    if merge_existing:
        existing_daily = load_existing_garmin_daily(output_path)
        existing_activities = load_existing_garmin_detail_artifact(
            supporting_paths["activities"]
        )
        existing_heart_rate = load_existing_garmin_detail_artifact(
            supporting_paths["heart_rate"]
        )

    garmin_daily = merge_garmin_daily(existing_daily, imported_daily)
    garmin_activities = merge_garmin_activities(existing_activities, imported_activities)
    garmin_heart_rate = merge_garmin_heart_rate_detail(
        existing_heart_rate,
        imported_heart_rate,
    )
    write_dataframe_atomically(garmin_daily, output_path)
    write_dataframe_atomically(garmin_activities, supporting_paths["activities"])
    write_dataframe_atomically(garmin_heart_rate, supporting_paths["heart_rate"])
    return output_path


def _build_argument_parser() -> argparse.ArgumentParser:
    """Create the CLI parser for historical Garmin export import.

    Returns:
        argparse.ArgumentParser: Configured CLI parser.
    """
    parser = argparse.ArgumentParser(
        description="Build Garmin historical CSV artifacts from exported JSON files.",
    )
    parser.add_argument(
        "--export-root",
        default=str(Path(__file__).resolve().parents[1] / "garmin_data"),
        help="Path to the Garmin export root folder.",
    )
    parser.add_argument(
        "--output-path",
        default=DEFAULT_GARMIN_OUTPUT_PATH,
        help="Destination path for garmin_daily.csv.",
    )
    parser.add_argument(
        "--no-merge-existing",
        action="store_true",
        help="Write only the imported export history without merging existing artifacts.",
    )
    return parser


def main() -> str:
    """Run the historical Garmin export importer CLI.

    Returns:
        str: Written Garmin daily artifact path.
    """
    parser = _build_argument_parser()
    args = parser.parse_args()
    return build_garmin_historical_artifacts(
        export_root=args.export_root,
        output_path=args.output_path,
        merge_existing=not args.no_merge_existing,
    )


if __name__ == "__main__":
    print(main())
