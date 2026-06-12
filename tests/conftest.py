import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from pathlib import Path
import json
from shapely.geometry import box, mapping


@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path


@pytest.fixture
def synthetic_swe_tif(tmp_path):
    """3x3 SNODAS-style SWE GeoTIFF (int16, EPSG:4326, nodata=-9999)."""
    path = tmp_path / "swe.tif"
    data = np.array([[100, 200, 300],
                     [400, 500, -9999],
                     [600, 700, 800]], dtype=np.int16)
    transform = from_origin(-120.0, 48.0, 0.008333, 0.008333)
    with rasterio.open(
        path, 'w', driver='GTiff',
        height=3, width=3, count=1,
        dtype='int16', crs='EPSG:4326',
        transform=transform, nodata=-9999
    ) as dst:
        dst.write(data, 1)
    return path


@pytest.fixture
def synthetic_dem_tif(tmp_path):
    """3x3 DEM GeoTIFF pixel-aligned with synthetic_swe_tif."""
    path = tmp_path / "dem.tif"
    data = np.array([[100.0, 300.0, 600.0],
                     [150.0, 350.0, 650.0],
                     [200.0, 400.0, 700.0]], dtype=np.float32)
    transform = from_origin(-120.0, 48.0, 0.008333, 0.008333)
    with rasterio.open(
        path, 'w', driver='GTiff',
        height=3, width=3, count=1,
        dtype='float32', crs='EPSG:4326',
        transform=transform, nodata=-9999.0
    ) as dst:
        dst.write(data, 1)
    return path


@pytest.fixture
def basin_geom():
    """Small polygon covering the synthetic raster extent."""
    return box(-120.05, 47.95, -119.95, 48.05)


@pytest.fixture
def basin_geojson(tmp_path, basin_geom):
    """Single-feature GeoJSON file."""
    path = tmp_path / "test_basin.geojson"
    fc = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {"name": "Test Basin", "huc2": "17"},
            "geometry": mapping(basin_geom)
        }]
    }
    path.write_text(json.dumps(fc))
    return path
