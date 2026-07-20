from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

import config
import datasets
import timeseries
from basin_loader import load_huc2, load_huc4
from charts import make_huc2_figure, make_huc4_figure, make_huc2_volume_figure, make_huc4_volume_figure
from dem_processor import get_aligned_dem
from elevation_bands import compute_bands
from plotter import plot_hypsometric
from snodas_fetcher import fetch_swe

_HUC2_KEY = 'Columbia River Basin'


def _cache_path(date_key: str, cache_dir: Path, dataset: str = 'snodas') -> Path:
    base = cache_dir / 'bands'
    if dataset != 'snodas':
        base = base / dataset
    return base / f'{date_key}_250m.parquet'


def save_band_cache(bands_by_basin: dict, date_key: str, cache_dir: Path,
                    dataset: str = 'snodas') -> None:
    path = _cache_path(date_key, cache_dir, dataset)
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = []
    for name, df in bands_by_basin.items():
        row = df.copy()
        row.insert(0, 'basin', name)
        frames.append(row)
    pd.concat(frames).to_parquet(path, index=False)


def load_band_cache(date_key: str, cache_dir: Path,
                    dataset: str = 'snodas') -> dict | None:
    path = _cache_path(date_key, cache_dir, dataset)
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    return {
        name: group.drop(columns='basin').reset_index(drop=True)
        for name, group in df.groupby('basin')
    }


def run_pipeline(date_str: str, set_progress=None, dataset: str = 'snodas') -> dict:
    """Run full pipeline. Returns dict with huc2_fig, huc4_fig, huc2_png, huc4_png, error."""

    def _progress(step: int, total: int, msg: str) -> None:
        if set_progress:
            set_progress((int(step / total * 100), msg))

    try:
        ds = datasets.get(dataset)
        date = datetime.strptime(date_str, '%Y-%m-%d')
        date_key = date.strftime('%Y%m%d')
        cache_dir = config.get_cache_dir()
        output_dir = config.get_output_dir()
        if dataset != 'snodas':
            output_dir = output_dir / dataset   # PNG stems collide otherwise

        _progress(1, 5, f'Fetching {ds["label"]} data...')
        # NOTE: 'snodas' routes through the module-level `fetch_swe` name (not
        # ds['fetch_swe']) so that tests/test_pipeline.py's pre-existing
        # `patch('pipeline.fetch_swe', ...)` mocks keep working unmodified —
        # patching a dict value bound in datasets.py at import time wouldn't
        # reach through a `ds['fetch_swe']` call. See task-3-report.md.
        fetch_fn = fetch_swe if dataset == 'snodas' else ds['fetch_swe']
        swe_tif = fetch_fn(date, cache_dir=cache_dir)

        _progress(2, 5, 'Loading basin boundaries...')
        huc2 = load_huc2()
        huc4 = load_huc4()

        _progress(3, 5, 'Building/loading DEM...')
        dem_tif = get_aligned_dem(swe_tif, dem_cache=cache_dir / 'dem' / ds['dem_filename'])

        _progress(4, 5, 'Computing elevation bands...')
        cached = load_band_cache(date_key, cache_dir, dataset)
        if cached is None:
            bands_by_basin: dict = {
                _HUC2_KEY: compute_bands(swe_tif, dem_tif, huc2.geometry[0],
                                         min_band_area_km2=100.0)
            }
            for _, row in huc4.iterrows():
                bands_by_basin[row['name']] = compute_bands(
                    swe_tif, dem_tif, row.geometry, min_band_area_km2=100.0
                )
            save_band_cache(bands_by_basin, date_key, cache_dir, dataset)
        else:
            bands_by_basin = cached

        timeseries.append_volumes(date, bands_by_basin, cache_dir, dataset=dataset)

        _progress(5, 5, 'Rendering figures...')
        written = plot_hypsometric(bands_by_basin, date, output_dir)
        png_by_stem = {p.stem: p for p in written}

        huc4_bands = {k: v for k, v in bands_by_basin.items() if k != _HUC2_KEY}
        huc2_df = bands_by_basin.get(_HUC2_KEY)
        huc2_fig = make_huc2_figure(huc2_df, date) if huc2_df is not None else go.Figure()
        huc4_fig = make_huc4_figure(huc4_bands, date)
        huc2_vol_fig = make_huc2_volume_figure(huc2_df, date) if huc2_df is not None else go.Figure()
        huc4_vol_fig = make_huc4_volume_figure(huc4_bands, date)

        return {
            'huc2_fig': huc2_fig,
            'huc4_fig': huc4_fig,
            'huc2_vol_fig': huc2_vol_fig,
            'huc4_vol_fig': huc4_vol_fig,
            'huc2_png': str(png_by_stem.get(f'snow_hypsometric_huc2_{date_key}', '')),
            'huc4_png': str(png_by_stem.get(f'snow_hypsometric_huc4_{date_key}', '')),
            'error': None,
        }

    except Exception as exc:
        return {
            'huc2_fig': go.Figure(),
            'huc4_fig': go.Figure(),
            'huc2_vol_fig': go.Figure(),
            'huc4_vol_fig': go.Figure(),
            'huc2_png': '',
            'huc4_png': '',
            'error': str(exc),
        }
