"""
Philippines 2024 — 6-month lookback split into two 3-month windows.

For each collection date in CWBD_PHL.csv the script:
  1. (Optional) Downloads climate data for the Philippines via ag-cube-cm.
  2. Looks back 180 days from the collection date.
  3. Splits that window into two non-overlapping 3-month periods:
       • m1_m3  →  T−90  to  T      (most recent 3 months)
       • m4_m6  →  T−180 to  T−91   (earliest  3 months)
  4. Computes meteorological summaries + climate indices per period.
  5. Extracts values at observation points.
  6. Saves combined features to data/processed/phl_2024_climate_windows.parquet

Download steps (run once before this script):
    python -m src.data.download_climate --config options/ag_cube_weather_phl_2024_download.yaml
    python -m src.data.download_climate --config options/ag_cube_weather_phl_2024_datacube.yaml

Then run this script:
    python -m notebooks.phl_2024_temporal_windows
"""

import sys
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd
import xarray
from tqdm import tqdm

# ── make src importable when run directly ─────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.features.climate_indices import calculate_indices
from src.features.met_summaries import calculate_meteorological_summaries
from src.utils.spatial_utils import extracting_using_gpdf

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

# NetCDF produced by the datacube step  (weather_<suffix>_<sy>_<ey>.nc)
CLIMATE_NC = "outputs/climate_data/weather_phl_2024_2023_2024.nc"

# ag-cube-cm config files for the two download steps
DOWNLOAD_CFG  = "options/ag_cube_weather_phl_2024_download.yaml"
DATACUBE_CFG  = "options/ag_cube_weather_phl_2024_datacube.yaml"

LOOKBACK_DAYS = 180   # total lookback from collection date
WINDOW_DAYS   = 90    # each 3-month period

VARIABLES_DICT = {
    "temp_accum":    ["tmean"],
    "hr_accum":      ["dailyhr"],
    "hr06_accum":    ["hr06"],
    "hr09_accum":    ["hr09"],
    "hr12_accum":    ["hr12"],
    "hr15_accum":    ["hr15"],
    "hr18_accum":    ["hr18"],
    "dewtemp_accum": ["dpt"],
    "vpd_accum":     ["vpd"],
    "etr_accum":     ["etr"],
    "srad_accum":    ["srad"],
    "prec_accum":    ["precipitation"],
}

INDICES_DICT = {
    "vpd_lt_20":              ["vpd", 1.5],
    "n_vpd_spells":           ["vpd", 1.5, 7],
    "n_wet_spells":           ["precipitation", 1.0, 7],
    "n_dry_spells":           ["precipitation", 1.0, 7],
    "avg_wet_spell_duration": ["precipitation", 1.0, 7],
    "avg_dry_spell_duration": ["precipitation", 1.0, 7],
    "rh_85_90_days": [
        ["dailyhr", "hr06", "hr09", "hr12", "hr15", "hr18"],
        [85, 90], [">=", "<="],
    ],
    "tmean_25_30_days":      ["tmean", [25, 30], [">=", "<="]],
    "max_temp_days":         ["tmax", 32],
    "precip_max_15d":        ["precipitation"],
    "max_hr_days":           ["dailyhr", 80],
    "consecutive_dry_days":  ["precipitation", 1.0],
    "growing_degree_days":   ["tmean", 15],
    "daily_intensity_index": ["precipitation", 1.0],
    "disease_pressure_index": ["vpd"],
}

# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — CLIMATE DOWNLOAD  (delegates to ag-cube-cm via the CLI script)
# ══════════════════════════════════════════════════════════════════════════════

def download_phl_climate():
    """Run the two-step download + datacube pipeline via ag-cube-cm."""
    for cfg, label in [
        (DOWNLOAD_CFG,  "download"),
        (DATACUBE_CFG, "datacube"),
    ]:
        print(f"\n[ag-cube-cm] task={label} …")
        result = subprocess.run(
            [sys.executable, "-m", "src.data.download_climate", "--config", cfg],
            cwd=str(ROOT),
            check=True,
        )
    print(f"\nClimate cube ready → {CLIMATE_NC}")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — DERIVED VARIABLES
# ══════════════════════════════════════════════════════════════════════════════

def prepare_derived_vars(ds: xarray.Dataset) -> xarray.Dataset:
    """Add tmean and dailyhr; expects tmax/tmin already in °C."""
    ds = ds.copy()
    ds["tmean"]   = (ds["tmax"] + ds["tmin"]) / 2
    ds["dailyhr"] = (
        ds[["hr06", "hr09", "hr12", "hr15", "hr18"]]
        .to_array(dim="hour")
        .mean(dim="hour")
    )
    return ds


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — WINDOW FEATURE COMPUTATION
# ══════════════════════════════════════════════════════════════════════════════

