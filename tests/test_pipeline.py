import pandas as pd
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch
import plotly.graph_objects as go


@pytest.fixture
def sample_bands():
    return pd.DataFrame({
        'elev_band_m': [0, 250, 500],
        'mean_swe_mm': [5.0, 80.0, 200.0],
        'area_km2': [100.0, 200.0, 150.0],
        'total_swe_volume_km3': [0.0005, 0.016, 0.03],
    })


@pytest.fixture
def sample_bands_by_basin(sample_bands):
    return {
        'Columbia River Basin': sample_bands.copy(),
        'Upper Columbia': sample_bands.copy(),
    }


def test_save_and_load_band_cache(tmp_path, sample_bands_by_basin):
    from pipeline import save_band_cache, load_band_cache
    save_band_cache(sample_bands_by_basin, '20240401', tmp_path)
    loaded = load_band_cache('20240401', tmp_path)
    assert set(loaded.keys()) == set(sample_bands_by_basin.keys())
    pd.testing.assert_frame_equal(
        loaded['Columbia River Basin'].reset_index(drop=True),
        sample_bands_by_basin['Columbia River Basin'].reset_index(drop=True),
    )


def test_load_band_cache_returns_none_if_missing(tmp_path):
    from pipeline import load_band_cache
    result = load_band_cache('20240401', tmp_path)
    assert result is None


def test_run_pipeline_returns_figures_on_success(tmp_path, sample_bands_by_basin):
    from pipeline import run_pipeline

    with patch('pipeline.fetch_swe', return_value=Path('swe.tif')), \
         patch('pipeline.load_huc2') as mock_huc2, \
         patch('pipeline.load_huc4') as mock_huc4, \
         patch('pipeline.get_aligned_dem', return_value=Path('dem.tif')), \
         patch('pipeline.compute_bands', return_value=sample_bands_by_basin['Columbia River Basin']), \
         patch('pipeline.plot_hypsometric', return_value=[
             tmp_path / 'snow_hypsometric_huc2_20240401.png',
             tmp_path / 'snow_hypsometric_huc4_20240401.png',
         ]), \
         patch('pipeline.config.get_cache_dir', return_value=tmp_path), \
         patch('pipeline.config.get_output_dir', return_value=tmp_path):

        huc2_gdf = MagicMock()
        huc2_gdf.geometry = [MagicMock()]
        mock_huc2.return_value = huc2_gdf

        huc4_gdf = MagicMock()
        row = MagicMock()
        row.__getitem__ = MagicMock(return_value='Upper Columbia')
        row.geometry = MagicMock()
        huc4_gdf.iterrows.return_value = iter([(0, row)])
        mock_huc4.return_value = huc4_gdf

        result = run_pipeline('2024-04-01')

    assert result['error'] is None
    assert isinstance(result['huc2_fig'], go.Figure)
    assert isinstance(result['huc4_fig'], go.Figure)


def test_run_pipeline_returns_error_on_exception(tmp_path):
    from pipeline import run_pipeline

    with patch('pipeline.fetch_swe', side_effect=RuntimeError('network error')), \
         patch('pipeline.config.get_cache_dir', return_value=tmp_path), \
         patch('pipeline.config.get_output_dir', return_value=tmp_path):
        result = run_pipeline('2024-04-01')

    assert result['error'] == 'network error'


def test_run_pipeline_uses_band_cache_on_second_call(tmp_path, sample_bands_by_basin):
    from pipeline import run_pipeline, save_band_cache

    save_band_cache(sample_bands_by_basin, '20240401', tmp_path)

    with patch('pipeline.fetch_swe', return_value=Path('swe.tif')), \
         patch('pipeline.load_huc2') as mock_huc2, \
         patch('pipeline.load_huc4') as mock_huc4, \
         patch('pipeline.get_aligned_dem', return_value=Path('dem.tif')), \
         patch('pipeline.compute_bands') as mock_compute, \
         patch('pipeline.plot_hypsometric', return_value=[
             tmp_path / 'snow_hypsometric_huc2_20240401.png',
             tmp_path / 'snow_hypsometric_huc4_20240401.png',
         ]), \
         patch('pipeline.config.get_cache_dir', return_value=tmp_path), \
         patch('pipeline.config.get_output_dir', return_value=tmp_path):

        mock_huc2.return_value = MagicMock()
        mock_huc2.return_value.geometry = [MagicMock()]
        mock_huc4.return_value = MagicMock()
        mock_huc4.return_value.iterrows.return_value = iter([])

        run_pipeline('2024-04-01')

    mock_compute.assert_not_called()


def test_run_pipeline_progress_called(tmp_path, sample_bands_by_basin):
    from pipeline import run_pipeline

    progress_calls = []

    def fake_progress(args):
        progress_calls.append(args)

    with patch('pipeline.fetch_swe', return_value=Path('swe.tif')), \
         patch('pipeline.load_huc2') as mock_huc2, \
         patch('pipeline.load_huc4') as mock_huc4, \
         patch('pipeline.get_aligned_dem', return_value=Path('dem.tif')), \
         patch('pipeline.compute_bands', return_value=sample_bands_by_basin['Columbia River Basin']), \
         patch('pipeline.plot_hypsometric', return_value=[
             tmp_path / 'snow_hypsometric_huc2_20240401.png',
             tmp_path / 'snow_hypsometric_huc4_20240401.png',
         ]), \
         patch('pipeline.config.get_cache_dir', return_value=tmp_path), \
         patch('pipeline.config.get_output_dir', return_value=tmp_path):

        huc2_gdf = MagicMock()
        huc2_gdf.geometry = [MagicMock()]
        mock_huc2.return_value = huc2_gdf
        mock_huc4.return_value = MagicMock()
        mock_huc4.return_value.iterrows.return_value = iter([])

        run_pipeline('2024-04-01', set_progress=fake_progress)

    assert len(progress_calls) == 5
    pcts = [c[0] for c in progress_calls]
    assert pcts == sorted(pcts)
    assert pcts[-1] == 100


def test_band_cache_swann_routes_to_subdir(tmp_path):
    import pandas as pd
    from pipeline import save_band_cache, load_band_cache

    bands = {"Columbia River Basin": pd.DataFrame({
        "elev_band_m": [1000], "mean_swe_mm": [100.0],
        "area_km2": [50.0], "total_swe_volume_km3": [0.005],
    })}
    save_band_cache(bands, "20260115", tmp_path, dataset="swann")
    assert (tmp_path / "bands" / "swann" / "20260115_250m.parquet").exists()
    assert not (tmp_path / "bands" / "20260115_250m.parquet").exists()

    loaded = load_band_cache("20260115", tmp_path, dataset="swann")
    assert "Columbia River Basin" in loaded
    assert load_band_cache("20260115", tmp_path) is None  # snodas view empty


def test_run_pipeline_routes_fetcher_by_dataset(tmp_path, monkeypatch):
    """run_pipeline(dataset='swann') must call the SWANN fetcher, not SNODAS."""
    import pipeline
    import datasets

    called = {}

    def fake_swann_fetch(date, cache_dir):
        called["swann"] = True
        raise ConnectionError("stop here — routing verified")

    def fake_snodas_fetch(date, cache_dir):
        called["snodas"] = True
        raise ConnectionError("stop here")

    monkeypatch.setitem(datasets.DATASETS["swann"], "fetch_swe", fake_swann_fetch)
    monkeypatch.setitem(datasets.DATASETS["snodas"], "fetch_swe", fake_snodas_fetch)

    result = pipeline.run_pipeline("2026-01-15", dataset="swann")
    assert called == {"swann": True}
    assert result["error"] is not None
