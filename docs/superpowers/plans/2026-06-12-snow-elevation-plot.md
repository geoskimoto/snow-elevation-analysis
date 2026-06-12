# Snow Elevation Plot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a CLI pipeline that downloads SNODAS SWE data, bins pixels by elevation band per HUC basin, and produces hypsometric curve PNGs.

**Architecture:** Modular pipeline — `snodas_fetcher` downloads and caches SNODAS GeoTIFFs; `dem_processor` fetches and caches an SRTM DEM pixel-aligned to the SNODAS grid; `elevation_bands` masks rasters to each basin polygon and bins by elevation; `plotter` draws hypsometric curves. `main.py` wires these together as a CLI.

**Tech Stack:** Python 3.12, rasterio, rioxarray, geopandas, shapely, numpy, matplotlib, elevation (SRTM), ftplib (stdlib), pytest, pytest-mock

---

## File Map

| File | Purpose |
|---|---|
| `requirements.txt` | Pinned dependencies |
| `basin_loader.py` | Load HUC2/HUC4 GeoJSON as GeoDataFrames |
| `snodas_fetcher.py` | FTP download, .tar extract, .dat.gz → GeoTIFF, date-keyed cache |
| `dem_processor.py` | SRTM 90m download via `elevation` pkg, warp to SNODAS grid, single persistent cache file |
| `elevation_bands.py` | Clip rasters to basin polygon, bin by elevation, return DataFrame |
| `plotter.py` | Hypsometric curve figures (HUC2 + HUC4) saved as PNG |
| `main.py` | argparse CLI wiring all modules |
| `tests/conftest.py` | Shared pytest fixtures (synthetic rasters, tiny GeoJSON) |
| `tests/test_basin_loader.py` | Unit tests for basin_loader |
| `tests/test_snodas_fetcher.py` | Unit tests for snodas_fetcher (mocked FTP) |
| `tests/test_dem_processor.py` | Unit tests for dem_processor (mocked elevation download) |
| `tests/test_elevation_bands.py` | Unit + property tests for elevation_bands |
| `tests/test_plotter.py` | Snapshot test for plotter output |
| `tests/test_integration.py` | Full pipeline integration test using fixture SNODAS file |
| `data/basemaps/` | huc2_pnw.geojson, huc4_pnw.geojson (copied from usgs-streamflow-dashboard) |

---

## SNODAS Format Reference

- **FTP host:** `sidads.colorado.edu`
- **FTP path:** `/pub/DATASETS/NOAA/G02158/masked/{YYYY}/{MM_Mon}/SNODAS_{YYYYMMDD}.tar`
  - Month format: `01_Jan`, `02_Feb`, ..., `12_Dec`
- **SWE file inside tar:** `us_ssmv11034tS__T0001TTNATS{YYYYMMDD}05HP001.dat.gz`
- **Grid (masked CONUS product):**
  - Columns: 6935, Rows: 3351
  - Upper-left: (-124.733749999, 52.874583333)
  - Pixel size: 0.00833333333 degrees
  - CRS: EPSG:4326
  - Data type: int16 big-endian
  - No-data: -9999
  - Units: stored value = SWE in mm (scale factor 0.001 m/unit)

---

## Task 1: Project Scaffold

