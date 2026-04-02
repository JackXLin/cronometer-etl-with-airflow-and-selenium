"""Tests for Garmin gap-detection helpers."""

import os
import sys
from datetime import date

import pandas as pd
import pytest

# Reason: dags/ is not a package, so we add it to sys.path for test imports.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dags"))

import garmin_gap_backfill


class TestFindGarminDailyGapDates:
    """Tests for bounded Garmin historical gap detection."""

    def test_expected_use_detects_interior_hrv_gap(self) -> None:
        """Should return dates where HRV is missing between observed HRV values.

        Returns:
            None
        """
        existing_daily = pd.DataFrame(
            {
                "Date": ["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04"],
                "garmin_steps": [1000, 1100, 1200, 1300],
                "garmin_hrv": [55.0, None, 57.0, 58.0],
            }
        )

        result = garmin_gap_backfill.find_garmin_daily_gap_dates(
            existing_daily,
            historical_start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 4),
            scan_days=10,
            max_dates=10,
            min_missing_metrics=2,
        )

        assert result == ["2025-01-02"]

    def test_expected_use_detects_interior_sleep_score_gap(self) -> None:
        """Should backfill interior gaps for non-HRV priority Garmin metrics.

        Returns:
            None
        """
        existing_daily = pd.DataFrame(
            {
                "Date": ["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04"],
                "garmin_steps": [1000, 1100, 1200, 1300],
                "garmin_sleep_score": [81.0, None, 84.0, 85.0],
            }
        )

        result = garmin_gap_backfill.find_garmin_daily_gap_dates(
            existing_daily,
            historical_start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 4),
            scan_days=10,
            max_dates=10,
            min_missing_metrics=2,
        )

        assert result == ["2025-01-02"]

    def test_edge_case_skips_overlap_window_and_trailing_missing_values(self) -> None:
        """Should skip dates already covered by overlap refresh and trailing blanks.

        Returns:
            None
        """
        existing_daily = pd.DataFrame(
            {
                "Date": ["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04"],
                "garmin_steps": [1000, 1100, 1200, 1300],
                "garmin_hrv": [55.0, None, 57.0, None],
            }
        )

        result = garmin_gap_backfill.find_garmin_daily_gap_dates(
            existing_daily,
            historical_start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 4),
            overlap_start_date=date(2025, 1, 3),
            scan_days=10,
            max_dates=10,
            min_missing_metrics=2,
        )

        assert result == ["2025-01-02"]

    def test_edge_case_excludes_session_only_metric_gaps(self) -> None:
        """Should not backfill dates based only on sparse session-only metrics.

        Returns:
            None
        """
        existing_daily = pd.DataFrame(
            {
                "Date": ["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04"],
                "garmin_steps": [1000, 1100, 1200, 1300],
                "garmin_activity_duration_min": [45.0, None, 50.0, 55.0],
            }
        )

        result = garmin_gap_backfill.find_garmin_daily_gap_dates(
            existing_daily,
            historical_start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 4),
            scan_days=10,
            max_dates=10,
            min_missing_metrics=2,
        )

        assert result == []

    def test_failure_case_missing_date_column_raises(self) -> None:
        """Should fail clearly when the Garmin daily artifact lacks `Date`.

        Returns:
            None
        """
        existing_daily = pd.DataFrame({"garmin_hrv": [55.0, None, 57.0]})

        with pytest.raises(ValueError):
            garmin_gap_backfill.find_garmin_daily_gap_dates(
                existing_daily,
                historical_start_date=date(2025, 1, 1),
                end_date=date(2025, 1, 4),
            )
