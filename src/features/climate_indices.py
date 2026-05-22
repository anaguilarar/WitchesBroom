"""
Climate indices for Witches' Broom disease modelling.

Functions here compute threshold-based and spell-length indicators from
xarray Datasets produced by the climate data pipeline.  The expected
time dimension is named 'time'.

Usage example
-------------
from src.features.climate_indices import calculate_indices

indices_dict = {
    "vpd_lt_15":            ['vpd', 1.5],
    "n_vpd_spells":         ['vpd', 1.5, 7],
    "n_wet_spells":         ['precipitation', 1.0, 7],
    "n_dry_spells":         ['precipitation', 1.0, 7],
    "avg_wet_spell_duration": ['precipitation', 1.0, 7],
    "avg_dry_spell_duration": ['precipitation', 1.0, 7],
    "rh_85_90_days":        [['dailyhr','hr06','hr09','hr12','hr15','hr18'], [85, 90], ['>=','<=']],
    "tmean_25_30_days":     ['tmean', [25, 30], ['>=','<=']],
    "max_temp_days":        ['tmax', 32],
    "precip_max_15d":       ['precipitation'],
    "max_hr_days":          ['dailyhr', 80],
    "consecutive_dry_days": ['precipitation', 1.0],
    "growing_degree_days":  ['tmean', 15],
    "daily_intensity_index":['precipitation', 1.0],
    "disease_pressure_index": ['vpd'],
}

indices_ds = calculate_indices(ds, indices_dict)
"""

import operator
import numpy as np
import xarray
import xclim
from xclim.indices import run_length


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def normalize(da):
    """Min-max normalisation to [0, 1]."""
    return (da - da.min()) / (da.max() - da.min())


def set_variable_units(xrdata, variable):
    """Attach CF-compliant unit string to a DataArray's attrs."""
    unit_map = {
        'temp': 'degC',
        'hr':   '%',
        'prec': 'mm/d',
        'vpd':  'kPa',
    }
    xrdata.attrs['units'] = unit_map[variable]
    return xrdata


def mask_operation(xrdata, op, value, unit):
    """Return a boolean mask after unit-aware comparison via xclim."""
    ops = {
        '>':  operator.gt,
        '<':  operator.lt,
        '>=': operator.ge,
        '<=': operator.le,
        '==': operator.eq,
    }
    thresh = xclim.core.units.convert_units_to(f"{value} {unit}", xrdata)
    return ops[op](xrdata, thresh)


def threshold_days(xrclimatedata, value, meteorological_var, op='>='):
    """Count days where *xrclimatedata* satisfies *op* against *value*."""
    xrclimatedata = set_variable_units(xrclimatedata, meteorological_var)
    mask = mask_operation(xrclimatedata, op, value, xrclimatedata.attrs['units'])
    return mask.sum(dim='time')


def multiple_threshold_days(xrclimatedata, values, op_symbols, meteorological_var):
    """Count days satisfying multiple simultaneous threshold conditions."""
    xrclimatedata = set_variable_units(xrclimatedata, meteorological_var)
    mask = xarray.ones_like(xrclimatedata)
    op_symbols = list(op_symbols) if not isinstance(op_symbols, list) else op_symbols
    values = list(values) if not isinstance(values, list) else values
    for op, v in zip(op_symbols, values):
        mask = mask * mask_operation(xrclimatedata, op, v, xrclimatedata.attrs['units'])
    return mask.sum(dim='time')


def consecutive_days(xrclimatedata, value, meteorological_var, op='>='):
    """Longest run of consecutive days satisfying the threshold condition."""
    xrclimatedata = set_variable_units(xrclimatedata, meteorological_var)
    mask = mask_operation(xrclimatedata, op, value, xrclimatedata.attrs['units'])
    return run_length.longest_run(mask, dim='time')


def get_avg_spell_length(precip_1d, threshold=1.0, window=5,
                         cond_op='>=', window_op='>='):
    """
    Average length of spells (runs) exceeding *window* days.

    Parameters
    ----------
    precip_1d : array-like
        1-D time series (typically precipitation or a boolean mask).
    threshold : float
        Value compared against *precip_1d* using *cond_op*.
    window : int
        Minimum spell length to include in the average.
    cond_op : str
        Comparison operator for the per-day condition.
    window_op : str
        Comparison operator applied to the run length vs *window*.
    """
    ops = {
        '>':  operator.gt,
        '<':  operator.lt,
        '>=': operator.ge,
        '<=': operator.le,
        '==': operator.eq,
    }
    mask = ops[cond_op](precip_1d, threshold)
    padded = np.pad(mask, (1, 1), mode='constant', constant_values=False)
    diffs = np.diff(padded.astype(int))
    starts = np.where(diffs == 1)[0]
    ends   = np.where(diffs == -1)[0]
    lengths = ends - starts
    valid = lengths[ops[window_op](lengths, window)]
    return np.mean(valid) if len(valid) > 0 else np.nan


# ---------------------------------------------------------------------------
# Main index computation
# ---------------------------------------------------------------------------