**Files:**
- Create: `requirements.txt`
- Create: `data/basemaps/huc2_pnw.geojson` (copy)
- Create: `data/basemaps/huc4_pnw.geojson` (copy)
- Create: `tests/conftest.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create directory structure**

```bash
cd /home/geoskimoto/projects/snow_elevation_plot
mkdir -p data/cache/snodas data/cache/dem data/basemaps output tests
touch tests/__init__.py
```

- [ ] **Step 2: Copy basemaps**

```bash
cp /home/geoskimoto/projects/usgs-streamflow-dashboard/data/basemaps/huc2_pnw.geojson data/basemaps/
cp /home/geoskimoto/projects/usgs-streamflow-dashboard/data/basemaps/huc4_pnw.geojson data/basemaps/
```

- [ ] **Step 3: Create requirements.txt**

```
numpy==2.2.6
rasterio==1.4.3
rioxarray==0.18.2
geopandas==1.0.1
shapely==2.1.0
matplotlib==3.10.3
elevation==1.1.3
GDAL==3.10.3
pytest==8.3.5
pytest-mock==3.14.1
```

- [ ] **Step 4: Create virtualenv and install dependencies**

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Expected: all packages install without error.

- [ ] **Step 5: Create tests/conftest.py with shared fixtures**

```python
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from pathlib import Path
import tempfile
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
    # Elevations: 0-250m band, 250-500m band, 500-750m band
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
```

- [ ] **Step 6: Commit scaffold**

```bash
git init
git add requirements.txt tests/ data/basemaps/
git commit -m "chore: project scaffold, basemaps, test fixtures"
```

---

## Task 2: basin_loader.py

**Files:**
- Create: `basin_loader.py`
- Create: `tests/test_basin_loader.py`

- [ ] **Step 1: Write failing tests**

```python
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


def test_load_huc4_has_twelve_subbasins():
    gdf = basin_loader.load_huc4()
    assert len(gdf) == 12


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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /home/geoskimoto/projects/snow_elevation_plot
source venv/bin/activate
pytest tests/test_basin_loader.py -v
```

Expected: `ModuleNotFoundError: No module named 'basin_loader'`

- [ ] **Step 3: Write basin_loader.py**

```python
from pathlib import Path
import geopandas as gpd

BASEMAP_DIR = Path(__file__).parent / "data" / "basemaps"


def load_huc2() -> gpd.GeoDataFrame:
    path = BASEMAP_DIR / "huc2_pnw.geojson"
    if not path.exists():
        raise FileNotFoundError(f"huc2_pnw.geojson not found in {BASEMAP_DIR}")
    return gpd.read_file(path).to_crs(epsg=4326)


def load_huc4() -> gpd.GeoDataFrame:
    path = BASEMAP_DIR / "huc4_pnw.geojson"
    if not path.exists():
        raise FileNotFoundError(f"huc4_pnw.geojson not found in {BASEMAP_DIR}")
    return gpd.read_file(path).to_crs(epsg=4326)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_basin_loader.py -v
```

Expected: all 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add basin_loader.py tests/test_basin_loader.py
git commit -m "feat: basin_loader — load HUC2/HUC4 GeoJSON boundaries"
```

---

## Task 3: snodas_fetcher.py

**Files:**
- Create: `snodas_fetcher.py`
- Create: `tests/test_snodas_fetcher.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_snodas_fetcher.py
import pytest
import numpy as np
import rasterio
from datetime import datetime
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
    rows, cols = snodas_fetcher.SNODAS_ROWS, snodas_fetcher.SNODAS_COLS
    # Use small synthetic slice for speed — just test value preservation
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_snodas_fetcher.py -v
```

Expected: `ModuleNotFoundError: No module named 'snodas_fetcher'`

- [ ] **Step 3: Write snodas_fetcher.py**

