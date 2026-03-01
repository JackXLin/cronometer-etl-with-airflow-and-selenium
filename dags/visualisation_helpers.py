"""
Shared helper utilities for the visualisation module.

Contains data preparation, metric computation, and BMI category logic
used across multiple PDF pages.
"""

from datetime import timedelta

import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import numpy as np
import pandas as pd
from scipy import stats


def get_bmi_category(bmi: float) -> str:
    """
    Return BMI category string based on WHO classification.

    Args:
        bmi (float): Body mass index value.

    Returns:
        str: Category label.
    """
    if bmi < 18.5:
        return "Underweight"
    elif bmi < 25:
        return "Normal"
    elif bmi < 30:
        return "Overweight"
    return "Obese"


def prepare_metrics(processed: pd.DataFrame, height_cm: float,
                    target_weight_kg: float, target_calories: int,
                    calorie_tolerance_pct: float) -> pd.DataFrame:
    """
    Compute all derived columns needed by the visualisation pages.

    Adds columns in-place: BMI, macro percentages, calorie deficit,
    on-track flag, weekday/weekend flags, weight velocity.

    Args:
        processed (pd.DataFrame): Merged nutrition + weight data.
        height_cm (float): User height in centimetres.
        target_weight_kg (float): Goal body weight.
        target_calories (int): Daily calorie target.
        calorie_tolerance_pct (float): Fraction tolerance for on-track.

    Returns:
        pd.DataFrame: The same DataFrame with new columns added.
    """
    height_m = height_cm / 100.0
    processed["BMI"] = processed["Weight (kg)"] / (height_m ** 2)

    # Weight velocity via linear slope over rolling windows
    processed["Weight_velocity_7d"] = (
        processed["Weight (kg)"]
        .rolling(7)
        .apply(lambda x: np.polyfit(range(len(x)), x, 1)[0] * 7
               if len(x) >= 3 else np.nan)
    )

    # Macro percentages (avoid div-by-zero)
    energy = processed["Energy (kcal)"]
    safe_energy = energy.replace(0, np.nan)
    processed["Protein_pct"] = (processed["Protein (g)"] * 4) / safe_energy * 100
    processed["Carbs_pct"] = (processed["Carbs (g)"] * 4) / safe_energy * 100
    processed["Fat_pct"] = (processed["Fat (g)"] * 9) / safe_energy * 100

    # Calorie deficit/surplus (positive = under target = deficit)
    processed["Calorie_deficit"] = target_calories - energy

    # On-track flag
    low = target_calories * (1 - calorie_tolerance_pct)
    high = target_calories * (1 + calorie_tolerance_pct)
    processed["On_track_calories"] = energy.between(low, high)

    # Temporal features
    processed["Month"] = processed["Date"].dt.month
    processed["Weekday"] = processed["Date"].dt.dayofweek
    processed["Is_weekend"] = processed["Weekday"].isin([5, 6])

    return processed


def compute_nutrient_correlations(processed: pd.DataFrame,
                                  nutrients: list) -> list:
    """
    Compute Pearson correlations between each nutrient and daily weight change,
    including p-values and significance flags.

    Args:
        processed (pd.DataFrame): Data with nutrient columns and
            'Daily Weight change (kg)'.
        nutrients (list): Column names of nutrients to test.

    Returns:
        list[dict]: Sorted by absolute correlation descending. Each dict has
            keys: nutrient, correlation, p_value, significant.
    """
    results = []
    wt_change = processed["Daily Weight change (kg)"]
    for nutrient in nutrients:
        valid = ~(processed[nutrient].isna() | wt_change.isna())
        if valid.sum() > 2:
            corr, p = stats.pearsonr(processed[nutrient][valid], wt_change[valid])
            results.append({
                "nutrient": nutrient,
                "correlation": corr,
                "p_value": p,
                "significant": p < 0.05,
            })
    results.sort(key=lambda x: abs(x["correlation"]), reverse=True)
    return results


