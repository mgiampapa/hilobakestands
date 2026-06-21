#!/usr/bin/env python3
"""HiloBakeStands social-activity monitor (posts-only, runs on the homelab).

What it does, once a day:
  1. Reads a JSON snapshot of published stands + their instagram handles
     (produced on the web server by `manage.py export_socials` and scp'd here).
  2. For each stand, fetches the timestamp of its newest public Instagram post.
  3. Compares against a small local SQLite state file and decides whether the
     stand just crossed one of two thresholds:
        * WENT QUIET  — was active, now no post in the last LOOKBACK_DAYS days.
        * RESUMED     — was quiet, a fresh post has appeared.
  4. Emails a short digest *only when something changed*. Silent otherwise.

Design notes / deliberate choices:
  - Runs from a RESIDENTIAL IP (the homelab). Instagram hard-blocks datacenter
    IPs, so this must NOT run on the Oracle web server.
  - Uses curl_cffi (TLS-impersonates a browser); plain `requests` is fingerprinted
    and blocked. Endpoint is web_profile_info, which is more stable than the
    graphql doc_id path (that rotates every few weeks).
  - Pinned posts can sort to the front with an OLD timestamp, so we take the
    MAX timestamp across the returned posts, not the first one.
  - First time we ever see a stand we only record a baseline — we never email a
    transition on first sight (otherwise the first run would flood you).
  - A failed/blocked fetch never flips a stand to "quiet" — that would be a false
    alarm. Errors are counted; a handle that fails ERROR_THRESHOLD days running
    is surfaced once as "couldn't check — verify the handle."
  - Notes (the ephemeral IG status field) are NOT covered: they aren't public.
    This is the posts-only first pass; a Notes tier would need an authenticated
    @hilobakestands session and is intentionally out of scope here.

Nothing is committed or run automatically — review, then wire up cron yourself.
"""
import argparse
import json
import os
import random
import smtplib
import sqlite3
import sys
import time
from datetime import datetime, timezone
from email.message import EmailMessage

# --------------------------------------------------------------------------- #
# Config (env-driven; see .env.example). Kept here so the file is self-documenting.
# --------------------------------------------------------------------------- #
def _env(name, default=None):
    return os.environ.get(name, default)

LOOKBACK_DAYS   = int(_env('LOOKBACK_DAYS', '30'))
ERROR_THRESHOLD = int(_env('ERROR_THRESHOLD', '3'))     # consecutive fails before flagging
MIN_DELAY       = float(_env('MIN_DELAY', '6'))          # seconds between fetches
MAX_DELAY       = float(_env('MAX_DELAY', '18'))
REQUEST_TIMEOUT = int(_env('REQUEST_TIMEOUT', '25'))

STANDS_JSON = _env('STANDS_JSON', 'stands_socials.json')
STATE_DB    = _env('STATE_DB', 'monitor_state.sqlite')

SMTP_HOST = _env('EMAIL_HOST', 'smtp.gmail.com')
SMTP_PORT = int(_env('EMAIL_PORT', '587'))
SMTP_USER = _env('EMAIL_HOST_USER', '')
SMTP_PASS = _env('EMAIL_HOST_PASSWORD', '')
MAIL_FROM = _env('DIGEST_FROM', 'Hilo Bake Stands Monitor <matt@hilobakestands.com>')
MAIL_TO   = _env('DIGEST_TO', 'matt@giampapa.com')

IG_ENDPOINT = 'https://www.instagram.com/api/v1/users/web_profile_info/?username={}'
IG_APP_ID = '936619743392459'   # public web app id IG's own site sends


# --------------------------------------------------------------------------- #
# Pure logic (no network / no DB) — this is what the offline tests exercise.
# --------------------------------------------------------------------------- #
def classify(last_post_at, now_ts, lookback_days=LOOKBACK_DAYS):
    """Return 'active' or 'quiet' from a newest-post unix ts (or None)."""
    if last_post_at is None:
        return 'quiet'          # zero visible posts == no recent activity
    return 'active' if (now_ts - last_post_at) <= lookback_days * 86400 else 'quiet'


def decide(prev_state, new_state):
    """Map (previous stored state, freshly-computed state) -> a signal.

    Returns one of: None, 'went_quiet', 'resumed'. We only ever signal on a real
    active<->quiet crossing; first sight (prev None/'unknown') is a baseline.
    """
    if prev_state in (None, 'unknown'):
        return None
    if prev_state == 'active' and new_state == 'quiet':
        return 'went_quiet'
    if prev_state == 'quiet' and new_state == 'active':
        return 'resumed'
    return None


