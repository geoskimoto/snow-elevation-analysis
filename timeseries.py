"""timeseries.py — SWE volume time series utilities.

Functions
---------
water_year(date)          -- return water-year integer for a datetime
append_volumes(date, bands_by_basin, cache_dir, dataset='snodas')
                          -- sum total_swe_volume_km3 per basin and append to
                             the WY parquet; idempotent on (date, basin).
load_timeseries(wy, cache_dir, dataset='snodas')
                          -- read the WY parquet; return empty DataFrame if
                             the file does not exist.

Dataset routing: 'snodas' uses {cache_dir}/timeseries/WY*.parquet;
other datasets use {cache_dir}/timeseries/{dataset}/WY*.parquet.
"""

from datetime import datetime
from pathlib import Path

import pandas as pd


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_COLUMNS = ['date', 'basin', 'total_swe_volume_km3']


def _parquet_path(wy: int, cache_dir: Path, dataset: str = 'snodas') -> Path:
    # Routing rule shared with climatology/pipeline: the default dataset keeps
    # its historical location; any other dataset gets a subdir named after it.
    base = cache_dir / 'timeseries'
    if dataset != 'snodas':
        base = base / dataset
    return base / f'WY{wy}_volume.parquet'


def _empty_df() -> pd.DataFrame:
    return pd.DataFrame({
        'date': pd.Series([], dtype='datetime64[ns]'),
        'basin': pd.Series([], dtype=str),
        'total_swe_volume_km3': pd.Series([], dtype=float),
    })


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def water_year(date: datetime) -> int:
    """Return the water year (Oct 1 – Sep 30) for *date*.

    Oct 1, 2025 → 2026
    Sep 30, 2025 → 2025
    Jan 15, 2026 → 2026
    """
    if date.month >= 10:
        return date.year + 1
    return date.year


def append_volumes(date: datetime, bands_by_basin: dict[str, pd.DataFrame], cache_dir: Path, dataset: str = 'snodas') -> None:
    """Sum ``total_swe_volume_km3`` per basin and append one row per basin.

    Parameters
    ----------
    date:
        The date the SWE data represents.
    bands_by_basin:
        Mapping of basin name → DataFrame with columns
        ``[elev_band_m, mean_swe_mm, area_km2, total_swe_volume_km3]``.
        Both the HUC2 key (``'Columbia River Basin'``) and HUC4 subbasin
        keys are stored without filtering.
    cache_dir:
        Root cache directory.  The parquet is written to
        ``{cache_dir}/timeseries/WY{wy}_volume.parquet`` for 'snodas',
        or ``{cache_dir}/timeseries/{dataset}/WY{wy}_volume.parquet`` for
        other datasets.
    dataset:
        Dataset key ('snodas' or 'swann'). Default: 'snodas'.

    Idempotency
    -----------
    If a row for *(date, basin)* already exists the row is **not** added
    again.  Existing data is never modified.
    """
    wy = water_year(date)
    path = _parquet_path(wy, cache_dir, dataset)

    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing data (or start fresh)
    if path.exists():
        existing = pd.read_parquet(path)
    else:
        existing = _empty_df()

    ts = pd.Timestamp(date)

    new_rows = []
    for basin_name, df in bands_by_basin.items():
        # Idempotency check: skip if (date, basin) already recorded
        already_exists = (
            len(existing) > 0
            and ((existing['date'] == ts) & (existing['basin'] == basin_name)).any()
        )
        if already_exists:
            continue

        total_volume = float(df['total_swe_volume_km3'].sum())
        new_rows.append({
            'date': ts,
            'basin': basin_name,
            'total_swe_volume_km3': total_volume,
        })

    if not new_rows:
        return  # Nothing to write

    # NOTE: full read-modify-write per call; acceptable for daily frequency but not bulk ingestion
    new_df = pd.DataFrame(new_rows)
    combined = pd.concat([existing, new_df], ignore_index=True)
    combined['date'] = pd.to_datetime(combined['date'])
    combined = combined[_COLUMNS]
    combined.to_parquet(path, index=False)


def load_timeseries(wy: int, cache_dir: Path, dataset: str = 'snodas') -> pd.DataFrame:
    """Read the WY parquet and return a DataFrame sorted by (basin, date).

    Parameters
    ----------
    wy:
        Water year to load.
    cache_dir:
        Root cache directory.
    dataset:
        Dataset key ('snodas' or 'swann'). Default: 'snodas'.

    Returns
    -------
    pd.DataFrame
        Columns: ``date`` (datetime64), ``basin`` (str),
        ``total_swe_volume_km3`` (float), sorted by ``basin`` then ``date``
        so callers can plot rows in array order.
        Returns an empty DataFrame with those columns if the file does not
        exist.
    """
    path = _parquet_path(wy, cache_dir, dataset)
    if not path.exists():
        return _empty_df()

    df = pd.read_parquet(path)
    df['date'] = pd.to_datetime(df['date'])
    # Rows land in the parquet in the order analyses were run, so a backfilled
    # date can trail a later one. Plotly connects points in array order.
    df = df.sort_values(['basin', 'date']).reset_index(drop=True)
    return df[_COLUMNS]
