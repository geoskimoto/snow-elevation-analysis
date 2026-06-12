# tests/test_integration.py
import pytest
import numpy as np
import rasterio
from rasterio.transform import from_origin
from datetime import datetime
from pathlib import Path
import pandas as pd
import basin_loader
import elevation_bands

FIXTURE_TIF = Path(__file__).parent / "fixtures" / "snodas_20240401_columbia.tif"


@pytest.fixture
def columbia_dem(tmp_path):
    """Synthetic DEM aligned to fixture SNODAS extent."""
    with rasterio.open(FIXTURE_TIF) as src:
        h, w = src.height, src.width
        transform = src.transform
        crs = src.crs
    # Synthetic elevation gradient: 0m (west) to 3000m (east)
    cols = np.linspace(0, 3000, w)
    data = np.tile(cols, (h, 1)).astype(np.float32)
    dem_path = tmp_path / "synthetic_dem.tif"
    with rasterio.open(dem_path, 'w', driver='GTiff',
                       height=h, width=w, count=1,
                       dtype='float32', crs=crs,
                       transform=transform, nodata=-9999.0) as dst:
        dst.write(data, 1)
    return dem_path


@pytest.mark.skipif(not FIXTURE_TIF.exists(), reason="SNODAS fixture not built yet")
def test_integration_compute_bands_huc2(columbia_dem):
    huc2 = basin_loader.load_huc2()
    geom = huc2.geometry.iloc[0]
    result = elevation_bands.compute_bands(
        FIXTURE_TIF, columbia_dem, geom, band_interval_m=250
    )
    assert isinstance(result, pd.DataFrame)
    assert len(result) > 0
    assert (result['mean_swe_mm'] >= 0).all()
    assert (result['mean_swe_mm'] <= 2000).all()


@pytest.mark.skipif(not FIXTURE_TIF.exists(), reason="SNODAS fixture not built yet")
def test_integration_plotter_writes_files(tmp_path, columbia_dem):
    from plotter import plot_hypsometric

    huc2 = basin_loader.load_huc2()
    geom = huc2.geometry.iloc[0]
    df = elevation_bands.compute_bands(
        FIXTURE_TIF, columbia_dem, geom, band_interval_m=500
    )
    paths = plot_hypsometric(
        {'Columbia River Basin': df},
        datetime(2024, 4, 1),
        tmp_path
    )
    assert len(paths) == 1
    assert paths[0].exists()
    assert paths[0].stat().st_size > 1000
