# Dash Web App — Snow Elevation Plot
**Date:** 2026-06-12
**Status:** Approved

## Overview

A single-user Dash web app that runs the existing snow elevation pipeline interactively and displays hypsometric curves in-browser. Eliminates the need to SCP output files to view results. Deployed as a systemd service proxied through nginx at `snow-elevation-analysis.streamflows.org`.

---

## 1. Architecture

```
snow_elevation_plot/
├── app.py              # Dash app factory, Flask login routes, long callback setup
├── auth.py             # Password check, session helpers
├── layout.py           # App layout (login page + main dashboard)
├── callbacks.py        # Long callback (pipeline run) + chart update callbacks
├── config.py           # Env-based config (PASSWORD_HASH, SECRET_KEY, etc.)
├── wsgi.py             # Gunicorn entrypoint: from app import server
├── main.py             # Existing CLI (unchanged)
└── [existing modules]  # basin_loader, snodas_fetcher, dem_processor, elevation_bands, plotter
```

**Request flow:**
1. Browser → nginx (SSL termination) → gunicorn on `127.0.0.1:8050`
2. Unauthenticated request → Flask redirects to `/login`
3. POST `/login` with correct password → sets `session['authed'] = True`, redirects to `/`
4. Authenticated Dash app loads; user picks a date and clicks "Run"
5. Long callback fires in background (diskcache job queue), progress bar updates via polling
6. On completion, Plotly figures render inline; PNG download button appears

**Key boundaries:**
- Flask handles `/login` and `/logout` as server routes
- Dash handles `/` and all component interaction
- `diskcache` provides both the long-callback job backend and band result caching
- Existing pipeline modules called directly from the long callback — no subprocess

---

## 2. Auth

**Single-user model** — one password protects the entire app.

**Config (`.env`):**
```
DASH_PASSWORD_HASH=<bcrypt hash>
SECRET_KEY=<random 32-byte hex>
SESSION_LIFETIME_HOURS=8
```

Password hash generated at deploy time:
```bash
python -c "import bcrypt; print(bcrypt.hashpw(b'yourpassword', bcrypt.gensalt()).decode())"
```

**Login flow:**
- `GET /login` → plain HTML form (no Dash, no JS framework)
- `POST /login` → bcrypt compare; success sets `session['authed'] = True` + `session.permanent = True`; failure re-renders form with "Invalid password"
- All Dash routes protected by `before_request` hook: unauthenticated → 302 to `/login`
- `GET /logout` → clears session, redirects to `/login`

**Session cookie:** `httponly=True`, `samesite='Lax'`, `secure=True`

**Rate limiting:** 5 failed attempts / 15 min via `Flask-Limiter` (in-memory)

---

## 3. Dashboard Layout

**Controls (top bar or sidebar):**
- Date picker (defaults to today)
- "Run Analysis" button (disabled while job is running)
- Progress bar (hidden until job starts; shows step text e.g. "Fetching SNODAS data...")
- Inline error message area (shown on failure)
- "Logout" link

**Output area:**
- Two Plotly figures (side by side, stacked on narrow screens):
  - Left: Columbia River Basin (HUC2) — SWE (mm) X-axis, Elevation (m) Y-axis
  - Right: HUC4 subbasins — same axes, one line per subbasin, colorblind-safe palette, legend
- Placeholder text ("Select a date and click Run") shown until first successful run
- If selected date has cached results, figures render immediately on page load

**Download:**
- "Download PNGs" button appears after a successful run
- `dcc.Download` delivers a zip containing `snow_hypsometric_huc2_YYYYMMDD.png` and `snow_hypsometric_huc4_YYYYMMDD.png`
- PNGs written to `output/` by existing `plotter.py` (unchanged)

**Error states:**
- SNODAS unavailable for date → inline error below button
- Network/download failure → inline error with exception message

---

## 4. Long Callback & Pipeline Integration

Single long callback triggered by "Run Analysis" button.

**Progress steps (5 total):**
1. Fetching SNODAS data
2. Loading basin boundaries
3. Building/loading aligned DEM
4. Computing elevation bands
5. Rendering figures

**Caching:**
- SNODAS `.tif` files: `data/cache/` (existing, unchanged)
- DEM: `data/cache/dem/` (existing, unchanged)
- Band results: parquet keyed by `{date}_{band_interval}` in `data/cache/bands/`
- Re-run for same date returns from cache at each step; progress still steps through for consistent UX

**Concurrency:**
- "Run" button disabled while job is in progress
- 2 gunicorn workers: one serves UI, one runs long callback

---

## 5. Deployment

**systemd service** (`/etc/systemd/system/snow-elevation-plot.service`):
```ini
[Unit]
Description=Snow Elevation Plot Dash App
After=network.target

[Service]
User=geoskimoto
WorkingDirectory=/home/geoskimoto/projects/snow_elevation_plot
ExecStart=/home/geoskimoto/projects/snow_elevation_plot/venv/bin/gunicorn \
    --workers 2 --bind 127.0.0.1:8050 wsgi:server
EnvironmentFile=/home/geoskimoto/projects/snow_elevation_plot/.env
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

**nginx:** CloudPanel vhost at `snow-elevation-analysis.streamflows.org` with `location /` proxy to `127.0.0.1:8050`. SSL via Let's Encrypt.

**One-time deploy steps:**
1. `pip install` new dependencies into existing venv
2. Generate `SECRET_KEY` and `DASH_PASSWORD_HASH`, write to `.env`
3. Create CloudPanel site → add nginx proxy block
4. `sudo clpctl lets-encrypt:install:certificate --domainName=snow-elevation-analysis.streamflows.org`
5. `sudo systemctl enable --now snow-elevation-plot`

---

## New Dependencies

- `dash>=2.14`
- `dash[diskcache]` (pulls in `diskcache`, `multiprocess`, `psutil`)
- `flask-limiter`
- `bcrypt`
- `gunicorn`

---

## Testing

- Unit: `auth.py` password check, session helpers, config loading
- Integration: login flow (correct/incorrect password, rate limit, session expiry)
- Callback: long callback progress steps, cache hit/miss behavior, download zip generation
- No browser automation required — Dash provides `dash.testing` for callback integration tests
