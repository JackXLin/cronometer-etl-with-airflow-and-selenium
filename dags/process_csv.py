import os
from typing import Optional

import pandas as pd


PROCESSED_OUTPUT_PATH = "/opt/airflow/csvs/processed_data.csv"


def _load_nutrition_data(file_path: str) -> pd.DataFrame:
    """
    Load and prepare the Cronometer nutrition export.

    Args:
        file_path (str): Path to the Cronometer daily nutrition CSV.

    Returns:
        pd.DataFrame: Cleaned nutrition data.
    """
    nutrition = pd.read_csv(file_path)
    nutrition["Date"] = pd.to_datetime(nutrition["Date"])
    return nutrition.drop(columns=["Completed"], errors="ignore")


def _load_biometric_data(file_path: str) -> pd.DataFrame:
    """
    Load and prepare the Cronometer biometrics export.

    Args:
        file_path (str): Path to the Cronometer biometrics CSV.

    Returns:
        pd.DataFrame: Weight-only biometrics data keyed by Date.
    """
    bio = pd.read_csv(file_path)
    bio = bio.rename(columns={"Day": "Date", "Amount": "Weight (kg)"})
    bio_cleaned = bio[bio["Unit"] == "kg"].copy()
    bio_cleaned["Date"] = pd.to_datetime(bio_cleaned["Date"])
    return bio_cleaned.drop(columns=["Unit", "Metric"], errors="ignore")


def _load_garmin_data(file_path: Optional[str]) -> Optional[pd.DataFrame]:
    """
    Load optional Garmin daily data for merging.

    Args:
        file_path (Optional[str]): Path to the Garmin daily CSV, if available.

    Returns:
        Optional[pd.DataFrame]: Garmin data keyed by Date, or None.

    Raises:
        FileNotFoundError: If a Garmin path is provided but does not exist.
        ValueError: If the Garmin CSV does not include a Date column.
    """
    if not file_path:
        return None

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Garmin CSV not found at `{file_path}`.")

    garmin = pd.read_csv(file_path)
    if "Date" not in garmin.columns:
        raise ValueError("Garmin CSV must include a `Date` column.")

    garmin_columns = [
        column_name
        for column_name in garmin.columns
        if column_name == "Date" or column_name.startswith("garmin_")
    ]
    garmin = garmin[garmin_columns].copy()
    garmin["Date"] = pd.to_datetime(garmin["Date"])
    return garmin


def _fill_non_garmin_values(processed: pd.DataFrame) -> pd.DataFrame:
    """
    Fill missing non-Garmin values while preserving Garmin NaNs.

    Args:
        processed (pd.DataFrame): Merged processed dataset.

    Returns:
        pd.DataFrame: Processed dataset with Garmin NaNs preserved.
    """
    garmin_columns = [
        column_name
        for column_name in processed.columns
        if column_name.startswith("garmin_")
    ]
    fill_columns = [
        column_name
        for column_name in processed.columns
        if column_name != "Date" and column_name not in garmin_columns
    ]
    processed[fill_columns] = processed[fill_columns].fillna(0)
    return processed


def process_csv(
    file_path1: str,
    file_path2: str,
    garmin_file_path: Optional[str] = None,
) -> str:
    """
    Merge Cronometer nutrition, Cronometer biometrics, and optional Garmin data.

    Args:
        file_path1 (str): Path to the Cronometer nutrition CSV.
        file_path2 (str): Path to the Cronometer biometrics CSV.
        garmin_file_path (Optional[str]): Path to the Garmin daily CSV.

    Returns:
        str: Path to the saved processed CSV.
    """
    nutrition = _load_nutrition_data(file_path1)
    bio_cleaned = _load_biometric_data(file_path2)
    processed = pd.merge(nutrition, bio_cleaned, how="left", on="Date")

    garmin_data = _load_garmin_data(garmin_file_path)
    if garmin_data is not None:
        processed = pd.merge(processed, garmin_data, how="left", on="Date")

    processed = processed.sort_values("Date").reset_index(drop=True)
    processed["Weight (kg)"] = processed["Weight (kg)"].bfill()
    processed = _fill_non_garmin_values(processed)
    processed["Energy 7 days avg (kcal)"] = processed["Energy (kcal)"].rolling(7).mean()
    processed["Energy 30 days avg (kcal)"] = processed["Energy (kcal)"].rolling(30).mean()
    processed["Daily Weight change (kg)"] = (
        processed["Weight (kg)"] - processed["Weight (kg)"].shift(1)
    )
    processed["Daily Weight change (kg)"] = processed["Daily Weight change (kg)"].shift(-1)
    processed.to_csv(path_or_buf=PROCESSED_OUTPUT_PATH, index=False)
    return PROCESSED_OUTPUT_PATH
