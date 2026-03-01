"""
PDF page renderer for the Goal Progress & Calorie Budget Burn-down page.

Extracted from visualisation_pages.py to keep every module under 500 lines.
"""

from datetime import timedelta as td

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from tdee_calculator import KCAL_PER_KG


# ─────────────────────────────────────────────────────────────────────────────
# PAGE 7 — Goal Progress & Calorie Budget Burn-down
# ─────────────────────────────────────────────────────────────────────────────
def page_goal_progress(pdf, processed, target_weight_kg, tdee_estimates):
    """
    Top:    Weight milestone progress bar with projected completion date.
    Bottom: Cumulative calorie deficit burn-down chart vs required deficit.

    Args:
        pdf: PdfPages object.
        processed (pd.DataFrame): Full dataset with Weight_smoothed, TDEE cols.
        target_weight_kg (float): Goal weight.
        tdee_estimates (dict): TDEE results from estimate_tdee().
    """
    fig, (ax_top, ax_bot) = plt.subplots(2, 1, figsize=(14, 11))

    current_weight = processed["Weight (kg)"].dropna().iloc[-1]
    start_weight = processed["Weight (kg)"].dropna().iloc[0]

    # --- Top: Weight Milestone Progress ---
    ax_top.axis("off")

    total_to_lose = start_weight - target_weight_kg
    lost_so_far = start_weight - current_weight
    # Reason: clamp progress to [0, 1] to handle overshoot or wrong direction.
    pct_complete = (
        np.clip(lost_so_far / total_to_lose, 0, 1)
        if abs(total_to_lose) > 0.1 else 0
    )
    kg_remaining = current_weight - target_weight_kg

    # Determine trend from smoothed weight
    trend_wk = 0.0
    if "Weight_smoothed" in processed.columns:
        recent_30 = processed.tail(30)
        sm = recent_30["Weight_smoothed"].dropna()
        if len(sm) >= 2:
            span_days = max(
                (recent_30["Date"].iloc[-1] - recent_30["Date"].iloc[0]).days, 1,
            )
            trend_wk = (sm.iloc[-1] - sm.iloc[0]) / span_days * 7

    # Projected completion
    if abs(trend_wk) > 0.01:
        moving_toward = (
            (current_weight > target_weight_kg and trend_wk < 0)
            or (current_weight < target_weight_kg and trend_wk > 0)
        )
        if moving_toward:
            days_to_goal = abs(kg_remaining) / abs(trend_wk) * 7
            projected_date = processed["Date"].iloc[-1] + td(
                days=int(days_to_goal),
            )
            eta_str = (
                f"Projected: {projected_date.strftime('%d %b %Y')} "
                f"(~{days_to_goal:.0f} days)"
            )
            status_color = "#2ecc71"
            status_label = "On Track"
        else:
            eta_str = "Moving away from goal"
            status_color = "#e74c3c"
            status_label = "Off Track"
    else:
        eta_str = "Weight stable — no clear trend"
        status_color = "#f39c12"
        status_label = "Stalled"

    # Draw progress bar
    bar_y = 0.55
    bar_h = 0.12
    ax_top.add_patch(plt.Rectangle(
        (0.05, bar_y), 0.9, bar_h, transform=ax_top.transAxes,
        facecolor="#ecf0f1", edgecolor="gray", linewidth=2,
    ))
    ax_top.add_patch(plt.Rectangle(
        (0.05, bar_y), 0.9 * pct_complete, bar_h, transform=ax_top.transAxes,
        facecolor=status_color, edgecolor="gray", linewidth=2,
    ))

    # Labels on progress bar
    ax_top.text(0.05, bar_y + bar_h + 0.03,
                f"Start: {start_weight:.1f} kg", transform=ax_top.transAxes,
                fontsize=11, ha="left")
    ax_top.text(0.95, bar_y + bar_h + 0.03,
                f"Target: {target_weight_kg:.1f} kg",
                transform=ax_top.transAxes, fontsize=11, ha="right")
    ax_top.text(
        0.5, bar_y + bar_h / 2,
        f"{pct_complete * 100:.1f}% complete"
        f" — {kg_remaining:+.1f} kg remaining",
        transform=ax_top.transAxes, fontsize=12, ha="center",
        va="center", fontweight="bold",
    )

    # Status badge
    ax_top.text(0.5, bar_y - 0.08, f"Status: {status_label}",
                transform=ax_top.transAxes, fontsize=13, ha="center",
                fontweight="bold", color=status_color,
                bbox=dict(boxstyle="round,pad=0.4", fc="white",
                          edgecolor=status_color, linewidth=2))
    ax_top.text(0.5, bar_y - 0.18, eta_str,
                transform=ax_top.transAxes, fontsize=11, ha="center",
                color="gray")
    ax_top.text(0.5, bar_y - 0.26,
                f"Current trend: {trend_wk:+.2f} kg/week",
                transform=ax_top.transAxes, fontsize=10, ha="center",
                color="gray")

    ax_top.set_title("Weight Goal Progress", fontsize=14, fontweight="bold",
                     pad=20)

    # --- Bottom: Cumulative Calorie Deficit Burn-down ---
    total_deficit_needed = kg_remaining * KCAL_PER_KG
    # Reason: positive deficit_needed means we need to burn more than we eat
    # to reach target (weight loss scenario).

    est_tdee = tdee_estimates.get("weighted_average")
    intake = processed["Energy (kcal)"]
    dates = processed["Date"]

    if est_tdee and len(intake) > 7:
        if "TDEE_adaptive" in processed.columns:
            daily_tdee = processed["TDEE_adaptive"].fillna(est_tdee)
        else:
            daily_tdee = pd.Series(
                [est_tdee] * len(intake), index=intake.index,
            )

        daily_deficit = daily_tdee - intake
        cumulative_actual = daily_deficit.cumsum()

        n_days = len(dates)
        if abs(total_deficit_needed) > 100:
            cumulative_required = np.linspace(
                0, total_deficit_needed, n_days,
            )
        else:
            cumulative_required = np.zeros(n_days)

        ax_bot.plot(dates, cumulative_actual, color="blue", linewidth=2,
                    label="Actual Cumulative Deficit")
        ax_bot.plot(dates, cumulative_required, "--", color="red", linewidth=2,
                    label="Required Pace (linear)")
        ax_bot.axhline(
            y=total_deficit_needed, color="purple", linestyle=":",
            linewidth=2,
            label=f"Total Needed: {total_deficit_needed:,.0f} kcal",
        )

        # Shade ahead/behind
        ax_bot.fill_between(
            dates, cumulative_actual, cumulative_required,
            where=(cumulative_actual >= cumulative_required),
            color="green", alpha=0.15, label="Ahead of schedule",
        )
        ax_bot.fill_between(
            dates, cumulative_actual, cumulative_required,
            where=(cumulative_actual < cumulative_required),
            color="red", alpha=0.15, label="Behind schedule",
        )

        ax_bot.set_ylabel("Cumulative Calorie Deficit (kcal)")
        ax_bot.legend(fontsize=9)
        ax_bot.grid(True, alpha=0.3)
        plt.setp(ax_bot.xaxis.get_majorticklabels(), rotation=45)
    else:
        ax_bot.text(
            0.5, 0.5, "Insufficient TDEE data for burn-down chart",
            transform=ax_bot.transAxes, ha="center", va="center",
            fontsize=14,
        )

    ax_bot.set_title("Calorie Budget Burn-down (Are You On Pace?)",
                     fontsize=14, fontweight="bold")

    plt.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)
