# Running your own copy (self-hosting guide)

This guide is for someone who wants to run this directory for **their own
town or island** — for example an Oahu version. It covers every account you
need, the server setup, and everything that's hardcoded to Hilo and must be
changed.

> **License:** this code is shared under the
> [PolyForm Noncommercial License 1.0.0](LICENSE.md). Running a free
> community directory as a hobby is fine. Charging stands to be listed,
> selling featured spots, or otherwise running it as a business is **not**.
> Keep `LICENSE.md` (including its `Required Notice:` line) in your copy.

---

## 0. What you're signing up for

**Skills:** comfortable in a terminal, with SSH and editing text files on a
Linux server. No Django experience is needed for a basic launch, but the
rebranding (section 7) means editing HTML templates and a little Python.

**Cost:** about **$10–15/year for the domain name**. Everything else below
fits in free tiers. Some providers (Oracle, Google Cloud) ask for a credit
card to verify your identity even on free plans. Stay on the
"Always Free" / free-plan options and you won't be billed.

**What runs where:**

```
Visitor ──HTTPS──> Cloudflare (DNS, TLS, caching, Turnstile)
                        │  Cloudflare Tunnel (outbound-only from your server;
                        │  no open inbound ports)
                        ▼
              Your Linux VM (Oracle Always Free)
              cloudflared → gunicorn (Django) on 127.0.0.1:8000
              SQLite database + uploaded photos on local disk
              nightly backup timer
```

**The stack:** Python 3 · Django 5.2 · SQLite · django-allauth (Google
sign-in) · gunicorn · whitenoise (static files) · Leaflet + OpenStreetMap
(maps; no API key) · OSM Nominatim (address → map pin; no API key) ·
Pillow / qrcode / reportlab (photos, QR codes, PDF flyers).

---

## 1. Accounts checklist

| Service | Needed? | What it's for | Cost |
|---|---|---|---|
| **Domain registrar** (Cloudflare Registrar, Namecheap, Porkbun…) | Required | Your domain name | ~$10–15/yr |
| **Cloudflare** | Required | DNS, HTTPS, Tunnel to your server, Turnstile bot check, optional email forwarding | Free plan |
| **Oracle Cloud** (or any Ubuntu VPS) | Required | The server | Always Free tier |
| **Google account** with 2-Step Verification | Required | Sending notification email (SMTP app password) | Free |
| **Google Cloud** project | Required | "Sign in with Google" for stand owners | Free |
| **GitHub** | Recommended | Keeping your copy of the code | Free |
| Google Cloud Vision API | Optional | Automatic photo safety check | Free 1,000/month, but needs billing linked |

---

## 2. Domain + Cloudflare

1. **Buy a domain.** Cloudflare Registrar sells at cost and skips the
   nameserver step below. Any registrar works.
2. **Create a free Cloudflare account** → *Add a domain* → Free plan.
3. If you bought the domain elsewhere, set its nameservers at your
   registrar to the two Cloudflare nameservers it shows you. Wait for
   Cloudflare to say **Active** (minutes to a few hours).
4. Recommended settings once active:
   - **SSL/TLS → Overview:** mode **Full**.
   - **SSL/TLS → Edge Certificates:** **Always Use HTTPS** on.
   - HSTS (same page) is optional. If you turn it on, leave *preload* off:
     preload is very hard to undo.

Don't create DNS records for the site by hand. The tunnel command in
section 4 creates them.

---

## 3. The server (Oracle Cloud Always Free)

Any Ubuntu 22.04 or 24.04 machine works (another cloud, a spare PC at home).
These steps assume Oracle.

1. Sign up at Oracle Cloud and pick a **home region** near you. You can't
   change it later, and free resources only exist in your home region.
2. **Compute → Instances → Create instance:**
   - Image: **Canonical Ubuntu 24.04**.
   - Shape: **VM.Standard.A1.Flex** (ARM, Always Free, up to 4 CPU / 24 GB)
     if capacity is available. A1 capacity is often "out of host capacity"
     for weeks. The x86 **VM.Standard.E2.1.Micro** (1 GB RAM, also Always
     Free) runs this site fine, and the original site ran on one.
   - Paste your **SSH public key**.
   - Networking: defaults are fine. **Don't open any inbound ports besides
     SSH (22)**. The Cloudflare Tunnel connects outward only. You can
     restrict SSH to your home IP.
3. SSH in: `ssh ubuntu@<public-ip>`. Make sure `rsync` is installed:
   `sudo apt-get update && sudo apt-get install -y rsync`.

**Packages:** `deploy/bootstrap.sh` installs everything else:

