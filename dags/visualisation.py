import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.colors import LinearSegmentedColormap
from datetime import datetime, timedelta
import numpy as np
import warnings
import os

from tdee_calculator import estimate_tdee
from visualisation_helpers import (
    get_bmi_category,
    prepare_metrics,
    compute_nutrient_correlations,
    build_key_figures_table,
)
from visualisation_pages import (
    page_weight_prediction,
    page_tdee_dashboard,
    page_energy_macros,
)

warnings.filterwarnings("ignore")

# Consistent colour palette for nutrients
NUTRIENT_COLORS = {
    "Energy (kcal)": "#e74c3c",
    "Protein (g)": "#3498db",
    "Carbs (g)": "#f39c12",
    "Fat (g)": "#9b59b6",
    "Fiber (g)": "#2ecc71",
    "Sodium (mg)": "#1abc9c",
    "Water (g)": "#34495e",
}

NUTRIENTS = list(NUTRIENT_COLORS.keys())


def visualise_data(file_path: str) -> str:
    """
    Create a streamlined 6-page PDF report focused on body-weight analysis,
    TDEE estimation, and actionable nutrition insights.

    Pages:
        1. Weight Trend & Calorie-Aware Prediction
        2. TDEE Dashboard
        3. Energy & Macros
        4. Nutrient-Weight Correlations
        5. Behavioural Patterns & Adherence Calendar
        6. Key Figures Table & Summary

    Args:
        file_path (str): Path to the processed CSV file.

    Returns:
        str: Path to the generated PDF report.
    """
    # --- Load environment parameters ---
    height_cm = float(os.getenv("USER_HEIGHT_CM", 175))
    target_weight_kg = float(os.getenv("TARGET_WEIGHT_KG", 70))
    target_calories = int(os.getenv("TARGET_CALORIES", 2000))
    protein_goal_g = int(os.getenv("PROTEIN_GOAL_G", 100))
    fiber_goal_g = int(os.getenv("FIBER_GOAL_G", 25))
    calorie_tolerance_pct = float(os.getenv("CALORIE_TOLERANCE_PCT", 0.1))

    print(f"DEBUG: TARGET_WEIGHT_KG={target_weight_kg}  "
          f"USER_HEIGHT_CM={height_cm}  TARGET_CALORIES={target_calories}")

    # --- Load & prepare data ---
    processed = pd.read_csv(file_path)
    processed["Date"] = pd.to_datetime(processed["Date"])
    processed = processed.sort_values("Date").reset_index(drop=True)

    processed = prepare_metrics(
        processed, height_cm, target_weight_kg,
        target_calories, calorie_tolerance_pct,
    )

    # TDEE estimation (adds TDEE columns in-place)
    tdee_estimates = estimate_tdee(processed)

    the_time = datetime.now().strftime("%Y-%m-%d_%H-%M")
    pdf_path = f"/opt/airflow/csvs/analytics_report_{the_time}.pdf"

    with PdfPages(pdf_path) as pdf:
        page_weight_prediction(
            pdf, processed, target_weight_kg, tdee_estimates, height_cm,
        )
        page_tdee_dashboard(pdf, processed, tdee_estimates, target_calories)
        page_energy_macros(
            pdf, processed, target_calories, calorie_tolerance_pct,
        )
        _page_nutrient_correlations(pdf, processed)
        _page_behavioural_patterns(pdf, processed, target_calories)
        _page_key_figures_summary(
            pdf, processed, tdee_estimates, target_weight_kg, target_calories,
            protein_goal_g, fiber_goal_g, height_cm,
        )

    return pdf_path


