"""Garmin-specific contextual report page renderers and helpers."""

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


GARMIN_REPORT_COLUMNS = [
    "garmin_steps",
    "garmin_sleep_seconds",
    "garmin_avg_stress",
    "garmin_body_battery_max",
    "garmin_body_battery_min",
    "garmin_resting_hr_bpm",
    "garmin_intensity_moderate_min",
    "garmin_intensity_vigorous_min",
    "garmin_activity_count",
]


def has_garmin_report_data(processed: pd.DataFrame) -> bool:
    """Return whether the processed dataset contains usable Garmin report data.

    Args:
        processed (pd.DataFrame): Processed dataset.

    Returns:
        bool: True when at least one supported Garmin metric has data.
    """
    return any(
        column_name in processed.columns and processed[column_name].notna().any()
        for column_name in GARMIN_REPORT_COLUMNS
    )



def build_garmin_adherence_insights(
    processed: pd.DataFrame,
    target_calories: int,
) -> list[str]:
    """Build plain-language insights linking Garmin context to calorie adherence.

    Args:
        processed (pd.DataFrame): Processed dataset.
        target_calories (int): Daily calorie target.

    Returns:
        list[str]: Short human-readable insight strings.
    """
    recent = processed.copy().tail(60)
    insights: list[str] = []

    if "On_track_calories" not in recent.columns and "Energy (kcal)" in recent.columns:
        recent["On_track_calories"] = recent["Energy (kcal)"] <= target_calories

    if "garmin_sleep_seconds" in recent.columns and recent["garmin_sleep_seconds"].notna().sum() >= 6:
        sleep_hours = recent["garmin_sleep_seconds"] / 3600.0
        sleep_cutoff = sleep_hours.median()
        higher_sleep = sleep_hours >= sleep_cutoff
        lower_sleep = sleep_hours < sleep_cutoff
        if higher_sleep.sum() > 0 and lower_sleep.sum() > 0 and "On_track_calories" in recent.columns:
            high_sleep_rate = recent.loc[higher_sleep, "On_track_calories"].mean() * 100
            low_sleep_rate = recent.loc[lower_sleep, "On_track_calories"].mean() * 100
            insights.append(
                f"Sleep: days at or above {sleep_cutoff:.1f}h hit calorie target {high_sleep_rate:.0f}% of the time vs {low_sleep_rate:.0f}% on shorter-sleep days."
            )

    if "garmin_avg_stress" in recent.columns and recent["garmin_avg_stress"].notna().sum() >= 6:
        stress_cutoff = recent["garmin_avg_stress"].median()
        high_stress = recent["garmin_avg_stress"] >= stress_cutoff
        low_stress = recent["garmin_avg_stress"] < stress_cutoff
        if high_stress.sum() > 0 and low_stress.sum() > 0 and "Energy (kcal)" in recent.columns:
            high_stress_over = (recent.loc[high_stress, "Energy (kcal)"] > target_calories).mean() * 100
            low_stress_over = (recent.loc[low_stress, "Energy (kcal)"] > target_calories).mean() * 100
            insights.append(
                f"Stress: above-median stress days went over target {high_stress_over:.0f}% of the time vs {low_stress_over:.0f}% on lower-stress days."
            )

    if "garmin_steps" in recent.columns and recent["garmin_steps"].notna().sum() >= 6 and "On_track_calories" in recent.columns:
        on_track_steps = recent.loc[recent["On_track_calories"], "garmin_steps"].mean()
        off_track_steps = recent.loc[~recent["On_track_calories"], "garmin_steps"].mean()
        if not np.isnan(on_track_steps) and not np.isnan(off_track_steps):
            insights.append(
                f"Steps: on-target days averaged {on_track_steps:.0f} steps vs {off_track_steps:.0f} steps on off-target days."
            )

    if "garmin_body_battery_max" in recent.columns and recent["garmin_body_battery_max"].notna().sum() >= 6:
        recent_bb = recent["garmin_body_battery_max"].mean()
        insights.append(
            f"Recovery: average daily peak body battery over the last 60 days was {recent_bb:.0f}."
        )

    if not insights:
        insights.append("Insufficient Garmin coverage for activity and recovery adherence insights.")
    return insights