```python
import ftplib
import gzip
import shutil
import tarfile
from datetime import datetime
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

SNODAS_FTP_HOST = "sidads.colorado.edu"
SNODAS_ROWS = 3351
SNODAS_COLS = 6935
SNODAS_XMIN = -124.733749999
SNODAS_YMAX = 52.874583333
SNODAS_CELLSIZE = 0.00833333333
SNODAS_NODATA = -9999

_MONTH_ABBR = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"
}

_DEFAULT_CACHE = Path(__file__).parent / "data" / "cache" / "snodas"
_SNODAS_START = datetime(2003, 10, 1)


def validate_date(date: datetime) -> None:
    if date < _SNODAS_START:
        raise ValueError(
            f"SNODAS begins October 2003; requested date {date.date()} is too early."
        )


def ftp_dir_path(date: datetime) -> str:
    return (
        f"/pub/DATASETS/NOAA/G02158/masked/"
        f"{date.year}/{date.month:02d}_{_MONTH_ABBR[date.month]}/"
    )


def ftp_filename(date: datetime) -> str:
    return f"SNODAS_{date.strftime('%Y%m%d')}.tar"


def swe_dat_filename(date: datetime) -> str:
    return f"us_ssmv11034tS__T0001TTNATS{date.strftime('%Y%m%d')}05HP001.dat.gz"


def cache_path(date: datetime, cache_dir: Path = _DEFAULT_CACHE) -> Path:
    return cache_dir / f"{date.year}" / f"{date.month:02d}" / f"{date.strftime('%Y%m%d')}_swe.tif"


def dat_to_geotiff(
    dat_path: Path,
    tif_path: Path,
    rows: int = SNODAS_ROWS,
    cols: int = SNODAS_COLS,
) -> None:
    data = np.fromfile(dat_path, dtype=">i2").reshape(rows, cols)
    transform = from_origin(SNODAS_XMIN, SNODAS_YMAX, SNODAS_CELLSIZE, SNODAS_CELLSIZE)
    tif_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        tif_path, "w",
        driver="GTiff",
        height=rows, width=cols,
        count=1, dtype="int16",
        crs="EPSG:4326",
        transform=transform,
        nodata=SNODAS_NODATA,
        compress="lzw",
    ) as dst:
        dst.write(data, 1)


def download_and_extract(date: datetime, tif_path: Path) -> None:
    tmp_tar = tif_path.parent / ftp_filename(date)
    tif_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with ftplib.FTP(SNODAS_FTP_HOST) as ftp:
            ftp.login()
            ftp.cwd(ftp_dir_path(date))
            with open(tmp_tar, "wb") as f:
                ftp.retrbinary(f"RETR {ftp_filename(date)}", f.write)
    except ftplib.all_errors as e:
        if tmp_tar.exists():
            tmp_tar.unlink()
        raise ConnectionError(
            f"SNODAS FTP download failed for {date.date()}: {e}\n"
            f"Try an earlier date or check your connection."
        ) from e

    dat_gz_name = swe_dat_filename(date)
    tmp_dat_gz = tif_path.parent / dat_gz_name
    tmp_dat = tif_path.parent / dat_gz_name.replace(".gz", "")

    try:
        with tarfile.open(tmp_tar) as tar:
            member = tar.getmember(dat_gz_name)
            with tar.extractfile(member) as gz_file, open(tmp_dat_gz, "wb") as out:
                out.write(gz_file.read())
        with gzip.open(tmp_dat_gz, "rb") as gz, open(tmp_dat, "wb") as out:
            shutil.copyfileobj(gz, out)
        dat_to_geotiff(tmp_dat, tif_path)
    finally:
        for p in [tmp_tar, tmp_dat_gz, tmp_dat]:
            if p.exists():
                p.unlink()


def fetch_swe(date: datetime, cache_dir: Path = _DEFAULT_CACHE) -> Path:
    validate_date(date)
    tif = cache_path(date, cache_dir)
    if tif.exists():
        return tif
    download_and_extract(date, tif)
    return tif
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_snodas_fetcher.py -v
```

Expected: all 11 tests PASS

- [ ] **Step 5: Commit**

```bash
git add snodas_fetcher.py tests/test_snodas_fetcher.py
git commit -m "feat: snodas_fetcher — FTP download, .dat extraction, GeoTIFF cache"
```

---

## Task 4: dem_processor.py

**Files:**
- Create: `dem_processor.py`
- Create: `tests/test_dem_processor.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_dem_processor.py
import pytest
import numpy as np
import rasterio
from rasterio.transform import from_origin
from pathlib import Path
from unittest.mock import patch, MagicMock
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
    # Build a fake raw DEM (different resolution) to warp
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_dem_processor.py -v
```

Expected: `ModuleNotFoundError: No module named 'dem_processor'`

- [ ] **Step 3: Write dem_processor.py**

