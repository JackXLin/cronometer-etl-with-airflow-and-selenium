"""Garmin analytics report pages for the PDF-first reporting section."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

import matplotlib.dates as mdates
import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from garmin_report_helpers import (
    GARMIN_LAG_METRICS,
    RECOVERY_SCATTER_COLUMNS,
    build_activity_contribution_summary,
    build_activity_session_table,
    build_coverage_table,
    build_lag_correlation_result,
    build_outlier_diagnostic_table,
    build_regime_comparison_table,
    build_weekly_summary_table_garmin,
    prepare_garmin_report_inputs,
)


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



def _render_empty_axis(ax, title: str, message: str) -> None:
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



def _render_table(ax, data: pd.DataFrame, title: str, font_size: float = 8.0) -> None:
    """Render a compact dataframe table on the given axis.

    Args:
        ax: Matplotlib axis.
        data (pd.DataFrame): Table source data.
        title (str): Table title.
        font_size (float): Table font size.

    Returns:
        None
    """
    ax.axis("off")
    ax.set_title(title, fontsize=12, fontweight="bold", pad=10)
    if data.empty:
        ax.text(0.5, 0.5, "Insufficient data", ha="center", va="center", transform=ax.transAxes)
        return
    display = data.copy()
    for column_name in display.columns:
        if pd.api.types.is_numeric_dtype(display[column_name]):
            display[column_name] = display[column_name].map(
                lambda value: "--" if pd.isna(value) else f"{value:.2f}" if abs(float(value)) < 10 else f"{value:.0f}"
            )
    table = ax.table(
        cellText=display.values,
        colLabels=list(display.columns),
        cellLoc="center",
        loc="center",
        colColours=["#e8f1fb"] * len(display.columns),
    )
    table.auto_set_font_size(False)
    table.set_fontsize(font_size)
    table.scale(1.0, 1.4)



def _style_date_axis(ax) -> None:
    """Apply a consistent date axis formatter.

    Args:
        ax: Matplotlib axis.

    Returns:
        None
    """
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=35, ha="right")



def page_garmin_adjusted_tdee_panel(pdf, processed: pd.DataFrame, tdee_estimates: dict) -> None:
    """Render the Garmin-adjusted TDEE context page.

    Args:
        pdf: PdfPages object.
        processed (pd.DataFrame): Enriched processed dataset.
        tdee_estimates (dict): TDEE estimate output.

    Returns:
        None
    """
    fig, (ax_top, ax_bottom) = plt.subplots(2, 1, figsize=(15, 11), sharex=True)
    intake_7d = processed["Energy (kcal)"].rolling(7, min_periods=1).mean()
    tdee_line = processed.get("TDEE_adaptive", pd.Series(np.nan, index=processed.index))
    ax_top.plot(processed["Date"], intake_7d, color="#4c78a8", linewidth=2, label="Intake kcal (7d)")
    ax_top.plot(processed["Date"], tdee_line, color="#e45756", linewidth=2, label="Current model TDEE")
    proxy_axis = ax_top.twinx()
    proxy_axis.plot(
        processed["Date"],
        processed["garmin_activity_proxy_7d"],
        color="#54a24b",
        linewidth=2,
        label="Garmin activity proxy (7d)",
    )
    ax_top.set_title("Garmin-Adjusted TDEE Context", fontsize=14, fontweight="bold")
    ax_top.set_ylabel("Calories / Day")
    proxy_axis.set_ylabel("Activity proxy")
    ax_top.grid(True, alpha=0.3)
    handles, labels = ax_top.get_legend_handles_labels()
    proxy_handles, proxy_labels = proxy_axis.get_legend_handles_labels()
    ax_top.legend(handles + proxy_handles, labels + proxy_labels, fontsize=8, loc="upper left")

    ax_bottom.plot(
        processed["Date"],
        processed["Weight_smoothed"],
        color="#2a9d8f",
        linewidth=2.5,
        label="Smoothed weight trend",
    )
    high_activity = processed["garmin_activity_proxy_kcal"] >= processed["garmin_activity_proxy_kcal"].quantile(0.75)
    low_activity = processed["garmin_activity_proxy_kcal"] <= processed["garmin_activity_proxy_kcal"].quantile(0.25)
    ax_bottom.fill_between(
        processed["Date"],
        processed["Weight_smoothed"].min(),
        processed["Weight_smoothed"].max(),
        where=high_activity,
        color="#54a24b",
        alpha=0.08,
        transform=ax_bottom.get_xaxis_transform(),
        label="Unusually active",
    )
    ax_bottom.fill_between(
        processed["Date"],
        processed["Weight_smoothed"].min(),
        processed["Weight_smoothed"].max(),
        where=low_activity,
        color="#e45756",
        alpha=0.08,
        transform=ax_bottom.get_xaxis_transform(),
        label="Unusually sedentary",
    )
    ax_bottom.set_ylabel("Weight (kg)")
    ax_bottom.set_title("Smoothed Weight Trend vs Activity Regimes", fontsize=12, fontweight="bold")
    ax_bottom.grid(True, alpha=0.3)
    ax_bottom.legend(fontsize=8, loc="upper right")
    _style_date_axis(ax_bottom)

    weighted_tdee = tdee_estimates.get("weighted_average")
    latest_proxy = processed["garmin_activity_proxy_kcal"].tail(30)
    latest_intake_gap = (processed["Energy (kcal)"] - tdee_line).tail(30)
    valid = ~(latest_proxy.isna() | latest_intake_gap.isna())
    if valid.sum() > 10:
        bias_corr = float(np.corrcoef(latest_proxy[valid], latest_intake_gap[valid])[0, 1])
    else:
        bias_corr = np.nan
    summary_text = (
        f"Weighted TDEE estimate: {weighted_tdee:.0f} kcal/day\n"
        if isinstance(weighted_tdee, (int, float))
        else "Weighted TDEE estimate unavailable\n"
    )
    if np.isnan(bias_corr):
        summary_text += "Activity-vs-gap bias signal: insufficient data"
    else:
        summary_text += f"Activity-vs-gap bias signal (last 30d): r={bias_corr:+.2f}"
    fig.text(
        0.02,
        0.02,
        summary_text,
        fontsize=10,
        bbox=dict(boxstyle="round,pad=0.4", fc="#f8f4d7", alpha=0.9),
    )
    plt.tight_layout(rect=[0, 0.04, 1, 1])
    pdf.savefig(fig)
    plt.close(fig)



def page_garmin_lag_heatmap(pdf, processed: pd.DataFrame) -> None:
    """Render Garmin lag heatmaps and the lag summary table.

    Args:
        pdf: PdfPages object.
        processed (pd.DataFrame): Enriched processed dataset.

    Returns:
        None
    """
    daily_result = build_lag_correlation_result(processed, GARMIN_LAG_METRICS, "Daily Weight change (kg)")
    trend_result = build_lag_correlation_result(processed, GARMIN_LAG_METRICS, "Weight_trend_change_7d")
    fig = plt.figure(figsize=(16, 12))
    gs = gridspec.GridSpec(2, 2, height_ratios=[1.2, 1], hspace=0.35, wspace=0.25)
    ax_daily = fig.add_subplot(gs[0, 0])
    ax_trend = fig.add_subplot(gs[0, 1])
    ax_table = fig.add_subplot(gs[1, :])

    for axis, matrix, title in [
        (ax_daily, daily_result.correlation_matrix, "Lag vs Daily Weight Change"),
        (ax_trend, trend_result.correlation_matrix, "Lag vs 7-Day Trend Weight Change"),
    ]:
        if matrix.empty:
            _render_empty_axis(axis, title, "Insufficient data")
            continue
        im = axis.imshow(matrix.values, aspect="auto", cmap="RdBu_r", vmin=-0.5, vmax=0.5)
        axis.set_title(title, fontsize=12, fontweight="bold")
        axis.set_xticks(range(len(matrix.columns)))
        axis.set_xticklabels([column.replace("lag_", "") for column in matrix.columns])
        axis.set_yticks(range(len(matrix.index)))
        axis.set_yticklabels(matrix.index, fontsize=9)
        for row_idx in range(len(matrix.index)):
            for col_idx in range(len(matrix.columns)):
                value = matrix.iloc[row_idx, col_idx]
                if not np.isnan(value):
                    axis.text(col_idx, row_idx, f"{value:+.2f}", ha="center", va="center", fontsize=8)
        plt.colorbar(im, ax=axis, shrink=0.75)

    lag_table = daily_result.summary_table.copy()
    if not lag_table.empty:
        lag_table = lag_table[["metric", "best_lag", "best_correlation", "sign", "sample_size"]]
    _render_table(ax_table, lag_table, "Lag Correlation Summary", font_size=8.5)
    fig.suptitle("Garmin Lag Heatmaps", fontsize=15, fontweight="bold")
    plt.tight_layout(rect=[0, 0, 1, 0.97])
    pdf.savefig(fig)
    plt.close(fig)



def page_weight_spike_attribution(pdf, processed: pd.DataFrame) -> None:
    """Render the weight spike attribution chart and outlier diagnostic table.

    Args:
        pdf: PdfPages object.
        processed (pd.DataFrame): Enriched processed dataset.

    Returns:
        None
    """
    diagnostics = build_outlier_diagnostic_table(processed)
    fig = plt.figure(figsize=(16, 11))
    gs = gridspec.GridSpec(2, 1, height_ratios=[1.25, 0.9], hspace=0.28)
    ax_heatmap = fig.add_subplot(gs[0, 0])
    ax_table = fig.add_subplot(gs[1, 0])
    if diagnostics.empty:
        _render_empty_axis(ax_heatmap, "Weight Spike Attribution", "No weight spikes exceeded the configured threshold.")
        _render_table(ax_table, diagnostics, "Outlier-Day Diagnostic Table")
    else:
        columns = [
            "carbs z-score",
            "sodium z-score",
            "water z-score",
            "sleep score z-score",
            "stress z-score",
            "steps z-score",
            "active kcal z-score",
            "resting HR delta",
            "body battery min",
            "HRV delta",
        ]
        heatmap_df = diagnostics.head(10)[columns].copy()
        heatmap_df.index = diagnostics.head(10)["date"]
        im = ax_heatmap.imshow(heatmap_df.values, aspect="auto", cmap="coolwarm", vmin=-3, vmax=3)
        ax_heatmap.set_title("Weight Spike Attribution Z-Scores", fontsize=13, fontweight="bold")
        ax_heatmap.set_xticks(range(len(columns)))
        ax_heatmap.set_xticklabels(columns, rotation=35, ha="right", fontsize=9)
        ax_heatmap.set_yticks(range(len(heatmap_df.index)))
        ax_heatmap.set_yticklabels(heatmap_df.index, fontsize=9)
        for row_idx in range(len(heatmap_df.index)):
            for col_idx in range(len(columns)):
                value = heatmap_df.iloc[row_idx, col_idx]
                if not np.isnan(value):
                    ax_heatmap.text(col_idx, row_idx, f"{value:+.1f}", ha="center", va="center", fontsize=8)
        plt.colorbar(im, ax=ax_heatmap, shrink=0.8)
        _render_table(
            ax_table,
            diagnostics[[
                "date",
                "weight delta",
                "carbs z-score",
                "sodium z-score",
                "sleep score z-score",
                "stress z-score",
                "resting HR delta",
                "body battery min",
                "HRV delta",
                "activity kcal",
                "likely explanation tag",
            ]].head(8),
            "Outlier-Day Diagnostic Table",
            font_size=7.5,
        )
    fig.suptitle("Weight Spike Attribution", fontsize=15, fontweight="bold")
    plt.tight_layout(rect=[0, 0, 1, 0.97])
    pdf.savefig(fig)
    plt.close(fig)



def page_recovery_vs_scale_noise(pdf, processed: pd.DataFrame) -> None:
    """Render recovery-vs-scale-noise scatter plots.

    Args:
        pdf: PdfPages object.
        processed (pd.DataFrame): Enriched processed dataset.

    Returns:
        None
    """
    fig, axes = plt.subplots(2, 3, figsize=(16, 10))
    color_metric = processed.get("Carbs (g)", processed.get("Sodium (mg)", pd.Series(np.nan, index=processed.index)))
    color_label = "Prior-day carbs" if "Carbs (g)" in processed.columns else "Prior-day sodium"
    for ax, (label, column_name) in zip(axes.flat, RECOVERY_SCATTER_COLUMNS.items()):
        if column_name not in processed.columns:
            _render_empty_axis(ax, label, "Unavailable")
            continue
        x = pd.to_numeric(processed[column_name], errors="coerce")
        y = pd.to_numeric(processed["Daily Weight change (kg)"], errors="coerce")
        valid = ~(x.isna() | y.isna() | color_metric.isna())
        if valid.sum() < 5:
            _render_empty_axis(ax, label, "Insufficient data")
            continue
        scatter = ax.scatter(x[valid], y[valid], c=color_metric[valid], cmap="viridis", alpha=0.75)
        ax.axhline(0, color="black", linewidth=1, alpha=0.5)
        ax.set_title(label, fontsize=11, fontweight="bold")
        ax.set_xlabel(label)
        ax.set_ylabel("Next-day weight change (kg)")
        ax.grid(True, alpha=0.2)
        plt.colorbar(scatter, ax=ax, shrink=0.8, label=color_label)
    fig.suptitle("Recovery vs Scale-Noise Scatter", fontsize=15, fontweight="bold")
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    pdf.savefig(fig)
    plt.close(fig)



def page_weekly_energy_balance_dashboard(pdf, processed: pd.DataFrame) -> None:
    """Render the weekly energy balance dashboard and summary table.

    Args:
        pdf: PdfPages object.
        processed (pd.DataFrame): Enriched processed dataset.

    Returns:
        None
    """
    weekly = build_weekly_summary_table_garmin(processed)
    fig = plt.figure(figsize=(16, 12))
    gs = gridspec.GridSpec(2, 2, height_ratios=[1.2, 1], hspace=0.3, wspace=0.24)
    ax_energy = fig.add_subplot(gs[0, 0])
    ax_recovery = fig.add_subplot(gs[0, 1])
    ax_table = fig.add_subplot(gs[1, :])
    if weekly.empty:
        _render_empty_axis(ax_energy, "Weekly Energy & Activity", "Insufficient weekly Garmin data")
        _render_empty_axis(ax_recovery, "Weekly Recovery & Weight Trend", "Insufficient weekly Garmin data")
        _render_table(ax_table, weekly, "Weekly Summary Table")
    else:
        x = np.arange(len(weekly.index))
        labels = weekly["week start"].tolist()
        ax_energy.bar(x - 0.18, weekly["avg_intake"], width=0.35, color="#4c78a8", label="Avg intake")
        ax_energy.bar(x + 0.18, weekly["total_active_kcal"], width=0.35, color="#54a24b", label="Total active kcal")
        steps_axis = ax_energy.twinx()
        steps_axis.plot(x, weekly["avg_steps"] / 1000.0, color="#f58518", marker="o", linewidth=2, label="Avg steps (k)")
        ax_energy.set_xticks(x)
        ax_energy.set_xticklabels(labels, rotation=35, ha="right", fontsize=8)
        ax_energy.set_title("Weekly Energy & Activity", fontsize=12, fontweight="bold")
        ax_energy.set_ylabel("Calories")
        steps_axis.set_ylabel("Steps (thousands)")
        handles, labels_primary = ax_energy.get_legend_handles_labels()
        handles_secondary, labels_secondary = steps_axis.get_legend_handles_labels()
        ax_energy.legend(handles + handles_secondary, labels_primary + labels_secondary, fontsize=8, loc="upper left")
        ax_energy.grid(True, alpha=0.25)

        ax_recovery.plot(x, weekly["avg_sleep_hours"], color="#4c78a8", marker="o", linewidth=2, label="Avg sleep h")
        ax_recovery.plot(x, weekly["avg_stress"], color="#e45756", marker="o", linewidth=2, label="Avg stress")
        ax_recovery.plot(x, weekly["avg_resting_hr"], color="#72b7b2", marker="o", linewidth=2, label="Avg resting HR")
        trend_axis = ax_recovery.twinx()
        trend_axis.bar(x, weekly["weight trend slope"], alpha=0.25, color="#9d755d", label="Weight trend slope")
        ax_recovery.set_xticks(x)
        ax_recovery.set_xticklabels(labels, rotation=35, ha="right", fontsize=8)
        ax_recovery.set_title("Weekly Recovery & Weight Trend", fontsize=12, fontweight="bold")
        ax_recovery.grid(True, alpha=0.25)
        handles, labels_primary = ax_recovery.get_legend_handles_labels()
        handles_secondary, labels_secondary = trend_axis.get_legend_handles_labels()
        ax_recovery.legend(handles + handles_secondary, labels_primary + labels_secondary, fontsize=8, loc="upper left")
        _render_table(ax_table, weekly, "Weekly Summary Table", font_size=7.2)
    fig.suptitle("Weekly Energy Balance Dashboard", fontsize=15, fontweight="bold")
    plt.tight_layout(rect=[0, 0, 1, 0.97])
    pdf.savefig(fig)
    plt.close(fig)



def page_activity_type_contribution(pdf, processed: pd.DataFrame, activity_df: pd.DataFrame) -> None:
    """Render weekly activity-type contributions and session details.

    Args:
        pdf: PdfPages object.
        processed (pd.DataFrame): Enriched processed dataset.
        activity_df (pd.DataFrame): Garmin activity sessions.

    Returns:
        None
    """
    fig = plt.figure(figsize=(16, 12))
    gs = gridspec.GridSpec(2, 2, height_ratios=[1.15, 1], hspace=0.3, wspace=0.28)
    ax_chart = fig.add_subplot(gs[0, :])
    ax_summary = fig.add_subplot(gs[1, 0])
    ax_sessions = fig.add_subplot(gs[1, 1])
    if activity_df.empty:
        _render_empty_axis(ax_chart, "Activity-Type Contribution", "No Garmin activity sessions were available.")
        _render_table(ax_summary, pd.DataFrame(), "Activity-Type Summary")
        _render_table(ax_sessions, pd.DataFrame(), "Activity Session Table")
    else:
        sessions = activity_df.copy()
        sessions["Date"] = pd.to_datetime(sessions["Date"])
        sessions["Week"] = sessions["Date"].dt.to_period("W").astype(str)
        grouped = sessions.groupby(["Week", "garmin_activity_group"], dropna=False)["garmin_activity_calories_kcal"].sum().unstack(fill_value=0)
        grouped = grouped.tail(8)
        grouped.plot(kind="bar", stacked=True, ax=ax_chart, colormap="tab20")
        ax_chart.set_title("Weekly Activity Calories by Type", fontsize=13, fontweight="bold")
        ax_chart.set_ylabel("Calories")
        ax_chart.set_xlabel("Week")
        ax_chart.grid(True, alpha=0.2, axis="y")
        ax_chart.legend(fontsize=8, ncol=3)
        _render_table(ax_summary, build_activity_contribution_summary(activity_df, processed), "Activity-Type Summary", font_size=7.8)
        _render_table(ax_sessions, build_activity_session_table(activity_df, processed), "Activity Session Table", font_size=7.2)
    fig.suptitle("Activity-Type Contribution", fontsize=15, fontweight="bold")
    plt.tight_layout(rect=[0, 0, 1, 0.97])
    pdf.savefig(fig)
    plt.close(fig)



def page_recovery_regime_comparison(pdf, processed: pd.DataFrame) -> None:
    """Render recovery regime comparison box plots and summary table.

    Args:
        pdf: PdfPages object.
        processed (pd.DataFrame): Enriched processed dataset.

    Returns:
        None
    """
    fig = plt.figure(figsize=(16, 12))
    gs = gridspec.GridSpec(3, 2, height_ratios=[1, 1, 0.95], hspace=0.35, wspace=0.28)
    plot_specs = [
        ("Sleep score quartiles", "garmin_sleep_score"),
        ("Stress high vs low", "garmin_avg_stress"),
        ("Steps high vs low", "garmin_steps"),
        ("HRV high vs low", "garmin_hrv"),
    ]
    for axis, (title, column_name) in zip([fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1]), fig.add_subplot(gs[1, 0]), fig.add_subplot(gs[1, 1])], plot_specs):
        if column_name not in processed.columns or processed[column_name].notna().sum() < 8:
            _render_empty_axis(axis, title, "Insufficient data")
            continue
        series = pd.to_numeric(processed[column_name], errors="coerce")
        target = pd.to_numeric(processed["Daily Weight change (kg)"], errors="coerce")
        if title == "Sleep score quartiles":
            bins = pd.qcut(series.rank(method="first"), 4, labels=["Q1", "Q2", "Q3", "Q4"])
        else:
            median = series.median()
            bins = np.where(series >= median, "High", "Low")
        groups = []
        labels = []
        for label in pd.Series(bins).dropna().unique():
            mask = pd.Series(bins, index=processed.index) == label
            values = target[mask].dropna().values
            if len(values) > 0:
                groups.append(values)
                labels.append(str(label))
        if not groups:
            _render_empty_axis(axis, title, "Insufficient grouped data")
            continue
        axis.boxplot(groups, labels=labels, patch_artist=True)
        axis.axhline(0, color="black", linewidth=1, alpha=0.5)
        axis.set_title(title, fontsize=11, fontweight="bold")
        axis.set_ylabel("Next-day weight change (kg)")
        axis.grid(True, alpha=0.2)
    ax_table = fig.add_subplot(gs[2, :])
    _render_table(ax_table, build_regime_comparison_table(processed), "Regime Comparison Table", font_size=7.5)
    fig.suptitle("Recovery Regime Comparison", fontsize=15, fontweight="bold")
    plt.tight_layout(rect=[0, 0, 1, 0.97])
    pdf.savefig(fig)
    plt.close(fig)



def _plot_month_calendar(ax, month_df: pd.DataFrame, value_column: str, title: str) -> None:
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
        _render_empty_axis(ax, title, "Insufficient data")
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
    im = ax.imshow(matrix, aspect="auto", cmap="coolwarm")
    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.set_yticks(range(7))
    ax.set_yticklabels(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], fontsize=8)
    ax.set_xticks(range(max_week + 1))
    ax.set_xticklabels([f"W{k + 1}" for k in range(max_week + 1)], fontsize=8)
    for row_idx in range(matrix.shape[0]):
        for col_idx in range(matrix.shape[1]):
            if labels[row_idx, col_idx]:
                ax.text(col_idx, row_idx, labels[row_idx, col_idx], ha="center", va="center", fontsize=8)
    plt.colorbar(im, ax=ax, shrink=0.7)



def page_calendar_and_coverage(pdf, processed: pd.DataFrame, activity_df: pd.DataFrame) -> None:
    """Render recent monthly calendar heatmaps and the coverage table.

    Args:
        pdf: PdfPages object.
        processed (pd.DataFrame): Enriched processed dataset.
        activity_df (pd.DataFrame): Garmin activity sessions.

    Returns:
        None
    """
    latest_month = processed["Date"].dt.to_period("M").max()
    month_df = processed[processed["Date"].dt.to_period("M") == latest_month].copy()
    fig = plt.figure(figsize=(16, 12))
    gs = gridspec.GridSpec(3, 2, height_ratios=[1, 1, 0.9], hspace=0.35, wspace=0.26)
    axes = [
        fig.add_subplot(gs[0, 0]),
        fig.add_subplot(gs[0, 1]),
        fig.add_subplot(gs[1, 0]),
        fig.add_subplot(gs[1, 1]),
    ]
    _plot_month_calendar(axes[0], month_df, "Daily Weight change (kg)", f"{latest_month} Weight Change")
    _plot_month_calendar(axes[1], month_df, "garmin_sleep_score", f"{latest_month} Sleep Score")
    _plot_month_calendar(axes[2], month_df, "garmin_avg_stress", f"{latest_month} Stress")
    _plot_month_calendar(axes[3], month_df, "garmin_steps", f"{latest_month} Steps")
    ax_table = fig.add_subplot(gs[2, :])
    _render_table(ax_table, build_coverage_table(processed, activity_df), "Data Coverage / Missingness Table", font_size=8.0)
    fig.suptitle("Month Calendar Heatmap & Coverage", fontsize=15, fontweight="bold")
    plt.tight_layout(rect=[0, 0, 1, 0.97])
    pdf.savefig(fig)
    plt.close(fig)



def render_garmin_analytics_pages(
    pdf,
    processed: pd.DataFrame,
    tdee_estimates: dict,
) -> None:
    """Render the Garmin analytics section using optional activity artifacts.

    Args:
        pdf: PdfPages object.
        processed (pd.DataFrame): Main processed dataset.
        tdee_estimates (dict): TDEE estimate output.

    Returns:
        None
    """
    activity_df = load_optional_garmin_activity_data()
    report_df, prepared_activity_df = prepare_garmin_report_inputs(processed, activity_df)
    page_garmin_adjusted_tdee_panel(pdf, report_df, tdee_estimates)
    page_garmin_lag_heatmap(pdf, report_df)
    page_weight_spike_attribution(pdf, report_df)
    page_recovery_vs_scale_noise(pdf, report_df)
    page_weekly_energy_balance_dashboard(pdf, report_df)
    page_activity_type_contribution(pdf, report_df, prepared_activity_df)
    page_recovery_regime_comparison(pdf, report_df)
    page_calendar_and_coverage(pdf, report_df, prepared_activity_df)
