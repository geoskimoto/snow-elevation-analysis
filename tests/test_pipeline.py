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


# huc-code -> display name, paired with sample_bands_by_basin's keys for the
# huc-keyed save_band_cache/load_band_cache signature (Task 2).
_HUC_NAMES = {'17': 'Columbia River Basin', '1701': 'Upper Columbia'}


def test_save_and_load_band_cache(tmp_path, sample_bands_by_basin):
    from pipeline import save_band_cache, load_band_cache
    bands_by_huc = {'17': sample_bands_by_basin['Columbia River Basin'],
                    '1701': sample_bands_by_basin['Upper Columbia']}
    save_band_cache(bands_by_huc, _HUC_NAMES, '20240401', tmp_path)
    loaded = load_band_cache('20240401', tmp_path)
    bands_out, names_out = loaded
    assert set(bands_out.keys()) == set(bands_by_huc.keys())
    assert names_out == _HUC_NAMES
    pd.testing.assert_frame_equal(
        bands_out['17'].reset_index(drop=True),
        bands_by_huc['17'].reset_index(drop=True),
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

    bands = {"17": pd.DataFrame({
        "elev_band_m": [1000], "mean_swe_mm": [100.0],
        "area_km2": [50.0], "total_swe_volume_km3": [0.005],
    })}
    save_band_cache(bands, {"17": "Columbia River Basin"}, "20260115", tmp_path, dataset="swann")
    assert (tmp_path / "bands" / "swann" / "20260115_250m.parquet").exists()
    assert not (tmp_path / "bands" / "20260115_250m.parquet").exists()

    loaded = load_band_cache("20260115", tmp_path, dataset="swann")
    bands_out, names_out = loaded
    assert "17" in bands_out
    assert names_out["17"] == "Columbia River Basin"
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


def test_band_cache_roundtrip_huc_schema(tmp_path):
    import pandas as pd
    from pipeline import save_band_cache, load_band_cache

    band = pd.DataFrame({
        "elev_band_m": [1000], "mean_swe_mm": [100.0],
        "area_km2": [50.0], "total_swe_volume_km3": [0.005],
    })
    save_band_cache({"170602": band}, {"170602": "Salmon"}, "20260115", tmp_path)
    out = load_band_cache("20260115", tmp_path)
    assert out is not None
    bands_by_huc, names = out
    assert set(bands_by_huc) == {"170602"}
    assert names["170602"] == "Salmon"
    assert "huc" not in bands_by_huc["170602"].columns  # values are pure band frames


def test_load_band_cache_old_schema_is_cache_miss(tmp_path):
    """Pre-HUC6 caches (basin-keyed, no huc column) must read as None so
    the recompute regenerates them instead of using stale basin sets."""
    import pandas as pd
    from pipeline import load_band_cache

    old = pd.DataFrame({
        "basin": ["Kootenai"], "elev_band_m": [1000], "mean_swe_mm": [100.0],
        "area_km2": [50.0], "total_swe_volume_km3": [0.005],
    })
    path = tmp_path / "bands" / "20260115_250m.parquet"
    path.parent.mkdir(parents=True)
    old.to_parquet(path, index=False)
    assert load_band_cache("20260115", tmp_path) is None
