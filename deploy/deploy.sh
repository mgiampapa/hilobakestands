#!/usr/bin/env bash
# Fast, DATA-SAFE deploy: code + migrations + static only.
# NEVER runs seed or import_listings — production DB is the source of truth.
# Run as a sudo-capable user from the uploaded project directory:
#   cd ~/HiloBakeStands.com && sudo bash deploy/deploy.sh
set -euo pipefail

APP_DIR=/opt/hilobakestands
SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [ ! -f "$APP_DIR/.env" ]; then
  echo "ERROR: $APP_DIR/.env not found — this box isn't provisioned yet."
  echo "Run: sudo bash deploy/bootstrap.sh"
  exit 1
fi

echo "==> Sync code"
# 'media' excluded defensively: user uploads must never ride the mirror.
# '.env' excluded: prod config is systemd's EnvironmentFile at $APP_DIR/.env;
# a developer's local app/.env (e.g. DEBUG=1) must never travel to the box.
rsync -a --delete --exclude '.venv' --exclude 'db.sqlite3' \
  --exclude '__pycache__' --exclude 'media' --exclude '.env' \
  "$SRC_DIR/" "$APP_DIR/app/"

echo "==> Dependencies"
"$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/app/requirements.txt" gunicorn whitenoise openpyxl

echo "==> Migrate + static"
cd "$APP_DIR/app"
set -a; source "$APP_DIR/.env"; set +a
"$APP_DIR/venv/bin/python" manage.py migrate --noinput
"$APP_DIR/venv/bin/python" manage.py collectstatic --noinput
chown -R hilobake:hilobake "$APP_DIR"

echo "==> Restart"
systemctl restart hilobakestands
systemctl --no-pager --lines=0 status hilobakestands

echo "Done. Data untouched."
