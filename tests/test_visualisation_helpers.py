"""
Tests for the visualisation_helpers module.

Covers:
    - get_bmi_category: WHO classification boundaries
    - prepare_metrics: derived column creation
    - compute_nutrient_correlations: correlation + significance
    - build_key_figures_table: table structure and formatting
    - _fmt: numeric formatting helper
"""

import sys
import os
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dags"))

from visualisation_helpers import (
    get_bmi_category,
    prepare_metrics,
    compute_nutrient_correlations,
    build_key_figures_table,
    _fmt,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture()
def sample_df():
    """
    Minimal DataFrame matching the schema produced by process_csv.
    30 days of synthetic nutrition + weight data.
    """
    n = 30
    rng = np.random.default_rng(42)
    dates = pd.date_range("2025-01-01", periods=n, freq="D")
    weight = 85.0 + np.cumsum(rng.normal(0, 0.3, n))
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


# ---------------------------------------------------------------------------
# get_bmi_category
# ---------------------------------------------------------------------------
class TestGetBMICategory:
    """Tests for WHO BMI classification."""

    def test_underweight(self):
        """BMI < 18.5 should be Underweight."""
        assert get_bmi_category(17.0) == "Underweight"

    def test_normal(self):
        """BMI 18.5–24.9 should be Normal."""
        assert get_bmi_category(22.0) == "Normal"

    def test_overweight(self):
        """BMI 25–29.9 should be Overweight."""
        assert get_bmi_category(27.5) == "Overweight"

    def test_obese(self):
        """BMI >= 30 should be Obese."""
        assert get_bmi_category(35.0) == "Obese"

    def test_boundary_18_5(self):
        """Exactly 18.5 should be Normal (not Underweight)."""
        assert get_bmi_category(18.5) == "Normal"

    def test_boundary_25(self):
        """Exactly 25 should be Overweight (not Normal)."""
        assert get_bmi_category(25.0) == "Overweight"

    def test_boundary_30(self):
        """Exactly 30 should be Obese (not Overweight)."""
        assert get_bmi_category(30.0) == "Obese"


# ---------------------------------------------------------------------------
# prepare_metrics
# ---------------------------------------------------------------------------
class TestPrepareMetrics:
    """Tests for the metric preparation pipeline."""

    def test_adds_bmi_column(self, sample_df):
        """prepare_metrics should add a BMI column."""
        result = prepare_metrics(sample_df, 175.0, 70.0, 2000, 0.1)
        assert "BMI" in result.columns
        assert result["BMI"].notna().all()

    def test_adds_macro_percentages(self, sample_df):
        """Protein_pct, Carbs_pct, Fat_pct should be added."""
        result = prepare_metrics(sample_df, 175.0, 70.0, 2000, 0.1)
        for col in ["Protein_pct", "Carbs_pct", "Fat_pct"]:
            assert col in result.columns

    def test_calorie_deficit_sign(self, sample_df):
        """Calorie_deficit > 0 means eating below target."""
        result = prepare_metrics(sample_df, 175.0, 70.0, 5000, 0.1)
        # Target is 5000, intake ~2200 → deficit should be positive
        assert (result["Calorie_deficit"] > 0).all()

    def test_on_track_within_tolerance(self, sample_df):
        """On_track should be True when intake is within tolerance of target."""
        # Set target to median intake so roughly half are on track
        median_cal = sample_df["Energy (kcal)"].median()
        result = prepare_metrics(sample_df, 175.0, 70.0, int(median_cal), 0.5)
        assert result["On_track_calories"].any()

    def test_weekend_flag(self, sample_df):
        """Is_weekend should flag Saturdays and Sundays."""
        result = prepare_metrics(sample_df, 175.0, 70.0, 2000, 0.1)
        assert "Is_weekend" in result.columns
        weekend_days = result[result["Is_weekend"]]["Date"].dt.dayofweek
        assert weekend_days.isin([5, 6]).all()

    def test_returns_same_dataframe(self, sample_df):
        """prepare_metrics should modify in place and return the same object."""
        result = prepare_metrics(sample_df, 175.0, 70.0, 2000, 0.1)
        assert result is sample_df


# ---------------------------------------------------------------------------
# compute_nutrient_correlations
# ---------------------------------------------------------------------------
class TestComputeNutrientCorrelations:
    """Tests for the Pearson correlation calculator."""

    def test_returns_list_of_dicts(self, sample_df):
        """Each item should have nutrient, correlation, p_value, significant."""
        nutrients = ["Energy (kcal)", "Protein (g)"]
        result = compute_nutrient_correlations(sample_df, nutrients)
        assert isinstance(result, list)
        assert len(result) == 2
        for item in result:
            assert "nutrient" in item
            assert "correlation" in item
            assert "p_value" in item
            assert "significant" in item

    def test_sorted_by_abs_correlation(self, sample_df):
        """Results should be sorted by absolute correlation descending."""
        nutrients = ["Energy (kcal)", "Protein (g)", "Carbs (g)"]
        result = compute_nutrient_correlations(sample_df, nutrients)
        abs_corrs = [abs(r["correlation"]) for r in result]
        assert abs_corrs == sorted(abs_corrs, reverse=True)

    def test_empty_with_insufficient_data(self):
        """Should return empty list when fewer than 3 valid rows."""
        df = pd.DataFrame({
            "Energy (kcal)": [2000.0, 2100.0],
            "Daily Weight change (kg)": [0.1, -0.1],
        })
        result = compute_nutrient_correlations(df, ["Energy (kcal)"])
        assert result == []


# ---------------------------------------------------------------------------
# build_key_figures_table
# ---------------------------------------------------------------------------
class TestBuildKeyFiguresTable:
    """Tests for the actionable key-figures table builder."""

    def test_returns_dataframe(self, sample_df):
        """Should return a pd.DataFrame."""
        prepare_metrics(sample_df, 175.0, 70.0, 2000, 0.1)
        result = build_key_figures_table(sample_df, {}, 2000, 100, 25)
        assert isinstance(result, pd.DataFrame)

    def test_has_three_time_window_columns(self, sample_df):
        """Table should have Last 7 Days, Last 30 Days, All Time columns."""
        prepare_metrics(sample_df, 175.0, 70.0, 2000, 0.1)
        result = build_key_figures_table(sample_df, {}, 2000, 100, 25)
        assert "Last 7 Days" in result.columns
        assert "Last 30 Days" in result.columns
        assert "All Time" in result.columns

    def test_contains_key_metric_rows(self, sample_df):
        """Table index should contain TDEE, intake, adherence rows."""
        prepare_metrics(sample_df, 175.0, 70.0, 2000, 0.1)
        result = build_key_figures_table(sample_df, {}, 2000, 100, 25)
        assert "Avg Intake (kcal)" in result.index
        assert "Cal Adherence (%)" in result.index


# ---------------------------------------------------------------------------
# _fmt
# ---------------------------------------------------------------------------
class TestFmt:
    """Tests for the numeric formatting helper."""

    def test_nan_returns_dashes(self):
        """NaN input should produce '--'."""
        assert _fmt(np.nan) == "--"
        assert _fmt(None) == "--"

    def test_positive_with_sign(self):
        """Positive value with sign=True should have '+' prefix."""
        assert _fmt(123.456, 1, sign=True) == "+123.5"

    def test_negative_with_sign(self):
        """Negative value with sign=True should show '-'."""
        assert _fmt(-42.0, 0, sign=True) == "-42"

    def test_zero_decimals(self):
        """Zero decimals should round to integer representation."""
        assert _fmt(2500.7, 0) == "2501"