```python
from pathlib import Path

import numpy as np
import rasterio
import rasterio.warp
from rasterio.enums import Resampling

_DEFAULT_DEM_CACHE = (
    Path(__file__).parent / "data" / "cache" / "dem" / "columbia_basin_swe_aligned.tif"
)
_COLUMBIA_BASIN_BOUNDS = (-125.0, 24.0, -66.5, 53.0)


def warp_dem_to_grid(raw_dem: Path, reference_tif: Path, output: Path) -> None:
    """Reproject and resample raw_dem to exactly match reference_tif grid."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(reference_tif) as ref:
        dst_crs = ref.crs
        dst_transform = ref.transform
        dst_width = ref.width
        dst_height = ref.height

    with rasterio.open(raw_dem) as src:
        data, _ = rasterio.warp.reproject(
            source=rasterio.band(src, 1),
            destination=np.empty((dst_height, dst_width), dtype=np.float32),
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=dst_transform,
            dst_crs=dst_crs,
            resampling=Resampling.bilinear,
        )

    with rasterio.open(
        output, "w",
        driver="GTiff",
        height=dst_height, width=dst_width,
        count=1, dtype="float32",
        crs=dst_crs,
        transform=dst_transform,
        nodata=-9999.0,
        compress="lzw",
    ) as dst:
        dst.write(data, 1)


def build_aligned_dem(swe_tif: Path, dem_cache: Path) -> None:
    """Fetch SRTM 90m for Columbia Basin bbox, warp to SNODAS grid, cache."""
    import elevation
    import tempfile

    dem_cache.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as f:
        raw_path = Path(f.name)

    try:
        elevation.clip(
            bounds=_COLUMBIA_BASIN_BOUNDS,
            output=str(raw_path),
            product="SRTM3",
        )
        warp_dem_to_grid(raw_path, swe_tif, dem_cache)
    finally:
        if raw_path.exists():
            raw_path.unlink()
        elevation.clean()


def get_aligned_dem(
    swe_tif: Path,
    dem_cache: Path = _DEFAULT_DEM_CACHE,
) -> Path:
    if dem_cache.exists():
        return dem_cache
    build_aligned_dem(swe_tif, dem_cache)
    return dem_cache
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_dem_processor.py -v
```

Expected: all 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add dem_processor.py tests/test_dem_processor.py
git commit -m "feat: dem_processor — SRTM fetch, warp to SNODAS grid, persistent cache"
```

---

## Task 5: elevation_bands.py

**Files:**
- Create: `elevation_bands.py`
- Create: `tests/test_elevation_bands.py`

- [ ] **Step 1: Write failing tests**

```python
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

    # Elevations: 0-250, 250-500, 500-750, 750-1000 bands
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
    """Bands with valid pixels but SWE=0 must appear in output."""
    swe_tif, dem_tif, geom = aligned_swe_dem
    result = elevation_bands.compute_bands(swe_tif, dem_tif, geom, band_interval_m=250)
    # The fixture has SWE=0 pixels at low elevations (row 3, cols 0-1)
    zero_swe_bands = result[result['mean_swe_mm'] == 0.0]
    assert len(zero_swe_bands) >= 1


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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_elevation_bands.py -v
```

Expected: `ModuleNotFoundError: No module named 'elevation_bands'`

- [ ] **Step 3: Write elevation_bands.py**

```python
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import rasterio.mask
from shapely.geometry import mapping, Geometry


