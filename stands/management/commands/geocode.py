"""Geocode stands that are missing coordinates, via OSM Nominatim.

Usage:
    python manage.py geocode [--all] [--dry-run]

The lookup rules (Big-Island bias/bound, road-level rejection, query shaping)
live in stands/geocoding.py and are SHARED with the admin "Geocode now" button,
so the two can never drift apart. This command adds the batch-only concerns:
- only touches stands whose coords_source is blank or 'geocoded' — a pin placed
  by an admin or owner is NEVER overwritten by automation.
- by default only stands with no coordinates; --all re-geocodes previously
  auto-geocoded stands too (e.g. after fixing an address).
- spaces calls 1.1s apart to respect Nominatim's 1 req/s policy.
"""
import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from stands import geocoding
from stands.models import Stand


class Command(BaseCommand):
    help = 'Geocode stands missing coordinates (Nominatim, never overwrites pins).'

    def add_arguments(self, parser):
        parser.add_argument('--all', action='store_true',
                            help='Also re-geocode stands whose coords came '
                                 'from a previous geocode run.')
        parser.add_argument('--dry-run', action='store_true',
                            help='Show what would happen without saving.')

    def handle(self, *args, **opts):
        stands = Stand.objects.exclude(
            coords_source__in=[Stand.CoordsSource.OWNER_PIN,
                               Stand.CoordsSource.ADMIN])
        if not opts['all']:
            stands = stands.filter(latitude__isnull=True)

        done = failed = 0
        for stand in stands:
            result = geocoding.geocode_address(stand.street_address)
            time.sleep(1.1)  # Nominatim policy: max 1 req/s

            status = result['status']
            if status == 'error':
                failed += 1
                self.stderr.write(
                    f'  network error for {stand.name}: {result["error"]}')
                continue
            if status == 'no_match':
                failed += 1
                self.stdout.write(self.style.WARNING(
                    f'NO MATCH  {stand.name!r}  addr={stand.street_address!r}'))
                continue
            if status == 'road_only':
                failed += 1
                self.stdout.write(self.style.WARNING(
                    f'ROAD ONLY (skipped)  {stand.name!r}  '
                    f'addr={stand.street_address!r} — place the pin by hand'))
                continue

            # status == 'ok'
            self.stdout.write(
                f'{result["precision"]:<12} {stand.name}: '
                f'{result["lat"]},{result["lon"]}')
            if not opts['dry_run']:
                stand.latitude = result['lat']
                stand.longitude = result['lon']
                stand.coords_source = Stand.CoordsSource.GEOCODED
                stand.geocode_precision = result['precision'][:30]
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
