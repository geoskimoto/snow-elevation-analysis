# snow_elevation_plot — Project Notes

## File ownership

All files and directories in this project must be owned by
`geoskimoto:geoskimoto`. Agents and cron jobs sometimes run as root — after
any root-run operation that creates or modifies files here (including inside
`.git/`), restore ownership with
`sudo chown -R geoskimoto:geoskimoto /home/geoskimoto/projects/snow_elevation_plot`.
Root-owned files break geoskimoto's git operations, venv installs, and cron
jobs.

Dash app that plots SNODAS snow-water-equivalent by elevation band for
Columbia Basin HUC2/HUC4 basins. Data layer in `snodas_fetcher.py`,
`pipeline.py`, `timeseries.py`; charts in `charts.py`; Dash callbacks in
`callbacks.py`. The app has three tabs: **Snowpack** (per-date hypsometric
curves), **Trends** (current-WY volume timeseries), and **Historical**
(cross-year climatology envelope, see below).

## Historical / climatology tab

- `climatology.py` aggregates *all* committed `WY*_volume.parquet` snapshots
  into a day-of-water-year percentile envelope (min–max / 10–90 / 25–75 /
  median) with the current WY overlaid; `charts.make_climatology_figure`
  renders it and `callbacks.build_historical_view` wires it to the tab.
- **Read-only at serve time.** The tab only reads committed volume parquets —
  it never fetches SNODAS or writes cache — so it behaves identically on the
  scheduled server and on Posit Connect (which cannot run jobs). Data
  freshness on Posit = last commit/deploy.
- **Backfill (server-only, one-time):**
  `python populate_timeseries.py --start 2003-10-01 --discard-raster`. The
  `--discard-raster` flag deletes each CONUS SWE GeoTIFF after its bands are
  computed, keeping the full-record run from parking ~65 GB of intermediate
  rasters; the committed volume parquets (~1 MB total) are what the tab needs.
  `update_timeseries.py` accepts the same flag for the daily job.

## Testing

- Run the full suite before every commit: `venv/bin/python -m pytest tests/`
- **Tests must be updated in the same commit as the behavior change they
  cover.** This repo has been burned by stale tests twice: the imperial-units
  chart rework (`c9470d2`) and the 6-plot zip download (`c833363`) both
  shipped without updating `tests/test_charts.py` / `tests/test_callbacks.py`,
  leaving 12 tests red for months and masking whether new failures were real.
  A red suite that "always fails anyway" is worse than no suite.

## SNODAS download transport

- The committed default is `https` (noaadata.apps.nsidc.org mirror) — see
  `SNODAS_TRANSPORT_DEFAULT` in `config.py`. A machine's local `.env` can
  override with `SNODAS_TRANSPORT=ftp` (sidads.colorado.edu); some hosts
  block outbound port 21, so https is the safe default. Both transports
  produce byte-identical rasters.
- Non-sensitive settings live as committed defaults in `config.py`;
  `.env` (gitignored) holds secrets and per-machine overrides only.
  Never commit `.env` — it contains the streamflows SSO `JWT_SECRET`.
- The Dash app gets env vars from the systemd unit's `EnvironmentFile=`;
  the cron scripts (`update_timeseries.py`, `populate_timeseries.py`) load
  `.env` themselves via python-dotenv.
