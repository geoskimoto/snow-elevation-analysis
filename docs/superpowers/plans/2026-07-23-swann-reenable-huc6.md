# SWANN Re-enable at HUC6 Granularity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recompute SWANN on the 35-basin huc-keyed schema, restore the dataset toggle with transboundary daggers, and resume daily dual-dataset updates.

**Architecture:** Data-first sequencing: purge old-schema SWANN parquets and run the 35-basin backfill (download-and-discard, ~100 MB peak) with a self-removing watchdog; meanwhile land the display-layer dagger machinery (`basin_loader.transboundary_hucs()` from the WBD `states` attribute + a `dagger()` helper applied at each display surface); flip the toggle + cron only after the record verifies.

**Tech Stack:** existing app stack; no new dependencies.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-23-swann-reenable-huc6-design.md`.
- Disk: download-and-discard only (`--discard-raster`); one WY netCDF (~95 MB) + one temp tif at a time; never accumulate rasters.
- Daggers/captions are display-layer only — parquets never store coverage flags or daggered names.
- venv/bin/python; TDD; full suite green before every commit; same-commit test updates. Commits as geoskimoto (`sudo -u geoskimoto git ...`); chown anything created as root.
- The toggle stays hidden until Task 3 (data verified) — no broken interim state.

---

### Task 1: purge old SWANN parquets, launch backfill + watchdog

- [ ] **Step 1:** Confirm old files and delete them (git history preserves; they are incompatible with huc-keyed loaders):
```bash
ls data/cache/timeseries/swann/                       # expect WY1982..WY2026 old-schema
sudo -u geoskimoto git rm -q data/cache/timeseries/swann/WY*_volume.parquet
sudo -u geoskimoto git commit -m "chore: drop old-schema (15-basin, name-keyed) SWANN parquets ahead of 35-basin recompute"
```
- [ ] **Step 2:** Launch the backfill (nohup, ~3–4 h):
```bash
sudo -u geoskimoto nohup venv/bin/python populate_timeseries.py --dataset swann \
    --start 1981-10-01 --discard-raster > logs/populate_swann_huc6.log 2>&1 &
sleep 20 && tail -3 logs/populate_timeseries.log     # expect WY-file-mode OK lines
```
- [ ] **Step 3:** Install `scripts/finish_swann_backfill.sh` — copy `scripts/finish_huc6_backfill.sh` with these deltas, then add the cron line `13 2,8,14,20 * * * bash /home/geoskimoto/projects/snow_elevation_plot/scripts/finish_swann_backfill.sh` to geoskimoto's crontab:
  - pgrep pattern → `"populate_timeseries.py --dataset swann"`; restart command mirrors Step 2.
  - DONE marker grep → `"populate_timeseries (swann) DONE"`; failures parsed from the same line's `— N failures`.
  - Coverage check → `load_all_water_years(Path('data/cache'), dataset='swann')`, assert `wys >= 44 and hucs == 35`.
  - Commit path → `git add -f data/cache/timeseries/swann/` with message `chore: commit SWANN WY1982-2026 volume parquets at 35-basin granularity`.
  - Log/lock/restart-counter filenames s/huc6/swann/.
  Commit the script: `chore: add self-removing watchdog for the SWANN 35-basin backfill`.

### Task 2: transboundary daggers (runs while backfill grinds)

**Interfaces produced:** `basin_loader.transboundary_hucs() -> set[str]`; `basin_loader.dagger(name: str, huc: str, tb: set) -> str`.

- [ ] **Step 1: failing tests** — append to `tests/test_basin_loader.py`:
```python
def test_transboundary_hucs_from_states_attribute():
    from basin_loader import transboundary_hucs
    tb = transboundary_hucs()
    assert {"17", "1701", "1702", "1711", "170101", "170102", "170200", "171100"} == tb


def test_dagger_helper():
    from basin_loader import dagger
    assert dagger("Kootenai", "170101", {"170101"}) == "Kootenai †"
    assert dagger("Salmon", "170602", {"170101"}) == "Salmon"
```
Append to `tests/test_layout.py`:
```python
def test_drill_options_carry_daggers():
    from layout import _huc4_drill_options
    labels = {o["value"]: o["label"] for o in _huc4_drill_options()}
    assert labels["1701"].endswith("†")
    assert not labels["1706"].endswith("†")
```
Append to `tests/test_callbacks.py`:
```python
def test_historical_options_and_legend_names_daggered():
    import pandas as pd
    import callbacks
    from basin_loader import transboundary_hucs
    df = pd.DataFrame({
        "date": pd.to_datetime(["2026-01-01"] * 2),
        "huc": ["170101", "170602"],
        "basin": ["Kootenai", "Salmon"],
        "total_swe_volume_km3": [1.0, 2.0],
    })
    out = callbacks.display_frame(df, transboundary_hucs())
    assert set(out["basin"]) == {"Kootenai †", "Salmon"}
