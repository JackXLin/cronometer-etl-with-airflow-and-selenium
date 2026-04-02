"""Tests for Garmin analytics helper computations."""

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dags"))

from garmin_report_helpers import (
    GARMIN_LAG_METRICS,
    build_activity_contribution_summary,
    build_activity_session_table,
    build_coverage_table,
    build_lag_correlation_result,
    build_outlier_diagnostic_table,
    build_regime_comparison_table,
    build_weekly_summary_table_garmin,
    prepare_garmin_report_inputs,
)


@pytest.fixture()
def sample_processed_garmin_analytics() -> pd.DataFrame:
    """Build a Garmin-rich processed dataset for analytics helper tests.

    Returns:
        pd.DataFrame: Synthetic processed dataset.
    """
    n_days = 42
    dates = pd.date_range("2025-01-01", periods=n_days, freq="D")
    day_idx = np.arange(n_days)
    return pd.DataFrame(
        {
            "Date": dates,
            "Weight (kg)": 88 + np.sin(day_idx / 6) * 0.8 + day_idx * 0.01,
            "Daily Weight change (kg)": np.where(day_idx % 11 == 0, 0.75, np.where(day_idx % 7 == 0, -0.65, np.sin(day_idx / 4) * 0.2)),
            "Energy (kcal)": 2200 + (day_idx % 5) * 110,
            "Protein (g)": 170 + (day_idx % 4) * 5,
            "Carbs (g)": 180 + (day_idx % 6) * 20,
            "Sodium (mg)": 2400 + (day_idx % 7) * 180,
            "Water (g)": 2800 + (day_idx % 5) * 140,
            "On_track_calories": day_idx % 3 != 0,
            "TDEE_adaptive": 2550 + np.cos(day_idx / 8) * 90,
            "garmin_steps": 7000 + day_idx * 130,
            "garmin_distance_m": 5200 + day_idx * 45,
            "garmin_active_calories_kcal": 420 + (day_idx % 6) * 32,
            "garmin_resting_hr_bpm": 58 - np.sin(day_idx / 8) * 3,
            "garmin_sleep_seconds": 7 * 3600 + (day_idx % 4) * 1800,
            "garmin_sleep_score": 70 + (day_idx % 8),
            "garmin_avg_stress": 22 + (day_idx % 7) * 3,
            "garmin_body_battery_min": 24 + (day_idx % 9),
            "garmin_body_battery_max": 72 + (day_idx % 8),
            "garmin_hrv": 42 + np.cos(day_idx / 5) * 6,
            "garmin_respiration_avg": 14 + np.sin(day_idx / 7),
            "garmin_intensity_moderate_min": 28 + (day_idx % 5) * 4,
            "garmin_intensity_vigorous_min": 8 + (day_idx % 3) * 2,
        }
    )


@pytest.fixture()
def sample_activity_sessions() -> pd.DataFrame:
    """Build Garmin activity session data for analytics helper tests.

    Returns:
        pd.DataFrame: Synthetic activity-session dataset.
    """
    dates = pd.date_range("2025-01-01", periods=18, freq="2D")
    session_types = [
        "running",
        "walking",
        "strength_training",
        "cycling",
        "walking",
        "running",
        "strength_training",
        "walking",
        "cycling",
    ]
    repeated_types = (session_types * 2)[: len(dates)]
    return pd.DataFrame(
        {
            "Date": dates,
            "garmin_activity_id": np.arange(len(dates)) + 100,
            "garmin_activity_type": repeated_types,
            "garmin_activity_duration_min": np.linspace(35, 85, len(dates)),
            "garmin_activity_calories_kcal": np.linspace(240, 620, len(dates)),
            "garmin_activity_avg_hr_bpm": np.linspace(118, 146, len(dates)),
            "garmin_activity_max_hr_bpm": np.linspace(148, 182, len(dates)),
            "garmin_activity_training_effect": np.linspace(2.0, 4.4, len(dates)),
            "garmin_activity_training_load": np.linspace(45, 120, len(dates)),
        }
    )


class TestPrepareGarminReportInputs:
    """Tests for Garmin report input preparation."""

    def test_expected_use_enriches_processed_with_garmin_activity_features(
        self,
        sample_processed_garmin_analytics: pd.DataFrame,
        sample_activity_sessions: pd.DataFrame,
    ) -> None:
        """Should derive Garmin helper columns and merge daily activity summaries.

        Returns:
            None
        """
        enriched, activities = prepare_garmin_report_inputs(
            sample_processed_garmin_analytics,
            sample_activity_sessions,
        )

        assert "garmin_sleep_hours" in enriched.columns
        assert "garmin_total_intensity_min" in enriched.columns
        assert "garmin_activity_proxy_kcal" in enriched.columns
        assert "Weight_trend_change_7d" in enriched.columns
        assert "garmin_activity_group" in activities.columns
        assert activities["garmin_activity_group"].isin(
            ["walks", "runs", "cycling", "gym/resistance training"]
        ).all()

    def test_edge_case_without_activity_sessions_returns_empty_activity_frame(
        self,
        sample_processed_garmin_analytics: pd.DataFrame,
    ) -> None:
        """Should still derive daily Garmin helper columns without activity data.

        Returns:
            None
        """
        enriched, activities = prepare_garmin_report_inputs(
            sample_processed_garmin_analytics,
            None,
        )

        assert activities.empty is True
        assert enriched["garmin_activity_proxy_kcal"].notna().all()


