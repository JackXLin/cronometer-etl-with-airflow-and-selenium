"""Layout helpers for Garmin analytics report pages."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import textwrap
from typing import Iterable

import matplotlib.dates as mdates
import numpy as np
import pandas as pd


DEFAULT_GARMIN_ACTIVITY_PATH = "/opt/airflow/csvs/garmin_activities.csv"



def load_optional_garmin_activity_data(
    activity_path: str = DEFAULT_GARMIN_ACTIVITY_PATH,
) -> pd.DataFrame:
    """Load optional Garmin activity-session data for reporting.

    Args:
        activity_path (str): Activity session CSV path.

    Returns:
        pd.DataFrame: Activity-session data when available, else empty DataFrame.
    """
    path = Path(activity_path)
    if not path.exists():
        return pd.DataFrame()
    activity_df = pd.read_csv(path)
    if "Date" in activity_df.columns:
        activity_df["Date"] = pd.to_datetime(activity_df["Date"])
    return activity_df



def render_empty_axis(ax, title: str, message: str) -> None:
    """Render a standard empty-state axis.

    Args:
        ax: Matplotlib axis.
        title (str): Axis title.
        message (str): Empty-state message.

    Returns:
        None
    """
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.axis("off")
    ax.text(0.5, 0.5, message, ha="center", va="center", transform=ax.transAxes)



def _format_table_value(value: object, max_chars: int) -> str:
    """Format one table value for compact PDF display.

    Args:
        value (object): Source value.
        max_chars (int): Maximum number of display characters.

    Returns:
        str: Formatted display value.
    """
    if pd.isna(value):
        return "--"
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float)):
        numeric_value = float(value)
        if abs(numeric_value) >= 1000:
            return f"{numeric_value:,.0f}"
        if abs(numeric_value) >= 10:
            return f"{numeric_value:.0f}"
        return f"{numeric_value:.2f}"

    text_value = str(value)
    if len(text_value) > max_chars:
        return f"{text_value[: max_chars - 1]}…"
    return text_value



def _compute_col_widths(display: pd.DataFrame, headers: list[str]) -> list[float]:
    """Estimate proportional column widths from content length.

    Args:
        display (pd.DataFrame): Formatted table data.
        headers (list[str]): Display headers.

    Returns:
        list[float]: Normalized column widths.
    """
    estimated_widths: list[float] = []
    for column_idx, column_name in enumerate(display.columns):
        cell_lengths = [len(str(value).replace("\n", " ")) for value in display[column_name].tolist()]
        header_length = len(headers[column_idx].replace("\n", " "))
        max_length = max([header_length, *cell_lengths], default=header_length)
        estimated_widths.append(min(max(max_length / 90.0, 0.08), 0.22))

    total_width = sum(estimated_widths) or 1.0
    return [width / total_width for width in estimated_widths]



def wrap_labels(labels: Iterable[object], width: int = 16) -> list[str]:
    """Wrap labels to keep axes and table headers compact.

    Args:
        labels (Iterable[object]): Labels to wrap.
        width (int): Wrap width.

    Returns:
        list[str]: Wrapped labels.
    """
    wrapped_labels: list[str] = []
    for label in labels:
        text_label = str(label).replace("_", " ")
        wrapped_labels.append(
            textwrap.fill(text_label, width=width, break_long_words=False)
        )
    return wrapped_labels



def render_table(
    ax,
    data: pd.DataFrame,
    title: str,
    font_size: float = 8.0,
    title_pad: float = 10.0,
    max_cell_chars: int = 18,
    header_wrap: int = 16,
    bbox: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 0.86),
) -> None:
    """Render a compact dataframe table on the given axis.

    Args:
        ax: Matplotlib axis.
        data (pd.DataFrame): Table source data.
        title (str): Table title.
        font_size (float): Base table font size.
        title_pad (float): Axis-title padding.
        max_cell_chars (int): Maximum characters per cell.
        header_wrap (int): Wrap width for headers.
        bbox (tuple[float, float, float, float]): Table bounding box.

    Returns:
        None
    """
    ax.axis("off")
    ax.set_title(title, fontsize=12, fontweight="bold", pad=title_pad)
    if data.empty:
        ax.text(0.5, 0.5, "Insufficient data", ha="center", va="center", transform=ax.transAxes)
        return

    display = data.copy()
    for column_name in display.columns:
        display[column_name] = display[column_name].map(
            lambda value: _format_table_value(value, max_chars=max_cell_chars)
        )

    wrapped_headers = wrap_labels(display.columns, width=header_wrap)
    column_widths = _compute_col_widths(display, wrapped_headers)
    row_count = len(display.index)
    col_count = len(display.columns)
    adjusted_font_size = max(
        6.1,
        min(
            font_size,
            font_size - max(0, col_count - 8) * 0.22 - max(0, row_count - 8) * 0.08,
        ),
    )

    table = ax.table(
        cellText=display.values,
        colLabels=wrapped_headers,
        cellLoc="center",
        colLoc="center",
        loc="center",
        bbox=bbox,
        colWidths=column_widths,
        colColours=["#e8f1fb"] * len(display.columns),
    )
    table.auto_set_font_size(False)
    table.set_fontsize(adjusted_font_size)
    table.scale(1.0, 1.15 if row_count <= 8 else 1.08)

    for (row_idx, _col_idx), cell in table.get_celld().items():
        cell.set_edgecolor("#cfd8e3")
        cell.set_linewidth(0.6)
        cell.PAD = 0.018 if col_count >= 9 else 0.03
        if row_idx == 0:
            cell.set_text_props(fontweight="bold", color="#1f2933")
            cell.set_facecolor("#dbeafe")
        else:
            cell.set_facecolor("#f8fafc" if row_idx % 2 == 0 else "white")

    try:
        table.auto_set_column_width(col=list(range(col_count)))
    except AttributeError:
        pass



def style_date_axis(ax, rotation: int = 30) -> None:
    """Apply a consistent compact date axis formatter.

    Args:
        ax: Matplotlib axis.
        rotation (int): Tick label rotation.

    Returns:
        None
    """
    locator = mdates.AutoDateLocator(minticks=5, maxticks=8)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
    for label in ax.get_xticklabels():
        label.set_rotation(rotation)
        label.set_horizontalalignment("right")



def finalize_figure(
    fig,
    top: float = 0.92,
    bottom: float = 0.06,
    left: float = 0.06,
    right: float = 0.96,
    hspace: float = 0.34,
    wspace: float = 0.26,
) -> None:
    """Apply stable figure spacing for PDF export.

    Args:
        fig: Matplotlib figure.
        top (float): Top margin.
        bottom (float): Bottom margin.
        left (float): Left margin.
        right (float): Right margin.
        hspace (float): Vertical subplot spacing.
        wspace (float): Horizontal subplot spacing.

    Returns:
        None
    """
    fig.subplots_adjust(
        top=top,
        bottom=bottom,
        left=left,
        right=right,
        hspace=hspace,
        wspace=wspace,
    )



def add_shared_colorbar(
    fig,
    mappable,
    axes: Iterable,
    label: str,
    shrink: float = 0.9,
    pad: float = 0.02,
):
    """Create a single shared colorbar for a group of axes.

    Args:
        fig: Matplotlib figure.
        mappable: Matplotlib mappable object.
        axes (Iterable): Axes sharing the colorbar.
        label (str): Colorbar label.
        shrink (float): Colorbar shrink factor.
        pad (float): Padding between axes and colorbar.

    Returns:
        Matplotlib colorbar: Created colorbar instance.
    """
    colorbar = fig.colorbar(mappable, ax=list(axes), shrink=shrink, pad=pad)
    colorbar.set_label(label)
    return colorbar



def plot_month_calendar(ax, month_df: pd.DataFrame, value_column: str, title: str) -> None:
    """Render a compact month calendar heatmap for one metric.

    Args:
        ax: Matplotlib axis.
        month_df (pd.DataFrame): Data for the target month.
        value_column (str): Metric column.
        title (str): Plot title.

    Returns:
        None
    """
    if month_df.empty or value_column not in month_df.columns:
        render_empty_axis(ax, title, "Insufficient data")
        return

    calendar_df = month_df.copy()
    calendar_df["day"] = calendar_df["Date"].dt.day
    calendar_df["weekday"] = calendar_df["Date"].dt.weekday
    calendar_df["week"] = ((calendar_df["day"] + calendar_df["Date"].dt.to_period("M").dt.start_time.dt.weekday - 1) // 7).astype(int)
    max_week = int(calendar_df["week"].max()) if not calendar_df.empty else 0
    matrix = np.full((7, max_week + 1), np.nan)
    labels = np.full((7, max_week + 1), "", dtype=object)
    for _, row in calendar_df.iterrows():
        matrix[int(row["weekday"]), int(row["week"])] = row[value_column]
        labels[int(row["weekday"]), int(row["week"])] = str(int(row["day"]))

    image = ax.imshow(matrix, aspect="auto", cmap="coolwarm")
    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.set_yticks(range(7))
    ax.set_yticklabels(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], fontsize=8)
    ax.set_xticks(range(max_week + 1))
    ax.set_xticklabels([f"W{k + 1}" for k in range(max_week + 1)], fontsize=8)
    for row_idx in range(matrix.shape[0]):
        for col_idx in range(matrix.shape[1]):
            if labels[row_idx, col_idx]:
                ax.text(col_idx, row_idx, labels[row_idx, col_idx], ha="center", va="center", fontsize=8)

    colorbar = ax.figure.colorbar(image, ax=ax, shrink=0.72, pad=0.03)
    colorbar.ax.tick_params(labelsize=7)
