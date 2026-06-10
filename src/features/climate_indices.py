"""
Climate indices for Witches' Broom disease modelling.

Functions here compute threshold-based and spell-length indicators from
xarray Datasets produced by the climate data pipeline.  The expected
time dimension is named 'time'.

Usage example
-------------
from src.features.climate_indices import calculate_indices

indices_dict = {
    "vpd_lt_20":            ['vpd', 1.5],
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
    return mask.sum(dim='date')


def multiple_threshold_days(xrclimatedata, values, op_symbols, meteorological_var):
    """Count days satisfying multiple simultaneous threshold conditions."""
    xrclimatedata = set_variable_units(xrclimatedata, meteorological_var)
    mask = xarray.ones_like(xrclimatedata)
    op_symbols = list(op_symbols) if not isinstance(op_symbols, list) else op_symbols
    values = list(values) if not isinstance(values, list) else values
    for op, v in zip(op_symbols, values):
        mask = mask * mask_operation(xrclimatedata, op, v, xrclimatedata.attrs['units'])
    return mask.sum(dim='date')


def consecutive_days(xrclimatedata, value, meteorological_var, op='>='):
    """Longest run of consecutive days satisfying the threshold condition."""
    xrclimatedata = set_variable_units(xrclimatedata, meteorological_var)
    mask = mask_operation(xrclimatedata, op, value, xrclimatedata.attrs['units'])
    return run_length.longest_run(mask, dim='date')


def get_avg_spell_length(precip_1d, threshold=1.0, window=5,
                         cond_op='>=', window_op='>='):
    """
    Average length of spells (runs) exceeding *window* days.
    Returns 0.0 instead of np.nan if no spells are found.
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
    return np.mean(valid) if len(valid) > 0 else 0.0


def _compute_cwd_1d(hr06, hr09, hr12, hr15, hr18, threshold=85.0):
    """
    Estimate mean canopy wetness duration (hours/day) from 5 daily RH observations.

    Linearly interpolates between fixed-time RH values (06, 09, 12, 15, 18 h) and
    across the nighttime gap (18 h today → 06 h next day) to approximate a
    continuous 24-hour RH curve, then integrates hours at or above *threshold*.

    The tmin < tmax condition (normal diurnal temperature gradient) is implicitly
    satisfied whenever the five RH observations show realistic diurnal variation;
    no additional filter is applied.

    Parameters
    ----------
    hr06, hr09, hr12, hr15, hr18 : 1-D numpy arrays, length n_days
        Relative humidity (%) at each observation hour.
    threshold : float
        RH threshold (%) above which canopy is considered wet.

    Returns
    -------
    float
        Mean hours per day with RH >= threshold over the window.
    """
    n = len(hr06)
    if n == 0:
        return 0.0

    OBS_TIMES  = [6, 9, 12, 15, 18]
    obs_arrays = [hr06, hr09, hr12, hr15, hr18]

    def _wet_hours_segment(rh_a, rh_b, dt):
        if rh_a >= threshold and rh_b >= threshold:
            return float(dt)
        if rh_a < threshold and rh_b < threshold:
            return 0.0
        f = (threshold - rh_a) / (rh_b - rh_a)   # crossing fraction [0, 1]
        return (f * dt) if rh_a >= threshold else ((1.0 - f) * dt)

    total_wet = 0.0
    for i in range(n):
        day_wet = 0.0

        # daytime: four 3-hour intervals (06→09, 09→12, 12→15, 15→18)
        for j in range(len(OBS_TIMES) - 1):
            dt = OBS_TIMES[j + 1] - OBS_TIMES[j]
            day_wet += _wet_hours_segment(obs_arrays[j][i], obs_arrays[j + 1][i], dt)

        # nighttime: 18:00 → 06:00 next day (12-hour gap)
        rh_end = hr06[i + 1] if i + 1 < n else hr06[i]
        day_wet += _wet_hours_segment(hr18[i], rh_end, 12)

        total_wet += day_wet

    return total_wet / n


