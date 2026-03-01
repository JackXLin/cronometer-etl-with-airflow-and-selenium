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
# PAGE 8 — Goal Progress & Calorie Budget Burn-down
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
    fig = plt.figure(figsize=(14, 14))
    ax_prog = fig.add_subplot(3, 1, 1)
    ax_cum = fig.add_subplot(3, 1, 2)
    ax_bot = fig.add_subplot(3, 1, 3)

    current_weight = processed["Weight (kg)"].dropna().iloc[-1]
    start_weight = processed["Weight (kg)"].dropna().iloc[0]

    # --- Top: Weight Milestone Progress ---
    ax_prog.axis("off")

    # Reason: support both weight loss and weight gain goals by
    # computing progress based on direction of the goal.
    wants_loss = start_weight > target_weight_kg
    if wants_loss:
        total_change_needed = start_weight - target_weight_kg
        change_so_far = start_weight - current_weight
    else:
        total_change_needed = target_weight_kg - start_weight
        change_so_far = current_weight - start_weight

    pct_complete = (
        np.clip(change_so_far / total_change_needed, 0, 1)
        if abs(total_change_needed) > 0.1 else 0
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
    ax_prog.add_patch(plt.Rectangle(
        (0.05, bar_y), 0.9, bar_h, transform=ax_prog.transAxes,
        facecolor="#ecf0f1", edgecolor="gray", linewidth=2,
    ))
    ax_prog.add_patch(plt.Rectangle(
        (0.05, bar_y), 0.9 * pct_complete, bar_h,
        transform=ax_prog.transAxes,
        facecolor=status_color, edgecolor="gray", linewidth=2,
    ))

    ax_prog.text(0.05, bar_y + bar_h + 0.03,
                 f"Start: {start_weight:.1f} kg",
                 transform=ax_prog.transAxes, fontsize=11, ha="left")
    ax_prog.text(0.95, bar_y + bar_h + 0.03,
                 f"Target: {target_weight_kg:.1f} kg",
                 transform=ax_prog.transAxes, fontsize=11, ha="right")
    ax_prog.text(
        0.5, bar_y + bar_h / 2,
        f"{pct_complete * 100:.1f}% complete"
        f" \u2014 {kg_remaining:+.1f} kg remaining",
        transform=ax_prog.transAxes, fontsize=12, ha="center",
        va="center", fontweight="bold",
    )

    ax_prog.text(0.5, bar_y - 0.08, f"Status: {status_label}",
                 transform=ax_prog.transAxes, fontsize=13, ha="center",
                 fontweight="bold", color=status_color,
                 bbox=dict(boxstyle="round,pad=0.4", fc="white",
                           edgecolor=status_color, linewidth=2))
    ax_prog.text(0.5, bar_y - 0.18, eta_str,
                 transform=ax_prog.transAxes, fontsize=11, ha="center",
                 color="gray")
    ax_prog.text(0.5, bar_y - 0.26,
                 f"Current trend: {trend_wk:+.2f} kg/week",
                 transform=ax_prog.transAxes, fontsize=10, ha="center",
                 color="gray")

    ax_prog.set_title("Weight Goal Progress", fontsize=14, fontweight="bold",
                      pad=20)

    # --- Middle: Cumulative Weight Change Timeline ---
    wt_data = processed[["Date", "Weight (kg)"]].dropna(subset=["Weight (kg)"])
    cumulative_change = wt_data["Weight (kg)"] - start_weight
    ax_cum.plot(wt_data["Date"], cumulative_change, color="blue", linewidth=2,
                label="Cumulative Weight Change")
    target_change = target_weight_kg - start_weight
    ax_cum.axhline(y=target_change, color="purple", linestyle=":",
                   linewidth=2,
                   label=f"Target ({target_change:+.1f} kg)")
    ax_cum.axhline(y=0, color="black", linestyle="-", linewidth=0.5,
                   alpha=0.5)

    # Shade progress vs remaining
    ax_cum.fill_between(
        wt_data["Date"], cumulative_change, 0,
        where=(cumulative_change * np.sign(target_change) >= 0),
        color="green", alpha=0.15, label="Progress toward goal",
        interpolate=True,
    )
    ax_cum.fill_between(
        wt_data["Date"], cumulative_change, 0,
        where=(cumulative_change * np.sign(target_change) < 0),
        color="red", alpha=0.15, label="Away from goal",
        interpolate=True,
    )

    ax_cum.set_title("Cumulative Weight Change from Start", fontsize=12,
                     fontweight="bold")
    ax_cum.set_ylabel("Weight Change (kg)")
    ax_cum.legend(fontsize=8)
    ax_cum.grid(True, alpha=0.3)
    plt.setp(ax_cum.xaxis.get_majorticklabels(), rotation=45)

    # --- Bottom: Forward-Looking Calorie Deficit Burn-down ---
    # Reason: redesigned to project forward from today to the ETA,
    # rather than retroactively from day 1 which always shows "behind."
    remaining_deficit = abs(kg_remaining) * KCAL_PER_KG

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

        ax_bot.plot(dates, cumulative_actual, color="blue", linewidth=2,
                    label="Actual Cumulative Deficit")

        # Forward projection line from current position to target
        last_date = dates.iloc[-1]
        current_cum = cumulative_actual.iloc[-1]
        if abs(trend_wk) > 0.01 and moving_toward:
            days_remaining = abs(kg_remaining) / abs(trend_wk) * 7
            future_date = last_date + td(days=int(days_remaining))
            target_cum = current_cum + remaining_deficit
            ax_bot.plot(
                [last_date, future_date],
                [current_cum, target_cum],
                "--", color="green", linewidth=2,
                label=f"Required pace to target ({future_date.strftime('%b %Y')})",
            )

        ax_bot.axhline(
            y=current_cum + remaining_deficit, color="purple",
            linestyle=":", linewidth=2,
            label=f"Remaining Deficit: {remaining_deficit:,.0f} kcal",
        )

        ax_bot.set_ylabel("Cumulative Calorie Deficit (kcal)")
        ax_bot.legend(fontsize=8)
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
