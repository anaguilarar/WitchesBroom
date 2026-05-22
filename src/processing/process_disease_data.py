"""
Disease observation data processing.

Steps
-----
1. Read raw CSV files (CWBD2.csv, CWBD_PHL.csv).
2. Convert to GeoDataFrame with point geometry.
3. Compute visual symptom frequency per unique location.
4. Create a raster of mean symptom frequency aligned to the climate grid.
5. Integrate new-country data (Philippines 2024).
6. Create train / validation temporal splits.

Usage
-----
python -m src.processing.process_disease_data
"""

import os
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import xarray
from shapely.geometry import box


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def read_csv_data(file_path: str) -> pd.DataFrame:
    return pd.read_csv(file_path)


def from_tabular_to_geospatial(df: pd.DataFrame, x_col: str, y_col: str,
                                crs: str = 'EPSG:4326') -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df[x_col], df[y_col]),
        crs=crs,
    )


# ---------------------------------------------------------------------------
# Unique-coordinate derivation
# ---------------------------------------------------------------------------

def create_unique_coordinates(gpdf: gpd.GeoDataFrame, output_dir: str) -> gpd.GeoDataFrame:
    """
    Derive unique observation locations and compute disease symptom frequency.

    Reprojects to ESRI:54052 (equal-area), deduplicates points, and
    calculates the proportion of 'P' (positive) symptom records per location.

    Saves the result as a Shapefile.
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    gs = gpdf.to_crs('ESRI:54052').copy()
    gs['year'] = gs['collection_date_YYYYMMDD'].apply(lambda x: int(str(x)[:4]))
    gs['unique_coordinates'] = gs.apply(
        lambda r: f"{r['longitude']}_{r['latitude']}", axis=1
    )

    gs_unique = gs.drop_duplicates(subset=['unique_coordinates']).copy()
    gs_unique['visual_symptom_frequency'] = 0.0

    for coord, subset in gs_unique.groupby('unique_coordinates'):
        all_obs = gs.loc[gs['unique_coordinates'] == coord,
                         ['collection_date_YYYYMMDD', 'visual_symptom']]
        positive = all_obs.loc[all_obs['visual_symptom'] == 'P']
        freq = (len(positive) / len(all_obs)) * 100
        gs_unique.loc[subset.index, 'visual_symptom_frequency'] = freq

    out_path = os.path.join(output_dir, 'spatial_data_unique.shp')
    gs_unique.to_file(out_path, driver='ESRI Shapefile')
    print(f"Saved unique coordinates → {out_path}")
    return gs_unique


# ---------------------------------------------------------------------------
# Symptom raster creation
# ---------------------------------------------------------------------------

def create_symptoms_raster(gpdf: gpd.GeoDataFrame, climate_data: xarray.Dataset,
                            output_dir: str, year: int = 2014) -> None:
    """
    Rasterise mean symptom frequency onto the climate grid for *year*.

    Saves a GeoTIFF to *output_dir*/visual_symptoms_{year}.tif.
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    gpdf = gpdf.copy()
    gpdf['year'] = gpdf['collection'].astype(str).str[:4].astype(int)
    gpdf = gpdf.loc[gpdf.year == year].to_crs(climate_data.rio.crs)

    da = climate_data.precipitation.isel(date=0)
    transform = climate_data.rio.transform()
    ny, nx = da.shape

    # Build a vector grid aligned to the raster pixels
    polygons, ids = [], []
    for row in range(ny):
        for col in range(nx):
            x_left, y_top    = transform * (col,     row)
            x_right, y_bottom = transform * (col + 1, row + 1)
            polygons.append(box(x_left, y_bottom, x_right, y_top))
            ids.append(row * nx + col)

    grid = gpd.GeoDataFrame({'cell_id': ids}, geometry=polygons, crs=climate_data.rio.crs)
    joined = gpd.sjoin(gpdf, grid, predicate='within')
    cell_mean = joined.groupby('cell_id')['visual_s_1'].mean()

    result = np.full(ny * nx, np.nan)
    result[cell_mean.index] = cell_mean.values
    result = result.reshape((ny, nx))

    mean_da = xarray.DataArray(result, coords=da.coords, dims=da.dims)
    mean_da.rio.write_crs(climate_data.rio.crs, inplace=True)

    out_path = os.path.join(output_dir, f'visual_symptoms_{year}.tif')
    mean_da.rio.to_raster(out_path)
    print(f"Saved symptom raster → {out_path}")


# ---------------------------------------------------------------------------
# Dataset integration
# ---------------------------------------------------------------------------

def integrate_new_country(main_data_path: str, new_data_path: str,
                           output_path: str) -> pd.DataFrame:
    """Concatenate a new country CSV into the main dataset."""
    df_main = pd.read_csv(main_data_path)
    df_new  = pd.read_csv(new_data_path)
    combined = pd.concat([df_main, df_new], ignore_index=True)
    combined.to_csv(output_path, index=False)
    print(f"Combined data saved → {output_path}")
    return combined


# ---------------------------------------------------------------------------
# Train / validation split
# ---------------------------------------------------------------------------

def create_temporal_split(data_path: str, validation_year: int = 2022,
                           output_dir: str = 'data/processed') -> None:
    """
    Split observations into training and validation sets by year.

    The *validation_year* rows are isolated; all other years form the
    training set.  Both CSVs are saved to *output_dir*.
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(data_path)
    df['year'] = pd.to_datetime(
        df['collection_date'], format='%Y%m%d', errors='coerce'
    ).dt.year

    val   = df.loc[df['year'] == validation_year]
    train = df.loc[df['year'] != validation_year]

    val.to_csv(os.path.join(output_dir, f'wb_validation_{validation_year}.csv'), index=False)
    train.to_csv(os.path.join(output_dir, f'wb_train_exclude_{validation_year}.csv'), index=False)

    print(f"Validation ({validation_year}): {len(val)} rows")
    print(f"Training:                       {len(train)} rows")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    RAW_DIR       = 'data/raw'
    PROCESSED_DIR = 'data/processed'
    SPATIAL_DIR   = 'outputs/spatial_data'
    CLIMATE_NC    = 'outputs/climate_data/weather_southeastasia_2013_2014.nc'

    # Step 1 – unique observation coordinates
    df = read_csv_data(os.path.join(RAW_DIR, 'CWBD2.csv'))
    gdf = from_tabular_to_geospatial(df, 'longitude', 'latitude')
    create_unique_coordinates(gdf, SPATIAL_DIR)

    # Step 2 – symptom raster aligned to climate grid
    climate_data = xarray.open_dataset(CLIMATE_NC)
    data_points  = gpd.read_file(os.path.join(SPATIAL_DIR, 'spatial_data_unique.shp'))
    create_symptoms_raster(data_points, climate_data, 'outputs/model_outputs')

    # Step 3 – integrate Philippines 2024 data
    integrate_new_country(
        main_data_path=os.path.join(RAW_DIR, 'CWBD2.csv'),
        new_data_path=os.path.join(RAW_DIR, 'CWBD_PHL.csv'),
        output_path=os.path.join(PROCESSED_DIR, 'cassava_wb_merged_all.csv'),
    )

    # Step 4 – temporal split (2022 validation)
    create_temporal_split(
        data_path=os.path.join(PROCESSED_DIR, 'cassava_wb_merged_all.csv'),
        validation_year=2022,
        output_dir=PROCESSED_DIR,
    )