- apt: `python3-venv`, `python3-pip`, `sqlite3`, `curl`, `unattended-upgrades`
- `cloudflared` (latest .deb from Cloudflare's GitHub releases)
- Python packages from `requirements.txt` (Django, django-allauth, Pillow,
  openpyxl, whitenoise, gunicorn, qrcode, reportlab) in a venv

It also turns on automatic security updates, with auto-reboot at 14:30
server time (UTC by default, which is 4:30am Hawaii time) when needed.

---

## 4. Install the app

### 4a. Before you upload: edit `.env.example` and the data files

`bootstrap.sh` copies `.env.example` to the server's real config file on
first run and runs the first database migration with it. Edit these lines
in `.env.example` **first**, with your domain in place of `example.org`:

```
ALLOWED_HOSTS=example.org,www.example.org
CSRF_TRUSTED_ORIGINS=https://example.org,https://www.example.org
SITE_BASE_URL=https://example.org
ADMIN_EMAIL=you@gmail.com
```

(`ADMIN_EMAIL` is commented out in the file: remove the `#`. Don't put
comments at the end of a value line. systemd would treat them as part of
the value.)

> ⚠️ **Set `ADMIN_EMAIL`.** If you don't, every notification from your site
> (reports, submissions, errors) goes to the original author's email.

On a fresh database, bootstrap also loads:

- `seed`: payment methods, starter categories, and one **fake example
  stand** ("Auntie Lehua's", a Hilo address). Delete it in the admin later.
- `import_listings listings.xlsx`: **the Hilo listings, as drafts**. Before
  uploading, open `listings.xlsx` and replace the data rows with your own
  stands, or delete them and keep only the header row and the "Field guide"
  sheet. If you forget, delete the imported drafts in the admin.

### 4b. Upload and bootstrap

From your computer, in the project folder:

```bash
rsync -az --delete --exclude .venv --exclude db.sqlite3 --exclude .env --exclude media \
  ./ ubuntu@<server>:~/BakeStands/
ssh ubuntu@<server> 'cd ~/BakeStands && sudo bash deploy/bootstrap.sh'
```

This creates the `hilobake` system user and `/opt/hilobakestands/` (app,
venv, data, media, `.env` with a freshly generated `SECRET_KEY`), installs
the systemd services, and starts the site on `127.0.0.1:8000`.

The internal names (`hilobake`, `/opt/hilobakestands`, `hilobakestands.service`)
are never seen by visitors. **Leave them as they are**: renaming means
editing every file in `deploy/` consistently.

Create your admin login:

```bash
sudo -u hilobake bash -c 'set -a; source /opt/hilobakestands/.env; set +a; \
  /opt/hilobakestands/venv/bin/python /opt/hilobakestands/app/manage.py createsuperuser'
```

### 4c. Connect the Cloudflare Tunnel

First edit `deploy/cloudflared-config.yml` (on the server it's at
`/opt/hilobakestands/app/deploy/`) and replace both `hilobakestands.com`
hostnames with yours. Then, on the server:

```bash
sudo cloudflared tunnel login                # prints a URL: open it, pick your domain
sudo cloudflared tunnel create bakestands    # note the tunnel ID it prints
sudo cloudflared tunnel route dns bakestands example.org
sudo cloudflared tunnel route dns bakestands www.example.org
sudo mkdir -p /etc/cloudflared && sudo cp /root/.cloudflared/*.json /etc/cloudflared/
sudo cp /opt/hilobakestands/app/deploy/cloudflared-config.yml /etc/cloudflared/config.yml
sudo nano /etc/cloudflared/config.yml        # replace TUNNEL_ID (2 places) with the ID
sudo cloudflared service install && sudo systemctl enable --now cloudflared
```

Your site should now load at `https://example.org`, and the admin at
`/admin/`.

---

## 5. Server config: the `.env` file

The real config lives at **`/opt/hilobakestands/.env`** on the server.
systemd loads it into the app. Deploys never overwrite it. After any
change:

```bash
sudo nano /opt/hilobakestands/.env
sudo systemctl restart hilobakestands
```

| Variable | Required? | Notes |
|---|---|---|
| `SECRET_KEY` | Yes | Generated by bootstrap. Keep it secret; the site won't start without it. |
| `DEBUG` | Yes | Must be `0` in production. |
| `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` | Yes | Your domain(s), see 4a. |
| `SITE_BASE_URL` | Yes | `https://your-domain`, no trailing slash. |
| `ADMIN_EMAIL` | **Yes** | Where notifications go. |
| `DB_PATH`, `MEDIA_ROOT`, `USAGE_LOG_PATH` | Yes | Leave as in `.env.example`. |
| `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | Yes | Section 6a. |
| `DEFAULT_FROM_EMAIL` | Yes, for you | Section 6a. |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Yes | Section 6b. |
| `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY` | Recommended | Section 6c. Blank = no bot check. |
| `VISION_API_KEY` | Optional | Section 6d. |
| `MODERATION_FALLBACK_URL`, `MODERATION_FALLBACK_TOKEN` | Optional | Self-hosted photo checker, see `deploy/homelab-moderation/`. Skip it. |
| `APPLE_*` | No | Apple sign-in is wired up but unused (it needs a $99/yr Apple account). |

**Never commit a real `.env` to git.** `.gitignore` already excludes it.

---

## 6. Third-party setup

### 6a. Email

The site sends email **only to you** (`ADMIN_EMAIL`): new reports, new
community submissions, photos needing review, and server errors. It never
emails the public, so deliverability barely matters. The code sends through
Gmail's SMTP server (`smtp.gmail.com:587`).

1. Use a Google account (plain Gmail is fine) with **2-Step Verification**
   on.
2. Google Account → Security → **App passwords** → create one.
3. In `/opt/hilobakestands/.env`:
   ```
   EMAIL_HOST_USER=you@gmail.com
   EMAIL_HOST_PASSWORD=<the 16-character app password>
   DEFAULT_FROM_EMAIL=you@gmail.com
   ```
   `DEFAULT_FROM_EMAIL` must be the Gmail address itself or a verified Gmail
   "Send mail as" alias. Use a plain address here: systemd mangles
   `Name <addr>` values. To get a friendly display name, edit the default in
   `config/settings.py` (search `DEFAULT_FROM_EMAIL`) and leave the `.env`
   line blank.

**A contact address on your domain** (the site shows one on the FAQ and
claim pages): the easy free option is **Cloudflare Email Routing**
(Cloudflare → your domain → Email → Email Routing). It forwards
`hello@your-domain` to your Gmail and adds the DNS records itself.

### 6b. "Sign in with Google" (required for stand owners)

1. https://console.cloud.google.com → create a project.
2. **APIs & Services → OAuth consent screen** (now called *Google Auth
   Platform*): User type **External**, app name, your support email, your
   domain. Scopes: only the basic `email` and `profile` (no Google review
   needed).
   **Publish the app ("In production").** In *Testing* mode only listed test
   users can sign in.
3. **Credentials → Create credentials → OAuth client ID → Web application:**
   - Authorized JavaScript origins: `https://example.org`
   - Authorized redirect URIs:
     `https://example.org/accounts/google/login/callback/`
     (add the `www.` versions too if you use www)
4. Put the client ID and secret in `.env` as `GOOGLE_CLIENT_ID` /
   `GOOGLE_CLIENT_SECRET`, then restart.

The client ID is public by design (it appears in the login URL). The
**client secret** is the sensitive one.

### 6c. Cloudflare Turnstile (spam/bot check on public forms)

Cloudflare → **Turnstile → Add widget** → hostname = your domain, mode
*Managed*. Put the **site key** and **secret key** in `.env` as
`TURNSTILE_SITE_KEY` / `TURNSTILE_SECRET_KEY`, then restart.

### 6d. Photo moderation (optional, can wait)

Without any moderation backend, owner-uploaded photos **wait for you to
approve them** in the admin. That's fine for a small site. For automatic
checks with Google Vision SafeSearch (1,000 free per month):

1. In your Google Cloud project, enable **Cloud Vision API**.
2. Create a **billing account** and link it **to the project**. Vision
   returns 403 errors until the *project* is linked, even inside the free
   quota. Set a budget alert.
3. Create an **API key** restricted to *Cloud Vision API* only, and to your
   server's IP address.
4. `VISION_API_KEY=<key>` in `.env`, then restart.

---

## 7. Rebranding: everything hardcoded to Hilo

None of this is in `.env`. These are code edits. Do them in your copy
before going live.

### Must change (or the site misbehaves)

| What | Where | Why |
|---|---|---|
| **Map-pin bounding box** | `stands/views.py`: `BIG_ISLAND_BOUNDS` | Pins outside the Big Island are **rejected**. Oahu is roughly `{'lat': (21.2, 21.8), 'lng': (-158.35, -157.6)}`. |
| **Geocoder area** | `stands/geocoding.py`: `VIEWBOX`, and the `", Hawaii, USA"` suffix in `queries_for` | Address lookup only searches the Big Island. Oahu viewbox: `'-158.35,21.8,-157.6,21.2'` (lng1,lat1,lng2,lat2). |
| **Geocoder contact** | `stands/geocoding.py`: `USER_AGENT` | OpenStreetMap's Nominatim usage policy requires *your* contact info. |
| **Default map center** (Hilo `19.7074, -155.0885`) | `stands/templates/stands/list.html`, `map.html`, `submit.html`, `edit_pin.html`, and `stands/static/stands/admin_map_pin.js` | Maps open on Hilo. Honolulu is about `21.3069, -157.8583`. |
| **Tunnel hostnames** | `deploy/cloudflared-config.yml` | See 4c. |
| **Notification From/To defaults** | `config/settings.py`: `DEFAULT_FROM_EMAIL`, `ADMINS` | Original author's addresses (or set both in `.env`). |

### Should change (branding and contact info)

- **Site name "HiloBakeStands"** in page titles: almost every file in
  `stands/templates/`, plus the header, footer and default
  description/social-share text in `stands/templates/stands/base.html`.
- **Contact email `matt@hilobakestands.com` and Instagram `@hilobakestands`**:
  `faq.html`, `claim_your_stand.html`, `claim_invalid.html`,
  `edit_stand.html`, `submit.html`, `stands/flyers.py`, and the
  `security.txt` view at the bottom of `stands/views.py`.
- **Copy that mentions Hilo / the Big Island**: `faq.html`,
  `claim_your_stand.html`, `list.html`, `map.html`, `submit.html`, the
  detail-page description in `stands/views.py` (`meta_description`), and the
  printable claim flyers in `stands/flyers.py`.
- **Admin**: the site header/title at the bottom of `stands/admin.py` and
  the owner outreach message template near the top of the same file.
- **Images**: `stands/static/stands/og-image.png` (social-share preview) and
  the hibiscus logo files (`hibiscus.svg` / `.png`), and `brand/`.
- **Django "Site" name**: set it in the admin under *Sites*. Don't edit
  the migration files.

To find anything left over:

```bash
grep -rniE 'hilo|big island|hilobakestands|matt@|19\.70' \
  stands config deploy --include='*.py' --include='*.html' --include='*.js' --include='*.yml'
```

**Tests:** `stands/tests.py` uses Big Island coordinates. After changing the
bounding box, update those coordinates so the test suite passes:

```bash
DEBUG=1 python manage.py test stands
```

### Things you can ignore or delete

- `tools/`: the original author's personal Oracle-capacity scripts.
- `deploy/homelab-moderation/`: optional self-hosted photo checker that
  needs a ~16 GB home server. Skip it.
- `SPEC.md`, `SPEC-1.1.md`, `STATUS.md`, `DEPLOY.md`, `build.log`,
  `deploy.log`: the original project's design notes and history. Useful
  background reading, but they describe the Hilo setup specifically.
- `stands/data/denylist.txt`: the text-moderation word list. It's tuned for
  Hawaii (it includes Pidgin/Hawaiian terms) and should work as-is on Oahu.
  Edit it only in a plain-text code editor, never TextEdit/Word: smart
  quotes corrupt it.

---

## 8. Running it day to day

**Deploy code changes** (data-safe: never touches the database or photos):

```bash
rsync -az --delete --exclude .venv --exclude db.sqlite3 --exclude .env --exclude media \
  ./ ubuntu@<server>:~/BakeStands/
ssh ubuntu@<server> 'cd ~/BakeStands && sudo bash deploy/deploy.sh'
```

**The live database is the source of truth.** Add and edit listings in the
admin. Never re-run `seed`/`import_listings` or copy a local `db.sqlite3`
over the server's.

**Backups:** a systemd timer snapshots the database nightly at 03:15
server time (Oracle VMs run on UTC, so that's 5:15pm Hawaii time) to
`/var/backups/hilobakestands/` (kept 14 days), plus a copy of uploaded
photos. That's on the same server, so also copy it somewhere else, e.g. a
nightly `rsync` from a home computer.

**Useful commands on the server:**

```bash
sudo systemctl status hilobakestands        # is the app running?
sudo journalctl -u hilobakestands -n 100    # recent app logs
sudo systemctl status cloudflared           # is the tunnel up?
```

**Local development:** see `README.md` (quick start). Create a local `.env`
with `DEBUG=1`. In debug mode, emails print to the terminal instead of being
sent.

---

## 9. Pre-launch checklist

- [ ] `https://your-domain` loads, with a padlock.
- [ ] `ADMIN_EMAIL` is set to **you**. Submit a test report on a stand and
      confirm the email arrives.
- [ ] "Sign in with Google" works from a non-admin Google account.
- [ ] Turnstile appears on the submit/report forms.
- [ ] You can drop a map pin on your island (bounding box updated).
- [ ] The fake example stand and any imported Hilo drafts are deleted.
- [ ] No "Hilo" left in visible pages (run the grep in section 7).
- [ ] `sudo ls /var/backups/hilobakestands/` shows a backup the morning after.
- [ ] `LICENSE.md` is still in your repo.
