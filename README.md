# Cassava Witches' Broom — Climate Analysis Pipeline

> **Can climate conditions explain where and when Cassava Witches' Broom disease appears?**
>
> This project builds a reproducible pipeline that links field disease observations
> in Southeast Asia and Central America to gridded climate indices, then uses those
> indices to model and explain disease incidence.

---

## Table of contents

1. [Background](#1-background)
2. [Scientific approach](#2-scientific-approach)
3. [Repository layout](#3-repository-layout)
4. [Installation](#4-installation)
5. [Step-by-step pipeline](#5-step-by-step-pipeline)
   - [5.1 Download climate data](#51-download-climate-data)
   - [5.2 Download administrative boundaries](#52-download-administrative-boundaries)
   - [5.3 Process disease observations](#53-process-disease-observations)
   - [5.4 Compute climate indices](#54-compute-climate-indices)
   - [5.5 Extract features at observation points](#55-extract-features-at-observation-points)
   - [5.6 Explore and model](#56-explore-and-model)
6. [Philippines 2024 example (temporal windows)](#6-philippines-2024-example-temporal-windows)
7. [Climate indices reference](#7-climate-indices-reference)
8. [Configuration reference](#8-configuration-reference)
9. [Roadmap](#9-roadmap)

---

## 1. Background

Cassava Witches' Broom (CWB) is a phytoplasma disease that causes severe yield
losses in cassava (*Manihot esculenta*) across Southeast Asia — Thailand, Laos,
Cambodia, Vietnam and the Philippines — and has recently been reported in Central
America. The pathogen is transmitted by insect vectors whose activity, and the
plant's susceptibility, are both modulated by weather conditions.

Field surveys have documented CWB incidence at hundreds of geo-referenced sites
across multiple growing seasons, but **the climate conditions that favour or
suppress disease outbreaks are not yet well quantified**. Understanding this link
would allow:

- Early-warning maps based on seasonal climate forecasts.
- Targeting surveillance to high-risk areas.
- Informing crop management calendars (planting date, monitoring windows).

This repository turns those field observations and gridded climate products into
a modelling-ready dataset.

---

## 2. Scientific approach

The analysis rests on three ideas:

**Lookback window.** Disease symptoms observed on a collection date reflect
conditions accumulated over the preceding growing period. We use a **180-day
(6-month) lookback** from each collection date, optionally split into
consecutive **3-month sub-windows** to capture temporal dynamics (early vs.
recent season conditions).

**Climate indices.** Rather than raw daily values, we compute 15 biologically
motivated indices — wet/dry spells, vapour-pressure deficit thresholds,
humidity-range days, degree-days, a composite disease-pressure index, etc. —
that map mechanistic hypotheses about pathogen and vector activity onto
measurable features. See the [full index reference](#7-climate-indices-reference).

**Spatial matching.** Each observation point is matched to the nearest
grid cell of a ~5 km resolution climate cube (AgEra5 + CHIRPS), so every
record receives the same set of features regardless of how many observations
share a cell.

The resulting tabular dataset feeds a **Random Forest regressor** with
spatially-aware cross-validation (`StratifiedGroupKFold` grouped by grid cell)
to prevent spatial leakage. Feature importance is assessed both by impurity
(MDI) and permutation, and Partial Dependence Plots reveal the shape of
individual variable–incidence relationships.

---

## 3. Repository layout

```
WitchesBroom/
│
├── config/
│   └── pipeline_config.yaml        <- centralised parameters (extent, dates, variables)
│
├── options/                         <- per-run YAML configs for ag-cube-cm
│   ├── ag_cube_weather_phl_2024_download.yaml
│   └── ag_cube_weather_phl_2024_datacube.yaml
│
├── notebooks/
│   ├── 01_exploratory_analysis.ipynb    <- full workflow demo (SEA 2014 dataset)
│   ├── 02_data_exploration.ipynb
│   └── phl_2024_temporal_windows.py     <- Philippines 2024 example script
│
├── data/
│   ├── raw/          <- original CSVs  (CWBD2.csv, CWBD_PHL.csv, …)
│   ├── processed/    <- cleaned / merged datasets
│   └── adm/          <- GADM administrative boundaries (downloaded)
│
├── outputs/
│   ├── climate_data/   <- NetCDF weather cubes  (AgEra5 + CHIRPS)
│   ├── spatial_data/   <- shapefiles / parquet observation files
│   ├── model_outputs/  <- cluster labels, symptom rasters, model artefacts
│   └── plots/
│
├── src/
│   ├── data/
│   │   ├── download_climate.py    <- ag-cube-cm download + datacube CLI
│   │   └── download_adm.py        <- GADM boundary downloader
│   ├── processing/
│   │   ├── process_disease_data.py   <- CSV -> GeoDataFrame, raster, train/val split
│   │   └── data_clustering.py        <- temporal KMeans clustering
│   ├── features/
│   │   ├── climate_indices.py    <- 15 disease-relevant climate indices
│   │   └── met_summaries.py      <- meteorological accumulators & averages
│   └── utils/
│       ├── spatial_utils.py      <- point extraction from xarray grids
│       └── visualization.py      <- facet-grid plotting helpers
│
├── docs/
│   ├── GITHUB_ISSUES_PLAN.md     <- GitHub Project backlog
│   └── PROPOSAL_README.md
│
└── bibliography/                  <- key references (PDFs)
```

---

## 4. Installation

### Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.10+ | |
| [ag-cube-cm](https://github.com/anaguilarar/ag-cube-cm) | Clone and install; provides `WeatherDownloadOrchestrator`, `MLTWeatherDataCube` |
| CDS / Copernicus account | Required for AgEra5 downloads (free registration) |

### Python packages

```bash
pip install xclim xarray rioxarray geopandas pandas numpy \
            omegaconf requests tslearn gdown tqdm scikit-learn \
            matplotlib seaborn
```

### Clone and set up

```bash
git clone <repo-url>
cd WitchesBroom
pip install -e .     # or add the root to PYTHONPATH
```

---

## 5. Step-by-step pipeline

The pipeline has five stages. Stages 1–3 are run once per region/period;
stages 4–6 are repeated for each analysis.

```
[1] Download climate    ->  outputs/climate_data/*.nc
[2] Download ADM        ->  data/adm/*.gpkg
[3] Process disease     ->  outputs/spatial_data/  +  data/processed/
[4] Compute indices     ->  (in-memory xarray Dataset)
[5] Extract at points   ->  data/processed/climate_incidence.parquet
[6] Explore & model     ->  notebooks/01_exploratory_analysis.ipynb
```

---

### 5.1 Download climate data

Climate data comes from two sources downloaded via **ag-cube-cm**:

| Source | Variables | Resolution |
|---|---|---|
| **AgEra5** | Tmax, Tmin, Solar radiation, RH at 06/09/12/15/18 UTC | ~5 km / daily |
| **CHIRPS** | Precipitation | ~5 km / daily |

The downloader uses YAML configuration files in `options/`. Each run has two
steps — `download` (fetch raw yearly files) and `datacube` (stack into one NetCDF).

**Edit the config** to set your spatial extent, date range, and output path:

```yaml
# options/ag_cube_weather_phl_2024_download.yaml
DATES:
  starting_date: "2023-10-01"
  ending_date:   "2024-09-30"
SPATIAL_INFO:
  extent: [121.0, 7.0, 126.0, 18.0]   # [xmin, ymin, xmax, ymax]
GENERAL:
  task:   download
  suffix: phl_2024
  ncores: 5
```

**Run:**

```bash
# Step 1 – download raw files
python -m src.data.download_climate --config options/ag_cube_weather_phl_2024_download.yaml

# Step 2 – stack into a single NetCDF cube
python -m src.data.download_climate --config options/ag_cube_weather_phl_2024_datacube.yaml
```

The second step produces `outputs/climate_data/weather_phl_2024_2023_2024.nc`
— a single file with dimensions `(date, y, x)` and all meteorological variables.

> **Tip:** For the Southeast Asia 2013–2014 dataset used in the exploratory
> notebook, change `extent` to `[96.98, 5.6, 110.0, 23.4]` and dates to
> `2013-01-01` / `2014-12-31`.

---

### 5.2 Download administrative boundaries

Administrative boundaries (provinces, districts) are used for spatial
summaries and mapping. They are downloaded from
[GADM 4.1](https://gadm.org) and saved as GeoPackage files.

```bash
# All countries defined in config (THA, LAO, KHM, VNM, PHL, MMR, HND, COL)
python -m src.data.download_adm

# Single country, ADM level 0 and 1
python -m src.data.download_adm --iso PHL --level 0 1

# Include district level (ADM2)
python -m src.data.download_adm --iso THA --level 0 1 2
```

Files are saved to `data/adm/PHL_adm0.gpkg`, `data/adm/PHL_adm1.gpkg`, etc.

---

### 5.3 Process disease observations

The raw observation CSV (`data/raw/CWBD2.csv`) records individual plant
assessments. This step:

1. Converts lat/lon columns to a GeoDataFrame.
2. Deduplicates to unique locations and computes **visual symptom frequency**
   (% of positive assessments per site).
3. Rasterises symptom frequency onto the climate grid.
4. Merges the Philippines 2024 data and creates a temporal train/validation split.

```bash
python -m src.processing.process_disease_data
```

Key outputs:

| File | Description |
|---|---|
| `outputs/spatial_data/spatial_data_unique.shp` | Unique observation locations with symptom frequency |
| `outputs/model_outputs/visual_symptoms_2014.tif` | Raster of mean symptom frequency on climate grid |
| `data/processed/wb_train_exclude_2022.csv` | Training set (all years except 2022) |
| `data/processed/wb_validation_2022.csv` | Held-out validation set |

---

### 5.4 Compute climate indices

Climate indices are computed **per observation date** using the
`src/features/` modules. The core function is `calculate_indices`, which
accepts an xarray Dataset and a dict describing what to compute:

```python
from src.features.climate_indices import calculate_indices
from src.features.met_summaries import calculate_meteorological_summaries

# Define a 180-day window ending on the collection date
window = climate_ds.sel(date=slice(start_date, collection_date))
window = window.rename({"date": "time"})
window["tmean"]   = (window["tmax"] + window["tmin"]) / 2
window["dailyhr"] = window[["hr06","hr09","hr12","hr15","hr18"]].to_array("h").mean("h")

# 12 meteorological accumulators
summaries = calculate_meteorological_summaries(window, variables_dict)

# 15 climate indices
indices = calculate_indices(window, indices_dict)
```

See the [index reference](#7-climate-indices-reference) for the full list and
biological rationale.

---

### 5.5 Extract features at observation points

Once indices are computed spatially (as xarray DataArrays), values are
extracted at each observation point using nearest-grid-cell matching:

```python
from src.utils.spatial_utils import extracting_using_gpdf

features_at_points = extracting_using_gpdf(observation_gdf, climate_indices_ds)
```

The result is a GeoDataFrame where each row is one (observation point, date)
pair and the columns are the climate features.

The full loop across all collection dates is implemented in
`notebooks/01_exploratory_analysis.ipynb` and produces
`data/processed/climate_incidence.parquet` — the modelling-ready dataset with
407 rows × 43 columns for the SEA 2014 dataset.

---

### 5.6 Explore and model

Open `notebooks/01_exploratory_analysis.ipynb` for the complete workflow:

**Spatial visualisation.** Each index is plotted as a spatial map with
observation points overlaid, to check that the climate signal aligns with
the observed disease distribution.

```python
from src.utils.visualization import plot_facet_grid_with_points
plot_facet_grid_with_points(indices_ds, points_gdf=observations_2014, ncols=4)
```

**Random Forest model.** A spatially-aware train/test split avoids
leakage between nearby points:

```python
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.ensemble import RandomForestRegressor

sgkf = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=42)
for train_idx, test_idx in sgkf.split(X, y_binary, groups=cell_ids):
    ...

rf = RandomForestRegressor(n_estimators=300, max_depth=5,
                           min_samples_leaf=5, max_features="sqrt")
rf.fit(X_train, y_train)
```

**Feature importance.** Two methods are compared:

- *MDI (built-in Gini importance)* — fast but biased toward high-cardinality features.
- *Permutation importance* — measures actual drop in R² when each feature is
  scrambled; more reliable for correlated features.

**Partial Dependence Plots.** Show the average marginal effect of a single
variable on predicted incidence, holding all others at their mean:

```python
from sklearn.inspection import PartialDependenceDisplay
PartialDependenceDisplay.from_estimator(rf, X_train,
    features=["prec_accum"], kind="both")
```

---

## 6. Philippines 2024 example (temporal windows)

The Philippines 2024 dataset (`data/raw/CWBD_PHL.csv`, 735 records,
15 collection dates) demonstrates the **temporal window** approach: instead
of one 6-month accumulation, the lookback is split into two consecutive
3-month periods to capture whether *early* or *recent* conditions matter more.

```
Collection date T
│
├── m4_m6  [T−180 to T−91]   early season  (e.g. Oct–Jan for an Apr collection)
└── m1_m3  [T−90  to T]      recent season (e.g. Jan–Apr for an Apr collection)
```

Each period produces its own set of 27 features, prefixed `m4_m6__` and
`m1_m3__` respectively, for a total of 54 features per observation point.

**Run the full example:**

```bash
# Download (if climate NetCDF not yet available)
python -m src.data.download_climate --config options/ag_cube_weather_phl_2024_download.yaml
python -m src.data.download_climate --config options/ag_cube_weather_phl_2024_datacube.yaml

# Compute temporal-window features
python -m notebooks.phl_2024_temporal_windows
```

Output: `data/processed/phl_2024_climate_windows.parquet`

---

## 7. Climate indices reference

All indices are implemented in `src/features/climate_indices.py`.
They operate on xarray Datasets with a `time` dimension and standard
meteorological variables (see configuration section for variable names).

| Index | Variables used | Description | Disease relevance |
|---|---|---|---|
| `vpd_lt_15` | `vpd` | % of days with VPD ≤ 1.5 kPa | Low VPD = high atmospheric humidity, favours phytoplasma vector activity |
| `n_vpd_spells` | `vpd` | Number of runs of ≥ 7 consecutive humid days (VPD ≤ 1.5 kPa) | Sustained humid periods drive vector population build-up |
| `n_wet_spells` | `precipitation` | Number of runs of ≥ 7 consecutive wet days (≥ 1 mm/d) | Wet spells increase canopy wetness and insect breeding sites |
| `n_dry_spells` | `precipitation` | Number of runs of ≥ 7 consecutive dry days (< 1 mm/d) | Drought stress can increase plant susceptibility |
| `avg_wet_spell_duration` | `precipitation` | Mean length (days) of wet spells ≥ 7 days | Captures persistence of wet conditions |
| `avg_dry_spell_duration` | `precipitation` | Mean length (days) of dry spells ≥ 7 days | Captures persistence of drought |
| `rh_85_90_days` | `dailyhr`, `hr06`–`hr18` | Days with RH between 85–90% (×6 time slots) | Optimal humidity range for phytoplasma transmission; computed independently at each observation time |
| `tmean_25_30_days` | `tmean` | Days with mean temperature 25–30 °C | Optimal thermal range for both vector and pathogen development |
| `max_temp_days` | `tmax` | Days with max temperature > 32 °C | Heat stress may inhibit vector or pathogen activity above threshold |
| `max_hr_days` | `dailyhr` | Days with mean daily RH ≥ 80% | Broad humidity threshold associated with disease-favourable conditions |
| `precip_max_15d` | `precipitation` | Maximum 15-day accumulated rainfall | Captures intense rainfall events that promote vector breeding |
| `consecutive_dry_days` | `precipitation` | Longest run of dry days (< 1 mm/d) | Extreme drought periods as stress indicator |
| `growing_degree_days` | `tmean` | Accumulated heat units above 15 °C base | Proxy for crop phenological stage at collection time |
| `daily_intensity_index` | `precipitation` | Mean rainfall on rainy days (≥ 1 mm/d) | Distinguishes frequent light rain from infrequent heavy events |
| `disease_pressure_index` | `dailyhr`, `precipitation`, `vpd` | Composite: (RH_norm × precip_norm) / VPD_norm, clipped 0–1 | Single score combining humidity, rainfall, and dryness into one disease-pressure signal |

In addition, 12 **meteorological accumulators** are computed:

| Accumulator | Description |
|---|---|
| `temp_accum` | Sum of daily mean temperature |
| `hr_accum` / `hr06_accum` … `hr18_accum` | Sum of relative humidity (daily mean + each observation time) |
| `dewtemp_accum` | Sum of dew-point temperature |
| `vpd_accum` | Sum of vapour-pressure deficit |
| `etr_accum` | Sum of reference evapotranspiration |
| `srad_accum` | Sum of solar radiation |
| `prec_accum` | Total precipitation |

---

## 8. Configuration reference

All pipeline parameters are centralised in `config/pipeline_config.yaml`.

| Key | Default | Description |
|---|---|---|
| `spatial.extent` | `[96.98, 5.6, 110.0, 23.4]` | `[xmin, ymin, xmax, ymax]` for SEA full region |
| `dates.starting_date` | `2013-01-01` | Start of climate download period |
| `dates.ending_date` | `2022-12-31` | End of climate download period |
| `dates.validation_year` | `2022` | Year held out for temporal validation |
| `indices.lookback_days` | `180` | Days before collection date |
| `indices.vpd_threshold` | `1.5` | kPa threshold for humid-day classification |
| `indices.precip_wet_threshold` | `1.0` | mm/d threshold for wet-day classification |
| `indices.spell_window` | `7` | Minimum consecutive days to count as a spell |
| `indices.temp_base` | `15` | °C base temperature for growing degree days |
| `general.ncores` | `5` | Parallel cores for download |
| `general.suffix` | `sea` | Label appended to output folder names |

Per-run overrides (spatial extent, dates) go in dedicated `options/*.yaml` files.

---

## 9. Roadmap

Full issue details in [docs/GITHUB_ISSUES_PLAN.md](docs/GITHUB_ISSUES_PLAN.md).

| Status | Item |
|---|---|
| ✅ Done | Project restructure (`src/data`, `src/features`, `src/processing`, `src/utils`) |
| ✅ Done | 15 climate indices extracted into reusable module |
| ✅ Done | Philippines 2024 temporal-window example |
| 🔲 Next | Integrate Philippines 2024 data into main training set |
| 🔲 Next | Use 2022 as held-out temporal validation |
| 🔲 Next | Compare 60-day, 90-day, and 180-day feature windows |
| 🔲 Next | Vegetation-index–based planting date estimation (NDVI/EVI green-up) |
| 🔲 Next | Align climate window to planting date instead of collection date |
| 🔲 Next | Additional bioclimatic indices (WorldClim-style) |
| 🔲 Next | Formal spatial cross-validation report (R², RMSE per country) |
| 🔲 Final | **Write and submit scientific paper** (target: *Plant Disease* or *Agricultural and Forest Meteorology*) |

---

*Maintained by the CGIAR Plant Health team.*
*Climate data: AgEra5 (Copernicus / FAO) + CHIRPS (UCSB). Disease data: CGIAR field surveys.*
