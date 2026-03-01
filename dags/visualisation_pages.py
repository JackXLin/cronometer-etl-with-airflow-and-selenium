"""
PDF page renderers for the first three report pages.

Pages:
    1. Weight Trend & Calorie-Aware Prediction
    2. TDEE Dashboard
    3. Energy & Macros

Extracted from visualisation.py to keep every module under 500 lines.
"""

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.gridspec as gridspec
import numpy as np
import os
import pandas as pd
from scipy import stats

from tdee_calculator import KCAL_PER_KG
from visualisation_helpers import get_bmi_category
from visualisation_helpers_v2 import (
    compute_dynamic_ylim,
    compute_healthy_bmi_range,
    build_tdee_summary_text,
)


def target_calories_from_env() -> int:
    """
    Read target calories from the environment.

    Returns:
        int: Target daily calorie intake.
    """
    return int(os.getenv("TARGET_CALORIES", 2000))


# ─────────────────────────────────────────────────────────────────────────────
# PAGE 1 — Weight Trend & Calorie-Aware Prediction
# ─────────────────────────────────────────────────────────────────────────────
def page_weight_prediction(pdf, processed, target_weight_kg,
                           tdee_estimates, height_cm):
    """
    Top: smoothed weight with overall trend, target line, BMI annotation.
    Bottom: calorie-aware multi-scenario weight projection with confidence.

    Args:
        pdf: PdfPages object.
        processed (pd.DataFrame): Data with Weight_smoothed column.
        target_weight_kg (float): Goal weight.
        tdee_estimates (dict): TDEE results.
        height_cm (float): User height for BMI annotation.
    """
    fig, (ax_top, ax_bot) = plt.subplots(2, 1, figsize=(12, 10))
    y_min, y_max = compute_dynamic_ylim(processed, target_weight_kg)

    # --- Top panel: weight trend ---
    ax_top.plot(processed["Date"], processed["Weight (kg)"],
                alpha=0.35, color="lightgreen", label="Daily Weight")
    if "Weight_smoothed" in processed.columns:
        ax_top.plot(processed["Date"], processed["Weight_smoothed"],
                    color="green", linewidth=2, label="Smoothed (EMA-10)")

    # Healthy BMI zone shading
    bmi_low, bmi_high = compute_healthy_bmi_range(height_cm)
    ax_top.axhspan(bmi_low, bmi_high, alpha=0.08, color="green",
                   label=f"Normal BMI ({bmi_low:.0f}-{bmi_high:.0f} kg)")

    # Segmented trend: last 90 days vs all-time
    days_num = (processed["Date"] - processed["Date"].min()).dt.days
    valid = ~(processed["Weight (kg)"].isna() | days_num.isna())
    if valid.sum() > 1:
        slope, intercept, r_val, _, _ = stats.linregress(
            days_num[valid], processed["Weight (kg)"][valid],
        )
        trend = slope * days_num + intercept
        ax_top.plot(processed["Date"], trend, "--", color="red",
                    linewidth=1.5, alpha=0.5,
                    label=f"All-time ({slope * 7:+.2f} kg/wk)")

    # Reason: recent 90-day trend is more actionable than all-time
    # because it reflects current behaviour, not historical.
    recent_90 = processed.tail(90)
    if len(recent_90) > 7:
        days_90 = (recent_90["Date"] - recent_90["Date"].min()).dt.days
        valid_90 = ~(recent_90["Weight (kg)"].isna() | days_90.isna())
        if valid_90.sum() > 1:
            sl90, int90, r90, _, _ = stats.linregress(
                days_90[valid_90], recent_90["Weight (kg)"][valid_90],
            )
            trend_90 = sl90 * days_90 + int90
            ax_top.plot(recent_90["Date"], trend_90, "-", color="red",
                        linewidth=2,
                        label=f"Last 90d ({sl90 * 7:+.2f} kg/wk)")

    ax_top.axhline(y=target_weight_kg, color="purple", linestyle=":",
                   linewidth=2, label="Target Weight")

    # BMI annotation on latest point
    latest_bmi = processed["BMI"].iloc[-1]
    if not pd.isna(latest_bmi):
        cat = get_bmi_category(latest_bmi)
        ax_top.annotate(
            f"BMI {latest_bmi:.1f} ({cat})",
            xy=(processed["Date"].iloc[-1], processed["Weight (kg)"].iloc[-1]),
            xytext=(20, 20), textcoords="offset points",
            arrowprops=dict(arrowstyle="->", color="gray"),
            fontsize=10, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.3", fc="lightyellow", alpha=0.9),
        )

    # "Weight Lost" annotation
    start_wt = processed["Weight (kg)"].dropna().iloc[0]
    current_wt = processed["Weight (kg)"].dropna().iloc[-1]
    total_change = current_wt - start_wt
    change_label = "lost" if total_change < 0 else "gained"
    ax_top.text(
        0.02, 0.02,
        f"Total {change_label}: {abs(total_change):.1f} kg",
        transform=ax_top.transAxes, fontsize=11, fontweight="bold",
        color="green" if total_change < 0 else "red",
        bbox=dict(boxstyle="round,pad=0.3", fc="white", alpha=0.85),
    )

    ax_top.set_title("Weight Progress with Smoothed Trend", fontsize=14,
                     fontweight="bold")
    ax_top.set_ylabel("Weight (kg)")
    ax_top.set_ylim(y_min, y_max)
    ax_top.legend(fontsize=8, loc="lower right")
    ax_top.grid(True, alpha=0.3)

    # --- Bottom panel: calorie-aware multi-scenario projection ---
    proj_days = 90
    recent = processed.tail(30)
    if "Weight_smoothed" in recent.columns:
        smoothed_recent = recent["Weight_smoothed"].dropna()
    else:
        smoothed_recent = recent["Weight (kg)"].dropna()

    if len(smoothed_recent) > 1:
        last_weight = smoothed_recent.iloc[-1]
        last_date = recent["Date"].iloc[-1]
        d = np.arange(len(smoothed_recent))
        sm_slope, sm_intercept = np.polyfit(d, smoothed_recent, 1)

        # Standard error for confidence band
        residuals = smoothed_recent.values - (sm_slope * d + sm_intercept)
        se = np.std(residuals)

        future = np.arange(len(smoothed_recent), len(smoothed_recent) + proj_days)

        # Reason: use calendar dates on x-axis so the user can relate
        # projections to real months, not abstract day indices.
        from datetime import timedelta as td
        recent_dates = recent["Date"].values
        future_dates = pd.date_range(
            start=last_date + td(days=1), periods=proj_days, freq="D",
        )

        # Scenario 1: current trend
        current_proj = sm_slope * future + sm_intercept
        upper = current_proj + 1.96 * se
        lower = current_proj - 1.96 * se

        ax_bot.plot(recent_dates, smoothed_recent, "o-", color="blue",
                    markersize=3, label="Recent (smoothed)")
        ax_bot.plot(future_dates, current_proj, "--", color="blue",
                    linewidth=2, label="Current Trend")
        ax_bot.fill_between(future_dates, lower, upper, color="blue",
                            alpha=0.1, label="95% CI")

        # Multi-scenario TDEE-based projections
        est_tdee = tdee_estimates.get("weighted_average")
        scenario_table_rows = []
        kg_to_target = last_weight - target_weight_kg

        if est_tdee:
            avg_intake = recent["Energy (kcal)"].mean()
            # Reason: each scenario represents a different daily calorie
            # intake level; the resulting weight trajectory depends on
            # the caloric surplus/deficit relative to TDEE.
            scenarios = [
                ("Aggressive (TDEE\u2212750)", est_tdee - 750, "#e74c3c", "-"),
                ("Standard (TDEE\u2212500)", est_tdee - 500, "#e67e22", "--"),
                ("Slow (TDEE\u2212250)", est_tdee - 250, "#f1c40f", "-."),
                (f"Current avg ({avg_intake:.0f})", avg_intake, "#2ecc71", ":"),
            ]

            for label, cal_level, color, ls in scenarios:
                deficit = cal_level - est_tdee
                daily_kg = deficit / KCAL_PER_KG
                proj = last_weight + daily_kg * np.arange(1, proj_days + 1)
                ax_bot.plot(future_dates, proj, ls, color=color, linewidth=2,
                            label=label)

                # Days to target + projected date
                if abs(daily_kg) > 1e-5 and kg_to_target * daily_kg < 0:
                    dtg = abs(kg_to_target / daily_kg)
                    target_date = (last_date + td(days=int(dtg))
                                   ).strftime("%d %b %Y")
                    scenario_table_rows.append(
                        [label, f"{cal_level:.0f}",
                         f"{dtg:.0f}", target_date])
                else:
                    scenario_table_rows.append(
                        [label, f"{cal_level:.0f}", "N/A", "N/A"])

        ax_bot.axhline(y=target_weight_kg, color="purple", linestyle=":",
                       linewidth=2, label="Target Weight")

        ax_bot.set_title(f"{proj_days}-Day Weight Projection (Multi-Scenario)",
                         fontsize=14, fontweight="bold")
        ax_bot.set_xlabel("Date")
        ax_bot.set_ylabel("Weight (kg)")
        ax_bot.set_ylim(y_min, y_max)
        ax_bot.legend(fontsize=8, loc="lower right")
        ax_bot.grid(True, alpha=0.3)
        plt.setp(ax_bot.xaxis.get_majorticklabels(), rotation=45)

        # Inset table: days + target date per scenario
        if scenario_table_rows:
            inset_tbl = ax_bot.table(
                cellText=scenario_table_rows,
                colLabels=["Scenario", "kcal/day", "Days", "Target Date"],
                cellLoc="center",
                loc="lower left",
                bbox=[0.02, 0.08, 0.55, 0.28],
            )
            inset_tbl.auto_set_font_size(False)
            inset_tbl.set_fontsize(7)
            for key, cell in inset_tbl.get_celld().items():
                cell.set_alpha(0.85)
                if key[0] == 0:
                    cell.set_facecolor("#d5e8d4")
                    cell.set_fontsize(7)
                else:
                    cell.set_facecolor("white")

    plt.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)


