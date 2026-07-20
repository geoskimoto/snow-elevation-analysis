"""swann_fetcher.py — UA SWANN (UA-SWE, NSIDC-0719) 4 km daily SWE.

Mirrors snodas_fetcher's interface: fetch_swe(date, cache_dir) returns a
GeoTIFF path ready for elevation_bands.compute_bands. SWANN netCDFs are
converted to SNODAS conventions (int16 mm, nodata -9999) so the rest of the
pipeline is dataset-agnostic.

Source (verified live 2026-07-20; no authentication required):
    https://climate.arizona.edu/data/UA_SWE/
Daily files carry exactly one lifecycle suffix — stable, provisional, or
early (newest, ~1-2 day latency) — so download tries each in that order.
Water-year bulk files (WYData_4km/) exist for WY1982-WY2023 and are used by
the backfill; later years fall back to daily files.
"""

import shutil
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import rasterio

from timeseries import water_year

SWANN_BASE = "https://climate.arizona.edu/data/UA_SWE"
SWANN_TIMEOUT_S = 120
SWANN_SRC_NODATA = -999
OUT_NODATA = -9999          # SNODAS convention; lets compute_bands run unchanged
SWANN_START = datetime(1981, 10, 1)
SWANN_RES_DEG = 0.0416667   # ~4 km grid, verified live 2026-07-20
SWANN_RES_TOL_DEG = 1e-4

_SUFFIXES = ("stable", "provisional", "early")
_DEFAULT_CACHE = Path(__file__).parent / "data" / "cache"


def validate_date(date: datetime) -> None:
    if date < SWANN_START:
        raise ValueError(
            f"SWANN begins October 1981; requested date {date.date()} is too early."
        )


def cache_path(date: datetime, cache_dir: Path = _DEFAULT_CACHE) -> Path:
    return (cache_dir / "swann" / f"{date.year}" / f"{date.month:02d}"
            / f"{date.strftime('%Y%m%d')}_swe.tif")


def daily_url(date: datetime, suffix: str) -> str:
    return (f"{SWANN_BASE}/DailyData_4km/WY{water_year(date)}/"
            f"UA_SWE_Depth_4km_v1_{date.strftime('%Y%m%d')}_{suffix}.nc")


def wy_url(wy: int) -> str:
    return f"{SWANN_BASE}/WYData_4km/UA_SWE_Depth_WY{wy}.nc"


def _urlretrieve(url: str, dest: Path) -> None:
    """Stream url to dest; raises urllib.error.HTTPError on non-200."""
    with urllib.request.urlopen(url, timeout=SWANN_TIMEOUT_S) as resp, \
            open(dest, "wb") as f:
        shutil.copyfileobj(resp, f)


def nc_to_geotiff(nc_path: Path, tif_path: Path,
                  variable: str | None = "SWE", band: int = 1) -> None:
    """Convert one band of a SWANN netCDF to a SNODAS-convention GeoTIFF.

    variable=None opens the file directly (single-variable netCDF, as GDAL
    writes in tests); production files need the 'SWE' subdataset. band picks
    the day out of a multi-day water-year file (1-based).
    """
    src_path = f"netcdf:{nc_path}:{variable}" if variable else str(nc_path)
    with rasterio.open(src_path) as src:
        # Ingest validation — SWANN units/orientation/nodata conventions are
        # verified before conversion; a drift here (grid change, reprojection,
        # different nodata sentinel) must fail loudly rather than silently
        # produce a mis-scaled or mis-oriented raster downstream.
        if src.dtypes[0] != "int16":
            raise ValueError(
                f"SWANN ingest validation failed: expected dtype int16, "
                f"got {src.dtypes[0]!r} ({nc_path})")
        if src.nodata is not None and src.nodata != SWANN_SRC_NODATA:
            raise ValueError(
                f"SWANN ingest validation failed: expected nodata "
                f"{SWANN_SRC_NODATA}, got {src.nodata!r} ({nc_path})")
        if abs(abs(src.transform.a) - SWANN_RES_DEG) >= SWANN_RES_TOL_DEG:
            raise ValueError(
                f"SWANN ingest validation failed: expected pixel size "
                f"~{SWANN_RES_DEG} deg (x), got {src.transform.a!r} ({nc_path})")
        if abs(abs(src.transform.e) - SWANN_RES_DEG) >= SWANN_RES_TOL_DEG:
            raise ValueError(
                f"SWANN ingest validation failed: expected pixel size "
                f"~{SWANN_RES_DEG} deg (y), got {src.transform.e!r} ({nc_path})")
        if src.transform.e >= 0:
            raise ValueError(
                f"SWANN ingest validation failed: expected north-up raster "
                f"(transform.e < 0), got {src.transform.e!r} ({nc_path})")

        arr = src.read(band).astype(np.int16)
        src_nodata = src.nodata if src.nodata is not None else SWANN_SRC_NODATA
        arr[arr == src_nodata] = OUT_NODATA
        profile = {
            "driver": "GTiff", "height": src.height, "width": src.width,
            "count": 1, "dtype": "int16", "crs": src.crs,
            "transform": src.transform, "nodata": OUT_NODATA, "compress": "lzw",
        }
    tif_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(tif_path, "w", **profile) as dst:
        dst.write(arr, 1)


