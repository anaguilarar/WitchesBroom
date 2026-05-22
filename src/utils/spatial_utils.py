"""Spatial extraction and raster utilities."""

import pandas as pd
import xarray


def extracting_using_gpdf(gpdf, xrdata):
    """
    Extract xarray values at point locations defined by a GeoDataFrame.

    Nearest-neighbor lookup in x/y.  Returns a DataFrame with the
    original GeoDataFrame columns joined to the extracted climate values.
    """
    x_coords = xarray.DataArray(gpdf.geometry.x, dims='z')
    y_coords = xarray.DataArray(gpdf.geometry.y, dims='z')
    extracted = xrdata.sel(x=x_coords, y=y_coords, method='nearest')
    df_extracted = extracted.to_dataframe().reset_index(drop=True)
    return pd.concat([gpdf.reset_index(drop=True), df_extracted], axis=1)
