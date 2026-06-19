"""Shared OSM Nominatim geocoding for HiloBakeStands.

Used by BOTH the batch `geocode` management command and the admin per-stand
"Geocode now" button, so they obey identical rules:
- results are biased + bounded to the Big Island
- Nominatim's usage policy is max 1 request/second; a single ad-hoc lookup is
  well within it. Callers doing many lookups (the batch command) space their
  own calls out — this module does NOT sleep.
- ROAD-LEVEL / highway matches are REJECTED — a street centroid on a long rural
  road is worse than no pin (Matthew, 2026-06-11). Only place-level results
  (house/building/amenity...) are usable; the rest get a hand-placed pin.
- precedence is NOT decided here — callers choose whether to overwrite coords.
"""
import json
import urllib.error
import urllib.parse
import urllib.request

NOMINATIM_URL = 'https://nominatim.openstreetmap.org/search'
USER_AGENT = 'HiloBakeStands.com geocoder (matt@hilobakestands.com)'
# Big Island bounding box (lng1,lat1,lng2,lat2) to bias + bound results.
VIEWBOX = '-156.1,20.3,-154.7,18.8'


def queries_for(address):
    """Candidate query strings for an address. No street-only fallback — that
    can only produce road-level matches, which we reject anyway."""
    addr = (address or '').strip().rstrip('.,')
    if not addr:
        return []
    if 'hi' not in addr.lower() and 'hawaii' not in addr.lower():
        return [f'{addr}, Hawaii, USA']
    return [f'{addr}, USA']


def nominatim(query, timeout=10):
    params = urllib.parse.urlencode({
        'q': query, 'format': 'jsonv2', 'limit': 1, 'countrycodes': 'us',
        'viewbox': VIEWBOX, 'bounded': 1,
    })
    req = urllib.request.Request(f'{NOMINATIM_URL}?{params}',
                                 headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        results = json.load(resp)
    return results[0] if results else None


def geocode_address(address, timeout=10):
    """Best-effort single lookup. Never raises on network trouble — returns a
    status dict the caller can branch on:

        {'status': 'ok', 'lat': float, 'lon': float, 'precision': str}
        {'status': 'road_only', 'precision': str}   # rejected rough match
        {'status': 'no_match'}                       # nothing usable / no addr
        {'status': 'error', 'error': str}            # network/parse problem
    """
    queries = queries_for(address)
    if not queries:
        return {'status': 'no_match'}
    hit = None
    for query in queries:
        try:
            hit = nominatim(query, timeout=timeout)
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            return {'status': 'error', 'error': str(e)}
        if hit:
            break
    if not hit:
        return {'status': 'no_match'}
    precision = hit.get('addresstype') or hit.get('type', '')
    if hit.get('class') == 'highway' or precision == 'road':
        return {'status': 'road_only', 'precision': precision}
    return {'status': 'ok',
            'lat': round(float(hit['lat']), 6),
            'lon': round(float(hit['lon']), 6),
            'precision': precision}
