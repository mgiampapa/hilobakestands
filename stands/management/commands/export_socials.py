"""Dump published stands' social handles to a JSON file for the activity monitor.

Usage:
    python manage.py export_socials [--out PATH]

This is the Oracle-side half of the social-activity monitor (see
tools/social-monitor/). It runs from cron on the web server and leaves a small
JSON snapshot on the local filesystem. The homelab ("media") box scp's that
file and parses it each run — nothing here is exposed to the internet, and the
monitor never touches this database directly.

Only PUBLISHED stands with a non-empty instagram handle are exported (those are
the only ones the posts-only signal can check). Handles are normalised to a
bare username so the homelab side can build the IG URL without guessing.

The write is atomic (temp file + os.replace) so the homelab never scp's a
half-written file if the two crons happen to overlap.
"""
import json
import os
import tempfile

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from stands.models import Stand

# Default lands next to the project; override with --out or SOCIALS_EXPORT_PATH.
DEFAULT_OUT = os.environ.get(
    'SOCIALS_EXPORT_PATH',
    os.path.join(settings.BASE_DIR, 'exports', 'stands_socials.json'),
)


def normalise_handle(raw):
    """Return a bare instagram username from whatever was stored.

    The model stores `instagram` as a handle, but be defensive: tolerate a
    leading '@', a full instagram.com URL, or trailing slashes/query strings.
    Returns '' if nothing usable is left.
    """
    h = (raw or '').strip()
    if not h:
        return ''
    h = h.split('?', 1)[0].rstrip('/')          # drop query + trailing slash
    if 'instagram.com' in h:
        h = h.rstrip('/').rsplit('/', 1)[-1]      # .../<handle>
    return h.lstrip('@').strip()


class Command(BaseCommand):
    help = "Export published stands' instagram handles to JSON for the monitor."

    def add_arguments(self, parser):
        parser.add_argument(
            '--out', default=DEFAULT_OUT,
            help=f'Output path (default: {DEFAULT_OUT}).')

    def handle(self, *args, **opts):
        out_path = opts['out']
        os.makedirs(os.path.dirname(out_path), exist_ok=True)

        rows = []
        qs = (Stand.objects
              .filter(status=Stand.Status.PUBLISHED)
              .exclude(instagram='')
              .order_by('name'))
        for s in qs:
            handle = normalise_handle(s.instagram)
            if not handle:
                continue
            rows.append({
                'slug': s.slug,
                'name': s.name,
                'instagram': handle,
                'verification': s.verification,
                'detail_url': f"{settings.SITE_BASE_URL}{s.get_absolute_url()}",
            })

        payload = {
            'generated_at': timezone.now().isoformat(),
            'count': len(rows),
            'stands': rows,
        }

        # Atomic write: temp file in the same dir, then replace.
        d = os.path.dirname(out_path)
        fd, tmp = tempfile.mkstemp(dir=d, prefix='.stands_socials.', suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
            os.replace(tmp, out_path)
        except Exception:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

        self.stdout.write(self.style.SUCCESS(
            f'Wrote {len(rows)} stand(s) with instagram handles to {out_path}'))
