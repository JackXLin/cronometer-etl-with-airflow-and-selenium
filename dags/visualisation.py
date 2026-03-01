import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from datetime import datetime
import numpy as np
import warnings
import os

from tdee_calculator import estimate_tdee
from visualisation_helpers import (
    get_bmi_category,
    prepare_metrics,
    compute_nutrient_correlations,
    compute_lagged_correlations,
    compute_correlation_ci,
    build_key_figures_table,
    draw_weekly_waterfall,
    draw_adherence_calendar,
)
from visualisation_pages import (
    page_weight_prediction,
    page_tdee_dashboard,
    page_energy_macros,
)
from visualisation_goals import page_goal_progress

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
        7. Goal Progress & Calorie Budget Burn-down

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
        page_tdee_dashboard(
            pdf, processed, tdee_estimates, target_calories, target_weight_kg,
        )
        page_energy_macros(
            pdf, processed, target_calories, calorie_tolerance_pct,
        )
        _page_nutrient_correlations(pdf, processed)
        _page_behavioural_patterns(pdf, processed, target_calories)
        _page_key_figures_summary(
            pdf, processed, tdee_estimates, target_weight_kg, target_calories,
            protein_goal_g, fiber_goal_g, height_cm,
        )
        page_goal_progress(
            pdf, processed, target_weight_kg, tdee_estimates,
        )

    return pdf_path


# ─────────────────────────────────────────────────────────────────────────────
# PAGE 4 — What Drives Your Weight Change?
# ─────────────────────────────────────────────────────────────────────────────
def _page_nutrient_correlations(pdf, processed):
    """
    Top:    Lagged correlation heatmap (nutrients × lag days 0-3).
    Bottom: Enhanced bar chart with 95% CI whiskers and significance.

    Args:
        pdf: PdfPages object.
        processed (pd.DataFrame): Full dataset.
    """
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 11))

    # --- Top: Lagged correlation heatmap ---
    lagged = compute_lagged_correlations(processed, NUTRIENTS, max_lag=3)
    lag_cols = [c for c in lagged.columns if c.startswith("lag_")]

    # Build numeric matrix and significance mask
    r_matrix = np.full((len(NUTRIENTS), len(lag_cols)), np.nan)
    sig_mask = np.full((len(NUTRIENTS), len(lag_cols)), False)
    for i, nutrient in enumerate(NUTRIENTS):
        if nutrient in lagged.index:
            for j, col in enumerate(lag_cols):
                cell = lagged.loc[nutrient, col]
                if isinstance(cell, dict):
                    r_matrix[i, j] = cell["r"]
                    sig_mask[i, j] = cell["significant"]

    # Reason: diverging colormap centred on 0 makes positive/negative
    # correlations immediately distinguishable.
    from matplotlib.colors import TwoSlopeNorm
    norm = TwoSlopeNorm(vmin=-0.4, vcenter=0, vmax=0.4)
    im = ax1.imshow(r_matrix, cmap="RdBu_r", norm=norm, aspect="auto")

    ax1.set_xticks(range(len(lag_cols)))
    ax1.set_xticklabels([f"Same day" if i == 0 else f"+{i} day{'s' if i > 1 else ''}"
                         for i in range(len(lag_cols))], fontsize=10)
    ax1.set_yticks(range(len(NUTRIENTS)))
    ax1.set_yticklabels(NUTRIENTS, fontsize=10)

    # Annotate each cell with r value and significance asterisk
    for i in range(len(NUTRIENTS)):
        for j in range(len(lag_cols)):
            val = r_matrix[i, j]
            if not np.isnan(val):
                star = "*" if sig_mask[i, j] else ""
                color = "white" if abs(val) > 0.25 else "black"
                ax1.text(j, i, f"{val:.3f}{star}", ha="center", va="center",
                         fontsize=9, fontweight="bold" if star else "normal",
                         color=color)

    cbar = plt.colorbar(im, ax=ax1, shrink=0.7, aspect=25)
    cbar.set_label("Pearson r", fontsize=10)
    ax1.set_title(
        "What Drives Your Weight Change? (Lagged Correlations, * = p < 0.05)",
        fontsize=13, fontweight="bold",
    )
    ax1.set_xlabel("Lag (nutrient intake day → weight change day)")

    # --- Bottom: Enhanced bar chart with 95% CI ---
    corrs_ci = compute_correlation_ci(processed, NUTRIENTS)

    if corrs_ci:
        y_pos = range(len(corrs_ci))
        r_vals = [c["correlation"] for c in corrs_ci]
        ci_low = [c["ci_low"] for c in corrs_ci]
        ci_high = [c["ci_high"] for c in corrs_ci]
        # Reason: xerr expects distances from the bar value, not absolute positions.
        xerr_neg = [r - lo for r, lo in zip(r_vals, ci_low)]
        xerr_pos = [hi - r for r, hi in zip(r_vals, ci_high)]

        bar_colors = []
        bar_alphas = []
        for c in corrs_ci:
            base = NUTRIENT_COLORS.get(c["nutrient"], "gray")
            bar_colors.append(base)
            bar_alphas.append(0.85 if c["significant"] else 0.35)

        bars = ax2.barh(
            y_pos, r_vals, color=bar_colors, edgecolor="black", linewidth=1.2,
        )
        # Apply per-bar alpha
        for bar, alpha in zip(bars, bar_alphas):
            bar.set_alpha(alpha)

        ax2.errorbar(
            r_vals, y_pos, xerr=[xerr_neg, xerr_pos],
            fmt="none", ecolor="black", elinewidth=1.5, capsize=4,
        )

        ax2.set_yticks(y_pos)
        labels = []
        for c in corrs_ci:
            sig_marker = " **" if c["significant"] else " (ns)"
            labels.append(f"{c['nutrient']}{sig_marker}")
        ax2.set_yticklabels(labels, fontsize=10)

        ax2.axvline(x=0, color="black", linestyle="-", alpha=0.5)
        ax2.set_xlabel("Correlation with Daily Weight Change")
        ax2.set_xlim(-0.5, 0.5)
        ax2.grid(True, alpha=0.3, axis="x")

        # Annotate r value and sample size
        for i, c in enumerate(corrs_ci):
            xp = c["correlation"] + (0.03 if c["correlation"] >= 0 else -0.03)
            ha = "left" if c["correlation"] >= 0 else "right"
            ax2.text(xp, i, f'r={c["correlation"]:.3f} (n={c["n"]})',
                     va="center", ha=ha, fontsize=9)

    ax2.set_title(
        "Nutrient-Weight Correlations with 95% CI (faded = not significant)",
        fontsize=12, fontweight="bold",
    )

    plt.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)


