# SWANN Dataset Toggle — Design Spec

**Date:** 2026-07-20
**Status:** Approved design, pending implementation plan

## Goal

Add the University of Arizona SWANN dataset (UA SWE, NSIDC-0719; 4 km daily
SWE, October 1981 – present, updated near-real-time) as a second, fully
independent dataset alongside SNODAS. Every analysis the app performs on
SNODAS is performed analogously on SWANN. The two datasets are **compared,
never combined**: no mixed parquets, no cross-dataset math. A global toggle
selects which dataset feeds all three tabs.

Rationale: SWANN provides a 44-year record (vs. SNODAS's start in WY2004)
for a longer climatology baseline, stays current daily (so it can serve the
Trends tab, unlike a frozen reanalysis), and its full Columbia-Basin record
is only a few GB, so both backfill and daily updates run on the VPS.

Decisions that led here (recorded for posterity):

- UCLA WUS-SR was the original candidate; rejected because it is frozen at
  ~WY2021 (cannot serve Trends/Snowpack for current dates) and its backfill
  is a few hundred GB of tile downloads.
- A fully separate app instance was rejected: with full parity every file
  would be cloned and every future fix doubled. Separation is achieved at
  the data level (parallel directory trees) and UI level (explicit toggle).

## Architecture

One app, one global dataset selector in the header:

- Radio: **SNODAS (~1 km, WY2004–present)** / **SWANN (4 km, WY1982–present)**
- All three tab callbacks take the selector as an input and route to the
  corresponding fetcher and cache directories.
- SNODAS remains the default selection.

## Data layer

### New module: `swann_fetcher.py`

Mirrors `snodas_fetcher.py`'s public interface:
`fetch_swe(date, cache_dir) -> Path` returning a raster ready for
`compute_bands`. Two sources:

- **NSIDC-0719 stable archive** — used by the backfill. Requires NASA
  Earthdata credentials (in `.env`, never committed).
- **UA near-real-time daily feed** — used by the daily cron increment.
  The exact NRT endpoint and its publication lag (expected ~1–2 days) must
  be **verified against the live service during implementation**, not taken
  from memory. The per-dataset "latest available date" logic depends on it.

SWANN units/orientation/nodata conventions are validated at ingest (pipeline
entry-point validation), and the fetcher logs data-quality issues (missing
dates, gaps) rather than silently skipping.

### DEM

A second cached DEM aligned to SWANN's 4 km grid, produced by the existing
`get_aligned_dem` machinery with a dataset-specific cache path
(`dem/columbia_basin_swann_aligned.tif`). `compute_bands` is
resolution-agnostic and is not modified.

### Cache namespacing (no migration)

SNODAS paths do not move. SWANN gets a parallel subtree with identical
schemas:

```
data/cache/bands/swann/{YYYYMMDD}_4km.parquet
data/cache/timeseries/swann/WY{yyyy}_volume.parquet   # committed to repo
```

Volume parquet schema is identical to SNODAS's:
`date, basin, total_swe_volume_km3`. Same basins (HUC2 Columbia + HUC4s).

### Config

Non-sensitive SWANN URLs/settings are committed defaults in `config.py`
(same pattern as `SNODAS_TRANSPORT_DEFAULT`). Earthdata credentials live in
`.env` only and are needed only by the backfill.

## App / UI changes

- **Global selector** in the header layout; a single control feeding all
  tab callbacks (kept lean — routing only; data logic stays in the data
  layer).
- **Snowpack tab**: date-picker bounds are per-dataset (SWANN back to
  1981-10-01; SNODAS from its 2003 start). Under SWANN, a visible caveat
  notes that 4 km resolution makes hypsometric curves legitimately coarser.
- **Trends tab**: current-WY volume timeseries from the selected dataset's
  `timeseries/` subtree.
- **Historical tab**: percentile envelope **and** current-WY overlay both
  come from the selected dataset (SNODAS envelope = WY2004+; SWANN envelope
  = WY1982+). Comparison between datasets is done by flipping the toggle,
  not by overlaying envelopes.
- **Figure honesty**: every figure title/subtitle names the active dataset,
  its resolution, and its record period, so a screenshot cannot be
  misattributed. Axes keep units per existing conventions.
- **Missing-data state**: if SWANN is selected before its parquets exist
  (pre-backfill), tabs show a friendly "SWANN data not yet loaded" message
  instead of empty charts.

## Ops

- **Backfill (one-time, VPS)**: `populate_timeseries.py` grows a
  `--dataset swann` mode. 44 water years, resumable per-WY, `nohup`-run
  (>5 min rule). Per water year: download → compute band volumes → append
  to WY parquet → delete raw raster (`--discard-raster` pattern). Only
  volume parquets are needed up front; band caches build on demand as they
  do for SNODAS today.
- **Daily cron**: `update_timeseries.py` extended to process both datasets
  in one run. Before changing the job's workload, review existing crontabs
  for timing conflicts and document the outcome (per global cron rule).
- **Posit Connect**: gitignore carve-outs extended to
  `data/cache/timeseries/swann/`. Serve-time behavior unchanged — the
  Historical tab remains read-only over committed parquets; freshness on
  Posit remains last-commit/deploy.
- **File ownership**: any root-run step that touches the repo is followed by
  `chown -R geoskimoto:geoskimoto` per project CLAUDE.md.

## Testing

Updated in the same commit as the behavior they cover (repo rule):

- **Unit**: fetcher selection / dataset routing; path namespacing for bands,
  timeseries, and DEM caches; per-dataset date bounds.
- **Fetcher**: fixture-based SWANN fetcher test (no network); ingest
  validation (units, nodata, orientation).
- **Callbacks**: toggle routing per tab; "SWANN parquets absent" state.
- **Charts**: dataset/resolution/period labeling assertions for all figure
  factories.
- **Climatology**: envelope built from the SWANN subtree; day-of-WY
  alignment unchanged (water-year logic stays in its single source of
  truth).

## Out of scope

- Cross-dataset difference/bias views (validation-study features).
- Any change to SNODAS paths, schemas, or existing tab behavior under the
  SNODAS selection.
- UCLA WUS-SR ingestion (may be revisited later as a third, frozen-record
  baseline; the toggle design does not preclude it).
