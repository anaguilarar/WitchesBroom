import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import seaborn as sns
from scipy import stats
from pathlib import Path

def main():
    # ── Paths & Setup ─────────────────────────────────────────────────────────
    csv_path = "outputs/climate_indices/extracted_climate_data_phl_2024.csv"
    if not os.path.exists(csv_path):
        print(f"Error: CSV file not found at {csv_path}")
        return

    # Ensure output directories exist
    fig_dir = Path("outputs/figures")
    plot_dir = Path("outputs/plots")
    fig_dir.mkdir(parents=True, exist_ok=True)
    plot_dir.mkdir(parents=True, exist_ok=True)

    # Load data
    df = pd.read_csv(csv_path)
    target = "visual_symptom_frequency"

    # Define severity groups for scatter plots
    def get_severity(val):
        if val == 0:
            return "Asymptomatic (0%)"
        elif val == 100:
            return "Fully Symptomatic (100%)"
        else:
            return "Intermediate (1-99%)"
            
    df["Symptom Severity"] = df[target].apply(get_severity)
    severity_order = ["Asymptomatic (0%)", "Intermediate (1-99%)", "Fully Symptomatic (100%)"]
    
    # ── Color Palette ──────────────────────────────────────────────────────────
    # Okabe-Ito colors
    window_colors = {
        "m1_m3": "#E69F00",   # orange   — M1-M3 (Months 1-3)
        "m4_m6": "#56B4E9",   # sky-blue — M4-M6 (Months 4-6)
    }
    window_labels = {"m1_m3": "M1-M3 (Jan-Mar)", "m4_m6": "M4-M6 (Apr-Jun)"}

    severity_colors = {
        "Asymptomatic (0%)": "#009E73",         # Okabe-Ito green
        "Intermediate (1-99%)": "#E69F00",      # Okabe-Ito orange
        "Fully Symptomatic (100%)": "#D55E00"   # Okabe-Ito vermilion
    }

    # ── Typography & RC Parameters ─────────────────────────────────────────────
    _avail = {f.name for f in fm.fontManager.ttflist}
    _sans = next((f for f in ["Arial", "Helvetica", "DejaVu Sans"] if f in _avail), "sans-serif")
    
    plt.rcParams.update({
        "font.family":      "sans-serif",
        "font.sans-serif":  [_sans],
        "font.size":        8,
        "axes.labelsize":   9,
        "axes.titlesize":   9,
        "xtick.labelsize":  7.5,
        "ytick.labelsize":  7.5,
        "legend.fontsize":  8,
        "figure.dpi":       300,
    })

    # ── Features definition ────────────────────────────────────────────────────
    bases = [
        "tmax_avg", "tmin_avg", "tmean_avg", "rh06_avg", "rh09_avg", "rh12_avg",
        "rh15_avg", "rh18_avg", "vpd_accum", "precipitation_accum", "etr_accum",
        "srad_accum", "vpd_lt_20", "n_wet_spells", "n_dry_spells", "heat_wave_duration",
        "cold_wave_duration", "avg_wet_spell_duration", "max_hr_days", "max_hr06_days",
        "max_hr09_days", "max_hr12_days", "max_hr15_days", "max_hr18_days",
        "consecutive_dry_days", "growing_degree_days", "daily_intensity_index",
        "canopy_wetness_duration", "cool_night_frequency"
    ]
    
    axis_labels = {
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
        "max_hr18_days":          r"Days RH$_{18}$ $\geq$ 70 %",
    }

    # ── 1. Ranked Correlation Plot ─────────────────────────────────────────────
    print("Generating ranked correlation plots...")
    records = []
    for b in bases:
        for win in ["m1_m3", "m4_m6"]:
            col = f"{win}_{b}"
            if col not in df.columns:
                continue
            x = df[col].values
            y = df[target].values
            mask = np.isfinite(x) & np.isfinite(y)
            if mask.sum() > 2 and x[mask].std() > 0:
                r, p = stats.pearsonr(x[mask], y[mask])
            else:
                r, p = 0.0, 1.0
            records.append({
                "base": b,
                "window": win,
                "r": r,
                "p": p,
                "abs_r": abs(r)
            })

    corr_df = pd.DataFrame(records)

    # Sort bases by mean absolute correlation across both windows descending
    mean_abs_r = corr_df.groupby("base")["abs_r"].mean().sort_values(ascending=True)
    ordered_bases = mean_abs_r.index.tolist()

    fig_h = max(6.0, len(ordered_bases) * 0.35)
    fig, ax = plt.subplots(figsize=(6.5, fig_h), constrained_layout=True)

    y_positions = np.arange(len(ordered_bases))
    bar_h = 0.35

    for offset, win in zip([-bar_h / 2, bar_h / 2], ["m1_m3", "m4_m6"]):
        sub = corr_df[corr_df["window"] == win].set_index("base")
        r_vals = [sub.loc[b, "r"] if b in sub.index else 0.0 for b in ordered_bases]
        p_vals = [sub.loc[b, "p"] if b in sub.index else 1.0 for b in ordered_bases]

        bars = ax.barh(
            y_positions + offset, r_vals, height=bar_h,
            color=window_colors[win], alpha=0.85,
            label=window_labels[win], edgecolor="none"
        )

        # Significance labels
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
                x_tip = r_v + (0.015 if r_v >= 0 else -0.015)
                ha = "left" if r_v >= 0 else "right"
                ax.text(
                    x_tip, yp, star, va="center", ha=ha,
                    fontsize=7, color="black", fontweight="bold"
                )

    ax.set_yticks(y_positions)
    ax.set_yticklabels([axis_labels.get(b, b) for b in ordered_bases], fontsize=8)
    ax.axvline(0, color="0.3", linewidth=0.8, zorder=1)
    ax.set_xlabel(r"Pearson correlation coefficient ($r$) with disease frequency", fontsize=9)
    ax.set_xlim(-1.05, 1.05)
    ax.yaxis.grid(False)
    ax.xaxis.grid(True, linewidth=0.4, color="0.85", zorder=0)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, loc="lower right", fontsize=8)
    sns.despine(ax=ax)

    # Save Ranked Correlation
    fig.savefig(fig_dir / "correlation_ranked.pdf", dpi=300, bbox_inches="tight")
    fig.savefig(plot_dir / "correlation_ranked.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print("  Saved ranked correlation plots.")

    # ── 2. Correlation Heatmap (Top 20 variables) ──────────────────────────────
    print("Generating pairwise correlation heatmap...")
    feat_cols = [f"{win}_{b}" for b in bases for win in ["m1_m3", "m4_m6"] if f"{win}_{b}" in df.columns]
    
    # Compute absolute Pearson correlations with target to identify top 20
    target_corrs = df[feat_cols].corrwith(df[target]).abs().sort_values(ascending=False)
    top_cols = target_corrs.head(20).index.tolist()

    # Create readable short labels for top columns
    def get_short_label(col):
        parts = col.split("_")
        win = "M1-3" if col.startswith("m1_m3") else "M4-6"
        base_name = "_".join(parts[2:])
        clean_base = base_name.replace("_avg", "").replace("_accum", "").upper()
        return f"{win} {clean_base}"

    rename_dict = {c: get_short_label(c) for c in top_cols}
    sub_df = df[top_cols + [target]].rename(columns={**rename_dict, target: "Disease Freq."})
    corr_matrix = sub_df.corr()

    # Mask upper triangle
    mask = np.triu(np.ones_like(corr_matrix, dtype=bool), k=1)

    fig, ax = plt.subplots(figsize=(7.5, 6.5), constrained_layout=True)
    sns.heatmap(
        corr_matrix, mask=mask, ax=ax,
        cmap="RdBu_r", center=0, vmin=-1, vmax=1,
        annot=True, fmt=".2f", annot_kws={"size": 6.5},
        linewidths=0.25, square=True,
        cbar_kws={"shrink": 0.7, "label": "Pearson correlation coefficient ($r$)"}
    )
    
    ax.tick_params(axis="x", labelsize=7, rotation=45)
    ax.tick_params(axis="y", labelsize=7, rotation=0)
    sns.despine(ax=ax, top=True, right=True, left=True, bottom=True)
    
    # Save Heatmap
    fig.savefig(fig_dir / "correlation_heatmap.pdf", dpi=300, bbox_inches="tight")
    fig.savefig(plot_dir / "correlation_heatmap.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print("  Saved correlation heatmap.")

    # ── 3. Individual Scatters (Top 6 variables) ──────────────────────────────
    print("Generating scatter plots for top 6 correlated variables...")
    # Get top 6 variables
    top_6_cols = target_corrs.head(6).index.tolist()

    fig, axes = plt.subplots(2, 3, figsize=(7.2, 5.0), constrained_layout=True)
    axes_flat = axes.flatten()

    for idx, col_name in enumerate(top_6_cols):
        ax = axes_flat[idx]
        
        # Plot scatter
        sns.scatterplot(
            data=df, x=col_name, y=target, hue="Symptom Severity",
            hue_order=severity_order, palette=severity_colors,
            ax=ax, s=20, alpha=0.85, edgecolor="none", zorder=3
        )
        
        # Fit OLS
        x_val = df[col_name].values
        y_val = df[target].values
        mask = np.isfinite(x_val) & np.isfinite(y_val)
        slope, intercept, r_val, p_val, _ = stats.linregress(x_val[mask], y_val[mask])
        
        x_fit = np.linspace(x_val[mask].min(), x_val[mask].max(), 100)
        ax.plot(x_fit, slope * x_fit + intercept, color="black", lw=1.0, ls="--", zorder=2)
        
        # R2 & p-value label
        r2 = r_val ** 2
        r2_label = f"$R^2={r2:.2f}$\n$p={p_val:.3f}$" if p_val >= 0.001 else f"$R^2={r2:.2f}$\n$p<0.001$"
        ax.text(0.05, 0.95, r2_label, transform=ax.transAxes, fontsize=8, va="top")
        
        # Clean labels using axis_labels dict
        base_name = "_".join(col_name.split("_")[2:])
        win_label = "M1-M3" if col_name.startswith("m1_m3") else "M4-M6"
        clean_label = axis_labels.get(base_name, base_name)
        ax.set_xlabel(f"{win_label} {clean_label}", fontsize=8.5)
        ax.set_ylabel("Disease Freq. (%)" if idx % 3 == 0 else "", fontsize=8.5)
        
        # Subtle horizontal/vertical grid
        ax.yaxis.grid(True, linewidth=0.4, color="0.85", zorder=0)
        ax.xaxis.grid(True, linewidth=0.4, color="0.85", zorder=0)
        ax.set_axisbelow(True)
        sns.despine(ax=ax)
        
        # Show legend only on first panel, keep it frame-free
        if idx == 0:
            ax.legend(frameon=False, loc="upper right", bbox_to_anchor=(1.02, 1.0))
        else:
            legend = ax.get_legend()
            if legend is not None:
                legend.remove()
                
        # Subpanel labels A, B, C, D, E, F
        letter = chr(65 + idx)
        ax.text(-0.15, 1.02, letter, transform=ax.transAxes,
                fontsize=11, fontweight="bold", va="bottom")

    # Save Scatters
    fig.savefig(fig_dir / "correlation_top_scatters.pdf", dpi=300, bbox_inches="tight")
    fig.savefig(plot_dir / "correlation_top_scatters.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print("  Saved top 6 scatter plots.")

if __name__ == "__main__":
    main()