def _compute_cmf_1d(tmin, threshold=15.0, window=10, aggregation='mean'):
    """
    Cool Night Minimum Frequency (CMF) — count of nights below *threshold* per
    rolling *window*-day sub-period, then aggregated across the seasonal window.

    Uses a cumulative-sum rolling approach (O(n)) to count threshold exceedances
    in every *window*-day stretch, then returns the mean or maximum such count.

    Parameters
    ----------
    tmin        : 1-D numpy array — daily minimum temperature (°C)
    threshold   : float — cool-night temperature ceiling (default 15 °C)
    window      : int   — rolling sub-period length in days (default 10)
    aggregation : str   — 'mean' (average exposure) or 'max' (peak suppression)

    Returns
    -------
    float
        Mean or max number of cool nights per *window*-day sub-period.
        Interpretation: 7.5 with window=10 means on average 7-8 nights per
        10-day stretch were below *threshold*.
    """
    n = len(tmin)
    if n == 0:
        return 0.0

    cool = (tmin < threshold).astype(float)

    if n < window:
        # Fewer days than one full window: return raw count
        return float(np.sum(cool))

    # Rolling sum via cumsum: rolling[i] = sum of cool[i : i+window]
    cumsum  = np.concatenate([[0.0], np.cumsum(cool)])
    rolling = cumsum[window:] - cumsum[:-window]   # length: n - window + 1

    return float(np.mean(rolling)) if aggregation == 'mean' else float(np.max(rolling))


def _spatial_template(da):
    """
    Return a spatial DataArray (date dimension collapsed) for use as a
    zeros/NaN template.  Safe when the date dimension is empty (size 0).
    """
    if da.sizes.get('date', 0) > 0:
        return da.isel(date=0, drop=True)
    return da.mean(dim='date')   # returns NaN-filled spatial array when empty


