#!/usr/bin/env bash
# finish_huc6_backfill.sh — cron watchdog for the WY2004-2025 HUC6 rebuild.
#
# Runs every 6h from geoskimoto's crontab (installed 2026-07-22; slot 13min
# past 02/08/14/20 UTC avoids the 11:00 daily job, the 14:00-15:00 synopsis
# window, and the hourly :30 cache warmer). Behavior:
#   - backfill still running          -> exit quietly
#   - backfill crashed / incomplete   -> restart it (max 3 restarts), alert in log
#   - backfill DONE with 0 failures   -> run the completion checklist:
#       verify coverage -> delete timeseries_old/ + stale band caches ->
#       full test suite -> commit + push parquets -> remove own crontab line
#   - any check fails                 -> loud log line, NO cleanup, cron stays
#
# Self-removing: on successful completion it strips its own line from the
# crontab. All state lives in logs/ (gitignored).

set -u
cd /home/geoskimoto/projects/snow_elevation_plot || exit 1

LOG=logs/finish_huc6_backfill.log
RESTARTS=logs/finish_huc6_backfill.restarts
LOCK=/tmp/finish_huc6_backfill.lock
BACKFILL_LOG=logs/populate_timeseries.log

log() { echo "$(date -u '+%Y-%m-%d %H:%M:%S')  $*" >> "$LOG"; }

exec 9>"$LOCK"
flock -n 9 || { log "SKIP another instance holds the lock"; exit 0; }

# --- 1. Still running? -------------------------------------------------------
if pgrep -f "populate_timeseries.py --start 2003-10-01" > /dev/null; then
    last=$(tail -1 "$BACKFILL_LOG" 2>/dev/null | cut -c1-80)
    log "RUNNING  ${last}"
    exit 0
fi

# --- 2. Finished successfully? ----------------------------------------------
# The run's final lines: "=== populate_timeseries DONE ===" then
# "Processed N dates; M failed". Require DONE with 0 failed.
done_line=$(grep -c "=== populate_timeseries DONE ===" "$BACKFILL_LOG" 2>/dev/null || echo 0)
fail_summary=$(grep "Processed .* dates; " "$BACKFILL_LOG" 2>/dev/null | tail -1)
failed_count=$(echo "$fail_summary" | sed -n 's/.*dates; \([0-9]*\) failed.*/\1/p')

if [ "$done_line" -eq 0 ] || [ -z "$fail_summary" ]; then
    # Not running, never finished -> crashed. Restart (bounded).
    n=$(cat "$RESTARTS" 2>/dev/null || echo 0)
    if [ "$n" -ge 3 ]; then
        log "ALERT backfill not running, not finished, and restart budget (3) exhausted — human needed"
        exit 1
    fi
    echo $((n + 1)) > "$RESTARTS"
    log "RESTART #$((n + 1)) backfill not running and no DONE marker — relaunching (resume is idempotent)"
    nohup venv/bin/python populate_timeseries.py --start 2003-10-01 --end 2025-09-30 \
        --discard-raster >> logs/populate_huc6_rebuild.log 2>&1 &
    exit 0
fi

if [ -z "$failed_count" ] || [ "$failed_count" -gt 0 ]; then
    log "ALERT backfill finished with ${failed_count:-unknown} failed dates — human review needed, no cleanup performed"
    exit 1
fi

log "DONE detected with 0 failures — running completion checklist"

# --- 3. Coverage check -------------------------------------------------------
venv/bin/python - >> "$LOG" 2>&1 <<'EOF'
from pathlib import Path
import sys
from climatology import load_all_water_years
df = load_all_water_years(Path('data/cache'))
wys, hucs = df.wy.nunique(), df.huc.nunique()
print(f'coverage: {wys} water years, {hucs} hucs, {len(df)} rows')
if wys < 22 or hucs != 35:
    print('COVERAGE CHECK FAILED')
    sys.exit(1)
EOF
if [ $? -ne 0 ]; then
    log "ALERT coverage check failed — no cleanup performed"
    exit 1
fi

# --- 4. Full test suite ------------------------------------------------------
if ! venv/bin/python -m pytest tests/ -q >> "$LOG" 2>&1; then
    log "ALERT test suite red after backfill — no cleanup performed"
    exit 1
fi

# --- 5. Cleanup (only after all checks) -------------------------------------
rm -rf data/cache/timeseries_old
find data/cache/bands -maxdepth 1 -name '*_250m.parquet' -delete
log "cleanup done: timeseries_old/ removed, stale old-schema band caches deleted"

# --- 6. Commit + push --------------------------------------------------------
git add -f data/cache/timeseries/WY20*_volume.parquet
if git commit -q -m "chore: commit HUC6-rebuilt SNODAS WY2004-2025 volume parquets (35 basins)

Automated by scripts/finish_huc6_backfill.sh after the multi-day rebuild
completed with 0 failures and the full suite passed."; then
    if git push origin master >> "$LOG" 2>&1; then
        log "committed and pushed historical parquets"
    else
        log "ALERT commit ok but push FAILED — push manually"
        exit 1
    fi
else
    log "ALERT git commit failed (nothing to commit?) — verify manually"
    exit 1
fi

# --- 7. Self-remove from crontab --------------------------------------------
crontab -l | grep -v finish_huc6_backfill.sh | crontab -
log "SUCCESS — completion checklist finished; watchdog removed from crontab"
