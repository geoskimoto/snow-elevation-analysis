# tests/test_populate_timeseries.py
"""Tests for populate_timeseries._process_date, focused on the
--discard-raster behavior that bounds disk during a full-record backfill."""

import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import populate_timeseries as pt
from timeseries import append_volumes


def _bands() -> dict:
    df = pd.DataFrame({
        'elev_band_m': [500, 750],
        'mean_swe_mm': [100.0, 150.0],
        'area_km2': [10.0, 10.0],
        'total_swe_volume_km3': [0.001, 0.0015],
    })
    return {'Columbia River Basin': df}


def _basins_names():
    """Minimal 1-basin frame for the SWANN-backfill tests below.

    These tests exercise the download-skip / mismatch-cleanup / corrupt-file
    paths of _run_swann_backfill, none of which ever reach basins.geometry
    (they bail out, or _swann_process_day is mocked out, before that). A
    single fake huc keeps the n_basins completeness threshold equivalent to
    the pre-migration `1 + len(huc4)` with an empty huc4 frame, without
    needing all 35 real basin geometries."""
    basins = pd.DataFrame({'huc': ['17'], 'name': ['Columbia River Basin'],
                          'geometry': [None]})
    names = dict(zip(basins['huc'], basins['name']))
    return basins, names


def _run_process_date(tmp_path, discard_raster):
    """Drive _process_date with all I/O mocked; return the fake SWE tif path."""
    from basin_loader import load_all_basins

    swe_tif = tmp_path / '2026' / '01' / '20260115_swe.tif'
    swe_tif.parent.mkdir(parents=True, exist_ok=True)
    swe_tif.write_bytes(b'fake-raster')

    logger = logging.getLogger('test_populate')
    # _process_date now iterates basins.itertuples() over the real 35-basin
    # frame (Task 6 migration) rather than a separate huc2/huc4 pair, so a
    # MagicMock() stand-in for huc2 no longer works here.
    basins = load_all_basins()
    names = dict(zip(basins['huc'], basins['name']))
    with patch.object(pt, 'load_band_cache', return_value=None), \
         patch.object(pt, 'fetch_swe', return_value=swe_tif), \
         patch.object(pt, 'get_aligned_dem', return_value=tmp_path / 'dem.tif'), \
         patch.object(pt, 'compute_bands', return_value=_bands()['Columbia River Basin']), \
         patch.object(pt, 'save_band_cache'), \
         patch.object(pt, 'append_volumes'):
        ok = pt._process_date(
            date(2026, 1, 15), tmp_path, tmp_path / 'dem.tif',
            basins, names, logger, discard_raster=discard_raster,
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


class _FakeRasterioSrc:
    """Minimal stand-in for the rasterio dataset context manager used to
    read WY-file band-count/time-axis metadata."""

    def __init__(self, tags: dict, count: int):
        self._tags = tags
        self.count = count

    def tags(self):
        return self._tags

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_swann_backfill_skips_download_when_year_fully_done(tmp_path):
    """A water year whose [start, end] window is already fully recorded in
    the SWANN volume parquet must not call download_wy_nc at all — resuming
    a backfill should never re-fetch a ~95 MB bulk file for a year that's
    already done."""
    start = date(2020, 1, 1)
    end = date(2020, 1, 3)

    vol_df = pd.DataFrame({'total_swe_volume_km3': [1.0]})
    d = start
    while d <= end:
        append_volumes(datetime(d.year, d.month, d.day),
                       {'17': vol_df}, {'17': 'Columbia River Basin'},
                       tmp_path, dataset='swann')
        d += timedelta(days=1)

    basins, names = _basins_names()
    logger = logging.getLogger('test_populate')

    def _boom(*args, **kwargs):
        raise AssertionError('download_wy_nc must not be called for a fully-done year')

    with patch.object(pt.swann_fetcher, 'download_wy_nc', side_effect=_boom):
        failed = pt._run_swann_backfill(start, end, tmp_path, basins, names,
                                        logger, discard=False)

    assert failed == []


def test_swann_backfill_mismatch_cleans_up_wy_nc(tmp_path):
    """A WY file whose declared band count disagrees with its time axis is
    skipped, but the downloaded netCDF (and the shared tmp extract tif) must
    still be cleaned up when --discard-raster is set — a mismatched year
    must not silently retain a ~95 MB file."""
    start = date(2020, 1, 1)
    end = date(2020, 1, 5)
    wy = 2020

    swann_dir = tmp_path / 'swann'
    swann_dir.mkdir(parents=True)
    wy_nc = swann_dir / f'UA_SWE_Depth_WY{wy}.nc'
    wy_nc.write_bytes(b'fake-nc')

    basins, names = _basins_names()
    logger = logging.getLogger('test_populate')

    fake_tags = {
        'NETCDF_DIM_time_VALUES': '{1,2}',          # 2 dates ...
        'time#units': 'days since 1900-01-01 00:00:00',
    }

    with patch.object(pt.swann_fetcher, 'download_wy_nc', return_value=wy_nc), \
         patch.object(pt.rasterio, 'open',
                      return_value=_FakeRasterioSrc(fake_tags, count=3)):  # ... 3 bands
        failed = pt._run_swann_backfill(start, end, tmp_path, basins, names,
                                        logger, discard=True)

    assert date(wy - 1, 10, 1) in failed
    assert not wy_nc.exists(), 'discarded WY netCDF must be removed even on the mismatch path'
    assert not (tmp_path / 'swann' / 'wy_extract_tmp.tif').exists()


def test_swann_backfill_daily_fallback_cleans_up_failed_day(tmp_path):
    """In daily-file (fallback) mode, a day that raises during processing
    must still have its fetched raster discarded when --discard-raster is
    set — cleanup should not be conditioned on success."""
    start = date(2024, 10, 1)
    end = date(2024, 10, 1)

    basins, names = _basins_names()
    logger = logging.getLogger('test_populate')

    swe_tif = tmp_path / '20241001_swe.tif'
    swe_tif.write_bytes(b'fake-raster')

    with patch.object(pt.swann_fetcher, 'download_wy_nc',
                      side_effect=FileNotFoundError('no bulk file')), \
         patch.object(pt.swann_fetcher, 'fetch_swe', return_value=swe_tif), \
         patch.object(pt, 'get_aligned_dem', return_value=tmp_path / 'dem.tif'), \
         patch.object(pt, '_swann_process_day', side_effect=RuntimeError('boom')):
        failed = pt._run_swann_backfill(start, end, tmp_path, basins, names,
                                        logger, discard=True)

    assert failed == [date(2024, 10, 1)]
    assert not swe_tif.exists(), 'failed day must still discard its fetched raster'


def test_swann_backfill_corrupt_wy_file_does_not_abort_run(tmp_path):
    """A corrupt/truncated WY netCDF (e.g. a partial download left by a
    killed run — download_wy_nc returns it without validation) must not
    raise out of _run_swann_backfill and kill the whole multi-decade run:
    the year's metadata read failing is caught, logged to `failed`, and the
    loop proceeds to the next water year."""
    import rasterio.errors

    start = date(2019, 1, 1)
    end = date(2020, 1, 3)   # spans WY2019 and WY2020

    basins, names = _basins_names()
    logger = logging.getLogger('test_populate')

    download_calls = []

    def fake_download(wy, dest_dir):
        download_calls.append(wy)
        dest_dir.mkdir(parents=True, exist_ok=True)
        stub = dest_dir / f'UA_SWE_Depth_WY{wy}.nc'
        stub.write_bytes(b'truncated')  # corrupt stand-in
        return stub

    def fake_open(*args, **kwargs):
        raise rasterio.errors.RasterioIOError('corrupt netCDF')

    with patch.object(pt.swann_fetcher, 'download_wy_nc', side_effect=fake_download), \
         patch.object(pt.rasterio, 'open', side_effect=fake_open):
        failed = pt._run_swann_backfill(start, end, tmp_path, basins, names,
                                        logger, discard=False)

    # Both years are marked failed (metadata read raised for each) ...
    assert date(2018, 10, 1) in failed
    assert date(2019, 10, 1) in failed
    # ... but the loop kept going past year 1: year 2's download was attempted.
    assert download_calls == [2019, 2020]


def test_main_invalid_end_date_exits_with_friendly_message(monkeypatch, capsys):
    """--end with an unparsable date must print the same friendly
    ERROR/YYYY-MM-DD message --start already gets, and exit(1) — not raise a
    raw ValueError traceback."""
    import pytest
    import populate_timeseries

    monkeypatch.setattr(
        "sys.argv",
        ["populate_timeseries.py", "--end", "not-a-date"],
    )
    with pytest.raises(SystemExit) as exc_info:
        populate_timeseries.main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert 'invalid --end date "not-a-date"' in captured.err
    assert 'YYYY-MM-DD' in captured.err


def test_stage_dir_and_end_args():
    import populate_timeseries
    p = populate_timeseries.build_parser()
    a = p.parse_args(["--stage-dir", "/tmp/x", "--end", "2026-07-01"])
    assert a.stage_dir == "/tmp/x" and a.end == "2026-07-01"
    assert p.parse_args([]).stage_dir is None


def test_process_date_writes_to_stage_dir(tmp_path, monkeypatch):
    import logging, pandas as pd
    from datetime import date
    import populate_timeseries
    from basin_loader import load_all_basins
    from timeseries import load_timeseries

    logger = logging.getLogger("t"); logger.addHandler(logging.NullHandler())
    basins = load_all_basins()
    names = dict(zip(basins["huc"], basins["name"]))
    monkeypatch.setattr(populate_timeseries, "fetch_swe",
                        lambda d, cache_dir: tmp_path / "x.tif")
    monkeypatch.setattr(populate_timeseries, "get_aligned_dem",
                        lambda s, dem_cache: tmp_path / "d.tif")
    monkeypatch.setattr(
        populate_timeseries, "compute_bands",
        lambda s, d, g, min_band_area_km2=0.0: pd.DataFrame(
            {"elev_band_m": [1000], "mean_swe_mm": [50.0],
             "area_km2": [10.0], "total_swe_volume_km3": [0.001]}))

    stage = tmp_path / "rebuild"
    ok = populate_timeseries._process_date(
        date(2026, 1, 15), tmp_path, tmp_path / "dem.tif", basins, names,
        logger, discard_raster=False, ts_dir=stage)
    assert ok
    assert len(load_timeseries(2026, tmp_path, ts_dir=stage)) == 35
    assert not (tmp_path / "timeseries" / "WY2026_volume.parquet").exists()