# ─────────────────────────────────────────────────────────────────────────────
# PAGE 5 — Behavioural Patterns & Adherence Calendar
# ─────────────────────────────────────────────────────────────────────────────
def _page_behavioural_patterns(pdf, processed, target_calories):
    """
    Top-left:  Weekly weight change waterfall chart.
    Top-right: Weight change distribution histogram.
    Bottom:    Calorie adherence calendar heatmap (last 6 months).

    Args:
        pdf: PdfPages object.
        processed (pd.DataFrame): Full dataset with Is_weekend, On_track_calories.
        target_calories (int): Daily calorie target.
    """
    fig = plt.figure(figsize=(16, 12))
    ax_wf = fig.add_subplot(2, 2, 1)
    ax_hist = fig.add_subplot(2, 2, 2)
    ax_cal = fig.add_subplot(2, 1, 2)

    # --- Weekly Weight Change Waterfall ---
    draw_weekly_waterfall(ax_wf, processed)

    # --- Weight change distribution ---
    wc = processed["Daily Weight change (kg)"].dropna()
    ax_hist.hist(wc, bins=30, alpha=0.7, color="purple")
    ax_hist.axvline(x=0, color="red", linestyle="--", alpha=0.7)
    ax_hist.set_title("Daily Weight Change Distribution", fontsize=12,
                      fontweight="bold")
    ax_hist.set_xlabel("Weight Change (kg)")
    ax_hist.set_ylabel("Frequency")

    # --- Calendar heatmap ---
    draw_adherence_calendar(ax_cal, processed)

    plt.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)


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