```
Run: `venv/bin/python -m pytest tests/test_basin_loader.py tests/test_layout.py tests/test_callbacks.py -q` → new tests FAIL.
- [ ] **Step 2: implement** —
  `basin_loader.py` additions:
```python
def transboundary_hucs() -> set[str]:
    """Huc codes whose WBD `states` attribute includes Canada ('CN').

    Data-driven from the committed geojsons; used only for display-layer
    daggers — never stored in parquets.
    """
    out = set()
    for gdf, code_col in ((load_huc2(), "huc2"), (load_huc4(), "huc4"),
                          (load_huc6(), "huc6")):
        mask = gdf["states"].fillna("").str.contains("CN")
        out.update(gdf.loc[mask, code_col].astype(str))
    return out


def dagger(name: str, huc: str, tb: set) -> str:
    """Append the transboundary dagger to a display name when flagged."""
    return f"{name} †" if huc in tb else name
```
  `callbacks.py`: add `from basin_loader import transboundary_hucs, dagger`, module-level `_TB = transboundary_hucs()`, and:
```python
def display_frame(df, tb):
    """Copy of a volume frame with transboundary display names daggered."""
    out = df.copy()
    out['basin'] = [dagger(n, h, tb) for n, h in zip(out['basin'], out['huc'])]
    return out
```
  Apply at each display surface (all in `callbacks.py` unless noted):
  - `populate_historical_basins`: label = `dagger(r.basin, r.huc, _TB)` before the code prefix.
  - `update_trends_tab`: wrap both pre-filtered frames in `display_frame(...)`.
  - `update_trends_drilldown`: `children = display_frame(huc6_children(df, huc4), _TB)`; names dict built from the RAW df (group label uses `dagger` on the parent name via `drill_group_label` unchanged — pass `dagger(parent, huc4, _TB)` by pre-daggering the names dict for that lookup).
  - `update_snowpack_drilldown`: children keys = `dagger(names.get(h, h), h, _TB)`.
  - `pipeline.run_pipeline`: `huc4_by_name = {dagger(names[h], h, tb): b ...}` with `tb = transboundary_hucs()` imported from basin_loader (computed once next to `basins = load_all_basins()`).
  - `datasets.py`: append the two footnote key sentences from the spec verbatim to the respective `footnote` strings.
- [ ] **Step 3:** Full suite (`venv/bin/python -m pytest tests/ -q`) green; registration smoke; commit `feat: transboundary daggers on basin names + coverage footnote keys`.

### Task 3 (GATED: backfill verified): re-enable toggle + cron

- [ ] **Step 1:** Gate check — watchdog SUCCESS line (or manual verify): 45 WYs × 35 hucs via `climatology.load_all_water_years(cache_dir, dataset='swann')`; parquets committed.
- [ ] **Step 2:** Flip tests first (RED): in `tests/test_layout.py`, `test_dataset_radio_snodas_only_and_hidden` becomes:
```python
def test_dataset_radio_two_options_visible():
    from layout import get_layout
    radio = _find(get_layout(), "dataset-select")
    assert [o["value"] for o in radio.options] == ["snodas", "swann"]
    assert radio.value == "snodas"
    assert radio.style.get("display") != "none"
```
- [ ] **Step 3:** `layout.py`: restore `{'label': datasets.get('swann')['label'], 'value': 'swann'}` in the options list and remove `'display': 'none'` (keep the comment, updated to say re-enabled 2026-07-23). Suite green; commit `feat: re-enable SWANN dataset toggle at 35-basin granularity`.
- [ ] **Step 4:** Cron: `sudo -u geoskimoto bash -c "crontab -l | sed 's|update_timeseries.py --dataset snodas --discard-raster|update_timeseries.py --dataset both --discard-raster|' | crontab -"`; verify with `crontab -l | tail -1`.

### Task 4: E2E verify + deploy

- [ ] **Step 1:** E2E under swann: `build_historical_view(df_swann, wy, '170602', dataset='swann')` renders a ~44-year envelope; `load_timeseries(wy, cache_dir, dataset='swann')` has 35 hucs; one manual `update_timeseries.py --dataset both` run exits 0 with both `[snodas]`/`[swann]` Done lines.
- [ ] **Step 2:** Restart service, health check, push, chown sweep. Final suite run. Done.

## Self-review notes

- Spec coverage: purge/backfill/watchdog (T1), daggers + footnotes (T2), toggle/cron flip gated (T3), E2E/deploy (T4). Disk constraint embedded in T1 commands (`--discard-raster`, no staging of rasters).
- Type consistency: `transboundary_hucs()` set[str] consumed by `dagger(name, huc, tb)`; `display_frame(df, tb)` returns a frame copy — parquets untouched.
