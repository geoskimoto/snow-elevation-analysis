# snow_elevation_plot — Project Notes

Dash app that plots SNODAS snow-water-equivalent by elevation band for
Columbia Basin HUC2/HUC4 basins. Data layer in `snodas_fetcher.py`,
`pipeline.py`, `timeseries.py`; charts in `charts.py`; Dash callbacks in
`callbacks.py`.

## Testing

- Run the full suite before every commit: `venv/bin/python -m pytest tests/`
- **Tests must be updated in the same commit as the behavior change they
  cover.** This repo has been burned by stale tests twice: the imperial-units
  chart rework (`c9470d2`) and the 6-plot zip download (`c833363`) both
  shipped without updating `tests/test_charts.py` / `tests/test_callbacks.py`,
  leaving 12 tests red for months and masking whether new failures were real.
  A red suite that "always fails anyway" is worse than no suite.

## SNODAS download transport

- `SNODAS_TRANSPORT` env var selects `ftp` (default, sidads.colorado.edu)
  or `https` (noaadata.apps.nsidc.org mirror). Use `https` on hosts that
  block outbound port 21. Both produce byte-identical rasters.
- The Dash app gets env vars from the systemd unit's `EnvironmentFile=`;
  the cron scripts (`update_timeseries.py`, `populate_timeseries.py`) load
  `.env` themselves via python-dotenv.
