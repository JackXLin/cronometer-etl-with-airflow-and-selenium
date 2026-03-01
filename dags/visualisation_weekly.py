"""
PDF page renderer for Weekly Summary & Rate of Change page.

Contains the weekly summary table and Weight_velocity_7d time-series chart
that were missing from earlier report versions.
"""

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd

from visualisation_helpers_v2 import build_weekly_summary_table


# ─────────────────────────────────────────────────────────────────────────────
# PAGE 7 — Weekly Summary & Rate of Change
# ─────────────────────────────────────────────────────────────────────────────
def page_weekly_and_velocity(pdf, processed):
    """
    Top:    Weight velocity (rate of change) time-series with zero line.
    Bottom: Week-by-week summary table (last 8 weeks).

    The velocity chart uses the pre-computed Weight_velocity_7d column
    (7-day rolling linear slope × 7, in kg/week units).

    Args:
        pdf: PdfPages object.
        processed (pd.DataFrame): Full dataset with Weight_velocity_7d column.
    """
    fig, (ax_top, ax_bot) = plt.subplots(2, 1, figsize=(14, 11))

    # --- Top: Rate of Weight Change ---
    if "Weight_velocity_7d" in processed.columns:
        vel = processed["Weight_velocity_7d"]
        dates = processed["Date"]

        ax_top.plot(dates, vel, color="black", linewidth=1.5, alpha=0.8)
        ax_top.axhline(y=0, color="black", linestyle="-", linewidth=0.8)

        # Reason: colour bands make it immediately obvious whether
        # the user is currently losing or gaining weight.
        ax_top.fill_between(
            dates, vel, 0,
            where=(vel <= 0), color="green", alpha=0.3,
            label="Losing weight", interpolate=True,
        )
        ax_top.fill_between(
            dates, vel, 0,
            where=(vel > 0), color="red", alpha=0.3,
            label="Gaining weight", interpolate=True,
        )

        # Safe rate guidelines
        ax_top.axhline(y=-0.5, color="green", linestyle=":", alpha=0.5,
                       label="Safe loss rate (0.5 kg/wk)")
        ax_top.axhline(y=-1.0, color="orange", linestyle=":", alpha=0.5,
                       label="Aggressive loss rate (1.0 kg/wk)")

        ax_top.set_title(
            "Rate of Weight Change Over Time (7-Day Rolling Slope)",
            fontsize=14, fontweight="bold",
        )
        ax_top.set_ylabel("Weight Change (kg/week)")
        ax_top.legend(fontsize=8, loc="upper right")
        ax_top.grid(True, alpha=0.3)
        ax_top.xaxis.set_major_locator(mdates.MonthLocator())
        ax_top.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
        plt.setp(ax_top.xaxis.get_majorticklabels(), rotation=45)

        # Annotate current rate
        latest_vel = vel.dropna()
        if len(latest_vel) > 0:
            cur_rate = latest_vel.iloc[-1]
            rate_color = "green" if cur_rate <= 0 else "red"
            ax_top.text(
                0.02, 0.95,
                f"Current: {cur_rate:+.2f} kg/wk",
                transform=ax_top.transAxes, fontsize=12,
                fontweight="bold", color=rate_color,
                bbox=dict(boxstyle="round,pad=0.3", fc="white", alpha=0.85),
            )
    else:
        ax_top.text(
            0.5, 0.5, "Weight_velocity_7d column not available",
            transform=ax_top.transAxes, ha="center", va="center",
            fontsize=14,
        )
        ax_top.set_title("Rate of Weight Change", fontsize=14,
                         fontweight="bold")

    # --- Bottom: Weekly Summary Table ---
    ax_bot.axis("off")
    weekly_df = build_weekly_summary_table(processed, n_weeks=8)

    if len(weekly_df) > 0:
        tbl = ax_bot.table(
            cellText=weekly_df.values,
            colLabels=weekly_df.columns,
            cellLoc="center",
            loc="center",
            colColours=["#e1f5fe"] * len(weekly_df.columns),
        )
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(9)
        tbl.scale(1.0, 1.8)

        # Conditional coloring on Wt Delta column
        delta_col_idx = list(weekly_df.columns).index("Wt Delta")
        for row_idx in range(len(weekly_df)):
            cell = tbl[(row_idx + 1, delta_col_idx)]
            cell_text = cell.get_text().get_text()
            if cell_text.startswith("-"):
                cell.set_facecolor("#c8e6c9")
            elif cell_text.startswith("+"):
                cell.set_facecolor("#ffcdd2")

    ax_bot.set_title("Weekly Summary (Last 8 Weeks)", fontsize=14,
                     fontweight="bold", pad=20)

    plt.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)
