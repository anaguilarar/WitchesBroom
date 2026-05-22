# Witches' Broom Disease — Climate Analysis Pipeline

Modelling the relationship between climate conditions and Cassava Witches' Broom
(CWB) disease incidence in Southeast Asia and Central America.

---

## Project structure

```
WitchesBroom/
│
├── config/
│   └── pipeline_config.yaml      ← all parameters (dates, extents, variables)
│
├── notebooks/
│   ├── 01_exploratory_analysis.ipynb   ← full workflow demo (180-day lookback)
│   └── 02_data_exploration.ipynb
│
├── data/
│   ├── raw/          ← original CSVs (CWBD2.csv, CWBD_PHL.csv, …)
│   ├── processed/    ← cleaned / merged datasets
│   └── adm/          ← GADM administrative boundaries (downloaded)
│
├── outputs/
│   ├── climate_data/   ← NetCDF weather cubes (AgEra5 + CHIRPS)
│   ├── spatial_data/   ← shapefiles / parquet spatial files
│   ├── model_outputs/  ← cluster labels, symptom rasters, model artefacts
│   └── plots/
│
├── src/
│   ├── data/
│   │   ├── download_climate.py   ← AgEra5 + CHIRPS via ag-cube-cm
│   │   └── download_adm.py       ← GADM boundary download
│   │
│   ├── processing/
│   │   ├── process_disease_data.py  ← CSV → shapefile, raster, train/val split
│   │   └── data_clustering.py       ← TimeSeriesKMeans by weather pattern
│   │
│   ├── features/
│   │   ├── climate_indices.py    ← 15 disease-relevant climate indices
│   │   └── met_summaries.py      ← meteorological accumulators & averages
│   │
│   └── utils/
│       ├── spatial_utils.py      ← point extraction from xarray
│       └── visualization.py      ← facet grid plots
│
├── docs/
│   ├── GITHUB_ISSUES_PLAN.md     ← GitHub Project issues backlog
│   └── PROPOSAL_README.md
│
└── bibliography/
```

---

## Pipeline overview

```
1. DOWNLOAD DATA
   ├─ src/data/download_climate.py   →  outputs/climate_data/*.nc
   └─ src/data/download_adm.py       →  data/adm/*.gpkg

2. PROCESS OBSERVATIONS
   └─ src/processing/process_disease_data.py
       ├─ unique coordinates  →  outputs/spatial_data/spatial_data_unique.shp
       ├─ symptom raster      →  outputs/model_outputs/visual_symptoms_2014.tif
       └─ train/val split     →  data/processed/wb_train_*.csv

3. FEATURE ENGINEERING  (for each collection date, 180-day lookback)
   ├─ src/features/met_summaries.py    →  12 met accumulators / averages
   └─ src/features/climate_indices.py  →  15 disease-pressure indices
       vpd_lt_15, n_vpd_spells, n_wet_spells, n_dry_spells,
       avg_wet/dry_spell_duration, rh_85_90_days (×6 times),
       tmean_25_30_days, max_temp_days, max_hr_days,
       precip_max_15d, consecutive_dry_days, growing_degree_days,
       daily_intensity_index, disease_pressure_index

4. MODELLING  (notebook 01)
   ├─ StratifiedGroupKFold split (group = cell_id)
   ├─ RandomForestRegressor (n=300, max_depth=5)
   ├─ MDI + Permutation feature importance
   └─ Partial Dependence Plots

5. OPTIONAL: TIME-SERIES CLUSTERING
   └─ src/processing/data_clustering.py  →  KMeans on weather time series
```

---

## Quick start

### 1. Download climate data

```bash
python -m src.data.download_climate   # uses config/pipeline_config.yaml
```

### 2. Download administrative boundaries

```bash
python -m src.data.download_adm                  # all countries, ADM0+ADM1
python -m src.data.download_adm --iso THA        # single country
python -m src.data.download_adm --level 0 1 2    # include district level
```

### 3. Process disease observations

```bash
python -m src.processing.process_disease_data
```

### 4. Run full exploratory workflow

Open `notebooks/01_exploratory_analysis.ipynb`.

---

## Configuration

All parameters live in [config/pipeline_config.yaml](config/pipeline_config.yaml):

| Key | Description |
|-----|-------------|
| `spatial.extent` | `[xmin, ymin, xmax, ymax]` bounding box for downloads |
| `dates.starting_date` / `ending_date` | download / analysis period |
| `dates.validation_year` | year held out for validation (2022) |
| `weather.agera5_variables` | AgEra5 variables to download |
| `weather.chirps_variables` | CHIRPS precipitation |
| `indices.lookback_days` | days before collection date (default 180) |
| `general.ncores` | parallel download workers |

---

## Dependencies

Install with:
```bash
pip install xclim xarray rioxarray geopandas pandas numpy omegaconf requests tslearn gdown tqdm
```

The climate downloader also requires the
[ag-cube-cm](https://github.com/anaguilarar/ag-cube-cm) package

---

## Planned work

See [docs/GITHUB_ISSUES_PLAN.md](docs/GITHUB_ISSUES_PLAN.md) for the full
GitHub Project backlog, including:

- Philippines 2024 data integration
- 2022 temporal validation
- 2- and 3-month temporal aggregation windows
- Vegetation index–based planting date estimation
- Additional bioclimatic indices
