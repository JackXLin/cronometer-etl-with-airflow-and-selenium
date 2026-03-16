"""Tests for Garmin-specific report rendering helpers."""

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dags"))

from visualisation_garmin import (
    build_garmin_adherence_insights,
    has_garmin_report_data,
    page_garmin_context,
)


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
def sample_garmin_processed() -> pd.DataFrame:
    """Build processed-style data with Garmin context for report tests.

    Returns:
        pd.DataFrame: Synthetic processed dataset with Garmin metrics.
    """
    n_days = 56
    dates = pd.date_range("2025-01-01", periods=n_days, freq="D")
    energy = np.where(np.arange(n_days) % 2 == 0, 1950, 2250)
    sleep_seconds = np.where(np.arange(n_days) % 2 == 0, 8 * 3600, 6 * 3600)
    stress = np.where(np.arange(n_days) % 2 == 0, 20, 35)
    return pd.DataFrame(
        {
            "Date": dates,
            "Energy (kcal)": energy,
            "On_track_calories": energy <= 2000,
            "garmin_steps": np.linspace(7000, 12000, n_days),
            "garmin_sleep_seconds": sleep_seconds,
            "garmin_avg_stress": stress,
            "garmin_body_battery_max": np.linspace(70, 90, n_days),
            "garmin_body_battery_min": np.linspace(20, 40, n_days),
            "garmin_resting_hr_bpm": np.linspace(56, 50, n_days),
            "garmin_intensity_moderate_min": np.full(n_days, 25),
            "garmin_intensity_vigorous_min": np.full(n_days, 8),
            "garmin_activity_count": np.where(np.arange(n_days) % 3 == 0, 2, 1),
        }
    )


class TestHasGarminReportData:
    """Tests for Garmin report-data detection."""

    def test_expected_use_detects_available_garmin_columns(
        self,
        sample_garmin_processed: pd.DataFrame,
    ) -> None:
        """Should return True when Garmin metrics are present.

        Returns:
            None
        """
        assert has_garmin_report_data(sample_garmin_processed) is True


class TestPageGarminContext:
    """Tests for the Garmin context report page."""

    def test_expected_use_renders_garmin_context_page(
        self,
        sample_garmin_processed: pd.DataFrame,
    ) -> None:
        """Should render the Garmin context page with expected panel titles.

        Returns:
            None
        """
        pdf = DummyPdf()

        page_garmin_context(pdf, sample_garmin_processed, target_calories=2000)

        assert len(pdf.figures) == 1
        titles = {axis.get_title() for axis in pdf.figures[0].axes if axis.get_title()}
        assert "Weekly Activity Summary" in titles
        assert "Recovery Trends: Sleep & Stress" in titles
        assert "Body Battery & Resting HR" in titles
        insights = build_garmin_adherence_insights(sample_garmin_processed, 2000)
        assert any(line.startswith("Sleep:") for line in insights)

    def test_edge_case_partial_garmin_data_still_renders(
        self,
        sample_garmin_processed: pd.DataFrame,
    ) -> None:
        """Should render even when only a subset of Garmin metrics exists.

        Returns:
            None
        """
        partial = sample_garmin_processed[
            [
                "Date",
                "Energy (kcal)",
                "On_track_calories",
                "garmin_sleep_seconds",
                "garmin_avg_stress",
            ]
        ].copy()
        pdf = DummyPdf()

        page_garmin_context(pdf, partial, target_calories=2000)

        assert len(pdf.figures) == 1

    def test_failure_case_without_garmin_columns_raises_value_error(self) -> None:
        """Should reject datasets without Garmin report metrics.

        Returns:
            None
        """
        invalid = pd.DataFrame(
            {
                "Date": pd.date_range("2025-01-01", periods=3, freq="D"),
                "Energy (kcal)": [2000, 2100, 2200],
            }
        )
        pdf = DummyPdf()

        with pytest.raises(ValueError):
            page_garmin_context(pdf, invalid, target_calories=2000)
