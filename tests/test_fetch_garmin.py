"""Tests for Garmin daily data extraction."""

import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

# Reason: dags/ is not a package, so we add it to sys.path for test imports.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dags"))

import fetch_garmin


class FakeGarminClient:
    """Fake Garmin client exposing the endpoints used by normalization."""

    def get_user_summary(self, date_str: str):
        """Return a synthetic Garmin user summary payload.

        Args:
            date_str (str): Requested Garmin date.

        Returns:
            dict[str, int]: Synthetic summary payload.
        """
        return {
            "totalSteps": 9876,
            "totalDistanceMeters": 7654,
            "activeKilocalories": 432,
        }

    def get_sleep_data(self, date_str: str):
        """Return a synthetic Garmin sleep payload.

        Args:
            date_str (str): Requested Garmin date.

        Returns:
            dict[str, object]: Synthetic sleep payload.
        """
        return {
            "dailySleepDTO": {"sleepTimeSeconds": 25200},
            "sleepScores": {"overall": {"value": 83}},
        }

    def get_stress_data(self, date_str: str):
        """Return a synthetic Garmin stress payload.

        Args:
            date_str (str): Requested Garmin date.

        Returns:
            dict[str, int]: Synthetic stress payload.
        """
        return {"averageStressLevel": 21}

    def get_heart_rates(self, date_str: str):
        """Return a synthetic Garmin heart-rate payload.

        Args:
            date_str (str): Requested Garmin date.

        Returns:
            dict[str, int]: Synthetic heart-rate payload.
        """
        return {"restingHeartRate": 52}

    def get_intensity_minutes_data(self, date_str: str):
        """Return a synthetic Garmin intensity payload.

        Args:
            date_str (str): Requested Garmin date.

        Returns:
            dict[str, int]: Synthetic intensity payload.
        """
        return {
            "moderateIntensityMinutes": 40,
            "vigorousIntensityDurationInSeconds": 900,
        }

    def get_body_battery(self, start_date: str, end_date: str):
        """Return a synthetic Garmin body battery payload.

        Args:
            start_date (str): Requested start date.
            end_date (str): Requested end date.

        Returns:
            dict[str, list[dict[str, int]]]: Synthetic body battery payload.
        """
        return {
            "bodyBatteryValuesArray": [
                {"bodyBatteryLevel": 31},
                {"bodyBatteryLevel": 64},
                {"bodyBatteryLevel": 92},
            ]
        }

    def get_activities_by_date(self, start_date: str, end_date: str):
        """Return a synthetic Garmin activity list.

        Args:
            start_date (str): Requested start date.
            end_date (str): Requested end date.

        Returns:
            list[dict[str, int]]: Synthetic activity payload.
        """
        return [
            {"activityId": 1001},
            {"activityId": 1002},
            {"activityId": 1003},
        ]


class MinimalGarminClient:
    """Fake client exposing only the core daily endpoints."""

    def get_user_summary(self, date_str: str):
        """Return a summary payload without optional Garmin extras.

        Args:
            date_str (str): Requested Garmin date.

        Returns:
            dict[str, int]: Synthetic summary payload.
        """
        return {
            "totalSteps": 3210,
            "totalDistanceMeters": 2100,
            "activeKilocalories": 120,
        }

    def get_sleep_data(self, date_str: str):
        """Return sleep payload for edge-case coverage.

        Args:
            date_str (str): Requested Garmin date.

        Returns:
            dict[str, object]: Synthetic sleep payload.
        """
        return {"dailySleepDTO": {"sleepTimeSeconds": 21600}}

    def get_stress_data(self, date_str: str):
        """Return stress payload for edge-case coverage.

        Args:
            date_str (str): Requested Garmin date.

        Returns:
            dict[str, int]: Synthetic stress payload.
        """
        return {"averageStressLevel": 18}

    def get_heart_rates(self, date_str: str):
        """Return resting heart-rate payload for edge-case coverage.

        Args:
            date_str (str): Requested Garmin date.

        Returns:
            dict[str, int]: Synthetic heart-rate payload.
        """
        return {"restingHeartRate": 50}

    def get_intensity_minutes_data(self, date_str: str):
        """Return intensity payload for edge-case coverage.

        Args:
            date_str (str): Requested Garmin date.

        Returns:
            dict[str, int]: Synthetic intensity payload.
        """
        return {"moderateIntensityMinutes": 20}


class TestBuildDateRange:
    """Tests for Garmin date range generation."""

    def test_expected_use_returns_inclusive_ordered_dates(self) -> None:
        """Should build a contiguous oldest-to-newest ISO date range.

        Returns:
            None
        """
        result = fetch_garmin.build_date_range(3, end_date=date(2025, 1, 3))

        assert result == ["2025-01-01", "2025-01-02", "2025-01-03"]

    def test_non_positive_lookback_raises(self) -> None:
        """Should reject non-positive lookback windows.

        Returns:
            None
        """
        with pytest.raises(ValueError):
            fetch_garmin.build_date_range(0)


class TestNormalizeGarminDay:
    """Tests for Garmin payload normalization."""

    def test_expected_use_flattens_supported_metrics(self) -> None:
        """Should flatten Garmin endpoint payloads into one daily row.

        Returns:
            None
        """
        result = fetch_garmin.normalize_garmin_day(FakeGarminClient(), "2025-01-10")

        assert result["Date"] == "2025-01-10"
        assert result["garmin_steps"] == 9876
        assert result["garmin_distance_m"] == 7654
        assert result["garmin_active_calories_kcal"] == 432
        assert result["garmin_resting_hr_bpm"] == 52
        assert result["garmin_sleep_seconds"] == 25200
        assert result["garmin_sleep_score"] == 83
        assert result["garmin_avg_stress"] == 21
        assert result["garmin_body_battery_max"] == 92.0
        assert result["garmin_body_battery_min"] == 31.0
        assert result["garmin_intensity_moderate_min"] == 40.0
        assert result["garmin_intensity_vigorous_min"] == 15.0
        assert result["garmin_activity_count"] == 3

    def test_edge_case_missing_optional_endpoints_returns_none_metrics(self) -> None:
        """Should keep optional Garmin extras empty when endpoints are unavailable.

        Returns:
            None
        """
        result = fetch_garmin.normalize_garmin_day(MinimalGarminClient(), "2025-01-10")

        assert result["garmin_body_battery_max"] is None
        assert result["garmin_body_battery_min"] is None
        assert result["garmin_activity_count"] is None