def compute_window(ds_full: xarray.Dataset,
                   start: pd.Timestamp,
                   end: pd.Timestamp,
                   label: str) -> xarray.Dataset:
    """
    Slice the climate cube to [start, end], derive variables, compute
    summaries + indices, and prefix every output variable with *label*.
    """
    window = ds_full.sel(date=slice(start, end))
    window = window.set_index(date="date").rename({"date": "time"})
    window = prepare_derived_vars(window)

    summaries = calculate_meteorological_summaries(window, VARIABLES_DICT)
    indices   = calculate_indices(window, INDICES_DICT)
    merged    = xarray.merge([summaries, indices])
    return merged.rename({v: f"{label}__{v}" for v in merged.data_vars})


# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — LOAD AND PREP OBSERVATIONS
# ══════════════════════════════════════════════════════════════════════════════

def load_observations(csv_path: str) -> gpd.GeoDataFrame:
    """
    Read CWBD_PHL.csv.  Returns one row per unique (location, date) with
    disease_incidence = proportion of 'P' records at that location/date.
    """
    df = pd.read_csv(csv_path)
    df["collection_date"] = pd.to_datetime(
        df["collection_date"].astype(str), format="%Y%m%d"
    )
    df["presence"] = (df["VS"].str.upper() == "P").astype(int)
    df["loc_key"]  = df["latitude"].astype(str) + "_" + df["longitude"].astype(str)

    grouped = (
        df.groupby(["loc_key", "collection_date", "latitude", "longitude"])
        ["presence"]
        .agg(disease_incidence="mean", n_obs="count")
        .reset_index()
    )
    return gpd.GeoDataFrame(
        grouped,
        geometry=gpd.points_from_xy(grouped.longitude, grouped.latitude),
        crs="EPSG:4326",
    )


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    os.chdir(ROOT)   # ensure relative paths resolve from project root

    # ── Observations ─────────────────────────────────────────────────────
    obs = load_observations("data/raw/CWBD_PHL.csv")
    collection_dates = sorted(obs["collection_date"].unique())
    print(f"Loaded {len(obs)} (location, date) records across {len(collection_dates)} dates.")

    # ── Climate data ──────────────────────────────────────────────────────
    if not Path(CLIMATE_NC).exists():
        print(f"Climate file not found: {CLIMATE_NC}")
        print("Starting download via ag-cube-cm (~30 min) …")
        download_phl_climate()

    print(f"Opening {CLIMATE_NC} …")
    climate_ds = xarray.open_dataset(CLIMATE_NC)

    # Unit corrections (guard against already-converted cubes)
    if float(climate_ds["vpd"].max()) > 10:
        climate_ds["vpd"] = climate_ds["vpd"] * 0.1        # hPa → kPa
    if float(climate_ds["dpt"].max()) > 100:
        climate_ds["dpt"] = climate_ds["dpt"] - 273.15     # K → °C

    print(climate_ds)

    # ── Main loop ─────────────────────────────────────────────────────────
    results = []

    for cdate in tqdm(collection_dates, desc="Collection dates"):
        t0 = pd.Timestamp(cdate)

        windows = {
            "m1_m3": (t0 - timedelta(days=WINDOW_DAYS),   t0),
            "m4_m6": (t0 - timedelta(days=LOOKBACK_DAYS), t0 - timedelta(days=WINDOW_DAYS + 1)),
        }

        date_obs = obs.loc[obs["collection_date"] == cdate].copy()
        if date_obs.empty:
            continue

        window_dss = {}
        for label, (wstart, wend) in windows.items():
            try:
                window_dss[label] = compute_window(climate_ds, wstart, wend, label)
            except Exception as e:
                print(f"  [warn] {cdate} / {label}: {e}")

        if not window_dss:
            continue

        combined = xarray.merge(list(window_dss.values()))
        date_obs["collection_date"] = cdate.strftime("%Y%m%d")
        results.append(extracting_using_gpdf(date_obs, combined))

    # ── Save ──────────────────────────────────────────────────────────────
    if not results:
        print("No results — check that climate data covers all collection dates.")
        return

    final = gpd.GeoDataFrame(
        pd.concat(results, ignore_index=True),
        geometry=pd.concat(results, ignore_index=True).geometry,
        crs="EPSG:4326",
    )

    out_path = "data/processed/phl_2024_climate_windows.parquet"
    Path("data/processed").mkdir(parents=True, exist_ok=True)
    final.to_parquet(out_path)

    m1_cols = [c for c in final.columns if c.startswith("m1_m3__")]
    m4_cols = [c for c in final.columns if c.startswith("m4_m6__")]
    print(f"\nSaved {len(final)} rows × {len(final.columns)} columns → {out_path}")
    print(f"  m1_m3 features : {len(m1_cols)}")
    print(f"  m4_m6 features : {len(m4_cols)}")
    print(f"\n{final[['collection_date','latitude','longitude','disease_incidence'] + m1_cols[:3] + m4_cols[:3]].head()}")

    return final


if __name__ == "__main__":
    main()