# ─────────────────────────────────────────────────────────────────────────────
# PAGE 4 — Nutrient-Weight Correlations
# ─────────────────────────────────────────────────────────────────────────────
def _page_nutrient_correlations(pdf, processed):
    """
    Top:    Rolling 14-day correlations between each nutrient and weight change.
    Bottom: Static Pearson correlation bar chart with significance borders.

    Args:
        pdf: PdfPages object.
        processed (pd.DataFrame): Full dataset.
    """
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))

    # Rolling correlations
    window = 14
    for nutrient in NUTRIENTS:
        rc = processed[nutrient].rolling(window).corr(
            processed["Daily Weight change (kg)"]
        )
        ax1.plot(processed["Date"], rc,
                 label=nutrient.replace(" (", "\n("),
                 color=NUTRIENT_COLORS.get(nutrient, "gray"),
                 linewidth=1.5, alpha=0.8)

    ax1.axhline(y=0, color="black", linestyle="-", alpha=0.3)
    ax1.axhline(y=0.3, color="green", linestyle="--", alpha=0.3,
                label="Strong +")
    ax1.axhline(y=-0.3, color="red", linestyle="--", alpha=0.3,
                label="Strong -")
    ax1.set_title("Rolling 14-Day Correlation: Nutrients vs Weight Change",
                  fontsize=12, fontweight="bold")
    ax1.set_ylabel("Correlation Coefficient")
    ax1.set_ylim(-1, 1)
    ax1.legend(bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=8)
    ax1.grid(True, alpha=0.3)
    plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45)

    # Static bar chart
    corrs = compute_nutrient_correlations(processed, NUTRIENTS)

    y_pos = range(len(corrs))
    bar_c = [NUTRIENT_COLORS.get(c["nutrient"], "gray") for c in corrs]
    edge_c = ["black" if c["significant"] else "none" for c in corrs]

    ax2.barh(y_pos, [c["correlation"] for c in corrs],
             color=bar_c, alpha=0.7, edgecolor=edge_c, linewidth=2)
    ax2.set_yticks(y_pos)
    ax2.set_yticklabels([c["nutrient"] for c in corrs])
    ax2.axvline(x=0, color="black", linestyle="-", alpha=0.5)
    ax2.set_xlabel("Correlation with Daily Weight Change")
    ax2.set_title(
        "Nutrient-Weight Correlations (black border = p < 0.05)",
        fontsize=12, fontweight="bold",
    )
    ax2.set_xlim(-0.5, 0.5)
    ax2.grid(True, alpha=0.3, axis="x")

    for i, c in enumerate(corrs):
        xp = c["correlation"] + (0.02 if c["correlation"] >= 0 else -0.02)
        ha = "left" if c["correlation"] >= 0 else "right"
        ax2.text(xp, i, f'{c["correlation"]:.3f}', va="center", ha=ha,
                 fontsize=9)

    plt.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)


# ─────────────────────────────────────────────────────────────────────────────
# PAGE 5 — Behavioural Patterns & Adherence Calendar
# ─────────────────────────────────────────────────────────────────────────────
def _page_behavioural_patterns(pdf, processed, target_calories):
    """
    Top-left:  Weekday vs Weekend intake comparison.
    Top-right: Weight change distribution histogram.
    Bottom:    Calorie adherence calendar heatmap (last 6 months).

    Args:
        pdf: PdfPages object.
        processed (pd.DataFrame): Full dataset with Is_weekend, On_track_calories.
        target_calories (int): Daily calorie target.
    """
    fig = plt.figure(figsize=(16, 12))
    ax_wk = fig.add_subplot(2, 2, 1)
    ax_hist = fig.add_subplot(2, 2, 2)
    ax_cal = fig.add_subplot(2, 1, 2)

    # --- Weekday vs Weekend ---
    weekday = processed[~processed["Is_weekend"]]
    weekend = processed[processed["Is_weekend"]]
    cats = ["Energy (kcal)", "Protein (g)", "Carbs (g)", "Fat (g)"]
    wd_means = [weekday[c].mean() for c in cats]
    we_means = [weekend[c].mean() for c in cats]
    x = np.arange(len(cats))
    w = 0.35
    ax_wk.bar(x - w / 2, wd_means, w, label="Weekdays", alpha=0.7)
    ax_wk.bar(x + w / 2, we_means, w, label="Weekends", alpha=0.7)
    ax_wk.set_title("Weekday vs Weekend Intake", fontsize=12, fontweight="bold")
    ax_wk.set_xticks(x)
    ax_wk.set_xticklabels(cats, rotation=45, ha="right")
    ax_wk.legend()

    # --- Weight change distribution ---
    wc = processed["Daily Weight change (kg)"].dropna()
    ax_hist.hist(wc, bins=30, alpha=0.7, color="purple")
    ax_hist.axvline(x=0, color="red", linestyle="--", alpha=0.7)
    ax_hist.set_title("Daily Weight Change Distribution", fontsize=12,
                      fontweight="bold")
    ax_hist.set_xlabel("Weight Change (kg)")
    ax_hist.set_ylabel("Frequency")

    # --- Calendar heatmap ---
    _draw_adherence_calendar(ax_cal, processed)

    plt.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)


