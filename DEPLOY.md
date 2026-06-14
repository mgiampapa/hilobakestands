# Deploying HiloBakeStands.com

Target: Oracle Cloud free tier + Cloudflare Tunnel (no inbound ports open).
Steps 1–2 are console work we can do together in Chrome; 3–5 are paste-into-SSH.

## 1. Create the Oracle instance (console, one time)

Oracle Cloud → Compute → Instances → Create:

- Image: **Ubuntu 24.04**, Shape: **VM.Standard.A1.Flex** (Ampere ARM, Always Free
  — 2 OCPU / 12 GB is comfortably free tier; this app would run in 1/6 of that)
- Add your SSH public key
- Boot volume: default 47 GB is fine
- Networking: default VCN. **No ingress rules needed beyond SSH (22)** — the
  tunnel makes outbound connections only. You can even close 22 to the world
  and allow just your home IP.

## 2. Cloudflare zone + nameservers (console, one time)

1. Cloudflare → Add site → `hilobakestands.com` → Free plan. It imports DNS.
2. Namecheap → Domain → Nameservers → Custom DNS → paste the two Cloudflare
   nameservers it shows you.
3. Wait for "Active" in Cloudflare (minutes to a few hours).
4. Recommended Cloudflare settings once active: SSL/TLS mode **Full**,
   Always Use HTTPS on.

## 3. Get the code onto the box

From the Mac (or any machine with the project folder):

```bash
rsync -az --delete --exclude .venv --exclude db.sqlite3 --exclude .env \
  ~/Claude/Projects/HiloBakeStands.com/ ubuntu@oracle.hilobakestands.com:~/HiloBakeStands.com/
```

## 4. Bootstrap (paste into SSH on the box)

```bash
cd ~/HiloBakeStands.com && sudo bash deploy/bootstrap.sh
```

Installs Python env, creates `/opt/hilobakestands`, generates SECRET_KEY,
migrates, seeds, imports listings.xlsx (as drafts), collects static, starts
gunicorn via systemd, schedules nightly 03:15 backups, installs cloudflared.

Then create your admin login:

```bash
sudo -u hilobake bash -c 'set -a; source /opt/hilobakestands/.env; set +a; \
  /opt/hilobakestands/venv/bin/python /opt/hilobakestands/app/manage.py createsuperuser'
```

## 5. Connect the tunnel (paste into SSH, one interactive login)

```bash
sudo cloudflared tunnel login        # prints a URL — open it, pick the zone
sudo cloudflared tunnel create hilobakestands
sudo cloudflared tunnel route dns hilobakestands hilobakestands.com
sudo cloudflared tunnel route dns hilobakestands www.hilobakestands.com
sudo mkdir -p /etc/cloudflared && sudo cp /root/.cloudflared/*.json /etc/cloudflared/
sudo cp /opt/hilobakestands/app/deploy/cloudflared-config.yml /etc/cloudflared/config.yml
# edit /etc/cloudflared/config.yml: replace TUNNEL_ID (shown by `tunnel create`)
sudo cloudflared service install && sudo systemctl enable --now cloudflared
```

Site is now live at https://hilobakestands.com. Publish the listings:
admin → Stands → select all → action "Publish selected stands".

## Updating the app later

Routine deploys use **deploy.sh** — code, deps, migrations, static, restart.
It NEVER runs seed/import, so production data (admin edits, reports, claims)
is safe:

```bash
rsync -az --delete --exclude .venv --exclude db.sqlite3 --exclude .env ~/Claude/Projects/HiloBakeStands.com/ ubuntu@oracle.hilobakestands.com:~/HiloBakeStands.com/
ssh ubuntu@oracle.hilobakestands.com 'cd ~/HiloBakeStands.com && sudo bash deploy/deploy.sh'

`--delete` keeps the staging dir an exact mirror — without it, files deleted
or renamed locally would live on in staging and be re-deployed forever.
(deploy.sh's internal rsync already mirrors with --delete; excluded paths
are protected from deletion on both hops.)
```

bootstrap.sh is for provisioning a fresh box. It only seeds/imports when no
db.sqlite3 exists yet (or with `--with-data`). `import_listings` is itself
non-destructive now: existing stands are left untouched unless `--overwrite`.

## The two .env files — maintain them separately

There are now **two independent `.env` files** and deploys deliberately keep
them apart (rsync `--exclude .env` on both hops). Changing one does NOT change
the other — if a setting must apply in both places, edit both:

| | Dev (your Mac) | Prod (the box) |
|---|---|---|
| Path | `~/Claude/Projects/HiloBakeStands.com/.env` | `/opt/hilobakestands/.env` |
| Loaded by | the loader in `config/settings.py` (reads `BASE_DIR/.env` if present) | **systemd** EnvironmentFile, injected into the gunicorn process |
| `DEBUG` | `1` (full error pages for local dev) | `0` (fail-closed; no traceback/.env leakage) |
| Contains | only what local dev needs | real SECRET_KEY, OAuth secrets, DB_PATH, USAGE_LOG_PATH, etc. |
| Gitignored / deploy-excluded | yes | yes (lives outside `app/`, never synced) |

Because `settings.py` loads via `os.environ.setdefault`, the real environment
always wins: in prod systemd's values take precedence and the file loader is a
no-op. To change a prod value, edit `/opt/hilobakestands/.env` on the box and
restart (`sudo systemctl restart hilobakestands`) — a deploy will not do it for
you.

## Backups

- Nightly 03:15 HST snapshot to `/var/backups/hilobakestands`, 14-day retention.
- SPEC calls for off-box copies: from the home server, cron
  `rsync -az ubuntu@oracle.hilobakestands.com:/var/backups/hilobakestands/ ~/backups/hilobakestands/`
