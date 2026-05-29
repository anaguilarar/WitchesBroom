"""Plotting utilities for climate indices and disease data."""

import math
import matplotlib.pyplot as plt


def plot_facet_grid(xrdata, ncols=3, figsize=None):
    """
    Grid of spatial maps, one panel per variable in *xrdata*.

    Parameters
    ----------
    xrdata : xarray.Dataset
    ncols : int
    figsize : tuple, optional
    """
    variables = list(xrdata.data_vars)
    n_vars = len(variables)
    nrows = math.ceil(n_vars / ncols)
    if figsize is None:
        figsize = (ncols * 5, nrows * 4)

    fig, axes = plt.subplots(nrows, ncols, figsize=figsize)
    axes = axes.flatten()

    for i, var_name in enumerate(variables):
        ax = axes[i]
        xrdata[var_name].plot(
            ax=ax,
            robust=True,
            cmap='YlGnBu',
            cbar_kwargs={'label': getattr(xrdata[var_name], 'units', var_name)},
        )
        ax.set_title(var_name.upper())
        ax.axis('off')

    for j in range(i + 1, len(axes)):
        axes[j].set_visible(False)

    plt.tight_layout()
    plt.show()


def plot_facet_grid_with_points(xr_ds, points_gdf=None, ncols=3, figsize=(15, 12)):
    """
    Grid of spatial maps with optional disease observation points overlaid.

    Parameters
    ----------
    xr_ds : xarray.Dataset
    points_gdf : geopandas.GeoDataFrame, optional
        Observation locations drawn as red dots.
    ncols : int
    figsize : tuple
    """
    variables = list(xr_ds.data_vars)
    variables.remove('spatial_ref') if 'spatial_ref' in variables else None
    n_vars = len(variables)
    nrows = math.ceil(n_vars / ncols)

    fig, axes = plt.subplots(nrows, ncols, figsize=figsize)
    axes = axes.flatten()

    for i, var_name in enumerate(variables):
        
        ax = axes[i]
        xr_ds[var_name].plot(
            ax=ax,
            robust=True,
            cmap='YlGnBu',
            cbar_kwargs={'label': getattr(xr_ds[var_name], 'units', '')},
        )
        if points_gdf is not None:
            points_gdf.plot(
                ax=ax,
                color='red',
                markersize=15,
                edgecolor='black',
                linewidth=0.5,
                alpha=0.8,
            )
        ax.set_title(var_name.upper())
        ax.set_xlabel('Longitude')
        ax.set_ylabel('Latitude')

    for j in range(i + 1, len(axes)):
        axes[j].set_visible(False)

    plt.tight_layout()
    plt.show()
