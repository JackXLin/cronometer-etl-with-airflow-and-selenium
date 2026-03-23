"""Garmin analytics report pages for the PDF-first reporting section."""

from __future__ import annotations

import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np
import pandas as pd

from garmin_report_helpers import (
    GARMIN_LAG_METRICS,
    RECOVERY_SCATTER_COLUMNS,
    build_lag_correlation_result,
    build_outlier_diagnostic_table,
    prepare_garmin_report_inputs,
)
from visualisation_garmin_analytics_sections import (
    page_activity_type_contribution,
    page_calendar_and_coverage,
    page_recovery_regime_comparison,
    page_weekly_energy_balance_dashboard,
)
from visualisation_garmin_layout import (
    DEFAULT_GARMIN_ACTIVITY_PATH,
    finalize_figure,
    load_optional_garmin_activity_data,
    render_empty_axis,
    render_table,
    style_date_axis,
    wrap_labels,
)


def page_garmin_adjusted_tdee_panel(pdf, processed: pd.DataFrame, tdee_estimates: dict) -> None:
    """Render the Garmin-adjusted TDEE context page.

    Args:
        pdf: PdfPages object.
        processed (pd.DataFrame): Enriched processed dataset.
        tdee_estimates (dict): TDEE estimate output.

    Returns:
        None
    """
    fig, (ax_top, ax_middle, ax_bottom) = plt.subplots(
        3,
        1,
        figsize=(16.2, 13.4),
        sharex=True,
        gridspec_kw={"height_ratios": [1.02, 0.72, 1.0]},
    )
    intake_7d = processed["Energy (kcal)"].rolling(7, min_periods=1).mean()
    tdee_line = processed.get("TDEE_adaptive", pd.Series(np.nan, index=processed.index))
    activity_daily = processed["garmin_activity_proxy_kcal"]
    activity_7d = processed["garmin_activity_proxy_7d"]
    ax_top.plot(processed["Date"], intake_7d, color="#4c78a8", linewidth=1.8, label="Intake kcal (7d)")
    ax_top.plot(processed["Date"], tdee_line, color="#e45756", linewidth=1.8, label="Current model TDEE")
    valid_gap = ~(intake_7d.isna() | tdee_line.isna())
    ax_top.fill_between(
        processed["Date"],
        intake_7d,
        tdee_line,
        where=valid_gap & (intake_7d >= tdee_line),
        color="#e45756",
        alpha=0.12,
        interpolate=True,
    )
    ax_top.fill_between(
        processed["Date"],
        intake_7d,
        tdee_line,
        where=valid_gap & (intake_7d < tdee_line),
        color="#4c78a8",
        alpha=0.08,
        interpolate=True,
    )
    ax_top.set_title("Garmin-Adjusted TDEE Context", fontsize=14, fontweight="bold")
    ax_top.set_ylabel("Calories / Day")
    ax_top.grid(True, alpha=0.3)
    ax_top.legend(
        fontsize=8.5,
        loc="upper left",
        ncol=2,
        frameon=False,
    )

    ax_middle.plot(
        processed["Date"],
        activity_daily,
        color="#b7dfb3",
        linewidth=1.0,
        alpha=0.8,
        label="Daily activity proxy",
    )
    ax_middle.fill_between(processed["Date"], activity_7d, color="#54a24b", alpha=0.14)
    ax_middle.plot(
        processed["Date"],
        activity_7d,
        color="#2f7d32",
        linewidth=1.8,
        label="Garmin activity proxy (7d)",
    )
    ax_middle.set_ylabel("Activity proxy")
    ax_middle.set_title("Garmin Activity Proxy Trend", fontsize=12, fontweight="bold")
    ax_middle.grid(True, alpha=0.25)
    ax_middle.legend(fontsize=8, loc="upper left", ncol=2, frameon=False)

    weight_line, = ax_bottom.plot(
        processed["Date"],
        processed["Weight_smoothed"],
        color="#2a9d8f",
        linewidth=2.2,
        label="Smoothed weight trend",
    )
    activity_regime = activity_7d.rolling(14, min_periods=5).mean()
    valid_regime = activity_regime.dropna()
    if not valid_regime.empty:
        high_threshold = valid_regime.quantile(0.67)
        low_threshold = valid_regime.quantile(0.33)
        regime_state = pd.Series("normal", index=processed.index, dtype="object")
        regime_state.loc[activity_regime >= high_threshold] = "high"
        regime_state.loc[activity_regime <= low_threshold] = "low"
        for state, color, alpha in [
            ("high", "#54a24b", 0.14),
            ("low", "#e45756", 0.12),
        ]:
            start_idx = None
            for idx, current_state in enumerate(regime_state.tolist() + ["stop"]):
                if current_state == state and start_idx is None:
                    start_idx = idx
                elif current_state != state and start_idx is not None:
                    end_idx = idx - 1
                    if end_idx - start_idx >= 3:
                        ax_bottom.axvspan(
                            processed["Date"].iloc[start_idx],
                            processed["Date"].iloc[end_idx],
                            color=color,
                            alpha=alpha,
                            linewidth=0,
                        )
                    start_idx = None

    ax_bottom.set_ylabel("Weight (kg)")
    ax_bottom.set_title("Smoothed Weight Trend vs Activity Regimes", fontsize=12, fontweight="bold")
    ax_bottom.grid(True, alpha=0.3)
    ax_bottom.legend(
        handles=[
            weight_line,
            Patch(facecolor="#54a24b", alpha=0.14, label="Higher-activity regime"),
            Patch(facecolor="#e45756", alpha=0.12, label="Lower-activity regime"),
        ],
        fontsize=8,
        loc="upper left",
        frameon=False,
    )
    style_date_axis(ax_bottom)

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
        0.065,
        0.03,
        summary_text,
        fontsize=10,
        va="bottom",
        bbox=dict(boxstyle="round,pad=0.4", fc="#f8f4d7", alpha=0.9),
    )
    finalize_figure(fig, top=0.92, bottom=0.1, left=0.08, right=0.95, hspace=0.26)
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
    recent_processed = processed.sort_values("Date").tail(30).reset_index(drop=True)
    recent_daily_result = build_lag_correlation_result(
        recent_processed,
        GARMIN_LAG_METRICS,
        "Daily Weight change (kg)",
    )
    recent_trend_result = build_lag_correlation_result(
        recent_processed,
        GARMIN_LAG_METRICS,
        "Weight_trend_change_7d",
    )
    fig = plt.figure(figsize=(16.8, 14.2))
    gs = gridspec.GridSpec(
        3,
        3,
        height_ratios=[1.0, 1.0, 0.82],
        width_ratios=[1.0, 1.0, 0.06],
        hspace=0.44,
        wspace=0.28,
    )
    ax_daily = fig.add_subplot(gs[0, 0])
    ax_trend = fig.add_subplot(gs[0, 1])
    ax_recent_daily = fig.add_subplot(gs[1, 0])
    ax_recent_trend = fig.add_subplot(gs[1, 1])
    ax_colorbar = fig.add_subplot(gs[:2, 2])
    ax_table = fig.add_subplot(gs[2, :2])
    shared_image = None

    for axis, matrix, title in [
        (ax_daily, daily_result.correlation_matrix, "All-Time: Lag vs Daily Weight Change"),
        (ax_trend, trend_result.correlation_matrix, "All-Time: Lag vs 7-Day Trend Weight Change"),
        (ax_recent_daily, recent_daily_result.correlation_matrix, "Recent 30d: Lag vs Daily Weight Change"),
        (ax_recent_trend, recent_trend_result.correlation_matrix, "Recent 30d: Lag vs 7-Day Trend Weight Change"),
    ]:
        if matrix.empty:
            render_empty_axis(axis, title, "Insufficient data")
            continue
        im = axis.imshow(matrix.values, aspect="auto", cmap="RdBu_r", vmin=-0.5, vmax=0.5)
        shared_image = im
        axis.set_title(title, fontsize=12, fontweight="bold")
        axis.set_xticks(range(len(matrix.columns)))
        axis.set_xticklabels([f"Lag {column.replace('lag_', '')}" for column in matrix.columns], fontsize=9)
        axis.set_yticks(range(len(matrix.index)))
        axis.set_yticklabels(wrap_labels(matrix.index, width=14), fontsize=8.2)
        for row_idx in range(len(matrix.index)):
            for col_idx in range(len(matrix.columns)):
                value = matrix.iloc[row_idx, col_idx]
                if not np.isnan(value):
                    axis.text(col_idx, row_idx, f"{value:+.2f}", ha="center", va="center", fontsize=8)

    if shared_image is not None:
        colorbar = fig.colorbar(shared_image, cax=ax_colorbar)
        colorbar.set_label("Pearson r")
        colorbar.ax.tick_params(labelsize=8)
    else:
        ax_colorbar.axis("off")

    lag_table = daily_result.summary_table[["metric", "best_lag", "best_correlation"]].rename(
        columns={
            "metric": "metric",
            "best_lag": "all-time lag",
            "best_correlation": "all-time r",
        }
    )
    lag_table = lag_table.merge(
        recent_daily_result.summary_table[["metric", "best_lag", "best_correlation"]].rename(
            columns={
                "metric": "metric",
                "best_lag": "recent 30d lag",
                "best_correlation": "recent 30d r",
            }
        ),
        on="metric",
        how="outer",
    )
    render_table(ax_table, lag_table, "Lag Correlation Summary", font_size=8.3, header_wrap=12)
    fig.suptitle("Garmin Lag Heatmaps", fontsize=15, fontweight="bold")
    finalize_figure(fig, top=0.9, bottom=0.05, left=0.07, right=0.95, hspace=0.42, wspace=0.28)
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
    fig = plt.figure(figsize=(16.4, 12.5))
    gs = gridspec.GridSpec(2, 1, height_ratios=[1.1, 0.95], hspace=0.34)
    ax_heatmap = fig.add_subplot(gs[0, 0])
    ax_table = fig.add_subplot(gs[1, 0])
    if diagnostics.empty:
        render_empty_axis(ax_heatmap, "Weight Spike Attribution", "No weight spikes exceeded the configured threshold.")
        render_table(ax_table, diagnostics, "Outlier-Day Diagnostic Table")
    else:
        heatmap_columns = [
            ("carbs z", "carbs z-score"),
            ("sodium z", "sodium z-score"),
            ("water z", "water z-score"),
            ("sleep z", "sleep score z-score"),
            ("stress z", "stress z-score"),
            ("steps z", "steps z-score"),
            ("active kcal z", "active kcal z-score"),
            ("resting HR Δ", "resting HR delta"),
            ("body battery min", "body battery min"),
            ("HRV Δ", "HRV delta"),
        ]
        heatmap_df = diagnostics.head(10)[[column_name for _display_name, column_name in heatmap_columns]].copy()
        heatmap_df.index = diagnostics.head(10)["date"]
        im = ax_heatmap.imshow(heatmap_df.values, aspect="auto", cmap="coolwarm", vmin=-3, vmax=3)
        ax_heatmap.set_title("Weight Spike Attribution Z-Scores", fontsize=13, fontweight="bold")
        ax_heatmap.set_xticks(range(len(heatmap_columns)))
        ax_heatmap.set_xticklabels(wrap_labels([display_name for display_name, _column_name in heatmap_columns], width=11), rotation=0, fontsize=8.5)
        ax_heatmap.set_yticks(range(len(heatmap_df.index)))
        ax_heatmap.set_yticklabels(heatmap_df.index, fontsize=9)
        for row_idx in range(len(heatmap_df.index)):
            for col_idx in range(len(heatmap_columns)):
                value = heatmap_df.iloc[row_idx, col_idx]
                if not np.isnan(value):
                    ax_heatmap.text(col_idx, row_idx, f"{value:+.1f}", ha="center", va="center", fontsize=8)
        colorbar = fig.colorbar(im, ax=ax_heatmap, shrink=0.82, pad=0.02)
        colorbar.set_label("Standard deviations")
        colorbar.ax.tick_params(labelsize=8)
        render_table(
            ax_table,
            diagnostics[[
                "date",
                "weight delta",
                "carbs z-score",
                "sodium z-score",
                "sleep score z-score",
                "stress z-score",
                "HRV delta",
                "activity kcal",
                "likely explanation tag",
            ]].head(8),
            "Outlier-Day Diagnostic Table",
            font_size=7.4,
            header_wrap=13,
            max_cell_chars=20,
        )
    fig.suptitle("Weight Spike Attribution", fontsize=15, fontweight="bold")
    finalize_figure(fig, top=0.9, bottom=0.05, left=0.07, right=0.94, hspace=0.34)
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
    fig = plt.figure(figsize=(17.2, 11.4))
    gs = gridspec.GridSpec(2, 4, width_ratios=[1.0, 1.0, 1.0, 0.08], hspace=0.35, wspace=0.38)
    axes = np.array(
        [
            [fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1]), fig.add_subplot(gs[0, 2])],
            [fig.add_subplot(gs[1, 0]), fig.add_subplot(gs[1, 1]), fig.add_subplot(gs[1, 2])],
        ]
    )
    ax_colorbar = fig.add_subplot(gs[:, 3])
    color_metric = processed.get("Carbs (g)", processed.get("Sodium (mg)", pd.Series(np.nan, index=processed.index)))
    color_label = "Prior-day carbs" if "Carbs (g)" in processed.columns else "Prior-day sodium"
    shared_scatter = None
    for ax, (label, column_name) in zip(axes.flat, RECOVERY_SCATTER_COLUMNS.items()):
        if column_name not in processed.columns:
            render_empty_axis(ax, label, "Unavailable")
            continue
        x = pd.to_numeric(processed[column_name], errors="coerce")
        y = pd.to_numeric(processed["Daily Weight change (kg)"], errors="coerce")
        valid = ~(x.isna() | y.isna() | color_metric.isna())
        if valid.sum() < 5:
            render_empty_axis(ax, label, "Insufficient data")
            continue
        scatter = ax.scatter(x[valid], y[valid], c=color_metric[valid], cmap="viridis", alpha=0.75, s=28, edgecolors="none")
        shared_scatter = scatter
        ax.axhline(0, color="black", linewidth=1, alpha=0.5)
        ax.set_title(label, fontsize=11, fontweight="bold")
        ax.set_xlabel(label)
        ax.set_ylabel("Next-day weight change (kg)")
        ax.grid(True, alpha=0.2)
        ax.tick_params(labelsize=8.5)
    if shared_scatter is not None:
        colorbar = fig.colorbar(shared_scatter, cax=ax_colorbar)
        colorbar.set_label(color_label)
        colorbar.ax.tick_params(labelsize=8)
    else:
        ax_colorbar.axis("off")
    fig.suptitle("Recovery vs Scale-Noise Scatter", fontsize=15, fontweight="bold")
    finalize_figure(fig, top=0.9, bottom=0.08, left=0.07, right=0.94, hspace=0.34, wspace=0.36)
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
