#!/usr/bin/env bash
#
# deploy.sh — deploy snow-elevation-analysis to the self-operated server
# (systemd + gunicorn + nginx, user `geoskimoto`).
#
# This targets ONLY the server you control and can schedule jobs on. The Posit
# Connect deployment is git-backed / push-button published from the platform
# and does not use this script — see NOTES at the bottom.
#
# What it does, in order:
#   1. Fast-forward the checkout to origin/<branch>.
#   2. Sync the venv against requirements.txt.
#   3. Run the test suite as a release gate (abort on failure).
#   4. Restart the systemd service and health-check the login endpoint.
#
# It does NOT run the SNODAS backfill — that is a one-time job (see
# `populate_timeseries.py --start 2003-10-01 --discard-raster`) and the daily
# refresh is handled by cron/`update_timeseries.py`, not by a deploy.
#
# Usage:
#   ./deploy.sh                 # deploy current branch
#   SKIP_TESTS=1 ./deploy.sh    # skip the test gate (not recommended)
#
# Overridable via environment:
#   SERVICE   systemd unit name        (default: snow-elevation-plot)
#   HEALTH_URL  URL to curl post-restart (default: http://127.0.0.1:8052/login)
#   BRANCH    git branch to deploy     (default: current branch)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

SERVICE="${SERVICE:-snow-elevation-plot}"
# 8052, NOT 8050 — 8050 is dashboard.streamflows.org's gunicorn, which also
# answers /login with a 302 and silently satisfies a mispointed health check.
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8052/login}"
BRANCH="${BRANCH:-$(git rev-parse --abbrev-ref HEAD)}"
PY="$SCRIPT_DIR/venv/bin/python"

log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }

# --- 1. Update the checkout ------------------------------------------------
log "Updating checkout to origin/$BRANCH"
git fetch --prune origin
git checkout "$BRANCH"
git merge --ff-only "origin/$BRANCH"

# --- 2. Sync the virtualenv ------------------------------------------------
if [[ ! -x "$PY" ]]; then
    log "Creating virtualenv (venv/)"
    python3 -m venv "$SCRIPT_DIR/venv"
fi
log "Installing/updating dependencies"
"$PY" -m pip install --quiet --upgrade pip
"$PY" -m pip install --quiet -r requirements.txt

# --- 3. Test gate ----------------------------------------------------------
if [[ "${SKIP_TESTS:-0}" == "1" ]]; then
    log "SKIP_TESTS=1 — skipping test suite (not recommended)"
else
    log "Running test suite (release gate)"
    "$PY" -m pytest tests/ -q
fi

# --- 4. Restart and health-check ------------------------------------------
log "Restarting systemd service: $SERVICE"
sudo systemctl restart "$SERVICE"

# gunicorn needs a moment to bind before the health check.
for i in $(seq 1 10); do
    code="$(curl -s -o /dev/null -w '%{http_code}' "$HEALTH_URL" || true)"
    if [[ "$code" == "200" || "$code" == "302" ]]; then
        log "Health check OK ($code) — deploy complete."
        sudo systemctl --no-pager --lines=0 status "$SERVICE" || true
        exit 0
    fi
    sleep 2
done

log "Health check FAILED (last status: ${code:-none}) — dumping recent logs"
sudo systemctl --no-pager --lines=20 status "$SERVICE" || true
exit 1

# ---------------------------------------------------------------------------
# NOTES — Posit Connect
# ---------------------------------------------------------------------------
# Posit Connect serves the app read-only and cannot run jobs, so it has no
# deploy.sh. It is published from `manifest.json` (git-backed publishing or
# `rsconnect deploy`). After changing dependencies or adding source files,
# regenerate the manifest so the bundle stays in sync:
#
#     rsconnect write-manifest dash . --overwrite
#
# The Historical/Trends tabs read the committed `data/cache/timeseries/`
# parquets; whichever refresh cadence you use, a redeploy is what makes new
# data visible on Posit.
