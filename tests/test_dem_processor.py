# tests/test_dem_processor.py
import pytest
import numpy as np
import rasterio
from rasterio.transform import from_origin
from pathlib import Path
from unittest.mock import patch
import dem_processor


def test_get_aligned_dem_returns_cached_if_exists(tmp_path, synthetic_swe_tif):
    cache = tmp_path / "dem" / "columbia_basin_swe_aligned.tif"
    cache.parent.mkdir(parents=True)
    cache.touch()

    with patch('dem_processor.build_aligned_dem') as mock_build:
        result = dem_processor.get_aligned_dem(synthetic_swe_tif, dem_cache=cache)
        mock_build.assert_not_called()
    assert result == cache


def test_get_aligned_dem_calls_build_when_cache_missing(tmp_path, synthetic_swe_tif):
    cache = tmp_path / "dem" / "columbia_basin_swe_aligned.tif"

    def fake_build(swe_tif, dem_cache):
        dem_cache.parent.mkdir(parents=True, exist_ok=True)
        dem_cache.touch()

    with patch('dem_processor.build_aligned_dem', side_effect=fake_build) as mock_build:
        dem_processor.get_aligned_dem(synthetic_swe_tif, dem_cache=cache)
        mock_build.assert_called_once_with(synthetic_swe_tif, cache)


def test_get_aligned_dem_returns_path(tmp_path, synthetic_swe_tif):
    cache = tmp_path / "dem" / "columbia_basin_swe_aligned.tif"

    def fake_build(swe_tif, dem_cache):
        dem_cache.parent.mkdir(parents=True, exist_ok=True)
        dem_cache.touch()

    with patch('dem_processor.build_aligned_dem', side_effect=fake_build):
        result = dem_processor.get_aligned_dem(synthetic_swe_tif, dem_cache=cache)
    assert result == cache
    assert result.exists()


def test_warp_dem_to_snodas_grid_matches_shape(tmp_path, synthetic_swe_tif):
    """warp_dem_to_grid output must have identical shape/transform to the reference tif."""
    raw_dem = tmp_path / "raw_dem.tif"
    data = np.random.rand(6, 6).astype(np.float32) * 2000
    transform = from_origin(-120.05, 48.05, 0.004, 0.004)
    with rasterio.open(
        raw_dem, 'w', driver='GTiff',
        height=6, width=6, count=1,
        dtype='float32', crs='EPSG:4326',
        transform=transform
    ) as dst:
        dst.write(data, 1)

    output = tmp_path / "warped.tif"
    dem_processor.warp_dem_to_grid(raw_dem, synthetic_swe_tif, output)

    with rasterio.open(output) as dst, rasterio.open(synthetic_swe_tif) as ref:
        assert dst.width == ref.width
        assert dst.height == ref.height
        assert dst.transform == ref.transform
        assert dst.crs == ref.crs