def calculate_indices(xrdata, climate_indices):
    """
    Compute a set of climate indices from a meteorological xarray Dataset.
    """
    out = {}
    idx_map = {idx.name: idx for idx in climate_indices}

    # Track the total number of valid days in this specific slice
    total_days = len(xrdata.date)

    if "vpd_lt_20" in idx_map:
        idx = idx_map["vpd_lt_20"]
        var = idx.meteorological_variables[0]
        thresh = idx.parameters.get("threshold", 1.5) if idx.parameters else 1.5
        
        if total_days > 0:
            out["vpd_lt_20"] = (
                threshold_days(xrdata[var], thresh, meteorological_var='vpd', op='<=')
                / total_days
            ) * 100
        else:
            out["vpd_lt_20"] = xarray.full_like(_spatial_template(xrdata[var]), np.nan)

    if "n_vpd_spells" in idx_map:
        idx = idx_map["n_vpd_spells"]
        var = idx.meteorological_variables[0]
        params = idx.parameters or {}
        thresh = params.get("threshold", 1.5)
        window = params.get("min_duration_days", 7)
        
        # Guard 1: Ensure array length meets minimum spell window requirements
        if total_days >= window:
            is_humid = xrdata[var] <= thresh
            out["n_vpd_spells"] = run_length.windowed_run_events(
                is_humid, window=window, dim='date'
            )
        else:
            out["n_vpd_spells"] = xarray.zeros_like(_spatial_template(xrdata[var]), dtype=float)

    if "n_wet_spells" in idx_map:
        idx = idx_map["n_wet_spells"]
        var = idx.meteorological_variables[0]
        params = idx.parameters or {}
        thresh = params.get("thresh", 1.0)
        min_duration = params.get("min_duration_days", 7)
        
        # Guard 2: Protect against ZeroDivisionError
        if total_days >= min_duration:
            out["n_wet_spells"] = run_length.windowed_run_events(
                xrdata[var] >= thresh, window=min_duration, dim='date'
            )
        else:
            out["n_wet_spells"] = xarray.zeros_like(_spatial_template(xrdata[var]), dtype=float)

    if "n_dry_spells" in idx_map:
        idx = idx_map["n_dry_spells"]
        var = idx.meteorological_variables[0]
        params = idx.parameters or {}
        thresh = params.get("thresh", 1.0)
        min_duration = params.get("min_duration_days", 7)
        
        # Guard 3: Protect against ZeroDivisionError
        if total_days >= min_duration:
            out["n_dry_spells"] = run_length.windowed_run_events(
                xrdata[var] < thresh, window=min_duration, dim='date'
            )
        else:
            out["n_dry_spells"] = xarray.zeros_like(_spatial_template(xrdata[var]), dtype=float)
    
    if "heat_wave_duration" in idx_map:
        idx = idx_map["heat_wave_duration"]
        var = idx.meteorological_variables[0]
        params = idx.parameters or {}
        thresh = params.get("thresh", 28.0)
        min_duration_days = params.get("min_duration_days", 5)
        
        if total_days >= min_duration_days:
            out["heat_wave_duration"] = xarray.apply_ufunc(
                get_avg_spell_length,
                xrdata[var],
                kwargs={'threshold': thresh, 'window': min_duration_days,
                        'cond_op': '>=', 'window_op': '>='},
                input_core_dims=[['date']],
                output_core_dims=[[]],
                vectorize=True,
                dask='allowed',
                output_dtypes=[float],
            )
        else:
            # Ensures 0.0 is passed up if the temporal slice is completely empty
            out["heat_wave_duration"] = xarray.zeros_like(_spatial_template(xrdata[var]), dtype=float)

    if "cold_wave_duration" in idx_map:
        idx = idx_map["cold_wave_duration"]
        var = idx.meteorological_variables[0]
        params = idx.parameters or {}
        thresh = params.get("thresh", 5.0)
        min_duration_days = params.get("min_duration_days", 5)
        
        if total_days >= min_duration_days:
            out["cold_wave_duration"] = xarray.apply_ufunc(
                get_avg_spell_length,
                xrdata[var],
                kwargs={'threshold': thresh, 'window': min_duration_days,
                        'cond_op': '<=', 'window_op': '>='},
                input_core_dims=[['date']],
                output_core_dims=[[]],
                vectorize=True,
                dask='allowed',
                output_dtypes=[float],
            )
        else:
            out["cold_wave_duration"] = xarray.zeros_like(_spatial_template(xrdata[var]), dtype=float)

    if "avg_wet_spell_duration" in idx_map:
        idx = idx_map["avg_wet_spell_duration"]
        var = idx.meteorological_variables[0]
        params = idx.parameters or {}
        thresh = params.get("thresh", 1.0)
        min_duration = params.get("min_duration_days", 7)
        
        if total_days >= min_duration:
            out["avg_wet_spell_duration"] = xarray.apply_ufunc(
                get_avg_spell_length,
                xrdata[var],
                kwargs={'threshold': thresh, 'window': min_duration,
                        'cond_op': '>=', 'window_op': '>='},
                input_core_dims=[['date']],
                output_core_dims=[[]],
                vectorize=True,
                dask='allowed',
                output_dtypes=[float],
            )
        else:
            out["avg_wet_spell_duration"] = xarray.zeros_like(_spatial_template(xrdata[var]), dtype=float)

    if "avg_dry_spell_duration" in idx_map:
        idx = idx_map["avg_dry_spell_duration"]
        var = idx.meteorological_variables[0]
        params = idx.parameters or {}
        thresh = params.get("thresh", 1.0)
        window = params.get("min_duration_days", 7)
        
        if total_days >= window:
            out["avg_dry_spell_duration"] = xarray.apply_ufunc(
                get_avg_spell_length,
                xrdata[var],
                kwargs={'threshold': thresh, 'window': window,
                        'cond_op': '<', 'window_op': '>='},
                input_core_dims=[['date']],
                output_core_dims=[[]],
                vectorize=True,
                dask='allowed',
                output_dtypes=[float],
            )
        else:
            out["avg_dry_spell_duration"] = xarray.zeros_like(_spatial_template(xrdata[var]), dtype=float)
    
    if "rh_85_90_days" in idx_map:
        idx = idx_map["rh_85_90_days"]
        var_names = idx.meteorological_variables
        params = idx.parameters or {}
        thresholds = params.get("thresholds", [85, 90])
        op_symbols = params.get("op_symbols", [">=", "<="])
        
        for var in var_names:
            out[f'{var}_85_90_days'] = multiple_threshold_days(
                xrdata[var], values=thresholds,
                op_symbols=op_symbols, meteorological_var='hr'
            )

    if "tmean_25_30_days" in idx_map:
        idx = idx_map["tmean_25_30_days"]
        var = idx.meteorological_variables[0]
        params = idx.parameters or {}
        thresholds = params.get("thresholds", [25, 30])
        op_symbols = params.get("op_symbols", [">=", "<="])
        
        out["tmean_25_30_days"] = multiple_threshold_days(
            xrdata[var], values=thresholds,
            op_symbols=op_symbols, meteorological_var='hr'
        )

    if "max_temp_days" in idx_map:
        idx = idx_map["max_temp_days"]
        var = idx.meteorological_variables[0]
        thresh = idx.parameters.get("threshold_celsius", 35.0) if idx.parameters else 35.0
        
        out["max_temp_days"] = threshold_days(
            xrdata[var], thresh, meteorological_var='temp', op='>='
        )

    rhoptions = ["hr", "hr06", "hr09", "hr12", "hr15", "hr18"]
    for option in rhoptions:
        option_name = f"max_{option}_days"
        if option_name in idx_map:
            idx = idx_map[option_name]
            var = idx.meteorological_variables[0]
            thresh = idx.parameters.get("thresh", 80.0) if idx.parameters else 80.0
            
            out[option_name] = threshold_days(
                xrdata[var], thresh, meteorological_var='hr', op='>='
            )

    if "precip_max_15d" in idx_map:
        idx = idx_map["precip_max_15d"]
        var = idx.meteorological_variables[0]
        if total_days >= 15:
            out["precip_max_15d"] = xrdata[var].rolling(date=15).sum().max(dim='date')
        else:
            out["precip_max_15d"] = xarray.zeros_like(_spatial_template(xrdata[var]), dtype=float)

    if "consecutive_dry_days" in idx_map:
        idx = idx_map["consecutive_dry_days"]
        var = idx.meteorological_variables[0]
        thresh = idx.parameters.get("thresh", 1.0) if idx.parameters else 1.0
        
        if total_days > 0:
            out["consecutive_dry_days"] = consecutive_days(
                xrdata[var], value=thresh, meteorological_var='prec', op='<'
            )
        else:
            out["consecutive_dry_days"] = xarray.zeros_like(_spatial_template(xrdata[var]), dtype=float)

    if "growing_degree_days" in idx_map:
        idx = idx_map["growing_degree_days"]
        var = idx.meteorological_variables[0]
        tbase = idx.parameters.get("base_temperature", 15.0) if idx.parameters else 15.0
        
        out["growing_degree_days"] = (xrdata[var] - tbase).sum(
            dim='date', keep_attrs=True
        )

    if "daily_intensity_index" in idx_map:
        idx = idx_map["daily_intensity_index"]
        var = idx.meteorological_variables[0]
        thresh = idx.parameters.get("thresh", 1.0) if idx.parameters else 1.0
        
        out["daily_intensity_index"] = xrdata[var].where(
            xrdata[var] >= thresh
        ).mean(dim='date', keep_attrs=True)

    if "canopy_wetness_duration" in idx_map:
        idx = idx_map["canopy_wetness_duration"]
        vars_ = idx.meteorological_variables   # expected: [hr06, hr09, hr12, hr15, hr18]
        params = idx.parameters or {}
        rh_thresh = params.get("rh_threshold", 85.0)

        rh_vars_present = all(v in xrdata for v in vars_)
        if total_days > 0 and rh_vars_present:
            out["canopy_wetness_duration"] = xarray.apply_ufunc(
                _compute_cwd_1d,
                *[xrdata[v] for v in vars_],
                kwargs={'threshold': rh_thresh},
                input_core_dims=[['date']] * len(vars_),
                output_core_dims=[[]],
                vectorize=True,
                dask='allowed',
                output_dtypes=[float],
            )
        else:
            ref_var = vars_[0] if vars_ else list(xrdata.data_vars)[0]
            out["canopy_wetness_duration"] = xarray.zeros_like(
                _spatial_template(xrdata[ref_var]), dtype=float
            )

    if "cool_night_frequency" in idx_map:
        idx  = idx_map["cool_night_frequency"]
        var  = idx.meteorological_variables[0]
        params      = idx.parameters or {}
        thr         = params.get("threshold", 15.0)
        win         = int(params.get("window", 10))
        agg         = params.get("aggregation", "mean")

        if total_days > 0:
            out["cool_night_frequency"] = xarray.apply_ufunc(
                _compute_cmf_1d,
                xrdata[var],
                kwargs={'threshold': thr, 'window': win, 'aggregation': agg},
                input_core_dims=[['date']],
                output_core_dims=[[]],
                vectorize=True,
                dask='allowed',
                output_dtypes=[float],
            )
        else:
            out["cool_night_frequency"] = xarray.zeros_like(
                _spatial_template(xrdata[var]), dtype=float
            )

    if "disease_pressure_index" in idx_map:
        idx = idx_map["disease_pressure_index"]
        vpd_var = idx.meteorological_variables[0]
        
        if "max_hr_days" in out and "daily_intensity_index" in out:
            rh_norm  = normalize(out["max_hr_days"])
            pi_norm  = normalize(out["daily_intensity_index"])
            vpd_norm = normalize(xrdata[vpd_var].mean(dim='date', keep_attrs=True))
            out["disease_pressure_index"] = (
                (rh_norm * pi_norm) / vpd_norm
            ).clip(min=0, max=1)

    # Clean up single-variable nested sub-datasets safely
    for key, value in out.items():
        if isinstance(value, xarray.Dataset):
            inner = list(value.data_vars)[0]
            out[key] = value[inner]

    return xarray.Dataset(out)