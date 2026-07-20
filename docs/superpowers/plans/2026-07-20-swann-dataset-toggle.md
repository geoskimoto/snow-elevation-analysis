# SWANN Dataset Toggle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the UA SWANN dataset (4 km daily SWE, WY1982–present) as a second, fully parallel dataset with a global toggle switching all three tabs between SNODAS and SWANN.

**Architecture:** A new `swann_fetcher.py` mirrors `snodas_fetcher.py`'s interface and converts SWANN netCDF to SNODAS-convention GeoTIFFs (mm, int16, nodata −9999) so `compute_bands` and `dem_processor` are reused unchanged. A tiny `datasets.py` registry maps dataset key → fetcher/labels/DEM path; `timeseries`/`climatology`/`pipeline` gain a `dataset='snodas'` parameter that routes to parallel cache subtrees (`bands/swann/`, `timeseries/swann/`). A header radio threads the dataset key through all callbacks.

**Tech Stack:** Python 3.12, Dash/Plotly, rasterio (GDAL netCDF driver — the venv has **no** netCDF4/h5netcdf engine, so all netCDF access goes through `rasterio.open('netcdf:<path>:<var>')`), pandas/parquet, pytest.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-20-swann-dataset-toggle-design.md`. Datasets are compared, never combined: no mixed parquets, no cross-dataset math.
- Python is ALWAYS `venv/bin/python` (system python lacks the deps).
- Run the full suite before every commit: `venv/bin/python -m pytest tests/` — tests are updated in the SAME commit as the behavior change they cover.
- **Never modify application code to make failing tests pass; never modify a task's test file after writing it in order to make implementation pass.** If a test fails unexpectedly, stop and report.
- All files must be owned `geoskimoto:geoskimoto`. If running as root: run git via `sudo -u geoskimoto git ...` and after any root file write run `sudo chown -R geoskimoto:geoskimoto /home/geoskimoto/projects/snow_elevation_plot`.
- Commit messages: `<tag>: <summary>` (`feat`, `fix`, `test`, `docs`, `chore`).
- SNODAS behavior must be byte-for-byte unchanged when `dataset='snodas'` (the default everywhere).
- Existing SNODAS paths never move: `data/cache/timeseries/WY*.parquet`, `data/cache/bands/*.parquet`, `data/cache/dem/columbia_basin_swe_aligned.tif`.

## Verified SWANN facts (checked live 2026-07-20 — do not re-derive from memory)

- Base URL: `https://climate.arizona.edu/data/UA_SWE/` — **no authentication** (no Earthdata login; the spec's NSIDC/Earthdata path is unnecessary — the UA portal hosts the same product, per its Readme).
- Water-year files (backfill): `WYData_4km/UA_SWE_Depth_WY{yyyy}.nc`, available WY1982–WY2023, ~95 MB each, one time-band per day.
- Daily files (cron + recent years): `DailyData_4km/WY{wy}/UA_SWE_Depth_4km_v1_{yyyymmdd}_{suffix}.nc` where suffix is exactly one of `stable` | `provisional` | `early` per date (lifecycle: early → provisional → stable). Latency ~1–2 days. WY2024, WY2025, WY2026 exist only as daily files.
- netCDF subdatasets: `time_str`, `SWE`, `DEPTH`. Open via `rasterio.open(f'netcdf:{path}:SWE')`.
- SWE grid: 621×1405, CRS EPSG:4269, res 0.0416667°, transform origin (−125.0208, 49.9375), north-up, dtype int16, nodata **−999**, units mm. Band tag `NETCDF_DIM_time` = days since 1900-01-01.
- A URL for a nonexistent file returns an HTTP 404 HTML page (~265 bytes) — the fetcher must check status, never trust a 200-length body blindly.

## File Structure

- Create `swann_fetcher.py` — download/convert SWANN daily + WY netCDF → GeoTIFF; `fetch_swe`, `fetch_latest_swe` mirroring snodas_fetcher.
- Create `datasets.py` — registry: key → label, footnote, start date, fetchers, DEM filename.
- Create `tests/test_swann_fetcher.py`, `tests/test_datasets.py`, `tests/test_update_timeseries.py`.
- Modify `timeseries.py`, `climatology.py` — `dataset` param → subtree routing (rule: non-`snodas` datasets live in a subdir named after the dataset key).
- Modify `pipeline.py` — `dataset` param (fetcher, band-cache subdir, DEM path, output subdir, chart labels).
- Modify `charts.py` — `dataset_label` on all figure factories; `record_label` on climatology figure.
- Modify `layout.py`, `callbacks.py` — header radio `dataset-select`, per-dataset date bounds, footnotes, empty states, downloads.
- Modify `update_timeseries.py` — process both datasets per run.
- Modify `populate_timeseries.py` — `--dataset swann` bulk backfill from WY files with daily-file fallback.
- Modify `.gitignore` — ship the SWANN DEM; verify `timeseries/swann/` is already un-ignored.
- Modify matching test files in the same commits: `test_timeseries.py`, `test_climatology.py`, `test_pipeline.py`, `test_charts.py`, `test_layout.py`, `test_callbacks.py`, `test_populate_timeseries.py`.

Note: the spec names the band cache `bands/swann/{YYYYMMDD}_4km.parquet`; the existing suffix `_250m` denotes the **elevation-band interval** (250 m), not raster resolution, and SWANN uses the same 250 m bands — so the plan keeps `bands/swann/{YYYYMMDD}_250m.parquet` for consistency. This is a deliberate, documented deviation.

---

### Task 1: `swann_fetcher.py`

**Files:**
- Create: `swann_fetcher.py`
- Test: `tests/test_swann_fetcher.py`

**Interfaces:**
- Consumes: `timeseries.water_year(date) -> int` (existing).
- Produces:
  - `SWANN_START = datetime(1981, 10, 1)`; `SWANN_BASE = "https://climate.arizona.edu/data/UA_SWE"`
  - `validate_date(date: datetime) -> None` (raises ValueError before SWANN_START)
  - `cache_path(date, cache_dir) -> Path` → `{cache_dir}/swann/{yyyy}/{mm}/{yyyymmdd}_swe.tif`
  - `daily_url(date: datetime, suffix: str) -> str`
  - `wy_url(wy: int) -> str`
  - `nc_to_geotiff(nc_path: Path, tif_path: Path, variable: str | None = 'SWE', band: int = 1) -> None` (remaps nodata −999 → −9999, writes int16 LZW GeoTIFF, preserves source CRS/transform)
  - `fetch_swe(date: datetime, cache_dir: Path) -> Path`
  - `fetch_latest_swe(reference_date, cache_dir, max_lookback_days=5) -> tuple[Path, datetime]`
  - `download_wy_nc(wy: int, dest_dir: Path) -> Path` (raises FileNotFoundError on HTTP 404 → caller falls back to daily files)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_swann_fetcher.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_swann_fetcher.py -v`
Expected: FAIL / errors with `ModuleNotFoundError: No module named 'swann_fetcher'`

- [ ] **Step 3: Write the implementation**

Create `swann_fetcher.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_swann_fetcher.py -v`
Expected: all PASS

- [ ] **Step 5: Full suite, then commit**

Run: `venv/bin/python -m pytest tests/`
Expected: no new failures.

```bash
sudo -u geoskimoto git add swann_fetcher.py tests/test_swann_fetcher.py
sudo -u geoskimoto git commit -m "feat: add SWANN 4km SWE fetcher mirroring snodas_fetcher interface"
```

---

### Task 2: `datasets.py` registry + dataset-aware `timeseries`/`climatology`

**Files:**
- Create: `datasets.py`
- Modify: `timeseries.py` (`_parquet_path`, `append_volumes`, `load_timeseries`)
- Modify: `climatology.py` (`load_all_water_years`)
- Test: `tests/test_datasets.py`; extend `tests/test_timeseries.py`, `tests/test_climatology.py`

**Interfaces:**
- Consumes: `snodas_fetcher.fetch_swe/fetch_latest_swe`, `swann_fetcher.fetch_swe/fetch_latest_swe`.
- Produces:
  - `datasets.get(key: str) -> dict` with keys: `label`, `footnote`, `start` (datetime), `fetch_swe`, `fetch_latest_swe`, `dem_filename`. Raises `KeyError` on unknown key. Valid keys: `'snodas'`, `'swann'`.
  - `timeseries.append_volumes(date, bands_by_basin, cache_dir, dataset='snodas')`
  - `timeseries.load_timeseries(wy, cache_dir, dataset='snodas')`
  - `climatology.load_all_water_years(cache_dir, dataset='snodas')`
  - Routing rule (documented in both modules): `dataset='snodas'` → existing paths; any other key → `timeseries/{dataset}/` subdir. `timeseries`/`climatology` do NOT import `datasets` (avoids an import cycle through `swann_fetcher` → `timeseries`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_datasets.py`:

```python
from datetime import datetime

import pytest

import datasets


def test_registry_has_both_datasets():
    assert set(datasets.DATASETS) == {"snodas", "swann"}


def test_snodas_entry():
    d = datasets.get("snodas")
    assert d["start"] == datetime(2003, 10, 1)
    assert "SNODAS" in d["label"] and "1 km" in d["label"]
    assert d["dem_filename"] == "columbia_basin_swe_aligned.tif"
    assert callable(d["fetch_swe"]) and callable(d["fetch_latest_swe"])


def test_swann_entry():
    d = datasets.get("swann")
    assert d["start"] == datetime(1981, 10, 1)
    assert "SWANN" in d["label"] and "4 km" in d["label"]
    assert d["dem_filename"] == "columbia_basin_swann_aligned.tif"
    assert "4 km" in d["footnote"]


def test_unknown_dataset_raises():
    with pytest.raises(KeyError):
        datasets.get("modis")
```

Append to `tests/test_timeseries.py`:

```python
def test_append_and_load_swann_dataset_routes_to_subdir(tmp_path):
    import pandas as pd
    from datetime import datetime
    from timeseries import append_volumes, load_timeseries

    bands = {"Columbia River Basin": pd.DataFrame({
        "elev_band_m": [1000], "mean_swe_mm": [100.0],
        "area_km2": [50.0], "total_swe_volume_km3": [0.005],
    })}
    append_volumes(datetime(2026, 1, 15), bands, tmp_path, dataset="swann")

    assert (tmp_path / "timeseries" / "swann" / "WY2026_volume.parquet").exists()
    # default (snodas) tree untouched
    assert not (tmp_path / "timeseries" / "WY2026_volume.parquet").exists()

    df = load_timeseries(2026, tmp_path, dataset="swann")
    assert len(df) == 1
    assert load_timeseries(2026, tmp_path).empty          # snodas view is empty
```

Append to `tests/test_climatology.py`:

```python
def test_load_all_water_years_swann_reads_subdir_only(tmp_path):
    import pandas as pd
    from datetime import datetime
    from climatology import load_all_water_years
    from timeseries import append_volumes

    bands = {"Columbia River Basin": pd.DataFrame({
        "elev_band_m": [1000], "mean_swe_mm": [100.0],
        "area_km2": [50.0], "total_swe_volume_km3": [0.005],
    })}
    append_volumes(datetime(1999, 1, 15), bands, tmp_path, dataset="swann")
    append_volumes(datetime(2026, 1, 15), bands, tmp_path)  # snodas

    swann = load_all_water_years(tmp_path, dataset="swann")
    assert sorted(swann["wy"].unique()) == [1999]
    snodas = load_all_water_years(tmp_path)
    assert sorted(snodas["wy"].unique()) == [2026]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_datasets.py tests/test_timeseries.py tests/test_climatology.py -v`
Expected: new tests FAIL (`ModuleNotFoundError: datasets`, `TypeError: unexpected keyword argument 'dataset'`).

- [ ] **Step 3: Implement**

Create `datasets.py`:

```python
"""datasets.py — registry of gridded SWE datasets the app can analyze.

Single source of truth for dataset routing: labels, record start, fetcher
functions, and DEM cache filename. Cache-subtree routing itself lives in
timeseries/climatology/pipeline via the convention "non-'snodas' datasets
use a subdir named after the dataset key" — those modules deliberately do
not import this one (swann_fetcher imports timeseries, so an import here
would cycle).
"""

from datetime import datetime

import snodas_fetcher
import swann_fetcher

DATASETS = {
    "snodas": {
        "label": "SNODAS (~1 km)",
        "start": datetime(2003, 10, 1),
        "dem_filename": "columbia_basin_swe_aligned.tif",
        "fetch_swe": snodas_fetcher.fetch_swe,
        "fetch_latest_swe": snodas_fetcher.fetch_latest_swe,
        "footnote": (
            "NOAA SNODAS (~1 km daily gridded SWE, WY2004-present). Assimilates "
            "SNOTEL/COOP ground stations with meteorological model forcing. "
            "Limitations: Station network thins above ~7,000 ft, leading to "
            "underestimation of deep mountain snowpack (published bias: 20-40% low "
            "in high-elevation basins). Glacier pixels are excluded."
        ),
    },
    "swann": {
        "label": "SWANN (4 km)",
        "start": datetime(1981, 10, 1),
        "dem_filename": "columbia_basin_swann_aligned.tif",
        "fetch_swe": swann_fetcher.fetch_swe,
        "fetch_latest_swe": swann_fetcher.fetch_latest_swe,
        "footnote": (
            "UA SWANN / UA-SWE (4 km daily gridded SWE, WY1982-present). "
            "Interpolates SNOTEL and COOP observations using PRISM "
            "temperature/precipitation gradients. Limitations: 4 km pixels span "
            "wide elevation ranges in steep terrain, so per-elevation-band SWE is "
            "smeared and hypsometric curves are coarser than SNODAS (~1 km)."
        ),
    },
}


def get(dataset: str) -> dict:
    if dataset not in DATASETS:
        raise KeyError(
            f"Unknown dataset '{dataset}'; expected one of {sorted(DATASETS)}")
    return DATASETS[dataset]
```

Modify `timeseries.py` — replace `_parquet_path` and thread `dataset`:

```python
def _parquet_path(wy: int, cache_dir: Path, dataset: str = 'snodas') -> Path:
    # Routing rule shared with climatology/pipeline: the default dataset keeps
    # its historical location; any other dataset gets a subdir named after it.
    base = cache_dir / 'timeseries'
    if dataset != 'snodas':
        base = base / dataset
    return base / f'WY{wy}_volume.parquet'
```

In `append_volumes`, change the signature to
`def append_volumes(date, bands_by_basin, cache_dir, dataset: str = 'snodas') -> None:`
and the path line to `path = _parquet_path(wy, cache_dir, dataset)`.
In `load_timeseries`, change to
`def load_timeseries(wy, cache_dir, dataset: str = 'snodas') -> pd.DataFrame:`
and `path = _parquet_path(wy, cache_dir, dataset)`. Update both docstrings to mention the parameter.

Modify `climatology.py` — `load_all_water_years`:

```python
def load_all_water_years(cache_dir: Path, dataset: str = 'snodas') -> pd.DataFrame:
```

and its first lines:

```python
    ts_dir = Path(cache_dir) / 'timeseries'
    if dataset != 'snodas':
        ts_dir = ts_dir / dataset
    if not ts_dir.exists():
        return _empty_df()
```

(The glob loop is unchanged — it is non-recursive, so the snodas view never picks up `swann/` files and vice versa.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_datasets.py tests/test_timeseries.py tests/test_climatology.py -v`
Expected: all PASS.

- [ ] **Step 5: Full suite, then commit**

Run: `venv/bin/python -m pytest tests/`

```bash
sudo -u geoskimoto git add datasets.py timeseries.py climatology.py tests/test_datasets.py tests/test_timeseries.py tests/test_climatology.py
sudo -u geoskimoto git commit -m "feat: dataset registry + dataset-namespaced timeseries/climatology subtrees"
```

---

### Task 3: dataset-aware `pipeline.py`

**Files:**
- Modify: `pipeline.py`
- Test: extend `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `datasets.get`, Task 2's `timeseries.append_volumes(..., dataset=)`.
- Produces:
  - `pipeline._cache_path(date_key, cache_dir, dataset='snodas') -> Path` (band cache; `bands/swann/{date}_250m.parquet` for swann)
  - `pipeline.save_band_cache(bands_by_basin, date_key, cache_dir, dataset='snodas')`
  - `pipeline.load_band_cache(date_key, cache_dir, dataset='snodas')`
  - `pipeline.run_pipeline(date_str, set_progress=None, dataset='snodas') -> dict` (same result keys as today)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_pipeline.py`:

```python
def test_band_cache_swann_routes_to_subdir(tmp_path):
    import pandas as pd
    from pipeline import save_band_cache, load_band_cache

    bands = {"Columbia River Basin": pd.DataFrame({
        "elev_band_m": [1000], "mean_swe_mm": [100.0],
        "area_km2": [50.0], "total_swe_volume_km3": [0.005],
    })}
    save_band_cache(bands, "20260115", tmp_path, dataset="swann")
    assert (tmp_path / "bands" / "swann" / "20260115_250m.parquet").exists()
    assert not (tmp_path / "bands" / "20260115_250m.parquet").exists()

    loaded = load_band_cache("20260115", tmp_path, dataset="swann")
    assert "Columbia River Basin" in loaded
    assert load_band_cache("20260115", tmp_path) is None  # snodas view empty


def test_run_pipeline_routes_fetcher_by_dataset(tmp_path, monkeypatch):
    """run_pipeline(dataset='swann') must call the SWANN fetcher, not SNODAS."""
    import pipeline
    import datasets

    called = {}

    def fake_swann_fetch(date, cache_dir):
        called["swann"] = True
        raise ConnectionError("stop here — routing verified")

    def fake_snodas_fetch(date, cache_dir):
        called["snodas"] = True
        raise ConnectionError("stop here")

    monkeypatch.setitem(datasets.DATASETS["swann"], "fetch_swe", fake_swann_fetch)
    monkeypatch.setitem(datasets.DATASETS["snodas"], "fetch_swe", fake_snodas_fetch)

    result = pipeline.run_pipeline("2026-01-15", dataset="swann")
    assert called == {"swann": True}
    assert result["error"] is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_pipeline.py -v`
Expected: new tests FAIL (`TypeError: unexpected keyword argument 'dataset'`).

- [ ] **Step 3: Implement**

In `pipeline.py`:

1. Add `import datasets` after `import config`.
2. Replace the three cache functions' signatures and path logic:

```python
def _cache_path(date_key: str, cache_dir: Path, dataset: str = 'snodas') -> Path:
    base = cache_dir / 'bands'
    if dataset != 'snodas':
        base = base / dataset
    return base / f'{date_key}_250m.parquet'


def save_band_cache(bands_by_basin: dict, date_key: str, cache_dir: Path,
                    dataset: str = 'snodas') -> None:
    path = _cache_path(date_key, cache_dir, dataset)
    ...  # body unchanged


def load_band_cache(date_key: str, cache_dir: Path,
                    dataset: str = 'snodas') -> dict | None:
    path = _cache_path(date_key, cache_dir, dataset)
    ...  # body unchanged
```

3. `run_pipeline` — new signature `def run_pipeline(date_str: str, set_progress=None, dataset: str = 'snodas') -> dict:` and inside the try block:

```python
        ds = datasets.get(dataset)
        date = datetime.strptime(date_str, '%Y-%m-%d')
        date_key = date.strftime('%Y%m%d')
        cache_dir = config.get_cache_dir()
        output_dir = config.get_output_dir()
        if dataset != 'snodas':
            output_dir = output_dir / dataset   # PNG stems collide otherwise

        _progress(1, 5, f'Fetching {ds["label"]} data...')
        swe_tif = ds['fetch_swe'](date, cache_dir=cache_dir)
        ...
        dem_tif = get_aligned_dem(swe_tif, dem_cache=cache_dir / 'dem' / ds['dem_filename'])
        ...
        cached = load_band_cache(date_key, cache_dir, dataset)
        # (both save_band_cache and append_volumes calls gain dataset=dataset)
```

4. The `from snodas_fetcher import fetch_swe` import at the top becomes unused — remove it.
5. Chart calls gain the label (Task 4 adds the parameter; this task passes it):
   `make_huc2_figure(huc2_df, date, dataset_label=ds['label'])` etc. — **do this in Task 4's commit** if Task 4 is not yet done; otherwise here. To keep tasks independent: in THIS task call charts exactly as before, and Task 4 updates the call sites. 

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_pipeline.py -v`
Expected: all PASS.

- [ ] **Step 5: Full suite, then commit**

Run: `venv/bin/python -m pytest tests/`

```bash
sudo -u geoskimoto git add pipeline.py tests/test_pipeline.py
sudo -u geoskimoto git commit -m "feat: dataset-aware pipeline (fetcher routing, band-cache subtree, per-dataset DEM and output dir)"
```

---

### Task 4: dataset labels in `charts.py`

**Files:**
- Modify: `charts.py`, `pipeline.py` (call sites)
- Test: extend `tests/test_charts.py`

**Interfaces:**
- Produces (all keyword-only additions, defaults preserve current SNODAS output):
  - `make_huc2_figure(df, date, dataset_label='SNODAS (~1 km)')`
  - `make_huc4_figure(bands_by_subbasin, date, dataset_label='SNODAS (~1 km)')`
  - `make_huc2_volume_figure(df, date, dataset_label='SNODAS (~1 km)')`
  - `make_huc4_volume_figure(bands_by_subbasin, date, dataset_label='SNODAS (~1 km)')`
  - `make_basin_timeseries_figure(df, wy, dataset_label='SNODAS (~1 km)')`
  - `make_huc4_timeseries_figure(df, wy, dataset_label='SNODAS (~1 km)')`
  - `make_climatology_figure(clim_df, current_df, basin_label, wy, summary=None, dataset_label='SNODAS (~1 km)', record_label='')`
  - Every figure title's first line ends with ` · {dataset_label}`; the climatology title additionally shows `record_label` (e.g. `WY2004–WY2025 envelope`) in its `<sub>`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_charts.py`:

```python
def test_all_figures_carry_dataset_label():
    from datetime import datetime
    import pandas as pd
    import charts

    bands = pd.DataFrame({
        "elev_band_m": [1000, 1250], "mean_swe_mm": [100.0, 200.0],
        "area_km2": [50.0, 60.0], "total_swe_volume_km3": [0.005, 0.012],
    })
    ts = pd.DataFrame({
        "date": pd.to_datetime(["2026-01-01", "2026-01-02"]),
        "basin": ["Columbia River Basin"] * 2,
        "total_swe_volume_km3": [1.0, 1.1],
    })
    d = datetime(2026, 1, 15)
    label = "SWANN (4 km)"

    figs = [
        charts.make_huc2_figure(bands, d, dataset_label=label),
        charts.make_huc4_figure({"A": bands}, d, dataset_label=label),
        charts.make_huc2_volume_figure(bands, d, dataset_label=label),
        charts.make_huc4_volume_figure({"A": bands}, d, dataset_label=label),
        charts.make_basin_timeseries_figure(ts, 2026, dataset_label=label),
        charts.make_huc4_timeseries_figure(
            ts.assign(basin="Yakima"), 2026, dataset_label=label),
    ]
    for fig in figs:
        assert label in fig.layout.title.text


def test_default_dataset_label_is_snodas():
    from datetime import datetime
    import pandas as pd
    import charts

    bands = pd.DataFrame({
        "elev_band_m": [1000], "mean_swe_mm": [100.0],
        "area_km2": [50.0], "total_swe_volume_km3": [0.005],
    })
    fig = charts.make_huc2_figure(bands, datetime(2026, 1, 15))
    assert "SNODAS" in fig.layout.title.text


def test_climatology_figure_shows_dataset_and_record_label():
    import pandas as pd
    import charts

    clim = pd.DataFrame({
        "dow": [1, 2],
        "ref_date": pd.to_datetime(["2022-10-01", "2022-10-02"]),
        "min": [0.1, 0.1], "p10": [0.2, 0.2], "p25": [0.3, 0.3],
        "p50": [0.5, 0.5], "p75": [0.7, 0.7], "p90": [0.8, 0.8],
        "max": [1.0, 1.0], "n": [10, 10],
    })
    fig = charts.make_climatology_figure(
        clim, None, "Columbia River Basin", 2026,
        dataset_label="SWANN (4 km)", record_label="WY1982–WY2025 envelope")
    assert "SWANN (4 km)" in fig.layout.title.text
    assert "WY1982" in fig.layout.title.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_charts.py -v`
Expected: new tests FAIL (`TypeError: unexpected keyword argument 'dataset_label'`).

- [ ] **Step 3: Implement**

In `charts.py`, add module constant `_DEFAULT_DATASET_LABEL = 'SNODAS (~1 km)'`, then for each factory add the keyword parameter and fold the label into the title's first line:

```python
def make_huc2_figure(df: pd.DataFrame, date: datetime,
                     dataset_label: str = _DEFAULT_DATASET_LABEL) -> go.Figure:
    ...
    title=dict(text=f'Columbia Basin — SWE by Elevation · {dataset_label}<br>{date_label}', ...)
```

Same pattern for `make_huc4_figure` (`HUC4 Subbasins — SWE by Elevation · {dataset_label}`), `make_huc2_volume_figure` (`Columbia Basin — Volume by Elevation · {dataset_label}`), `make_huc4_volume_figure`, `make_basin_timeseries_figure` (`Columbia Basin — SWE Volume WY{wy} · {dataset_label}`), `make_huc4_timeseries_figure`.

`make_climatology_figure` gains `dataset_label: str = _DEFAULT_DATASET_LABEL, record_label: str = ''` and builds its title as:

```python
    title = f'{basin_label} — SWE Climatology · {dataset_label}'
    sub_parts = []
    if record_label:
        sub_parts.append(record_label)
    if summary:
        sub_parts.append(
            f'WY{wy}: {summary["pct_of_median"]:.0f}% of median · '
            f'ranked {summary["rank_from_bottom"]} of {summary["total_years"]} years '
            f'(as of {summary["as_of"]:%b %d})')
    if sub_parts:
        title += '<br><sub>' + ' · '.join(sub_parts) + '</sub>'
```

In `pipeline.py` `run_pipeline`, pass the label to all four chart calls, e.g. `make_huc2_figure(huc2_df, date, dataset_label=ds['label'])`.

**Existing chart tests that assert exact title strings will now fail — that is an intended behavior change (title format gained the label). Update those assertions to the new titles in the SAME commit; do not weaken them (keep exact-match style).**

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_charts.py tests/test_pipeline.py -v`
Expected: all PASS.

- [ ] **Step 5: Full suite, then commit**

Run: `venv/bin/python -m pytest tests/`

```bash
sudo -u geoskimoto git add charts.py pipeline.py tests/test_charts.py
sudo -u geoskimoto git commit -m "feat: dataset labels on all figures so screenshots can't be misattributed"
```

---

### Task 5: layout + callbacks toggle

**Files:**
- Modify: `layout.py`, `callbacks.py`
- Test: extend `tests/test_layout.py`, `tests/test_callbacks.py`

**Interfaces:**
- Consumes: `datasets.get`, Task 2–4 signatures.
- Produces:
  - Layout: `dcc.RadioItems(id='dataset-select', value='snodas')` in the header with options `snodas`/`swann`; `date-picker` gains `min_date_allowed`; the Snowpack footnote paragraph gets `id='snowpack-footnote'`.
  - `callbacks.build_historical_view(df, wy, basin, dataset='snodas') -> tuple[go.Figure, str]` — labels from `datasets.get(dataset)`, per-dataset empty-state messages.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_layout.py`:

```python
def test_dataset_selector_present_with_snodas_default():
    from layout import get_layout

    layout = get_layout()

    def find(component, cid):
        if getattr(component, "id", None) == cid:
            return component
        children = getattr(component, "children", None)
        if children is None:
            return None
        if not isinstance(children, (list, tuple)):
            children = [children]
        for child in children:
            if hasattr(child, "to_plotly_json"):
                found = find(child, cid)
                if found is not None:
                    return found
        return None

    radio = find(layout, "dataset-select")
    assert radio is not None
    assert radio.value == "snodas"
    assert {o["value"] for o in radio.options} == {"snodas", "swann"}

    picker = find(layout, "date-picker")
    assert picker.min_date_allowed is not None

    assert find(layout, "snowpack-footnote") is not None
```

Append to `tests/test_callbacks.py`:

```python
def test_build_historical_view_swann_empty_names_backfill():
    import callbacks
    from climatology import _empty_df

    fig, caption = callbacks.build_historical_view(
        _empty_df(), 2026, "Columbia River Basin", dataset="swann")
    text = fig.layout.annotations[0].text
    assert "swann" in text.lower()
    assert "--dataset swann" in text


def test_build_historical_view_labels_dataset(tmp_path):
    import pandas as pd
    import callbacks

    rows = []
    for wy in (2004, 2005, 2006, 2007):
        for day in ("01-10", "01-11", "01-12"):
            rows.append({"date": pd.Timestamp(f"{wy}-{day}"),
                         "basin": "Columbia River Basin",
                         "total_swe_volume_km3": 1.0 + wy % 3, "wy": wy})
    df = pd.DataFrame(rows)
    fig, caption = callbacks.build_historical_view(
        df, 2026, "Columbia River Basin", dataset="swann")
    assert "SWANN (4 km)" in fig.layout.title.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_layout.py tests/test_callbacks.py -v`
Expected: new tests FAIL.

- [ ] **Step 3: Implement layout**

In `layout.py`:

1. Add `from dash import dcc, html` (already imported) and `import datasets` at top.
2. Header bar — replace the header `html.Div([...])` children list with:

```python
            html.H2('Snow Elevation Analysis',
                    style={'margin': '0', 'color': '#333', 'fontSize': '1.2rem'}),
            dcc.RadioItems(
                id='dataset-select',
                options=[
                    {'label': datasets.get('snodas')['label'], 'value': 'snodas'},
                    {'label': datasets.get('swann')['label'], 'value': 'swann'},
                ],
                value='snodas',
                inline=True,
                style={'fontSize': '0.85rem', 'color': '#333'},
                inputStyle={'marginRight': '0.3rem', 'marginLeft': '0.9rem'},
            ),
```

3. Date picker gains bounds (default dataset = SNODAS):

```python
                dcc.DatePickerSingle(
                    id='date-picker',
                    date=today,
                    min_date_allowed=datasets.get('snodas')['start'].date().isoformat(),
                    max_date_allowed=today,
                    display_format='YYYY-MM-DD',
                    style={'marginBottom': '1rem'},
                ),
```

4. Snowpack footnote — replace the static `html.P([...])` block with a container whose default content is the SNODAS footnote and which a callback can rewrite:

```python
                            html.Div([
                                html.P([
                                    html.Strong('Data: '),
                                    datasets.get('snodas')['footnote'],
                                ], style={'margin': '0'}),
                            ], id='snowpack-footnote', style={
                                'fontSize': '0.75rem', 'color': '#666', 'lineHeight': '1.5',
                                'borderTop': '1px solid #ddd', 'paddingTop': '0.6rem',
                            }),
```

- [ ] **Step 4: Implement callbacks**

In `callbacks.py`:

1. Add `import datasets` and `from dash import html` (extend the existing dash import).
2. `build_historical_view` — new signature and labels:

```python
def build_historical_view(df, wy: int, basin: str | None,
                          dataset: str = 'snodas') -> tuple[go.Figure, str]:
    basin = basin or 'Columbia River Basin'
    ds = datasets.get(dataset)
    if df.empty:
        if dataset == 'snodas':
            msg = 'No data yet — run populate_timeseries.py to build the record.'
        else:
            msg = (f'{ds["label"]} data not yet loaded — run '
                   f'populate_timeseries.py --dataset {dataset} to backfill.')
        return _annotated_empty_figure(msg), ''

    n_years = climatology.n_historical_years(df, basin, wy)
    if n_years < climatology.MIN_YEARS_FOR_ENVELOPE:
        return _annotated_empty_figure(
            f'Not enough {ds["label"]} history for {basin} yet — {n_years} prior '
            f'water year(s); need at least {climatology.MIN_YEARS_FOR_ENVELOPE}. '
            f'Run the full-record backfill to populate.'), ''

    clim = climatology.compute_climatology(df, basin, wy)
    current = climatology.current_series(df, basin, wy)
    summary = climatology.summarize_current(df, basin, wy)
    hist_wys = sorted(df[(df['basin'] == basin) & (df['wy'] != wy)]['wy'].unique())
    record_label = f'WY{hist_wys[0]}–WY{hist_wys[-1]} envelope ({n_years} years)'
    fig = charts.make_climatology_figure(
        clim, current, basin, wy, summary,
        dataset_label=ds['label'], record_label=record_label)
    caption = (f'{ds["label"]} envelope from {n_years} water years '
               f'(WY{hist_wys[0]}–WY{hist_wys[-1]}); bold line is WY{wy}.')
    return fig, caption
```

3. `run_analysis` — add `State('dataset-select', 'value')` after the date State; signature becomes `def run_analysis(set_progress, n_clicks, date_str, dataset):`; call `pipeline.run_pipeline(date_str, set_progress, dataset=dataset)`; store `'dataset': dataset` in `result-store` data.
4. `update_trends_tab` — add `Input('dataset-select', 'value')`; signature `def update_trends_tab(tab_value, dataset):`; per-dataset load and empty message:

```python
        ds = datasets.get(dataset)
        _no_data_annotation = dict(
            text=(f'No {ds["label"]} data yet — run the populate script'
                  + ('' if dataset == 'snodas' else f' with --dataset {dataset}')
                  + ' or click Run Analysis'),
            x=0.5, y=0.5, xref='paper', yref='paper', showarrow=False,
            font={'size': 14, 'color': '#888'},
        )
        ...
        df = timeseries.load_timeseries(wy, cache_dir, dataset=dataset)
        ...
        return (
            charts.make_basin_timeseries_figure(df, wy, dataset_label=ds['label']),
            charts.make_huc4_timeseries_figure(df, wy, dataset_label=ds['label']),
        )
```

5. `populate_historical_basins` — add `Input('dataset-select', 'value')`; pass `dataset=dataset` to `climatology.load_all_water_years`.
6. `update_historical_tab` — add `Input('dataset-select', 'value')`; `df = climatology.load_all_water_years(config.get_cache_dir(), dataset=dataset)`; `return build_historical_view(df, wy, basin, dataset=dataset)`.
7. New small callbacks (routing only — no data logic):

```python
    @app.callback(
        Output('date-picker', 'min_date_allowed'),
        Input('dataset-select', 'value'),
    )
    def update_date_bounds(dataset):
        return datasets.get(dataset)['start'].date().isoformat()

    @app.callback(
        Output('snowpack-footnote', 'children'),
        Input('dataset-select', 'value'),
    )
    def update_snowpack_footnote(dataset):
        ds = datasets.get(dataset)
        return [html.P([html.Strong('Data: '), ds['footnote']],
                       style={'margin': '0'})]
```

8. Downloads — both `download_pngs` and `download_html` read the dataset from the store (`store_data.get('dataset', 'snodas')`), pass it to `timeseries.load_timeseries(..., dataset=...)` and `charts.make_*_timeseries_figure(..., dataset_label=ds['label'])`, name the zip `f'snow_analysis_{dataset}.zip'` / html `f'snow_analysis_{dataset}_{date_str}.html'`, and the HTML footnote uses `ds['footnote']` instead of the hardcoded SNODAS text.

- [ ] **Step 5: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_layout.py tests/test_callbacks.py -v`
Expected: all PASS (update any existing exact-string assertions broken by the new messages/labels in the same commit — intended behavior change).

- [ ] **Step 6: Smoke-test the app**

Use the `run-app` skill to launch the dev server; verify: toggle renders in header, switching to SWANN shows the "not yet loaded" states on Trends/Historical (no parquets yet), date picker min date changes to 1981-10-01, footnote swaps.

- [ ] **Step 7: Full suite, then commit**

Run: `venv/bin/python -m pytest tests/`

```bash
sudo -u geoskimoto git add layout.py callbacks.py tests/test_layout.py tests/test_callbacks.py
sudo -u geoskimoto git commit -m "feat: global dataset toggle wiring all three tabs to SNODAS or SWANN"
```

---

### Task 6: dual-dataset `update_timeseries.py`

**Files:**
- Modify: `update_timeseries.py`
- Test: create `tests/test_update_timeseries.py`

**Interfaces:**
- Consumes: `datasets.get`, dataset-aware `pipeline.load_band_cache/save_band_cache`, `timeseries.append_volumes`.
- Produces: `update_timeseries.process_dataset(dataset, date_arg, cache_dir, huc2, huc4, logger, discard_raster) -> bool` (True on success/already-current). `main()` runs snodas then swann; exit 0 only if both succeed. `--dataset {snodas,swann,both}` (default `both`) for selective runs.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_update_timeseries.py`:

```python
import logging
from datetime import datetime

import pytest

import datasets
import update_timeseries


@pytest.fixture
def quiet_logger():
    logger = logging.getLogger("test_update_timeseries")
    logger.addHandler(logging.NullHandler())
    return logger


def test_process_dataset_routes_to_swann_fetcher(tmp_path, monkeypatch, quiet_logger):
    called = {}

    def fake_latest(ref, cache_dir):
        called["swann"] = True
        raise ConnectionError("routing verified")

    monkeypatch.setitem(datasets.DATASETS["swann"], "fetch_latest_swe", fake_latest)
    ok = update_timeseries.process_dataset(
        "swann", None, tmp_path, None, None, quiet_logger, discard_raster=False)
    assert ok is False
    assert called == {"swann": True}


def test_process_dataset_skips_when_band_cache_current(tmp_path, monkeypatch, quiet_logger):
    """If the target date's band cache exists, no bands are recomputed."""
    import pandas as pd
    from pipeline import save_band_cache

    target = datetime(2026, 7, 18)
    bands = {"Columbia River Basin": pd.DataFrame({
        "elev_band_m": [1000], "mean_swe_mm": [100.0],
        "area_km2": [50.0], "total_swe_volume_km3": [0.005],
    })}
    save_band_cache(bands, "20260718", tmp_path, dataset="swann")

    monkeypatch.setitem(
        datasets.DATASETS["swann"], "fetch_latest_swe",
        lambda ref, cache_dir: (tmp_path / "unused.tif", target))

    ok = update_timeseries.process_dataset(
        "swann", None, tmp_path, None, None, quiet_logger, discard_raster=False)
    assert ok is True
    # volumes were appended from the cache
    from timeseries import load_timeseries
    assert not load_timeseries(2026, tmp_path, dataset="swann").empty


def test_main_dataset_choices():
    parser = update_timeseries.build_parser()
    assert parser.parse_args([]).dataset == "both"
    assert parser.parse_args(["--dataset", "swann"]).dataset == "swann"
    with pytest.raises(SystemExit):
        parser.parse_args(["--dataset", "modis"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_update_timeseries.py -v`
Expected: FAIL (`AttributeError: module 'update_timeseries' has no attribute 'process_dataset'` / `build_parser`).

- [ ] **Step 3: Implement**

Restructure `update_timeseries.py` (keep logging setup, dotenv preamble, constants):

1. Add `import datasets` to the imports; drop `from snodas_fetcher import fetch_swe, fetch_latest_swe`.
2. Extract the argument parser so tests can reach it:

```python
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Process SWE data for a given date (default: today).')
    parser.add_argument('--date', type=lambda s: datetime.strptime(s, '%Y-%m-%d'),
                        default=None,
                        help='Date to process in YYYY-MM-DD format (default: today).')
    parser.add_argument('--dataset', choices=('snodas', 'swann', 'both'),
                        default='both',
                        help='Which dataset(s) to process (default: both).')
    parser.add_argument('--discard-raster', action='store_true',
                        help='Delete the CONUS SWE raster after bands are computed.')
    return parser
```

3. Extract the fetch→bands→volumes body into a per-dataset function (this is the existing `main()` try-block, parameterized — same logic, same log lines, with `dataset=` threaded into `load_band_cache`, `save_band_cache`, `append_volumes`, and the DEM path taken from the registry):

```python
def process_dataset(dataset: str, date_arg, cache_dir, huc2, huc4,
                    logger: logging.Logger, discard_raster: bool) -> bool:
    """Fetch and process the latest (or given) date for one dataset.

    Returns True on success or already-current; False on any error (logged).
    """
    ds = datasets.get(dataset)
    dem_cache = cache_dir / 'dem' / ds['dem_filename']
    try:
        if date_arg:
            target = date_arg
            logger.info('[%s] Fetching SWE for %s ...', dataset, target.date())
            swe_tif = ds['fetch_swe'](target, cache_dir=cache_dir)
        else:
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            logger.info('[%s] Fetching latest available SWE at or before %s ...',
                        dataset, today.date())
            swe_tif, target = ds['fetch_latest_swe'](today, cache_dir=cache_dir)
            logger.info('[%s] Latest available product: %s', dataset, target.date())

        date_key = target.strftime('%Y%m%d')

        cached = load_band_cache(date_key, cache_dir, dataset)
        if cached is not None:
            logger.info('[%s] Band cache already exists for %s — nothing to do.',
                        dataset, target.date())
            try:
                append_volumes(target, cached, cache_dir, dataset=dataset)
            except Exception as exc:
                logger.warning('[%s] timeseries append failed (non-fatal): %s',
                               dataset, exc)
            return True

        logger.info('[%s] Loading aligned DEM ...', dataset)
        dem_tif = get_aligned_dem(swe_tif, dem_cache=dem_cache)

        logger.info('[%s] Computing elevation bands ...', dataset)
        bands_by_basin: dict = {
            _HUC2_KEY: compute_bands(swe_tif, dem_tif, huc2.geometry[0],
                                     min_band_area_km2=_MIN_BAND_AREA_KM2)
        }
        for _, row in huc4.iterrows():
            bands_by_basin[row['name']] = compute_bands(
                swe_tif, dem_tif, row.geometry,
                min_band_area_km2=_MIN_BAND_AREA_KM2)

        save_band_cache(bands_by_basin, date_key, cache_dir, dataset)
        append_volumes(target, bands_by_basin, cache_dir, dataset=dataset)
        if discard_raster:
            swe_tif.unlink(missing_ok=True)
            logger.debug('[%s] Discarded raster %s', dataset, swe_tif.name)

        logger.info('[%s] Done — %d basins processed for %s.',
                    dataset, len(bands_by_basin), target.date())
        return True

    except (ConnectionError, OSError, IOError) as exc:
        logger.error('[%s] Fetch / network error: %s', dataset, exc)
        return False
    except Exception as exc:
        logger.error('[%s] Unexpected error: %s', dataset, exc, exc_info=True)
        return False
```

4. New `main()`:

```python
def main() -> None:
    args = build_parser().parse_args()
    logger = _setup_logging()
    cache_dir = config.get_cache_dir()
    date_arg = (args.date.replace(hour=0, minute=0, second=0, microsecond=0)
                if args.date else None)

    logger.info('=== update_timeseries (datasets: %s) ===', args.dataset)
    logger.info('cache_dir: %s', cache_dir)

    logger.info('Loading basin boundaries ...')
    huc2 = load_huc2()
    huc4 = load_huc4()

    targets = ('snodas', 'swann') if args.dataset == 'both' else (args.dataset,)
    results = {
        d: process_dataset(d, date_arg, cache_dir, huc2, huc4, logger,
                           discard_raster=args.discard_raster)
        for d in targets
    }
    failed = [d for d, ok in results.items() if not ok]
    if failed:
        logger.error('Datasets failed: %s', ', '.join(failed))
        sys.exit(1)
    sys.exit(0)
```

(Each dataset runs in its own try block via `process_dataset`, so a SNODAS outage doesn't block SWANN or vice versa.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_update_timeseries.py -v`
Expected: all PASS.

- [ ] **Step 5: Full suite, then commit**

Run: `venv/bin/python -m pytest tests/`

```bash
sudo -u geoskimoto git add update_timeseries.py tests/test_update_timeseries.py
sudo -u geoskimoto git commit -m "feat: daily update job processes SNODAS and SWANN independently per run"
```

---

### Task 7: SWANN backfill in `populate_timeseries.py`

**Files:**
- Modify: `populate_timeseries.py`
- Test: extend `tests/test_populate_timeseries.py`

**Interfaces:**
- Consumes: `swann_fetcher.download_wy_nc`, `swann_fetcher.nc_to_geotiff`, `swann_fetcher.fetch_swe`, dataset-aware `timeseries.append_volumes`, `timeseries.load_timeseries`, `timeseries.water_year`.
- Produces:
  - `--dataset {snodas,swann}` (default `snodas` — existing behavior unchanged).
  - `parse_time_values(tags: dict) -> list[datetime]` — pure function turning GDAL netCDF global tags (`NETCDF_DIM_time_VALUES` like `"{30955,30956,...}"` + `time#units` like `"days since 1900-01-01 00:00:00"`) into per-band dates.
  - `_run_swann_backfill(start, end, cache_dir, huc2, huc4, logger, discard) -> list[date]` (returns failed dates). WY-file mode for years with a bulk file; daily-file fallback (via `swann_fetcher.fetch_swe`) when `download_wy_nc` raises `FileNotFoundError` (WY2024+). Volumes only — **no band caches saved** during backfill (they build on demand later, per spec).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_populate_timeseries.py`:

```python
def test_parse_time_values_days_since_1900():
    from datetime import datetime
    import populate_timeseries

    # Anchor pair verified against a live SWANN file on 2026-07-20:
    # the daily file for 2026-01-15 carries NETCDF_DIM_time = 46035.
    tags = {
        "NETCDF_DIM_time_VALUES": "{46035,46036,46037}",
        "time#units": "days since 1900-01-01 00:00:00",
    }
    dates = populate_timeseries.parse_time_values(tags)
    assert dates[0] == datetime(2026, 1, 15)
    assert dates[2] == datetime(2026, 1, 17)
    assert len(dates) == 3


def test_parse_time_values_rejects_unknown_units():
    import pytest
    import populate_timeseries

    with pytest.raises(ValueError):
        populate_timeseries.parse_time_values(
            {"NETCDF_DIM_time_VALUES": "{1}", "time#units": "hours since 1900-01-01"})


def test_dataset_arg_default_snodas():
    import populate_timeseries
    parser = populate_timeseries.build_parser()
    assert parser.parse_args([]).dataset == "snodas"
    assert parser.parse_args(["--dataset", "swann"]).dataset == "swann"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_populate_timeseries.py -v`
Expected: new tests FAIL (`AttributeError: parse_time_values` / `build_parser`).

- [ ] **Step 3: Implement**

In `populate_timeseries.py`:

1. Imports: add `import re`, `import rasterio`, `import swann_fetcher`, `import datasets`, and `from timeseries import append_volumes, load_timeseries, water_year`.
2. Extract the parser (existing args unchanged, one addition):

```python
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--start', metavar='YYYY-MM-DD',
                        default=_DEFAULT_START.isoformat(),
                        help='First date to process (default: 2025-10-01)')
    parser.add_argument('--dataset', choices=('snodas', 'swann'), default='snodas',
                        help='Dataset to backfill (default: snodas). SWANN uses '
                             'bulk water-year files (WY1982-WY2023) and falls back '
                             'to daily files for later years.')
    parser.add_argument('--discard-raster', action='store_true',
                        help='Delete each downloaded raster/netCDF after processing.')
    return parser
```

3. Time-value parsing (pure, unit-testable):

```python
_TIME_UNITS_RE = re.compile(r'^days since (\d{4}-\d{2}-\d{2})')


def parse_time_values(tags: dict) -> list[datetime]:
    """Decode GDAL netCDF global tags into one datetime per time band.

    SWANN WY files carry time as 'days since 1900-01-01'; anything else is a
    format change we must not silently misread.
    """
    m = _TIME_UNITS_RE.match(tags.get('time#units', ''))
    if not m:
        raise ValueError(
            f"Unexpected SWANN time units: {tags.get('time#units')!r}")
    origin = datetime.strptime(m.group(1), '%Y-%m-%d')
    raw = tags['NETCDF_DIM_time_VALUES'].strip('{}')
    return [origin + timedelta(days=int(float(v))) for v in raw.split(',')]
```

4. The SWANN backfill driver:

```python
def _swann_dates_done(wy: int, cache_dir: Path, n_basins: int) -> set:
    """Dates already fully recorded (all basins) in the SWANN WY parquet."""
    df = load_timeseries(wy, cache_dir, dataset='swann')
    if df.empty:
        return set()
    counts = df.groupby('date')['basin'].nunique()
    return {ts.to_pydatetime().date() for ts, n in counts.items() if n >= n_basins}


def _swann_process_day(swe_tif: Path, dem_tif: Path, dt: datetime,
                       huc2, huc4, cache_dir: Path) -> None:
    """Compute per-basin bands in memory and append volumes (no band cache —
    the full-record backfill only needs the tiny volume parquets; band caches
    build on demand from the Snowpack tab, per the design spec)."""
    bands_by_basin: dict = {
        _HUC2_KEY: compute_bands(swe_tif, dem_tif, huc2.geometry[0],
                                 min_band_area_km2=_MIN_BAND_AREA_KM2)
    }
    for _, row in huc4.iterrows():
        bands_by_basin[row['name']] = compute_bands(
            swe_tif, dem_tif, row.geometry, min_band_area_km2=_MIN_BAND_AREA_KM2)
    append_volumes(dt, bands_by_basin, cache_dir, dataset='swann')


def _run_swann_backfill(start: date, end: date, cache_dir: Path,
                        huc2, huc4, logger: logging.Logger,
                        discard: bool) -> list[date]:
    """Backfill SWANN volumes for [start, end]. Returns failed dates."""
    ds = datasets.get('swann')
    dem_cache = cache_dir / 'dem' / ds['dem_filename']
    n_basins = 1 + len(huc4)
    failed: list[date] = []
    tmp_tif = cache_dir / 'swann' / 'wy_extract_tmp.tif'

    first_wy = water_year(datetime(start.year, start.month, start.day))
    last_wy = water_year(datetime(end.year, end.month, end.day))

    for wy in range(first_wy, last_wy + 1):
        done = _swann_dates_done(wy, cache_dir, n_basins)
        try:
            wy_nc = swann_fetcher.download_wy_nc(wy, cache_dir / 'swann')
        except FileNotFoundError:
            wy_nc = None       # no bulk file (WY2024+): daily-file mode
        except ConnectionError as exc:
            logger.error('WY%d  bulk download failed: %s — skipping year', wy, exc)
            wy_start = date(wy - 1, 10, 1)
            failed.extend([wy_start])   # marker; details in log
            continue

        if wy_nc is not None:
            logger.info('WY%d  bulk file mode (%s)', wy, wy_nc.name)
            sd = f'netcdf:{wy_nc}:SWE'
            with rasterio.open(sd) as src:
                band_dates = parse_time_values(src.tags())
                n_bands = src.count
            if len(band_dates) != n_bands:
                logger.error('WY%d  time axis mismatch (%d dates, %d bands) — skipping',
                             wy, len(band_dates), n_bands)
                failed.append(date(wy - 1, 10, 1))
                continue
            for band_idx, dt in enumerate(band_dates, start=1):
                d = dt.date()
                if d < start or d > end or d in done:
                    continue
                try:
                    swann_fetcher.nc_to_geotiff(wy_nc, tmp_tif, variable='SWE',
                                                band=band_idx)
                    dem_tif = get_aligned_dem(tmp_tif, dem_cache=dem_cache)
                    _swann_process_day(tmp_tif, dem_tif, dt, huc2, huc4, cache_dir)
                    logger.info('%s  OK (WY file band %d)', d, band_idx)
                except Exception as exc:
                    logger.error('%s  ERROR: %s', d, exc)
                    failed.append(d)
            tmp_tif.unlink(missing_ok=True)
            if discard:
                wy_nc.unlink(missing_ok=True)
                logger.debug('WY%d  discarded %s', wy, wy_nc.name)
        else:
            logger.info('WY%d  daily file mode (no bulk file)', wy)
            d = max(start, date(wy - 1, 10, 1))
            wy_end = min(end, date(wy, 9, 30))
            while d <= wy_end:
                if d not in done:
                    dt = datetime(d.year, d.month, d.day)
                    try:
                        swe_tif = swann_fetcher.fetch_swe(dt, cache_dir=cache_dir)
                        dem_tif = get_aligned_dem(swe_tif, dem_cache=dem_cache)
                        _swann_process_day(swe_tif, dem_tif, dt, huc2, huc4, cache_dir)
                        if discard:
                            swe_tif.unlink(missing_ok=True)
                        logger.info('%s  OK (daily file)', d)
                    except Exception as exc:
                        logger.error('%s  ERROR: %s', d, exc)
                        failed.append(d)
                d += timedelta(days=1)
    return failed
```

5. In `main()`: parse with `build_parser()`; when `args.dataset == 'swann'`, use SWANN's record start as the default start (`date(1981, 10, 1)` if the user didn't pass `--start`, i.e. compare `args.start` to `_DEFAULT_START.isoformat()`), then after loading basins:

```python
    if args.dataset == 'swann':
        failed = _run_swann_backfill(start, yesterday, cache_dir, huc2, huc4,
                                     logger, discard=args.discard_raster)
        logger.info('=== populate_timeseries (swann) DONE — %d failures ===',
                    len(failed))
        if failed:
            logger.warning('Failed dates: %s', ', '.join(str(d) for d in failed))
            sys.exit(1)
        sys.exit(0)
```

The existing SNODAS loop below runs only for `dataset == 'snodas'` and is otherwise untouched.

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_populate_timeseries.py -v`
Expected: all PASS.

- [ ] **Step 5: Live single-day sanity check (network, ~100 MB)**

Run a one-year-bounded smoke test against the real service — this validates the WY-file path end to end (download, time parsing, band extraction, DEM alignment at 4 km, volume append):

```bash
sudo -u geoskimoto venv/bin/python populate_timeseries.py --dataset swann \
    --start 1985-01-01 --discard-raster &
sleep 600 && kill %1   # let it process WY1985 partially, then stop
venv/bin/python -c "
from pathlib import Path
from timeseries import load_timeseries
df = load_timeseries(1985, Path('data/cache'), dataset='swann')
print(df.head(15)); print('rows:', len(df), 'basins:', df.basin.nunique())
assert not df.empty and df.basin.nunique() >= 10"
```

Expected: non-empty frame, 12 basins, plausible volumes (Columbia January SWE roughly 10–40 km³). If values are wildly off (units/grid error), STOP and report — do not adjust tests.

- [ ] **Step 6: Full suite, then commit**

Run: `venv/bin/python -m pytest tests/`

```bash
sudo -u geoskimoto git add populate_timeseries.py tests/test_populate_timeseries.py
sudo -u geoskimoto git commit -m "feat: SWANN full-record backfill via bulk WY files with daily-file fallback"
```

---

### Task 8: ops — gitignore, cron review, backfill run, ship parquets

**Files:**
- Modify: `.gitignore`
- No test files (infrastructure task; verified by commands below).

- [ ] **Step 1: gitignore — ship the SWANN DEM, verify swann timeseries inclusion**

Add one line after the existing DEM carve-out (`!data/cache/dem/columbia_basin_swe_aligned.tif`):

```
!data/cache/dem/columbia_basin_swann_aligned.tif
```

Verify the SWANN timeseries subtree is already un-ignored by the existing `!data/cache/timeseries/` rule:

```bash
git check-ignore -v data/cache/timeseries/swann/WY1982_volume.parquet ; echo "exit=$?"
```

Expected: `exit=1` (NOT ignored). If it prints a matching rule instead, add `!data/cache/timeseries/swann/` below the existing carve-out and re-verify.

```bash
sudo -u geoskimoto git add .gitignore
sudo -u geoskimoto git commit -m "chore: ship SWANN-aligned DEM via gitignore carve-out"
```

- [ ] **Step 2: cron review (global CLAUDE.md rule)**

```bash
crontab -l; sudo -u geoskimoto crontab -l; ls /etc/cron.d/ && cat /etc/cron.d/* 2>/dev/null | grep -v '^#'
```

The daily job invokes `update_timeseries.py`, which now processes both datasets in the same run — **no schedule change and no new crontab entry**. Confirm which crontab holds the entry (should be geoskimoto's, per the file-ownership rule; if it is in root's, flag to the user rather than moving it). Document in the commit message or `deploy.md` if it exists: runtime grows by one SWANN fetch (~1 MB download + 4 km band computation, well under a minute), which cannot overlap other jobs' windows meaningfully.

- [ ] **Step 3: run the full backfill (VPS, nohup, hours-long)**

```bash
sudo -u geoskimoto nohup venv/bin/python populate_timeseries.py \
    --dataset swann --start 1981-10-01 --discard-raster \
    > logs/populate_swann_nohup.log 2>&1 &
```

Monitor: `tail -f logs/populate_timeseries.log`. Expected duration: ~42 WY files × (~95 MB download + ~365 days × 12 basin maskings); the log prints per-day `OK` lines. Peak disk: one WY nc (~95 MB) + one temp tif at a time.

On completion: `venv/bin/python -m pytest tests/` (suite must still pass), then verify record coverage:

```bash
venv/bin/python - <<'EOF'
from pathlib import Path
from climatology import load_all_water_years
df = load_all_water_years(Path('data/cache'), dataset='swann')
print('water years:', df.wy.min(), '-', df.wy.max(), '| n =', df.wy.nunique())
print('basins:', df.basin.nunique(), '| rows:', len(df))
assert df.wy.nunique() >= 42
EOF
```

- [ ] **Step 4: commit artifacts + deploy**

```bash
sudo chown -R geoskimoto:geoskimoto /home/geoskimoto/projects/snow_elevation_plot
sudo -u geoskimoto git add -f data/cache/timeseries/swann/ data/cache/dem/columbia_basin_swann_aligned.tif
sudo -u geoskimoto git commit -m "chore: commit SWANN WY1982-2026 volume parquets + 4km-aligned DEM"
```

Restart the app service (name per deploy.md), flip the toggle to SWANN in a browser, and verify: Historical shows a WY1982+ envelope labeled `SWANN (4 km)`, Trends shows the current WY, Snowpack runs an analysis for a pre-2004 date (e.g. 1996-02-01 — the 1996 flood year snowpack, a nice sanity check that SNODAS could never render).

---

## Self-review notes

- Spec coverage: fetcher (T1), registry/config (T2), pipeline parity (T3), figure honesty (T4), toggle + date bounds + empty states + downloads (T5), daily cron (T6), backfill (T7), gitignore/Posit + cron review + ops (T8). Spec's Earthdata/NSIDC credential requirement dropped — verified live that the UA portal needs no auth (spec explicitly deferred endpoint choice to implementation-time verification).
- Deviation: band-cache filename keeps `_250m` suffix (band interval, not resolution) — documented above.
- Type consistency: `dataset: str = 'snodas'` keyword everywhere; `dataset_label`/`record_label` strings; registry keys `label/start/dem_filename/fetch_swe/fetch_latest_swe/footnote` used consistently in T2–T7.
