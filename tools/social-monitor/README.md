# Social-activity monitor (posts-only)

Surfaces two signals for manual review, by email, **only when they change**:

- **Gone quiet** — a stand with no Instagram post in the last 30 days. Likely on
  hiatus / closed → needs validation.
- **Resumed** — a previously-quiet stand that posted again → treat as active.

It does **not** modify the site. It's a standalone watcher. (A third "couldn't
check" line appears if a handle fails for 3+ days running — usually a renamed or
deleted account worth a look.)

## Why two boxes

Instagram hard-blocks datacenter IPs, so the fetcher **must not** run on the
Oracle web server. It runs on the homelab (`media`, residential IP). The web
server only exports the stand list to a local file; the homelab pulls it by scp.

```
Oracle (web)                         media (homelab)
  manage.py export_socials   --scp-->  run.sh -> monitor.py
  writes exports/                       reads stands_socials.json
  stands_socials.json                   keeps monitor_state.sqlite
                                        emails digest on change
```

## Web-server side (Oracle)

`stands/management/commands/export_socials.py` writes published stands' IG
handles to JSON. Run it from cron via `deploy/export_socials.sh`, which sources
the prod env (cron has no systemd, so `SECRET_KEY` etc. must be loaded by hand)
and uses the prod venv at `/opt/hilobakestands/venv`. Schedule it as the app
user, a little before the homelab run:

```cron
# sudo -u hilobake crontab -e   (write the snapshot at 07:05)
5 7 * * *  /opt/hilobakestands/app/deploy/export_socials.sh >> /opt/hilobakestands/export.log 2>&1
```

Output lands at `/opt/hilobakestands/app/exports/stands_socials.json` (this is
`<BASE_DIR>/exports/`; override with `--out`/`SOCIALS_EXPORT_PATH`). Nothing is
exposed to the internet — the homelab reads it over ssh.

## Homelab side (media)

```bash
cd /home/matt/social-monitor
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then edit: ssh target, paths, SMTP app password
chmod +x run.sh
```

Test it without sending mail or hammering IG:

```bash
# uses whatever stands_socials.json you've copied locally
python3 monitor.py --dry-run --no-delay
```

Then schedule the wrapper (it does the scp + the run):

```cron
17 7 * * *  /home/matt/social-monitor/run.sh >> /home/matt/social-monitor/run.log 2>&1
```

## How the signal works

Each run records each stand's newest-post timestamp in `monitor_state.sqlite`
and classifies it `active` (post within `LOOKBACK_DAYS`) or `quiet`. An email
fires only on an `active <-> quiet` crossing — never every day, and never on the
first time a stand is seen (that's just a baseline). A blocked/failed fetch
never flips a stand to quiet, so a bad IG day won't cause false alarms.

## Known limits

- **Pinned posts** sort to the front with old dates → we use the max timestamp
  across returned posts, not the first.
- **Private accounts** can't be read → reported as "private", no state change.
- **IG changes** occasionally break the endpoint; the "couldn't check" line is
  your early warning. `web_profile_info` is more stable than the graphql path
  but expect to touch this a few times a year.
- **Notes** (the ephemeral status field) are not public and are out of scope
  here. Adding them later needs an authenticated `@hilobakestands` session that
  follows each stand — separate build, account-ban risk.

## Files

| file | runs on | purpose |
|------|---------|---------|
| `../../stands/management/commands/export_socials.py` | Oracle | export handles to JSON |
| `monitor.py` | media | fetch + classify + email |
| `run.sh` | media | scp pull, then run monitor |
| `.env.example` | media | config template |
| `tests/test_logic.py` | anywhere | offline logic checks (no network) |
