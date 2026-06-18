#!/bin/bash
# MF Flow daily wrapper. Run by cron (TZ=Asia/Kolkata) OR manually.
#
# Cron-safe: explicitly cd's to the project, uses absolute venv path, and
# writes a date-stamped log so concurrent invocations don't clobber each
# other. The runner itself loads .env via lib/paths.py — see the global
# memory rule "cron runs with an EMPTY environment, so scripts MUST load
# their .env explicitly".
#
# Usage:
#   /opt/mf-flow/bin/run.sh              # full run, all MFs
#   /opt/mf-flow/bin/run.sh --only mf16  # forwarded args
#
# Cron line (NOT installed by default — see README):
#   TZ=Asia/Kolkata
#   0 20 * * * /opt/mf-flow/bin/run.sh
set -euo pipefail

PROJECT_DIR="/opt/mf-flow"
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

cd "$PROJECT_DIR"
DATE_TAG=$(date +%Y-%m-%d)
LOG_FILE="$LOG_DIR/cron-$DATE_TAG.log"

# Append start marker + arg echo (helps when a single day has multiple invocations)
{
  echo ""
  echo "==== $(date +%Y-%m-%dT%H:%M:%S%z)  run.sh args=[$*] ===="
} >> "$LOG_FILE"

exec "$PROJECT_DIR/.venv/bin/python" "$PROJECT_DIR/run_scraper.py" "$@" >> "$LOG_FILE" 2>&1
