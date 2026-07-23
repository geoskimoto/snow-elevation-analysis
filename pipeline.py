from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

import config
import datasets
import timeseries
from basin_loader import load_all_basins, transboundary_hucs, dagger
from charts import make_huc2_figure, make_huc4_figure, make_huc2_volume_figure, make_huc4_volume_figure
from dem_processor import get_aligned_dem
from elevation_bands import compute_bands
from plotter import plot_hypsometric
from snodas_fetcher import fetch_swe


def _cache_path(date_key: str, cache_dir: Path, dataset: str = 'snodas') -> Path:
    base = cache_dir / 'bands'
    if dataset != 'snodas':
        base = base / dataset
    return base / f'{date_key}_250m.parquet'


def save_band_cache(bands_by_huc: dict, names: dict, date_key: str,
                    cache_dir: Path, dataset: str = 'snodas') -> None:
    path = _cache_path(date_key, cache_dir, dataset)
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = []
    for huc, df in bands_by_huc.items():
        row = df.copy()
        row.insert(0, 'basin', names[huc])
        row.insert(0, 'huc', huc)
        frames.append(row)
    pd.concat(frames).to_parquet(path, index=False)


def load_band_cache(date_key: str, cache_dir: Path,
                    dataset: str = 'snodas') -> tuple[dict, dict] | None:
    """Return (bands_by_huc, names) or None on miss. Old-schema files
    (pre-HUC6, no 'huc' column) read as a miss so stale basin sets are
    recomputed rather than reused. A corrupt/unreadable cache file (e.g.
    truncated by a kill mid-save_band_cache) also reads as a miss — the
    bad file is deleted so the resume path self-heals instead of wedging
    on the same date every retry."""
    path = _cache_path(date_key, cache_dir, dataset)
    if not path.exists():
        return None
    try:
        df = pd.read_parquet(path)
    except Exception:
        path.unlink(missing_ok=True)
        return None
    if 'huc' not in df.columns:
        return None
    bands_by_huc = {
        huc: group.drop(columns=['huc', 'basin']).reset_index(drop=True)
        for huc, group in df.groupby('huc')
    }
    names = dict(df.groupby('huc')['basin'].first())
    return bands_by_huc, names


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
        # reach through a `ds['fetch_swe']` call.
        fetch_fn = fetch_swe if dataset == 'snodas' else ds['fetch_swe']
        swe_tif = fetch_fn(date, cache_dir=cache_dir)

        _progress(2, 5, 'Loading basin boundaries...')
        basins = load_all_basins()
        names = dict(zip(basins['huc'], basins['name']))

        _progress(3, 5, 'Building/loading DEM...')
        dem_tif = get_aligned_dem(swe_tif, dem_cache=cache_dir / 'dem' / ds['dem_filename'])

        _progress(4, 5, 'Computing elevation bands...')
        cached = load_band_cache(date_key, cache_dir, dataset)
        if cached is None:
            bands_by_huc = {
                row.huc: compute_bands(swe_tif, dem_tif, row.geometry,
                                       min_band_area_km2=100.0)
                for row in basins.itertuples()
            }
            save_band_cache(bands_by_huc, names, date_key, cache_dir, dataset)
        else:
            bands_by_huc, names = cached

        timeseries.append_volumes(date, bands_by_huc, names, cache_dir,
                                  dataset=dataset)

        _progress(5, 5, 'Rendering figures...')
        huc2_df = bands_by_huc.get('17')
        tb = transboundary_hucs()
        huc4_by_name = {dagger(names[h], h, tb): b for h, b in bands_by_huc.items()
                        if len(h) == 4}
        written = plot_hypsometric(
            {'Columbia River Basin': huc2_df, **huc4_by_name}, date, output_dir)
        png_by_stem = {p.stem: p for p in written}

        huc2_fig = make_huc2_figure(huc2_df, date, dataset_label=ds['label']) \
            if huc2_df is not None else go.Figure()
        huc4_fig = make_huc4_figure(huc4_by_name, date, dataset_label=ds['label'])
        huc2_vol_fig = make_huc2_volume_figure(huc2_df, date, dataset_label=ds['label']) \
            if huc2_df is not None else go.Figure()
        huc4_vol_fig = make_huc4_volume_figure(huc4_by_name, date,
                                               dataset_label=ds['label'])

        return {
            'huc2_fig': huc2_fig,
            'huc4_fig': huc4_fig,
            'huc2_vol_fig': huc2_vol_fig,
            'huc4_vol_fig': huc4_vol_fig,
            'huc6_bands': {h: b.to_dict('records')
                           for h, b in bands_by_huc.items() if len(h) == 6},
            'names': names,
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
            'huc6_bands': {},
            'names': {},
            'huc2_png': '',
            'huc4_png': '',
            'error': str(exc),
        }
