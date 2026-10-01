# HiloBakeStands.com

Directory of bake stands, food trucks, farm stands, and pop-ups in Hilo, HI.
See `SPEC.md` for the full project specification.

**Running your own copy for another town?** Start with
[`SELF-HOSTING.md`](SELF-HOSTING.md) — accounts, hosting, Cloudflare, email,
sign-in, and everything that needs rebranding.

## Quick start

```bash
cd /path/to/HiloBakeStands.com
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed              # payment methods, categories, example stand
python manage.py import_listings   # imports listings.xlsx as DRAFTS for review
python manage.py createsuperuser   # your admin login
python manage.py runserver
```

Then open http://127.0.0.1:8000/ (public site) and http://127.0.0.1:8000/admin/
(enter real listings here — the example stand is fake and safe to delete).

## Environment variables (all optional until launch)

| Variable | Purpose |
|---|---|
| `DB_PATH` | SQLite file location (defaults to `db.sqlite3` in project root) |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google sign-in (django-allauth) |
| `APPLE_CLIENT_ID` / `APPLE_KEY_ID` / `APPLE_PRIVATE_KEY` | Apple sign-in |
| `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | Gmail SMTP (app-specific password) |
| `DEFAULT_FROM_EMAIL` | From address for outgoing mail |

In `DEBUG` mode, email prints to the console instead of sending.

## Layout

- `config/` — Django settings, urls
- `stands/` — the app: models, admin, views, templates, `seed` command
- `listings.xlsx` — data-collection spreadsheet; `python manage.py import_listings`
  loads it (drafts by default, `--publish` to go straight live; idempotent —
  re-running updates from the sheet and rebuilds hours)

## Tests

```bash
python manage.py test
```

## Before launch (from SPEC)

- Set `DEBUG = False`, set `ALLOWED_HOSTS`, generate a fresh `SECRET_KEY`
- Cloudflare in front; Turnstile on the report/submission forms
- Nightly copy of the SQLite file to a second machine
- OAuth credentials for Google/Apple sign-in

## License

Free for personal, hobby, nonprofit, and educational use under the
[PolyForm Noncommercial License 1.0.0](LICENSE.md). Commercial use is not
permitted. If you share this code or a modified version, include `LICENSE.md`
(including its `Required Notice:` line).