# ─────────────────────────────────────────────────────────────────────────────
# PAGE 2 — TDEE Dashboard
# ─────────────────────────────────────────────────────────────────────────────
def page_tdee_dashboard(pdf, processed, tdee_estimates, target_calories,
                        target_weight_kg=70):
    """
    Three-panel TDEE dashboard:
        Top-left:  TDEE method comparison bars.
        Top-right: Text summary with recommendations.
        Bottom (full width): Intake vs TDEE time-series.

    Args:
        pdf: PdfPages object.
        processed (pd.DataFrame): Data with TDEE columns.
        tdee_estimates (dict): TDEE results.
        target_calories (int): Daily calorie target.
        target_weight_kg (float): Goal weight for colour logic.
    """
    fig = plt.figure(figsize=(15, 12.5))
    gs = gridspec.GridSpec(
        2, 2, figure=fig, height_ratios=[1.25, 2],
        width_ratios=[1.2, 1], hspace=0.42, wspace=0.22,
    )

    ax_bars = fig.add_subplot(gs[0, 0])
    ax_summary = fig.add_subplot(gs[0, 1])
    ax_intake = fig.add_subplot(gs[1, :])

    # --- Top-left: method comparison bars ---
    method_colors = {
        "adaptive": "#2E8B57",
        "rolling_30d": "#4682B4",
        "rolling_14d": "#6495ED",
        "stable_periods": "#FF6347",
        "regression": "#9370DB",
        "recent_30d": "#20B2AA",
    }
    method_labels = {
        "adaptive": "Adaptive EMA",
        "rolling_30d": "Rolling 30d",
        "rolling_14d": "Rolling 14d",
        "stable_periods": "Stable Periods",
        "regression": "Regression",
        "recent_30d": "Recent 30d",
    }

    methods, vals, cols = [], [], []
    for key in method_labels:
        if key in tdee_estimates and isinstance(tdee_estimates[key], (int, float)):
            if 1200 < tdee_estimates[key] < 4000:
                methods.append(method_labels[key])
                vals.append(tdee_estimates[key])
                cols.append(method_colors.get(key, "#808080"))

    if methods:
        bars = ax_bars.bar(range(len(methods)), vals, color=cols, alpha=0.7)
        ax_bars.set_xticks(range(len(methods)))
        ax_bars.set_xticklabels(methods, rotation=35, ha="right", fontsize=9)
        ax_bars.set_title("TDEE Estimates by Method", fontsize=12,
                          fontweight="bold")
        ax_bars.set_ylabel("Calories / Day")
        ax_bars.grid(True, alpha=0.3, axis="y")
        for bar, v in zip(bars, vals):
            ax_bars.text(bar.get_x() + bar.get_width() / 2,
                         bar.get_height() + 20,
                         f"{v:.0f}", ha="center", va="bottom", fontsize=9)

    # --- Top-right: text summary ---
    ax_summary.axis("off")
    recent_30 = processed.tail(30)
    recent_avg = recent_30["Energy (kcal)"].mean()
    txt = build_tdee_summary_text(
        tdee_estimates, recent_avg, target_weight_kg,
    )
    summary_fontsize = 9 if txt.count("\n") > 16 else 10
    ax_summary.text(
        0.02, 0.98, txt, transform=ax_summary.transAxes,
        fontsize=summary_fontsize, verticalalignment="top",
        fontfamily="monospace", linespacing=1.15, clip_on=True,
        bbox=dict(boxstyle="round,pad=0.35", fc="lightyellow", alpha=0.8),
    )

    # --- Bottom (full width): Intake vs TDEE time-series ---
    est_tdee = tdee_estimates.get("weighted_average")

    if est_tdee and "TDEE_adaptive" in processed.columns:
        intake_7d = processed["Energy (kcal)"].rolling(7, min_periods=1).mean()
        tdee_line = processed["TDEE_adaptive"]
        ax_intake.plot(processed["Date"], intake_7d, color="blue", linewidth=1,
                       label="7d Avg Intake")
        ax_intake.plot(processed["Date"], tdee_line, color="red", linewidth=1,
                       label="Adaptive TDEE")

        # Reason: shade the gap between intake and TDEE to show when
        # the user was in deficit (green) vs surplus (red).
        ax_intake.fill_between(
            processed["Date"], intake_7d, tdee_line,
            where=(intake_7d <= tdee_line),
            color="green", alpha=0.15, label="Deficit",
            interpolate=True,
        )
        ax_intake.fill_between(
            processed["Date"], intake_7d, tdee_line,
            where=(intake_7d > tdee_line),
            color="red", alpha=0.15, label="Surplus",
            interpolate=True,
        )
        ax_intake.set_title("Intake vs TDEE Over Time", fontsize=14,
                            fontweight="bold", pad=10)
        ax_intake.set_xlabel("Date")
        ax_intake.set_ylabel("Calories / Day")
        ax_intake.legend(fontsize=9, loc="upper left")
        ax_intake.grid(True, alpha=0.3)
        plt.setp(ax_intake.xaxis.get_majorticklabels(), rotation=45)
    else:
        # Fallback to simple bar comparison
        recent = processed.tail(30)
        avg_intake = recent["Energy (kcal)"].mean()
        if est_tdee:
            surplus = avg_intake - est_tdee
            current_weight = processed["Weight (kg)"].dropna().iloc[-1]
            wants_loss = current_weight > target_weight_kg
            goal_aligned = (surplus < 0 and wants_loss) or (
                surplus > 0 and not wants_loss
            )
            sc = "green" if goal_aligned else "red"
            b = ax_intake.bar(["Avg Intake", "Est. TDEE"],
                              [avg_intake, est_tdee],
                              color=["lightblue", "lightcoral"], alpha=0.7)
            ax_intake.set_title("Intake vs TDEE (Last 30 Days)", fontsize=14,
                                fontweight="bold", pad=10)
            ax_intake.set_ylabel("Calories / Day")

    fig.subplots_adjust(top=0.95, bottom=0.08, left=0.06, right=0.98)
    pdf.savefig(fig)
    plt.close(fig)


