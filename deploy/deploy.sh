#!/usr/bin/env bash
# Redeploy script - runs ON the Lightsail server, as the `ubuntu` user.
# Pulls latest main, only reinstalls deps/collects static when those
# specific files actually changed (keeps routine deploys fast), restarts
# PM2, and verifies the app actually comes back up. Every step is logged
# with a timestamp to both stdout (captured by SSM/GitHub Actions) and a
# persistent log file on disk.
#
# Safe to run manually too: ssh onto the box and run
#   /home/ubuntu/Natsukashi_Main/deploy/deploy.sh
set -euo pipefail

PROJECT_DIR="/home/ubuntu/Natsukashi_Main"
LOG_FILE="$PROJECT_DIR/deploy/deploy.log"
VENV_PY="$PROJECT_DIR/.venv/bin/python"
VENV_PIP="$PROJECT_DIR/.venv/bin/pip"

log() {
    echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] $*" | tee -a "$LOG_FILE"
}

fail() {
    log "DEPLOY FAILED: $*"
    exit 1
}

trap 'fail "unexpected error at line $LINENO"' ERR

cd "$PROJECT_DIR"

log "===== Deploy started ====="

BEFORE_COMMIT=$(git rev-parse HEAD)
log "Current commit: $BEFORE_COMMIT"

log "Fetching latest changes from origin/main..."
git fetch origin main >> "$LOG_FILE" 2>&1
git merge --ff-only origin/main >> "$LOG_FILE" 2>&1 \
    || fail "git merge --ff-only failed - local commits or a conflict on the server? Check 'git status' manually."

AFTER_COMMIT=$(git rev-parse HEAD)

if [ "$BEFORE_COMMIT" = "$AFTER_COMMIT" ]; then
    log "Already up to date at $AFTER_COMMIT - nothing to deploy."
    log "===== Deploy finished (no-op) ====="
    exit 0
fi

log "Updated: $BEFORE_COMMIT -> $AFTER_COMMIT"

CHANGED_FILES=$(git diff --name-only "$BEFORE_COMMIT" "$AFTER_COMMIT")
log "Changed files:"
echo "$CHANGED_FILES" | sed 's/^/  /' | tee -a "$LOG_FILE"

# --- Only reinstall dependencies if requirements.txt actually changed ---
if echo "$CHANGED_FILES" | grep -q '^requirements\.txt$'; then
    log "requirements.txt changed - installing dependencies..."
    "$VENV_PIP" install -r requirements.txt >> "$LOG_FILE" 2>&1 \
        || fail "pip install failed"
else
    log "requirements.txt unchanged - skipping pip install."
fi

# --- Migrations: fast/no-op when nothing's pending, always safe to run ---
log "Running migrations..."
"$VENV_PY" manage.py migrate --noinput >> "$LOG_FILE" 2>&1 \
    || fail "migrate failed - check $LOG_FILE for the traceback"

# --- Only re-collect static files if static/templates actually changed ---
if echo "$CHANGED_FILES" | grep -qE '^product/static/|\.html$'; then
    log "Static/template files changed - running collectstatic..."
    "$VENV_PY" manage.py collectstatic --noinput >> "$LOG_FILE" 2>&1 \
        || fail "collectstatic failed"
else
    log "No static/template changes - skipping collectstatic."
fi

# --- Restart app, picking up any .env changes (--update-env) too ---
log "Restarting natsukashi via PM2..."
pm2 restart natsukashi --update-env >> "$LOG_FILE" 2>&1 \
    || fail "pm2 restart failed"

sleep 3

RESTART_COUNT=$(pm2 jlist | "$VENV_PY" -c "
import json, sys
data = json.load(sys.stdin)
for p in data:
    if p['name'] == 'natsukashi':
        print(p['pm2_env']['restart_time'])
        sys.exit(0)
print('unknown')
")
PM2_STATUS=$(pm2 jlist | "$VENV_PY" -c "
import json, sys
data = json.load(sys.stdin)
for p in data:
    if p['name'] == 'natsukashi':
        print(p['pm2_env']['status'])
        sys.exit(0)
print('unknown')
")
log "PM2 status after restart: status=$PM2_STATUS restarts=$RESTART_COUNT"

if [ "$PM2_STATUS" != "online" ]; then
    log "----- Last 30 lines of natsukashi error log -----"
    tail -30 /home/ubuntu/.pm2/logs/natsukashi-error.log | tee -a "$LOG_FILE"
    fail "app is not online after restart (status=$PM2_STATUS)"
fi

log "Checking HTTP response from the app..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 http://localhost/ || echo "000")
log "Local HTTP check: $HTTP_CODE"

if [ "$HTTP_CODE" != "200" ] && [ "$HTTP_CODE" != "301" ] && [ "$HTTP_CODE" != "302" ]; then
    log "----- Last 30 lines of natsukashi error log -----"
    tail -30 /home/ubuntu/.pm2/logs/natsukashi-error.log | tee -a "$LOG_FILE"
    fail "unexpected HTTP status $HTTP_CODE after deploy"
fi

log "===== Deploy finished successfully (commit $AFTER_COMMIT) ====="
