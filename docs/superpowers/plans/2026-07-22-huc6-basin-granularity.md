# HUC6 Basin Granularity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the basin structure with standard WBD HUC2/HUC4/HUC6 (35 basins), key all stats on `huc` codes, add HUC6 drill-down UI, put SWANN dormant, and stage a full-record SNODAS recompute.

**Architecture:** `basin_loader.load_all_basins()` becomes the single source of the 35 `(huc, name, geometry)` rows. Parquet schema gains a `huc` column that is the unique key everywhere (display `basin` names collide across levels; codes don't). Charts stay name-keyed (callers translate huc→name); only the Historical dropdown surfaces codes. Recompute is staged: WY2026 from cached rasters into a rebuild dir, atomic swap, then a multi-day historical re-download appends into the live dir.

**Tech Stack:** Python 3.12, Dash/Plotly, geopandas (WBD geojson), rasterio, pandas/parquet, pytest. Basemaps from USGS WBD ArcGIS REST (`hydro.nationalmap.gov/arcgis/rest/services/wbd/MapServer`, layer 2 = HUC4, layer 3 = HUC6 — verified live 2026-07-22).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-22-huc6-basin-granularity-design.md`.
- Python is ALWAYS `venv/bin/python`. Full suite before every commit: `venv/bin/python -m pytest tests/` — tests updated in the SAME commit as the behavior they cover. Never modify application code to make failing tests pass; never modify a task's own brief-specified tests to make implementation pass. Unexpected failure → stop and report.
- Running as root: commit via `sudo -u geoskimoto git add ... && sudo -u geoskimoto git commit -m "..."`; `chown geoskimoto:geoskimoto` anything created. Commit format `<tag>: <summary>`.
- **SWANN is dormant, not deleted:** all `dataset=` machinery, `swann_fetcher.py`, and registry entries stay; SWANN code paths must still compile and their tests pass (updated to new signatures where shared helpers change). No SWANN execution, no SWANN UI option, no SWANN recompute.
- **Schema (spec-fixed):** volume parquets `[date, huc, basin, total_swe_volume_km3]`; band caches `[huc, basin, elev_band_m, mean_swe_mm, area_km2, total_swe_volume_km3]`. `huc` = WBD code string (`'17'`, `'1706'`, `'170602'`) is the unique key; idempotency on `(date, huc)`; level = `len(huc)`. No backward-compat shim — but `load_band_cache` must return `None` (cache miss) for old-schema files so the 8,311 stale caches force recompute instead of poisoning results.
- HUC2 display name stays **'Columbia River Basin'** (the app's existing label; WBD calls region 17 "Pacific Northwest Region" — `load_all_basins` overrides the name for code `'17'` only).
- 35 basins: `'17'` + 12 HUC4 (1701–1712) + 22 HUC6 (verified inventory: 170101 Kootenai, 170102 Pend Oreille, 170103 Spokane, 170200 Upper Columbia, 170300 Yakima, 170401 Snake Headwaters, 170402 Upper Snake, 170501 Middle Snake-Boise, 170502 Middle Snake-Powder, 170601 Lower Snake, 170602 Salmon, 170603 Clearwater, 170701 Middle Columbia, 170702 John Day, 170703 Deschutes, 170800 Lower Columbia, 170900 Willamette, 171001 Washington Coastal, 171002 Northern Oregon Coastal, 171003 Southern Oregon Coastal, 171100 Puget Sound, 171200 Oregon Closed Basins).
- `min_band_area_km2` stays `100.0` at all levels.
- The live app keeps serving old-schema data until Task 7's swap; do not restart the service or touch `data/cache/timeseries/` contents before Task 7.

## File Structure

- Create `scripts/fetch_wbd_basemaps.py` — one-time committed fetch script (reproducibility).
- Create `data/basemaps/huc6_pnw.geojson`; replace `data/basemaps/huc4_pnw.geojson` (standard 12).
- Modify `basin_loader.py` (+`load_huc6`, `load_all_basins`), `timeseries.py` (schema + `names` + `ts_dir`), `pipeline.py` (band-cache schema + 35-basin loop + store payload), `climatology.py` (huc-keyed), `charts.py` (`group_label` param), `layout.py` (drill-downs, hidden radio), `callbacks.py` (drill-down callbacks, code-valued dropdown), `update_timeseries.py`, `populate_timeseries.py` (`--end`, `--stage-dir`, basins loop).
- Tests: new `tests/test_basemaps.py`; updates to `test_basin_loader.py`, `test_timeseries.py`, `test_pipeline.py`, `test_climatology.py`, `test_charts.py`, `test_layout.py`, `test_callbacks.py`, `test_populate_timeseries.py`, `test_update_timeseries.py`, `test_integration.py` (whichever assert old names/schema).

---

### Task 1: WBD basemaps + `basin_loader`

**Files:**
- Create: `scripts/fetch_wbd_basemaps.py`, `data/basemaps/huc6_pnw.geojson`
- Replace: `data/basemaps/huc4_pnw.geojson` (keep no `.bak`; git history preserves the old file)
- Modify: `basin_loader.py`
- Test: `tests/test_basemaps.py`, extend `tests/test_basin_loader.py`

**Interfaces:**
- Produces:
  - `basin_loader.load_huc6() -> gpd.GeoDataFrame` (columns include `huc6`, `name`, `geometry`; EPSG:4326)
  - `basin_loader.load_all_basins() -> gpd.GeoDataFrame` with EXACTLY columns `['huc', 'name', 'geometry']`, 35 rows, EPSG:4326, sorted by `huc`; row `'17'` has `name == 'Columbia River Basin'`.
  - `load_huc2`/`load_huc4` unchanged in signature (huc4 now returns the standard 12).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_basemaps.py`:

```python
"""Integrity tests for the committed WBD basemaps (35-basin structure)."""
import geopandas as gpd
import pytest

from basin_loader import load_huc2, load_huc4, load_huc6, load_all_basins


def test_huc4_is_standard_twelve():
    g = load_huc4()
    assert sorted(g["huc4"]) == [f"17{i:02d}" for i in range(1, 13)]
    # no custom pseudo-codes survive
    assert not any(c.endswith(("a", "b")) for c in g["huc4"])


def test_huc6_is_twentytwo_and_nested():
    g6 = load_huc6()
    assert len(g6) == 22
    huc4s = set(load_huc4()["huc4"])
    assert all(c[:4] in huc4s for c in g6["huc6"])
    assert g6.geometry.is_valid.all()


def test_load_all_basins_shape_and_key():
    b = load_all_basins()
    assert list(b.columns) == ["huc", "name", "geometry"]
    assert len(b) == 35
    assert b["huc"].is_unique
    assert list(b["huc"]) == sorted(b["huc"])
    assert set(b["huc"].str.len().unique()) == {2, 4, 6}
    assert b.loc[b["huc"] == "17", "name"].iloc[0] == "Columbia River Basin"
    assert b.crs.to_epsg() == 4326


def test_name_collisions_exist_but_codes_disambiguate():
    b = load_all_basins()
    assert b["name"].duplicated().any()      # e.g. Yakima at 1703 and 170300
    assert b["huc"].is_unique


def test_salmon_and_clearwater_present():
    b = load_all_basins().set_index("huc")
    assert b.loc["170602", "name"] == "Salmon"
    assert b.loc["170603", "name"] == "Clearwater"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_basemaps.py -v`
Expected: FAIL (`ImportError: cannot import name 'load_huc6'`).

- [ ] **Step 3: Write the fetch script**

Create `scripts/fetch_wbd_basemaps.py`:

```python
"""One-time fetch of standard WBD basemaps for region 17 from the USGS
WBD ArcGIS REST service. Writes data/basemaps/huc4_pnw.geojson (12
subregions) and data/basemaps/huc6_pnw.geojson (22 basins). Committed for
reproducibility; not part of any scheduled job.

Usage: venv/bin/python scripts/fetch_wbd_basemaps.py
"""
import sys
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://hydro.nationalmap.gov/arcgis/rest/services/wbd/MapServer"
OUT = Path(__file__).resolve().parent.parent / "data" / "basemaps"
# (layer id, code field, where clause, output filename, expected count)
LAYERS = [
    (2, "huc4", "huc4 LIKE '17%'", "huc4_pnw.geojson", 12),
    (3, "huc6", "huc6 LIKE '17%'", "huc6_pnw.geojson", 22),
]


def fetch(layer: int, field: str, where: str) -> bytes:
    params = urllib.parse.urlencode({
        "where": where,
        "outFields": f"{field},name,areasqkm,states",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
    })
    url = f"{BASE}/{layer}/query?{params}"
    with urllib.request.urlopen(url, timeout=300) as resp:
        return resp.read()


def main() -> None:
    import geopandas as gpd
    for layer, field, where, filename, expected in LAYERS:
        raw = fetch(layer, field, where)
        path = OUT / filename
        path.write_bytes(raw)
        g = gpd.read_file(path)
        if len(g) != expected:
            print(f"ERROR: {filename}: got {len(g)} features, expected {expected}",
                  file=sys.stderr)
            sys.exit(1)
        if not g.geometry.is_valid.all():
            print(f"ERROR: {filename}: invalid geometries", file=sys.stderr)
            sys.exit(1)
        print(f"{filename}: {len(g)} features OK")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the fetch (network; ~3 MB total)**

Run: `venv/bin/python scripts/fetch_wbd_basemaps.py`
Expected: `huc4_pnw.geojson: 12 features OK` / `huc6_pnw.geojson: 22 features OK`.
Then delete the stale backup: `rm data/basemaps/huc4_pnw.geojson.bak` (git history preserves the custom-split originals). `chown geoskimoto:geoskimoto data/basemaps/*.geojson`.

- [ ] **Step 5: Extend `basin_loader.py`**

Replace the file's contents with:

```python
from pathlib import Path

import geopandas as gpd
import pandas as pd

BASEMAP_DIR = Path(__file__).parent / "data" / "basemaps"

# The app brands WBD region 17 ("Pacific Northwest Region") as the Columbia
# River Basin — keep that display name for code '17' only.
_HUC2_DISPLAY_NAME = "Columbia River Basin"


def _load(filename: str) -> gpd.GeoDataFrame:
    path = BASEMAP_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"{filename} not found in {BASEMAP_DIR}")
    return gpd.read_file(path).to_crs(epsg=4326)


def load_huc2() -> gpd.GeoDataFrame:
    return _load("huc2_pnw.geojson")


def load_huc4() -> gpd.GeoDataFrame:
    return _load("huc4_pnw.geojson")


def load_huc6() -> gpd.GeoDataFrame:
    return _load("huc6_pnw.geojson")


def load_all_basins() -> gpd.GeoDataFrame:
    """All 35 basins as rows of (huc, name, geometry), sorted by huc.

    huc is the WBD code string ('17', '1706', '170602') and is the unique
    key used by every parquet, cache, and callback; name is display-only
    (names collide across levels — e.g. Yakima is both 1703 and 170300).
    """
    frames = []
    for gdf, code_col in ((load_huc2(), "huc2"),
                          (load_huc4(), "huc4"),
                          (load_huc6(), "huc6")):
        f = gdf[[code_col, "name", "geometry"]].rename(columns={code_col: "huc"})
        frames.append(f)
    out = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326")
    out["huc"] = out["huc"].astype(str)
    out.loc[out["huc"] == "17", "name"] = _HUC2_DISPLAY_NAME
    return out.sort_values("huc").reset_index(drop=True)
```

- [ ] **Step 6: Run tests**

Run: `venv/bin/python -m pytest tests/test_basemaps.py tests/test_basin_loader.py -v`
Expected: `test_basemaps.py` all PASS. If `test_basin_loader.py` asserts the old custom-split names/counts, update those assertions to the standard-12 reality in this commit (intended behavior change; list each in the report).

- [ ] **Step 7: Full suite, then commit**

Run: `venv/bin/python -m pytest tests/`
Expected: failures ONLY in tests that assert old basin names from the replaced huc4 file (e.g. integration tests). If such failures exist, note them in the report — they are fixed by later tasks IF they concern schema; but tests that merely name 'Kootenai' as a huc4 must be updated NOW (same-commit rule for this task's behavior change). Anything else unexpected → STOP.

```bash
sudo -u geoskimoto git add scripts/fetch_wbd_basemaps.py data/basemaps/huc4_pnw.geojson data/basemaps/huc6_pnw.geojson basin_loader.py tests/test_basemaps.py tests/test_basin_loader.py
sudo -u geoskimoto git rm --cached -q data/basemaps/huc4_pnw.geojson.bak 2>/dev/null || true
sudo -u geoskimoto git commit -m "feat: standard WBD HUC4/HUC6 basemaps + load_all_basins (35-basin structure)"
```

---

### Task 2: huc-keyed schema in `timeseries.py` + band caches in `pipeline.py`

**Files:**
- Modify: `timeseries.py`, `pipeline.py` (cache functions only — `run_pipeline` is Task 4)
- Test: extend `tests/test_timeseries.py`, `tests/test_pipeline.py`

**Interfaces:**
- Consumes: nothing new (pure schema change).
- Produces:
  - `timeseries._COLUMNS = ['date', 'huc', 'basin', 'total_swe_volume_km3']`
  - `timeseries.append_volumes(date, bands_by_huc: dict[str, pd.DataFrame], names: dict[str, str], cache_dir, dataset='snodas', ts_dir: Path | None = None)` — idempotent on `(date, huc)`; `ts_dir` overrides the parquet directory (staging support).
  - `timeseries.load_timeseries(wy, cache_dir, dataset='snodas', ts_dir=None) -> pd.DataFrame` (new columns, sorted by `huc, date`).
  - `pipeline.save_band_cache(bands_by_huc, names, date_key, cache_dir, dataset='snodas')` — parquet columns `[huc, basin, elev_band_m, mean_swe_mm, area_km2, total_swe_volume_km3]`.
  - `pipeline.load_band_cache(date_key, cache_dir, dataset='snodas') -> tuple[dict[str, pd.DataFrame], dict[str, str]] | None` — returns `(bands_by_huc, names)`; returns **None** when the file is missing OR lacks a `huc` column (old-schema ⇒ cache miss).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_timeseries.py`:

```python
import pandas as pd
from datetime import datetime
from pathlib import Path


def _band_df():
    return pd.DataFrame({
        "elev_band_m": [1000], "mean_swe_mm": [100.0],
        "area_km2": [50.0], "total_swe_volume_km3": [0.005],
    })


def test_append_volumes_huc_schema_and_idempotency(tmp_path):
    from timeseries import append_volumes, load_timeseries

    bands = {"17": _band_df(), "170602": _band_df()}
    names = {"17": "Columbia River Basin", "170602": "Salmon"}
    append_volumes(datetime(2026, 1, 15), bands, names, tmp_path)
    append_volumes(datetime(2026, 1, 15), bands, names, tmp_path)  # no dupes

    df = load_timeseries(2026, tmp_path)
    assert list(df.columns) == ["date", "huc", "basin", "total_swe_volume_km3"]
    assert len(df) == 2
    assert set(df["huc"]) == {"17", "170602"}
    assert df.loc[df["huc"] == "170602", "basin"].iloc[0] == "Salmon"


def test_append_volumes_name_collision_safe(tmp_path):
    """Two different hucs sharing a display name must both be stored."""
    from timeseries import append_volumes, load_timeseries

    bands = {"1703": _band_df(), "170300": _band_df()}
    names = {"1703": "Yakima", "170300": "Yakima"}
    append_volumes(datetime(2026, 1, 15), bands, names, tmp_path)
    df = load_timeseries(2026, tmp_path)
    assert len(df) == 2
    assert set(df["huc"]) == {"1703", "170300"}


def test_append_volumes_ts_dir_override(tmp_path):
    from timeseries import append_volumes, load_timeseries

    stage = tmp_path / "rebuild"
    append_volumes(datetime(2026, 1, 15), {"17": _band_df()},
                   {"17": "Columbia River Basin"}, tmp_path, ts_dir=stage)
    assert (stage / "WY2026_volume.parquet").exists()
    assert not (tmp_path / "timeseries" / "WY2026_volume.parquet").exists()
    assert len(load_timeseries(2026, tmp_path, ts_dir=stage)) == 1
```

Append to `tests/test_pipeline.py`:

```python
def test_band_cache_roundtrip_huc_schema(tmp_path):
    import pandas as pd
    from pipeline import save_band_cache, load_band_cache

    band = pd.DataFrame({
        "elev_band_m": [1000], "mean_swe_mm": [100.0],
        "area_km2": [50.0], "total_swe_volume_km3": [0.005],
    })
    save_band_cache({"170602": band}, {"170602": "Salmon"}, "20260115", tmp_path)
    out = load_band_cache("20260115", tmp_path)
    assert out is not None
    bands_by_huc, names = out
    assert set(bands_by_huc) == {"170602"}
    assert names["170602"] == "Salmon"
    assert "huc" not in bands_by_huc["170602"].columns  # values are pure band frames


def test_load_band_cache_old_schema_is_cache_miss(tmp_path):
    """Pre-HUC6 caches (basin-keyed, no huc column) must read as None so
    the recompute regenerates them instead of using stale basin sets."""
    import pandas as pd
    from pipeline import load_band_cache

    old = pd.DataFrame({
        "basin": ["Kootenai"], "elev_band_m": [1000], "mean_swe_mm": [100.0],
        "area_km2": [50.0], "total_swe_volume_km3": [0.005],
    })
    path = tmp_path / "bands" / "20260115_250m.parquet"
    path.parent.mkdir(parents=True)
    old.to_parquet(path, index=False)
    assert load_band_cache("20260115", tmp_path) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_timeseries.py tests/test_pipeline.py -v`
Expected: new tests FAIL (`TypeError` on signatures / tuple-unpack).

- [ ] **Step 3: Implement `timeseries.py`**

Replace `_COLUMNS`, `_empty_df`, `_parquet_path`, `append_volumes`, `load_timeseries` (docstrings updated accordingly; `water_year` unchanged):

```python
_COLUMNS = ['date', 'huc', 'basin', 'total_swe_volume_km3']


def _empty_df() -> pd.DataFrame:
    return pd.DataFrame({
        'date': pd.Series([], dtype='datetime64[ns]'),
        'huc': pd.Series([], dtype=str),
        'basin': pd.Series([], dtype=str),
        'total_swe_volume_km3': pd.Series([], dtype=float),
    })


def _parquet_path(wy: int, cache_dir: Path, dataset: str = 'snodas',
                  ts_dir: Path | None = None) -> Path:
    if ts_dir is not None:
        return Path(ts_dir) / f'WY{wy}_volume.parquet'
    base = cache_dir / 'timeseries'
    if dataset != 'snodas':
        base = base / dataset
    return base / f'WY{wy}_volume.parquet'


def append_volumes(date: datetime, bands_by_huc: dict[str, pd.DataFrame],
                   names: dict[str, str], cache_dir: Path,
                   dataset: str = 'snodas', ts_dir: Path | None = None) -> None:
    """Sum total_swe_volume_km3 per basin and append one row per huc code.

    bands_by_huc maps WBD huc code -> band DataFrame; names maps huc code ->
    display name (codes are the unique key: display names collide across
    HUC levels). Idempotent on (date, huc). ts_dir overrides the output
    directory (used by the staged rebuild); default routing is unchanged.
    """
    wy = water_year(date)
    path = _parquet_path(wy, cache_dir, dataset, ts_dir)
    path.parent.mkdir(parents=True, exist_ok=True)

    existing = pd.read_parquet(path) if path.exists() else _empty_df()
    ts = pd.Timestamp(date)

    new_rows = []
    for huc, df in bands_by_huc.items():
        already = (
            len(existing) > 0
            and ((existing['date'] == ts) & (existing['huc'] == huc)).any()
        )
        if already:
            continue
        new_rows.append({
            'date': ts,
            'huc': huc,
            'basin': names[huc],
            'total_swe_volume_km3': float(df['total_swe_volume_km3'].sum()),
        })

    if not new_rows:
        return
    combined = pd.concat([existing, pd.DataFrame(new_rows)], ignore_index=True)
    combined['date'] = pd.to_datetime(combined['date'])
    combined[_COLUMNS].to_parquet(path, index=False)


def load_timeseries(wy: int, cache_dir: Path, dataset: str = 'snodas',
                    ts_dir: Path | None = None) -> pd.DataFrame:
    """Read the WY parquet; columns [date, huc, basin, total_swe_volume_km3]
    sorted by (huc, date). Empty DataFrame with those columns if absent."""
    path = _parquet_path(wy, cache_dir, dataset, ts_dir)
    if not path.exists():
        return _empty_df()
    df = pd.read_parquet(path)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values(['huc', 'date']).reset_index(drop=True)
    return df[_COLUMNS]
```

- [ ] **Step 4: Implement `pipeline.py` cache functions**

Replace `save_band_cache` and `load_band_cache` (`_cache_path` unchanged):

```python
def save_band_cache(bands_by_huc: dict, names: dict, date_key: str,
                    cache_dir: Path, dataset: str = 'snodas') -> None:
    path = _cache_path(date_key, cache_dir, dataset)
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = []
    for huc, df in bands_by_huc.items():
        row = df.copy()
        row.insert(0, 'basin', names[huc])
        row.insert(0, 'huc', huc)
        frames.append(row)
    pd.concat(frames).to_parquet(path, index=False)


def load_band_cache(date_key: str, cache_dir: Path,
                    dataset: str = 'snodas') -> tuple[dict, dict] | None:
    """Return (bands_by_huc, names) or None on miss. Old-schema files
    (pre-HUC6, no 'huc' column) read as a miss so stale basin sets are
    recomputed rather than reused."""
    path = _cache_path(date_key, cache_dir, dataset)
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    if 'huc' not in df.columns:
        return None
    bands_by_huc = {
        huc: group.drop(columns=['huc', 'basin']).reset_index(drop=True)
        for huc, group in df.groupby('huc')
    }
    names = dict(df.groupby('huc')['basin'].first())
    return bands_by_huc, names
```

Callers inside `pipeline.run_pipeline`, `update_timeseries.py`, and `populate_timeseries.py` still use old signatures and will FAIL TO RUN until Tasks 4/6 — that is expected mid-branch; the failing suite entries for those modules' integration points must be limited to signature errors you can attribute to this sequencing. Run the two test files from Step 1 plus `tests/test_climatology.py`; if `test_update_timeseries.py`/`test_populate_timeseries.py`/`test_callbacks.py` now fail on the changed signatures, update ONLY the direct-call fixtures in them (seeding via `append_volumes(...)` etc.) in this commit; leave their behavioral assertions for later tasks. Anything else unexpected → STOP.

- [ ] **Step 5: Run tests, full suite, commit**

Run: `venv/bin/python -m pytest tests/ -x -q` (fix fixture fallout per Step 4 note).

```bash
sudo -u geoskimoto git add timeseries.py pipeline.py tests/
sudo -u geoskimoto git commit -m "feat: huc-code-keyed volume/band schema with staging override and old-cache invalidation"
```

---

### Task 3: huc-keyed `climatology.py`

**Files:**
- Modify: `climatology.py`
- Test: extend `tests/test_climatology.py`

**Interfaces:**
- Consumes: Task 2 parquet schema.
- Produces (all filter args renamed `basin` → `huc`, filtering on the `huc` column):
  - `load_all_water_years(cache_dir, dataset='snodas')` → columns `[date, huc, basin, total_swe_volume_km3, wy]`
  - `compute_climatology(df, huc, current_wy)`, `current_series(df, huc, current_wy)`, `n_historical_years(df, huc, current_wy)`, `summarize_current(df, huc, current_wy)` — same return shapes as today.
  - `display_name(df, huc) -> str` — the `basin` value for that huc (`''` if absent).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_climatology.py`:

```python
def test_climatology_huc_keyed_and_collision_safe(tmp_path):
    import pandas as pd
    from datetime import datetime
    import climatology
    from timeseries import append_volumes

    band = pd.DataFrame({
        "elev_band_m": [1000], "mean_swe_mm": [100.0],
        "area_km2": [50.0], "total_swe_volume_km3": [1.0],
    })
    names = {"1703": "Yakima", "170300": "Yakima"}
    for yr in (2004, 2005, 2006, 2007):
        for day in (10, 11, 12):
            bands = {"1703": band, "170300": band * 2}
            append_volumes(datetime(yr, 1, day), bands, names, tmp_path)

    df = climatology.load_all_water_years(tmp_path)
    assert "huc" in df.columns

    clim4 = climatology.compute_climatology(df, "1703", 2026)
    clim6 = climatology.compute_climatology(df, "170300", 2026)
    assert not clim4.empty and not clim6.empty
    # the two same-named basins have different volumes -> different medians
    assert clim6["p50"].iloc[0] > clim4["p50"].iloc[0]
    assert climatology.n_historical_years(df, "1703", 2026) == 4
    assert climatology.display_name(df, "1703") == "Yakima"
    assert climatology.display_name(df, "9999") == ""
```

- [ ] **Step 2: Run to verify failure**

Run: `venv/bin/python -m pytest tests/test_climatology.py -v`
Expected: new test FAILS (KeyError 'huc' / AttributeError `display_name`).

- [ ] **Step 3: Implement**

In `climatology.py`:
1. `_COLUMNS = ['date', 'huc', 'basin', 'total_swe_volume_km3', 'wy']`; `_empty_df` gains `'huc': pd.Series([], dtype=str)`; `load_all_water_years` selects `df[['date', 'huc', 'basin', 'total_swe_volume_km3']]` before tagging `wy`.
2. Replace `_HUC2_KEY = 'Columbia River Basin'` with `_HUC2_CODE = '17'`.
3. Every `df['basin'] == basin` filter becomes `df['huc'] == huc`; rename the `basin` parameter to `huc` in `n_historical_years`, `compute_climatology`, `current_series`, `summarize_current` (bodies otherwise unchanged).
4. Add:

```python
def display_name(df: pd.DataFrame, huc: str) -> str:
    """Display name for a huc code, from the data itself ('' if absent)."""
    if df.empty:
        return ''
    rows = df.loc[df['huc'] == huc, 'basin']
    return str(rows.iloc[0]) if len(rows) else ''
```

Update the module docstring's function list accordingly. Existing tests seeding old-schema frames must be updated to seed via `append_volumes` with names dicts (same commit; list each change in the report).

- [ ] **Step 4: Run tests, full suite, commit**

Run: `venv/bin/python -m pytest tests/test_climatology.py -v`, then `venv/bin/python -m pytest tests/ -q` (same sequencing tolerance as Task 2 Step 4: signature-fallout fixture updates allowed, behavior changes not).

```bash
sudo -u geoskimoto git add climatology.py tests/test_climatology.py tests/
sudo -u geoskimoto git commit -m "feat: huc-code-keyed climatology with display_name lookup"
```

---

### Task 4: `pipeline.run_pipeline` over 35 basins + `charts.py` group labels

**Files:**
- Modify: `pipeline.py` (`run_pipeline`), `charts.py`
- Test: extend `tests/test_pipeline.py`, `tests/test_charts.py`

**Interfaces:**
- Consumes: `basin_loader.load_all_basins()`, Task 2 cache/volume signatures.
- Produces:
  - `charts.make_huc4_figure(bands_by_name, date, dataset_label=..., group_label='HUC4 Subbasins')` — same for `make_huc4_volume_figure` and `make_huc4_timeseries_figure` (`group_label` replaces the hardcoded `'HUC4 Subbasins'` in titles; default preserves current output).
  - `pipeline.run_pipeline(date_str, set_progress=None, dataset='snodas') -> dict` — same keys as today PLUS `'huc6_bands'`: `{huc: df.to_dict('records')}` for the 22 HUC6 basins and `'names'`: `{huc: name}` for all 35 (serializable; feeds the Snowpack drill-down without recompute).
  - The HUC2 chart uses huc `'17'`; the huc4 overlay charts use the 12 HUC4s keyed by display name; band cache and volumes cover all 35.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_charts.py`:

```python
def test_group_label_overrides_title():
    from datetime import datetime
    import pandas as pd
    import charts

    bands = pd.DataFrame({
        "elev_band_m": [1000], "mean_swe_mm": [100.0],
        "area_km2": [50.0], "total_swe_volume_km3": [0.005],
    })
    fig = charts.make_huc4_figure({"Salmon": bands}, datetime(2026, 1, 15),
                                  group_label="Lower Snake HUC6 Basins")
    assert "Lower Snake HUC6 Basins" in fig.layout.title.text
    default = charts.make_huc4_figure({"Salmon": bands}, datetime(2026, 1, 15))
    assert "HUC4 Subbasins" in default.layout.title.text
```

Append to `tests/test_pipeline.py`:

```python
def test_run_pipeline_computes_35_basins_and_exposes_huc6(tmp_path, monkeypatch):
    """run_pipeline must band all 35 basins and return huc6 bands + names."""
    import pandas as pd
    import pipeline
    import config

    monkeypatch.setenv("CACHE_DIR", str(tmp_path))
    computed = []

    def fake_compute(swe_tif, dem_tif, geom, min_band_area_km2=0.0):
        computed.append(1)
        return pd.DataFrame({
            "elev_band_m": [1000], "mean_swe_mm": [100.0],
            "area_km2": [500.0], "total_swe_volume_km3": [0.05],
        })

    monkeypatch.setattr(pipeline, "compute_bands", fake_compute)
    monkeypatch.setattr(pipeline, "fetch_swe", lambda d, cache_dir: tmp_path / "x.tif")
    monkeypatch.setattr(pipeline, "get_aligned_dem", lambda s, dem_cache: tmp_path / "d.tif")
    monkeypatch.setattr(pipeline, "plot_hypsometric", lambda b, d, o: [])

    result = pipeline.run_pipeline("2026-01-15")
    assert result["error"] is None
    assert len(computed) == 35
    assert len(result["huc6_bands"]) == 22
    assert result["names"]["170602"] == "Salmon"
    assert isinstance(result["huc6_bands"]["170602"], list)  # records, serializable
```

- [ ] **Step 2: Run to verify failure**

Run: `venv/bin/python -m pytest tests/test_charts.py tests/test_pipeline.py -v`
Expected: new tests FAIL.

- [ ] **Step 3: Implement `charts.py`**

In `make_huc4_figure`, `make_huc4_volume_figure`, `make_huc4_timeseries_figure`: add keyword `group_label: str = 'HUC4 Subbasins'` and replace the literal in the title f-string, e.g.:

```python
def make_huc4_figure(bands_by_subbasin: dict, date: datetime,
                     dataset_label: str = _DEFAULT_DATASET_LABEL,
                     group_label: str = 'HUC4 Subbasins') -> go.Figure:
    ...
    title=dict(text=f'{group_label} — SWE by Elevation · {dataset_label}<br>{date_label}', ...)
```

(`make_huc4_timeseries_figure` title: `f'{group_label} — SWE Volume WY{wy} · {dataset_label}'`. Its body currently filters `df['basin'] != 'Columbia River Basin'` — change to accept the frame as given, no filtering: callers now pre-filter by huc level. Note this in the report.)

- [ ] **Step 4: Implement `pipeline.run_pipeline`**

Replace the basin loop and result assembly (progress/DEM/fetch/error scaffolding unchanged; `_HUC2_KEY` constant deleted; import `load_all_basins` instead of `load_huc2`/`load_huc4`):

```python
        basins = load_all_basins()
        names = dict(zip(basins['huc'], basins['name']))

        cached = load_band_cache(date_key, cache_dir, dataset)
        if cached is None:
            bands_by_huc = {
                row.huc: compute_bands(swe_tif, dem_tif, row.geometry,
                                       min_band_area_km2=100.0)
                for row in basins.itertuples()
            }
            save_band_cache(bands_by_huc, names, date_key, cache_dir, dataset)
        else:
            bands_by_huc, names = cached

        timeseries.append_volumes(date, bands_by_huc, names, cache_dir,
                                  dataset=dataset)

        _progress(5, 5, 'Rendering figures...')
        huc2_df = bands_by_huc.get('17')
        huc4_by_name = {names[h]: b for h, b in bands_by_huc.items()
                        if len(h) == 4}
        written = plot_hypsometric(
            {'Columbia River Basin': huc2_df, **huc4_by_name}, date, output_dir)
        png_by_stem = {p.stem: p for p in written}

        huc2_fig = make_huc2_figure(huc2_df, date, dataset_label=ds['label']) \
            if huc2_df is not None else go.Figure()
        huc4_fig = make_huc4_figure(huc4_by_name, date, dataset_label=ds['label'])
        huc2_vol_fig = make_huc2_volume_figure(huc2_df, date, dataset_label=ds['label']) \
            if huc2_df is not None else go.Figure()
        huc4_vol_fig = make_huc4_volume_figure(huc4_by_name, date,
                                               dataset_label=ds['label'])

        return {
            'huc2_fig': huc2_fig,
            'huc4_fig': huc4_fig,
            'huc2_vol_fig': huc2_vol_fig,
            'huc4_vol_fig': huc4_vol_fig,
            'huc6_bands': {h: b.to_dict('records')
                           for h, b in bands_by_huc.items() if len(h) == 6},
            'names': names,
            'huc2_png': str(png_by_stem.get(f'snow_hypsometric_huc2_{date_key}', '')),
            'huc4_png': str(png_by_stem.get(f'snow_hypsometric_huc4_{date_key}', '')),
            'error': None,
        }
```

The exception path's empty result dict gains `'huc6_bands': {}, 'names': {}`.

- [ ] **Step 5: Run tests, full suite, commit**

Run: `venv/bin/python -m pytest tests/test_pipeline.py tests/test_charts.py -v` then `venv/bin/python -m pytest tests/ -q` (same sequencing tolerance; callbacks fixed in Task 5).

```bash
sudo -u geoskimoto git add pipeline.py charts.py tests/test_pipeline.py tests/test_charts.py tests/
sudo -u geoskimoto git commit -m "feat: pipeline bands all 35 basins and exposes HUC6 payload; charts gain group_label"
```

---

### Task 5: drill-down UI (`layout.py` + `callbacks.py`), SWANN radio hidden

**Files:**
- Modify: `layout.py`, `callbacks.py`
- Test: extend `tests/test_layout.py`, `tests/test_callbacks.py`

**Interfaces:**
- Consumes: `load_all_basins()`, `climatology.display_name`, Task 4's `result['huc6_bands']`/`result['names']`, Task 2 loaders, `charts.*(group_label=...)`.
- Produces:
  - Layout ids: `huc4-drill` (dcc.Dropdown, default `'1706'`, options = 12 HUC4s labeled `{huc} — {name}`), `huc6-graph` + `huc6-volume-graph` (Snowpack tab), `huc6-timeseries-graph` (Trends tab). `dataset-select` keeps id/value but renders SNODAS-only and hidden (`style={'display': 'none'}`), SWANN option in a comment block.
  - `historical-basin` options: values are huc codes, labels `{huc} — {name}` (huc2 label plain `Columbia River Basin`), ordered `'17'`, then HUC4s, then HUC6s.
  - `callbacks.build_historical_view(df, wy, huc, dataset='snodas')` — filters by huc, titles via `climatology.display_name`.
  - New callbacks: `update_snowpack_drilldown(store_data, huc4)` → huc6 chart pair from the result-store payload; `update_trends_drilldown(tab_value, huc4, dataset)` → huc6 trends chart from `load_timeseries` filtered `df['huc'].str.startswith(huc4) & (df['huc'].str.len() == 6)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_layout.py`:

```python
def _find(component, cid):
    if getattr(component, "id", None) == cid:
        return component
    children = getattr(component, "children", None)
    if children is None:
        return None
    if not isinstance(children, (list, tuple)):
        children = [children]
    for child in children:
        if hasattr(child, "to_plotly_json"):
            found = _find(child, cid)
            if found is not None:
                return found
    return None


def test_drilldown_selector_and_huc6_graphs_present():
    from layout import get_layout
    layout = get_layout()
    drill = _find(layout, "huc4-drill")
    assert drill is not None and drill.value == "1706"
    assert len(drill.options) == 12
    assert any("Lower Snake" in o["label"] for o in drill.options)
    for cid in ("huc6-graph", "huc6-volume-graph", "huc6-timeseries-graph"):
        assert _find(layout, cid) is not None, cid


def test_dataset_radio_snodas_only_and_hidden():
    from layout import get_layout
    radio = _find(get_layout(), "dataset-select")
    assert radio is not None and radio.value == "snodas"
    assert [o["value"] for o in radio.options] == ["snodas"]
    assert radio.style.get("display") == "none"
```

Append to `tests/test_callbacks.py`:

```python
def test_build_historical_view_by_huc_code(tmp_path):
    import pandas as pd
    from datetime import datetime
    import callbacks, climatology
    from timeseries import append_volumes

    band = pd.DataFrame({
        "elev_band_m": [1000], "mean_swe_mm": [100.0],
        "area_km2": [50.0], "total_swe_volume_km3": [1.0],
    })
    for yr in (2004, 2005, 2006, 2007):
        for day in (10, 11, 12):
            append_volumes(datetime(yr, 1, day), {"170602": band},
                           {"170602": "Salmon"}, tmp_path)
    df = climatology.load_all_water_years(tmp_path)
    fig, caption = callbacks.build_historical_view(df, 2026, "170602")
    assert "Salmon" in fig.layout.title.text
    assert "Salmon" in caption or "170602" in caption


def test_trends_drilldown_filters_huc6_children():
    import pandas as pd
    import callbacks

    df = pd.DataFrame({
        "date": pd.to_datetime(["2026-01-01"] * 4),
        "huc": ["17", "1706", "170602", "170300"],
        "basin": ["Columbia River Basin", "Lower Snake", "Salmon", "Yakima"],
        "total_swe_volume_km3": [10.0, 3.0, 1.5, 0.7],
    })
    children = callbacks.huc6_children(df, "1706")
    assert set(children["huc"]) == {"170602"}
```

- [ ] **Step 2: Run to verify failure**

Run: `venv/bin/python -m pytest tests/test_layout.py tests/test_callbacks.py -v`
Expected: new tests FAIL.

- [ ] **Step 3: Implement `layout.py`**

1. `dataset-select`: options `[{'label': datasets.get('snodas')['label'], 'value': 'snodas'}]`, `value='snodas'`, `style={'display': 'none'}` (keep `inline=True` etc.), preceded by the comment:

```python
            # SWANN dormant (2026-07-22 HUC6 redesign): to re-enable, add back
            #   {'label': datasets.get('swann')['label'], 'value': 'swann'},
            # and remove display:none. All dataset= machinery remains wired.
```

2. Snowpack tab, after the existing two chart-pair rows, add the drill-down block:

```python
                            html.Div([
                                html.Label('HUC6 drill-down',
                                           style={'fontWeight': 'bold',
                                                  'fontSize': '0.85rem',
                                                  'marginRight': '0.5rem'}),
                                dcc.Dropdown(
                                    id='huc4-drill',
                                    options=_huc4_drill_options(),
                                    value='1706',
                                    clearable=False,
                                    style={'width': '340px', 'fontSize': '0.85rem'},
                                ),
                            ], style={'display': 'flex', 'alignItems': 'center',
                                      'margin': '0.4rem 0'}),
                            html.Div([
                                dcc.Graph(id='huc6-graph', style={'flex': '1', 'minWidth': '0'},
                                          responsive=True, config={'displayModeBar': False}),
                                dcc.Graph(id='huc6-volume-graph', style={'flex': '1', 'minWidth': '0'},
                                          responsive=True, config={'displayModeBar': False}),
                            ], className='chart-pair',
                               style={'display': 'flex', 'gap': '1rem', 'marginBottom': '1rem'}),
```

with the module-level helper:

```python
def _huc4_drill_options() -> list:
    from basin_loader import load_huc4
    g = load_huc4()
    return [{'label': f"{r.huc4} — {r.name}", 'value': r.huc4}
            for r in sorted(g.itertuples(), key=lambda r: r.huc4)]
```

3. Trends tab: add `dcc.Graph(id='huc6-timeseries-graph', className='timeseries-graph', style={'height': '45vh'}, responsive=True, config={'displayModeBar': False})` after the existing two graphs (the `huc4-drill` selector is shared — it lives in the Snowpack tab; Trends reads its value).

- [ ] **Step 4: Implement `callbacks.py`**

1. Add module helper:

```python
def huc6_children(df, huc4: str):
    """Rows for the HUC6 children of a HUC4 (huc startswith + length 6)."""
    return df[(df['huc'].str.startswith(huc4)) & (df['huc'].str.len() == 6)]
```

2. `build_historical_view(df, wy, huc, dataset='snodas')`: parameter renamed; `huc = huc or '17'`; all `climatology.*` calls pass `huc`; label = `climatology.display_name(df, huc) or huc`; `basin_label` for the figure becomes `f'{label} ({huc})'` when `len(huc) > 2` else `label`; the `hist_wys` line filters `df['huc'] == huc`.
3. `populate_historical_basins`: build grouped options from the loaded frame:

```python
        hucs = (df[['huc', 'basin']].drop_duplicates()
                .sort_values('huc').itertuples())
        options = []
        for r in hucs:
            label = ('Columbia River Basin' if r.huc == '17'
                     else f'{r.huc} — {r.basin}')
            options.append({'label': label, 'value': r.huc})
        return options
```

`historical-basin` initial option/value in `layout.py` becomes `{'label': 'Columbia River Basin', 'value': '17'}` / `'17'`.
4. `update_historical_tab(tab_value, huc, dataset)` passes the code through to `build_historical_view`.
5. `update_trends_tab`: charts get pre-filtered frames — basin figure `df[df['huc'] == '17']`, huc4 figure `df[df['huc'].str.len() == 4]` (remember Task 4 removed the name-based filter inside `make_huc4_timeseries_figure`).
6. New callbacks (routing only):

```python
    @app.callback(
        Output('huc6-graph', 'figure'),
        Output('huc6-volume-graph', 'figure'),
        Input('result-store', 'data'),
        Input('huc4-drill', 'value'),
    )
    def update_snowpack_drilldown(store_data, huc4):
        if not store_data or 'huc6_bands' not in store_data or not huc4:
            return _annotated_empty_figure('Run an analysis to populate the drill-down.'), \
                   _annotated_empty_figure('')
        import pandas as pd
        names = store_data.get('names', {})
        children = {
            names.get(h, h): pd.DataFrame(rows)
            for h, rows in store_data['huc6_bands'].items()
            if h.startswith(huc4)
        }
        if not children:
            return _annotated_empty_figure('No HUC6 children for this subregion.'), \
                   _annotated_empty_figure('')
        date = datetime.strptime(store_data['date_str'], '%Y-%m-%d')
        parent = names.get(huc4, huc4)
        ds = datasets.get(store_data.get('dataset', 'snodas'))
        label = f'{parent} HUC6 Basins'
        return (charts.make_huc4_figure(children, date, dataset_label=ds['label'],
                                        group_label=label),
                charts.make_huc4_volume_figure(children, date, dataset_label=ds['label'],
                                               group_label=label))

    @app.callback(
        Output('huc6-timeseries-graph', 'figure'),
        Input('main-tabs', 'value'),
        Input('huc4-drill', 'value'),
        Input('dataset-select', 'value'),
    )
    def update_trends_drilldown(tab_value, huc4, dataset):
        if tab_value != 'trends' or not huc4:
            return _annotated_empty_figure('')
        wy = timeseries.water_year(date.today())
        df = timeseries.load_timeseries(wy, config.get_cache_dir(), dataset=dataset)
        children = huc6_children(df, huc4)
        if children.empty:
            return _annotated_empty_figure('No data yet for this subregion.')
        ds = datasets.get(dataset)
        parent = df.loc[df['huc'] == huc4, 'basin']
        parent_name = parent.iloc[0] if len(parent) else huc4
        return charts.make_huc4_timeseries_figure(
            children, wy, dataset_label=ds['label'],
            group_label=f'{parent_name} HUC6 Basins')
```

(`run_analysis` stores `'huc6_bands': result['huc6_bands'], 'names': result['names']` into `result-store` alongside the existing keys; add `from datetime import datetime` usage per the file's existing imports.)
7. Download callbacks: trend figures now receive pre-filtered frames as in item 5; zip/html contents otherwise unchanged.

- [ ] **Step 5: Run tests, full suite; runtime smoke; commit**

Run: `venv/bin/python -m pytest tests/test_layout.py tests/test_callbacks.py -v`, full suite, then the registration smoke:

```bash
venv/bin/python -c "
import dash, callbacks
from layout import get_layout
app = dash.Dash(__name__); app.layout = get_layout(); callbacks.register(app)
print('callbacks:', len(app.callback_map))"
```

Expected: no duplicate-output errors; callback count grows by 2.

```bash
sudo -u geoskimoto git add layout.py callbacks.py tests/test_layout.py tests/test_callbacks.py
sudo -u geoskimoto git commit -m "feat: HUC6 drill-down UI, code-valued historical dropdown, SWANN radio dormant"
```

---

### Task 6: scripts — `update_timeseries.py` + `populate_timeseries.py` on 35 basins

**Files:**
- Modify: `update_timeseries.py`, `populate_timeseries.py`
- Test: extend `tests/test_update_timeseries.py`, `tests/test_populate_timeseries.py`

**Interfaces:**
- Consumes: `load_all_basins()`, Task 2 signatures.
- Produces:
  - `update_timeseries.process_dataset(dataset, date_arg, cache_dir, basins, logger, discard_raster) -> bool` — `basins` is the `load_all_basins()` frame (replaces the `huc2, huc4` pair); `main()` loads it once.
  - `populate_timeseries` gains `--end YYYY-MM-DD` (default: yesterday) and `--stage-dir PATH` (default: None → live dir); `_process_date(target, cache_dir, dem_cache, basins, names, logger, discard_raster, ts_dir)` computes all 35 and appends with `ts_dir`; resume/skip keys on the new-schema `(date, huc)` completeness (all 35 hucs present) — old-schema band caches read as misses via Task 2's loader.
  - SWANN branches (`_run_swann_backfill`, `_swann_process_day`, swann side of `process_dataset`) compile against the new helpers (they take `basins`/`names` now) but are NEVER executed outside tests.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_update_timeseries.py`:

```python
def test_process_dataset_bands_all_35_basins(tmp_path, monkeypatch, quiet_logger):
    import pandas as pd
    from datetime import datetime
    import datasets, update_timeseries
    from basin_loader import load_all_basins

    basins = load_all_basins()
    monkeypatch.setitem(
        datasets.DATASETS["snodas"], "fetch_latest_swe",
        lambda ref, cache_dir: (tmp_path / "x.tif", datetime(2026, 7, 20)))
    monkeypatch.setattr(update_timeseries, "get_aligned_dem",
                        lambda s, dem_cache: tmp_path / "d.tif")
    calls = []

    def fake_compute(swe, dem, geom, min_band_area_km2=0.0):
        calls.append(1)
        return pd.DataFrame({"elev_band_m": [1000], "mean_swe_mm": [50.0],
                             "area_km2": [10.0], "total_swe_volume_km3": [0.001]})

    monkeypatch.setattr(update_timeseries, "compute_bands", fake_compute)
    ok = update_timeseries.process_dataset(
        "snodas", None, tmp_path, basins, quiet_logger, discard_raster=False)
    assert ok is True
    assert len(calls) == 35
    from timeseries import load_timeseries
    df = load_timeseries(2026, tmp_path)
    assert set(df["huc"].str.len().unique()) == {2, 4, 6}
    assert len(df) == 35
```

Append to `tests/test_populate_timeseries.py`:

```python
def test_stage_dir_and_end_args():
    import populate_timeseries
    p = populate_timeseries.build_parser()
    a = p.parse_args(["--stage-dir", "/tmp/x", "--end", "2026-07-01"])
    assert a.stage_dir == "/tmp/x" and a.end == "2026-07-01"
    assert p.parse_args([]).stage_dir is None


def test_process_date_writes_to_stage_dir(tmp_path, monkeypatch):
    import logging, pandas as pd
    from datetime import date
    import populate_timeseries
    from basin_loader import load_all_basins
    from timeseries import load_timeseries

    logger = logging.getLogger("t"); logger.addHandler(logging.NullHandler())
    basins = load_all_basins()
    names = dict(zip(basins["huc"], basins["name"]))
    monkeypatch.setattr(populate_timeseries, "fetch_swe",
                        lambda d, cache_dir: tmp_path / "x.tif")
    monkeypatch.setattr(populate_timeseries, "get_aligned_dem",
                        lambda s, dem_cache: tmp_path / "d.tif")
    monkeypatch.setattr(
        populate_timeseries, "compute_bands",
        lambda s, d, g, min_band_area_km2=0.0: pd.DataFrame(
            {"elev_band_m": [1000], "mean_swe_mm": [50.0],
             "area_km2": [10.0], "total_swe_volume_km3": [0.001]}))

    stage = tmp_path / "rebuild"
    ok = populate_timeseries._process_date(
        date(2026, 1, 15), tmp_path, tmp_path / "dem.tif", basins, names,
        logger, discard_raster=False, ts_dir=stage)
    assert ok
    assert len(load_timeseries(2026, tmp_path, ts_dir=stage)) == 35
    assert not (tmp_path / "timeseries" / "WY2026_volume.parquet").exists()
```

- [ ] **Step 2: Run to verify failure**

Run: `venv/bin/python -m pytest tests/test_update_timeseries.py tests/test_populate_timeseries.py -v`
Expected: new tests FAIL (signature mismatches).

- [ ] **Step 3: Implement `update_timeseries.py`**

`process_dataset(dataset, date_arg, cache_dir, basins, logger, discard_raster)`:
- `names = dict(zip(basins['huc'], basins['name']))` at the top.
- Cache-hit branch: `cached = load_band_cache(date_key, cache_dir, dataset)`; on hit `bands_by_huc, cached_names = cached; append_volumes(target, bands_by_huc, cached_names, cache_dir, dataset=dataset)`.
- Compute branch:

```python
        bands_by_huc = {
            row.huc: compute_bands(swe_tif, dem_tif, row.geometry,
                                   min_band_area_km2=_MIN_BAND_AREA_KM2)
            for row in basins.itertuples()
        }
        save_band_cache(bands_by_huc, names, date_key, cache_dir, dataset)
        append_volumes(target, bands_by_huc, names, cache_dir, dataset=dataset)
```

- `main()`: `basins = load_all_basins()` once (replacing `load_huc2()`/`load_huc4()`); pass to each `process_dataset` call; imports switch to `from basin_loader import load_all_basins`. Delete `_HUC2_KEY`.

- [ ] **Step 4: Implement `populate_timeseries.py`**

1. Parser: add

```python
    parser.add_argument('--end', metavar='YYYY-MM-DD', default=None,
                        help='Last date to process inclusive (default: yesterday).')
    parser.add_argument('--stage-dir', default=None,
                        help='Write volume parquets to this directory instead of '
                             'the live timeseries dir (staged rebuild).')
```

2. `_process_date(target, cache_dir, dem_cache, basins, names, logger, discard_raster=False, ts_dir=None)`: replace the `huc2`/`huc4` params and the two-step banding with the same 35-basin dict comprehension as Step 3; `save_band_cache(bands_by_huc, names, date_key, cache_dir)`; `append_volumes(dt, bands_by_huc, names, cache_dir, ts_dir=ts_dir)` (both call sites: cache-hit and computed). The skip check stays `load_band_cache(...) is not None` — Task 2's old-schema-is-miss rule makes stale caches recompute automatically.
3. `main()`: resolve `end = date.fromisoformat(args.end) if args.end else date.today() - timedelta(days=1)`; iterate `while current <= end`; `basins = load_all_basins()`; `names = dict(...)`; `ts_dir = Path(args.stage_dir) if args.stage_dir else None` threaded to `_process_date`. SNODAS loop only — `--dataset swann` unchanged in dispatch.
4. SWANN branches compile: `_swann_process_day(swe_tif, dem_tif, dt, basins, names, cache_dir)` uses the same 35-basin comprehension with `append_volumes(dt, bands_by_huc, names, cache_dir, dataset='swann')`; `_run_swann_backfill` signature swaps `huc2, huc4` → `basins, names`; `_swann_dates_done`'s completeness count becomes `n >= len(basins)` via a `n_basins` computed from `len(basins)`. Existing swann tests updated to the new seeding/signatures in this commit (list each in the report). No swann execution.

- [ ] **Step 5: Run tests, full suite, commit**

Run: `venv/bin/python -m pytest tests/test_update_timeseries.py tests/test_populate_timeseries.py -v`, then full suite — from this task on the suite must be FULLY green (all sequencing debts settled). Anything red → STOP.

```bash
sudo -u geoskimoto git add update_timeseries.py populate_timeseries.py tests/test_update_timeseries.py tests/test_populate_timeseries.py
sudo -u geoskimoto git commit -m "feat: scripts band all 35 basins; populate gains --end/--stage-dir for staged rebuild"
```

---

### Task 7: ops — staged WY2026 rebuild, swap, cron flip, cleanup, historical launch

**Files:** none created (infrastructure); crontab edited.

- [ ] **Step 1: Staged WY2026 recompute from cached rasters (~minutes, no network for cached dates)**

```bash
sudo -u geoskimoto venv/bin/python populate_timeseries.py \
    --start 2025-10-01 --stage-dir data/cache/timeseries/rebuild \
    >> logs/rebuild_wy2026.log 2>&1
```

Note: old band caches for these dates read as misses (schema rule), so every date recomputes bands for 35 basins from the cached tifs. Verify:

```bash
venv/bin/python - <<'EOF'
from pathlib import Path
import pandas as pd
df = pd.read_parquet('data/cache/timeseries/rebuild/WY2026_volume.parquet')
per_date = df.groupby('date')['huc'].nunique()
print('dates:', len(per_date), '| min hucs/date:', per_date.min())
print('salmon rows:', (df.huc == '170602').sum())
assert per_date.min() == 35 and (df.huc == '170602').sum() > 200
print('STAGE OK')
EOF
```

- [ ] **Step 2: Swap (atomic from the app's perspective: single mv + restart)**

```bash
sudo -u geoskimoto mkdir -p data/cache/timeseries_old
sudo -u geoskimoto bash -c 'mv data/cache/timeseries/WY*.parquet data/cache/timeseries_old/ && mv data/cache/timeseries/rebuild/WY2026_volume.parquet data/cache/timeseries/ && rmdir data/cache/timeseries/rebuild'
venv/bin/python -m pytest tests/ -q          # suite green against live layout
sudo systemctl restart snow-elevation-plot && sleep 4 && systemctl is-active snow-elevation-plot
```

(`timeseries_old/` is kept until Step 6; the swann subdir is untouched. NOTE the swap means WY2004–2025 SNODAS files are absent from the live dir until the backfill regenerates them — the Historical tab's minimum-years guard shows its friendly message in the interim, per spec.)

- [ ] **Step 3: Cron flip to SNODAS-only**

```bash
sudo -u geoskimoto bash -c "crontab -l | sed 's|update_timeseries.py --discard-raster|update_timeseries.py --dataset snodas --discard-raster|' | crontab -"
sudo -u geoskimoto crontab -l | tail -1
```

Expected: the 11:00 UTC line now carries `--dataset snodas`.

- [ ] **Step 4: Verify live app end-to-end**

```bash
venv/bin/python - <<'EOF'
from pathlib import Path
from datetime import datetime
import climatology, timeseries, callbacks, config
df = climatology.load_all_water_years(config.get_cache_dir())
wy = timeseries.water_year(datetime.now())
fig, cap = callbacks.build_historical_view(df, wy, '170602')
print('title:', fig.layout.title.text.split('<br>')[0], '| caption:', cap[:60])
EOF
```

Expected: renders (or the friendly not-enough-history message — only WY2026 exists at this point). Then run one daily-job cycle to prove the cron path writes new schema: `sudo -u geoskimoto venv/bin/python update_timeseries.py --dataset snodas` → exit 0, log shows 35 basins.

- [ ] **Step 5: Commit + push the swap**

```bash
sudo -u geoskimoto git add -A data/cache/timeseries/
sudo -u geoskimoto git commit -m "chore: swap in huc-keyed WY2026 volumes (35 basins); WY2004-2025 rebuild in progress"
sudo -u geoskimoto git push origin master
sudo chown -R geoskimoto:geoskimoto /home/geoskimoto/projects/snow_elevation_plot
```

(`git add -A data/cache/timeseries/` records both the old files' deletion and the new WY2026. The old parquets stay recoverable via git history; `timeseries_old/` is belt-and-suspenders until Step 6.)

- [ ] **Step 6: Launch the historical backfill (multi-day nohup) + schedule cleanup**

```bash
sudo -u geoskimoto nohup venv/bin/python populate_timeseries.py \
    --start 2003-10-01 --end 2025-09-30 --discard-raster \
    > logs/populate_huc6_rebuild.log 2>&1 &
tail -3 logs/populate_timeseries.log   # confirm it's fetching + banding 35 basins
```

Writes go straight to the live dir (no `--stage-dir`): each `(date, huc)` append is idempotent and the Historical tab picks up completed years progressively, per spec. Monitor via `tail -f logs/populate_timeseries.log`; NSIDC throughput dictates duration (est. 2–5 days). **After** the run completes and a spot-check shows ≥ 21 water years × 35 hucs: delete `data/cache/timeseries_old/` and the stale band caches (`find data/cache/bands -maxdepth 1 -name '*_250m.parquet' -delete` — only files directly in `bands/`, sparing `bands/swann/`), run the full suite, commit + push the historical parquets (`git add -f data/cache/timeseries/WY20*.parquet`), and `chown -R geoskimoto:geoskimoto` the tree. These completion steps belong to whoever attends the run's end — record them in the session ledger as pending if the run outlives the session.

---

## Self-review notes

- Spec coverage: basemaps/loader (T1), schema + old-cache invalidation (T2), climatology (T3), pipeline+charts (T4), UI incl. dormant SWANN radio (T5), scripts + staging/resume (T6), staged recompute/swap/cron/cleanup/Posit push (T7). All spec sections mapped.
- Sequencing debts are explicit: Tasks 2–5 may leave later-task modules failing on changed signatures; Task 6 Step 5 is the hard gate where the suite must be fully green.
- Type consistency: `bands_by_huc: dict[str, DataFrame]` + `names: dict[str, str]` flow through timeseries/pipeline/scripts identically; `load_band_cache` returns a tuple everywhere; `huc` params replace `basin` params in climatology/callbacks consistently; `group_label` naming matches between charts and both drill-down callbacks.
- The `--start` sentinel footgun noted in the SWANN final review is incidentally resolved by `--end`/explicit-args handling only if touched — it is NOT in scope here; snodas default start stays `2025-10-01` and Task 7 passes explicit `--start` everywhere.
