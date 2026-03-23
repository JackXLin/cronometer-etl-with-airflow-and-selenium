"""Additional Garmin analytics report page renderers."""

from __future__ import annotations

import math

import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from garmin_report_helpers import (
    build_activity_contribution_summary,
    build_activity_session_table,
    build_coverage_table,
    build_regime_comparison_table,
    build_weekly_summary_table_garmin,
)
from visualisation_garmin_layout import (
    finalize_figure,
    plot_month_calendar,
    render_empty_axis,
    render_table,
)


def page_weekly_energy_balance_dashboard(pdf, processed: pd.DataFrame) -> None:
    """Render the weekly energy balance dashboard and summary table.

    Args:
        pdf: PdfPages object.
        processed (pd.DataFrame): Enriched processed dataset.

    Returns:
        None
    """
    weekly = build_weekly_summary_table_garmin(processed)
    fig = plt.figure(figsize=(16.5, 12.8))
    gs = gridspec.GridSpec(2, 2, height_ratios=[1.15, 0.85], hspace=0.34, wspace=0.3)
    ax_energy = fig.add_subplot(gs[0, 0])
    ax_recovery = fig.add_subplot(gs[0, 1])
    ax_table = fig.add_subplot(gs[1, :])
    if weekly.empty:
        render_empty_axis(ax_energy, "Weekly Energy & Activity", "Insufficient weekly Garmin data")
        render_empty_axis(ax_recovery, "Weekly Recovery & Weight Trend", "Insufficient weekly Garmin data")
        render_table(ax_table, weekly, "Weekly Summary Table")
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
        ax_energy.legend(
            handles + handles_secondary,
            labels_primary + labels_secondary,
            fontsize=8,
            loc="upper center",
            bbox_to_anchor=(0.5, 1.16),
            ncol=3,
            frameon=False,
        )
        ax_energy.grid(True, alpha=0.25)
        steps_axis.tick_params(labelsize=8)

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
        ax_recovery.legend(
            handles + handles_secondary,
            labels_primary + labels_secondary,
            fontsize=8,
            loc="upper center",
            bbox_to_anchor=(0.5, 1.16),
            ncol=4,
            frameon=False,
        )
        trend_axis.tick_params(labelsize=8)
        weekly_table = weekly[[
            "week start",
            "7d weight delta",
            "avg_intake",
            "total_active_kcal",
            "avg_steps",
            "avg_sleep_hours",
            "avg_stress",
            "weight trend slope",
            "adherence flags",
        ]].rename(
            columns={
                "week start": "week",
                "7d weight delta": "weight Δ",
                "avg_intake": "intake",
                "total_active_kcal": "active kcal",
                "avg_steps": "steps",
                "avg_sleep_hours": "sleep h",
                "avg_stress": "stress",
                "weight trend slope": "trend slope",
                "adherence flags": "status",
            }
        )
        render_table(ax_table, weekly_table, "Weekly Summary Table", font_size=7.6, header_wrap=12, max_cell_chars=16)
    fig.suptitle("Weekly Energy Balance Dashboard", fontsize=15, fontweight="bold")
    finalize_figure(fig, top=0.89, bottom=0.05, left=0.07, right=0.93, hspace=0.36, wspace=0.32)
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
    fig = plt.figure(figsize=(16.8, 13.8))
    gs = gridspec.GridSpec(2, 1, height_ratios=[1.05, 1.0], hspace=0.34)
    ax_chart = fig.add_subplot(gs[0, 0])
    bottom_gs = gridspec.GridSpecFromSubplotSpec(1, 2, subplot_spec=gs[1, 0], width_ratios=[0.9, 1.4], wspace=0.18)
    ax_summary = fig.add_subplot(bottom_gs[0, 0])
    ax_sessions = fig.add_subplot(bottom_gs[0, 1])
    if activity_df.empty:
        render_empty_axis(ax_chart, "Activity-Type Contribution", "No Garmin activity sessions were available.")
        render_table(ax_summary, pd.DataFrame(), "Activity-Type Summary")
        render_table(ax_sessions, pd.DataFrame(), "Activity Session Table")
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
        plt.setp(ax_chart.get_xticklabels(), rotation=28, ha="right", fontsize=8)
        ax_chart.legend(
            fontsize=8,
            ncol=max(1, min(4, math.ceil(len(grouped.columns) / 2))),
            loc="upper center",
            bbox_to_anchor=(0.5, 1.14),
            frameon=False,
        )
        ax_chart.margins(x=0.03)
        summary_table = build_activity_contribution_summary(activity_df, processed).rename(
            columns={
                "type": "type",
                "sessions": "sessions",
                "total duration": "duration min",
                "total calories": "calories",
                "average HR": "avg HR",
                "next-day average scale change": "next-day Δ",
            }
        )
        session_table = build_activity_session_table(activity_df, processed, limit=8).rename(
            columns={
                "type": "type",
                "duration": "duration min",
                "calories": "calories",
                "avg HR": "avg HR",
                "max HR": "max HR",
                "training effect": "effect",
                "training load": "load",
                "same-day intake": "intake",
                "next-day weight change": "next-day Δ",
            }
        )
        render_table(
            ax_summary,
            summary_table,
            "Activity-Type Summary",
            font_size=8.0,
            header_wrap=12,
            bbox=(0.0, 0.04, 1.0, 0.88),
        )
        render_table(
            ax_sessions,
            session_table,
            "Activity Session Table",
            font_size=7.2,
            header_wrap=12,
            max_cell_chars=16,
            bbox=(0.0, 0.04, 1.0, 0.88),
        )
    fig.suptitle("Activity-Type Contribution", fontsize=15, fontweight="bold")
    finalize_figure(fig, top=0.9, bottom=0.05, left=0.06, right=0.96, hspace=0.34, wspace=0.2)
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
    fig = plt.figure(figsize=(16.5, 13))
    gs = gridspec.GridSpec(3, 2, height_ratios=[1, 1, 0.88], hspace=0.38, wspace=0.3)
    plot_specs = [
        ("Sleep score quartiles", "garmin_sleep_score"),
        ("Stress high vs low", "garmin_avg_stress"),
        ("Steps high vs low", "garmin_steps"),
        ("HRV high vs low", "garmin_hrv"),
    ]
    for axis, (title, column_name) in zip([fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1]), fig.add_subplot(gs[1, 0]), fig.add_subplot(gs[1, 1])], plot_specs):
        if column_name not in processed.columns or processed[column_name].notna().sum() < 8:
            render_empty_axis(axis, title, "Insufficient data")
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
            render_empty_axis(axis, title, "Insufficient grouped data")
            continue
        axis.boxplot(groups, labels=labels, patch_artist=True)
        axis.axhline(0, color="black", linewidth=1, alpha=0.5)
        axis.set_title(title, fontsize=11, fontweight="bold")
        axis.set_ylabel("Next-day weight change (kg)")
        axis.grid(True, alpha=0.2)
        axis.tick_params(labelsize=8.5)
    ax_table = fig.add_subplot(gs[2, :])
    regime_table = build_regime_comparison_table(processed).rename(
        columns={
            "regime": "regime",
            "mean intake": "intake",
            "mean weight change": "weight Δ",
            "mean active kcal": "active kcal",
            "mean resting HR": "resting HR",
            "mean HRV": "HRV",
            "count of days": "days",
        }
    )
    render_table(ax_table, regime_table, "Regime Comparison Table", font_size=7.5, header_wrap=12)
    fig.suptitle("Recovery Regime Comparison", fontsize=15, fontweight="bold")
    finalize_figure(fig, top=0.9, bottom=0.05, left=0.07, right=0.94, hspace=0.38, wspace=0.3)
    pdf.savefig(fig)
    plt.close(fig)



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
    latest_month_label = latest_month.to_timestamp().strftime("%b %Y")
    fig = plt.figure(figsize=(16.5, 11.8))
    gs = gridspec.GridSpec(2, 2, hspace=0.38, wspace=0.32)
    axes = [
        fig.add_subplot(gs[0, 0]),
        fig.add_subplot(gs[0, 1]),
        fig.add_subplot(gs[1, 0]),
        fig.add_subplot(gs[1, 1]),
    ]
    plot_month_calendar(axes[0], month_df, "Daily Weight change (kg)", f"{latest_month_label} Weight Change")
    plot_month_calendar(axes[1], month_df, "garmin_sleep_score", f"{latest_month_label} Sleep Score")
    plot_month_calendar(axes[2], month_df, "garmin_avg_stress", f"{latest_month_label} Stress")
    plot_month_calendar(axes[3], month_df, "garmin_steps", f"{latest_month_label} Steps")
    fig.suptitle("Month Calendar Heatmaps", fontsize=15, fontweight="bold")
    finalize_figure(fig, top=0.9, bottom=0.06, left=0.06, right=0.95, hspace=0.38, wspace=0.32)
    pdf.savefig(fig)
    plt.close(fig)

    fig = plt.figure(figsize=(16.5, 10.8))
    gs = gridspec.GridSpec(1, 1)
    ax_table = fig.add_subplot(gs[0, 0])
    coverage_table = build_coverage_table(processed, activity_df).rename(
        columns={
            "month": "month",
            "% days with weight": "weight %",
            "% days with sleep": "sleep %",
            "% days with HRV": "HRV %",
            "% days with body battery": "body battery %",
            "% days with activity details": "activity detail %",
            "% days with body composition": "body comp %",
        }
    )
    render_table(
        ax_table,
        coverage_table,
        "Data Coverage / Missingness Table",
        font_size=9.2,
        header_wrap=14,
        bbox=(0.02, 0.02, 0.96, 0.92),
    )
    fig.suptitle("Garmin Data Coverage Overview", fontsize=15, fontweight="bold")
    finalize_figure(fig, top=0.9, bottom=0.05, left=0.04, right=0.98, hspace=0.2, wspace=0.2)
    pdf.savefig(fig)
    plt.close(fig)