def _draw_adherence_calendar(ax, processed):
    """
    Draw a GitHub-style calorie adherence calendar heatmap on the given axis.

    Args:
        ax: Matplotlib axis.
        processed (pd.DataFrame): Must contain Date, On_track_calories,
            Calorie_deficit columns.
    """
    cal = processed[["Date", "On_track_calories", "Calorie_deficit"]].copy()
    cal["Weekday"] = cal["Date"].dt.weekday

    def status(row):
        """Map adherence to 0/0.5/1 for colouring."""
        if row["On_track_calories"]:
            return 1.0
        return 0.5 if row["Calorie_deficit"] > 0 else 0.0

    cal["Status"] = cal.apply(status, axis=1)

    six_m = cal["Date"].max() - timedelta(days=180)
    recent = cal[cal["Date"] >= six_m].copy()

    if len(recent) == 0:
        ax.text(0.5, 0.5, "Insufficient data", transform=ax.transAxes,
                ha="center", va="center", fontsize=14)
        ax.set_title("Calorie Adherence Calendar", fontsize=14,
                     fontweight="bold")
        return

    recent["YearWeek"] = recent["Date"].dt.strftime("%Y-W%V")
    weeks = sorted(recent["YearWeek"].unique())
    matrix = np.full((7, len(weeks)), np.nan)

    for _, row in recent.iterrows():
        wi = weeks.index(row["YearWeek"])
        matrix[row["Weekday"], wi] = row["Status"]

    cmap = LinearSegmentedColormap.from_list(
        "adh", ["#e74c3c", "#f39c12", "#2ecc71"], N=256,
    )
    im = ax.imshow(matrix, cmap=cmap, aspect="auto", vmin=0, vmax=1)
    ax.set_yticks(range(7))
    ax.set_yticklabels(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])

    # Month tick labels
    positions, labels = [], []
    cur_month = None
    for i, wk in enumerate(weeks):
        dates = recent[recent["YearWeek"] == wk]["Date"]
        if len(dates) > 0:
            m = dates.iloc[0].strftime("%b %Y")
            if m != cur_month:
                positions.append(i)
                labels.append(m)
                cur_month = m
    ax.set_xticks(positions)
    ax.set_xticklabels(labels, rotation=45, ha="right")

    cbar = plt.colorbar(im, ax=ax, shrink=0.5, aspect=20)
    cbar.set_ticks([0, 0.5, 1])
    cbar.set_ticklabels(["Over Target", "Under Target", "On Track"])

    total = len(recent)
    on = (recent["Status"] == 1.0).sum()
    under = (recent["Status"] == 0.5).sum()
    over = (recent["Status"] == 0.0).sum()
    summary = (
        f"Last 6 Months:\n"
        f"On Track: {on} days ({on / total * 100:.1f}%)\n"
        f"Under:    {under} days ({under / total * 100:.1f}%)\n"
        f"Over:     {over} days ({over / total * 100:.1f}%)"
    )
    ax.text(1.15, 0.5, summary, transform=ax.transAxes, fontsize=10,
            verticalalignment="center", fontfamily="monospace",
            bbox=dict(boxstyle="round,pad=0.5", fc="white", alpha=0.9))
    ax.set_title("Calorie Adherence Calendar (Last 6 Months)", fontsize=14,
                 fontweight="bold")


