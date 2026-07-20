# tests/test_populate_timeseries.py
"""Tests for populate_timeseries._process_date, focused on the
--discard-raster behavior that bounds disk during a full-record backfill."""

import logging
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

import populate_timeseries as pt


def _bands() -> dict:
    df = pd.DataFrame({
        'elev_band_m': [500, 750],
        'mean_swe_mm': [100.0, 150.0],
        'area_km2': [10.0, 10.0],
        'total_swe_volume_km3': [0.001, 0.0015],
    })
    return {'Columbia River Basin': df}


def _run_process_date(tmp_path, discard_raster):
    """Drive _process_date with all I/O mocked; return the fake SWE tif path."""
    swe_tif = tmp_path / '2026' / '01' / '20260115_swe.tif'
    swe_tif.parent.mkdir(parents=True, exist_ok=True)
    swe_tif.write_bytes(b'fake-raster')

    logger = logging.getLogger('test_populate')
    with patch.object(pt, 'load_band_cache', return_value=None), \
         patch.object(pt, 'fetch_swe', return_value=swe_tif), \
         patch.object(pt, 'get_aligned_dem', return_value=tmp_path / 'dem.tif'), \
         patch.object(pt, 'compute_bands', return_value=_bands()['Columbia River Basin']), \
         patch.object(pt, 'save_band_cache'), \
         patch.object(pt, 'append_volumes'):
        huc4 = pd.DataFrame({'name': [], 'geometry': []})
        ok = pt._process_date(
            date(2026, 1, 15), tmp_path, tmp_path / 'dem.tif',
            MagicMock(), huc4, logger, discard_raster=discard_raster,
        )
    return ok, swe_tif


def test_discard_raster_removes_tif(tmp_path):
    ok, swe_tif = _run_process_date(tmp_path, discard_raster=True)
    assert ok is True
    assert not swe_tif.exists()


def test_default_keeps_tif(tmp_path):
    ok, swe_tif = _run_process_date(tmp_path, discard_raster=False)
    assert ok is True
    assert swe_tif.exists()


def test_discard_raster_flag_parsed():
    """--discard-raster is exposed on the CLI and defaults off."""
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--start', default=pt._DEFAULT_START.isoformat())
    parser.add_argument('--discard-raster', action='store_true')
    assert parser.parse_args([]).discard_raster is False
    assert parser.parse_args(['--discard-raster']).discard_raster is True


def test_parse_time_values_days_since_1900():
    from datetime import datetime
    import populate_timeseries

    # Anchor pair verified against a live SWANN file on 2026-07-20:
    # the daily file for 2026-01-15 carries NETCDF_DIM_time = 46035.
    tags = {
        "NETCDF_DIM_time_VALUES": "{46035,46036,46037}",
        "time#units": "days since 1900-01-01 00:00:00",
    }
    dates = populate_timeseries.parse_time_values(tags)
    assert dates[0] == datetime(2026, 1, 15)
    assert dates[2] == datetime(2026, 1, 17)
    assert len(dates) == 3


def test_parse_time_values_rejects_unknown_units():
    import pytest
    import populate_timeseries

    with pytest.raises(ValueError):
        populate_timeseries.parse_time_values(
            {"NETCDF_DIM_time_VALUES": "{1}", "time#units": "hours since 1900-01-01"})


def test_dataset_arg_default_snodas():
    import populate_timeseries
    parser = populate_timeseries.build_parser()
    assert parser.parse_args([]).dataset == "snodas"
    assert parser.parse_args(["--dataset", "swann"]).dataset == "swann"