class TestLagAndOutlierAnalytics:
    """Tests for lag and outlier diagnostic helpers."""

    def test_expected_use_builds_lag_summary_for_available_metrics(
        self,
        sample_processed_garmin_analytics: pd.DataFrame,
    ) -> None:
        """Should return correlation matrix and best-lag summary rows.

        Returns:
            None
        """
        enriched, _ = prepare_garmin_report_inputs(sample_processed_garmin_analytics)
        result = build_lag_correlation_result(
            enriched,
            GARMIN_LAG_METRICS,
            "Daily Weight change (kg)",
        )

        assert result.correlation_matrix.shape[1] == 8
        assert "metric" in result.summary_table.columns
        assert "best_lag" in result.summary_table.columns
        assert result.summary_table["metric"].tolist()[0] == list(GARMIN_LAG_METRICS.keys())[0]

    def test_edge_case_missing_metric_columns_returns_nan_summary_rows(
        self,
        sample_processed_garmin_analytics: pd.DataFrame,
    ) -> None:
        """Missing metrics should remain in the output with NaN summaries.

        Returns:
            None
        """
        reduced = sample_processed_garmin_analytics[["Date", "Weight (kg)", "Daily Weight change (kg)", "Energy (kcal)", "Protein (g)", "Carbs (g)", "Sodium (mg)", "Water (g)", "On_track_calories"]].copy()
        enriched, _ = prepare_garmin_report_inputs(reduced)
        result = build_lag_correlation_result(enriched, {"steps": "garmin_steps"}, "Daily Weight change (kg)")

        assert result.summary_table.loc[0, "metric"] == "steps"
        assert pd.isna(result.summary_table.loc[0, "best_correlation"])

    def test_edge_case_sparse_recent_hrv_supports_recent_window_threshold(
        self,
        sample_processed_garmin_analytics: pd.DataFrame,
    ) -> None:
        """Sparse recent HRV should still produce recent-window correlations.

        Args:
            sample_processed_garmin_analytics (pd.DataFrame): Synthetic processed data.

        Returns:
            None
        """
        sparse = sample_processed_garmin_analytics.copy()
        sparse["garmin_hrv"] = np.nan
        recent_hrv_index = sparse.tail(6).index
        sparse.loc[recent_hrv_index, "garmin_hrv"] = np.linspace(55, 70, len(recent_hrv_index))
        enriched, _ = prepare_garmin_report_inputs(sparse)
        result = build_lag_correlation_result(
            enriched.tail(30).reset_index(drop=True),
            {"HRV": "garmin_hrv"},
            "Daily Weight change (kg)",
            min_samples=5,
        )

        assert result.correlation_matrix.loc["HRV"].notna().any()
        assert result.summary_table.loc[0, "sample_size"] >= 5

    def test_failure_case_outlier_table_returns_empty_when_no_large_weight_spikes(
        self,
        sample_processed_garmin_analytics: pd.DataFrame,
    ) -> None:
        """Without large daily weight moves, the diagnostic table should be empty.

        Returns:
            None
        """
        stable = sample_processed_garmin_analytics.copy()
        stable["Daily Weight change (kg)"] = 0.1
        enriched, _ = prepare_garmin_report_inputs(stable)
        result = build_outlier_diagnostic_table(enriched, threshold_kg=0.6)

        assert result.empty is True


class TestWeeklyActivityAndCoverageTables:
    """Tests for summary table helpers used by Garmin pages."""

    def test_expected_use_builds_weekly_activity_and_coverage_tables(
        self,
        sample_processed_garmin_analytics: pd.DataFrame,
        sample_activity_sessions: pd.DataFrame,
    ) -> None:
        """Should generate non-empty weekly, activity, and coverage tables.

        Returns:
            None
        """
        enriched, activities = prepare_garmin_report_inputs(
            sample_processed_garmin_analytics,
            sample_activity_sessions,
        )
        weekly = build_weekly_summary_table_garmin(enriched)
        contribution = build_activity_contribution_summary(activities, enriched)
        sessions = build_activity_session_table(activities, enriched)
        coverage = build_coverage_table(enriched, activities)
        regimes = build_regime_comparison_table(enriched)

        assert weekly.empty is False
        assert contribution.empty is False
        assert sessions.empty is False
        assert coverage.empty is False
        assert regimes.empty is False

    def test_edge_case_activity_summary_without_sessions_returns_empty_table(
        self,
        sample_processed_garmin_analytics: pd.DataFrame,
    ) -> None:
        """No activity sessions should yield an empty activity contribution table.

        Returns:
            None
        """
        enriched, _ = prepare_garmin_report_inputs(sample_processed_garmin_analytics)
        contribution = build_activity_contribution_summary(pd.DataFrame(), enriched)

        assert contribution.empty is True
