---
name: run-app
description: Launch the Snow Elevation Analysis Dash app locally for dev/verification. Use when asked to run, start, serve, or screenshot the app on this machine. Works around app.py's deployment-only streamflows_auth import via a no-auth dev runner.
---

# Run the app locally

The production entrypoint (`wsgi:server` / `app.py`) imports
`streamflows_auth`, a **deployment-only** module that is absent from a bare
checkout, so `python app.py` and `gunicorn wsgi:server` fail to import here.
For local dev, use the bundled no-auth runner instead — it mirrors
`create_app()` (layout + callbacks + DiskcacheManager) but skips
`streamflows_auth.protect_app`.

> Auth model: on the server `streamflows_auth` is the real login/SSO layer; on
> Posit Connect there is no app auth. This runner is DEV ONLY — never serve it
> in production. See `deploy.md`.

## Launch

Prereq: the venv exists (`venv/`). If not: `python3 -m venv venv &&
venv/bin/python -m pip install -r requirements.txt`.

```bash
# from the repo root; runs on http://127.0.0.1:8050 (override with PORT=)
fuser -k 8050/tcp 2>/dev/null || true
venv/bin/python .claude/skills/run-app/dev_server.py > /tmp/dev_server.log 2>&1 &

# wait for readiness
for i in $(seq 1 20); do
  code=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8050/ || true)
  [ "$code" = 200 ] && break; sleep 1
done
echo "status: $code"; tail -5 /tmp/dev_server.log
```

`dev_server.py` is self-contained: it puts the repo root on `sys.path`,
`chdir`s there so `CACHE_DIR=data/cache` resolves, and sets dummy
`SECRET_KEY` / `DASH_PASSWORD_HASH` (required by `config.py`).

## Drive it (don't just launch)

Load `http://127.0.0.1:8050/` in a browser and exercise the tabs — a Dash app
does its real work in callbacks, so a bare 200 isn't enough:

- **Snowpack** — default tab; charts are empty until "Run Analysis" (which does
  a live SNODAS fetch — slow, needs network).
- **Trends** — reads the committed current-WY parquet; shows the volume
  timeseries (or a "no data yet" annotation if absent).
- **Historical** — the climatology tab. Confirm the basin dropdown populates
  (15 basins, Columbia River Basin first) and the envelope renders — or, with
  only WY2026 committed, the "not enough history … run the full-record
  backfill" annotation. Both are correct behavior.

Screenshot the Historical tab and **look at it** — a blank frame means the app
didn't actually render.

## Stop

```bash
fuser -k 8050/tcp
```
