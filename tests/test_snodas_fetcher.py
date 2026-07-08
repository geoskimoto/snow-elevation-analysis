# tests/test_snodas_fetcher.py
import pytest
import numpy as np
import rasterio
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock
import snodas_fetcher


# --- Unit: filename helpers ---

def test_ftp_path_format():
    date = datetime(2024, 4, 1)
    path = snodas_fetcher.ftp_dir_path(date)
    assert path == "/pub/DATASETS/NOAA/G02158/masked/2024/04_Apr/"


def test_ftp_filename():
    date = datetime(2024, 4, 1)
    assert snodas_fetcher.ftp_filename(date) == "SNODAS_20240401.tar"


def test_swe_dat_filename():
    date = datetime(2024, 4, 1)
    assert snodas_fetcher.swe_dat_filename(date) == \
        "us_ssmv11034tS__T0001TTNATS2024040105HP001.dat.gz"


def test_cache_path_structure(tmp_path):
    date = datetime(2024, 4, 1)
    path = snodas_fetcher.cache_path(date, tmp_path)
    assert str(path) == str(tmp_path / "2024" / "04" / "20240401_swe.tif")


# --- Unit: date validation ---

def test_rejects_date_before_2003():
    with pytest.raises(ValueError, match="SNODAS begins October 2003"):
        snodas_fetcher.validate_date(datetime(2003, 9, 30))


def test_accepts_date_from_oct_2003():
    snodas_fetcher.validate_date(datetime(2003, 10, 1))  # no exception


def test_accepts_recent_date():
    snodas_fetcher.validate_date(datetime(2024, 4, 1))  # no exception


# --- Unit: dat binary → GeoTIFF conversion ---

def test_dat_to_geotiff_writes_correct_shape(tmp_path):
    # Create a minimal fake .dat file (3x5 int16 big-endian)
    rows, cols = 3, 5
    data = np.arange(rows * cols, dtype=">i2")
    dat_path = tmp_path / "fake.dat"
    dat_path.write_bytes(data.tobytes())

    tif_path = tmp_path / "out.tif"
    snodas_fetcher.dat_to_geotiff(dat_path, tif_path, rows=rows, cols=cols)

    with rasterio.open(tif_path) as src:
        assert src.width == cols
        assert src.height == rows
        assert src.nodata == -9999
        assert src.crs.to_epsg() == 4326


def test_dat_to_geotiff_preserves_values(tmp_path):
    test_rows, test_cols = 3, 3
    data = np.array([[100, 200, 300],
                     [400, -9999, 600],
                     [700, 800, 900]], dtype=">i2")
    dat_path = tmp_path / "slice.dat"
    dat_path.write_bytes(data.tobytes())
    tif_path = tmp_path / "out.tif"
    snodas_fetcher.dat_to_geotiff(dat_path, tif_path, rows=test_rows, cols=test_cols)

    with rasterio.open(tif_path) as src:
        arr = src.read(1)
    assert arr[0, 0] == 100
    assert arr[1, 1] == -9999


# --- Unit: cache hit avoids download ---

def test_fetch_swe_returns_cached_path_without_download(tmp_path):
    date = datetime(2024, 4, 1)
    expected = snodas_fetcher.cache_path(date, tmp_path)
    expected.parent.mkdir(parents=True)
    expected.touch()  # simulate cached file

    with patch('snodas_fetcher.download_and_extract') as mock_dl:
        result = snodas_fetcher.fetch_swe(date, cache_dir=tmp_path)
        mock_dl.assert_not_called()
    assert result == expected


# --- Unit: FTP failure raises clear error ---

def test_fetch_swe_raises_on_ftp_failure(tmp_path):
    date = datetime(2024, 4, 1)
    with patch('snodas_fetcher.download_and_extract',
               side_effect=ConnectionError("FTP timeout")):
        with pytest.raises(ConnectionError, match="FTP timeout"):
            snodas_fetcher.fetch_swe(date, cache_dir=tmp_path)


# --- Unit: HTTPS transport (SNODAS_TRANSPORT flag) ---

def test_https_url_format():
    date = datetime(2024, 4, 1)
    assert snodas_fetcher.https_url(date) == (
        "https://noaadata.apps.nsidc.org/NOAA/G02158/masked/"
        "2024/04_Apr/SNODAS_20240401.tar"
    )


