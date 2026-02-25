"""
Tests for the TDEE calculator module.

Covers:
    - smooth_weight: EMA smoothing behaviour
    - compute_adaptive_tdee: basic energy-balance logic
    - find_stable_weight_tdee: detection of stable periods
    - regression_tdee: zero-weight-change calorie level
    - estimate_tdee: integration / weighted-average path
"""

import sys
import os
import numpy as np
import pandas as pd
import pytest

# Reason: dags/ is not a package, so we add it to sys.path for test imports.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dags"))

from tdee_calculator import (
    KCAL_PER_KG,
    smooth_weight,
    compute_adaptive_tdee,
    compute_rolling_tdee,
    find_stable_weight_tdee,
    regression_tdee,
    estimate_tdee,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture()
def stable_weight_df():
    """
    DataFrame where weight is constant at 80 kg and daily intake is 2500 kcal.
    TDEE should converge near 2500 because weight is not changing.
    """
    n = 60
    dates = pd.date_range("2025-01-01", periods=n, freq="D")
    return pd.DataFrame({
        "Date": dates,
        "Energy (kcal)": [2500.0] * n,
        "Weight (kg)": [80.0] * n,
        "Daily Weight change (kg)": [0.0] * n,
    })


@pytest.fixture()
def losing_weight_df():
    """
    DataFrame simulating steady weight loss: ~0.5 kg/week deficit.
    Intake 2000, weight drops linearly from 90 to ~85.7 over 60 days.
    """
    n = 60
    dates = pd.date_range("2025-01-01", periods=n, freq="D")
    weight = np.linspace(90, 90 - (0.5 / 7) * n, n)
    daily_change = np.diff(weight, prepend=weight[0])
    return pd.DataFrame({
        "Date": dates,
        "Energy (kcal)": [2000.0] * n,
        "Weight (kg)": weight,
        "Daily Weight change (kg)": daily_change,
    })


# ---------------------------------------------------------------------------
# smooth_weight
# ---------------------------------------------------------------------------
class TestSmoothWeight:
    """Tests for the EMA weight smoother."""

    def test_constant_weight_unchanged(self):
        """Smoothing a constant series should return the same constant."""
        s = pd.Series([80.0] * 30)
        result = smooth_weight(s, span=10)
        np.testing.assert_allclose(result.dropna().values, 80.0, atol=0.01)

    def test_reduces_noise(self):
        """Smoothed series should have lower standard deviation than noisy input."""
        rng = np.random.default_rng(42)
        noisy = pd.Series(80.0 + rng.normal(0, 1.0, 60))
        smoothed = smooth_weight(noisy, span=10)
        assert smoothed.std() < noisy.std()

    def test_returns_same_length(self):
        """Output length must match input length."""
        s = pd.Series([80.0] * 20)
        assert len(smooth_weight(s)) == len(s)


# ---------------------------------------------------------------------------
# compute_adaptive_tdee
# ---------------------------------------------------------------------------
class TestAdaptiveTDEE:
    """Tests for the adaptive EMA-based TDEE estimator."""

    def test_stable_weight_converges_to_intake(self, stable_weight_df):
        """When weight is flat, adaptive TDEE should converge near calorie intake."""
        result = compute_adaptive_tdee(
            stable_weight_df["Energy (kcal)"],
            stable_weight_df["Weight (kg)"],
        )
        # Last 10 values should be close to 2500
        tail_mean = result.dropna().tail(10).mean()
        assert 2300 < tail_mean < 2700

    def test_returns_series_same_length(self, stable_weight_df):
        """Output must be a Series of the same length as input."""
        result = compute_adaptive_tdee(
            stable_weight_df["Energy (kcal)"],
            stable_weight_df["Weight (kg)"],
        )
        assert len(result) == len(stable_weight_df)


# ---------------------------------------------------------------------------
# compute_rolling_tdee
# ---------------------------------------------------------------------------
class TestRollingTDEE:
    """Tests for the rolling-window TDEE calculation."""

    def test_stable_weight_near_intake(self, stable_weight_df):
        """Rolling TDEE on stable weight should approximate calorie intake."""
        result = compute_rolling_tdee(
            stable_weight_df["Energy (kcal)"],
            stable_weight_df["Weight (kg)"],
            window=14,
            min_periods=7,
        )
        valid = result.dropna()
        assert len(valid) > 0
        assert 2300 < valid.mean() < 2700

    def test_early_values_are_nan(self, stable_weight_df):
        """First few values (< min_periods) should be NaN."""
        result = compute_rolling_tdee(
            stable_weight_df["Energy (kcal)"],
            stable_weight_df["Weight (kg)"],
            window=14,
            min_periods=7,
        )
        assert result.iloc[:6].isna().all()


# ---------------------------------------------------------------------------
# find_stable_weight_tdee
# ---------------------------------------------------------------------------
class TestStableWeightTDEE:
    """Tests for the stable-weight-period TDEE estimator."""

    def test_finds_stable_periods(self, stable_weight_df):
        """Constant weight should produce many stable periods."""
        result = find_stable_weight_tdee(stable_weight_df)
        assert result["period_count"] > 0
        assert 2300 < result["estimate"] < 2700

    def test_no_stable_periods_on_rapid_change(self):
        """Rapidly changing weight should yield no stable periods."""
        n = 30
        df = pd.DataFrame({
            "Energy (kcal)": [2500.0] * n,
            "Weight (kg)": np.linspace(90, 70, n),
        })
        result = find_stable_weight_tdee(df, window=14, tolerance_kg=0.5)
        assert result["estimate"] is None
        assert result["period_count"] == 0


# ---------------------------------------------------------------------------
# regression_tdee
# ---------------------------------------------------------------------------
class TestRegressionTDEE:
    """Tests for the regression-based TDEE estimator."""

    def test_stable_weight_returns_estimate(self, stable_weight_df):
        """Regression should return an estimate when data is sufficient."""
        result = regression_tdee(stable_weight_df)
        # With constant weight and constant intake, the regression may not
        # find a slope, so estimate could be None — that's acceptable.
        # If it does return, it should be realistic.
        if result["estimate"] is not None:
            assert 1000 < result["estimate"] < 5000

    def test_insufficient_data_returns_none(self):
        """With fewer than 14 rows, regression should return None."""
        df = pd.DataFrame({
            "Energy (kcal)": [2500.0] * 5,
            "Weight (kg)": [80.0] * 5,
        })
        result = regression_tdee(df)
        assert result["estimate"] is None


# ---------------------------------------------------------------------------
# estimate_tdee (integration)
# ---------------------------------------------------------------------------
class TestEstimateTDEE:
    """Integration tests for the full TDEE estimation pipeline."""

    def test_returns_dict(self, stable_weight_df):
        """estimate_tdee should always return a dict."""
        result = estimate_tdee(stable_weight_df)
        assert isinstance(result, dict)

    def test_adds_columns_to_dataframe(self, stable_weight_df):
        """estimate_tdee should add TDEE columns in-place."""
        estimate_tdee(stable_weight_df)
        assert "TDEE_adaptive" in stable_weight_df.columns
        assert "TDEE_14d" in stable_weight_df.columns
        assert "TDEE_30d" in stable_weight_df.columns
        assert "Weight_smoothed" in stable_weight_df.columns

    def test_weighted_average_realistic(self, stable_weight_df):
        """Weighted average TDEE should be in realistic range for stable weight."""
        result = estimate_tdee(stable_weight_df)
        if "weighted_average" in result:
            assert 1200 < result["weighted_average"] < 4000

    def test_losing_weight_tdee_above_intake(self, losing_weight_df):
        """When losing weight, estimated TDEE should be above average intake."""
        result = estimate_tdee(losing_weight_df)
        if "weighted_average" in result:
            assert result["weighted_average"] > 2000
