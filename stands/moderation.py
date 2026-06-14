"""Automated photo moderation: Google Vision SafeSearch first, the
homelab NSFW service (media.home) as fallback.

Outcomes:
  'ok'          → photo is clean, caller may auto-approve
  'flagged'     → a backend judged it explicit; keep unapproved, tell admin
  'unavailable' → no backend reachable/configured; keep PENDING (fail SAFE,
                  not open — a stray explicit photo is worse than a delay)

Both backends are optional: unset settings simply skip that backend, so
dev and tests run without keys and the feature degrades to manual review.
"""
import base64
import json
import logging
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

VISION_URL = 'https://vision.googleapis.com/v1/images:annotate'
# Vision likelihoods, in order. LIKELY and up = flagged.
_BAD = {'LIKELY', 'VERY_LIKELY'}
_CHECKED = ('adult', 'violence', 'racy')


def _vision_safesearch(image_bytes):
    """Returns ('ok'|'flagged', detail) or raises on transport problems."""
    key = settings.VISION_API_KEY
    body = json.dumps({'requests': [{
        'image': {'content': base64.b64encode(image_bytes).decode()},
        'features': [{'type': 'SAFE_SEARCH_DETECTION'}],
    }]}).encode()
    req = urllib.request.Request(
        f'{VISION_URL}?key={key}', data=body,
        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.load(resp)
    ann = data['responses'][0].get('safeSearchAnnotation')
    if not ann:
        raise ValueError('no safeSearchAnnotation in response')
    detail = ', '.join(f'{k}={ann.get(k, "?")}' for k in _CHECKED)
    flagged = any(ann.get(k) in _BAD for k in _CHECKED)
    return ('flagged' if flagged else 'ok'), f'safesearch: {detail}'


def _homelab_check(image_bytes):
    """Returns ('ok'|'flagged', detail) or raises on transport problems."""
    url = settings.MODERATION_FALLBACK_URL
    req = urllib.request.Request(
        url, data=image_bytes,
        headers={'Content-Type': 'application/octet-stream',
                 'X-Auth-Token': settings.MODERATION_FALLBACK_TOKEN})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.load(resp)
    score = float(data['nsfw'])
    return (('flagged' if score >= 0.5 else 'ok'),
            f'homelab: nsfw={score:.3f}')


def moderate_image(image_bytes):
    """Run the backend chain. Never raises."""
    if settings.VISION_API_KEY:
        try:
            return _vision_safesearch(image_bytes)
        except (urllib.error.URLError, TimeoutError, ValueError,
                KeyError, OSError) as e:
            logger.warning('SafeSearch unavailable (%s); trying fallback', e)
    if settings.MODERATION_FALLBACK_URL:
        try:
            return _homelab_check(image_bytes)
        except (urllib.error.URLError, TimeoutError, ValueError,
                KeyError, OSError) as e:
            logger.warning('Homelab moderation unavailable (%s)', e)
    return 'unavailable', 'no moderation backend reachable'
