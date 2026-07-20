"""climatology.py — Cross-water-year SWE climatology.

Where :mod:`timeseries` handles a single water year, this module aggregates
*all* committed WY volume parquets into a day-of-water-year climatology: the
per-day percentile envelope (min/10/25/median/75/90/max) that the Historical
tab draws with the current water year overlaid on top.

Everything here is a pure read of the committed parquet snapshots — no SNODAS
fetch, no cache writes — so it behaves identically on the scheduled server
and on Posit Connect (which cannot run jobs). Dataset routing: 'snodas' reads
{cache_dir}/timeseries/WY*.parquet; other datasets read
{cache_dir}/timeseries/{dataset}/WY*.parquet.

Functions
---------
load_all_water_years(cache_dir, dataset='snodas')
                          -- concat every WY parquet in the dataset subdir,
                             tagging rows with `wy`.
day_of_water_year(date)   -- 1..365 position within the water year
                             (Oct 1 -> 1); Feb 29 returns None so leap and
                             non-leap years align on a common (month, day) axis.
water_day_ref(dow)        -- map a day-of-water-year onto a fixed reference
                             calendar so the x-axis renders as Oct -> Sep.
compute_climatology(df, basin, current_wy)
                          -- per-day percentile envelope over all years except
                             `current_wy`.
current_series(df, basin, current_wy)
                          -- the current water year's line, day-of-WY indexed.
n_historical_years(df, basin, current_wy)
                          -- count of prior water years available for `basin`.
summarize_current(df, basin, current_wy)
                          -- latest-day headline stats (% of median, rank).
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_HUC2_KEY = 'Columbia River Basin'

# Minimum prior water years needed before a percentile envelope is meaningful.
MIN_YEARS_FOR_ENVELOPE = 3

_COLUMNS = ['date', 'basin', 'total_swe_volume_km3', 'wy']

_WY_FILE_RE = re.compile(r'WY(\d{4})_volume\.parquet$')

# Water year runs Oct -> Sep. Feb is treated as always 28 days so that every
# calendar year maps onto the same 365-slot axis; Feb 29 is dropped upstream.
_DAYS_IN_MONTH = {10: 31, 11: 30, 12: 31, 1: 31, 2: 28, 3: 31,
                  4: 30, 5: 31, 6: 30, 7: 31, 8: 31, 9: 30}
_WATER_MONTH_ORDER = [10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8, 9]


def _dow_month_starts() -> dict[int, int]:
    """Map month -> day-of-water-year of that month's first day (Oct 1 -> 1)."""
    starts, running = {}, 1
    for month in _WATER_MONTH_ORDER:
        starts[month] = running
        running += _DAYS_IN_MONTH[month]
    return starts


_DOW_MONTH_START = _dow_month_starts()

# Fixed non-leap water year used only to render the x-axis with month ticks.
_REF_WY_START = date(2022, 10, 1)  # WY2023 is non-leap


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _empty_df() -> pd.DataFrame:
    return pd.DataFrame({
        'date': pd.Series([], dtype='datetime64[ns]'),
        'basin': pd.Series([], dtype=str),
        'total_swe_volume_km3': pd.Series([], dtype=float),
        'wy': pd.Series([], dtype='int64'),
    })


def _empty_climatology() -> pd.DataFrame:
    cols = ['dow', 'ref_date', 'min', 'p10', 'p25', 'p50', 'p75', 'p90', 'max', 'n']
    return pd.DataFrame({c: pd.Series([], dtype=float) for c in cols})


