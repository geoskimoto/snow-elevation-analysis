import urllib.error
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

import swann_fetcher


@pytest.fixture
def synthetic_swann_nc(tmp_path):
    """2x2 SWANN-style netCDF (int16, EPSG:4269, nodata=-999), GDAL-written.

    GDAL names the variable 'Band1'; production files use 'SWE', so tests
    exercise nc_to_geotiff with variable=None (single-var direct open).
    """
    path = tmp_path / "swann.nc"
    data = np.array([[100, 200], [-999, 400]], dtype=np.int16)
    transform = from_origin(-125.0208, 49.9375, 0.0416667, 0.0416667)
    with rasterio.open(
        path, "w", driver="NETCDF",
        height=2, width=2, count=1, dtype="int16",
        crs="EPSG:4269", transform=transform, nodata=-999,
    ) as dst:
        dst.write(data, 1)
    return path


def test_validate_date_rejects_pre_swann():
    with pytest.raises(ValueError):
        swann_fetcher.validate_date(datetime(1981, 9, 30))
    swann_fetcher.validate_date(datetime(1981, 10, 1))  # no raise


def test_cache_path_is_namespaced_under_swann(tmp_path):
    p = swann_fetcher.cache_path(datetime(2026, 1, 15), tmp_path)
    assert p == tmp_path / "swann" / "2026" / "01" / "20260115_swe.tif"


def test_daily_url_uses_water_year_directory_and_suffix():
    url = swann_fetcher.daily_url(datetime(2026, 1, 15), "provisional")
    assert url == (
        "https://climate.arizona.edu/data/UA_SWE/DailyData_4km/WY2026/"
        "UA_SWE_Depth_4km_v1_20260115_provisional.nc"
    )
    # Oct 1 belongs to the NEXT water year's directory
    assert "/WY2027/" in swann_fetcher.daily_url(datetime(2026, 10, 1), "early")


def test_wy_url():
    assert swann_fetcher.wy_url(1982) == (
        "https://climate.arizona.edu/data/UA_SWE/WYData_4km/UA_SWE_Depth_WY1982.nc"
    )


def test_nc_to_geotiff_remaps_nodata_and_preserves_grid(synthetic_swann_nc, tmp_path):
    out = tmp_path / "out.tif"
    swann_fetcher.nc_to_geotiff(synthetic_swann_nc, out, variable=None)
    with rasterio.open(out) as d:
        arr = d.read(1)
        assert d.nodata == -9999
        assert d.dtypes[0] == "int16"
        assert arr[1, 0] == -9999          # -999 remapped
        assert arr[0, 0] == 100            # data preserved
        assert d.crs is not None
        assert abs(d.transform.a - 0.0416667) < 1e-6


def test_nc_to_geotiff_rejects_wrong_pixel_size(tmp_path):
    """A grid resolution that drifted from the verified 0.0416667 deg SWANN
    convention must fail loudly at ingest, not silently mis-scale downstream
    elevation-band math."""
    path = tmp_path / "wrong_res.nc"
    data = np.array([[100, 200], [300, 400]], dtype=np.int16)
    transform = from_origin(-125.0208, 49.9375, 0.008333, 0.008333)
    with rasterio.open(
        path, "w", driver="NETCDF",
        height=2, width=2, count=1, dtype="int16",
        crs="EPSG:4269", transform=transform, nodata=-999,
    ) as dst:
        dst.write(data, 1)

    with pytest.raises(ValueError):
        swann_fetcher.nc_to_geotiff(path, tmp_path / "out.tif", variable=None)


def test_nc_to_geotiff_rejects_wrong_dtype(tmp_path):
    """A source dtype other than int16 must fail loudly at ingest rather
    than silently truncate/misread SWE values."""
    path = tmp_path / "wrong_dtype.nc"
    data = np.array([[100.0, 200.0], [300.0, 400.0]], dtype=np.float32)
    transform = from_origin(-125.0208, 49.9375, 0.0416667, 0.0416667)
    with rasterio.open(
        path, "w", driver="NETCDF",
        height=2, width=2, count=1, dtype="float32",
        crs="EPSG:4269", transform=transform, nodata=-999.0,
    ) as dst:
        dst.write(data, 1)

    with pytest.raises(ValueError):
        swann_fetcher.nc_to_geotiff(path, tmp_path / "out.tif", variable=None)


def test_fetch_swe_returns_cached_without_download(tmp_path, monkeypatch):
    date = datetime(2026, 1, 15)
    tif = swann_fetcher.cache_path(date, tmp_path)
    tif.parent.mkdir(parents=True)
    tif.write_bytes(b"stub")

    def _boom(*a, **k):
        raise AssertionError("network touched despite cache hit")

    monkeypatch.setattr(swann_fetcher, "_download_daily_nc", _boom)
    assert swann_fetcher.fetch_swe(date, cache_dir=tmp_path) == tif


def test_download_daily_nc_falls_through_suffixes(tmp_path, monkeypatch):
    """404 on stable and provisional -> early is used."""
    calls = []

    def fake_urlretrieve(url, dest):
        calls.append(url)
        if "_early.nc" not in url:
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
        Path(dest).write_bytes(b"nc-bytes")

    monkeypatch.setattr(swann_fetcher, "_urlretrieve", fake_urlretrieve)
    dest = tmp_path / "d.nc"
    swann_fetcher._download_daily_nc(datetime(2026, 7, 19), dest)
    assert len(calls) == 3
    assert "_stable.nc" in calls[0] and "_provisional.nc" in calls[1] and "_early.nc" in calls[2]
    assert dest.read_bytes() == b"nc-bytes"


def test_download_daily_nc_all_missing_raises_connectionerror(tmp_path, monkeypatch):
    def fake_urlretrieve(url, dest):
        raise urllib.error.HTTPError(url, 404, "Not Found", None, None)

    monkeypatch.setattr(swann_fetcher, "_urlretrieve", fake_urlretrieve)
    with pytest.raises(ConnectionError):
        swann_fetcher._download_daily_nc(datetime(2026, 7, 19), tmp_path / "d.nc")


def test_fetch_latest_swe_scans_backward(tmp_path, monkeypatch):
    ref = datetime(2026, 7, 20)

    def fake_fetch(date, cache_dir):
        if date >= datetime(2026, 7, 19):
            raise ConnectionError("not published yet")
        return Path("/fake.tif")

    monkeypatch.setattr(swann_fetcher, "fetch_swe", fake_fetch)
    tif, actual = swann_fetcher.fetch_latest_swe(ref, cache_dir=tmp_path)
    assert actual == datetime(2026, 7, 18)


def test_download_wy_nc_404_raises_filenotfound(tmp_path, monkeypatch):
    def fake_urlretrieve(url, dest):
        raise urllib.error.HTTPError(url, 404, "Not Found", None, None)

    monkeypatch.setattr(swann_fetcher, "_urlretrieve", fake_urlretrieve)
    with pytest.raises(FileNotFoundError):
        swann_fetcher.download_wy_nc(2026, tmp_path)
