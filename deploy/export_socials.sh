#!/usr/bin/env bash
# Cron wrapper (runs on Oracle) for the social-activity monitor's export step.
#
# Why a wrapper: cron has no systemd, so the prod environment (SECRET_KEY, etc.)
# that the gunicorn service gets from EnvironmentFile=/opt/hilobakestands/.env is
# NOT present. We source that file ourselves, then run the management command
# with the prod venv. Output lands at /opt/hilobakestands/app/exports/.
#
# Install (as the app user, hilobake):
#   sudo -u hilobake crontab -e
#   5 7 * * *  /opt/hilobakestands/app/deploy/export_socials.sh >> /opt/hilobakestands/export.log 2>&1
set -euo pipefail
APP=/opt/hilobakestands
set -a; . "$APP/.env"; set +a
cd "$APP/app"
exec "$APP/venv/bin/python" manage.py export_socials
