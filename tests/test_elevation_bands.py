# tests/test_elevation_bands.py
import pytest
import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin
from pathlib import Path
from shapely.geometry import box
import elevation_bands


@pytest.fixture
def aligned_swe_dem(tmp_path):
    """SWE and DEM tifs on identical 4x4 grid, no nodata pixels."""
    transform = from_origin(-120.0, 48.0, 0.008333, 0.008333)
    crs = "EPSG:4326"

    swe_data = np.array([
        [100, 200, 300, 400],
        [150, 250, 350, 450],
        [50,  100, 200, 300],
        [0,   0,   50,  100],
    ], dtype=np.int16)
    swe_path = tmp_path / "swe.tif"
    with rasterio.open(swe_path, 'w', driver='GTiff', height=4, width=4,
                       count=1, dtype='int16', crs=crs, transform=transform,
                       nodata=-9999) as dst:
        dst.write(swe_data, 1)

    dem_data = np.array([
        [100.0, 300.0, 600.0, 800.0],
        [150.0, 350.0, 650.0, 850.0],
        [200.0, 400.0, 700.0, 900.0],
        [50.0,  100.0, 550.0, 750.0],
    ], dtype=np.float32)
    dem_path = tmp_path / "dem.tif"
    with rasterio.open(dem_path, 'w', driver='GTiff', height=4, width=4,
                       count=1, dtype='float32', crs=crs, transform=transform,
                       nodata=-9999.0) as dst:
        dst.write(dem_data, 1)

    geom = box(-120.05, 47.95, -119.95, 48.05)
    return swe_path, dem_path, geom


def test_compute_bands_returns_dataframe(aligned_swe_dem):
    swe_tif, dem_tif, geom = aligned_swe_dem
    result = elevation_bands.compute_bands(swe_tif, dem_tif, geom, band_interval_m=250)
    assert isinstance(result, pd.DataFrame)


def test_compute_bands_has_required_columns(aligned_swe_dem):
    swe_tif, dem_tif, geom = aligned_swe_dem
    result = elevation_bands.compute_bands(swe_tif, dem_tif, geom, band_interval_m=250)
    assert set(result.columns) >= {'elev_band_m', 'mean_swe_mm', 'area_km2', 'total_swe_volume_km3'}


def test_compute_bands_elev_bands_are_multiples_of_interval(aligned_swe_dem):
    swe_tif, dem_tif, geom = aligned_swe_dem
    result = elevation_bands.compute_bands(swe_tif, dem_tif, geom, band_interval_m=250)
    assert all(result['elev_band_m'] % 250 == 0)


def test_compute_bands_excludes_fully_masked_bands(tmp_path):
    """Bands where all pixels are nodata must not appear in output."""
    transform = from_origin(-120.0, 48.0, 0.008333, 0.008333)
    crs = "EPSG:4326"
    swe_data = np.array([[100, -9999], [-9999, -9999]], dtype=np.int16)
    swe_path = tmp_path / "swe_sparse.tif"
    with rasterio.open(swe_path, 'w', driver='GTiff', height=2, width=2,
                       count=1, dtype='int16', crs=crs, transform=transform,
                       nodata=-9999) as dst:
        dst.write(swe_data, 1)
    dem_data = np.array([[100.0, 300.0], [1500.0, 1600.0]], dtype=np.float32)
    dem_path = tmp_path / "dem_sparse.tif"
    with rasterio.open(dem_path, 'w', driver='GTiff', height=2, width=2,
                       count=1, dtype='float32', crs=crs, transform=transform,
                       nodata=-9999.0) as dst:
        dst.write(dem_data, 1)
    geom = box(-120.05, 47.95, -119.95, 48.05)
    result = elevation_bands.compute_bands(swe_path, dem_path, geom, band_interval_m=250)
    # Bands 1250-1500 and 1500-1750 should be absent (no valid SWE pixels)
    assert not any(result['elev_band_m'] >= 1250)


def test_compute_bands_includes_zero_swe_bands(aligned_swe_dem):
    """Bands containing valid zero-SWE pixels must appear in output (not filtered out)."""
    swe_tif, dem_tif, geom = aligned_swe_dem
    result = elevation_bands.compute_bands(swe_tif, dem_tif, geom, band_interval_m=250)
    # The 0-250m band contains pixels with SWE=0 — it must appear in the output
    assert 0 in result['elev_band_m'].values
    # And mean SWE in that band must be >= 0 (not filtered for being zero)
    band_0 = result[result['elev_band_m'] == 0]
    assert len(band_0) == 1
    assert band_0.iloc[0]['mean_swe_mm'] >= 0.0


def test_compute_bands_area_positive(aligned_swe_dem):
    swe_tif, dem_tif, geom = aligned_swe_dem
    result = elevation_bands.compute_bands(swe_tif, dem_tif, geom, band_interval_m=250)
    assert (result['area_km2'] > 0).all()


def test_compute_bands_volume_formula(aligned_swe_dem):
    """total_swe_volume_km3 == mean_swe_mm * area_km2 * 1e-6"""
    swe_tif, dem_tif, geom = aligned_swe_dem
    result = elevation_bands.compute_bands(swe_tif, dem_tif, geom, band_interval_m=250)
    expected = result['mean_swe_mm'] * result['area_km2'] * 1e-6
    np.testing.assert_allclose(result['total_swe_volume_km3'], expected, rtol=1e-6)


def test_compute_bands_swe_in_valid_range(aligned_swe_dem):
    """Property: mean SWE must be within SNODAS valid range 0-2000 mm."""
    swe_tif, dem_tif, geom = aligned_swe_dem
    result = elevation_bands.compute_bands(swe_tif, dem_tif, geom, band_interval_m=250)
    assert (result['mean_swe_mm'] >= 0).all()
    assert (result['mean_swe_mm'] <= 2000).all()


def test_compute_bands_respects_band_interval(aligned_swe_dem):
    """Changing band_interval_m changes the number of output rows."""
    swe_tif, dem_tif, geom = aligned_swe_dem
    result_250 = elevation_bands.compute_bands(swe_tif, dem_tif, geom, band_interval_m=250)
    result_500 = elevation_bands.compute_bands(swe_tif, dem_tif, geom, band_interval_m=500)
    assert len(result_250) >= len(result_500)


def test_compute_bands_raises_on_large_grid_mismatch(tmp_path):
    """Raises ValueError if SWE and DEM shapes differ by more than 1 pixel."""
    transform = from_origin(-120.0, 48.0, 0.008333, 0.008333)
    crs = "EPSG:4326"

    swe_data = np.ones((4, 4), dtype=np.int16) * 100
    swe_path = tmp_path / "swe_big.tif"
    with rasterio.open(swe_path, 'w', driver='GTiff', height=4, width=4,
                       count=1, dtype='int16', crs=crs, transform=transform,
                       nodata=-9999) as dst:
        dst.write(swe_data, 1)

    # DEM is 10x10 — much larger, simulating a misaligned DEM
    dem_transform = from_origin(-120.0, 48.0, 0.003333, 0.003333)
    dem_data = np.ones((10, 10), dtype=np.float32) * 500
    dem_path = tmp_path / "dem_wrong.tif"
    with rasterio.open(dem_path, 'w', driver='GTiff', height=10, width=10,
                       count=1, dtype='float32', crs=crs, transform=dem_transform,
                       nodata=-9999.0) as dst:
        dst.write(dem_data, 1)

    geom = box(-120.05, 47.95, -119.95, 48.05)
    with pytest.raises(ValueError, match="grid mismatch"):
        elevation_bands.compute_bands(swe_path, dem_path, geom, band_interval_m=250)