def compute_bands(
    swe_tif: Path,
    dem_tif: Path,
    basin_geom,
    band_interval_m: int = 250,
) -> pd.DataFrame:
    geom_json = [mapping(basin_geom)]

    with rasterio.open(swe_tif) as src:
        swe_arr, _ = rasterio.mask.mask(src, geom_json, crop=True, nodata=-9999)
        swe_arr = swe_arr[0].astype(np.float32)
        res_deg = abs(src.transform.a)
        lat_mid = (src.bounds.top + src.bounds.bottom) / 2.0

    with rasterio.open(dem_tif) as src:
        dem_arr, _ = rasterio.mask.mask(src, geom_json, crop=True, nodata=-9999.0)
        dem_arr = dem_arr[0].astype(np.float32)

    # Tolerate ≤1 pixel crop difference from rasterio.mask.mask; raise on larger mismatch
    if abs(swe_arr.shape[0] - dem_arr.shape[0]) > 1 or abs(swe_arr.shape[1] - dem_arr.shape[1]) > 1:
        raise ValueError(
            f"DEM/SWE grid mismatch: SWE shape {swe_arr.shape} vs DEM shape {dem_arr.shape}. "
            "Ensure the DEM was built with get_aligned_dem() using the same SNODAS tif."
        )
    min_h = min(swe_arr.shape[0], dem_arr.shape[0])
    min_w = min(swe_arr.shape[1], dem_arr.shape[1])
    swe_arr = swe_arr[:min_h, :min_w]
    dem_arr = dem_arr[:min_h, :min_w]

    valid_mask = (swe_arr != -9999) & (~np.isnan(swe_arr)) & (dem_arr != -9999) & (~np.isnan(dem_arr))
    swe_valid = swe_arr[valid_mask]
    elev_valid = dem_arr[valid_mask]

    # Pixel area in km² (approximate; latitude-corrected)
    km_per_deg_lon = 111.32 * np.cos(np.radians(lat_mid))
    km_per_deg_lat = 111.32
    pixel_km2 = res_deg * km_per_deg_lon * res_deg * km_per_deg_lat

    if len(elev_valid) == 0:
        return pd.DataFrame(columns=['elev_band_m', 'mean_swe_mm', 'area_km2', 'total_swe_volume_km3'])

    elev_min = int(np.floor(elev_valid.min() / band_interval_m) * band_interval_m)
    elev_max = int(np.ceil(elev_valid.max() / band_interval_m) * band_interval_m)

    records = []
    for band_floor in range(elev_min, elev_max, band_interval_m):
        band_ceil = band_floor + band_interval_m
        in_band = (elev_valid >= band_floor) & (elev_valid < band_ceil)
        n_pixels = int(in_band.sum())
        if n_pixels == 0:
            continue
        area_km2 = n_pixels * pixel_km2
        mean_swe = float(swe_valid[in_band].mean())
        records.append({
            'elev_band_m': band_floor,
            'mean_swe_mm': mean_swe,
            'area_km2': area_km2,
            'total_swe_volume_km3': mean_swe * area_km2 * 1e-6,
        })

    return pd.DataFrame(records)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_elevation_bands.py -v
```

Expected: all 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add elevation_bands.py tests/test_elevation_bands.py
git commit -m "feat: elevation_bands — bin SNODAS SWE pixels by elevation per basin"
```

---

## Task 6: plotter.py

**Files:**
- Create: `plotter.py`
- Create: `tests/test_plotter.py`
- Create: `tests/fixtures/` (reference PNGs written on first run)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_plotter.py
import pytest
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path
import matplotlib
matplotlib.use('Agg')  # non-interactive backend for tests
import plotter


@pytest.fixture
def sample_bands():
    """Minimal bands DataFrames for two basins."""
    huc2_df = pd.DataFrame({
        'elev_band_m': [0, 250, 500, 750, 1000],
        'mean_swe_mm': [0.0, 50.0, 150.0, 300.0, 400.0],
        'area_km2': [5000.0] * 5,
        'total_swe_volume_km3': [0.0, 0.25, 0.75, 1.5, 2.0],
    })
    sub_df = pd.DataFrame({
        'elev_band_m': [250, 500, 750],
        'mean_swe_mm': [30.0, 120.0, 280.0],
        'area_km2': [1000.0] * 3,
        'total_swe_volume_km3': [0.03, 0.12, 0.28],
    })
    return {
        'Columbia River Basin': huc2_df,
        'Upper Columbia': sub_df,
        'Yakima': sub_df.copy(),
    }


def test_plot_hypsometric_returns_list_of_paths(tmp_path, sample_bands):
    date = datetime(2024, 4, 1)
    result = plotter.plot_hypsometric(sample_bands, date, tmp_path)
    assert isinstance(result, list)
    assert len(result) == 2


