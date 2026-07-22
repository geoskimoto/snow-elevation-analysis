"""timeseries.py — SWE volume time series utilities.

Functions
---------
water_year(date)          -- return water-year integer for a datetime
append_volumes(date, bands_by_huc, names, cache_dir, dataset='snodas', ts_dir=None)
                          -- sum total_swe_volume_km3 per huc and append to
                             the WY parquet; idempotent on (date, huc).
load_timeseries(wy, cache_dir, dataset='snodas', ts_dir=None)
                          -- read the WY parquet; return empty DataFrame if
                             the file does not exist.

Dataset routing: 'snodas' uses {cache_dir}/timeseries/WY*.parquet;
other datasets use {cache_dir}/timeseries/{dataset}/WY*.parquet. Passing
ts_dir overrides the parquet directory entirely (used by the staged
rebuild), bypassing the cache_dir/dataset routing above.
"""

from datetime import datetime
from pathlib import Path

import pandas as pd


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_COLUMNS = ['date', 'huc', 'basin', 'total_swe_volume_km3']


def _empty_df() -> pd.DataFrame:
    return pd.DataFrame({
        'date': pd.Series([], dtype='datetime64[ns]'),
        'huc': pd.Series([], dtype=str),
        'basin': pd.Series([], dtype=str),
        'total_swe_volume_km3': pd.Series([], dtype=float),
    })


def _parquet_path(wy: int, cache_dir: Path, dataset: str = 'snodas',
                  ts_dir: Path | None = None) -> Path:
    # Routing rule shared with climatology/pipeline: the default dataset keeps
    # its historical location; any other dataset gets a subdir named after it.
    # ts_dir (when given) overrides this entirely -- used by the staged rebuild.
    if ts_dir is not None:
        return Path(ts_dir) / f'WY{wy}_volume.parquet'
    base = cache_dir / 'timeseries'
    if dataset != 'snodas':
        base = base / dataset
    return base / f'WY{wy}_volume.parquet'


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


def append_volumes(date: datetime, bands_by_huc: dict[str, pd.DataFrame],
                   names: dict[str, str], cache_dir: Path,
                   dataset: str = 'snodas', ts_dir: Path | None = None) -> None:
    """Sum total_swe_volume_km3 per basin and append one row per huc code.

    bands_by_huc maps WBD huc code -> band DataFrame; names maps huc code ->
    display name (codes are the unique key: display names collide across
    HUC levels). Idempotent on (date, huc). ts_dir overrides the output
    directory (used by the staged rebuild); default routing is unchanged.
    """
    wy = water_year(date)
    path = _parquet_path(wy, cache_dir, dataset, ts_dir)
    path.parent.mkdir(parents=True, exist_ok=True)

    existing = pd.read_parquet(path) if path.exists() else _empty_df()
    ts = pd.Timestamp(date)

    new_rows = []
    for huc, df in bands_by_huc.items():
        already = (
            len(existing) > 0
            and ((existing['date'] == ts) & (existing['huc'] == huc)).any()
        )
        if already:
            continue
        new_rows.append({
            'date': ts,
            'huc': huc,
            'basin': names[huc],
            'total_swe_volume_km3': float(df['total_swe_volume_km3'].sum()),
        })

    if not new_rows:
        return
    combined = pd.concat([existing, pd.DataFrame(new_rows)], ignore_index=True)
    combined['date'] = pd.to_datetime(combined['date'])
    combined[_COLUMNS].to_parquet(path, index=False)


def load_timeseries(wy: int, cache_dir: Path, dataset: str = 'snodas',
                    ts_dir: Path | None = None) -> pd.DataFrame:
    """Read the WY parquet; columns [date, huc, basin, total_swe_volume_km3]
    sorted by (huc, date). Empty DataFrame with those columns if absent."""
    path = _parquet_path(wy, cache_dir, dataset, ts_dir)
    if not path.exists():
        return _empty_df()
    df = pd.read_parquet(path)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values(['huc', 'date']).reset_index(drop=True)
    return df[_COLUMNS]
