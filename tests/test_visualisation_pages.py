"""Tests for page-level renderers in ``visualisation_pages.py``."""

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dags"))

import visualisation_pages
from visualisation_pages import page_tdee_dashboard


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
def sample_processed() -> pd.DataFrame:
    """Build a synthetic processed DataFrame for dashboard tests.

    Returns:
        pd.DataFrame: Data with Date, Energy, Weight, and TDEE_adaptive.
    """
    n_days = 120
    rng = np.random.default_rng(7)
    dates = pd.date_range("2025-01-01", periods=n_days, freq="D")
    energy = rng.normal(3200, 250, n_days).clip(1800)
    tdee = rng.normal(3300, 150, n_days).clip(2200)
    weight = 90 + np.cumsum(rng.normal(-0.02, 0.15, n_days))

    return pd.DataFrame(
        {
            "Date": dates,
            "Energy (kcal)": energy,
            "Weight (kg)": weight,
            "TDEE_adaptive": tdee,
        }
    )


@pytest.fixture()
def sample_tdee_estimates() -> dict:
    """Build representative TDEE method estimates.

    Returns:
        dict: TDEE estimates similar to production output.
    """
    return {
        "weighted_average": 3308,
        "adaptive": 3404,
        "rolling_30d": 3408,
        "rolling_14d": 3399,
        "stable_periods": 3166,
        "regression": 3604,
        "recent_30d": 2492,
        "stable_periods_count": 88,
        "regression_r2": 0.007,
    }


class TestPageTdeeDashboard:
    """Tests for ``page_tdee_dashboard`` rendering behavior."""

    def test_expected_use_layout(self, sample_processed, sample_tdee_estimates):
        """Render should produce a 3-panel dashboard with updated sizing.

        Args:
            sample_processed (pd.DataFrame): Synthetic processed data.
            sample_tdee_estimates (dict): Synthetic TDEE estimate output.

        Returns:
            None
        """
        pdf = DummyPdf()

        page_tdee_dashboard(
            pdf,
            sample_processed,
            sample_tdee_estimates,
            target_calories=2500,
            target_weight_kg=80,
        )

        assert len(pdf.figures) == 1
        fig = pdf.figures[0]
        width, height = fig.get_size_inches()
        assert width == pytest.approx(15.0)
        assert height == pytest.approx(12.5)

        ax_bars, ax_summary, ax_intake = fig.axes
        assert ax_bars.get_title() == "TDEE Estimates by Method"
        assert ax_intake.get_title() == "Intake vs TDEE Over Last 6 Months"
        assert ax_summary.axison is False

    def test_edge_case_long_history_is_limited_to_last_six_months(
        self, sample_tdee_estimates
    ) -> None:
        """Long histories should be clipped to the last six months on the intake plot.

        Args:
            sample_tdee_estimates (dict): Synthetic TDEE estimate output.

        Returns:
            None
        """
        n_days = 365
        dates = pd.date_range("2025-01-01", periods=n_days, freq="D")
        processed = pd.DataFrame(
            {
                "Date": dates,
                "Energy (kcal)": np.linspace(2600, 3200, n_days),
                "Weight (kg)": np.linspace(92, 86, n_days),
                "TDEE_adaptive": np.linspace(3000, 2900, n_days),
            }
        )
        pdf = DummyPdf()

        page_tdee_dashboard(
            pdf,
            processed,
            sample_tdee_estimates,
            target_calories=2500,
            target_weight_kg=80,
        )

        ax_intake = pdf.figures[0].axes[2]
        plotted_dates = pd.to_datetime(ax_intake.lines[0].get_xdata())
        expected_cutoff = processed["Date"].max() - pd.DateOffset(months=6)

        assert plotted_dates.min() >= expected_cutoff
        assert plotted_dates.max() == processed["Date"].max()

    def test_edge_case_without_adaptive_series_uses_fallback_chart(
        self, sample_processed, sample_tdee_estimates
    ):
        """Missing adaptive series should trigger fallback bar comparison.

        Args:
            sample_processed (pd.DataFrame): Synthetic processed data.
            sample_tdee_estimates (dict): Synthetic TDEE estimate output.

        Returns:
            None
        """
        fallback_df = sample_processed.drop(columns=["TDEE_adaptive"])
        pdf = DummyPdf()

        page_tdee_dashboard(
            pdf,
            fallback_df,
            sample_tdee_estimates,
            target_calories=2500,
            target_weight_kg=80,
        )

        assert len(pdf.figures) == 1
        ax_intake = pdf.figures[0].axes[2]
        assert ax_intake.get_title() == "Intake vs TDEE (Last 30 Days)"

    def test_edge_case_long_summary_text_reduces_font(
        self, sample_processed, sample_tdee_estimates, monkeypatch
    ):
        """Long summary should switch to smaller font to avoid clipping.

        Args:
            sample_processed (pd.DataFrame): Synthetic processed data.
            sample_tdee_estimates (dict): Synthetic TDEE estimate output.
            monkeypatch: Pytest monkeypatch fixture.

        Returns:
            None
        """
        long_text = "\n".join([f"Line {idx}" for idx in range(20)])
        monkeypatch.setattr(
            visualisation_pages,
            "build_tdee_summary_text",
            lambda *_args, **_kwargs: long_text,
        )

        pdf = DummyPdf()
        page_tdee_dashboard(
            pdf,
            sample_processed,
            sample_tdee_estimates,
            target_calories=2500,
            target_weight_kg=80,
        )

        summary_ax = pdf.figures[0].axes[1]
        assert len(summary_ax.texts) == 1
        assert summary_ax.texts[0].get_fontsize() == 9

    def test_failure_case_missing_energy_column_raises_key_error(
        self, sample_processed, sample_tdee_estimates
    ):
        """Missing mandatory energy column should raise ``KeyError``.

        Args:
            sample_processed (pd.DataFrame): Synthetic processed data.
            sample_tdee_estimates (dict): Synthetic TDEE estimate output.

        Returns:
            None
        """
        invalid_df = sample_processed.drop(columns=["Energy (kcal)"])
        pdf = DummyPdf()

        with pytest.raises(KeyError):
            page_tdee_dashboard(
                pdf,
                invalid_df,
                sample_tdee_estimates,
                target_calories=2500,
                target_weight_kg=80,
            )