def test_plot_hypsometric_files_exist(tmp_path, sample_bands):
    date = datetime(2024, 4, 1)
    paths = plotter.plot_hypsometric(sample_bands, date, tmp_path)
    for p in paths:
        assert Path(p).exists()


def test_plot_hypsometric_huc2_filename(tmp_path, sample_bands):
    date = datetime(2024, 4, 1)
    paths = plotter.plot_hypsometric(sample_bands, date, tmp_path)
    names = [Path(p).name for p in paths]
    assert 'snow_hypsometric_huc2_20240401.png' in names


def test_plot_hypsometric_huc4_filename(tmp_path, sample_bands):
    date = datetime(2024, 4, 1)
    paths = plotter.plot_hypsometric(sample_bands, date, tmp_path)
    names = [Path(p).name for p in paths]
    assert 'snow_hypsometric_huc4_20240401.png' in names


def test_plot_hypsometric_png_files_are_nonzero(tmp_path, sample_bands):
    date = datetime(2024, 4, 1)
    paths = plotter.plot_hypsometric(sample_bands, date, tmp_path)
    for p in paths:
        assert Path(p).stat().st_size > 1000  # at least 1 KB


def test_plot_hypsometric_creates_output_dir(tmp_path, sample_bands):
    date = datetime(2024, 4, 1)
    subdir = tmp_path / "new_subdir"
    plotter.plot_hypsometric(sample_bands, date, subdir)
    assert subdir.exists()


def test_plot_hypsometric_only_huc2_when_no_subbasins(tmp_path):
    date = datetime(2024, 4, 1)
    only_huc2 = {
        'Columbia River Basin': pd.DataFrame({
            'elev_band_m': [0, 250, 500],
            'mean_swe_mm': [0.0, 100.0, 200.0],
            'area_km2': [1000.0] * 3,
            'total_swe_volume_km3': [0.0, 0.1, 0.2],
        })
    }
    paths = plotter.plot_hypsometric(only_huc2, date, tmp_path)
    assert len(paths) == 1
    assert 'huc2' in Path(paths[0]).name
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_plotter.py -v
```

Expected: `ModuleNotFoundError: No module named 'plotter'`

- [ ] **Step 3: Write plotter.py**

```python
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

_PALETTE = [
    '#0072B2', '#E69F00', '#56B4E9', '#009E73',
    '#F0E442', '#D55E00', '#CC79A7', '#000000',
    '#999999', '#117733', '#882255', '#AA4499',
]

_HUC2_BASIN_KEY = 'Columbia River Basin'


def plot_hypsometric(
    bands_by_basin: dict,
    date: datetime,
    output_dir: Path,
) -> list:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    date_str = date.strftime('%Y%m%d')
    date_label = date.strftime('%B %d, %Y')
    written = []

    if _HUC2_BASIN_KEY in bands_by_basin:
        df = bands_by_basin[_HUC2_BASIN_KEY]
        fig, ax = plt.subplots(figsize=(8, 10))
        ax.plot(df['mean_swe_mm'], df['elev_band_m'],
                color=_PALETTE[0], linewidth=2)
        ax.set_xlabel('Mean SWE (mm)')
        ax.set_ylabel('Elevation (m)')
        ax.set_title(f'Columbia River Basin\nSWE by Elevation — {date_label}')
        ax.grid(True, alpha=0.3)
        path = output_dir / f'snow_hypsometric_huc2_{date_str}.png'
        fig.savefig(path, dpi=150, bbox_inches='tight')
        plt.close(fig)
        written.append(path)

    huc4 = {k: v for k, v in bands_by_basin.items() if k != _HUC2_BASIN_KEY}
    if huc4:
        fig, ax = plt.subplots(figsize=(10, 12))
        for i, (name, df) in enumerate(sorted(huc4.items())):
            ax.plot(df['mean_swe_mm'], df['elev_band_m'],
                    color=_PALETTE[i % len(_PALETTE)],
                    linewidth=1.5, label=name)
        ax.set_xlabel('Mean SWE (mm)')
        ax.set_ylabel('Elevation (m)')
        ax.set_title(f'Columbia River Basin — HUC4 Subbasins\nSWE by Elevation — {date_label}')
        ax.legend(loc='lower right', fontsize=8)
        ax.grid(True, alpha=0.3)
        path = output_dir / f'snow_hypsometric_huc4_{date_str}.png'
        fig.savefig(path, dpi=150, bbox_inches='tight')
        plt.close(fig)
        written.append(path)

    return written
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_plotter.py -v
```

Expected: all 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add plotter.py tests/test_plotter.py
git commit -m "feat: plotter — hypsometric curve PNGs for HUC2 and HUC4 basins"
```

