"""Tests for scripts/fetch_wbd_basemaps.py — no network; the download seam
(`fetch()`) is monkeypatched throughout."""
import json

import geopandas as gpd
import pytest
from shapely.geometry import Polygon, mapping

import scripts.fetch_wbd_basemaps as fwb


def _feature_collection(n: int, field: str) -> bytes:
    """A minimal, valid GeoJSON FeatureCollection with n features."""
    features = []
    for i in range(n):
        poly = Polygon([(i, 0), (i, 1), (i + 1, 1), (i + 1, 0)])
        features.append({
            "type": "Feature",
            "properties": {field: f"17{i:02d}", "name": f"Basin {i}"},
            "geometry": mapping(poly),
        })
    return json.dumps({"type": "FeatureCollection", "features": features}).encode()


# --- (a) pure URL-building helper ---

def test_build_query_url_includes_simplification_tolerance_and_format():
    url = fwb.build_query_url(2, "huc4", "huc4 LIKE '17%'")
    assert "maxAllowableOffset=0.001" in url
    assert "f=geojson" in url
    assert "huc4" in url


def test_build_query_url_uses_correct_layer_in_path():
    url = fwb.build_query_url(3, "huc6", "huc6 LIKE '17%'")
    assert f"{fwb.BASE}/3/query?" in url


# --- (b) size guard: must not clobber a pre-existing committed file ---

def test_size_guard_exits_without_replacing_existing_committed_file(tmp_path, monkeypatch):
    monkeypatch.setattr(fwb, "OUT", tmp_path)
    # Force the guard to trip on any real payload without needing an
    # actual >5MB fetch.
    monkeypatch.setattr(fwb, "MAX_BYTES", 10)

    committed_path = tmp_path / "huc4_pnw.geojson"
    committed_path.write_text('{"marker": "pre-existing committed content"}')

    payload = _feature_collection(1, "huc4")
    monkeypatch.setattr(fwb, "fetch", lambda layer, field, where: payload)

    layers = [(2, "huc4", "huc4 LIKE '17%'", "huc4_pnw.geojson", 1)]

    with pytest.raises(SystemExit) as exc_info:
        fwb.main(layers=layers)
    assert exc_info.value.code == 1

    # The committed file must be untouched by the failed run (proves the
    # write is atomic: checks run against the temp file, not the real path).
    assert committed_path.read_text() == '{"marker": "pre-existing committed content"}'
    # No temp file left behind on the failure path.
    assert not (tmp_path / "huc4_pnw.tmp").exists()


# --- (c) passing run: temp file is renamed onto the committed path ---

def test_successful_fetch_renames_tmp_to_final(tmp_path, monkeypatch):
    monkeypatch.setattr(fwb, "OUT", tmp_path)

    payload = _feature_collection(3, "huc6")
    monkeypatch.setattr(fwb, "fetch", lambda layer, field, where: payload)

    layers = [(3, "huc6", "huc6 LIKE '17%'", "huc6_pnw.geojson", 3)]

    fwb.main(layers=layers)

    final_path = tmp_path / "huc6_pnw.geojson"
    assert final_path.exists()
    assert not (tmp_path / "huc6_pnw.tmp").exists()

    g = gpd.read_file(final_path)
    assert len(g) == 3
    assert sorted(g["huc6"]) == ["1700", "1701", "1702"]


def test_feature_count_mismatch_exits_and_leaves_committed_file_untouched(tmp_path, monkeypatch):
    monkeypatch.setattr(fwb, "OUT", tmp_path)

    committed_path = tmp_path / "huc6_pnw.geojson"
    committed_path.write_text('{"marker": "pre-existing committed content"}')

    payload = _feature_collection(1, "huc6")  # only 1, but 22 expected
    monkeypatch.setattr(fwb, "fetch", lambda layer, field, where: payload)

    layers = [(3, "huc6", "huc6 LIKE '17%'", "huc6_pnw.geojson", 22)]

    with pytest.raises(SystemExit) as exc_info:
        fwb.main(layers=layers)
    assert exc_info.value.code == 1
    assert committed_path.read_text() == '{"marker": "pre-existing committed content"}'
    assert not (tmp_path / "huc6_pnw.tmp").exists()
