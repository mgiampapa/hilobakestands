#!/usr/bin/env bash
# Cron wrapper (runs on Oracle) for the social-activity monitor's export step.
#
# Why a wrapper: cron has no systemd, so the prod environment (SECRET_KEY, etc.)
# that the gunicorn service gets from EnvironmentFile=/opt/hilobakestands/.env is
# NOT present. We source that file ourselves, then run the management command
# with the prod venv.
#
# Output goes to /opt/hilobakestands/exports/ — a SIBLING of app/, deliberately
# OUTSIDE the deploy's `rsync --delete "$SRC_DIR/" "$APP_DIR/app/"` target, so a
# redeploy can't wipe it (same reason .env and venv live at $APP, not under app).
#
# Install (as the app user, hilobake):
#   sudo -u hilobake crontab -e
#   5 7 * * *  /opt/hilobakestands/app/deploy/export_socials.sh >> /opt/hilobakestands/export.log 2>&1
set -euo pipefail
APP=/opt/hilobakestands
set -a; . "$APP/.env"; set +a
cd "$APP/app"
exec "$APP/venv/bin/python" manage.py export_socials \
  --out "$APP/exports/stands_socials.json"