---

## Task 7: main.py

**Files:**
- Create: `main.py`
- Create: `tests/test_main.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_main.py
import pytest
from datetime import datetime, date
from unittest.mock import patch, MagicMock
from pathlib import Path
import main


def test_parse_args_defaults():
    args = main.parse_args([])
    assert args.date == datetime.today().date()
    assert args.band_interval == 250
    assert args.output_dir == Path('output')


def test_parse_args_custom_date():
    args = main.parse_args(['--date', '2024-04-01'])
    assert args.date == date(2024, 4, 1)


def test_parse_args_invalid_date_exits():
    with pytest.raises(SystemExit):
        main.parse_args(['--date', 'not-a-date'])


def test_parse_args_custom_band_interval():
    args = main.parse_args(['--band-interval', '500'])
    assert args.band_interval == 500


def test_parse_args_custom_output_dir():
    args = main.parse_args(['--output-dir', '/tmp/out'])
    assert args.output_dir == Path('/tmp/out')


def test_run_calls_fetch_swe(tmp_path):
    with patch('main.fetch_swe', return_value=tmp_path / 'swe.tif') as mock_fetch, \
         patch('main.get_aligned_dem', return_value=tmp_path / 'dem.tif'), \
         patch('main.load_huc2', return_value=MagicMock(geometry=[MagicMock()], iterrows=lambda: iter([]))), \
         patch('main.load_huc4', return_value=MagicMock(iterrows=lambda: iter([]))), \
         patch('main.compute_bands', return_value=MagicMock()), \
         patch('main.plot_hypsometric', return_value=[]):
        (tmp_path / 'swe.tif').touch()
        (tmp_path / 'dem.tif').touch()
        dt = datetime(2024, 4, 1)
        main.run(dt, band_interval=250, output_dir=tmp_path)
        mock_fetch.assert_called_once_with(dt)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_main.py -v
```

Expected: `ModuleNotFoundError: No module named 'main'`

- [ ] **Step 3: Write main.py**

```python
import argparse
import sys
from datetime import datetime, date
from pathlib import Path

from basin_loader import load_huc2, load_huc4
from dem_processor import get_aligned_dem
from elevation_bands import compute_bands
from plotter import plot_hypsometric
from snodas_fetcher import fetch_swe


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate hypsometric SWE curves for the Columbia River Basin."
    )
    parser.add_argument(
        '--date',
        type=lambda s: datetime.strptime(s, '%Y-%m-%d').date(),
        default=datetime.today().date(),
        help='Date to plot (YYYY-MM-DD). Default: today.',
    )
    parser.add_argument(
        '--band-interval',
        type=int,
        default=250,
        dest='band_interval',
        help='Elevation band interval in metres. Default: 250.',
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=Path('output'),
        dest='output_dir',
        help='Directory for output PNGs. Default: output/',
    )
    return parser.parse_args(argv)


def run(dt: datetime, band_interval: int, output_dir: Path) -> None:
    print(f"Fetching SNODAS SWE for {dt.date()}...")
    swe_tif = fetch_swe(dt)

    print("Loading/building aligned DEM...")
    dem_tif = get_aligned_dem(swe_tif)

    print("Loading basin boundaries...")
    huc2 = load_huc2()
    huc4 = load_huc4()

    bands_by_basin = {}

    print("Computing elevation bands for Columbia River Basin (HUC2)...")
    huc2_geom = huc2.geometry.iloc[0]
    bands_by_basin['Columbia River Basin'] = compute_bands(
        swe_tif, dem_tif, huc2_geom, band_interval_m=band_interval
    )

    for _, row in huc4.iterrows():
        name = row['name']
        print(f"  Computing bands for {name}...")
        bands_by_basin[name] = compute_bands(
            swe_tif, dem_tif, row.geometry, band_interval_m=band_interval
        )

    print("Generating plots...")
    paths = plot_hypsometric(bands_by_basin, dt, output_dir)
    for p in paths:
        print(f"  Saved: {p}")


def main() -> None:
    args = parse_args()
    dt = datetime.combine(args.date, datetime.min.time())
    try:
        run(dt, band_interval=args.band_interval, output_dir=args.output_dir)
    except (ValueError, FileNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ConnectionError as e:
        print(f"Download failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_main.py -v
```