def _with_dow(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with `dow`/`ref_date` columns, Feb 29 rows dropped."""
    out = df.copy()
    out['dow'] = out['date'].apply(day_of_water_year)
    out = out[out['dow'].notna()].copy()
    out['dow'] = out['dow'].astype(int)
    out['ref_date'] = out['dow'].apply(water_day_ref)
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def day_of_water_year(d) -> int | None:
    """Return the 1-based day-of-water-year (Oct 1 -> 1, Sep 30 -> 365).

    Feb 29 returns ``None`` so that leap and non-leap years align on a common
    ``(month, day)`` axis; callers drop those rows from the climatology.
    """
    if isinstance(d, (pd.Timestamp, datetime)):
        month, day = d.month, d.day
    else:  # datetime.date
        month, day = d.month, d.day
    if month == 2 and day == 29:
        return None
    return _DOW_MONTH_START[month] + day - 1


def water_day_ref(dow: int) -> pd.Timestamp:
    """Map a day-of-water-year (1..365) onto a fixed reference calendar date.

    Used purely for plotting so the x-axis shows Oct -> Sep month ticks rather
    than raw integers.
    """
    return pd.Timestamp(_REF_WY_START + timedelta(days=int(dow) - 1))


def load_all_water_years(cache_dir: Path, dataset: str = 'snodas') -> pd.DataFrame:
    """Concatenate every ``WY*_volume.parquet`` under *cache_dir*.

    Parameters
    ----------
    cache_dir:
        Root cache directory.
    dataset:
        Dataset key ('snodas' or 'swann'). Default: 'snodas'.
        Routing rule: 'snodas' reads {cache_dir}/timeseries/WY*.parquet;
        other datasets read {cache_dir}/timeseries/{dataset}/WY*.parquet.

    Returns
    -------
    pd.DataFrame
        Columns ``date, basin, total_swe_volume_km3, wy``. Empty (with those
        columns) if no parquet files exist.
    """
    ts_dir = Path(cache_dir) / 'timeseries'
    if dataset != 'snodas':
        ts_dir = ts_dir / dataset
    if not ts_dir.exists():
        return _empty_df()

    frames = []
    for path in sorted(ts_dir.glob('WY*_volume.parquet')):
        m = _WY_FILE_RE.search(path.name)
        if not m:
            continue
        df = pd.read_parquet(path)
        df['date'] = pd.to_datetime(df['date'])
        df['wy'] = int(m.group(1))
        frames.append(df[['date', 'basin', 'total_swe_volume_km3', 'wy']])

    if not frames:
        return _empty_df()

    combined = pd.concat(frames, ignore_index=True)
    return combined[_COLUMNS]


def n_historical_years(df: pd.DataFrame, basin: str, current_wy: int) -> int:
    """Count water years (excluding *current_wy*) that have data for *basin*."""
    if df.empty:
        return 0
    hist = df[(df['basin'] == basin) & (df['wy'] != current_wy)]
    return int(hist['wy'].nunique())


def compute_climatology(df: pd.DataFrame, basin: str, current_wy: int) -> pd.DataFrame:
    """Per-day percentile envelope over all water years except *current_wy*.

    Returns
    -------
    pd.DataFrame
        Columns ``dow, ref_date, min, p10, p25, p50, p75, p90, max, n`` sorted
        by ``dow``. Empty if *basin* has no historical data.
    """
    if df.empty:
        return _empty_climatology()

    hist = df[(df['basin'] == basin) & (df['wy'] != current_wy)]
    if hist.empty:
        return _empty_climatology()

    hist = _with_dow(hist)
    grouped = hist.groupby('dow')['total_swe_volume_km3']
    clim = pd.DataFrame({
        'min': grouped.min(),
        'p10': grouped.quantile(0.10),
        'p25': grouped.quantile(0.25),
        'p50': grouped.quantile(0.50),
        'p75': grouped.quantile(0.75),
        'p90': grouped.quantile(0.90),
        'max': grouped.max(),
        'n': grouped.count(),
    }).reset_index()
    clim['ref_date'] = clim['dow'].apply(water_day_ref)
    clim = clim.sort_values('dow').reset_index(drop=True)
    return clim[['dow', 'ref_date', 'min', 'p10', 'p25', 'p50', 'p75', 'p90', 'max', 'n']]


def current_series(df: pd.DataFrame, basin: str, current_wy: int) -> pd.DataFrame:
    """Return *current_wy*'s line for *basin*, day-of-water-year indexed.

    Columns ``dow, ref_date, date, total_swe_volume_km3`` sorted by ``dow``.
    """
    cols = ['dow', 'ref_date', 'date', 'total_swe_volume_km3']
    if df.empty:
        return pd.DataFrame({c: pd.Series([], dtype='float64') for c in cols})

    cur = df[(df['basin'] == basin) & (df['wy'] == current_wy)]
    if cur.empty:
        return pd.DataFrame({c: pd.Series([], dtype='float64') for c in cols})

    cur = _with_dow(cur).sort_values('dow').reset_index(drop=True)
    return cur[cols]


def summarize_current(df: pd.DataFrame, basin: str, current_wy: int) -> dict | None:
    """Headline stats for *basin*'s most recent current-year day.

    Returns a dict with ``as_of`` (Timestamp), ``current_km3``, ``median_km3``,
    ``pct_of_median``, ``rank_from_bottom`` and ``total_years`` (historical +
    current). Returns ``None`` when there is no current data or no historical
    data at the latest day-of-water-year.
    """
    cur = current_series(df, basin, current_wy)
    if cur.empty:
        return None

    latest = cur.iloc[-1]
    dow = int(latest['dow'])
    current_val = float(latest['total_swe_volume_km3'])

    hist = df[(df['basin'] == basin) & (df['wy'] != current_wy)]
    if hist.empty:
        return None
    hist = _with_dow(hist)
    at_day = hist[hist['dow'] == dow]['total_swe_volume_km3']
    if at_day.empty:
        return None

    median_val = float(at_day.median())
    rank_from_bottom = int((at_day < current_val).sum()) + 1
    return {
        'as_of': pd.Timestamp(latest['date']),
        'current_km3': current_val,
        'median_km3': median_val,
        'pct_of_median': (current_val / median_val * 100.0) if median_val else float('nan'),
        'rank_from_bottom': rank_from_bottom,
        'total_years': int(at_day.shape[0]) + 1,
    }
