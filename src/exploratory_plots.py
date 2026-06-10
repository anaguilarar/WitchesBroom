import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import seaborn as sns
from scipy import stats

def main():
    # 1. Load data
    data_path = "outputs/climate_indices/extracted_climate_data_phl_2024.csv"
    if not os.path.exists(data_path):
        print(f"Error: File {data_path} not found.")
        return
    
    df = pd.read_csv(data_path)
    
    # Define target and severity groups
    target_col = "visual_symptom_frequency"
    
    def get_severity(val):
        if val == 0:
            return "Asymptomatic (0%)"
        elif val == 100:
            return "Fully Symptomatic (100%)"
        else:
            return "Intermediate (1-99%)"
            
    df["Symptom Severity"] = df[target_col].apply(get_severity)
    
    # 2. Define global colors for cross-figure consistency
    SEVERITY_COLORS = {
        "Asymptomatic (0%)": "#009E73",         # Okabe-Ito green
        "Intermediate (1-99%)": "#E69F00",      # Okabe-Ito orange
        "Fully Symptomatic (100%)": "#D55E00"   # Okabe-Ito vermilion
    }
    
    # Ensure severity ordering
    severity_order = ["Asymptomatic (0%)", "Intermediate (1-99%)", "Fully Symptomatic (100%)"]
    
    # 3. Configure typography (Arial/Helvetica standards)
    _available = {f.name for f in fm.fontManager.ttflist}
    _sans = next((f for f in ["Arial", "Helvetica", "DejaVu Sans"] if f in _available), "sans-serif")
    
    plt.rcParams.update({
        "font.family":      "sans-serif",
        "font.sans-serif":  [_sans],
        "font.size":        8,
        "axes.titlesize":   9,
        "axes.labelsize":   10,
        "xtick.labelsize":  8,
        "ytick.labelsize":  8,
        "legend.fontsize":  8,
        "figure.dpi":       300,
    })
    
    # Key climate features to explore with scientific names and units
    features = [
        {
            "col": "m1_m3_tmean_avg",
            "name": r"Jan-Mar Mean Temperature ($\mathrm{^\circ C}$)",
            "short_name": "Jan-Mar Mean Temp"
        },
        {
            "col": "m1_m3_precipitation_accum",
            "name": r"Jan-Mar Precipitation ($\mathrm{mm}$)",
            "short_name": "Jan-Mar Precip"
        },
        {
            "col": "m4_m6_tmean_avg",
            "name": r"Apr-Jun Mean Temperature ($\mathrm{^\circ C}$)",
            "short_name": "Apr-Jun Mean Temp"
        },
        {
            "col": "m4_m6_precipitation_accum",
            "name": r"Apr-Jun Precipitation ($\mathrm{mm}$)",
            "short_name": "Apr-Jun Precip"
        }
    ]
    
    # Ensure outputs directory exists
    os.makedirs("outputs/figures", exist_ok=True)
    
    # ------------------ PLOT 1: Multi-panel Boxplots ------------------
    # Double column width (7.2 inches)
    fig_box, axes_box = plt.subplots(2, 2, figsize=(7.2, 5.5), constrained_layout=True)
    axes_box_flat = axes_box.flatten()
    
    for idx, feat in enumerate(features):
        ax = axes_box_flat[idx]
        col_name = feat["col"]
        
        # Plot Boxplot (dynamite charts banned!)
        sns.boxplot(
            data=df, x="Symptom Severity", y=col_name, ax=ax,
            order=severity_order, hue="Symptom Severity", palette=SEVERITY_COLORS, 
            legend=False, width=0.4, flierprops={"marker": "none"}
        )
        
        # Low-N Overlay rule (each severity class has N < 30)
        sns.stripplot(
            data=df, x="Symptom Severity", y=col_name, ax=ax,
            order=severity_order, color="0.3", alpha=0.5, size=3, jitter=0.15
        )
        
        ax.set_xlabel("")
        ax.set_ylabel(feat["name"])
        sns.despine(ax=ax)
        
        # Subtle horizontal grid
        ax.yaxis.grid(True, linewidth=0.4, color="0.85", zorder=0)
        ax.set_axisbelow(True)
        
        # Add subpanel labels (A, B, C, D)
        letter = chr(65 + idx) # A, B, C, D
        ax.text(-0.15, 1.02, letter, transform=ax.transAxes,
                fontsize=12, fontweight="bold", va="bottom")
                
    box_out_path = "outputs/figures/climate_boxplots.pdf"
    fig_box.savefig(box_out_path, dpi=300, bbox_inches="tight")
    plt.close(fig_box)
    print(f"Success! Boxplots saved to: {box_out_path}")
    
    # ------------------ PLOT 2: Multi-panel Scatters ------------------
    fig_scat, axes_scat = plt.subplots(2, 2, figsize=(7.2, 5.5), constrained_layout=True)
    axes_scat_flat = axes_scat.flatten()
    
    for idx, feat in enumerate(features):
        ax = axes_scat_flat[idx]
        col_name = feat["col"]
        
        # Scatter points colored by group severity
        sns.scatterplot(
            data=df, x=col_name, y=target_col, hue="Symptom Severity",
            hue_order=severity_order, palette=SEVERITY_COLORS,
            ax=ax, s=20, alpha=0.8, edgecolor="none"
        )
        
        # Linear regression calculation
        slope, intercept, r_val, p_val, _ = stats.linregress(df[col_name], df[target_col])
        x_range = np.linspace(df[col_name].min(), df[col_name].max(), 100)
        ax.plot(x_range, slope * x_range + intercept, color="#000000", lw=1.0, ls="--", zorder=2)
        
        # Formatted R2 and exact p-value
        r2 = r_val ** 2
        r2_label = f"$R^2={r2:.2f}$\n$p={p_val:.3f}$" if p_val >= 0.001 else f"$R^2={r2:.2f}$\n$p<0.001$"
        ax.text(0.05, 0.95, r2_label, transform=ax.transAxes, fontsize=8, va="top")
        
        ax.set_xlabel(feat["name"])
        ax.set_ylabel(r"Visual Symptom Frequency ($\%$)")
        sns.despine(ax=ax)
        
        # Subtle grid
        ax.yaxis.grid(True, linewidth=0.4, color="0.85", zorder=0)
        ax.set_axisbelow(True)
        
        # Bounding-box-free Legend (show legend only on first panel to save space)
        if idx == 0:
            ax.legend(frameon=False, loc="upper right")
        else:
            ax.get_legend().remove()
            
        # Add subpanel labels (A, B, C, D)
        letter = chr(65 + idx)
        ax.text(-0.15, 1.02, letter, transform=ax.transAxes,
                fontsize=12, fontweight="bold", va="bottom")
                
    scat_out_path = "outputs/figures/climate_scatters.pdf"
    fig_scat.savefig(scat_out_path, dpi=300, bbox_inches="tight")
    plt.close(fig_scat)
    print(f"Success! Scatter plots saved to: {scat_out_path}")

if __name__ == "__main__":
    main()