Expected: all 6 tests PASS

- [ ] **Step 5: Run the full test suite**

```bash
pytest tests/ -v
```

Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat: main.py — argparse CLI wiring full pipeline"
```

---

## Task 8: Integration Test & Smoke Test

**Files:**
- Create: `tests/test_integration.py`
- Create: `tests/fixtures/` (small real SNODAS GeoTIFF fixture)

- [ ] **Step 1: Create a small fixture SNODAS GeoTIFF**

Download one real SNODAS date and trim it to a small region for use as a fixture. Run this once:

```bash
cd /home/geoskimoto/projects/snow_elevation_plot
source venv/bin/activate
python - <<'EOF'
from datetime import datetime
from snodas_fetcher import fetch_swe
import rasterio
from rasterio.windows import from_bounds
from pathlib import Path

# Download a known-good date
tif = fetch_swe(datetime(2024, 4, 1))

# Trim to Columbia Basin bbox only (saves ~90% of file size)
out = Path("tests/fixtures/snodas_20240401_columbia.tif")
out.parent.mkdir(exist_ok=True)
with rasterio.open(tif) as src:
    window = from_bounds(-125, 42, -110, 50, src.transform)
    data = src.read(1, window=window)
    transform = src.window_transform(window)
    with rasterio.open(out, 'w', driver='GTiff',
                       height=data.shape[0], width=data.shape[1],
                       count=1, dtype='int16', crs=src.crs,
                       transform=transform, nodata=-9999,
                       compress='lzw') as dst:
        dst.write(data, 1)
print(f"Fixture written: {out} ({out.stat().st_size // 1024} KB)")
EOF
```

Expected output: `Fixture written: tests/fixtures/snodas_20240401_columbia.tif (XXXX KB)`

- [ ] **Step 2: Write integration test**

```python
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
    """Small synthetic DEM aligned to fixture SNODAS extent."""
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
```

- [ ] **Step 3: Run integration tests**

```bash
pytest tests/test_integration.py -v
```

Expected: both integration tests PASS (or SKIPPED if fixture not built yet)

- [ ] **Step 4: Run full test suite**

```bash
pytest tests/ -v --tb=short
```

Expected: all tests PASS

- [ ] **Step 5: Smoke test the CLI end-to-end**

```bash
python main.py --date 2024-04-01 --band-interval 250 --output-dir output/
```

Expected:
```
Fetching SNODAS SWE for 2024-04-01...
Loading/building aligned DEM...
Loading basin boundaries...
Computing elevation bands for Columbia River Basin (HUC2)...
  Computing bands for Kootenai-Pend Oreille-Spokane...
  ...
Generating plots...
  Saved: output/snow_hypsometric_huc2_20240401.png
  Saved: output/snow_hypsometric_huc4_20240401.png
```

- [ ] **Step 6: Final commit**

```bash
git add tests/test_integration.py tests/fixtures/
git commit -m "test: integration tests and SNODAS fixture for full pipeline validation"
```

---

## Dependency Versions Note

Run `pip freeze > requirements.txt` after successful install to capture exact pinned versions for reproducibility.
