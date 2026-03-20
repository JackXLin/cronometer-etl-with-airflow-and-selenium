"""Tests for Garmin sync storage helpers."""

import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

# Reason: dags/ is not a package, so we add it to sys.path for test imports.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dags"))

import garmin_sync_storage


class TestHistoricalStartDate:
    """Tests for Garmin historical start-date resolution."""

    def test_expected_use_reads_explicit_historical_start_date(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Should use the explicit historical start date when configured.

        Args:
            monkeypatch (pytest.MonkeyPatch): Pytest patch helper.

        Returns:
            None
        """
        monkeypatch.setenv("GARMIN_HISTORICAL_START_DATE", "2024-01-15")

        result = garmin_sync_storage.get_garmin_historical_start_date(
            end_date=date(2025, 1, 31),
        )

        assert result == date(2024, 1, 15)

    def test_edge_case_falls_back_to_lookback_window(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Should fall back to the legacy lookback window when unset.

        Args:
            monkeypatch (pytest.MonkeyPatch): Pytest patch helper.

        Returns:
            None
        """
        monkeypatch.delenv("GARMIN_HISTORICAL_START_DATE", raising=False)

        result = garmin_sync_storage.get_garmin_historical_start_date(
            end_date=date(2025, 1, 10),
            fallback_lookback_days=3,
        )

        assert result == date(2025, 1, 8)

    def test_failure_case_invalid_historical_start_date_raises(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Should reject non-ISO historical start-date values.

        Args:
            monkeypatch (pytest.MonkeyPatch): Pytest patch helper.

        Returns:
            None
        """
        monkeypatch.setenv("GARMIN_HISTORICAL_START_DATE", "2025/01/15")

        with pytest.raises(ValueError):
            garmin_sync_storage.get_garmin_historical_start_date(
                end_date=date(2025, 1, 31),
            )


class TestResolveGarminSyncStartDate:
    """Tests for Garmin incremental sync-start resolution."""

    def test_expected_use_rewinds_from_last_stored_date(self) -> None:
        """Should sync from the last stored date minus the overlap window.

        Returns:
            None
        """
        existing_daily = pd.DataFrame(
            {
                "Date": ["2025-01-01", "2025-01-05", "2025-01-08"],
                "garmin_steps": [1000, 2000, 3000],
            }
        )

        result = garmin_sync_storage.resolve_garmin_sync_start_date(
            existing_daily=existing_daily,
            historical_start_date=date(2025, 1, 1),
            overlap_days=2,
        )

        assert result == date(2025, 1, 6)

    def test_edge_case_clamps_to_historical_start(self) -> None:
        """Should not resolve earlier than the configured historical start.

        Returns:
            None
        """
        existing_daily = pd.DataFrame(
            {
                "Date": ["2025-01-02"],
                "garmin_steps": [1000],
            }
        )

        result = garmin_sync_storage.resolve_garmin_sync_start_date(
            existing_daily=existing_daily,
            historical_start_date=date(2025, 1, 1),
            overlap_days=5,
        )

        assert result == date(2025, 1, 1)

    def test_failure_case_missing_date_column_raises(self) -> None:
        """Should fail clearly when existing Garmin history lacks `Date`.

        Returns:
            None
        """
        existing_daily = pd.DataFrame({"garmin_steps": [1000]})

        with pytest.raises(ValueError):
            garmin_sync_storage.resolve_garmin_sync_start_date(
                existing_daily=existing_daily,
                historical_start_date=date(2025, 1, 1),
                overlap_days=2,
            )


class TestMergeGarminArtifacts:
    """Tests for Garmin artifact merge and deduplication."""

    def test_expected_use_merges_daily_history_and_recomputes_weekly_rollups(self) -> None:
        """Should merge daily history, deduplicate by `Date`, and refresh rollups.

        Returns:
            None
        """
        existing_daily = pd.DataFrame(
            {
                "Date": ["2025-01-01", "2025-01-02"],
                "garmin_steps": [1000, 1500],
                "garmin_avg_stress": [20, 30],
                "garmin_intensity_moderate_min": [10, 20],
                "garmin_intensity_vigorous_min": [5, 0],
            }
        )
        new_daily = pd.DataFrame(
            {
                "Date": ["2025-01-02", "2025-01-03"],
                "garmin_steps": [2000, 3000],
                "garmin_avg_stress": [40, 50],
                "garmin_intensity_moderate_min": [25, 30],
                "garmin_intensity_vigorous_min": [5, 10],
            }
        )

        result = garmin_sync_storage.merge_garmin_daily(existing_daily, new_daily)

        assert list(result["Date"]) == ["2025-01-01", "2025-01-02", "2025-01-03"]
        assert list(result["garmin_steps"]) == [1000, 2000, 3000]
        assert list(result["garmin_weekly_steps"]) == [1000.0, 3000.0, 6000.0]
        assert list(result["garmin_weekly_intensity_min"]) == [15.0, 45.0, 85.0]

    def test_edge_case_deduplicates_activity_rows_without_activity_id(self) -> None:
        """Should use a composite key when activity ids are unavailable.

        Returns:
            None
        """
        existing_activities = pd.DataFrame(
            {
                "Date": ["2025-01-10"],
                "garmin_activity_name": ["Walk"],
                "garmin_activity_type": ["walking"],
                "garmin_activity_start_time": ["2025-01-10T07:00:00"],
                "garmin_activity_duration_min": [30.0],
            }
        )
        new_activities = pd.DataFrame(
            {
                "Date": ["2025-01-10", "2025-01-10"],
                "garmin_activity_name": ["Walk", "Run"],
                "garmin_activity_type": ["walking", "running"],
                "garmin_activity_start_time": [
                    "2025-01-10T07:00:00",
                    "2025-01-10T18:00:00",
                ],
                "garmin_activity_duration_min": [30.0, 45.0],
            }
        )

        result = garmin_sync_storage.merge_garmin_activities(
            existing_activities,
            new_activities,
        )

        assert len(result.index) == 2
        assert list(result["garmin_activity_name"]) == ["Walk", "Run"]

    def test_failure_case_missing_heart_rate_key_columns_raises(self) -> None:
        """Should reject malformed heart-rate detail artifacts.

        Returns:
            None
        """
        malformed_detail = pd.DataFrame(
            {
                "Date": ["2025-01-10"],
                "garmin_hr_bpm": [55.0],
            }
        )

        with pytest.raises(ValueError):
            garmin_sync_storage.merge_garmin_heart_rate_detail(None, malformed_detail)


class TestStorageIO:
    """Tests for Garmin artifact loading and atomic writes."""

    def test_expected_use_loads_existing_daily_csv(self, tmp_path: Path) -> None:
        """Should load an existing Garmin daily CSV when present.

        Args:
            tmp_path (Path): Temporary file directory.

        Returns:
            None
        """
        garmin_path = tmp_path / "garmin_daily.csv"
        pd.DataFrame({"Date": ["2025-01-01"], "garmin_steps": [1234]}).to_csv(
            garmin_path,
            index=False,
        )

        result = garmin_sync_storage.load_existing_garmin_daily(str(garmin_path))

        assert list(result.columns) == ["Date", "garmin_steps"]
        assert result.loc[0, "Date"] == "2025-01-01"

    def test_edge_case_atomic_write_replaces_existing_file(self, tmp_path: Path) -> None:
        """Should replace the target file atomically with the new dataframe.

        Args:
            tmp_path (Path): Temporary file directory.

        Returns:
            None
        """
        garmin_path = tmp_path / "garmin_daily.csv"
        pd.DataFrame({"Date": ["2025-01-01"], "garmin_steps": [1000]}).to_csv(
            garmin_path,
            index=False,
        )

        garmin_sync_storage.write_dataframe_atomically(
            pd.DataFrame({"Date": ["2025-01-02"], "garmin_steps": [2000]}),
            str(garmin_path),
        )
        written = pd.read_csv(garmin_path)

        assert list(written["Date"]) == ["2025-01-02"]
        assert list(written["garmin_steps"]) == [2000]

    def test_failure_case_loading_malformed_daily_csv_raises(self, tmp_path: Path) -> None:
        """Should reject existing Garmin daily artifacts without `Date`.

        Args:
            tmp_path (Path): Temporary file directory.

        Returns:
            None
        """
        garmin_path = tmp_path / "garmin_daily.csv"
        pd.DataFrame({"garmin_steps": [1234]}).to_csv(garmin_path, index=False)

        with pytest.raises(ValueError):
            garmin_sync_storage.load_existing_garmin_daily(str(garmin_path))
