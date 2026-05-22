"""
Time-series KMeans clustering of observation points by climate weather patterns.

Reads a symptom-frequency raster and a multi-temporal weather cube, extracts
weather time series at observation locations, scales them, and clusters using
tslearn's TimeSeriesKMeans.

Usage
-----
python -m src.processing.data_clustering
"""

import geopandas as gpd
import rioxarray as rio
import xarray

from tslearn.clustering import TimeSeriesKMeans
from tslearn.preprocessing import TimeSeriesScalerMeanVariance


def cluster_by_weather(settings: dict) -> None:
    """
    Cluster observation points based on their weather time series.

    Parameters
    ----------
    settings : dict
        paths : dict
            data_points : str  – path to symptom-frequency raster (GeoTIFF)
            data_raster : str  – path to multi-temporal weather NetCDF
        weather_variables : list of str
            Variable names to include in the clustering feature vector.
        clustering : dict
            n_clusters, random_state, njobs, metric

    Saves a CSV with cluster labels to outputs/model_outputs/.
    """
    paths = settings['paths']

    freq_symptoms = rio.open_rasterio(paths['data_points'])
    weather_data  = xarray.open_dataset(paths['data_raster'])

    # Observation coordinates with valid symptom data
    coords = (
        freq_symptoms.to_dataframe(name='symptoms_freq')
        .reset_index()
        .dropna(subset=['symptoms_freq'])
    )

    x_da = xarray.DataArray(coords.x.values, dims='points')
    y_da = xarray.DataArray(coords.y.values, dims='points')

    # Extract and reshape: (n_points, n_timesteps, n_variables)
    wdata = weather_data[settings['weather_variables']].to_array()
    ts = (
        wdata.sel(x=x_da, y=y_da)
        .dropna('points')
        .transpose('points', 'date', 'variable')
        .values
    )

    print(f"Time series shape: {ts.shape}")

    scaler = TimeSeriesScalerMeanVariance(mu=0.0, std=1.0)
    ts_scaled = scaler.fit_transform(ts)

    clust_cfg = settings['clustering']
    model = TimeSeriesKMeans(
        n_clusters=clust_cfg['n_clusters'],
        metric=clust_cfg['metric'],
        max_iter=200,
        n_jobs=clust_cfg['njobs'],
        random_state=clust_cfg['random_state'],
        verbose=1,
    )
    model.fit(ts_scaled)
    labels = model.predict(ts_scaled)

    coords['cluster'] = labels

    raster_tag = paths['data_raster'][-12:-3]
    out_path = (
        f"outputs/model_outputs/cluster_labels_nclusters{clust_cfg['n_clusters']}"
        f"_metric_{clust_cfg['metric']}_{raster_tag}.csv"
    )
    coords.to_csv(out_path, index=False)
    print(f"Labels saved → {out_path}")


if __name__ == '__main__':
    settings = {
        'paths': {
            'data_points': 'outputs/model_outputs/visual_symptoms_2014.tif',
            'data_raster': 'outputs/climate_data/weather_southeastasia_2013_2014.nc',
        },
        'weather_variables': ['precipitation', 'tmin', 'tmax', 'hrmin', 'hrmax', 'srad'],
        'clustering': {
            'n_clusters': 20,
            'random_state': 42,
            'njobs': 6,
            'metric': 'euclidean',
        },
    }
    cluster_by_weather(settings)
