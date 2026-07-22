# HUC6 Basin Granularity — Design Spec

**Date:** 2026-07-22
**Status:** Approved design, pending implementation plan

## Goal

Replace the app's basin structure (HUC2 + custom-split HUC4s) with three
standard WBD levels — the HUC2 region, its 10 standard HUC4 subregions, and
its 22 HUC6 basins (33 polygons total) — and recompute all SNODAS volume
statistics for the new set over the full record (WY2004–present).

SWANN is **dormant** for the duration of this work: its UI toggle option is
removed (code preserved for later re-enable), the daily cron runs
`--dataset snodas` only, and no SWANN recompute happens until separately
requested. The old-schema SWANN parquets remain on disk unread.

Motivation: the Clearwater (170603) and Salmon (170602) basins — and other
tributaries the user cares about — only exist as separate units at HUC6;
the current HUC4 view lumps them into 1706 Lower Snake.

## Basin model & basemaps

- New committed basemaps, fetched once from the USGS WBD ArcGIS REST
  service (`hydro.nationalmap.gov/arcgis/rest/services/wbd/MapServer`),
  the same source lineage as the current files:
  - `data/basemaps/huc4_pnw.geojson` — the **standard** 10 HUC4 subregions
    of region 17 (1701–1712), REPLACING the current custom-split file
    (which carries pseudo-codes 1701a/b, 1702a/b).
  - `data/basemaps/huc6_pnw.geojson` — the 22 HUC6 basins of region 17
    (verified live 2026-07-22: 170101 Kootenai … 171200 Oregon Closed
    Basins).
  - `data/basemaps/huc2_pnw.geojson` — unchanged.
- `basin_loader.py` gains `load_huc6()` and `load_all_basins()`; the
  latter returns all 33 basins as rows of `(huc, name, geometry)` with
  `huc` the WBD code string (`'17'`, `'1706'`, `'170602'`).
- **Accepted losses from dropping the custom splits:**
  - Kootenai / Pend Oreille-Spokane: superseded — HUC6 provides Kootenai
    (170101), Pend Oreille (170102), and Spokane (170103) individually.
  - Upper Columbia (BC) / (Washington): **disappears with no equivalent** —
    WBD 170200 spans the border as a single basin and no standard HUC
    level splits it. (Masked SNODAS does carry data in southern BC — the
    mask follows the NOHRSC domain, not the border — so 170200 totals
    include the Canadian portion up to the mask edge, same as before.)

## Schema

- Volume parquets: `[date, huc, basin, total_swe_volume_km3]`.
  - `huc` (string WBD code) is the **unique key** for all joins, filters,
    and idempotency checks. This resolves cross-level name collisions
    (Yakima, Upper Columbia, Lower Columbia, Willamette, Puget Sound, and
    Oregon Closed Basins have identical names at HUC4 and HUC6).
  - `basin` is the WBD display name only.
  - Level is derived from `len(huc)` (2/4/6) — no separate column.
- Band caches gain the same `huc` column.
- **No backward-compat shim.** All SNODAS parquets are regenerated in one
  campaign; loaders read the new schema only. Old-schema SWANN parquets
  are never read while SWANN is dormant; the future SWANN recompute
  adopts the new schema.
- Idempotency (`append_volumes`, backfill resume) keys on `(date, huc)`.

## UI

- **Snowpack and Trends tabs** keep the current layout (HUC2 chart +
  all-HUC4 chart, now the standard 10) and gain a **HUC4 drill-down
  dropdown**: selecting a HUC4 renders a third chart (pair) showing its
  HUC6 children — 1–3 lines each. Default selection: **1706 Lower Snake**
  (children: Lower Snake, Salmon, Clearwater).
- **Historical tab** basin dropdown lists all 33 basins grouped by level,
  labels carrying the code (e.g. `170602 — Salmon`) so collisions are
  visually unambiguous; option `value` is the `huc` code.
- **SWANN option removed** from the `dataset-select` radio (single
  commented block in `layout.py`; everything downstream keeps its
  `dataset=` machinery untouched). With one option left, the radio is
  hidden via `style={'display': 'none'}`; the component and its callbacks
  stay wired so re-enable is a one-line change.
- Chart labeling rules from the SWANN spec (dataset label on every title)
  are unchanged.

## Recompute & ops

Staged so the live app never reads half-recomputed data:

1. **Stage:** regenerated parquets build in
   `data/cache/timeseries/rebuild/` (new schema, new basins).
2. **WY2026 first, from cache:** the 276 on-disk rasters recompute in
   minutes; after verification the rebuild dir contents swap into
   `data/cache/timeseries/` (old WY files replaced in one commit),
   the app restarts, and the new basin structure is live same-day.
3. **History in the background:** WY2004–WY2025 re-downloads from NSIDC
   (~65 GB total, `--discard-raster`, nohup, resumable keyed on
   `(date, huc)`), appending completed water years into the live
   timeseries dir as each finishes. Historical envelopes deepen as the
   backfill progresses; the tab's existing minimum-years guard handles
   the interim gracefully.
4. **Cron:** the 11:00 UTC job flips to `--dataset snodas` (SWANN dormant)
   in the same change that lands the new schema, so no old-schema rows
   are ever written post-swap.
5. **Cleanup:** the 8,311 old-basin band-cache parquets are deleted only
   after the WY2026 recompute is verified; the full-record recompute
   regenerates band caches per date as a side effect of banding.
6. **Posit Connect:** unchanged model — commit + push regenerated parquets
   (WY2026 swap immediately; historical years batched when the backfill
   completes).

- `min_band_area_km2` stays **100** at all levels for consistency;
  explicitly noted as tunable if small-basin (e.g. 170502, ~10.6k km²)
  hypsometry proves too coarse.
- `compute_bands`, `dem_processor`, and `snodas_fetcher` are unchanged.

## Testing

Updated in the same commit as each behavior change (repo rule):

- Basemap integrity: 33 features across the three files, unique `huc`
  codes, valid geometries, HUC6 codes all prefixed by an existing HUC4.
- Loader/schema: `load_all_basins()` shape; volume parquet round-trip with
  `huc` keys; idempotency on `(date, huc)`; name-collision safety (two
  basins named Yakima coexist).
- Callbacks: drill-down selector routing (HUC4 → children charts);
  Historical dropdown values are codes; grouped labels.
- Charts: HUC6 children figures labeled with parent and dataset.
- Backfill: staging-dir writes; resume keyed on new schema.

## Out of scope

- Any SWANN computation, UI, or re-enable (follow-up project; will adopt
  the new schema when it happens).
- Sub-splitting 170200 Upper Columbia at the border (no standard boundary
  exists; would require a custom split, which this redesign removes).
- HUC8 or finer levels.
- Changing elevation-band logic, DEM handling, or SNODAS transport.