def compute_lagged_correlations(processed: pd.DataFrame,
                                nutrients: list,
                                max_lag: int = 3) -> pd.DataFrame:
    """
    Compute Pearson correlations between each nutrient and weight change
    at multiple lag offsets (0 to max_lag days).

    A lag of N means: "does nutrient intake on day T correlate with
    weight change on day T+N?"

    Args:
        processed (pd.DataFrame): Data with nutrient columns and
            'Daily Weight change (kg)'.
        nutrients (list): Column names of nutrients to test.
        max_lag (int): Maximum lag in days (inclusive).

    Returns:
        pd.DataFrame: Index = nutrient names, columns = 'lag_0' .. 'lag_N'.
            Each cell is a dict with keys: r, p, significant.
    """
    wt_change = processed["Daily Weight change (kg)"]
    results = {}

    for nutrient in nutrients:
        row = {}
        for lag in range(max_lag + 1):
            # Reason: shift nutrient forward by `lag` so that nutrient[T]
            # aligns with weight_change[T+lag].
            shifted_nutrient = processed[nutrient].shift(lag)
            valid = ~(shifted_nutrient.isna() | wt_change.isna())
            if valid.sum() > 10:
                r, p = stats.pearsonr(
                    shifted_nutrient[valid], wt_change[valid],
                )
                row[f"lag_{lag}"] = {
                    "r": r, "p": p, "significant": p < 0.05,
                }
            else:
                row[f"lag_{lag}"] = {
                    "r": np.nan, "p": np.nan, "significant": False,
                }
        results[nutrient] = row

    return pd.DataFrame(results).T


def compute_correlation_ci(processed: pd.DataFrame,
                           nutrients: list,
                           confidence: float = 0.95) -> list:
    """
    Compute Pearson correlations with confidence intervals using
    Fisher z-transformation.

    Args:
        processed (pd.DataFrame): Data with nutrient columns and
            'Daily Weight change (kg)'.
        nutrients (list): Column names of nutrients to test.
        confidence (float): Confidence level (default 0.95).

    Returns:
        list[dict]: Sorted by absolute correlation descending. Each dict
            has keys: nutrient, correlation, p_value, significant,
            ci_low, ci_high, n.
    """
    wt_change = processed["Daily Weight change (kg)"]
    z_crit = stats.norm.ppf((1 + confidence) / 2)
    results = []

    for nutrient in nutrients:
        valid = ~(processed[nutrient].isna() | wt_change.isna())
        n = valid.sum()
        if n > 10:
            r, p = stats.pearsonr(
                processed[nutrient][valid], wt_change[valid],
            )
            # Reason: Fisher z-transform converts r to approximately
            # normal distribution for CI computation.
            z = np.arctanh(r)
            se = 1.0 / np.sqrt(n - 3)
            z_low = z - z_crit * se
            z_high = z + z_crit * se
            ci_low = np.tanh(z_low)
            ci_high = np.tanh(z_high)
            results.append({
                "nutrient": nutrient,
                "correlation": r,
                "p_value": p,
                "significant": p < 0.05,
                "ci_low": ci_low,
                "ci_high": ci_high,
                "n": n,
            })

    results.sort(key=lambda x: abs(x["correlation"]), reverse=True)
    return results


def build_key_figures_table(processed: pd.DataFrame,
                            tdee_estimates: dict,
                            target_calories: int,
                            protein_goal_g: int,
                            fiber_goal_g: int) -> pd.DataFrame:
    """
    Build an actionable key-figures table comparing metrics across time windows.

    Replaces the old gain-day / loss-day nutrient comparison with numbers
    the user can actually act on.

    Args:
        processed (pd.DataFrame): Full processed data with TDEE columns.
        tdee_estimates (dict): Output of estimate_tdee().
        target_calories (int): Daily calorie target.
        protein_goal_g (int): Daily protein target in grams.
        fiber_goal_g (int): Daily fibre target in grams.

    Returns:
        pd.DataFrame: Table with rows=metrics, columns=time windows.
    """
    windows = {
        "Last 7 Days": processed.tail(7),
        "Last 30 Days": processed.tail(30),
        "All Time": processed,
    }

    rows = []
    for label, data in windows.items():
        valid = data.dropna(subset=["Energy (kcal)"])
        avg_intake = valid["Energy (kcal)"].mean() if len(valid) > 0 else np.nan

        # TDEE from adaptive column if available
        tdee_val = np.nan
        if "TDEE_adaptive" in data.columns:
            tdee_col = data["TDEE_adaptive"].dropna()
            if len(tdee_col) > 0:
                tdee_val = tdee_col.iloc[-1] if label != "All Time" else tdee_col.mean()

        surplus_deficit = avg_intake - tdee_val if not np.isnan(tdee_val) else np.nan

        # Smoothed weight trend (kg/week)
        if "Weight_smoothed" in data.columns and len(data) > 1:
            sm = data["Weight_smoothed"].dropna()
            if len(sm) >= 2:
                days_span = max((data["Date"].iloc[-1] - data["Date"].iloc[0]).days, 1)
                trend_per_week = (sm.iloc[-1] - sm.iloc[0]) / days_span * 7
            else:
                trend_per_week = np.nan
        else:
            trend_per_week = np.nan

        # Predicted weekly delta from intake vs TDEE
        predicted_weekly = surplus_deficit / 7000 * 7 if not np.isnan(surplus_deficit) else np.nan

        protein_avg = valid["Protein (g)"].mean() if len(valid) > 0 else np.nan
        fiber_avg = valid["Fiber (g)"].mean() if len(valid) > 0 else np.nan
        adherence = data["On_track_calories"].mean() * 100 if "On_track_calories" in data.columns else np.nan

        rows.append({
            "Time Window": label,
            "Avg Intake (kcal)": _fmt(avg_intake, 0),
            "Est. TDEE (kcal)": _fmt(tdee_val, 0),
            "Surplus/Deficit (kcal)": _fmt(surplus_deficit, 0, sign=True),
            "Weight Trend (kg/wk)": _fmt(trend_per_week, 2, sign=True),
            "Predicted Wt Delta (kg/wk)": _fmt(predicted_weekly, 2, sign=True),
            "Protein (g/day)": _fmt(protein_avg, 0),
            "Fiber (g/day)": _fmt(fiber_avg, 0),
            "Cal Adherence (%)": _fmt(adherence, 1),
        })

    return pd.DataFrame(rows).set_index("Time Window").T