# ─────────────────────────────────────────────────────────────────────────────
# PAGE 6 — Key Figures Table & Summary
# ─────────────────────────────────────────────────────────────────────────────
def _page_key_figures_summary(pdf, processed, tdee_estimates,
                              target_weight_kg, target_calories,
                              protein_goal_g, fiber_goal_g, height_cm):
    """
    Top:    Text summary of current status, insights, recommendations.
    Bottom: Actionable key-figures table (replaces old gain/loss table).

    Args:
        pdf: PdfPages object.
        processed (pd.DataFrame): Full dataset.
        tdee_estimates (dict): TDEE results.
        target_weight_kg (float): Goal weight.
        target_calories (int): Daily calorie target.
        protein_goal_g (int): Daily protein target.
        fiber_goal_g (int): Daily fibre target.
        height_cm (float): User height.
    """
    fig, ax = plt.subplots(figsize=(14, 10))
    ax.axis("off")

    # --- Compute summary stats ---
    recent = processed.tail(30)
    current_weight = processed["Weight (kg)"].iloc[-1]
    current_bmi = processed["BMI"].iloc[-1]
    bmi_cat = get_bmi_category(current_bmi) if not pd.isna(current_bmi) else "Unknown"

    # Smoothed weight trend (kg/week)
    if "Weight_smoothed" in recent.columns and len(recent) > 1:
        sm = recent["Weight_smoothed"].dropna()
        if len(sm) >= 2:
            span_days = max((recent["Date"].iloc[-1] - recent["Date"].iloc[0]).days, 1)
            trend_wk = (sm.iloc[-1] - sm.iloc[0]) / span_days * 7
        else:
            trend_wk = 0
    else:
        trend_wk = 0

    if trend_wk < -0.05:
        trend_word = "losing"
    elif trend_wk > 0.05:
        trend_word = "gaining"
    else:
        trend_word = "maintaining"

    est_tdee = tdee_estimates.get("weighted_average")
    avg_intake = recent["Energy (kcal)"].mean()
    avg_deficit = recent["Calorie_deficit"].mean()
    adherence = recent["On_track_calories"].mean() * 100

    # Correlations for strongest predictor
    corrs = compute_nutrient_correlations(processed, NUTRIENTS)
    strongest = corrs[0]["nutrient"] if corrs else "N/A"
    strongest_r = corrs[0]["correlation"] if corrs else 0

    # Weekend / weekday
    wd = processed[~processed["Is_weekend"]]["Energy (kcal)"].mean()
    we = processed[processed["Is_weekend"]]["Energy (kcal)"].mean()
    wk_diff = we - wd

    # Days to goal
    if abs(trend_wk) > 0.01:
        days_to_goal = abs(current_weight - target_weight_kg) / abs(trend_wk) * 7
        # Reason: sign check — are we actually moving toward the goal?
        moving_toward = ((current_weight > target_weight_kg and trend_wk < 0) or
                         (current_weight < target_weight_kg and trend_wk > 0))
        dtg_str = f"~{days_to_goal:.0f} days" if moving_toward else "Moving away from goal"
    else:
        dtg_str = "N/A (weight stable)"

    tdee_line = f"  Est. TDEE:         {est_tdee:.0f} cal/day\n" if est_tdee else ""

    summary = (
        "BODY WEIGHT ANALYSIS SUMMARY\n"
        + "=" * 44 + "\n\n"
        "CURRENT STATUS\n"
        f"  Weight:  {current_weight:.1f} kg  |  Target: {target_weight_kg} kg\n"
        f"  BMI:     {current_bmi:.1f} ({bmi_cat})\n"
        f"  Trend:   {trend_word} ({trend_wk:+.2f} kg/wk smoothed)\n"
        f"  ETA:     {dtg_str}\n\n"
        "KEY INSIGHTS (Last 30 Days)\n"
        f"  Avg Intake:        {avg_intake:.0f} cal/day\n"
        + tdee_line
        + f"  Avg Deficit:       {avg_deficit:+.0f} cal/day\n"
        f"  Adherence:         {adherence:.1f}%\n"
        f"  Strongest Factor:  {strongest} (r={strongest_r:.3f})\n"
        f"  Wknd-Wkday Diff:  {wk_diff:+.0f} cal\n\n"
        "RECOMMENDATIONS\n"
    )

    # Build recommendations
    recs = []
    if est_tdee:
        if avg_intake > est_tdee + 200:
            recs.append("  Reduce intake toward TDEE for weight loss")
        elif avg_intake < est_tdee - 200:
            recs.append("  Increase intake — currently well below TDEE")
        else:
            recs.append("  Intake is near TDEE — maintain for stability")
    if abs(wk_diff) > 300:
        recs.append("  Improve weekend consistency (large gap)")
    else:
        recs.append("  Good weekday/weekend consistency")
    recs.append(f"  Prioritise {strongest.lower()} management")

    summary += "\n".join(recs)

    ax.text(0.03, 0.98, summary, transform=ax.transAxes, fontsize=10,
            verticalalignment="top", fontfamily="monospace",
            bbox=dict(boxstyle="round,pad=0.5", fc="lightblue", alpha=0.8))

    # --- Key figures table ---
    table_df = build_key_figures_table(
        processed, tdee_estimates, target_calories, protein_goal_g, fiber_goal_g,
    )
    tbl = ax.table(
        cellText=table_df.values,
        rowLabels=table_df.index,
        colLabels=table_df.columns,
        cellLoc="center",
        loc="bottom",
        colColours=["#e1f5fe"] * len(table_df.columns),
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(9)
    tbl.scale(1.0, 1.6)

    plt.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)
