"""
Publication-quality EDA figures — PHL 2024 climate features vs disease severity.

Outputs (outputs/figures/eda_sciplot/):
  boxplots_<group>.pdf      — M1-M3 vs M4-M6 distributions, box + strip overlay
  scatter_<group>.pdf       — each feature vs visual_symptom_frequency, OLS + R²
  correlation_ranked.pdf    — ranked Pearson r bar chart, both windows
  correlation_heatmap.pdf   — pairwise heatmap, top-N features + target

Run with the ml conda environment:
  C:/Users/AndresAguilar/AppData/Local/miniconda3/envs/ml/python.exe notebooks/eda_sciplot.py
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import seaborn as sns
from scipy import stats
from pathlib import Path

# ── Typography ─────────────────────────────────────────────────────────────────
_avail = {f.name for f in fm.fontManager.ttflist}
_sans = next((f for f in ["Arial", "Helvetica", "DejaVu Sans"] if f in _avail),
             "sans-serif")
plt.rcParams.update({
    "font.family":     "sans-serif",
    "font.sans-serif": [_sans],
    "font.size":        8,
    "axes.titlesize":   9,
    "axes.labelsize":  10,
    "xtick.labelsize":  8,
    "ytick.labelsize":  8,
    "legend.fontsize":  8,
    "figure.dpi":      300,
})

# ── Colorblind-safe palette (Okabe-Ito) ────────────────────────────────────────
WINDOW_COLORS = {
    "m1_m3": "#E69F00",   # orange   — M1-M3
    "m4_m6": "#56B4E9",   # sky-blue — M4-M6
}
WINDOW_LABELS = {"m1_m3": "M1-M3", "m4_m6": "M4-M6"}

# ── Paths ──────────────────────────────────────────────────────────────────────
CSV_PATH = "outputs/climate_indices/extracted_climate_data_phl_2024.csv"
OUT_DIR  = Path("outputs/figures/eda_sciplot")
OUT_DIR.mkdir(parents=True, exist_ok=True)
TARGET   = "visual_symptom_frequency"

# ── Load ───────────────────────────────────────────────────────────────────────
df = pd.read_csv(CSV_PATH)

# ── Feature groups (base names, without window prefix) ────────────────────────
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
        "heat_wave_duration", "cold_wave_duration", "growing_degree_days",
        "canopy_wetness_duration", "cool_night_frequency",
        "max_hr_days", "max_hr06_days", "max_hr09_days",
        "max_hr12_days", "max_hr15_days", "max_hr18_days",
    ],
}

# ── Axis label map (LaTeX scientific notation) ─────────────────────────────────
AXIS_LABELS = {
    "tmax_avg":               r"$T_{\max}$ (°C)",
    "tmin_avg":               r"$T_{\min}$ (°C)",
    "tmean_avg":              r"$T_{\mathrm{mean}}$ (°C)",
    "rh06_avg":               r"RH$_{06:00}$ (%)",
    "rh09_avg":               r"RH$_{09:00}$ (%)",
    "rh12_avg":               r"RH$_{12:00}$ (%)",
    "rh15_avg":               r"RH$_{15:00}$ (%)",
    "rh18_avg":               r"RH$_{18:00}$ (%)",
    "vpd_accum":              r"$\Sigma$VPD (kPa)",
    "vpd_lt_20":              r"VPD $<$ 2.0 kPa (%$\,$d)",
    "precipitation_accum":    r"$\Sigma$Precip. (mm)",
    "n_wet_spells":           r"$N$ wet spells",
    "n_dry_spells":           r"$N$ dry spells",
    "avg_wet_spell_duration": r"Wet spell dur. (d)",
    "consecutive_dry_days":   r"Max CDD (d)",
    "daily_intensity_index":  r"Rain intensity (mm $\mathrm{d^{-1}}$)",
    "etr_accum":              r"$\Sigma$ETr (mm)",
    "srad_accum":             r"$\Sigma$Srad (MJ $\mathrm{m^{-2}}$)",
    "heat_wave_duration":     r"Heat wave (d)",
    "cold_wave_duration":     r"Cold wave (d)",
    "growing_degree_days":    r"GDD (°C $\mathrm{d}$)",
    "canopy_wetness_duration":r"CWD (h $\mathrm{d^{-1}}$)",
    "cool_night_frequency":   r"Cool nights per 10 d",
    "max_hr_days":            r"Days RH$_{\mathrm{daily}}$ $\geq$ 80 %",
    "max_hr06_days":          r"Days RH$_{06}$ $\geq$ 85 %",
    "max_hr09_days":          r"Days RH$_{09}$ $\geq$ 85 %",
    "max_hr12_days":          r"Days RH$_{12}$ $\geq$ 70 %",
    "max_hr15_days":          r"Days RH$_{15}$ $\geq$ 70 %",
    "max_hr18_days":          r"Days RH$_{18}$ $\geq$ 85 %",
}

# Features where BOTH windows are constant — undefined correlation, skip scatter
ZERO_VAR = {
    base for base in AXIS_LABELS
    if all(
        df.get(f"{win}_{base}", pd.Series([np.nan])).std() == 0
        for win in WINDOW_COLORS
    )
}

# ── Layout helpers ─────────────────────────────────────────────────────────────

def _grid(n, max_cols=4):
    ncols = min(n, max_cols)
    nrows = int(np.ceil(n / ncols))
    return nrows, ncols


def _panel_letter(i):
    return chr(ord("A") + i)


def _shared_legend(fig):
    handles = [
        plt.Rectangle((0, 0), 1, 1, facecolor=WINDOW_COLORS[w],
                       alpha=0.8, linewidth=0)
        for w in WINDOW_COLORS
    ]
    fig.legend(handles, [WINDOW_LABELS[w] for w in WINDOW_COLORS],
               loc="lower center", ncol=2, frameon=False,
               bbox_to_anchor=(0.5, -0.02), fontsize=9)


# ══════════════════════════════════════════════════════════════════════════════
# Figure set 1 — BOXPLOTS (m1_m3 vs m4_m6 distributions)
# ══════════════════════════════════════════════════════════════════════════════

def plot_boxplots(group_name, base_names):
    valid = [b for b in base_names
             if any(f"{w}_{b}" in df.columns for w in WINDOW_COLORS)]
    if not valid:
        return

    nrows, ncols = _grid(len(valid))
    fig, axes = plt.subplots(nrows, ncols,
                             figsize=(7.20, nrows * 2.5),
                             constrained_layout=True)
    axes = np.array(axes).flatten()

    order   = [WINDOW_LABELS[w] for w in WINDOW_COLORS]
    palette = {WINDOW_LABELS[w]: c for w, c in WINDOW_COLORS.items()}

    for i, base in enumerate(valid):
        ax = axes[i]

        # Build long-form slice for this feature
        slices = []
        for win in WINDOW_COLORS:
            col = f"{win}_{base}"
            if col not in df.columns:
                continue
            tmp = df[[col]].rename(columns={col: "value"})
            tmp["window"] = WINDOW_LABELS[win]
            slices.append(tmp)
        long = pd.concat(slices, ignore_index=True)

        # Box + strip overlay (N=56 per window — show all points)
        sns.boxplot(data=long, x="window", y="value", hue="window",
                    order=order, palette=palette, width=0.42, ax=ax,
                    flierprops={"marker": "none"}, linewidth=0.8,
                    legend=False)
        sns.stripplot(data=long, x="window", y="value", hue="window",
                      order=order, palette=palette, size=2.6, alpha=0.55,
                      jitter=0.10, ax=ax, zorder=3, legend=False)

        ax.set_xlabel("")
        ax.set_ylabel(AXIS_LABELS.get(base, base), fontsize=9)
        ax.text(-0.15, 1.02, _panel_letter(i), transform=ax.transAxes,
                fontsize=12, fontweight="bold", va="bottom")
        ax.yaxis.grid(True, linewidth=0.4, color="0.85", zorder=0)
        ax.set_axisbelow(True)
        sns.despine(ax=ax)

    for ax in axes[len(valid):]:
        ax.set_visible(False)

    _shared_legend(fig)

    out = OUT_DIR / f"boxplots_{group_name}.pdf"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved {out}")


# ══════════════════════════════════════════════════════════════════════════════
# Figure set 2 — SCATTER vs visual_symptom_frequency
# ══════════════════════════════════════════════════════════════════════════════

def plot_scatter(group_name, base_names):
    valid = [b for b in base_names
             if b not in ZERO_VAR
             and any(f"{w}_{b}" in df.columns for w in WINDOW_COLORS)]
    if not valid:
        print(f"  [{group_name}] no features with variance — skipping scatter")
        return

    nrows, ncols = _grid(len(valid))
    fig, axes = plt.subplots(nrows, ncols,
                             figsize=(7.20, nrows * 2.7),
                             constrained_layout=True)
    axes = np.array(axes).flatten()
    y = df[TARGET].values

    for i, base in enumerate(valid):
        ax = axes[i]

        for win, color in WINDOW_COLORS.items():
            col = f"{win}_{base}"
            if col not in df.columns:
                continue
            x = df[col].values
            mask = np.isfinite(x) & np.isfinite(y)

            ax.scatter(x[mask], y[mask], color=color, alpha=0.60,
                       s=18, edgecolors="none", zorder=3,
                       label=WINDOW_LABELS[win])

            if mask.sum() > 2 and x[mask].std() > 0:
                sl, ic, r, p, _ = stats.linregress(x[mask], y[mask])
                xr = np.linspace(x[mask].min(), x[mask].max(), 200)
                ax.plot(xr, sl * xr + ic, color=color,
                        linewidth=1.3, zorder=4)

                r2_str = (
                    f"$R^2={r**2:.2f},\\;p={p:.3f}$"
                    if p >= 0.001 else
                    f"$R^2={r**2:.2f},\\;p<0.001$"
                )
                y_anchor = 0.97 - list(WINDOW_COLORS).index(win) * 0.15
                ax.text(0.04, y_anchor, r2_str,
                        transform=ax.transAxes, fontsize=7,
                        color=color, va="top")

        ax.set_xlabel(AXIS_LABELS.get(base, base), fontsize=9)
        ax.set_ylabel(
            r"Symptom freq. (%)" if i % ncols == 0 else "",
            fontsize=9,
        )
        ax.text(-0.15, 1.02, _panel_letter(i), transform=ax.transAxes,
                fontsize=12, fontweight="bold", va="bottom")
        ax.yaxis.grid(True, linewidth=0.4, color="0.85", zorder=0)
        ax.set_axisbelow(True)
        sns.despine(ax=ax)

    for ax in axes[len(valid):]:
        ax.set_visible(False)

    handles = [
        plt.Line2D([0], [0], marker="o", color="w",
                   markerfacecolor=WINDOW_COLORS[w], markersize=6,
                   label=WINDOW_LABELS[w])
        for w in WINDOW_COLORS
    ]
    fig.legend(handles=handles, loc="lower center", ncol=2,
               frameon=False, bbox_to_anchor=(0.5, -0.02), fontsize=9)

    out = OUT_DIR / f"scatter_{group_name}.pdf"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved {out}")


# ══════════════════════════════════════════════════════════════════════════════
# Figure 3 — RANKED CORRELATION BAR CHART (Pearson r vs target, both windows)
# ══════════════════════════════════════════════════════════════════════════════

def plot_correlation_ranked():
    all_bases = [b for grp in GROUPS.values() for b in grp]
    records = []
    for base in all_bases:
        for win in WINDOW_COLORS:
            col = f"{win}_{base}"
            if col not in df.columns:
                continue
            x = df[col].values
            y = df[TARGET].values
            mask = np.isfinite(x) & np.isfinite(y)
            if mask.sum() > 2 and x[mask].std() > 0:
                r, p = stats.pearsonr(x[mask], y[mask])
            else:
                r, p = 0.0, 1.0
            records.append({"base": base, "window": WINDOW_LABELS[win],
                             "r": r, "p": p, "color": WINDOW_COLORS[win]})

    corr = pd.DataFrame(records)

    # Sort by mean |r| across windows descending
    mean_abs = (corr.groupby("base")["r"]
                .apply(lambda x: x.abs().mean())
                .sort_values(ascending=True))
    ordered_bases = mean_abs.index.tolist()

    fig_h = max(4.0, len(ordered_bases) * 0.38)
    fig, ax = plt.subplots(figsize=(7.20, fig_h), constrained_layout=True)

    y_positions = np.arange(len(ordered_bases))
    bar_h = 0.35

    for offset, win in zip([-bar_h / 2, bar_h / 2], WINDOW_COLORS):
        win_label = WINDOW_LABELS[win]
        sub = corr[corr["window"] == win_label].set_index("base")
        r_vals = [sub.loc[b, "r"] if b in sub.index else 0.0
                  for b in ordered_bases]
        p_vals = [sub.loc[b, "p"] if b in sub.index else 1.0
                  for b in ordered_bases]

        bars = ax.barh(y_positions + offset, r_vals, height=bar_h,
                       color=WINDOW_COLORS[win], alpha=0.80,
                       label=win_label, edgecolor="none")

        # Significance stars at bar tip
        for yp, r_v, p_v in zip(y_positions + offset, r_vals, p_vals):
            if p_v < 0.001:
                star = "***"
            elif p_v < 0.01:
                star = "**"
            elif p_v < 0.05:
                star = "*"
            else:
                star = ""
            if star:
                x_tip = r_v + (0.01 if r_v >= 0 else -0.01)
                ha = "left" if r_v >= 0 else "right"
                ax.text(x_tip, yp, star, va="center", ha=ha,
                        fontsize=6.5, color=WINDOW_COLORS[win])

    ax.set_yticks(y_positions)
    ax.set_yticklabels(
        [AXIS_LABELS.get(b, b) for b in ordered_bases], fontsize=7.5
    )
    ax.axvline(0, color="0.3", linewidth=0.8, zorder=0)
    ax.set_xlabel(r"Pearson $r$ with visual symptom frequency (%)", fontsize=10)
    ax.yaxis.grid(False)
    ax.xaxis.grid(True, linewidth=0.4, color="0.85", zorder=0)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, loc="lower right", fontsize=8)
    sns.despine(ax=ax)

    out = OUT_DIR / "correlation_ranked.pdf"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved {out}")


# ══════════════════════════════════════════════════════════════════════════════
# Figure 4 — PAIRWISE CORRELATION HEATMAP (top-N features + target)
# ══════════════════════════════════════════════════════════════════════════════

def plot_correlation_heatmap(top_n=20):
    feat_cols = [c for c in df.columns
                 if c.startswith(("m1_m3_", "m4_m6_"))]

    # Select top_n features by |r| with target; sort ascending so the most
    # correlated features appear at the bottom (adjacent to the target row)
    abs_r = (df[feat_cols]
             .corrwith(df[TARGET])
             .abs()
             .sort_values(ascending=False))
    top_cols = abs_r.head(top_n).sort_values(ascending=True).index.tolist()

    # Rename columns to readable labels: "m1_m3_tmax_avg" → "M1 Tmax"
    def _short(col):
        win, base = col.split("_", 1)[0] + "_" + col.split("_", 1)[1].split("_")[0], \
                    "_".join(col.split("_")[2:])
        prefix = "M1" if col.startswith("m1") else "M4"
        return f"{prefix} {base.replace('_', ' ')}"

    rename = {c: _short(c) for c in top_cols}
    sub = df[top_cols + [TARGET]].rename(columns={**rename, TARGET: "Symptom freq."})
    corr_matrix = sub.corr()

    # Lower-triangle mask
    mask = np.triu(np.ones_like(corr_matrix, dtype=bool), k=1)

    fig_side = max(7.20, top_n * 0.42)
    fig, ax = plt.subplots(figsize=(fig_side, fig_side * 0.85),
                           constrained_layout=True)

    sns.heatmap(
        corr_matrix, mask=mask, ax=ax,
        cmap="RdBu_r", center=0, vmin=-1, vmax=1,
        annot=True, fmt=".2f", annot_kws={"size": 6},
        linewidths=0.25, square=True,
        cbar_kws={"shrink": 0.6, "label": "Pearson r"},
    )
    ax.set_title(
        f"Pairwise correlations — top {top_n} features + target",
        fontsize=10, pad=8
    )
    ax.tick_params(axis="x", labelsize=7, rotation=45)
    ax.tick_params(axis="y", labelsize=7, rotation=0)

    out = OUT_DIR / "correlation_heatmap.pdf"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved {out}")


# ── Run ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Boxplots")
    for grp, bases in GROUPS.items():
        plot_boxplots(grp, bases)

    print("\nScatter vs visual_symptom_frequency")
    for grp, bases in GROUPS.items():
        plot_scatter(grp, bases)

    print("\nCorrelation plots")
    plot_correlation_ranked()
    plot_correlation_heatmap(top_n=20)

    print(f"\nAll figures saved to {OUT_DIR.resolve()}")