def test_download_tar_dispatches_ftp_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv('SNODAS_TRANSPORT', raising=False)
    date = datetime(2024, 4, 1)
    with patch('snodas_fetcher._download_ftp') as mock_ftp, \
         patch('snodas_fetcher._download_https') as mock_https:
        snodas_fetcher._download_tar(date, tmp_path / "SNODAS_20240401.tar")
    mock_ftp.assert_called_once()
    mock_https.assert_not_called()


def test_download_tar_dispatches_https_when_flag_set(monkeypatch, tmp_path):
    monkeypatch.setenv('SNODAS_TRANSPORT', 'https')
    date = datetime(2024, 4, 1)
    with patch('snodas_fetcher._download_ftp') as mock_ftp, \
         patch('snodas_fetcher._download_https') as mock_https:
        snodas_fetcher._download_tar(date, tmp_path / "SNODAS_20240401.tar")
    mock_https.assert_called_once()
    mock_ftp.assert_not_called()


def test_https_download_writes_file(tmp_path):
    date = datetime(2024, 4, 1)
    tmp_tar = tmp_path / "SNODAS_20240401.tar"
    fake_body = b"tar-bytes-here"

    fake_resp = MagicMock()
    fake_resp.read.side_effect = [fake_body, b""]
    fake_resp.__enter__.return_value = fake_resp

    with patch('snodas_fetcher.urllib.request.urlopen',
               return_value=fake_resp) as mock_open:
        snodas_fetcher._download_https(date, tmp_tar)

    assert mock_open.call_args[0][0] == snodas_fetcher.https_url(date)
    assert tmp_tar.read_bytes() == fake_body


def test_https_download_404_raises_connection_error(tmp_path):
    import urllib.error
    date = datetime(2024, 4, 1)
    tmp_tar = tmp_path / "SNODAS_20240401.tar"
    err = urllib.error.HTTPError(
        snodas_fetcher.https_url(date), 404, "Not Found", {}, None
    )
    with patch('snodas_fetcher.urllib.request.urlopen', side_effect=err):
        with pytest.raises(ConnectionError,
                           match="SNODAS HTTPS download failed for 2024-04-01"):
            snodas_fetcher._download_https(date, tmp_tar)
    assert not tmp_tar.exists()  # no partial file left behind


def test_https_download_network_error_raises_connection_error(tmp_path):
    import urllib.error
    date = datetime(2024, 4, 1)
    tmp_tar = tmp_path / "SNODAS_20240401.tar"
    with patch('snodas_fetcher.urllib.request.urlopen',
               side_effect=urllib.error.URLError("timed out")):
        with pytest.raises(ConnectionError, match="SNODAS HTTPS download failed"):
            snodas_fetcher._download_https(date, tmp_tar)
    assert not tmp_tar.exists()


# --- Unit: fetch_latest_swe scans back for the newest available product ---

def test_fetch_latest_uses_reference_date_when_available(tmp_path):
    ref = datetime(2026, 6, 20)
    with patch('snodas_fetcher.fetch_swe', return_value=tmp_path / "x.tif") as m:
        tif, actual = snodas_fetcher.fetch_latest_swe(ref, cache_dir=tmp_path)
    assert actual == ref
    assert m.call_count == 1  # newest date preferred; no fallback needed


def test_fetch_latest_falls_back_to_previous_day(tmp_path):
    ref = datetime(2026, 6, 20)

    def side_effect(date, cache_dir=None):
        if date == ref:
            raise ConnectionError("550 Can't open SNODAS_20260620.tar")
        return tmp_path / "y.tif"

    with patch('snodas_fetcher.fetch_swe', side_effect=side_effect) as m:
        tif, actual = snodas_fetcher.fetch_latest_swe(ref, cache_dir=tmp_path)
    assert actual == ref - timedelta(days=1)
    assert m.call_count == 2


def test_fetch_latest_raises_when_nothing_in_window(tmp_path):
    ref = datetime(2026, 6, 20)
    with patch('snodas_fetcher.fetch_swe',
               side_effect=ConnectionError("nope")) as m:
        with pytest.raises(ConnectionError, match="No SNODAS product available"):
            snodas_fetcher.fetch_latest_swe(ref, cache_dir=tmp_path, max_lookback_days=3)
    assert m.call_count == 4  # deltas 0..3 inclusive