def _download_daily_nc(date: datetime, dest: Path) -> None:
    """Download the daily file, trying stable -> provisional -> early."""
    last_error: Exception | None = None
    for suffix in _SUFFIXES:
        url = daily_url(date, suffix)
        try:
            _urlretrieve(url, dest)
            return
        except urllib.error.HTTPError as e:
            last_error = e
            if dest.exists():
                dest.unlink()
            if e.code == 404:
                continue
            raise ConnectionError(
                f"SWANN download failed for {date.date()} ({url}): {e}") from e
        except OSError as e:
            if dest.exists():
                dest.unlink()
            raise ConnectionError(
                f"SWANN download failed for {date.date()} ({url}): {e}") from e
    raise ConnectionError(
        f"No SWANN daily file (stable/provisional/early) for {date.date()}"
    ) from last_error


def fetch_swe(date: datetime, cache_dir: Path = _DEFAULT_CACHE) -> Path:
    validate_date(date)
    tif = cache_path(date, cache_dir)
    if tif.exists():
        return tif
    tif.parent.mkdir(parents=True, exist_ok=True)
    tmp_nc = tif.parent / f"{date.strftime('%Y%m%d')}_swann.nc"
    try:
        _download_daily_nc(date, tmp_nc)
        nc_to_geotiff(tmp_nc, tif)
    except Exception:
        if tif.exists():
            tif.unlink()
        raise
    finally:
        if tmp_nc.exists():
            tmp_nc.unlink()
    return tif


def fetch_latest_swe(
    reference_date: datetime,
    cache_dir: Path = _DEFAULT_CACHE,
    max_lookback_days: int = 5,
) -> tuple[Path, datetime]:
    """Most recent available SWANN SWE at or before reference_date.

    SWANN publishes with ~1-2 day latency, so the daily cron scans backward
    like snodas_fetcher.fetch_latest_swe does.
    """
    last_error: Exception | None = None
    for delta in range(max_lookback_days + 1):
        candidate = reference_date - timedelta(days=delta)
        try:
            return fetch_swe(candidate, cache_dir=cache_dir), candidate
        except (ConnectionError, RuntimeError) as exc:
            last_error = exc
            continue
    raise ConnectionError(
        f"No SWANN product available within {max_lookback_days} days of "
        f"{reference_date.date()}"
    ) from last_error


def download_wy_nc(wy: int, dest_dir: Path) -> Path:
    """Download the WY bulk file (~95 MB). FileNotFoundError on 404 signals
    the caller (backfill) to fall back to daily files for that year."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"UA_SWE_Depth_WY{wy}.nc"
    if dest.exists():
        return dest
    url = wy_url(wy)
    try:
        _urlretrieve(url, dest)
    except urllib.error.HTTPError as e:
        if dest.exists():
            dest.unlink()
        if e.code == 404:
            raise FileNotFoundError(f"No SWANN WY file for WY{wy} ({url})") from e
        raise ConnectionError(f"SWANN WY download failed ({url}): {e}") from e
    except OSError as e:
        if dest.exists():
            dest.unlink()
        raise ConnectionError(f"SWANN WY download failed ({url}): {e}") from e
    return dest
