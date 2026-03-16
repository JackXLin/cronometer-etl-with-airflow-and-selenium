"""Tests for CSV processing with optional Garmin data."""

import os
import sys
from pathlib import Path

import pandas as pd
import pytest

# Reason: dags/ is not a package, so we add it to sys.path for test imports.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dags"))

import process_csv as process_csv_module


class TestLoadGarminData:
    """Tests for loading optional Garmin CSV data."""

    def test_expected_use_keeps_only_prefixed_columns(self, tmp_path: Path) -> None:
        """Should keep `Date` plus Garmin-prefixed columns only.

        Args:
            tmp_path (Path): Temporary file directory.

        Returns:
            None
        """
        garmin_path = tmp_path / "garmin.csv"
        pd.DataFrame(
            {
                "Date": ["2025-01-01"],
                "garmin_steps": [1234],
                "ignored_column": [999],
            }
        ).to_csv(garmin_path, index=False)

        result = process_csv_module._load_garmin_data(str(garmin_path))

        assert list(result.columns) == ["Date", "garmin_steps"]
        assert pd.api.types.is_datetime64_any_dtype(result["Date"])

    def test_empty_path_returns_none(self) -> None:
        """Should skip Garmin loading when no path is provided.

        Returns:
            None
        """
        assert process_csv_module._load_garmin_data(None) is None

    def test_missing_date_column_raises(self, tmp_path: Path) -> None:
        """Should reject Garmin CSVs that cannot be merged by date.

        Args:
            tmp_path (Path): Temporary file directory.

        Returns:
            None
        """
        garmin_path = tmp_path / "garmin.csv"
        pd.DataFrame({"garmin_steps": [1234]}).to_csv(garmin_path, index=False)

        with pytest.raises(ValueError):
            process_csv_module._load_garmin_data(str(garmin_path))


class TestProcessCsv:
    """Tests for merged Cronometer and Garmin processing."""

    def test_expected_use_merges_optional_garmin_metrics(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Should merge Garmin columns while preserving missing Garmin values.

        Args:
            monkeypatch (pytest.MonkeyPatch): Pytest patch helper.
            tmp_path (Path): Temporary file directory.

        Returns:
            None
        """
        nutrition_path = tmp_path / "nutrition.csv"
        biometrics_path = tmp_path / "biometrics.csv"
        garmin_path = tmp_path / "garmin.csv"
        output_path = tmp_path / "processed.csv"

        pd.DataFrame(
            {
                "Date": ["2025-01-01", "2025-01-02"],
                "Energy (kcal)": [2000, 2100],
                "Completed": [True, True],
            }
        ).to_csv(nutrition_path, index=False)
        pd.DataFrame(
            {
                "Day": ["2025-01-02"],
                "Metric": ["Weight"],
                "Unit": ["kg"],
                "Amount": [80.5],
            }
        ).to_csv(biometrics_path, index=False)
        pd.DataFrame(
            {
                "Date": ["2025-01-02"],
                "garmin_steps": [4567],
            }
        ).to_csv(garmin_path, index=False)

        monkeypatch.setattr(process_csv_module, "PROCESSED_OUTPUT_PATH", str(output_path))

        result = process_csv_module.process_csv(
            str(nutrition_path),
            str(biometrics_path),
            str(garmin_path),
        )
        processed = pd.read_csv(result)

        assert result == str(output_path)
        assert "garmin_steps" in processed.columns
        assert pd.isna(processed.loc[0, "garmin_steps"])
        assert processed.loc[1, "garmin_steps"] == 4567
        assert processed.loc[0, "Weight (kg)"] == 80.5
        assert processed.loc[1, "Weight (kg)"] == 80.5

    def test_missing_garmin_file_raises(self, tmp_path: Path) -> None:
        """Should fail clearly when a Garmin path is provided but missing.

        Args:
            tmp_path (Path): Temporary file directory.

        Returns:
            None
        """
        missing_path = tmp_path / "missing.csv"

        with pytest.raises(FileNotFoundError):
            process_csv_module._load_garmin_data(str(missing_path))
