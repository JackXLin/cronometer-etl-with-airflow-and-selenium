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
import numpy as np
import os
import pandas as pd
from scipy import stats

from tdee_calculator import KCAL_PER_KG
from visualisation_helpers import get_bmi_category


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

    # --- Top panel: weight trend ---
    ax_top.plot(processed["Date"], processed["Weight (kg)"],
                alpha=0.35, color="lightgreen", label="Daily Weight")
    if "Weight_smoothed" in processed.columns:
        ax_top.plot(processed["Date"], processed["Weight_smoothed"],
                    color="green", linewidth=2, label="Smoothed (EMA-10)")

    # Overall linear trend
    days_num = (processed["Date"] - processed["Date"].min()).dt.days
    valid = ~(processed["Weight (kg)"].isna() | days_num.isna())
    if valid.sum() > 1:
        slope, intercept, r_val, _, _ = stats.linregress(
            days_num[valid], processed["Weight (kg)"][valid],
        )
        trend = slope * days_num + intercept
        ax_top.plot(processed["Date"], trend, "--", color="red", linewidth=2,
                    label=f"Trend ({slope * 7:+.2f} kg/wk, R\u00b2={r_val**2:.3f})")

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

    ax_top.set_title("Weight Progress with Smoothed Trend", fontsize=14,
                     fontweight="bold")
    ax_top.set_ylabel("Weight (kg)")
    ax_top.set_ylim(100, 140)
    ax_top.legend(fontsize=9)
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
        d = np.arange(len(smoothed_recent))
        sm_slope, sm_intercept = np.polyfit(d, smoothed_recent, 1)

        # Standard error for confidence band
        residuals = smoothed_recent.values - (sm_slope * d + sm_intercept)
        se = np.std(residuals)

        future = np.arange(len(smoothed_recent), len(smoothed_recent) + proj_days)

        # Scenario 1: current trend
        current_proj = sm_slope * future + sm_intercept
        upper = current_proj + 1.96 * se
        lower = current_proj - 1.96 * se

        ax_bot.plot(d, smoothed_recent, "o-", color="blue", markersize=3,
                    label="Recent (smoothed)")
        ax_bot.plot(future, current_proj, "--", color="blue", linewidth=2,
                    label="Current Trend")
        ax_bot.fill_between(future, lower, upper, color="blue", alpha=0.1,
                            label="95% CI")

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
                ("Aggressive (TDEE−750)", est_tdee - 750, "#e74c3c", "-"),
                ("Standard (TDEE−500)", est_tdee - 500, "#e67e22", "--"),
                ("Slow (TDEE−250)", est_tdee - 250, "#f1c40f", "-."),
                (f"Current avg ({avg_intake:.0f})", avg_intake, "#2ecc71", ":"),
            ]

            for label, cal_level, color, ls in scenarios:
                deficit = cal_level - est_tdee
                daily_kg = deficit / KCAL_PER_KG
                proj = last_weight + daily_kg * np.arange(1, proj_days + 1)
                ax_bot.plot(future, proj, ls, color=color, linewidth=2,
                            label=label)

                # Days to target calculation
                if abs(daily_kg) > 1e-5 and kg_to_target * daily_kg < 0:
                    dtg = abs(kg_to_target / daily_kg)
                    scenario_table_rows.append([label, f"{cal_level:.0f}",
                                                f"{dtg:.0f}"])
                else:
                    scenario_table_rows.append([label, f"{cal_level:.0f}",
                                                "N/A"])

        ax_bot.axhline(y=target_weight_kg, color="purple", linestyle=":",
                       linewidth=2, label="Target Weight")

        ax_bot.set_title(f"{proj_days}-Day Weight Projection (Multi-Scenario)",
                         fontsize=14, fontweight="bold")
        ax_bot.set_xlabel("Days from start of recent window")
        ax_bot.set_ylabel("Weight (kg)")
        ax_bot.set_ylim(100, 140)
        ax_bot.legend(fontsize=8, loc="upper right")
        ax_bot.grid(True, alpha=0.3)

        # Inset table: days to target per scenario
        if scenario_table_rows:
            inset_tbl = ax_bot.table(
                cellText=scenario_table_rows,
                colLabels=["Scenario", "kcal/day", "Days to Target"],
                cellLoc="center",
                loc="lower left",
                bbox=[0.02, 0.02, 0.45, 0.28],
            )
            inset_tbl.auto_set_font_size(False)
            inset_tbl.set_fontsize(8)
            for key, cell in inset_tbl.get_celld().items():
                cell.set_alpha(0.85)
                if key[0] == 0:
                    cell.set_facecolor("#d5e8d4")
                    cell.set_fontsize(8)
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
    Four-panel TDEE dashboard:
        Top-left:  TDEE method comparison bars.
        Top-right: Adaptive TDEE over time with rolling alternatives.
        Bottom-left: Intake vs TDEE bar with surplus/deficit annotation.
        Bottom-right: Text summary with recommendations.

    Args:
        pdf: PdfPages object.
        processed (pd.DataFrame): Data with TDEE columns.
        tdee_estimates (dict): TDEE results.
        target_calories (int): Daily calorie target.
        target_weight_kg (float): Goal weight for colour logic.
    """
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 12))

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
        bars = ax1.bar(range(len(methods)), vals, color=cols, alpha=0.7)
        ax1.set_xticks(range(len(methods)))
        ax1.set_xticklabels(methods, rotation=45, ha="right")
        ax1.set_title("TDEE Estimates by Method", fontsize=12, fontweight="bold")
        ax1.set_ylabel("Calories / Day")
        ax1.grid(True, alpha=0.3, axis="y")
        for bar, v in zip(bars, vals):
            ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 20,
                     f"{v:.0f}", ha="center", va="bottom", fontsize=9)

    # --- Top-right: TDEE over time ---
    if "TDEE_adaptive" in processed.columns:
        ax2.plot(processed["Date"], processed["TDEE_adaptive"],
                 label="Adaptive EMA", color="green", linewidth=2)
    if "TDEE_14d" in processed.columns:
        ax2.plot(processed["Date"], processed["TDEE_14d"],
                 label="Rolling 14d", alpha=0.6, color="orange")
    if "TDEE_30d" in processed.columns:
        ax2.plot(processed["Date"], processed["TDEE_30d"],
                 label="Rolling 30d", alpha=0.6, color="blue")
    if "weighted_average" in tdee_estimates:
        ax2.axhline(y=tdee_estimates["weighted_average"], color="red",
                     linestyle="--",
                     label=f'Best est: {tdee_estimates["weighted_average"]:.0f}')
    ax2.set_title("TDEE Estimates Over Time", fontsize=12, fontweight="bold")
    ax2.set_ylabel("Calories / Day")
    ax2.legend(fontsize=8)
    ax2.grid(True, alpha=0.3)
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45)

    # --- Bottom-left: Intake vs TDEE ---
    recent = processed.tail(30)
    avg_intake = recent["Energy (kcal)"].mean()
    est_tdee = tdee_estimates.get("weighted_average")

    if est_tdee:
        surplus = avg_intake - est_tdee
        bar_vals = [avg_intake, est_tdee]
        bar_labels = ["Avg Intake", "Est. TDEE"]
        bar_cols = ["lightblue", "lightcoral"]
        b = ax3.bar(bar_labels, bar_vals, color=bar_cols, alpha=0.7)
        ax3.set_title("Intake vs TDEE (Last 30 Days)", fontsize=12,
                      fontweight="bold")
        ax3.set_ylabel("Calories / Day")
        for bi, vi in zip(b, bar_vals):
            ax3.text(bi.get_x() + bi.get_width() / 2, bi.get_height() + 20,
                     f"{vi:.0f}", ha="center", va="bottom", fontsize=10,
                     fontweight="bold")
        # Reason: colour depends on whether surplus/deficit moves weight
        # toward or away from the goal.
        current_weight = processed["Weight (kg)"].dropna().iloc[-1]
        wants_loss = current_weight > target_weight_kg
        # Deficit is good when trying to lose; surplus is good when gaining.
        goal_aligned = (surplus < 0 and wants_loss) or (
            surplus > 0 and not wants_loss
        )
        sc = "green" if goal_aligned else "red"
        ax3.text(0.5, max(bar_vals) * 0.5,
                 f'{"Surplus" if surplus > 0 else "Deficit"}:\n{abs(surplus):.0f} cal/day',
                 ha="center", va="center", fontsize=12, fontweight="bold",
                 color=sc, bbox=dict(boxstyle="round,pad=0.3", fc=sc, alpha=0.2))

    # --- Bottom-right: text summary ---
    ax4.axis("off")
    txt = _build_tdee_summary_text(tdee_estimates, avg_intake)
    ax4.text(0.05, 0.95, txt, transform=ax4.transAxes, fontsize=10,
             verticalalignment="top", fontfamily="monospace",
             bbox=dict(boxstyle="round,pad=0.5", fc="lightyellow", alpha=0.8))

    plt.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)


def _build_tdee_summary_text(tdee_estimates: dict, avg_intake: float) -> str:
    """
    Build the TDEE summary text block for the dashboard.

    Args:
        tdee_estimates (dict): All TDEE method results.
        avg_intake (float): Recent average calorie intake.

    Returns:
        str: Formatted multi-line summary.
    """
    lines = ["TDEE ESTIMATION SUMMARY\n"]

    if "weighted_average" in tdee_estimates:
        lines.append(f"Best Estimate: {tdee_estimates['weighted_average']:.0f} cal/day\n")

    lines.append("Method Results:")
    label_map = {
        "adaptive": "Adaptive EMA",
        "rolling_30d": "Rolling 30d",
        "rolling_14d": "Rolling 14d",
        "stable_periods": "Stable Periods",
        "regression": "Regression",
        "recent_30d": "Recent 30d",
    }
    for key, label in label_map.items():
        val = tdee_estimates.get(key)
        if val and isinstance(val, (int, float)) and 1200 < val < 4000:
            lines.append(f"  {label}: {val:.0f} cal")

    if "stable_periods_count" in tdee_estimates:
        lines.append("\nData Quality:")
        lines.append(f"  Stable periods found: {tdee_estimates['stable_periods_count']}")
    if "regression_r2" in tdee_estimates:
        lines.append(f"  Regression R2: {tdee_estimates['regression_r2']:.3f}")

    est = tdee_estimates.get("weighted_average")
    if est:
        lines.append("\nRecommendations:")
        if avg_intake > est + 200:
            lines.append("  Consider reducing intake for weight loss")
        elif avg_intake < est - 200:
            lines.append("  Consider increasing intake")
        else:
            lines.append("  Current intake appears well-balanced")
        lines.append(f"  For weight loss: ~{est - 500:.0f} cal/day")
        lines.append(f"  For weight gain: ~{est + 300:.0f} cal/day")

    return "\n".join(lines)


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

    # --- Top-left: energy rolling averages + weight overlay ---
    ax1.plot(processed["Date"], processed["Energy 7 days avg (kcal)"],
             label="7d Avg", color="blue", linewidth=2)
    ax1.plot(processed["Date"], processed["Energy 30 days avg (kcal)"],
             label="30d Avg", color="orange", linewidth=2)
    ax1.axhline(y=target_calories, color="red", linestyle=":", alpha=0.7,
                label="Target")
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
    ax1b.set_ylim(100, 140)
    ax1b.legend(loc="upper right", fontsize=8)

    # --- Top-right: macro pie chart ---
    recent = processed.tail(30)
    avg_macros = [
        recent["Protein_pct"].mean(),
        recent["Carbs_pct"].mean(),
        recent["Fat_pct"].mean(),
    ]
    macro_colors = ["#ff6b6b", "#ffa726", "#42a5f5"]
    ax2.pie(avg_macros, labels=["Protein", "Carbs", "Fat"],
            colors=macro_colors, autopct="%1.1f%%")
    ax2.set_title("Macro Distribution (Last 30 Days)", fontsize=12,
                  fontweight="bold")

    # --- Bottom-left: calorie deficit/surplus ---
    deficit = processed["Calorie_deficit"]
    bar_colors = ["green" if x > 0 else "red" for x in deficit]
    ax3.bar(processed["Date"], deficit, color=bar_colors, alpha=0.7)
    ax3.axhline(y=0, color="black", linestyle="-", alpha=0.5)
    ax3.set_title("Daily Calorie Deficit / Surplus", fontsize=12,
                  fontweight="bold")
    ax3.set_ylabel("Calories vs Target")
    ax3.grid(True, alpha=0.3)
    plt.setp(ax3.xaxis.get_majorticklabels(), rotation=45)

    # --- Bottom-right: adherence rate ---
    adherence = processed["On_track_calories"].rolling(7).mean() * 100
    ax4.plot(processed["Date"], adherence, color="green", linewidth=2)
    ax4.set_title("7-Day Calorie Target Adherence Rate", fontsize=12,
                  fontweight="bold")
    ax4.set_ylabel("Adherence (%)")
    ax4.set_ylim(0, 100)
    ax4.grid(True, alpha=0.3)
    plt.setp(ax4.xaxis.get_majorticklabels(), rotation=45)

    plt.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)
