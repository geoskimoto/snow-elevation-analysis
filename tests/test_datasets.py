from datetime import datetime

import pytest

import datasets


def test_registry_has_both_datasets():
    assert set(datasets.DATASETS) == {"snodas", "swann"}


def test_snodas_entry():
    d = datasets.get("snodas")
    assert d["start"] == datetime(2003, 10, 1)
    assert "SNODAS" in d["label"] and "1 km" in d["label"]
    assert d["dem_filename"] == "columbia_basin_swe_aligned.tif"
    assert callable(d["fetch_swe"]) and callable(d["fetch_latest_swe"])


def test_swann_entry():
    d = datasets.get("swann")
    assert d["start"] == datetime(1981, 10, 1)
    assert "SWANN" in d["label"] and "4 km" in d["label"]
    assert d["dem_filename"] == "columbia_basin_swann_aligned.tif"
    assert "4 km" in d["footnote"]


def test_unknown_dataset_raises():
    with pytest.raises(KeyError):
        datasets.get("modis")
