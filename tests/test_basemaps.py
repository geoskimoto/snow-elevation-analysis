"""Integrity tests for the committed WBD basemaps (35-basin structure)."""
import geopandas as gpd
import pytest

from basin_loader import load_huc2, load_huc4, load_huc6, load_all_basins


def test_huc4_is_standard_twelve():
    g = load_huc4()
    assert sorted(g["huc4"]) == [f"17{i:02d}" for i in range(1, 13)]
    # no custom pseudo-codes survive
    assert not any(c.endswith(("a", "b")) for c in g["huc4"])


def test_huc6_is_twentytwo_and_nested():
    g6 = load_huc6()
    assert len(g6) == 22
    huc4s = set(load_huc4()["huc4"])
    assert all(c[:4] in huc4s for c in g6["huc6"])
    assert g6.geometry.is_valid.all()


def test_load_all_basins_shape_and_key():
    b = load_all_basins()
    assert list(b.columns) == ["huc", "name", "geometry"]
    assert len(b) == 35
    assert b["huc"].is_unique
    assert list(b["huc"]) == sorted(b["huc"])
    assert set(b["huc"].str.len().unique()) == {2, 4, 6}
    assert b.loc[b["huc"] == "17", "name"].iloc[0] == "Columbia River Basin"
    assert b.crs.to_epsg() == 4326


def test_name_collisions_exist_but_codes_disambiguate():
    b = load_all_basins()
    assert b["name"].duplicated().any()      # e.g. Yakima at 1703 and 170300
    assert b["huc"].is_unique


def test_salmon_and_clearwater_present():
    b = load_all_basins().set_index("huc")
    assert b.loc["170602", "name"] == "Salmon"
    assert b.loc["170603", "name"] == "Clearwater"
