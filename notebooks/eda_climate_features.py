"""
Exploratory data analysis — PHL 2024 climate features vs visual symptom frequency.

Produces three figure sets saved to outputs/figures/eda/:
  1. boxplots_<group>.png  — variable distributions by seasonal window (m1_m3 vs m4_m6)
  2. scatter_<group>.png   — each feature vs visual_symptom_frequency
  3. correlation_heatmap.png — Pearson r between all features and target
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import seaborn as sns
from pathlib import Path

# ── paths ──────────────────────────────────────────────────────────────────────
CSV_PATH   = "outputs/climate_indices/extracted_climate_data_phl_2024.csv"
FIG_DIR    = Path("outputs/figures/eda")
FIG_DIR.mkdir(parents=True, exist_ok=True)

TARGET = "visual_symptom_frequency"

# ── load ───────────────────────────────────────────────────────────────────────
df = pd.read_csv(CSV_PATH)
print(f"Loaded {df.shape[0]} rows × {df.shape[1]} columns")

# ── feature groups (base name without window prefix) ──────────────────────────
GROUPS = {
    "temperature": ["tmax_avg", "tmin_avg", "tmean_avg"],
    "humidity":    ["rh06_avg", "rh09_avg", "rh12_avg", "rh15_avg", "rh18_avg"],
    "vpd":         ["vpd_accum", "vpd_lt_20"],
    "precipitation": [
        "precipitation_accum", "n_wet_spells", "n_dry_spells",
        "avg_wet_spell_duration", "consecutive_dry_days", "daily_intensity_index",
    ],
    "radiation":   ["etr_accum", "srad_accum"],
    "indices": [
        "heat_wave_duration", "cold_wave_duration",
        "max_hr_days", "max_hr06_days", "max_hr09_days",
        "max_hr12_days", "max_hr15_days", "max_hr18_days",
        "growing_degree_days", "canopy_wetness_duration", "cool_night_frequency",
    ],
}

WINDOWS  = ["m1_m3", "m4_m6"]
PALETTE  = {"m1_m3": "#4C72B0", "m4_m6": "#DD8452"}

# ── helpers ────────────────────────────────────────────────────────────────────

def feature_col(window, base):
    return f"{window}_{base}"


def long_form(df, base_names):
    """Melt a list of base feature names into long-form for both windows."""
    records = []
    for base in base_names:
        for win in WINDOWS:
            col = feature_col(win, base)
            if col in df.columns:
                sub = df[[TARGET, col]].copy()
                sub.columns = [TARGET, "value"]
                sub["variable"] = base
                sub["window"]   = win
                records.append(sub)
    return pd.concat(records, ignore_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# 1. BOXPLOTS — distribution by seasonal window
# ══════════════════════════════════════════════════════════════════════════════

def plot_boxplots(group_name, base_names):
    valid = [b for b in base_names if any(feature_col(w, b) in df.columns for w in WINDOWS)]
    if not valid:
        return

    n_vars = len(valid)
    ncols  = min(n_vars, 4)
    nrows  = int(np.ceil(n_vars / ncols))

    fig, axes = plt.subplots(nrows, ncols, figsize=(ncols * 3.8, nrows * 3.5))
    axes = np.array(axes).flatten()
    fig.suptitle(f"Distribution by seasonal window — {group_name}", fontsize=13, y=1.01)

    for ax, base in zip(axes, valid):
        data = []
        labels = []
        colors = []
        for win in WINDOWS:
            col = feature_col(win, base)
            if col in df.columns:
                data.append(df[col].dropna().values)
                labels.append(win)
                colors.append(PALETTE[win])

        bp = ax.boxplot(data, patch_artist=True, widths=0.5,
                        medianprops=dict(color="black", linewidth=1.5))
        for patch, color in zip(bp["boxes"], colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.75)

        ax.set_xticks([1, 2])
        ax.set_xticklabels(labels, fontsize=9)
        ax.set_title(base, fontsize=9)
        ax.tick_params(axis="y", labelsize=8)

    for ax in axes[n_vars:]:
        ax.set_visible(False)

    # legend
    handles = [plt.Rectangle((0, 0), 1, 1, facecolor=PALETTE[w], alpha=0.75) for w in WINDOWS]
    fig.legend(handles, WINDOWS, loc="lower center", ncol=2,
               bbox_to_anchor=(0.5, -0.03), fontsize=9)

    fig.tight_layout()
    out = FIG_DIR / f"boxplots_{group_name}.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved {out}")


# ══════════════════════════════════════════════════════════════════════════════
# 2. SCATTER PLOTS — each feature vs visual_symptom_frequency
# ══════════════════════════════════════════════════════════════════════════════

def plot_scatter(group_name, base_names):
    valid = [b for b in base_names if any(feature_col(w, b) in df.columns for w in WINDOWS)]
    if not valid:
        return

    n_vars = len(valid)
    ncols  = min(n_vars, 4)
    nrows  = int(np.ceil(n_vars / ncols))

    fig, axes = plt.subplots(nrows, ncols, figsize=(ncols * 3.8, nrows * 3.5))
    axes = np.array(axes).flatten()
    fig.suptitle(f"Feature vs visual symptom frequency — {group_name}", fontsize=13, y=1.01)

    for ax, base in zip(axes, valid):
        for win in WINDOWS:
            col = feature_col(win, base)
            if col not in df.columns:
                continue
            x = df[col]
            y = df[TARGET]
            ax.scatter(x, y, color=PALETTE[win], alpha=0.65, s=28, label=win, edgecolors="none")

            # regression line
            mask = x.notna() & y.notna()
            if mask.sum() > 2 and x[mask].std() > 0:
                m, b = np.polyfit(x[mask], y[mask], 1)
                xr = np.linspace(x[mask].min(), x[mask].max(), 100)
                ax.plot(xr, m * xr + b, color=PALETTE[win], linewidth=1.2, alpha=0.8)

                r = np.corrcoef(x[mask], y[mask])[0, 1]
                ax.annotate(f"r={r:.2f}", xy=(0.05, 0.93 - WINDOWS.index(win) * 0.12),
                            xycoords="axes fraction", fontsize=7.5,
                            color=PALETTE[win])

        ax.set_xlabel(base, fontsize=8)
        ax.set_ylabel(TARGET if axes.tolist().index(ax) % ncols == 0 else "", fontsize=8)
        ax.tick_params(labelsize=7.5)
        ax.set_title(base, fontsize=9)

    for ax in axes[n_vars:]:
        ax.set_visible(False)

    handles = [plt.Line2D([0], [0], marker="o", color="w",
                          markerfacecolor=PALETTE[w], markersize=7) for w in WINDOWS]
    fig.legend(handles, WINDOWS, loc="lower center", ncol=2,
               bbox_to_anchor=(0.5, -0.03), fontsize=9)

    fig.tight_layout()
    out = FIG_DIR / f"scatter_{group_name}.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved {out}")


# ══════════════════════════════════════════════════════════════════════════════
# 3. CORRELATION HEATMAP — Pearson r with target
# ══════════════════════════════════════════════════════════════════════════════

def plot_correlation_heatmap():
    feature_cols = [c for c in df.columns
                    if c.startswith(("m1_m3_", "m4_m6_"))]
    corr = df[feature_cols + [TARGET]].corr()[TARGET].drop(TARGET).sort_values()

    fig, ax = plt.subplots(figsize=(5, max(6, len(corr) * 0.28)))
    colors = ["#D62728" if v < 0 else "#1F77B4" for v in corr.values]
    ax.barh(corr.index, corr.values, color=colors, alpha=0.75, edgecolor="none")
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Pearson r  with  visual_symptom_frequency", fontsize=10)
    ax.set_title("Feature correlations with disease frequency (PHL 2024)", fontsize=11)
    ax.tick_params(axis="y", labelsize=7.5)

    # annotate values
    for y_pos, (val, label) in enumerate(zip(corr.values, corr.index)):
        ax.text(val + (0.005 if val >= 0 else -0.005), y_pos,
                f"{val:.2f}", va="center",
                ha="left" if val >= 0 else "right", fontsize=7)

    fig.tight_layout()
    out = FIG_DIR / "correlation_heatmap.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved {out}")


# ══════════════════════════════════════════════════════════════════════════════
# 4. PAIRWISE HEATMAP — full correlation matrix (top correlated features)
# ══════════════════════════════════════════════════════════════════════════════

def plot_pairwise_heatmap(top_n=20):
    feature_cols = [c for c in df.columns
                    if c.startswith(("m1_m3_", "m4_m6_"))]
    corr_target = df[feature_cols].corrwith(df[TARGET]).abs().sort_values(ascending=False)
    top_features = corr_target.head(top_n).index.tolist()

    corr_matrix = df[top_features + [TARGET]].corr()

    fig, ax = plt.subplots(figsize=(12, 10))
    mask = np.zeros_like(corr_matrix, dtype=bool)
    mask[np.triu_indices_from(mask, k=1)] = True

    sns.heatmap(
        corr_matrix, mask=mask, ax=ax,
        cmap="RdBu_r", center=0, vmin=-1, vmax=1,
        annot=True, fmt=".2f", annot_kws={"size": 6.5},
        linewidths=0.3, square=True,
    )
    ax.set_title(f"Pairwise correlations — top {top_n} features + target", fontsize=11)
    ax.tick_params(axis="x", labelsize=7, rotation=45)
    ax.tick_params(axis="y", labelsize=7, rotation=0)

    fig.tight_layout()
    out = FIG_DIR / "pairwise_heatmap.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved {out}")


# ══════════════════════════════════════════════════════════════════════════════
# RUN ALL
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n--- Boxplots ---")
    for grp, bases in GROUPS.items():
        plot_boxplots(grp, bases)

    print("\n--- Scatter plots ---")
    for grp, bases in GROUPS.items():
        plot_scatter(grp, bases)

    print("\n--- Correlation heatmap ---")
    plot_correlation_heatmap()

    print("\n--- Pairwise heatmap (top 20) ---")
    plot_pairwise_heatmap(top_n=20)

    print(f"\nAll figures saved to {FIG_DIR.resolve()}")