def calculate_indices(xrdata, climate_indices):
    """
    Compute a set of climate indices from a meteorological xarray Dataset.

    Parameters
    ----------
    xrdata : xarray.Dataset
        Must have a 'time' dimension.  Expected variables depend on the
        requested indices (see module docstring for full list).
    climate_indices : dict
        Mapping of index name → parameter list.  Recognised keys:

        vpd_lt_15, n_vpd_spells, n_wet_spells, n_dry_spells,
        avg_wet_spell_duration, avg_dry_spell_duration,
        rh_85_90_days, tmean_25_30_days, max_temp_days, max_hr_days,
        precip_max_15d, consecutive_dry_days, growing_degree_days,
        daily_intensity_index, disease_pressure_index

    Returns
    -------
    xarray.Dataset
        One variable per requested index.
    """
    out = {}

    if "vpd_lt_15" in climate_indices:
        var, thresh = climate_indices["vpd_lt_15"]
        out["vpd_lt_15"] = (
            threshold_days(xrdata[var], thresh, meteorological_var='vpd', op='<=')
            / len(xrdata.time)
        ) * 100

    if "n_vpd_spells" in climate_indices:
        var, thresh, window = climate_indices["n_vpd_spells"]
        is_humid = xrdata[var] <= thresh
        out["n_vpd_spells"] = run_length.windowed_run_events(
            is_humid, window=window, dim='time'
        )

    if "n_wet_spells" in climate_indices:
        var, thresh, window = climate_indices["n_wet_spells"]
        out["n_wet_spells"] = run_length.windowed_run_events(
            xrdata[var] >= thresh, window=window, dim='time'
        )

    if "n_dry_spells" in climate_indices:
        var, thresh, window = climate_indices["n_dry_spells"]
        out["n_dry_spells"] = run_length.windowed_run_events(
            xrdata[var] < thresh, window=window, dim='time'
        )

    if "avg_wet_spell_duration" in climate_indices:
        var, thresh, window = climate_indices["avg_wet_spell_duration"]
        out["avg_wet_spell_duration"] = xarray.apply_ufunc(
            get_avg_spell_length,
            xrdata[var],
            kwargs={'threshold': thresh, 'window': window,
                    'cond_op': '>=', 'window_op': '>='},
            input_core_dims=[['time']],
            output_core_dims=[[]],
            vectorize=True,
            dask='allowed',
            output_dtypes=[float],
        )

    if "avg_dry_spell_duration" in climate_indices:
        var, thresh, window = climate_indices["avg_dry_spell_duration"]
        out["avg_dry_spell_duration"] = xarray.apply_ufunc(
            get_avg_spell_length,
            xrdata[var],
            kwargs={'threshold': thresh, 'window': window,
                    'cond_op': '<', 'window_op': '>='},
            input_core_dims=[['time']],
            output_core_dims=[[]],
            vectorize=True,
            dask='allowed',
            output_dtypes=[float],
        )

    if "rh_85_90_days" in climate_indices:
        var_names, thresholds, op_symbols = climate_indices["rh_85_90_days"]
        if isinstance(var_names, list):
            for var in var_names:
                out[f'{var}_85_90_days'] = multiple_threshold_days(
                    xrdata[var], values=thresholds,
                    op_symbols=op_symbols, meteorological_var='hr'
                )

    if "tmean_25_30_days" in climate_indices:
        var, thresholds, op_symbols = climate_indices["tmean_25_30_days"]
        out["tmean_25_30_days"] = multiple_threshold_days(
            xrdata[var], values=thresholds,
            op_symbols=op_symbols, meteorological_var='hr'
        )

    if "max_temp_days" in climate_indices:
        var, thresh = climate_indices["max_temp_days"]
        out["max_temp_days"] = threshold_days(
            xrdata[var], thresh, meteorological_var='temp', op='>='
        )

    if "max_hr_days" in climate_indices:
        var, thresh = climate_indices["max_hr_days"]
        out["max_hr_days"] = threshold_days(
            xrdata[var], thresh, meteorological_var='hr', op='>='
        )

    if "precip_max_15d" in climate_indices:
        var = climate_indices["precip_max_15d"]
        out["precip_max_15d"] = xrdata[var].rolling(time=15).sum().max(dim='time')

    if "consecutive_dry_days" in climate_indices:
        var, thresh = climate_indices["consecutive_dry_days"]
        out["consecutive_dry_days"] = consecutive_days(
            xrdata[var], value=thresh, meteorological_var='prec', op='<'
        )

    if "growing_degree_days" in climate_indices:
        var, tbase = climate_indices["growing_degree_days"]
        out["growing_degree_days"] = (xrdata[var] - tbase).sum(
            dim='time', keep_attrs=True
        )

    if "daily_intensity_index" in climate_indices:
        var, thresh = climate_indices["daily_intensity_index"]
        out["daily_intensity_index"] = xrdata[var].where(
            xrdata[var] >= thresh
        ).mean(dim='time', keep_attrs=True)

    if "disease_pressure_index" in climate_indices:
        vpd_var = climate_indices["disease_pressure_index"]
        if "max_hr_days" in out and "daily_intensity_index" in out:
            rh_norm  = normalize(out["max_hr_days"])
            pi_norm  = normalize(out["daily_intensity_index"])
            vpd_norm = normalize(xrdata[vpd_var].mean(dim='time', keep_attrs=True))
            out["disease_pressure_index"] = (
                (rh_norm * pi_norm) / vpd_norm
            ).clip(min=0, max=1)

    # Unwrap single-variable Datasets that xclim may return
    for key, value in out.items():
        if isinstance(value, xarray.Dataset):
            inner = list(value.data_vars)[0]
            out[key] = value[inner]

    return xarray.Dataset(out)
