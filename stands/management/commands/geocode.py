"""Geocode stands that are missing coordinates, via OSM Nominatim.

Usage:
    python manage.py geocode [--all] [--dry-run]

- Only touches stands whose coords_source is blank or 'geocoded' — a pin
  placed by an admin or owner is NEVER overwritten by automation.
- By default only stands with no coordinates are geocoded; --all re-geocodes
  previously auto-geocoded stands too (e.g. after fixing an address).
- Respects the Nominatim usage policy: 1 request/second, descriptive
  User-Agent, results biased to the Big Island.
- Road-level matches are REJECTED (Matthew, 2026-06-11): a street centroid on
  a long rural road is worse than no pin — those stands get a hand-placed pin
  via the admin map widget instead. Only place-level results (house, building,
  amenity...) are saved; the result type lands in geocode_precision.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from django.core.management.base import BaseCommand
from django.utils import timezone

from stands.models import Stand

NOMINATIM_URL = 'https://nominatim.openstreetmap.org/search'
USER_AGENT = 'HiloBakeStands.com geocoder (matt@hilobakestands.com)'
# Big Island bounding box (lng1,lat1,lng2,lat2) to bias + bound results.
VIEWBOX = '-156.1,20.3,-154.7,18.8'


def nominatim(query):
    params = urllib.parse.urlencode({
        'q': query, 'format': 'jsonv2', 'limit': 1, 'countrycodes': 'us',
        'viewbox': VIEWBOX, 'bounded': 1,
    })
    req = urllib.request.Request(f'{NOMINATIM_URL}?{params}',
                                 headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(req, timeout=10) as resp:
        results = json.load(resp)
    return results[0] if results else None


class Command(BaseCommand):
    help = 'Geocode stands missing coordinates (Nominatim, never overwrites pins).'

    def add_arguments(self, parser):
        parser.add_argument('--all', action='store_true',
                            help='Also re-geocode stands whose coords came '
                                 'from a previous geocode run.')
        parser.add_argument('--dry-run', action='store_true',
                            help='Show what would happen without saving.')

    def queries_for(self, stand):
        """Candidate queries. No street-only fallback — that can only produce
        road-level matches, which we reject anyway."""
        addr = stand.street_address.strip().rstrip('.,')
        if not addr:
            return []
        if 'hi' not in addr.lower() and 'hawaii' not in addr.lower():
            return [f'{addr}, Hawaii, USA']
        return [f'{addr}, USA']

    def handle(self, *args, **opts):
        stands = Stand.objects.exclude(
            coords_source__in=[Stand.CoordsSource.OWNER_PIN,
                               Stand.CoordsSource.ADMIN])
        if not opts['all']:
            stands = stands.filter(latitude__isnull=True)

        done = failed = 0
        for stand in stands:
            hit = query = None
            for query in self.queries_for(stand):
                try:
                    hit = nominatim(query)
                except (urllib.error.URLError, TimeoutError, ValueError) as e:
                    self.stderr.write(f'  network error for {stand.name}: {e}')
                time.sleep(1.1)  # Nominatim policy: max 1 req/s
                if hit:
                    break
            if not hit:
                failed += 1
                self.stdout.write(self.style.WARNING(
                    f'NO MATCH  {stand.name!r}  addr={stand.street_address!r}'))
                continue

            precision = hit.get('addresstype') or hit.get('type', '')
            if hit.get('class') == 'highway' or precision == 'road':
                failed += 1
                self.stdout.write(self.style.WARNING(
                    f'ROAD ONLY (skipped)  {stand.name!r}  '
                    f'addr={stand.street_address!r} — place the pin by hand'))
                continue
            self.stdout.write(
                f'{precision:<12} {stand.name}: {hit["lat"]},{hit["lon"]}'
                f'  (query: {query})')
            if not opts['dry_run']:
                stand.latitude = round(float(hit['lat']), 6)
                stand.longitude = round(float(hit['lon']), 6)
                stand.coords_source = Stand.CoordsSource.GEOCODED
                stand.geocode_precision = precision[:30]
                stand.geocoded_at = timezone.now()
                stand.save(update_fields=[
                    'latitude', 'longitude', 'coords_source',
                    'geocode_precision', 'geocoded_at'])
            done += 1

        self.stdout.write(self.style.SUCCESS(
            f'Geocoded {done}, no match for {failed}.'
            f'{" (dry run — nothing saved)" if opts["dry_run"] else ""}'))
        if failed:
            self.stdout.write('Fix addresses or drag pins in the admin for '
                              'the unmatched stands.')
