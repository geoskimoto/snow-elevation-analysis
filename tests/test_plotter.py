# tests/test_plotter.py
import pytest
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path
import matplotlib
matplotlib.use('Agg')  # non-interactive backend for tests
import plotter


@pytest.fixture
def sample_bands():
    """Minimal bands DataFrames for two basins."""
    huc2_df = pd.DataFrame({
        'elev_band_m': [0, 250, 500, 750, 1000],
        'mean_swe_mm': [0.0, 50.0, 150.0, 300.0, 400.0],
        'area_km2': [5000.0] * 5,
        'total_swe_volume_km3': [0.0, 0.25, 0.75, 1.5, 2.0],
    })
    sub_df = pd.DataFrame({
        'elev_band_m': [250, 500, 750],
        'mean_swe_mm': [30.0, 120.0, 280.0],
        'area_km2': [1000.0] * 3,
        'total_swe_volume_km3': [0.03, 0.12, 0.28],
    })
    return {
        'Columbia River Basin': huc2_df,
        'Upper Columbia': sub_df,
        'Yakima': sub_df.copy(),
    }


def test_plot_hypsometric_returns_list_of_paths(tmp_path, sample_bands):
    date = datetime(2024, 4, 1)
    result = plotter.plot_hypsometric(sample_bands, date, tmp_path)
    assert isinstance(result, list)
    assert len(result) == 2


def test_plot_hypsometric_files_exist(tmp_path, sample_bands):
    date = datetime(2024, 4, 1)
    paths = plotter.plot_hypsometric(sample_bands, date, tmp_path)
    for p in paths:
        assert Path(p).exists()


def test_plot_hypsometric_huc2_filename(tmp_path, sample_bands):
    date = datetime(2024, 4, 1)
    paths = plotter.plot_hypsometric(sample_bands, date, tmp_path)
    names = [Path(p).name for p in paths]
    assert 'snow_hypsometric_huc2_20240401.png' in names


def test_plot_hypsometric_huc4_filename(tmp_path, sample_bands):
    date = datetime(2024, 4, 1)
    paths = plotter.plot_hypsometric(sample_bands, date, tmp_path)
    names = [Path(p).name for p in paths]
    assert 'snow_hypsometric_huc4_20240401.png' in names


def test_plot_hypsometric_png_files_are_nonzero(tmp_path, sample_bands):
    date = datetime(2024, 4, 1)
    paths = plotter.plot_hypsometric(sample_bands, date, tmp_path)
    for p in paths:
        assert Path(p).stat().st_size > 1000  # at least 1 KB


def test_plot_hypsometric_creates_output_dir(tmp_path, sample_bands):
    date = datetime(2024, 4, 1)
    subdir = tmp_path / "new_subdir"
    plotter.plot_hypsometric(sample_bands, date, subdir)
    assert subdir.exists()


def test_plot_hypsometric_only_huc2_when_no_subbasins(tmp_path):
    date = datetime(2024, 4, 1)
    only_huc2 = {
        'Columbia River Basin': pd.DataFrame({
            'elev_band_m': [0, 250, 500],
            'mean_swe_mm': [0.0, 100.0, 200.0],
            'area_km2': [1000.0] * 3,
            'total_swe_volume_km3': [0.0, 0.1, 0.2],
        })
    }
    paths = plotter.plot_hypsometric(only_huc2, date, tmp_path)
    assert len(paths) == 1
    assert 'huc2' in Path(paths[0]).name
