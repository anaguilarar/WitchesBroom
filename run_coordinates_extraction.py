"""Quick pipeline smoke-test — run from the WitchesBroom root."""
import sys, os
from datetime import timedelta, datetime
import pandas as pd
from tqdm import tqdm
import xarray
from pathlib import Path
import argparse
import geopandas as gpd

from src.utils.spatial_utils import process_temporal_windows, extracting_using_gpdf
from src.config.loader import load_config

def convert_column_2dateformat(column_date, format="%Y%m%d"):

    if not pd.api.types.is_string_dtype(column_date):
        column_date = column_date.astype(str)

    return pd.to_datetime(column_date, format=format, errors='coerce')

def climate_units(xrdataset):
    # Convert temperature from Kelvin to Celsius
    xrdataset['tmax'] = xrdataset['tmax'] - 273.15 if xrdataset['tmax'].mean().values> 100 else xrdataset['tmax']
    xrdataset['tmin'] = xrdataset['tmin'] - 273.15 if xrdataset['tmin'].mean().values> 100 else xrdataset['tmin']
    xrdataset['dpt'] = xrdataset['dpt'] - 273.15 if xrdataset['dpt'].mean().values> 100 else xrdataset['dpt']
    xrdataset['vpd'] = xrdataset['vpd'] * 0.1 if float(xrdataset['vpd'].max()) > 10 else xrdataset['vpd']

    return xrdataset


def main(config_path: str):

    print("--- Import configuration file ---")
    cfg = load_config(config_path)
    print(f"""  [OK] loaded config with {len(cfg.climate_config.summarizations)} 
                     summarizations and {len(cfg.climate_config.indices)} indices""")

    print("\n--- Load climate data cube ---")
    climate_data = xarray.open_dataset(cfg.climate_config.climate_data_path)
    climate_data = climate_units(climate_data)
    climate_data['tmean'] = (climate_data['tmax'] + climate_data['tmin']) / 2
    dailyhr = climate_data[[f'rh{i}' for i in ['06','09','12','15','18']]].to_array(dim='hour').mean(dim='hour')
    climate_data['dailyhr'] = dailyhr
    print(f"  [OK] loaded climate cube with dimensions: {dict(climate_data.dims)}")

    print("\n--- Load observation points ---")
    gdf = gpd.read_parquet(cfg.data_summarization.field_data_source)
    gdf['year'] = gdf.reset_index()[cfg.data_summarization.column_ending_date].astype(str).str[:4].astype(int)
    if cfg.general_info.year_oi is not None:
        gdf = gdf.loc[gdf.year == cfg.general_info.year_oi]

    print(f"  [OK] loaded {len(gdf)} observation points with columns: {gdf.columns.tolist()}")

    gp_date = convert_column_2dateformat(gdf[cfg.data_summarization.column_ending_date])
    seasonality = int(cfg.data_summarization.temporal_window) if cfg.data_summarization.temporal_window is not None else 6 
    lookback = int(cfg.data_summarization.nmonths_lookback) if cfg.data_summarization.nmonths_lookback is not None else 6 
    print("\n--- Computing summaries & indices per window ---")
    extracted_dfs = []
    for eval_date in tqdm(gp_date.unique()):
        merged_windows = process_temporal_windows(
            xrdata=climate_data,
            climate_config=cfg.climate_config,
            eval_date=eval_date,
            window_months=seasonality,
            lookback_months= None if lookback == 0 else lookback)
        
        obs_subset  = gdf.loc[gdf[cfg.data_summarization.column_ending_date].astype(str) == pd.Timestamp(eval_date).strftime('%Y%m%d')].copy()
        if obs_subset.empty:
            print(f"  (no observations for {eval_date.date()}, skipping)")
            continue

        extracted = extracting_using_gpdf(obs_subset, merged_windows)
        extracted_dfs.append(extracted)
    
    final_df = pd.concat(extracted_dfs, ignore_index=True)
    print(f"\n  [OK] final extracted DataFrame shape: {final_df.shape}")
    print(f"  Columns: {final_df.columns.tolist()}")    
    ## export 
    cfg.general_info.output_path.mkdir(parents=True, exist_ok=True)
    output_path = cfg.general_info.output_path / cfg.data_summarization.output_filename
    final_df.to_csv(output_path, index=False)

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description=__doc__)
    ## read config path using sys.argv or default to the provided YAML
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args()
    config_path = args.config if args.config else "options/climate_summary_sea_2014.yaml"
    print(f"Using config file: {config_path}")
    
    main(config_path)
