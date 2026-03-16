"""
Tests for the visualisation_helpers_v2 module.

Covers:
    - compute_dynamic_ylim: dynamic y-axis limits
    - compute_healthy_bmi_range: BMI-based weight band
    - compute_intake_consistency: coefficient of variation
    - build_weekly_summary_table: weekly summary table
    - compute_day_of_week_stats: day-of-week statistics
    - build_strongest_driver_callout: correlation callout text
    - build_tdee_summary_text: TDEE summary text builder
"""

import sys
import os
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dags"))

from visualisation_helpers import prepare_metrics
from visualisation_helpers_v2 import (
    compute_dynamic_ylim,
    compute_healthy_bmi_range,
    compute_intake_consistency,
    build_weekly_summary_table,
    compute_day_of_week_stats,
    build_strongest_driver_callout,
    build_tdee_summary_text,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture()
def sample_df():
    """
    Minimal DataFrame matching the schema produced by process_csv.
    60 days of synthetic nutrition + weight data for broader coverage.
    """
    n = 60
    rng = np.random.default_rng(42)
    dates = pd.date_range("2025-01-01", periods=n, freq="D")
    weight = 85.0 + np.cumsum(rng.normal(-0.05, 0.3, n))
    return pd.DataFrame({
        "Date": dates,
        "Energy (kcal)": rng.normal(2200, 200, n).clip(1500),
        "Protein (g)": rng.normal(120, 20, n).clip(50),
        "Carbs (g)": rng.normal(250, 40, n).clip(100),
        "Fat (g)": rng.normal(80, 15, n).clip(30),
        "Fiber (g)": rng.normal(25, 5, n).clip(10),
        "Sodium (mg)": rng.normal(2000, 400, n).clip(500),
        "Water (g)": rng.normal(2500, 500, n).clip(1000),
        "Weight (kg)": weight,
        "Daily Weight change (kg)": np.append(np.diff(weight), [0.0]),
        "Energy 7 days avg (kcal)": pd.Series(
            rng.normal(2200, 200, n).clip(1500)
        ).rolling(7).mean().values,
        "Energy 30 days avg (kcal)": pd.Series(
            rng.normal(2200, 200, n).clip(1500)
        ).rolling(30).mean().values,
    })


@pytest.fixture()
def prepared_df(sample_df):
    """Sample DataFrame with metrics already prepared."""
    return prepare_metrics(sample_df, 175.0, 70.0, 2000, 0.1)


# ---------------------------------------------------------------------------
# compute_dynamic_ylim
# ---------------------------------------------------------------------------
class TestComputeDynamicYlim:
    """Tests for dynamic y-axis limit computation."""

    def test_expected_use(self, sample_df):
        """Should return limits that bracket all weight values and target."""
        y_min, y_max = compute_dynamic_ylim(sample_df, 70.0)
        assert y_min < sample_df["Weight (kg)"].min()
        assert y_max > sample_df["Weight (kg)"].max()
        assert y_min <= 70.0

    def test_target_below_data(self, sample_df):
        """y_min should include target even if it's well below data."""
        y_min, _ = compute_dynamic_ylim(sample_df, 50.0)
        assert y_min < 50.0

    def test_empty_data(self):
        """Should return fallback limits when no weight data exists."""
        df = pd.DataFrame({"Weight (kg)": pd.Series(dtype=float)})
        y_min, y_max = compute_dynamic_ylim(df, 70.0)
        assert y_min < 70.0
        assert y_max > 70.0

    def test_custom_padding(self, sample_df):
        """Padding should control the gap beyond data range."""
        y_min_2, y_max_2 = compute_dynamic_ylim(sample_df, 70.0, padding=2.0)
        y_min_5, y_max_5 = compute_dynamic_ylim(sample_df, 70.0, padding=5.0)
        assert y_min_5 < y_min_2
        assert y_max_5 > y_max_2


# ---------------------------------------------------------------------------
# compute_healthy_bmi_range
# ---------------------------------------------------------------------------
class TestComputeHealthyBMIRange:
    """Tests for BMI-based healthy weight range."""

    def test_expected_use_175cm(self):
        """For 175cm, healthy range should be roughly 56.7-76.3 kg."""
        low, high = compute_healthy_bmi_range(175.0)
        assert 56.0 < low < 57.5
        assert 76.0 < high < 77.0

    def test_taller_person_wider_range(self):
        """Taller person should have higher weight limits."""
        low_short, high_short = compute_healthy_bmi_range(160.0)
        low_tall, high_tall = compute_healthy_bmi_range(190.0)
        assert low_tall > low_short
        assert high_tall > high_short

    def test_low_always_less_than_high(self):
        """Low bound should always be less than high bound."""
        for h in [150, 165, 175, 185, 200]:
            low, high = compute_healthy_bmi_range(float(h))
            assert low < high


# ---------------------------------------------------------------------------
# compute_intake_consistency
# ---------------------------------------------------------------------------
class TestComputeIntakeConsistency:
    """Tests for intake consistency (CV%) calculation."""

    def test_expected_use(self):
        """Normal variation should produce a reasonable CV%."""
        cal = pd.Series([2000, 2100, 1900, 2050, 1950])
        cv = compute_intake_consistency(cal)
        assert 0 < cv < 100

    def test_zero_variance(self):
        """Perfectly consistent intake should have CV = 0."""
        cal = pd.Series([2000, 2000, 2000, 2000])
        cv = compute_intake_consistency(cal)
        assert cv == 0.0

    def test_insufficient_data(self):
        """Fewer than 2 values should return NaN."""
        assert np.isnan(compute_intake_consistency(pd.Series([2000])))
        assert np.isnan(compute_intake_consistency(pd.Series(dtype=float)))

    def test_all_nan_returns_nan(self):
        """All-NaN series should return NaN."""
        cal = pd.Series([np.nan, np.nan, np.nan])
        assert np.isnan(compute_intake_consistency(cal))

    def test_high_variation(self):
        """Highly variable intake should have high CV%."""
        cal = pd.Series([1000, 3000, 1000, 3000])
        cv = compute_intake_consistency(cal)
        assert cv > 30


# ---------------------------------------------------------------------------
# build_weekly_summary_table
# ---------------------------------------------------------------------------
class TestBuildWeeklySummaryTable:
    """Tests for the weekly summary table builder."""

    def test_returns_dataframe(self, prepared_df):
        """Should return a DataFrame."""
        result = build_weekly_summary_table(prepared_df)
        assert isinstance(result, pd.DataFrame)

    def test_has_expected_columns(self, prepared_df):
        """Table should have Week, Avg Intake, Wt Delta, Adh % columns."""
        result = build_weekly_summary_table(prepared_df)
        for col in ["Week", "Avg Intake", "Wt Start", "Wt End",
                     "Wt Delta", "Adh %"]:
            assert col in result.columns

    def test_respects_n_weeks(self, prepared_df):
        """Should limit rows to n_weeks parameter."""
        result = build_weekly_summary_table(prepared_df, n_weeks=4)
        assert len(result) <= 4

    def test_includes_garmin_context_columns_when_available(self, prepared_df):
        """Should surface Garmin weekly context when Garmin columns exist.

        Returns:
            None
        """
        enriched = prepared_df.copy()
        enriched["garmin_steps"] = np.linspace(5000, 10000, len(enriched))
        enriched["garmin_sleep_seconds"] = 7 * 3600
        enriched["garmin_avg_stress"] = 25
        enriched["garmin_intensity_moderate_min"] = 30
        enriched["garmin_intensity_vigorous_min"] = 10
        enriched["garmin_activity_count"] = 1

        result = build_weekly_summary_table(enriched, n_weeks=2)

        for column_name in ["Steps", "Sleep h", "Stress", "Act Min", "Acts"]:
            assert column_name in result.columns

    def test_empty_dataframe(self):
        """Should handle empty input gracefully."""
        df = pd.DataFrame({
            "Date": pd.Series(dtype="datetime64[ns]"),
            "Weight (kg)": pd.Series(dtype=float),
            "Energy (kcal)": pd.Series(dtype=float),
            "On_track_calories": pd.Series(dtype=bool),
        })
        result = build_weekly_summary_table(df)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# compute_day_of_week_stats
# ---------------------------------------------------------------------------
class TestComputeDayOfWeekStats:
    """Tests for day-of-week calorie statistics."""

    def test_returns_seven_rows(self, prepared_df):
        """Should always have 7 rows (Mon-Sun)."""
        result = compute_day_of_week_stats(prepared_df)
        assert len(result) == 7

    def test_has_expected_columns(self, prepared_df):
        """Should contain Day, Mean, Median, Std, Count."""
        result = compute_day_of_week_stats(prepared_df)
        for col in ["Day", "Mean", "Median", "Std", "Count"]:
            assert col in result.columns

    def test_day_names_correct(self, prepared_df):
        """Day column should have Mon through Sun."""
        result = compute_day_of_week_stats(prepared_df)
        expected = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        assert list(result["Day"]) == expected


# ---------------------------------------------------------------------------
# build_strongest_driver_callout
# ---------------------------------------------------------------------------
class TestBuildStrongestDriverCallout:
    """Tests for the strongest correlation driver callout."""

    def test_expected_use(self):
        """Should produce a readable string mentioning the top nutrient."""
        corrs_ci = [
            {"nutrient": "Sodium (mg)", "correlation": 0.25,
             "p_value": 0.02, "significant": True,
             "ci_low": 0.05, "ci_high": 0.42, "n": 30},
        ]
        lagged = pd.DataFrame(
            {"lag_0": [{"r": 0.25, "p": 0.02, "significant": True}]},
            index=["Sodium (mg)"],
        )
        result = build_strongest_driver_callout(corrs_ci, lagged, ["Sodium (mg)"])
        assert "Sodium (mg)" in result
        assert "positively" in result
        assert "water retention" in result

    def test_empty_corrs(self):
        """Should return fallback text for empty correlations."""
        result = build_strongest_driver_callout(
            [], pd.DataFrame(), [],
        )
        assert "Insufficient" in result

    def test_non_water_nutrient(self):
        """Non-water nutrients should get 'energy balance' mechanism."""
        corrs_ci = [
            {"nutrient": "Fat (g)", "correlation": 0.15,
             "p_value": 0.1, "significant": False,
             "ci_low": -0.05, "ci_high": 0.35, "n": 30},
        ]
        lagged = pd.DataFrame(
            {"lag_0": [{"r": 0.15, "p": 0.1, "significant": False}]},
            index=["Fat (g)"],
        )
        result = build_strongest_driver_callout(corrs_ci, lagged, ["Fat (g)"])
        assert "energy balance" in result
        assert "not statistically significant" in result


# ---------------------------------------------------------------------------
# build_tdee_summary_text
# ---------------------------------------------------------------------------
class TestBuildTdeeSummaryText:
    """Tests for the TDEE dashboard summary text builder."""

    def test_expected_use(self):
        """Should produce text mentioning best estimate and recommendations."""
        estimates = {"weighted_average": 2500, "adaptive": 2550}
        result = build_tdee_summary_text(estimates, 2200)
        assert "2500" in result
        assert "Recommendations" in result

    def test_surplus_recommendation(self):
        """Surplus > 200 should trigger 'Reduce' recommendation."""
        estimates = {"weighted_average": 2000}
        result = build_tdee_summary_text(estimates, 2500)
        assert "Reduce" in result

    def test_deficit_recommendation(self):
        """Deficit > 200 should trigger 'deficit' recommendation."""
        estimates = {"weighted_average": 2500}
        result = build_tdee_summary_text(estimates, 2000)
        assert "deficit" in result

    def test_no_tdee_data(self):
        """Should produce basic text even without TDEE estimates."""
        result = build_tdee_summary_text({}, 2000)
        assert "TDEE ESTIMATION SUMMARY" in result
