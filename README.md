# Cassava Witches' Broom — Climate Analysis Pipeline

> **Can climate conditions explain where and when Cassava Witches' Broom disease appears?**
>
> This project builds a reproducible pipeline that links field disease observations
> in Southeast Asia and Central America to gridded climate indices, then uses those
> indices to model and explain disease incidence.

---

## Table of contents

1. [Background](#1-background)
2. [Repository layout](#2-repository-layout)
3. [Installation](#3-installation)
4. [Step-by-step pipeline](#4-step-by-step-pipeline)
   - [4.1 Download climate data](#41-download-climate-data)
   - [4.2 Download administrative boundaries](#42-download-administrative-boundaries)
   - [4.3 Process disease observations](#43-process-disease-observations)
   - [4.4 Compute climate indices](#44-compute-climate-indices)
5. [Climate indices reference](#5-climate-indices-reference)
6. [Configuration reference](#6-configuration-reference)


---

## 1. Background

Cassava Witches' Broom (CWB) is a phytoplasma disease that causes severe yield
losses in cassava (*Manihot esculenta*) across Southeast Asia — Thailand, Laos,
Cambodia, Vietnam and the Philippines — and has recently been reported in Central
America. The pathogen is transmitted by insect vectors whose activity, and the
plant's susceptibility, are both modulated by weather conditions.

---

## 2. Repository layout

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
│   │   ├── climate_indices.py    <- 17 disease-relevant climate indices
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

## 3. Installation

### Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.10+ | |
| CDS / Copernicus account | Required for AgEra5 downloads (free registration) |

### Python packages

```bash
pip install https://github.com/anaguilarar/ag-cube-cm.git
            
pip install xclim xarray rioxarray geopandas pandas numpy \
            omegaconf requests tslearn gdown tqdm scikit-learn \
            matplotlib seaborn

          
```

### Clone and set up

```bash
git clone https://github.com/anaguilarar/WitchesBroom.git
cd WitchesBroom
pip install -e .     # or add the root to PYTHONPATH
```

---

## 4. Step-by-step pipeline

The pipeline has five stages. Stages 1–3 are run once per region/period;
stages 4–6 are repeated for each analysis.

```
[1] Download climate    ->  outputs/climate_data/*.nc
[2] Download ADM        ->  data/adm/*.gpkg
[3] Process disease     ->  outputs/spatial_data/  +  data/processed/
[4] Compute indices     ->  (in-memory xarray Dataset)
```

---

### 4.1 Download climate data

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

### 4.2 Download administrative boundaries

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

### 4.3 Process disease observations

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

### 4.4 Compute climate indices

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

# 17 climate indices
indices = calculate_indices(window, indices_dict)
```

See the [index reference](#7-climate-indices-reference) for the full list and
biological rationale.

---

## 5. Climate indices reference

All indices are implemented in `src/features/climate_indices.py`.
They operate on xarray Datasets with a `date` dimension and standard
meteorological variables. Thresholds are literature-derived from cassava
physiology, phytoplasma biology, and leafhopper vector studies
(see `CWB_Climate_Thresholds_Literature_Review.md` for full citations).

### 5.1 Humidity & VPD indices

| Index | Variables | Description | Disease relevance |
|---|---|---|---|
| `vpd_lt_20` | `vpd` | % of days with VPD ≤ 1.5 kPa | Optimal stomatal conductance and vector activity range; 1.5 kPa is the upper limit for favourable phytoplasma transmission conditions |
| `n_vpd_spells` | `vpd` | Number of runs of ≥ 7 consecutive humid days (VPD ≤ 1.5 kPa) | Sustained humid periods drive leafhopper population build-up |
| `max_hr_days` | `dailyhr` | Days with mean daily RH ≥ 80% | Broad disease-favourable humidity threshold (literature: ≥ 80% optimal for *Hishimonus* spp.) |
| `max_hr06_days` / `max_hr09_days` / `max_hr18_days` | `hr06`, `hr09`, `hr18` | Days with morning / evening RH ≥ 85% | Crepuscular leafhopper activity peaks; dew formation and high canopy moisture maximise acquisition and inoculation windows |
| `max_hr12_days` / `max_hr15_days` | `hr12`, `hr15` | Days with midday / afternoon RH ≥ 70% | Lower threshold appropriate due to stomatal closure-driven reduction in vector feeding and phloem accessibility at peak VPD hour (Sci. Rep. 2018) |
| `rh_85_90_days` | `dailyhr`, `hr06`–`hr18` | Days with RH 85–90 % (×6 time slots) | Optimal narrow-band humidity range for phytoplasma transmission; computed independently per observation hour |
| `canopy_wetness_duration` | `hr06`, `hr09`, `hr12`, `hr15`, `hr18` | Mean hours/day with RH ≥ 85 %, estimated by linear interpolation across five fixed-time observations plus the 12 h nighttime gap (18:00 → next-day 06:00) | Direct driver of phytoplasma transmission opportunity; analogous diseases (rice yellow dwarf, sugarcane white leaf) show epidemic acceleration at CWD ≥ 8–10 h/day |

### 5.2 Temperature indices

| Index | Variables | Description | Disease relevance |
|---|---|---|---|
| `tmean_25_30_days` | `tmean` | Days with mean temperature 25–30 °C | Optimal thermal window for both leafhopper development and phytoplasma replication (transmission optimum 20–25 °C per Sci. Rep. 2018) |
| `max_temp_days` | `tmax` | Days with tmax > 32 °C | Early heat-stress signal; vector fecundity begins declining above 30–32 °C |
| `heat_wave_duration` | `tmax` | Mean duration (days) of spells with tmax > **35 °C** for ≥ 5 consecutive days | Above 35 °C cassava photosynthesis declines significantly and leafhopper reproduction fails; 30 °C (former threshold) is the cassava growth *optimum*, not a stress onset (Front. Plant Sci. 2023; Sci. Rep. 2018) |
| `cold_wave_duration` | `tmin` | Mean duration (days) of spells with tmin < **18 °C** for ≥ 5 consecutive days | Below 18 °C cassava root development halts; phytoplasma replication rate slows and leafhopper development stops; replaces former 22 °C threshold which is climatologically meaningless in tropical lowlands (Plants 2022; FAO GAEZ) |
| `cool_night_frequency` | `tmin` | Mean count of cool nights (tmin < **15 °C**) per rolling 10-day window | Highland-specific suppressor: frequent sub-15 °C nights reduce leafhopper population growth rate even when daytime temperatures are favourable; high values also correlate with dawn dew formation and sustained RH ≥ 90 % at 06:00 |
| `growing_degree_days` | `tmean` | Accumulated heat units above **10 °C** base (FAO tropical crop standard) | Proxy for cassava phenological stage and cumulative thermal exposure available for vector development; replaces former 15 °C base which underestimates GDD in SEA highland sites (FAO GAEZ) |

### 5.3 Precipitation indices

| Index | Variables | Description | Disease relevance |
|---|---|---|---|
| `n_wet_spells` | `precipitation` | Number of runs of ≥ 5 consecutive wet days (≥ 1 mm/d) | Wet spells sustain canopy wetness and leafhopper breeding sites; 5 days sufficient for early nymph survival |
| `n_dry_spells` | `precipitation` | Number of runs of ≥ **7** consecutive dry days (< 1 mm/d) | Drought stress and immune suppression onset in cassava after ≥ 7 dry days; 5 days too short for measurable physiological impact (Euphytica 2017; Plants 2024) |
| `avg_wet_spell_duration` | `precipitation` | Mean length (days) of wet spells ≥ 5 days | Captures persistence of wet conditions favouring vector population growth |
| `avg_dry_spell_duration` | `precipitation` | Mean length (days) of dry spells ≥ 7 days | Captures persistence of drought-driven plant susceptibility |
| `consecutive_dry_days` | `precipitation` | Longest run of dry days (< 1 mm/d) | Extreme drought period as plant-stress indicator |
| `precip_max_15d` | `precipitation` | Maximum 15-day accumulated rainfall | Captures intense rainfall events that promote vector breeding habitats |
| `daily_intensity_index` | `precipitation` | Mean rainfall on rainy days (≥ 1 mm/d) | Distinguishes frequent light rain from infrequent heavy events |

### 5.4 Composite index

| Index | Variables | Description | Disease relevance |
|---|---|---|---|
| `disease_pressure_index` | `dailyhr`, `precipitation`, `vpd` | (RH_norm × precip_norm) / VPD_norm, clipped 0–1 | Single score combining humidity, rainfall, and atmospheric dryness into one disease-pressure signal |

---

### 5.5 Meteorological accumulators

Twelve accumulators are computed alongside the indices by `met_summaries.py`:

| Accumulator | Description |
|---|---|
| `tmax_avg` / `tmin_avg` / `tmean_avg` | Mean maximum, minimum, and mean temperature |
| `rh06_avg` … `rh18_avg` | Mean relative humidity at each observation hour |
| `vpd_accum` | Sum of vapour-pressure deficit |
| `precipitation_accum` | Total precipitation |
| `etr_accum` | Sum of reference evapotranspiration |
| `srad_accum` | Sum of incoming solar radiation |

---

## 6. Configuration reference

All pipeline parameters are centralised in `config/pipeline_config.yaml`.

| Key | Default | Description |
|---|---|---|
| `spatial.extent` | `[96.98, 5.6, 110.0, 23.4]` | `[xmin, ymin, xmax, ymax]` for SEA full region |
| `dates.starting_date` | `2013-01-01` | Start of climate download period |
| `dates.ending_date` | `2022-12-31` | End of climate download period |
| `dates.validation_year` | `2022` | Year held out for temporal validation |
| `indices.lookback_days` | `180` | Days before collection date |
| `indices.vpd_threshold` | `1.5` | kPa threshold for humid-day classification (`vpd_lt_20`) |
| `indices.precip_wet_threshold` | `1.0` | mm/d threshold for wet-day classification (FAO standard) |
| `indices.spell_window` | `7` | Minimum consecutive days for wet spells; dry spells also use 7 days |
| `indices.temp_base` | `10` | °C base temperature for GDD (FAO tropical crop standard; replaces former 15 °C) |
| `indices.heat_wave_thresh` | `35` | °C tmax threshold for heat-wave detection (cassava photosynthesis stress onset) |
| `indices.cold_wave_thresh` | `18` | °C tmin threshold for cold-wave detection (cassava root development minimum) |
| `indices.cool_night_thresh` | `15` | °C tmin threshold for cool-night frequency (highland leafhopper suppression) |
| `indices.cwd_rh_threshold` | `85` | % RH threshold for canopy wetness duration estimation |
| `general.ncores` | `5` | Parallel cores for download |
| `general.suffix` | `sea` | Label appended to output folder names |

Per-run overrides (spatial extent, dates) go in dedicated `options/*.yaml` files.