# --------------------------------------------------------------------------- #
# State store
# --------------------------------------------------------------------------- #
SCHEMA = """
CREATE TABLE IF NOT EXISTS stand_state (
    slug                TEXT PRIMARY KEY,
    name                TEXT,
    instagram           TEXT,
    detail_url          TEXT,
    last_post_at        INTEGER,
    state               TEXT,
    last_state_change   TEXT,
    last_checked        TEXT,
    consecutive_errors  INTEGER DEFAULT 0,
    error_notified      INTEGER DEFAULT 0,
    last_error          TEXT
);
"""

def open_state(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn

def get_row(conn, slug):
    cur = conn.execute('SELECT * FROM stand_state WHERE slug=?', (slug,))
    return cur.fetchone()

def upsert(conn, slug, **cols):
    existing = get_row(conn, slug)
    if existing:
        sets = ', '.join(f'{k}=?' for k in cols)
        conn.execute(f'UPDATE stand_state SET {sets} WHERE slug=?',
                     (*cols.values(), slug))
    else:
        cols = {'slug': slug, **cols}
        names = ', '.join(cols)
        marks = ', '.join('?' for _ in cols)
        conn.execute(f'INSERT INTO stand_state ({names}) VALUES ({marks})',
                     tuple(cols.values()))
    conn.commit()


# --------------------------------------------------------------------------- #
# Instagram fetch — returns ('ok', last_post_at|None) / ('private',None) /
#                            ('notfound',msg) / ('error',msg)
# --------------------------------------------------------------------------- #
def fetch_last_post(handle):
    try:
        from curl_cffi import requests as cffi
    except ImportError:
        return ('error', 'curl_cffi not installed')

    url = IG_ENDPOINT.format(handle)
    headers = {
        'x-ig-app-id': IG_APP_ID,
        'Accept': '*/*',
        'Referer': f'https://www.instagram.com/{handle}/',
    }
    try:
        r = cffi.get(url, headers=headers, impersonate='chrome',
                     timeout=REQUEST_TIMEOUT)
    except Exception as e:                       # network / TLS / timeout
        return ('error', f'request failed: {e}')

    if r.status_code == 404:
        return ('notfound', 'profile not found (handle changed or deleted?)')
    if r.status_code == 429:
        return ('error', 'rate limited (429)')
    if r.status_code != 200:
        return ('error', f'http {r.status_code}')

    try:
        user = r.json()['data']['user']
    except Exception:
        # Usually a login wall / challenge HTML instead of JSON.
        return ('error', 'unexpected response (login wall or block?)')

    if user is None:
        return ('notfound', 'profile not found')

    edges = (user.get('edge_owner_to_timeline_media') or {}).get('edges') or []
    timestamps = [e['node']['taken_at_timestamp']
                  for e in edges if e.get('node', {}).get('taken_at_timestamp')]
    if timestamps:
        return ('ok', max(timestamps))           # MAX guards against pinned posts
    if user.get('is_private'):
        return ('private', None)                  # can't see posts, not an error
    return ('ok', None)                           # public account, zero posts


# --------------------------------------------------------------------------- #
# Core pass — generic over a fetcher + store so it can be tested without network.
# --------------------------------------------------------------------------- #
def run_pass(stands, conn, fetcher, now_ts, *, delay=False, log=print):
    """Process all stands; return dict of digest sections."""
    digest = {'went_quiet': [], 'resumed': [], 'needs_check': []}
    now_iso = datetime.fromtimestamp(now_ts, timezone.utc).isoformat()
    order = list(stands)
    random.shuffle(order)                          # vary request order

    for i, stand in enumerate(order):
        slug, handle = stand['slug'], stand['instagram']
        prev = get_row(conn, slug)
        prev_state = prev['state'] if prev else None
        kind, value = fetcher(handle)

        if kind in ('error', 'notfound'):
            errs = (prev['consecutive_errors'] if prev else 0) + 1
            notified = prev['error_notified'] if prev else 0
            if errs >= ERROR_THRESHOLD and not notified:
                digest['needs_check'].append({**stand, 'reason': value})
                notified = 1
            upsert(conn, slug, name=stand['name'], instagram=handle,
                   detail_url=stand.get('detail_url', ''),
                   last_checked=now_iso, consecutive_errors=errs,
                   error_notified=notified, last_error=value)
            log(f'  ! {handle}: {value} (fail {errs})')

        elif kind == 'private':
            # No activity state change; just note we looked.
            new_state = prev_state if prev_state else 'unknown'
            upsert(conn, slug, name=stand['name'], instagram=handle,
                   detail_url=stand.get('detail_url', ''), state=new_state,
                   last_checked=now_iso, consecutive_errors=0, error_notified=0,
                   last_error='private/not visible')
            log(f'  ~ {handle}: private/not visible')

        else:  # 'ok'
            last_post_at = value
            new_state = classify(last_post_at, now_ts)
            signal = decide(prev_state, new_state)
            entry = {**stand, 'last_post_at': last_post_at,
                     'days_since': (None if last_post_at is None
                                    else int((now_ts - last_post_at) // 86400))}
            if signal == 'went_quiet':
                digest['went_quiet'].append(entry)
            elif signal == 'resumed':
                digest['resumed'].append(entry)
            change_iso = (now_iso if (prev is None or prev_state != new_state)
                          else prev['last_state_change'])
            upsert(conn, slug, name=stand['name'], instagram=handle,
                   detail_url=stand.get('detail_url', ''),
                   last_post_at=last_post_at, state=new_state,
                   last_state_change=change_iso, last_checked=now_iso,
                   consecutive_errors=0, error_notified=0, last_error='')
            tag = f' [{signal}]' if signal else ''
            log(f'  . {handle}: {new_state}{tag}')

        if delay and i < len(order) - 1:
            time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

    return digest


# --------------------------------------------------------------------------- #
# Digest email
# --------------------------------------------------------------------------- #
def render_digest(digest, now_ts):
    lines = []
    when = datetime.fromtimestamp(now_ts, timezone.utc).strftime('%Y-%m-%d')
    if digest['went_quiet']:
        lines.append(f"GONE QUIET — no post in {LOOKBACK_DAYS}+ days (needs validation):")
        for s in digest['went_quiet']:
            d = 'no visible posts' if s['days_since'] is None else f"{s['days_since']} days ago"
            lines.append(f"  • {s['name']}  (@{s['instagram']}, last post {d})")
            if s.get('detail_url'):
                lines.append(f"      {s['detail_url']}")
        lines.append('')
    if digest['resumed']:
        lines.append("RESUMED — posted again, treat as active:")
        for s in digest['resumed']:
            d = '' if s['days_since'] is None else f" ({s['days_since']} days ago)"
            lines.append(f"  • {s['name']}  (@{s['instagram']}{d})")
            if s.get('detail_url'):
                lines.append(f"      {s['detail_url']}")
        lines.append('')
    if digest['needs_check']:
        lines.append(f"COULDN'T CHECK — failed {ERROR_THRESHOLD}+ days running (verify handle):")
        for s in digest['needs_check']:
            lines.append(f"  • {s['name']}  (@{s['instagram']}): {s['reason']}")
            if s.get('detail_url'):
                lines.append(f"      {s['detail_url']}")
        lines.append('')
    body = '\n'.join(lines).rstrip()
    subj = f"Bake stand activity — {when}: " + ', '.join(
        p for p in [
            f"{len(digest['went_quiet'])} quiet" if digest['went_quiet'] else '',
            f"{len(digest['resumed'])} resumed" if digest['resumed'] else '',
            f"{len(digest['needs_check'])} uncheckable" if digest['needs_check'] else '',
        ] if p)
    return subj, body


def send_email(subject, body, dry_run=False):
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = MAIL_FROM
    msg['To'] = MAIL_TO
    msg.set_content(body)
    if dry_run or not SMTP_USER:
        print('--- EMAIL (not sent) ---')
        print(f'Subject: {subject}\n')
        print(body)
        print('------------------------')
        return
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.starttls()
        smtp.login(SMTP_USER, SMTP_PASS)
        smtp.send_message(msg)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def load_stands(path):
    with open(path, encoding='utf-8') as fh:
        data = json.load(fh)
    return [s for s in data.get('stands', []) if s.get('instagram')]


def main():
    ap = argparse.ArgumentParser(description='HiloBakeStands social activity monitor')
    ap.add_argument('--stands', default=STANDS_JSON, help='path to stands_socials.json')
    ap.add_argument('--state', default=STATE_DB, help='path to sqlite state file')
    ap.add_argument('--dry-run', action='store_true',
                    help='print the digest instead of emailing')
    ap.add_argument('--no-delay', action='store_true',
                    help='skip inter-request jitter (testing only)')
    args = ap.parse_args()

    try:
        stands = load_stands(args.stands)
    except FileNotFoundError:
        sys.exit(f'stands file not found: {args.stands} (did the scp run?)')
    if not stands:
        print('no stands with instagram handles — nothing to do')
        return

    conn = open_state(args.state)
    now_ts = int(time.time())
    print(f'Checking {len(stands)} stand(s) at '
          f'{datetime.fromtimestamp(now_ts, timezone.utc).isoformat()} ...')

    digest = run_pass(stands, conn, fetch_last_post, now_ts,
                      delay=not args.no_delay)

    if any(digest.values()):
        subject, body = render_digest(digest, now_ts)
        send_email(subject, body, dry_run=args.dry_run)
        print(f'Digest sent: {subject}')
    else:
        print('No transitions today — staying silent.')


if __name__ == '__main__':
    main()