class TestFetchGarminDailyData:
    """Tests for end-to-end Garmin CSV generation."""

    def test_expected_use_writes_initial_backfill_csv(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Should write one CSV row per requested date during initial backfill.

        Args:
            monkeypatch (pytest.MonkeyPatch): Pytest patch helper.
            tmp_path (Path): Temporary output directory.

        Returns:
            None
        """
        output_path = tmp_path / "garmin_daily.csv"
        class FixedDate(date):
            """Fixed date helper for deterministic fetch windows."""

            @classmethod
            def today(cls) -> date:
                """Return the fixed current date.

                Returns:
                    date: Fixed sync end date.
                """
                return cls(2025, 1, 2)

        monkeypatch.setattr(fetch_garmin, "date", FixedDate)
        monkeypatch.setattr(fetch_garmin, "load_garmin_client_from_tokens", lambda: object())
        monkeypatch.setenv("GARMIN_HISTORICAL_START_DATE", "2025-01-01")
        monkeypatch.setenv("GARMIN_SYNC_OVERLAP_DAYS", "2")
        monkeypatch.delenv("GARMIN_FORCE_FULL_REFRESH", raising=False)
        monkeypatch.setattr(
            fetch_garmin,
            "build_date_range_from_bounds",
            lambda start_date, end_date: ["2025-01-01", "2025-01-02"],
        )
        monkeypatch.setattr(
            fetch_garmin,
            "normalize_garmin_day",
            lambda client, date_str: {
                "Date": date_str,
                "garmin_steps": 1000 if date_str.endswith("01") else 2000,
            },
        )

        result = fetch_garmin.fetch_garmin_daily_data(
            lookback_days=2,
            output_path=str(output_path),
        )
        written = pd.read_csv(result)

        assert result == str(output_path)
        assert list(written["Date"]) == ["2025-01-01", "2025-01-02"]
        assert list(written["garmin_steps"]) == [1000, 2000]

    def test_edge_case_incremental_sync_merges_existing_history(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Should reuse stored Garmin history and fetch only the overlap window.

        Args:
            monkeypatch (pytest.MonkeyPatch): Pytest patch helper.
            tmp_path (Path): Temporary output directory.

        Returns:
            None
        """
        output_path = tmp_path / "garmin_daily.csv"
        pd.DataFrame(
            {
                "Date": ["2025-01-02", "2025-01-03"],
                "garmin_steps": [1200, 1300],
            }
        ).to_csv(output_path, index=False)

        class FixedDate(date):
            """Fixed date helper for deterministic fetch windows."""

            @classmethod
            def today(cls) -> date:
                """Return the fixed current date.

                Returns:
                    date: Fixed sync end date.
                """
                return cls(2025, 1, 4)

        captured_bounds: dict[str, date] = {}
        original_build_date_range = fetch_garmin.build_date_range_from_bounds

        def _capture_date_range(start_date: date, end_date: date) -> list[str]:
            """Capture resolved sync bounds before building the date list.

            Args:
                start_date (date): Inclusive sync start date.
                end_date (date): Inclusive sync end date.

            Returns:
                list[str]: Ordered sync dates.
            """
            captured_bounds["start"] = start_date
            captured_bounds["end"] = end_date
            return original_build_date_range(start_date, end_date)

        monkeypatch.setattr(fetch_garmin, "date", FixedDate)
        monkeypatch.setattr(fetch_garmin, "load_garmin_client_from_tokens", lambda: object())
        monkeypatch.setenv("GARMIN_HISTORICAL_START_DATE", "2025-01-01")
        monkeypatch.setenv("GARMIN_SYNC_OVERLAP_DAYS", "2")
        monkeypatch.delenv("GARMIN_FORCE_FULL_REFRESH", raising=False)
        monkeypatch.setattr(fetch_garmin, "build_date_range_from_bounds", _capture_date_range)
        monkeypatch.setattr(
            fetch_garmin,
            "normalize_garmin_day",
            lambda client, date_str: {
                "Date": date_str,
                "garmin_steps": {
                    "2025-01-01": 1000,
                    "2025-01-02": 2000,
                    "2025-01-03": 3000,
                    "2025-01-04": 4000,
                }[date_str],
            },
        )

        result = fetch_garmin.fetch_garmin_daily_data(output_path=str(output_path))
        written = pd.read_csv(result)

        assert captured_bounds == {
            "start": date(2025, 1, 1),
            "end": date(2025, 1, 4),
        }
        assert list(written["Date"]) == [
            "2025-01-01",
            "2025-01-02",
            "2025-01-03",
            "2025-01-04",
        ]
        assert list(written["garmin_steps"]) == [1000, 2000, 3000, 4000]

    def test_invalid_env_lookback_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should reject invalid Garmin lookback configuration.

        Args:
            monkeypatch (pytest.MonkeyPatch): Pytest patch helper.

        Returns:
            None
        """
        monkeypatch.setenv("GARMIN_LOOKBACK_DAYS", "0")

        with pytest.raises(ValueError):
            fetch_garmin.get_garmin_lookback_days()
