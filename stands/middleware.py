"""Lightweight, privacy-preserving usage logging.

Appends one JSON line per non-static request to a local file
(settings.USAGE_LOG_PATH). No cookies, no third-party JavaScript, no
consent banner — it just records what the server already sees.

The visitor IP is NEVER stored raw: only a daily-salted, non-reversible
hash, so rough unique counts are possible within a day without retaining
PII (the salt rotates daily, so hashes aren't linkable across days).

Primary purpose: read visitors' preferred language (Accept-Language) to
decide whether Japanese i18n is worth doing, plus basic usage stats.
Heavy analysis is meant to happen off-box on the JSONL file.
"""
import hashlib
import json
import logging
from datetime import datetime, timezone

from django.conf import settings

logger = logging.getLogger(__name__)

# Noise we don't care about (static assets, favicon probes).
_SKIP_PREFIXES = ('/static/', '/media/', '/favicon')


def _client_ip(request):
    """Real client IP. Behind the Cloudflare Tunnel it arrives in
    CF-Connecting-IP; REMOTE_ADDR is just the local tunnel."""
    meta = request.META
    return (meta.get('HTTP_CF_CONNECTING_IP')
            or meta.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
            or meta.get('REMOTE_ADDR', ''))


def _visitor_hash(ip):
    """Daily-salted one-way hash of the IP. Unique within a UTC day,
    not linkable across days, never reversible to the address."""
    if not ip:
        return ''
    # UTC date so the hash's day boundary matches the UTC 'ts' we log,
    # making per-day unique counts exact regardless of the server's TZ.
    today = datetime.now(timezone.utc).date().isoformat()
    salt = f'{settings.SECRET_KEY}|{today}'
    return hashlib.sha256(f'{salt}|{ip}'.encode()).hexdigest()[:16]


class UsageLogMiddleware:
    """Append-only JSONL request log. Fails silently — must never break
    a request just because logging hiccupped."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        # Resolved per-request so settings overrides (and tests) take effect.
        path = getattr(settings, 'USAGE_LOG_PATH', None)
        if path and not request.path.startswith(_SKIP_PREFIXES):
            try:
                self._write(path, request, response)
            except Exception:  # noqa: BLE001 - logging is best-effort
                logger.warning('usage log write failed', exc_info=True)
        return response

    def _write(self, path, request, response):
        rec = {
            'ts': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'visitor': _visitor_hash(_client_ip(request)),
            'method': request.method,
            'path': request.path[:200],
            'status': response.status_code,
            'lang': request.META.get('HTTP_ACCEPT_LANGUAGE', '')[:200],
            'ua': request.META.get('HTTP_USER_AGENT', '')[:300],
            'ref': request.META.get('HTTP_REFERER', '')[:200],
        }
        line = json.dumps(rec, ensure_ascii=False)
        # O_APPEND keeps short concurrent writes from gunicorn workers atomic.
        with open(path, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
