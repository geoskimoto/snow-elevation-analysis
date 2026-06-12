# Snow Elevation Plot — Design Spec
**Date:** 2026-06-12  
**Status:** Approved

---

## Overview

A modular Python pipeline that produces hypsometric curve plots showing the distribution of snowpack (SWE) across elevation bands for the Columbia River Basin (HUC2) and each of its 12 HUC4 subbasins. Data source is SNODAS (1 km daily SWE). Plots are saved as PNG files. The architecture is designed for a future Dash web app conversion.

**Phase 1 (this spec):** Standalone CLI script — hypsometric curves for a user-specified date.  
**Phase 2 (future):** Dash app + time series by elevation band.

---

## Architecture

```
snow_elevation_plot/
├── main.py                        # CLI entry point
├── snodas_fetcher.py              # Download + cache SNODAS SWE GeoTIFFs
├── dem_processor.py               # Fetch SRTM, warp to SNODAS grid, cache
├── elevation_bands.py             # Bin SNODAS cells by elevation per basin
├── plotter.py                     # Draw hypsometric curve figures
├── basin_loader.py                # Load HUC2/HUC4 GeoJSON boundaries
├── data/
│   ├── cache/snodas/              # Cached SWE GeoTIFFs by date (YYYY/MM/YYYYMMDD_swe.tif)
│   ├── cache/dem/                 # Merged/warped SRTM DEM aligned to SNODAS grid
│   └── basemaps/                  # huc2_pnw.geojson, huc4_pnw.geojson
├── output/                        # Generated PNG figures
├── tests/
└── requirements.txt
```

**Data flow:**  
`main.py` → `snodas_fetcher` (SWE GeoTIFF for date) → `dem_processor` (elevation GeoTIFF on same grid) → `elevation_bands` (clip by HUC polygon, bin cells) → `plotter` (draw curves) → PNG saved to `output/`

---

## Data Sources

### SNODAS
- **Source:** NOAA FTP — `ftp://sidads.colorado.edu/pub/DATASETS/NOAA/G02158/masked/`
- **Variable:** SWE (product code `1034`), masked CONUS product
- **Resolution:** ~1 km (~30 arc-second), geographic CRS (EPSG:4326)
- **Coverage:** October 2003 to present
- **Cache key:** `data/cache/snodas/YYYY/MM/YYYYMMDD_swe.tif`
- **Disk management:** Raw `.tar` archives deleted immediately after GeoTIFF extraction (~15–20 MB per cached date, ~7 GB for a full water year)

### SRTM DEM
- **Source:** Fetched via `elevation` Python package (SRTM 90m tiles)
- **Processing:** Tiles merged, reprojected to SNODAS CRS, resampled to match SNODAS pixel grid exactly using `rasterio.warp.reproject`
- **Cache:** `data/cache/dem/columbia_basin_swe_aligned.tif` — computed once, reused every run
- **Purpose:** Assigns each SNODAS pixel an elevation value for band binning

### Basemaps
- `huc2_pnw.geojson` — Columbia River Basin boundary (1 feature)
- `huc4_pnw.geojson` — 12 HUC4 subbasins
- Copied from `usgs-streamflow-dashboard/data/basemaps/` at setup time

---

## Module Designs

### `snodas_fetcher.py`
- `fetch_swe(date: datetime) -> Path`  
  Checks cache first. If missing: downloads daily `.tar` from NOAA FTP, extracts SWE `.dat` file, converts to GeoTIFF, saves to cache, deletes `.tar`. Returns path to cached `_swe.tif`.  
  Handles NOAA filename format differences pre/post 2013.

### `dem_processor.py`
- `get_aligned_dem(snodas_tif: Path) -> Path`  
  If `columbia_basin_swe_aligned.tif` exists in cache, return it. Otherwise: fetch SRTM tiles for Columbia Basin bbox, merge, reproject and resample to exactly match SNODAS grid pixel-for-pixel, save to cache, return path.

### `basin_loader.py`
- `load_huc2() -> GeoDataFrame` — Columbia Basin polygon
- `load_huc4() -> GeoDataFrame` — 12 HUC4 subbasin polygons with `huc4` and `name` attributes

### `elevation_bands.py`
- `compute_bands(swe_tif: Path, dem_tif: Path, basin_geom: Geometry, band_interval_m: int = 250) -> pd.DataFrame`  
  Masks both rasters to basin polygon. Bins pixels by elevation. Returns DataFrame with columns:  
  `elev_band_m` (band floor), `mean_swe_mm`, `area_km2`, `total_swe_volume_km3`  
  Empty bands (zero valid pixels) are excluded from output. Area-weighted stats so curves reflect true snow volume distribution.

### `plotter.py`
- `plot_hypsometric(bands_by_basin: dict[str, pd.DataFrame], date: datetime, output_dir: Path) -> list[Path]`  
  Draws hypsometric curves: elevation (m) on Y-axis, mean SWE (mm) on X-axis. One labeled curve per basin. Colorblind-safe palette (matplotlib `tab10` or similar). Axes labeled with units. Title includes date.  
  Produces two PNG files in `output_dir`:
  1. `snow_hypsometric_huc2_YYYYMMDD.png` — Columbia River Basin as a whole
  2. `snow_hypsometric_huc4_YYYYMMDD.png` — all 12 HUC4 subbasins overlaid
  Returns list of written file paths.

### `main.py`
CLI entry point using `argparse`:
```
python main.py [--date YYYY-MM-DD] [--band-interval INT] [--output-dir PATH]
```
- `--date`: default = today's date
- `--band-interval`: default = 250 (meters)
- `--output-dir`: default = `output/`

---

## Error Handling

| Scenario | Behavior |
|---|---|
| SNODAS FTP timeout / date unavailable | Clear message with requested date, suggest trying previous date, exit cleanly, no partial cache files |
| Date before October 2003 | Validate at entry, print friendly message, exit |
| SNODAS no-data pixels (`-9999`) | Mask before binning — sparse high-elevation bands not skewed |
| Elevation band with no valid pixels (fully masked) | Skip band entirely — not plotted |
| Elevation band with valid pixels but SWE = 0 | Include band — zero SWE is meaningful (no snow at that elevation) |
| DEM/SWE pixel grid mismatch after warp | Raise descriptive exception — never silently produce wrong results |
| Missing geojson files | Check `data/basemaps/` at startup, print actionable message if absent |

---

## Testing Strategy

- **Unit:** Each module tested with small synthetic rasters (3×3 GeoTIFFs) — no real downloads required
- **Integration:** One test using a real cached SNODAS date (checked-in fixture) verifying full pipeline produces expected DataFrame shape and value ranges
- **Property:** Elevation band areas sum to full basin area; mean SWE always within valid SNODAS range (0–2000 mm)
- **Snapshot:** Reference PNG compared against known-good output for a fixed date to catch plotting regressions

---

## Disk Usage Estimates

| Item | Size | Notes |
|---|---|---|
| Aligned DEM cache | 50–100 MB | One-time, permanent |
| SNODAS per date | ~15–20 MB | `.tar` deleted after extraction |
| Full water year cache | ~5–7 GB | Optional — only if running historical analysis |
| Output PNGs | ~1–2 MB each | Negligible |

Available disk: 50 GB — no constraints needed for typical use.

---

## Future Work (Phase 2)

- **Dash app:** Date picker + subbasin selector driving the same data layer functions
- **Time series by elevation band:** Date on X-axis, SWE on Y-axis, separate lines per elevation band — shows seasonal accumulation/melt by elevation
- **HUC8 drill-down:** Click a HUC4 subbasin to show its HUC8 breakdown
