# Deployment Guide

This app runs in **two** environments with very different capabilities:

| | Your server | Posit Connect |
|---|---|---|
| Serves the Dash app | ✅ | ✅ |
| Can run scheduled jobs (cron/systemd) | ✅ | ❌ |
| Runs the SNODAS backfill / daily update | ✅ (data factory) | ❌ (read-only viewer) |
| Deploy mechanism | `./deploy.sh` (systemd + gunicorn) | git-backed publish via `manifest.json` |

The design keeps the two in sync through **git**: the server produces the small
committed volume parquets, and Posit serves whatever is committed. Because the
Trends and Historical tabs only *read* committed parquets (never fetch SNODAS or
write cache at request time), they behave identically in both places. Posit data
freshness = last commit/deploy.

---

## 1. Your server (systemd + gunicorn + nginx)

**Facts about the deployment:**

- User: `geoskimoto`
- Checkout: `/home/geoskimoto/projects/snow_elevation_plot`
- Virtualenv: `venv/` in the checkout
- systemd unit: `snow-elevation-plot` (gunicorn `wsgi:server` on `127.0.0.1:8050`,
  `--timeout 300`, `EnvironmentFile=.env`)
- nginx reverse-proxy → `https://snow-elevation-analysis.streamflows.org`
  (`proxy_read_timeout 310s`, must exceed gunicorn's 300s)

### Routine deploy

From the checkout on the server:

```bash
./deploy.sh
```

`deploy.sh` performs, in order:

1. **Fast-forward** the checkout to `origin/<current-branch>` (`git fetch` +
   `merge --ff-only`).
2. **Sync the venv** against `requirements.txt`.
3. **Run the test suite** as a release gate — aborts the deploy on any failure.
4. **Restart** the systemd service and **health-check** the login endpoint
   (accepts HTTP 200 or 302), dumping recent logs if it fails.

Overridable via environment:

```bash
SERVICE=snow-elevation-plot \
HEALTH_URL=http://127.0.0.1:8050/login \
BRANCH=master \
./deploy.sh

SKIP_TESTS=1 ./deploy.sh   # skip the gate (not recommended)
```

### First-time server setup (one-time, needs root)

The systemd unit and nginx proxy block are documented in full in
`docs/superpowers/plans/2026-06-12-dash-app.md` (Task 10). In brief:

```bash
# /etc/systemd/system/snow-elevation-plot.service — gunicorn wsgi:server,
# 2 workers, --timeout 300, EnvironmentFile=<checkout>/.env
sudo systemctl daemon-reload
sudo systemctl enable --now snow-elevation-plot

# nginx: proxy_pass http://127.0.0.1:8050 with WebSocket upgrade headers
sudo nginx -t && sudo systemctl reload nginx
```

---

## 2. Posit Connect (read-only viewer)

Posit cannot run jobs, so there is **no deploy script** — it publishes from
`manifest.json` (git-backed publishing or `rsconnect deploy`). Entrypoint is
`app:server`, appmode `python-dash`; dependencies install from
`requirements.txt`.

**After changing dependencies or adding/removing source files, regenerate the
manifest** so the deployed bundle stays in sync:

```bash
rsconnect write-manifest dash . --overwrite
git add manifest.json && git commit -m "chore: refresh Posit manifest"
```

> ⚠️ **Known gap:** `manifest.json`'s `files` map currently lists source + tests
> + basemaps but **not** the committed `data/cache/` artifacts (the `WY*`
> volume parquets and the aligned DEM). If your Posit publish is strictly
> manifest-driven, that data may not reach Posit and the Trends/Historical tabs
> would render empty there. Confirm the committed parquets actually arrive on
> Posit; if not, regenerate the manifest (above) or add those paths explicitly.

---

## 3. Data: backfill and daily refresh (server only)

The tabs need `data/cache/timeseries/WY*_volume.parquet`. These are tiny (~1 MB
for the full multi-decade record) and are **committed** so deploys ship with
data. `.gitignore` whitelists `data/cache/timeseries/`.

### One-time full-record backfill

Populate every water year back to the start of SNODAS (Oct 2003):

```bash
# Run detached; it's idempotent and resumable via --start. Logs to logs/.
nohup python populate_timeseries.py --start 2003-10-01 --discard-raster \
  > logs/backfill.out 2>&1 &
```

- `--discard-raster` deletes each CONUS SWE GeoTIFF once its bands are computed.
  **Use it for the full-record run** — otherwise the job parks ~65 GB of
  intermediate rasters. The volume parquets the tabs need are unaffected; peak
  disk stays a few hundred MB (band caches + transient tar/dat).
- ~8,000 daily downloads; expect some transient FTP/HTTPS failures. Re-run with
  `--start <first-failed-date>` to mop them up (skips already-cached dates).

### Daily refresh

`update_timeseries.py` processes the latest available SNODAS day and appends to
the current water year's parquet. Wire it to cron (or a systemd timer):

```cron
# ~06:30 daily; NSIDC publishes with a lag, so the script self-heals by
# scanning back a few days for the latest available product.
30 6 * * *  cd /home/geoskimoto/projects/snow_elevation_plot && \
            venv/bin/python update_timeseries.py --discard-raster \
            >> logs/update_timeseries.log 2>&1
```

`update_timeseries.py` loads `.env` itself via python-dotenv, so it does not
depend on the systemd `EnvironmentFile`.

### Publishing refreshed data

The server's checkout has the freshest parquets. To make new data visible on
Posit (and to back it up in git), commit and push the snapshot:

```bash
git add -f data/cache/timeseries/ && git commit -m "data: refresh WY timeseries" && git push
```

Then redeploy Posit (git-backed publish picks it up). On the server itself the
running app reads the parquets directly, so no restart is needed for data — only
for code.

---

## 4. Environment (`.env`)

`.env` is **gitignored** and holds secrets + per-machine overrides only.
Non-sensitive defaults live as committed defaults in `config.py`. **Never commit
`.env`** — it contains the streamflows SSO `JWT_SECRET`.

Variables the app / scripts read:

| Variable | Purpose | Notes |
|---|---|---|
| `DASH_PASSWORD_HASH` | bcrypt hash for password login | required |
| `SECRET_KEY` | Flask session signing | required |
| `JWT_SECRET` | streamflows SSO | required on the server; secret |
| `SESSION_LIFETIME_HOURS` | session length | default 8 |
| `CACHE_DIR` | cache root | default `data/cache` |
| `OUTPUT_DIR` | PNG output dir | default `output` |
| `SNODAS_TRANSPORT` | `https` or `ftp` | committed default `https`; some hosts block outbound port 21, so keep `https` unless FTP is required. Both transports produce byte-identical rasters. |

The Dash app gets these from the systemd unit's `EnvironmentFile=`; the cron
scripts load `.env` themselves via python-dotenv.

---

## 5. Git remote / SSH (push access)

The remote uses **SSH**: `git@github.com:geoskimoto/snow-elevation-analysis.git`.
Pushing requires an **account-level** SSH key (not a repo deploy key). On the
dev laptop that's `~/.ssh/id_ed25519`, registered at
`github.com/settings/keys`.

If a push ever fails with **"denied to deploy key"**, SSH authenticated with a
read-only *deploy key* instead of the account key (reads still work because the
repo is public). Ensure the account key is loaded/offered first
(`ssh-add ~/.ssh/id_ed25519`).

---

## 6. Testing

Run the full suite before every deploy (the release gate in `deploy.sh` does
this automatically):

```bash
venv/bin/python -m pytest tests/
```

Per `CLAUDE.md`: **tests must be updated in the same commit as the behavior
change they cover.** A red suite that "always fails anyway" masks real
regressions.

> Note: `tests/test_sso_integration.py` imports the deployment-only
> `streamflows_auth` module, which is absent from the repo. It collects on the
> server but not on a bare dev checkout — use
> `pytest tests/ --ignore=tests/test_sso_integration.py` locally if needed.
