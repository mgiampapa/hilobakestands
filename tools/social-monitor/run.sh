#!/usr/bin/env bash
# Daily wrapper for the homelab (media box): pull the latest stand list from the
# web server, then run the monitor. Cron calls THIS, not monitor.py directly.
#
#   crontab -e  ->  17 7 * * *  /home/matt/social-monitor/run.sh >> /home/matt/social-monitor/run.log 2>&1
#
set -euo pipefail
cd "$(dirname "$0")"

# Load config (ORACLE_SSH, paths, SMTP creds, ...).
set -a; [ -f .env ] && . ./.env; set +a

# 1. Pull the freshly-exported stand list from the web server.
#    -p preserves timestamps; the export is atomic on the far side so we never
#    grab a half-written file.
scp -p "${ORACLE_SSH}:${ORACLE_EXPORT_PATH}" "${STANDS_JSON}"

# 2. Run the monitor (sends email only if something changed).
#    Prefer the local venv's python so cron picks up curl_cffi without needing
#    the venv activated; fall back to system python3 if there's no venv.
PY=python3
[ -x .venv/bin/python ] && PY=.venv/bin/python
exec "$PY" monitor.py --stands "${STANDS_JSON}" --state "${STATE_DB}"
