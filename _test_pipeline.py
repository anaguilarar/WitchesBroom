"""Quick pipeline smoke-test — run from the WitchesBroom root."""
import sys, os
sys.path.insert(0, os.getcwd())

from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import geopandas as gpd
import xarray

# ── 1. Imports ────────────────────────────────────────────────────────────
print("--- Testing src imports ---")
from src.features.climate_indices import calculate_indices
from src.features.met_summaries import calculate_meteorological_summaries
from src.utils.spatial_utils import extracting_using_gpdf
print("  [OK] climate_indices, met_summaries, spatial_utils")
# visualization imports matplotlib — skip in headless test
try:
    from src.utils.visualization import plot_facet_grid
    print("  [OK] visualization")
except ModuleNotFoundError as e:
    print(f"  [skip] visualization ({e})")

# ── 2. Load observations ──────────────────────────────────────────────────
print("\n--- Loading CWBD_PHL.csv ---")
df = pd.read_csv("data/raw/CWBD_PHL.csv")
df["collection_date"] = pd.to_datetime(df["collection_date"].astype(str), format="%Y%m%d")
df["presence"] = (df["VS"].str.upper() == "P").astype(int)
df["loc_key"]  = df["latitude"].astype(str) + "_" + df["longitude"].astype(str)
grouped = (
    df.groupby(["loc_key", "collection_date", "latitude", "longitude"])["presence"]
    .agg(disease_incidence="mean", n_obs="count")
    .reset_index()
)
gdf = gpd.GeoDataFrame(
    grouped,
    geometry=gpd.points_from_xy(grouped.longitude, grouped.latitude),
    crs="EPSG:4326",
)
print(f"  [OK] {len(gdf)} unique (location, date) records")
dates_str = sorted(gdf.collection_date.dt.strftime("%Y-%m-%d").unique())
print(f"  Dates  : {dates_str}")
print(f"  Inc.   : {gdf.disease_incidence.min():.2f} – {gdf.disease_incidence.max():.2f}")
print(f"  BBox   : lon {gdf.geometry.x.min():.2f}–{gdf.geometry.x.max():.2f}, "
      f"lat {gdf.geometry.y.min():.2f}–{gdf.geometry.y.max():.2f}")

# ── 3. Synthetic climate test (no download needed) ────────────────────────
print("\n--- Synthetic climate + window logic ---")

np.random.seed(42)
dates  = pd.date_range("2023-10-01", "2024-09-30", freq="D")
lons   = np.linspace(121.0, 126.0, 20)
lats   = np.linspace(7.0,  18.0,  20)

def rand_var(mean, std):
    return (np.random.randn(len(dates), len(lats), len(lons)) * std + mean).astype(np.float32)

ds_synth = xarray.Dataset(
    {
        "precipitation": (["date", "y", "x"], rand_var(3.0,  2.0).clip(0)),
        "tmax":          (["date", "y", "x"], rand_var(32.0, 3.0)),
        "tmin":          (["date", "y", "x"], rand_var(22.0, 3.0)),
        "hr06":          (["date", "y", "x"], rand_var(80.0, 8.0).clip(0, 100)),
        "hr09":          (["date", "y", "x"], rand_var(75.0, 8.0).clip(0, 100)),
        "hr12":          (["date", "y", "x"], rand_var(65.0, 8.0).clip(0, 100)),
        "hr15":          (["date", "y", "x"], rand_var(60.0, 8.0).clip(0, 100)),
        "hr18":          (["date", "y", "x"], rand_var(70.0, 8.0).clip(0, 100)),
        "vpd":           (["date", "y", "x"], rand_var(1.2,  0.4).clip(0.01)),
        "dpt":           (["date", "y", "x"], rand_var(20.0, 2.0)),
        "etr":           (["date", "y", "x"], rand_var(4.0,  1.0).clip(0)),
        "srad":          (["date", "y", "x"], rand_var(18.0, 4.0).clip(0)),
    },
    coords={"date": dates, "y": lats, "x": lons},
)
print(f"  [OK] synthetic cube: {dict(ds_synth.dims)}")

