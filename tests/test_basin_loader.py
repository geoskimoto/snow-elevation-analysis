# tests/test_basin_loader.py
import pytest
import geopandas as gpd
from pathlib import Path
import basin_loader


def test_load_huc2_returns_geodataframe():
    gdf = basin_loader.load_huc2()
    assert isinstance(gdf, gpd.GeoDataFrame)


def test_load_huc2_has_one_feature():
    gdf = basin_loader.load_huc2()
    assert len(gdf) == 1


def test_load_huc2_crs_is_4326():
    gdf = basin_loader.load_huc2()
    assert gdf.crs.to_epsg() == 4326


def test_load_huc4_returns_geodataframe():
    gdf = basin_loader.load_huc4()
    assert isinstance(gdf, gpd.GeoDataFrame)


def test_load_huc4_has_expected_subbasins():
    gdf = basin_loader.load_huc4()
    # Standard WBD region 17: 12 subregions (1701-1712), no custom splits.
    assert len(gdf) == 12
    codes = set(gdf['huc4'])
    assert codes == {f"17{i:02d}" for i in range(1, 13)}
    names = set(gdf['name'])
    assert 'Kootenai-Pend Oreille-Spokane' in names
    assert 'Upper Columbia' in names
    assert 'Kootenai' not in names
    assert 'Pend Oreille-Spokane' not in names
    assert 'Upper Columbia (BC)' not in names
    assert 'Upper Columbia (Washington)' not in names


def test_load_huc4_has_name_column():
    gdf = basin_loader.load_huc4()
    assert 'name' in gdf.columns


def test_load_huc4_has_huc4_column():
    gdf = basin_loader.load_huc4()
    assert 'huc4' in gdf.columns


def test_load_huc2_raises_if_file_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(basin_loader, 'BASEMAP_DIR', tmp_path)
    with pytest.raises(FileNotFoundError, match="huc2_pnw.geojson"):
        basin_loader.load_huc2()


def test_load_huc4_raises_if_file_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(basin_loader, 'BASEMAP_DIR', tmp_path)
    with pytest.raises(FileNotFoundError, match="huc4_pnw.geojson"):
        basin_loader.load_huc4()
