#!/usr/bin/env bash
# Bootstrap HiloBakeStands on a fresh Ubuntu 22.04/24.04 box (Oracle A1 ARM is fine).
# Run as a sudo-capable user from the uploaded project directory:
#   cd ~/HiloBakeStands.com && sudo bash deploy/bootstrap.sh
#
# Seed/import only run on FIRST boot (no db.sqlite3 yet) or with --with-data.
# For routine code deploys use deploy/deploy.sh instead — it never touches data.
set -euo pipefail

APP_DIR=/opt/hilobakestands
SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"

WITH_DATA=0
for arg in "$@"; do
  [ "$arg" = "--with-data" ] && WITH_DATA=1
done

echo "==> Packages"
apt-get update -qq
apt-get install -y -qq python3-venv python3-pip sqlite3 curl unattended-upgrades

echo "==> Automatic updates (security pocket is Ubuntu default; add -updates + auto-reboot)"
# Idempotent: rewrites the same override file every run; APT merges it on top
# of the stock 50unattended-upgrades (scalars override, list entries append).
cat > /etc/apt/apt.conf.d/52hilobake-auto <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
Unattended-Upgrade::Allowed-Origins { "${distro_id}:${distro_codename}-updates"; };
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "14:30";
Unattended-Upgrade::Remove-Unused-Dependencies "true";
EOF
# 14:30 UTC = 04:30 HST, after the 03:15 HST nightly backup. Reboots only
# happen when a package requires one; all services are systemd-enabled.
systemctl enable --now unattended-upgrades

echo "==> App user + layout"
id -u hilobake &>/dev/null || useradd --system --create-home --shell /usr/sbin/nologin hilobake
mkdir -p "$APP_DIR" "$APP_DIR/data" "$APP_DIR/media" /var/backups/hilobakestands
chown hilobake:hilobake /var/backups/hilobakestands  # backup service runs as hilobake
rsync -a --delete --exclude '.venv' --exclude 'db.sqlite3' --exclude '__pycache__' \
  "$SRC_DIR/" "$APP_DIR/app/"

echo "==> Python env"
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install -q --upgrade pip
"$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/app/requirements.txt" gunicorn whitenoise openpyxl

echo "==> Env file"
if [ ! -f "$APP_DIR/.env" ]; then
  cp "$APP_DIR/app/.env.example" "$APP_DIR/.env"
  SECRET=$("$APP_DIR/venv/bin/python" -c "import secrets; print(secrets.token_urlsafe(50))")
  sed -i "s|^SECRET_KEY=.*|SECRET_KEY=$SECRET|" "$APP_DIR/.env"
  echo "    wrote $APP_DIR/.env with generated SECRET_KEY"
fi

echo "==> Django setup"
cd "$APP_DIR/app"
set -a; source "$APP_DIR/.env"; set +a
FIRST_BOOT=0
[ -f "$APP_DIR/data/db.sqlite3" ] || FIRST_BOOT=1
"$APP_DIR/venv/bin/python" manage.py migrate --noinput
if [ "$FIRST_BOOT" = 1 ] || [ "$WITH_DATA" = 1 ]; then
  echo "    seeding + importing listings (first boot or --with-data)"
  "$APP_DIR/venv/bin/python" manage.py seed
  "$APP_DIR/venv/bin/python" manage.py import_listings listings.xlsx || true
else
  echo "    existing DB found — skipping seed/import (use --with-data to force)"
fi
"$APP_DIR/venv/bin/python" manage.py collectstatic --noinput
chown -R hilobake:hilobake "$APP_DIR"

echo "==> systemd"
cp "$APP_DIR/app/deploy/hilobakestands.service" /etc/systemd/system/
cp "$APP_DIR/app/deploy/hilobakestands-backup.service" /etc/systemd/system/
cp "$APP_DIR/app/deploy/hilobakestands-backup.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now hilobakestands hilobakestands-backup.timer

echo "==> cloudflared"
if ! command -v cloudflared &>/dev/null; then
  ARCH=$(dpkg --print-architecture)
  curl -fsSL -o /tmp/cloudflared.deb \
    "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${ARCH}.deb"
  dpkg -i /tmp/cloudflared.deb
fi

echo
echo "Done. App is on http://127.0.0.1:8000 (gunicorn)."
echo "Next: authenticate the tunnel (interactive, needs Cloudflare login):"
echo "  cloudflared tunnel login"
echo "  cloudflared tunnel create hilobakestands"
echo "  cloudflared tunnel route dns hilobakestands hilobakestands.com"
echo "  cloudflared tunnel route dns hilobakestands www.hilobakestands.com"
echo "  cp \$HOME/.cloudflared/*.json /etc/cloudflared/  # credentials file"
echo "  cp $APP_DIR/app/deploy/cloudflared-config.yml /etc/cloudflared/config.yml"
echo "  (edit config.yml: set tunnel ID + credentials filename)"
echo "  cloudflared service install && systemctl enable --now cloudflared"
