# SWANN Re-enable at HUC6 Granularity — Design Spec

**Date:** 2026-07-23
**Status:** Approved design

## Goal

Bring SWANN back from dormancy with the same 35-basin granularity as SNODAS
(HUC2 + 12 HUC4 + 22 HUC6, huc-keyed schema), including a full-record
recompute (WY1982–present), the restored dataset toggle, resumed daily
updates, and honest handling of the US/Canada coverage asymmetry.

## Constraints

- **Disk**: the VPS has ~30 GB free and stays lean. The backfill uses the
  established download-and-discard pattern (`--discard-raster`): one ~95 MB
  SWANN water-year netCDF + one temp GeoTIFF on disk at a time, deleted per
  year; ~4 GB total transfer, ~100 MB peak footprint. Committed output is
  ~2–3 MB of parquets.
- Datasets remain compared-never-combined; daggers and captions are
  display-layer only — nothing coverage-related is stored in parquets.

## Sequence (data before UI — no broken interim state)

1. **Recompute**: delete the old name-keyed SWANN parquets
   (`data/cache/timeseries/swann/`, preserved in git history — they are
   incompatible with the huc-keyed loaders and would crash reads/appends),
   then `populate_timeseries.py --dataset swann --start 1981-10-01
   --discard-raster` under nohup (~3–4 h; bulk WY files 1982–2023, daily
   fallback 2024+; resumable; per-year crash guard and cleanup already in
   place from the first SWANN round).
2. **Verify**: 45 water years × 35 hucs; spot volumes in-family with the
   prior 15-basin record's totals; commit + push parquets.
3. **Re-enable commit**: toggle restored (swann option back, `display:none`
   removed — the dormancy comment marks the spot); crontab 11:00 UTC line
   → `--dataset both` (script default stays `snodas`); tests asserting the
   dormant radio flip back to two-option visible.

## Transboundary daggers

- `basin_loader.transboundary_hucs() -> set[str]`: hucs whose WBD `states`
  attribute contains `'CN'`, read from the committed geojsons (data-driven,
  no hardcoded list; catches '17', 1701, 1702, 1711, 170101, 170102,
  170200, 171100).
- A display helper daggers names (`'Kootenai †'`) in: Historical dropdown
  labels, both drill-down dropdown labels, and chart legend/trace names —
  under BOTH datasets (the flag is a property of the basin).
- Footnote key per dataset, appended to the registry footnotes:
  - SNODAS: "† transboundary basins include southern-BC coverage (the
    NOHRSC domain extends past the border)."
  - SWANN: "† transboundary basins are US-portion-only — totals exclude
    Canadian area and are not directly comparable to SNODAS there."

## Testing

- Unit: `transboundary_hucs()` contents (from real geojsons); dagger helper.
- Layout: dropdown labels carry daggers for flagged hucs; radio visible
  with both options, snodas default.
- Callbacks/charts: daggered names flow to legends; existing dataset
  routing untouched.
- Post-backfill E2E: SWANN Historical envelope renders (Salmon, 44 years);
  Trends + drill-downs populate under the toggle; registration smoke.
- Full suite green before each commit; same-commit test updates.

## Out of scope

- Any cross-dataset difference/bias computation.
- Changing SNODAS behavior, schemas, or the 35-basin structure.
- SWANN band-cache backfill (Snowpack computes SWANN bands on demand, as
  SNODAS does for uncached dates).