# Add derived variables
ds_synth["tmean"]   = (ds_synth["tmax"] + ds_synth["tmin"]) / 2
ds_synth["dailyhr"] = (
    ds_synth[["hr06","hr09","hr12","hr15","hr18"]]
    .to_array(dim="hour").mean(dim="hour")
)

# Pick one evaluation date and define two 3-month windows
eval_date = pd.Timestamp("2024-04-15")
WINDOW    = 90
LOOKBACK  = 180

windows = {
    "m1_m3": (eval_date - timedelta(days=WINDOW),   eval_date),
    "m4_m6": (eval_date - timedelta(days=LOOKBACK),  eval_date - timedelta(days=WINDOW+1)),
}
print(f"\n  Evaluation date : {eval_date.date()}")
for label, (s, e) in windows.items():
    print(f"  {label}            : {s.date()} to {e.date()}  ({(e-s).days} days)")

# ── 4. Summaries + indices per window ─────────────────────────────────────
print("\n--- Computing summaries & indices per window ---")
VARIABLES_DICT = {
    "temp_accum":   ["tmean"], "hr_accum":    ["dailyhr"],
    "vpd_accum":    ["vpd"],   "prec_accum":  ["precipitation"],
    "srad_accum":   ["srad"],
}
INDICES_DICT = {
    "vpd_lt_20":              ["vpd", 1.5],
    "n_wet_spells":           ["precipitation", 1.0, 7],
    "n_dry_spells":           ["precipitation", 1.0, 7],
    "avg_wet_spell_duration": ["precipitation", 1.0, 7],
    "max_hr_days":            ["dailyhr", 80],
    "consecutive_dry_days":   ["precipitation", 1.0],
    "growing_degree_days":    ["tmean", 15],
    "daily_intensity_index":  ["precipitation", 1.0],
}

windows = {
    "m1_m3": (eval_date - timedelta(days=WINDOW),   eval_date),
    "m4_m6": (eval_date - timedelta(days=LOOKBACK),  eval_date - timedelta(days=WINDOW+1)),
}

window_results = {}
for label, (wstart, wend) in windows.items():
    w = ds_synth.sel(date=slice(wstart, wend))
    w = w.set_index(date="date").rename({"date": "time"})
    summaries = calculate_meteorological_summaries(w, VARIABLES_DICT)
    indices   = calculate_indices(w, INDICES_DICT)
    merged    = xarray.merge([summaries, indices])
    merged    = merged.rename({v: f"{label}__{v}" for v in merged.data_vars})
    window_results[label] = merged
    n_vars = len(merged.data_vars)
    print(f"  [OK] {label}: {n_vars} variables computed  "
          f"(shape y={len(merged.y)}, x={len(merged.x)})")

# ── 5. Extract at observation points ─────────────────────────────────────
print("\n--- Extracting at observation points ---")
combined_ds = xarray.merge(list(window_results.values()))
obs_subset  = gdf.loc[gdf.collection_date == eval_date].copy()

if obs_subset.empty:
    # Use first available date if April 15 not in PHL data at this eval run
    eval_date2  = gdf.collection_date.iloc[0]
    obs_subset  = gdf.loc[gdf.collection_date == eval_date2].copy()
    print(f"  (using {eval_date2.date()} as test date instead)")

obs_subset["collection_date"] = obs_subset["collection_date"].dt.strftime("%Y%m%d")
extracted = extracting_using_gpdf(obs_subset, combined_ds)
print(f"  [OK] extracted: {extracted.shape[0]} points × {extracted.shape[1]} columns")
feature_cols = [c for c in extracted.columns if "__" in c]
print(f"  Feature columns ({len(feature_cols)}): {feature_cols[:6]} …")

# ── 6. Summary ─────────────────────────────────────────────────────────────
print("\n=== Pipeline smoke-test PASSED ===")
print(f"  Ready to run on real NetCDF once climate data is downloaded.")
print(f"  Download command:")
print(f"    python -m notebooks.phl_2024_temporal_windows")
