"""Tests for Garmin analytics layout helpers."""

import os
import sys

import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dags"))

from visualisation_garmin_layout import (
    load_optional_garmin_activity_data,
    render_table,
    wrap_labels,
)


def test_expected_use_load_optional_garmin_activity_data_reads_csv(tmp_path) -> None:
    """Should load Garmin activity CSV data and parse the Date column.

    Args:
        tmp_path: Pytest temporary path fixture.

    Returns:
        None
    """
    csv_path = tmp_path / "garmin_activities.csv"
    pd.DataFrame(
        {
            "Date": ["2025-01-01", "2025-01-02"],
            "garmin_activity_calories_kcal": [320, 410],
        }
    ).to_csv(csv_path, index=False)

    result = load_optional_garmin_activity_data(str(csv_path))

    assert list(result.columns) == ["Date", "garmin_activity_calories_kcal"]
    assert pd.api.types.is_datetime64_any_dtype(result["Date"])
    assert result.shape == (2, 2)


def test_edge_case_render_table_with_empty_frame_shows_empty_state() -> None:
    """An empty dataframe should render a standard insufficient-data table state.

    Returns:
        None
    """
    fig, ax = plt.subplots(figsize=(6, 4))

    try:
        render_table(ax, pd.DataFrame(), "Empty Garmin Table")

        assert ax.get_title() == "Empty Garmin Table"
        assert len(ax.texts) == 1
        assert ax.texts[0].get_text() == "Insufficient data"
    finally:
        plt.close(fig)


def test_failure_case_wrap_labels_replaces_underscores_and_wraps_long_text() -> None:
    """Long underscored labels should be normalized for compact display.

    Returns:
        None
    """
    labels = wrap_labels(["short", "very_long_metric_label_name"], width=8)

    assert labels[0] == "short"
    assert "_" not in labels[1]
    assert "\n" in labels[1]