def _plot_weekly_activity_summary(ax, processed: pd.DataFrame) -> None:
    """Render weekly steps, intensity minutes, and activity counts.

    Args:
        ax: Matplotlib axis.
        processed (pd.DataFrame): Processed dataset.
    """
    recent = processed.tail(56).copy()
    recent["Week"] = recent["Date"].dt.to_period("W")

    aggregations: dict[str, str] = {}
    for column_name in [
        "garmin_steps",
        "garmin_intensity_moderate_min",
        "garmin_intensity_vigorous_min",
        "garmin_activity_count",
    ]:
        if column_name in recent.columns:
            aggregations[column_name] = "sum"

    if not aggregations:
        ax.text(0.5, 0.5, "Garmin activity data unavailable", ha="center", va="center", transform=ax.transAxes)
        ax.set_title("Weekly Activity Summary", fontsize=13, fontweight="bold")
        return

    weekly = recent.groupby("Week").agg(aggregations).tail(8)
    if len(weekly) == 0:
        ax.text(0.5, 0.5, "Insufficient Garmin activity data", ha="center", va="center", transform=ax.transAxes)
        ax.set_title("Weekly Activity Summary", fontsize=13, fontweight="bold")
        return

    x_positions = np.arange(len(weekly))
    labels = [str(week)[-5:] for week in weekly.index]

    legend_handles = []
    legend_labels = []
    if "garmin_steps" in weekly.columns:
        step_bars = ax.bar(
            x_positions,
            weekly["garmin_steps"] / 1000.0,
            color="#4c78a8",
            alpha=0.75,
            label="Steps (k)",
        )
        legend_handles.append(step_bars)
        legend_labels.append("Steps (k)")
        ax.set_ylabel("Steps (thousands)")

    ax.set_xticks(x_positions)
    ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=9)
    ax.set_title("Weekly Activity Summary", fontsize=13, fontweight="bold")
    ax.grid(True, alpha=0.3, axis="y")

    total_intensity = None
    if (
        "garmin_intensity_moderate_min" in weekly.columns
        or "garmin_intensity_vigorous_min" in weekly.columns
    ):
        total_intensity = weekly.get("garmin_intensity_moderate_min", 0) + weekly.get(
            "garmin_intensity_vigorous_min",
            0,
        )

    if total_intensity is not None or "garmin_activity_count" in weekly.columns:
        ax_secondary = ax.twinx()
        if total_intensity is not None:
            intensity_line = ax_secondary.plot(
                x_positions,
                total_intensity,
                color="#f58518",
                linewidth=2,
                marker="o",
                label="Intensity min",
            )[0]
            legend_handles.append(intensity_line)
            legend_labels.append("Intensity min")
        if "garmin_activity_count" in weekly.columns:
            activity_markers = ax_secondary.scatter(
                x_positions,
                weekly["garmin_activity_count"],
                color="#54a24b",
                s=45,
                label="Activities",
                zorder=4,
            )
            legend_handles.append(activity_markers)
            legend_labels.append("Activities")
        ax_secondary.set_ylabel("Intensity / Activities")

    if legend_handles:
        ax.legend(legend_handles, legend_labels, fontsize=8, loc="upper left")



def _plot_sleep_and_stress_trends(ax, processed: pd.DataFrame) -> None:
    """Render sleep-duration and stress trends for the recent period.

    Args:
        ax: Matplotlib axis.
        processed (pd.DataFrame): Processed dataset.
    """
    recent = processed.tail(42).copy()
    handles = []
    labels = []

    if "garmin_sleep_seconds" in recent.columns and recent["garmin_sleep_seconds"].notna().any():
        sleep_hours = (recent["garmin_sleep_seconds"] / 3600.0).rolling(7, min_periods=1).mean()
        sleep_line = ax.plot(
            recent["Date"],
            sleep_hours,
            color="#4c78a8",
            linewidth=2,
            label="Sleep h (7d avg)",
        )[0]
        handles.append(sleep_line)
        labels.append("Sleep h (7d avg)")
        ax.set_ylabel("Sleep (hours)")

    if "garmin_avg_stress" in recent.columns and recent["garmin_avg_stress"].notna().any():
        stress_axis = ax.twinx()
        stress_line = stress_axis.plot(
            recent["Date"],
            recent["garmin_avg_stress"].rolling(7, min_periods=1).mean(),
            color="#e45756",
            linewidth=2,
            label="Stress (7d avg)",
        )[0]
        handles.append(stress_line)
        labels.append("Stress (7d avg)")
        stress_axis.set_ylabel("Stress")

    if not handles:
        ax.text(0.5, 0.5, "Garmin sleep and stress data unavailable", ha="center", va="center", transform=ax.transAxes)

    ax.set_title("Recovery Trends: Sleep & Stress", fontsize=13, fontweight="bold")
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=35, ha="right")
    if handles:
        ax.legend(handles, labels, fontsize=8, loc="upper left")