def _fmt(val, decimals: int = 1, sign: bool = False) -> str:
    """
    Format a numeric value for display, returning '--' for NaN.

    Args:
        val: Numeric value or NaN.
        decimals (int): Decimal places.
        sign (bool): If True, prefix positive values with '+'.

    Returns:
        str: Formatted string.
    """
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "--"
    fmt = f"{{:+.{decimals}f}}" if sign else f"{{:.{decimals}f}}"
    return fmt.format(val)


# ─────────────────────────────────────────────────────────────────────────────
# Drawing helpers (sub-panel renderers used by page functions)
# ─────────────────────────────────────────────────────────────────────────────
def draw_weekly_waterfall(ax, processed):
    """
    Draw a weekly weight change waterfall chart with cumulative progress line.

    Each bar represents one week's net weight change (green = loss, red = gain).
    A secondary axis shows the cumulative weight change from the start.

    Args:
        ax: Matplotlib axis.
        processed (pd.DataFrame): Must contain Date and Weight (kg) columns.
    """
    wt = processed[["Date", "Weight (kg)"]].dropna(subset=["Weight (kg)"]).copy()
    wt["Week"] = wt["Date"].dt.to_period("W")

    weekly = wt.groupby("Week").agg(
        first_wt=("Weight (kg)", "first"),
        last_wt=("Weight (kg)", "last"),
    )
    weekly["change"] = weekly["last_wt"] - weekly["first_wt"]
    weekly["cumulative"] = weekly["change"].cumsum()

    # Limit to last 16 weeks to keep chart readable
    weekly = weekly.tail(16)

    if len(weekly) == 0:
        ax.text(0.5, 0.5, "Insufficient data", transform=ax.transAxes,
                ha="center", va="center", fontsize=12)
        ax.set_title("Weekly Weight Change", fontsize=12, fontweight="bold")
        return

    x = np.arange(len(weekly))
    colors = ["#2ecc71" if c <= 0 else "#e74c3c" for c in weekly["change"]]
    ax.bar(x, weekly["change"], color=colors, alpha=0.75, edgecolor="gray",
           linewidth=0.5)
    ax.axhline(y=0, color="black", linestyle="-", linewidth=0.8)

    # Cumulative line on secondary axis
    ax2 = ax.twinx()
    ax2.plot(x, weekly["cumulative"].values, "o-", color="#3498db",
             linewidth=2, markersize=4, label="Cumulative")
    ax2.set_ylabel("Cumulative (kg)", color="#3498db", fontsize=9)
    ax2.tick_params(axis="y", labelcolor="#3498db")

    # Labels
    week_labels = [str(w)[-5:] for w in weekly.index]
    ax.set_xticks(x)
    ax.set_xticklabels(week_labels, rotation=60, ha="right", fontsize=7)
    ax.set_ylabel("Weekly Change (kg)")
    ax.set_title("Weekly Weight Change Waterfall", fontsize=12,
                 fontweight="bold")
    ax.grid(True, alpha=0.3, axis="y")


def draw_adherence_calendar(ax, processed):
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
