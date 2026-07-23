#!/usr/bin/env bash
# finish_swann_backfill.sh — cron watchdog for the SWANN 35-basin recompute.
#
# Same pattern as finish_huc6_backfill.sh (slot 13min past 02/08/14/20 UTC,
# chosen 2026-07-22 after full crontab review; still conflict-free):
#   - running                          -> exit quietly
#   - crashed / incomplete             -> restart (max 3), alert in log
#   - DONE with 0 failures             -> verify coverage -> commit + push
#                                         swann parquets -> self-remove
#   - any check fails                  -> loud ALERT, no commit, cron stays
# NOTE: does NOT flip the UI toggle or cron dataset — that is a gated code
# change done in-session (see docs/superpowers/plans/2026-07-23-swann-reenable-huc6.md).

set -u
cd /home/geoskimoto/projects/snow_elevation_plot || exit 1

LOG=logs/finish_swann_backfill.log
RESTARTS=logs/finish_swann_backfill.restarts
LOCK=/tmp/finish_swann_backfill.lock
BACKFILL_LOG=logs/populate_timeseries.log

log() { echo "$(date -u '+%Y-%m-%d %H:%M:%S')  $*" >> "$LOG"; }

exec 9>"$LOCK"
flock -n 9 || { log "SKIP another instance holds the lock"; exit 0; }

# --- 1. Still running? -------------------------------------------------------
if pgrep -f "populate_timeseries.py --dataset swann" > /dev/null; then
    last=$(tail -1 "$BACKFILL_LOG" 2>/dev/null | cut -c1-80)
    log "RUNNING  ${last}"
    exit 0
fi

# --- 2. Finished? SWANN mode logs: "=== populate_timeseries (swann) DONE — N failures ==="
done_line=$(grep "populate_timeseries (swann) DONE" "$BACKFILL_LOG" 2>/dev/null | tail -1)
failed_count=$(echo "$done_line" | sed -n 's/.*DONE — \([0-9]*\) failures.*/\1/p')

if [ -z "$done_line" ]; then
    n=$(cat "$RESTARTS" 2>/dev/null || echo 0)
    if [ "$n" -ge 3 ]; then
        log "ALERT swann backfill not running, not finished, restart budget (3) exhausted — human needed"
        exit 1
    fi
    echo $((n + 1)) > "$RESTARTS"
    log "RESTART #$((n + 1)) swann backfill not running and no DONE marker — relaunching (resume is idempotent)"
    nohup venv/bin/python populate_timeseries.py --dataset swann --start 1981-10-01 \
        --discard-raster >> logs/populate_swann_huc6.log 2>&1 &
    exit 0
fi

if [ -z "$failed_count" ] || [ "$failed_count" -gt 0 ]; then
    log "ALERT swann backfill finished with ${failed_count:-unknown} failed dates — human review needed, no commit"
    exit 1
fi

log "DONE detected with 0 failures — verifying"

# --- 3. Coverage check -------------------------------------------------------
venv/bin/python - >> "$LOG" 2>&1 <<'EOF'
from pathlib import Path
import sys
from climatology import load_all_water_years
df = load_all_water_years(Path('data/cache'), dataset='swann')
wys, hucs = df.wy.nunique(), df.huc.nunique()
print(f'swann coverage: {wys} water years, {hucs} hucs, {len(df)} rows')
if wys < 44 or hucs != 35:
    print('COVERAGE CHECK FAILED')
    sys.exit(1)
EOF
if [ $? -ne 0 ]; then
    log "ALERT swann coverage check failed — no commit"
    exit 1
fi

# --- 4. Full test suite ------------------------------------------------------
if ! venv/bin/python -m pytest tests/ -q >> "$LOG" 2>&1; then
    log "ALERT test suite red — no commit"
    exit 1
fi

# --- 5. Commit + push --------------------------------------------------------
git add -f data/cache/timeseries/swann/
if git commit -q -m "chore: commit SWANN WY1982-2026 volume parquets at 35-basin granularity

Automated by scripts/finish_swann_backfill.sh after the recompute completed
with 0 failures, coverage verified (>=44 WYs x 35 hucs), suite green."; then
    if git push origin master >> "$LOG" 2>&1; then
        log "committed and pushed swann parquets"
    else
        log "ALERT commit ok but push FAILED — push manually"
        exit 1
    fi
else
    log "ALERT git commit failed — verify manually"
    exit 1
fi

# --- 6. Self-remove ----------------------------------------------------------
crontab -l | grep -v finish_swann_backfill.sh | crontab -
log "SUCCESS — swann parquets committed+pushed; watchdog removed. UI flip still pending (in-session)."