# ─────────────────────────────────────────────────────────────────────────────
# PAGE 3 — Energy & Macros
# ─────────────────────────────────────────────────────────────────────────────
def page_energy_macros(pdf, processed, target_calories, tolerance_pct):
    """
    Top-left:  Energy rolling averages with weight overlay.
    Top-right: Macro % pie chart (last 30 days).
    Bottom-left:  Calorie deficit/surplus bar.
    Bottom-right: 7-day adherence rate.

    Args:
        pdf: PdfPages object.
        processed (pd.DataFrame): Full dataset.
        target_calories (int): Daily calorie target.
        tolerance_pct (float): Tolerance fraction for adherence.
    """
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 12))
    y_min, y_max = compute_dynamic_ylim(processed, target_calories)

    # --- Top-left: energy rolling averages + weight + protein goal ---
    ax1.plot(processed["Date"], processed["Energy 7 days avg (kcal)"],
             label="7d Avg", color="blue", linewidth=2)
    ax1.plot(processed["Date"], processed["Energy 30 days avg (kcal)"],
             label="30d Avg", color="orange", linewidth=2)
    ax1.axhline(y=target_calories, color="red", linestyle=":", alpha=0.7,
                label="Calorie Target")
    ax1.set_ylabel("Energy (kcal)", color="blue")
    ax1.set_title("Energy Intake Rolling Averages with Weight Overlay",
                  fontsize=12, fontweight="bold")
    ax1.legend(loc="upper left", fontsize=8)
    ax1.grid(True, alpha=0.3)
    ax1.xaxis.set_major_locator(mdates.MonthLocator())
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45)

    ax1b = ax1.twinx()
    ax1b.plot(processed["Date"], processed["Weight (kg)"], color="green",
              linewidth=2, label="Weight")
    ax1b.set_ylabel("Weight (kg)", color="green")
    wt_ymin, wt_ymax = compute_dynamic_ylim(
        processed, float(os.getenv("TARGET_WEIGHT_KG", 70)),
    )
    ax1b.set_ylim(wt_ymin, wt_ymax)
    ax1b.legend(loc="upper right", fontsize=8)

    # --- Top-right: macro stacked bar with gram values ---
    recent = processed.tail(30)
    avg_protein = recent["Protein (g)"].mean()
    avg_carbs = recent["Carbs (g)"].mean()
    avg_fat = recent["Fat (g)"].mean()
    avg_prot_pct = recent["Protein_pct"].mean()
    avg_carbs_pct = recent["Carbs_pct"].mean()
    avg_fat_pct = recent["Fat_pct"].mean()
    protein_goal = int(os.getenv("PROTEIN_GOAL_G", 100))

    macro_names = ["Protein", "Carbs", "Fat"]
    macro_grams = [avg_protein, avg_carbs, avg_fat]
    macro_pcts = [avg_prot_pct, avg_carbs_pct, avg_fat_pct]
    macro_colors = ["#ff6b6b", "#ffa726", "#42a5f5"]

    bars = ax2.bar(macro_names, macro_grams, color=macro_colors, alpha=0.8)
    for bar, g, pct in zip(bars, macro_grams, macro_pcts):
        ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 2,
                 f"{g:.0f}g ({pct:.0f}%)", ha="center", va="bottom",
                 fontsize=10, fontweight="bold")
    ax2.axhline(y=protein_goal, color="red", linestyle="--", alpha=0.7,
                label=f"Protein Goal ({protein_goal}g)")
    ax2.set_title("Macro Breakdown (Last 30 Days)", fontsize=12,
                  fontweight="bold")
    ax2.set_ylabel("Grams / Day")
    ax2.legend(fontsize=8)
    ax2.grid(True, alpha=0.3, axis="y")

    # --- Bottom-left: rolling deficit/surplus area chart ---
    deficit_7d = processed["Calorie_deficit"].rolling(7, min_periods=1).mean()
    ax3.fill_between(
        processed["Date"], deficit_7d, 0,
        where=(deficit_7d >= 0), color="green", alpha=0.4,
        label="Deficit (under target)",
        interpolate=True,
    )
    ax3.fill_between(
        processed["Date"], deficit_7d, 0,
        where=(deficit_7d < 0), color="red", alpha=0.4,
        label="Surplus (over target)",
        interpolate=True,
    )
    ax3.plot(processed["Date"], deficit_7d, color="black", linewidth=1,
             alpha=0.5)
    ax3.axhline(y=0, color="black", linestyle="-", alpha=0.5)
    ax3.set_title("7-Day Rolling Calorie Deficit / Surplus (vs Target)",
                  fontsize=12, fontweight="bold")
    ax3.set_ylabel("Calories vs Target")
    ax3.legend(fontsize=8)
    ax3.grid(True, alpha=0.3)
    plt.setp(ax3.xaxis.get_majorticklabels(), rotation=45)

    # --- Bottom-right: adherence rate with 80% target ---
    adherence = processed["On_track_calories"].rolling(7).mean() * 100
    ax4.plot(processed["Date"], adherence, color="green", linewidth=2)
    ax4.axhline(y=80, color="orange", linestyle="--", alpha=0.7,
                label="80% Target")
    ax4.set_title("7-Day Calorie Target Adherence Rate", fontsize=12,
                  fontweight="bold")
    ax4.set_ylabel("Adherence (%)")
    ax4.set_ylim(0, 100)
    ax4.legend(fontsize=8)
    ax4.grid(True, alpha=0.3)
    plt.setp(ax4.xaxis.get_majorticklabels(), rotation=45)

    plt.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)
