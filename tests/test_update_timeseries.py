import logging
from datetime import datetime

import pytest

import datasets
import update_timeseries


@pytest.fixture
def quiet_logger():
    logger = logging.getLogger("test_update_timeseries")
    logger.addHandler(logging.NullHandler())
    return logger


def test_process_dataset_routes_to_swann_fetcher(tmp_path, monkeypatch, quiet_logger):
    called = {}

    def fake_latest(ref, cache_dir):
        called["swann"] = True
        raise ConnectionError("routing verified")

    monkeypatch.setitem(datasets.DATASETS["swann"], "fetch_latest_swe", fake_latest)
    ok = update_timeseries.process_dataset(
        "swann", None, tmp_path, None, None, quiet_logger, discard_raster=False)
    assert ok is False
    assert called == {"swann": True}


def test_process_dataset_skips_when_band_cache_current(tmp_path, monkeypatch, quiet_logger):
    """If the target date's band cache exists, no bands are recomputed."""
    import pandas as pd
    from pipeline import save_band_cache

    target = datetime(2026, 7, 18)
    bands = {"Columbia River Basin": pd.DataFrame({
        "elev_band_m": [1000], "mean_swe_mm": [100.0],
        "area_km2": [50.0], "total_swe_volume_km3": [0.005],
    })}
    save_band_cache(bands, "20260718", tmp_path, dataset="swann")

    monkeypatch.setitem(
        datasets.DATASETS["swann"], "fetch_latest_swe",
        lambda ref, cache_dir: (tmp_path / "unused.tif", target))

    ok = update_timeseries.process_dataset(
        "swann", None, tmp_path, None, None, quiet_logger, discard_raster=False)
    assert ok is True
    # volumes were appended from the cache
    from timeseries import load_timeseries
    assert not load_timeseries(2026, tmp_path, dataset="swann").empty


def test_main_dataset_choices():
    parser = update_timeseries.build_parser()
    assert parser.parse_args([]).dataset == "both"
    assert parser.parse_args(["--dataset", "swann"]).dataset == "swann"
    with pytest.raises(SystemExit):
        parser.parse_args(["--dataset", "modis"])
