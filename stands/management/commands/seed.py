"""Seed reference data + the example stand from listings.xlsx. Idempotent."""
import datetime

from django.core.management.base import BaseCommand

from stands.models import Category, PaymentMethod, Stand, WeeklyHours


class Command(BaseCommand):
    help = 'Seed payment methods, starter categories, and the example stand.'

    def handle(self, *args, **options):
        for i, name in enumerate(['Cash', 'PayPal', 'Venmo', 'CashApp', 'Credit card']):
            PaymentMethod.objects.get_or_create(name=name, defaults={'sort_order': i})

        for name in ['Baked goods', 'Plate lunch', 'Shave ice', 'Mochi',
                     'Produce', 'Coffee', 'Lilikoi']:
            Category.objects.get_or_create(name=name)

        stand, created = Stand.objects.get_or_create(
            slug='auntie-lehuas-lilikoi-stand',
            defaults=dict(
                name="Auntie Lehua's Lilikoi Stand",
                location_type=Stand.LocationType.BAKE_STAND,
                description=('EXAMPLE LISTING — replace with real data. Honor stand '
                             'with lilikoi butter mochi, banana bread, and seasonal '
                             'lilikoi bars. Family recipe since the 80s.'),
                street_address='1234 Kaumana Dr, Hilo, HI 96720',
                latitude='19.707400', longitude='-155.120800',
                attendance=Stand.Attendance.UNATTENDED,
                irregular_hours_note='Stocked until sold out — often gone by noon',
                instagram='@auntielehuabakes',
                status=Stand.Status.PUBLISHED,
                # Seed/admin path is trusted → verified (only public submissions
                # stay at the unverified model default).
                verification=Stand.Verification.VERIFIED,
                created_via=Stand.CreatedVia.ADMIN_SEED,
                verified_via=Stand.VerifiedVia.ADMIN,
            ))
        if created:
            stand.categories.set(Category.objects.filter(
                name__in=['Baked goods', 'Mochi', 'Lilikoi']))
            stand.payment_methods.set(PaymentMethod.objects.filter(
                name__in=['Cash', 'Venmo']))
            for weekday, open_t, close_t in [
                (4, datetime.time(7), datetime.time(14)),   # Fri
                (5, datetime.time(7), datetime.time(14)),   # Sat
                (6, datetime.time(8), datetime.time(12)),   # Sun
            ]:
                WeeklyHours.objects.create(
                    stand=stand, weekday=weekday, open_time=open_t, close_time=close_t)
            self.stdout.write(self.style.SUCCESS('Seeded example stand.'))
        else:
            self.stdout.write('Example stand already present; reference data refreshed.')