def _plot_body_battery_and_resting_hr(ax, processed: pd.DataFrame) -> None:
    """Render body battery range and resting heart rate trends.

    Args:
        ax: Matplotlib axis.
        processed (pd.DataFrame): Processed dataset.
    """
    recent = processed.tail(42).copy()
    has_body_battery = (
        "garmin_body_battery_max" in recent.columns
        and recent["garmin_body_battery_max"].notna().any()
    ) or (
        "garmin_body_battery_min" in recent.columns
        and recent["garmin_body_battery_min"].notna().any()
    )
    has_resting_hr = (
        "garmin_resting_hr_bpm" in recent.columns
        and recent["garmin_resting_hr_bpm"].notna().any()
    )

    handles = []
    labels = []
    if has_body_battery:
        bb_max = recent.get("garmin_body_battery_max")
        bb_min = recent.get("garmin_body_battery_min")
        if bb_max is not None and bb_min is not None:
            ax.fill_between(
                recent["Date"],
                bb_min,
                bb_max,
                color="#72b7b2",
                alpha=0.35,
                label="Body Battery range",
            )
            bb_line = ax.plot(
                recent["Date"],
                bb_max.rolling(7, min_periods=1).mean(),
                color="#2a9d8f",
                linewidth=2,
                label="Peak body battery",
            )[0]
            handles.append(bb_line)
            labels.append("Peak body battery")
        ax.set_ylabel("Body Battery")

    if has_resting_hr:
        hr_axis = ax.twinx()
        hr_line = hr_axis.plot(
            recent["Date"],
            recent["garmin_resting_hr_bpm"].rolling(7, min_periods=1).mean(),
            color="#e45756",
            linewidth=2,
            label="Resting HR",
        )[0]
        handles.append(hr_line)
        labels.append("Resting HR")
        hr_axis.set_ylabel("Resting HR (bpm)")

    if not has_body_battery and not has_resting_hr:
        ax.text(0.5, 0.5, "Body battery and resting HR unavailable", ha="center", va="center", transform=ax.transAxes)

    ax.set_title("Body Battery & Resting HR", fontsize=13, fontweight="bold")
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=35, ha="right")
    if handles:
        ax.legend(handles, labels, fontsize=8, loc="upper left")



def _render_garmin_insights(ax, processed: pd.DataFrame, target_calories: int) -> None:
    """Render a text box with Garmin-derived adherence insights.

    Args:
        ax: Matplotlib axis.
        processed (pd.DataFrame): Processed dataset.
        target_calories (int): Daily calorie target.
    """
    insight_lines = build_garmin_adherence_insights(processed, target_calories)
    ax.axis("off")
    ax.set_title("Garmin Context Insights", fontsize=13, fontweight="bold", pad=12)
    ax.text(
        0.02,
        0.98,
        "\n\n".join(insight_lines),
        transform=ax.transAxes,
        va="top",
        fontsize=10,
        bbox=dict(boxstyle="round,pad=0.45", fc="#f8f4d7", alpha=0.9),
    )



def page_garmin_context(pdf, processed: pd.DataFrame, target_calories: int) -> None:
    """Render the Garmin activity and recovery context page.

    Args:
        pdf: PdfPages object.
        processed (pd.DataFrame): Processed dataset.
        target_calories (int): Daily calorie target.

    Raises:
        ValueError: If the dataset does not contain usable Garmin columns.
    """
    if not has_garmin_report_data(processed):
        raise ValueError("Processed data does not contain Garmin metrics for reporting.")

    fig, axes = plt.subplots(2, 2, figsize=(15, 11))
    fig.suptitle("Garmin Activity & Recovery Context", fontsize=16, fontweight="bold")

    _plot_weekly_activity_summary(axes[0, 0], processed)
    _plot_sleep_and_stress_trends(axes[0, 1], processed)
    _plot_body_battery_and_resting_hr(axes[1, 0], processed)
    _render_garmin_insights(axes[1, 1], processed, target_calories)

    plt.tight_layout(rect=[0, 0, 1, 0.97])
    pdf.savefig(fig)
    plt.close(fig)
