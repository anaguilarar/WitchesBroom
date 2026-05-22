"""
Meteorological summary statistics for Witches' Broom disease modelling.

Computes mean and accumulated statistics over a time window from an
xarray Dataset.  Also adds 6 monthly diurnal temperature difference
bands when requested.

Usage example
-------------
from src.features.met_summaries import calculate_meteorological_summaries

variables_dict = {
    "temp_accum":     ['tmean'],
    "hr_accum":       ['dailyhr'],
    "hr06_accum":     ['hr06'],
    "hr09_accum":     ['hr09'],
    "hr12_accum":     ['hr12'],
    "hr15_accum":     ['hr15'],
    "hr18_accum":     ['hr18'],
    "dewtemp_accum":  ['dpt'],
    "vpd_accum":      ['vpd'],
    "etr_accum":      ['etr'],
    "srad_accum":     ['srad'],
    "prec_accum":     ['precipitation'],
    "dtd_monthly":    ['tmax', 'tmin'],   # optional: 6 monthly bins
}

summary_ds = calculate_meteorological_summaries(ds, variables_dict)
"""

import numpy as np
import pandas as pd
import xarray


def calculate_meteorological_summaries(xrdata, summaries_config):
    """
    Compute per-pixel mean and accumulated statistics over the time window.

    Parameters
    ----------
    xrdata : xarray.Dataset
        Requires a 'time' dimension.
    summaries_config : dict
        Keys follow the pattern ``<name>_avg`` (time-mean) or
        ``<name>_accum`` (time-sum).  The value is a list with the
        variable name(s) from *xrdata*.

        Special key ``dtd_monthly`` expects ``[tmax_var, tmin_var]`` and
        produces six monthly diurnal temperature difference bands
        (``dtd_m1`` … ``dtd_m6``).

    Returns
    -------
    xarray.Dataset
    """
    summaries = {}

    for k, v in summaries_config.items():
        if k == "dtd_monthly":
            continue
        var_name = v[0] if isinstance(v, list) else v

        if '_avg' in k:
            summaries[k] = xrdata[var_name].mean(dim='time', keep_attrs=True)
        elif '_accum' in k:
            summaries[k] = xrdata[var_name].sum(dim='time', keep_attrs=True)

    # Unwrap single-variable Datasets returned by some xarray operations
    for key, value in summaries.items():
        if isinstance(value, xarray.Dataset):
            inner = list(value.data_vars)[0]
            summaries[key] = value[inner]

    summaries_ds = xarray.Dataset(summaries)

    if "dtd_monthly" in summaries_config:
        var_tmax, var_tmin = summaries_config["dtd_monthly"]

        collection_date = pd.to_datetime(xrdata.time.values.max())
        range_days = pd.Index(xrdata.time.values) - pd.to_datetime(collection_date)
        partial_monthlydates = np.arange(-180, 1, 30)

        dtd = xrdata[var_tmax] + xrdata[var_tmin]
        dtd = dtd.assign_coords(monthly=('time', range_days.days))
        dtd_monthly = dtd.groupby_bins('monthly', bins=partial_monthlydates).mean()
        dtd_monthly.coords['monthly_bins'] = [
            f"dtd_m{i+1}" for i in range(len(dtd_monthly.monthly_bins))
        ]
        dtd_vars_ds = dtd_monthly.to_dataset(dim='monthly_bins')
        summaries_ds = xarray.merge([summaries_ds, dtd_vars_ds])

    return summaries_ds
