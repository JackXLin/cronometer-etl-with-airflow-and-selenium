"""Tests for Garmin analytics PDF page rendering."""

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dags"))

import visualisation_garmin_analytics
from visualisation_garmin_analytics import render_garmin_analytics_pages


class DummyPdf:
    """Minimal ``PdfPages`` test double collecting saved figures."""

    def __init__(self) -> None:
        """Initialise an empty list of captured figures.

        Returns:
            None
        """
        self.figures: list = []

    def savefig(self, fig) -> None:
        """Capture a matplotlib figure instead of writing a PDF page.

        Args:
            fig: Matplotlib figure passed by the renderer.

        Returns:
            None
        """
        self.figures.append(fig)


@pytest.fixture()
def sample_processed_for_garmin_pages() -> pd.DataFrame:
    """Build Garmin-rich processed data for analytics page rendering tests.

    Returns:
        pd.DataFrame: Synthetic processed dataset.
    """
    n_days = 56
    dates = pd.date_range("2025-01-01", periods=n_days, freq="D")
    day_idx = np.arange(n_days)
    return pd.DataFrame(
        {
            "Date": dates,
            "Weight (kg)": 90 + np.cumsum(np.where(day_idx % 8 == 0, 0.3, -0.06)),
            "Daily Weight change (kg)": np.where(day_idx % 12 == 0, 0.85, np.where(day_idx % 9 == 0, -0.7, np.sin(day_idx / 5) * 0.18)),
            "Energy (kcal)": 2300 + (day_idx % 5) * 120,
            "Protein (g)": 165 + (day_idx % 4) * 7,
            "Carbs (g)": 190 + (day_idx % 6) * 18,
            "Sodium (mg)": 2300 + (day_idx % 7) * 200,
            "Water (g)": 2600 + (day_idx % 5) * 110,
            "On_track_calories": day_idx % 4 != 0,
            "TDEE_adaptive": 2550 + np.cos(day_idx / 6) * 110,
            "garmin_steps": 7500 + day_idx * 125,
            "garmin_distance_m": 5500 + day_idx * 55,
            "garmin_active_calories_kcal": 380 + (day_idx % 7) * 35,
            "garmin_resting_hr_bpm": 57 - np.sin(day_idx / 8) * 2.5,
            "garmin_sleep_seconds": 6.5 * 3600 + (day_idx % 4) * 1800,
            "garmin_sleep_score": 69 + (day_idx % 10),
            "garmin_avg_stress": 24 + (day_idx % 7) * 4,
            "garmin_body_battery_min": 20 + (day_idx % 9),
            "garmin_body_battery_max": 74 + (day_idx % 8),
            "garmin_hrv": 40 + np.cos(day_idx / 7) * 5,
            "garmin_respiration_avg": 14 + np.sin(day_idx / 7),
            "garmin_intensity_moderate_min": 26 + (day_idx % 5) * 4,
            "garmin_intensity_vigorous_min": 7 + (day_idx % 3) * 3,
        }
    )


@pytest.fixture()
def sample_activity_sessions_for_pages() -> pd.DataFrame:
    """Build Garmin activity-session data for analytics page rendering tests.

    Returns:
        pd.DataFrame: Synthetic activity-session dataset.
    """
    dates = pd.date_range("2025-01-01", periods=20, freq="2D")
    activity_types = (["running", "walking", "strength_training", "cycling", "walking"] * 4)[: len(dates)]
    return pd.DataFrame(
        {
            "Date": dates,
            "garmin_activity_id": np.arange(len(dates)) + 10,
            "garmin_activity_type": activity_types,
            "garmin_activity_duration_min": np.linspace(30, 95, len(dates)),
            "garmin_activity_calories_kcal": np.linspace(220, 700, len(dates)),
            "garmin_activity_avg_hr_bpm": np.linspace(115, 150, len(dates)),
            "garmin_activity_max_hr_bpm": np.linspace(145, 186, len(dates)),
            "garmin_activity_training_effect": np.linspace(1.8, 4.5, len(dates)),
            "garmin_activity_training_load": np.linspace(40, 130, len(dates)),
        }
    )


class TestRenderGarminAnalyticsPages:
    """Tests for the Garmin analytics PDF section."""

    def test_expected_use_renders_full_garmin_analytics_bundle(
        self,
        monkeypatch: pytest.MonkeyPatch,
        sample_processed_for_garmin_pages: pd.DataFrame,
        sample_activity_sessions_for_pages: pd.DataFrame,
    ) -> None:
        """Should render the full Garmin analytics page bundle.

        Returns:
            None
        """
        pdf = DummyPdf()
        monkeypatch.setattr(
            visualisation_garmin_analytics,
            "load_optional_garmin_activity_data",
            lambda activity_path=visualisation_garmin_analytics.DEFAULT_GARMIN_ACTIVITY_PATH: sample_activity_sessions_for_pages.copy(),
        )

        render_garmin_analytics_pages(
            pdf,
            sample_processed_for_garmin_pages,
            {"weighted_average": 2600},
        )

        assert len(pdf.figures) == 8
        titles = {
            axis.get_title()
            for figure in pdf.figures
            for axis in figure.axes
            if axis.get_title()
        }
        assert "Garmin-Adjusted TDEE Context" in titles
        assert "Lag Correlation Summary" in titles
        assert "Weight Spike Attribution Z-Scores" in titles
        assert "Weekly Activity Calories by Type" in titles
        assert "Data Coverage / Missingness Table" in titles

    def test_edge_case_without_activity_sessions_still_renders_bundle(
        self,
        monkeypatch: pytest.MonkeyPatch,
        sample_processed_for_garmin_pages: pd.DataFrame,
    ) -> None:
        """Missing activity detail CSV should still render the Garmin analytics pages.

        Returns:
            None
        """
        pdf = DummyPdf()
        monkeypatch.setattr(
            visualisation_garmin_analytics,
            "load_optional_garmin_activity_data",
            lambda activity_path=visualisation_garmin_analytics.DEFAULT_GARMIN_ACTIVITY_PATH: pd.DataFrame(),
        )

        render_garmin_analytics_pages(
            pdf,
            sample_processed_for_garmin_pages,
            {"weighted_average": 2550},
        )

        assert len(pdf.figures) == 8

    def test_failure_case_activity_loader_missing_file_returns_empty_frame(self) -> None:
        """A missing Garmin activity artifact should load as an empty DataFrame.

        Returns:
            None
        """
        result = visualisation_garmin_analytics.load_optional_garmin_activity_data(
            activity_path="Z:/definitely-missing/garmin_activities.csv",
        )

        assert result.empty is True
