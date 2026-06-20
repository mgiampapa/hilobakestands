import datetime
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import DayOverride, Stand, WeeklyHours


def make_stand(**kw):
    # A normal published stand is verified post-Slice-0 (admin/seed/import path);
    # tests that want a community submission pass verification=... explicitly.
    defaults = dict(name='Test Stand', location_type=Stand.LocationType.BAKE_STAND,
                    status=Stand.Status.PUBLISHED,
                    verification=Stand.Verification.VERIFIED,
                    latitude='19.700000', longitude='-155.100000')
    defaults.update(kw)
    return Stand.objects.create(**defaults)


class OpenNowTests(TestCase):
    def setUp(self):
        self.stand = make_stand()
        now = timezone.localtime()
        WeeklyHours.objects.create(
            stand=self.stand, weekday=now.weekday(),
            open_time=datetime.time(0, 0), close_time=datetime.time(23, 59))

    def test_open_via_weekly_schedule(self):
        self.assertTrue(self.stand.is_open_now())

    def test_closed_override_beats_schedule(self):
        DayOverride.objects.create(stand=self.stand, is_open=False, note='Out of mochi')
        self.assertFalse(self.stand.is_open_now())

    def test_open_override_without_times_means_open(self):
        other = make_stand(name='No Schedule Stand', slug='no-schedule')
        DayOverride.objects.create(stand=other, is_open=True)
        self.assertTrue(other.is_open_now())


class PageTests(TestCase):
    def setUp(self):
        self.stand = make_stand()

    def test_list_page(self):
        r = self.client.get(reverse('stand_list'))
        self.assertContains(r, 'Test Stand')

    def test_list_filter_excludes_drafts(self):
        make_stand(name='Hidden', slug='hidden', status=Stand.Status.DRAFT)
        r = self.client.get(reverse('stand_list'))
        self.assertNotContains(r, 'Hidden')

    def test_detail_page_has_directions(self):
        r = self.client.get(self.stand.get_absolute_url())
        self.assertContains(r, 'google.com/maps')
        self.assertContains(r, 'maps.apple.com')
        self.assertContains(r, 'waze.com')
        self.assertContains(r, 'openstreetmap.org')

    def test_report_lowers_validation_score(self):
        r = self.client.post(reverse('stand_report', args=[self.stand.slug]),
                             {'message': 'They moved down the road'})
        self.stand.refresh_from_db()
        self.assertEqual(self.stand.validation_score, 90)
        self.assertEqual(self.stand.reports.count(), 1)

    def test_report_honeypot_blocks_spam(self):
        self.client.post(reverse('stand_report', args=[self.stand.slug]),
                         {'message': 'spam', 'website_url': 'http://spam.example'})
        self.assertEqual(self.stand.reports.count(), 0)

    def test_report_emails_admins(self):
        from django.core import mail
        self.client.post(reverse('stand_report', args=[self.stand.slug]),
                         {'message': 'Closed for good', 'contact': '808-555-1234'})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Test Stand', mail.outbox[0].subject)
        self.assertIn('Closed for good', mail.outbox[0].body)
        self.assertIn('/admin/stands/report/', mail.outbox[0].body)

    def test_report_blocked_when_turnstile_fails(self):
        with mock.patch('stands.views.turnstile_ok', return_value=False):
            r = self.client.post(reverse('stand_report', args=[self.stand.slug]),
                                 {'message': 'bot says hi'}, follow=True)
        self.assertEqual(self.stand.reports.count(), 0)
        self.assertContains(r, 'Verification failed')

    def test_turnstile_skipped_without_secret(self):
        # No TURNSTILE_SECRET_KEY in test env → verification passes untouched.
        from stands.views import turnstile_ok
        self.assertTrue(turnstile_ok(mock.Mock()))

    def test_turnstile_fails_open_on_network_error(self):
        from django.test import override_settings
        import urllib.error
        with override_settings(TURNSTILE_SECRET_KEY='x'):
            with mock.patch('stands.views.urllib.request.urlopen',
                            side_effect=urllib.error.URLError('down')):
                from stands.views import turnstile_ok
                req = mock.Mock()
                req.POST = {}
                req.META = {}
                self.assertTrue(turnstile_ok(req))

    def test_turnstile_rejects_invalid_token(self):
        from django.test import override_settings
        from unittest.mock import MagicMock
        body = MagicMock()
        body.__enter__ = lambda s: s
        body.__exit__ = lambda s, *a: False
        body.read = lambda: b'{"success": false}'
        with override_settings(TURNSTILE_SECRET_KEY='x'):
            with mock.patch('stands.views.urllib.request.urlopen',
                            return_value=body):
                from stands.views import turnstile_ok
                req = mock.Mock()
                req.POST = {'cf-turnstile-response': 'bad'}
                req.META = {}
                self.assertFalse(turnstile_ok(req))

    def test_admin_loads(self):
        from django.contrib.auth.models import User
        User.objects.create_superuser('admin', 'a@b.c', 'pw')
        self.client.login(username='admin', password='pw')
        r = self.client.get('/admin/stands/stand/')
        self.assertEqual(r.status_code, 200)


class ImportListingsTests(TestCase):
    """import_listings must never clobber existing (admin-edited) stands."""

    def _sheet(self, tmpdir, description='From sheet', hours_mon='7am-2pm'):
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = 'Listings'
        ws.append(['Name', 'Location Type', 'Description / What They Sell',
                   'Hours Mon'])
        ws.append(['Aloha Stand', 'bake stand', description, hours_mon])
        path = f'{tmpdir}/listings.xlsx'
        wb.save(path)
        return path

    def test_creates_new_stand_as_draft(self):
        import tempfile
        from django.core.management import call_command
        with tempfile.TemporaryDirectory() as d:
            call_command('import_listings', self._sheet(d))
        stand = Stand.objects.get(slug='aloha-stand')
        self.assertEqual(stand.status, Stand.Status.DRAFT)
        # Import is a trusted admin path → verified (Slice 0).
        self.assertEqual(stand.verification, Stand.Verification.VERIFIED)
        self.assertEqual(stand.created_via, Stand.CreatedVia.ADMIN_SEED)
        self.assertEqual(stand.weekly_hours.count(), 1)

    def test_reimport_leaves_existing_stand_untouched(self):
        import tempfile
        from django.core.management import call_command
        with tempfile.TemporaryDirectory() as d:
            path = self._sheet(d)
            call_command('import_listings', path)
            # Simulate admin edits: publish, fix description, change hours.
            stand = Stand.objects.get(slug='aloha-stand')
            stand.status = Stand.Status.PUBLISHED
            stand.description = 'Admin-edited description'
            stand.save()
            stand.weekly_hours.all().delete()
            WeeklyHours.objects.create(
                stand=stand, weekday=5,
                open_time=datetime.time(8, 0), close_time=datetime.time(12, 0))
            call_command('import_listings', path)  # re-run, e.g. via bootstrap
        stand.refresh_from_db()
        self.assertEqual(stand.status, Stand.Status.PUBLISHED)
        self.assertEqual(stand.description, 'Admin-edited description')
        self.assertEqual(stand.weekly_hours.count(), 1)
        self.assertEqual(stand.weekly_hours.first().weekday, 5)

    def test_overwrite_flag_restores_sheet_values(self):
        import tempfile
        from django.core.management import call_command
        with tempfile.TemporaryDirectory() as d:
            path = self._sheet(d)
            call_command('import_listings', path)
            stand = Stand.objects.get(slug='aloha-stand')
            stand.description = 'Admin-edited description'
            stand.save()
            call_command('import_listings', path, '--overwrite')
        stand.refresh_from_db()
        self.assertEqual(stand.description, 'From sheet')


class VerificationTests(TestCase):
    """Slice 0: verification + provenance fields (v1.1)."""

    def test_new_stand_defaults_unverified(self):
        # Fail-safe: a plain new stand is UNVERIFIED until a trusted path acts.
        s = Stand.objects.create(
            name='Mystery Mochi', location_type=Stand.LocationType.BAKE_STAND)
        self.assertEqual(s.verification, Stand.Verification.UNVERIFIED)
        self.assertEqual(s.created_via, Stand.CreatedVia.ADMIN_SEED)
        self.assertFalse(s.auto_hidden)
        self.assertIsNone(s.verified_at)

    def test_mark_verified_helper(self):
        s = Stand.objects.create(
            name='Pau Hana Pops', location_type=Stand.LocationType.POPUP)
        s.mark_verified(via=Stand.VerifiedVia.CLAIM)
        s.refresh_from_db()
        self.assertEqual(s.verification, Stand.Verification.VERIFIED)
        self.assertEqual(s.verified_via, Stand.VerifiedVia.CLAIM)
        self.assertIsNotNone(s.verified_at)

    def test_admin_mark_verified_action(self):
        from django.contrib.admin.sites import AdminSite
        from stands.admin import StandAdmin
        s = Stand.objects.create(
            name='Queue Me', location_type=Stand.LocationType.BAKE_STAND)
        admin_obj = StandAdmin(Stand, AdminSite())
        admin_obj.message_user = mock.Mock()
        admin_obj.mark_verified(mock.Mock(), Stand.objects.filter(pk=s.pk))
        s.refresh_from_db()
        self.assertEqual(s.verification, Stand.Verification.VERIFIED)
        self.assertEqual(s.verified_via, Stand.VerifiedVia.ADMIN)
        self.assertIsNotNone(s.verified_at)


class VerifiedFilteringTests(TestCase):
    """Slice 1: verified-only default, community toggle, unverified badge."""

    def setUp(self):
        self.verified = Stand.objects.create(
            name='Verified Stand', location_type=Stand.LocationType.BAKE_STAND,
            status=Stand.Status.PUBLISHED, latitude='19.70', longitude='-155.08',
            verification=Stand.Verification.VERIFIED)
        self.unverified = Stand.objects.create(
            name='Community Stand', location_type=Stand.LocationType.POPUP,
            status=Stand.Status.PUBLISHED, latitude='19.71', longitude='-155.09',
            verification=Stand.Verification.UNVERIFIED)

    def test_list_defaults_to_verified_only(self):
        r = self.client.get(reverse('stand_list'))
        self.assertContains(r, 'Verified Stand')
        self.assertNotContains(r, 'Community Stand')

    def test_list_community_param_includes_unverified_with_badge(self):
        r = self.client.get(reverse('stand_list'), {'community': '1'})
        self.assertContains(r, 'Verified Stand')
        self.assertContains(r, 'Community Stand')
        self.assertContains(r, 'badge unverified')  # the badge (not the pill)

    def test_map_defaults_to_verified_only(self):
        r = self.client.get(reverse('stand_map'))
        self.assertContains(r, 'Verified Stand')   # in marker JSON
        self.assertNotContains(r, 'Community Stand')

    def test_unverified_detail_viewable_with_badge(self):
        r = self.client.get(self.unverified.get_absolute_url())
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Unverified')

    def test_auto_hidden_stand_404s_and_drops_from_list(self):
        self.unverified.auto_hidden = True
        self.unverified.save(update_fields=['auto_hidden'])
        self.assertEqual(
            self.client.get(self.unverified.get_absolute_url()).status_code, 404)
        r = self.client.get(reverse('stand_list'), {'community': '1'})
        self.assertNotContains(r, 'Community Stand')


class SubmitStandTests(TestCase):
    """Slice 2a: public submission form, create-as-unverified, notify."""

    def _user(self):
        from django.contrib.auth import get_user_model
        return get_user_model().objects.create_user(
            username='lani', email='lani@example.com', first_name='Lani')

    def test_anonymous_sees_signin_not_form(self):
        r = self.client.get(reverse('submit_stand'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Sign in with Google')
        self.assertNotContains(r, 'Stand name')

    def test_authenticated_sees_form(self):
        self.client.force_login(self._user())
        self.assertContains(self.client.get(reverse('submit_stand')), 'Stand name')

    def test_submit_creates_unverified_community_stand_and_notifies(self):
        from django.core import mail
        user = self._user()
        self.client.force_login(user)
        r = self.client.post(reverse('submit_stand'), {
            'name': 'Lani Lilikoi', 'location_type': 'bake_stand',
            'description': 'Lilikoi bars', 'street_address': '1 Main St, Hilo',
            'attendance': 'attended',
            'instagram': 'https://instagram.com/lanibakes'})
        stand = Stand.objects.get(name='Lani Lilikoi')
        self.assertRedirects(r, stand.get_absolute_url())
        self.assertEqual(stand.verification, Stand.Verification.UNVERIFIED)
        self.assertEqual(stand.created_via, Stand.CreatedVia.PUBLIC_SUBMIT)
        self.assertEqual(stand.created_by, user)
        self.assertEqual(stand.status, Stand.Status.PUBLISHED)
        self.assertIsNotNone(stand.submitted_at)
        self.assertTrue(stand.claim_token)                 # claim link minted
        self.assertEqual(stand.instagram, 'lanibakes')     # sanitized via mixin
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Lani Lilikoi', mail.outbox[0].subject)

    def test_submission_hidden_by_default_shown_with_community(self):
        self.client.force_login(self._user())
        # follow=True so the success flash is consumed on the detail page and
        # doesn't bleed into the next list render.
        self.client.post(reverse('submit_stand'), {
            'name': 'Hidden Gem', 'location_type': 'popup',
            'description': 'x', 'attendance': 'attended'}, follow=True)
        self.assertNotContains(self.client.get(reverse('stand_list')), 'Hidden Gem')
        self.assertContains(
            self.client.get(reverse('stand_list'), {'community': '1'}), 'Hidden Gem')

    def test_anonymous_post_creates_nothing(self):
        self.client.post(reverse('submit_stand'), {
            'name': 'Nope', 'location_type': 'popup', 'attendance': 'attended'})
        self.assertFalse(Stand.objects.filter(name='Nope').exists())

    def test_submitted_stand_claimable_via_minted_token_becomes_verified(self):
        # End-to-end Slice 2 -> Slice 3: a public submission mints a claim
        # token; the real operator (a DIFFERENT user from the submitter) claims
        # it with that token and the stand flips unverified -> verified and
        # appears in the default verified-only list.
        from django.contrib.auth import get_user_model
        self.client.force_login(self._user())
        self.client.post(reverse('submit_stand'), {
            'name': 'Loop Stand', 'location_type': 'popup',
            'description': 'malasadas', 'attendance': 'attended'}, follow=True)
        stand = Stand.objects.get(name='Loop Stand')
        token = stand.claim_token
        self.assertTrue(token)
        self.assertEqual(stand.verification, Stand.Verification.UNVERIFIED)
        self.assertNotContains(self.client.get(reverse('stand_list')), 'Loop Stand')

        operator = get_user_model().objects.create_user(
            username='operator', email='op@example.com')
        self.client.force_login(operator)
        self.client.post(reverse('stand_claim', args=[token]))
        stand.refresh_from_db()
        self.assertEqual(stand.owner, operator)            # submitter != owner
        self.assertEqual(stand.verification, Stand.Verification.VERIFIED)
        self.assertEqual(stand.verified_via, Stand.VerifiedVia.CLAIM)
        self.assertIsNone(stand.claim_token)               # token burned
        self.assertContains(self.client.get(reverse('stand_list')), 'Loop Stand')

    @mock.patch('stands.forms.url_domain_blocked', return_value=False)
    def test_bare_domain_website_gets_http_scheme(self, _block):
        self.client.force_login(self._user())
        self.client.post(reverse('submit_stand'), {
            'name': 'Web Stand', 'location_type': 'popup',
            'attendance': 'attended',
            'website': 'awesomesauce.com/bakedgoods'}, follow=True)
        stand = Stand.objects.get(name='Web Stand')
        self.assertEqual(stand.website, 'http://awesomesauce.com/bakedgoods')

    @mock.patch('stands.forms.url_domain_blocked', return_value=True)
    def test_blocked_website_rejected(self, _block):
        self.client.force_login(self._user())
        r = self.client.post(reverse('submit_stand'), {
            'name': 'Sketchy', 'location_type': 'popup',
            'attendance': 'attended', 'website': 'badsite.example'})
        self.assertFalse(Stand.objects.filter(name='Sketchy').exists())
        self.assertContains(r, 'adult or unsafe')

    def test_pin_saved_as_owner_pin(self):
        self.client.force_login(self._user())
        self.client.post(reverse('submit_stand'), {
            'name': 'Pinned', 'location_type': 'popup', 'attendance': 'attended',
            'latitude': '19.710000', 'longitude': '-155.090000'}, follow=True)
        s = Stand.objects.get(name='Pinned')
        self.assertEqual(float(s.latitude), 19.71)
        self.assertEqual(s.coords_source, Stand.CoordsSource.OWNER_PIN)

    def test_off_island_pin_rejected(self):
        self.client.force_login(self._user())
        r = self.client.post(reverse('submit_stand'), {
            'name': 'Mainland', 'location_type': 'popup',
            'attendance': 'attended',
            'latitude': '34.05', 'longitude': '-118.24'})  # Los Angeles
        self.assertFalse(Stand.objects.filter(name='Mainland').exists())
        self.assertContains(r, 'Big Island')

    def test_proximity_warning_then_confirm(self):
        make_stand(name='Existing', latitude='19.710000', longitude='-155.090000')
        self.client.force_login(self._user())
        data = {'name': 'Maybe Dup', 'location_type': 'popup',
                'attendance': 'attended',
                'latitude': '19.710001', 'longitude': '-155.090001'}
        r = self.client.post(reverse('submit_stand'), data)
        self.assertContains(r, 'within 25')                          # warned
        self.assertFalse(Stand.objects.filter(name='Maybe Dup').exists())
        data['confirm_duplicate'] = '1'
        self.client.post(reverse('submit_stand'), data, follow=True)
        self.assertTrue(Stand.objects.filter(name='Maybe Dup').exists())  # created

    def test_denylist_rejects_threat_in_address(self):
        self.client.force_login(self._user())
        r = self.client.post(reverse('submit_stand'), {
            'name': 'Sneaky Stand', 'location_type': 'popup',
            'attendance': 'attended',
            'street_address': 'behind the store — I will kill you'})
        self.assertFalse(Stand.objects.filter(name='Sneaky Stand').exists())
        self.assertContains(r, 'Please revise')

    def test_denylist_rejects_threat_in_name(self):
        self.client.force_login(self._user())
        r = self.client.post(reverse('submit_stand'), {
            'name': 'death to everyone', 'location_type': 'popup',
            'attendance': 'attended'})
        self.assertFalse(Stand.objects.filter(name__icontains='death').exists())
        self.assertContains(r, 'Please revise')

    def test_honeypot_silently_drops(self):
        self.client.force_login(self._user())
        r = self.client.post(reverse('submit_stand'), {
            'name': 'Bot Stand', 'location_type': 'popup',
            'attendance': 'attended',
            'website_url': 'http://spam.example'})  # honeypot filled
        self.assertFalse(Stand.objects.filter(name='Bot Stand').exists())
        self.assertEqual(r.status_code, 302)  # silent redirect, no error shown

    def test_rate_limit_after_five_per_day(self):
        user = self._user()
        self.client.force_login(user)
        for i in range(5):
            self.client.post(reverse('submit_stand'), {
                'name': f'Stand {i}', 'location_type': 'popup',
                'attendance': 'attended'}, follow=True)
        self.assertEqual(Stand.objects.filter(created_by=user).count(), 5)
        r = self.client.post(reverse('submit_stand'), {
            'name': 'Sixth', 'location_type': 'popup', 'attendance': 'attended'})
        self.assertFalse(Stand.objects.filter(name='Sixth').exists())
        self.assertContains(r, 'come back tomorrow')


class UrlSafetyCheckTests(TestCase):
    """url_domain_blocked parses the Cloudflare '1.1.1.3 for Families' DoH
    response — exercised against the real JSON shapes Cloudflare returns."""

    def _doh(self, payload):
        import io
        import json as _json
        cm = mock.MagicMock()
        cm.__enter__.return_value = io.BytesIO(_json.dumps(payload).encode())
        return cm

    @mock.patch('stands.forms.urllib.request.urlopen')
    def test_blocked_domain_detected(self, urlopen):
        from stands.forms import url_domain_blocked
        urlopen.return_value = self._doh({
            'Status': 0,
            'Answer': [{'name': 'x', 'type': 1, 'TTL': 60, 'data': '0.0.0.0'}],
            'Comment': ['EDE(17): Filtered']})
        self.assertTrue(url_domain_blocked('http://badsite.example/path'))

    @mock.patch('stands.forms.urllib.request.urlopen')
    def test_normal_domain_allowed(self, urlopen):
        from stands.forms import url_domain_blocked
        urlopen.return_value = self._doh({
            'Status': 0,
            'Answer': [{'name': 'example.com', 'type': 1, 'TTL': 231,
                        'data': '172.66.147.243'}]})
        self.assertFalse(url_domain_blocked('http://example.com'))

    @mock.patch('stands.forms.urllib.request.urlopen')
    def test_network_error_fails_open(self, urlopen):
        import urllib.error
        from stands.forms import url_domain_blocked
        urlopen.side_effect = urllib.error.URLError('boom')
        self.assertFalse(url_domain_blocked('http://example.com'))


class TextModerationTests(TestCase):
    """The denylist/threat filter (textmod) — must catch clear abuse but NOT
    flag legitimate food/local words (whole-word match + curated list)."""

    def test_blocks_obscenity_slur_and_threat(self):
        from stands.textmod import text_blocked
        self.assertTrue(text_blocked('this fucking nonsense'))
        self.assertTrue(text_blocked('you absolute bitch'))
        self.assertTrue(text_blocked('I will kill you'))     # threat regex
        self.assertTrue(text_blocked('death to them all'))   # threat regex

    def test_allows_food_and_legit_words(self):
        from stands.textmod import text_blocked
        for ok in ['Smoked pork butt', 'Crispy chicken breast',
                   'Sex on the Beach shave ice', "Dick's Drive-In",
                   'Garlic shrimp truck', 'A real class act',
                   'Scunthorpe Bakery', 'Grass-fed beef', 'Cornhole Fridays',
                   'Assorted malasadas', 'Coconut balls', 'Loco moco',
                   'Pūpū platter', 'Kaʻū coffee']:   # Hawaiian diacriticals
            self.assertFalse(text_blocked(ok), f'wrongly flagged: {ok!r}')

    def test_normalize_folds_hawaiian_diacriticals(self):
        from stands.textmod import _normalize
        self.assertEqual(_normalize('pūpū'), 'pupu')        # kahakō stripped
        self.assertEqual(_normalize('Kaʻū'.lower()), 'kau')  # ʻokina + macron

    def test_matching_is_diacritical_insensitive(self):
        # A plain-ASCII denylist term must match diacritical input (and vice
        # versa). Uses a benign word as a stand-in for a Hawaiian slur.
        from stands import textmod
        pat = textmod._compile(['pupu'])
        self.assertTrue(pat.search(textmod._normalize('fresh pūpū today')))
        self.assertTrue(pat.search(textmod._normalize('fresh pupu today')))


class MapViewTests(TestCase):
    def setUp(self):
        self.located = make_stand()  # has coords from make_stand defaults
        self.unlocated = make_stand(name='No Coords Stand', slug='no-coords',
                                    latitude=None, longitude=None)

    def test_map_page_renders_markers_and_unmapped(self):
        r = self.client.get(reverse('stand_map'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.context['markers']), 1)
        self.assertEqual(r.context['markers'][0]['name'], 'Test Stand')
        self.assertEqual([s.name for s in r.context['unmapped']],
                         ['No Coords Stand'])

    def test_map_respects_filters(self):
        truck = make_stand(name='Truck', slug='truck',
                           location_type=Stand.LocationType.FOOD_TRUCK)
        r = self.client.get(reverse('stand_map'), {'type': 'food_truck'})
        self.assertEqual([m['name'] for m in r.context['markers']], ['Truck'])

    def test_map_excludes_drafts(self):
        make_stand(name='Draft Stand', slug='draft-stand',
                   status=Stand.Status.DRAFT)
        r = self.client.get(reverse('stand_map'))
        names = [m['name'] for m in r.context['markers']]
        self.assertNotIn('Draft Stand', names)


class GeocodeCommandTests(TestCase):
    def _fake_hit(self, addresstype='house', cls='place'):
        return {'lat': '19.71', 'lon': '-155.08',
                'addresstype': addresstype, 'class': cls}

    def test_geocodes_stand_without_coords(self):
        from django.core.management import call_command
        s = make_stand(latitude=None, longitude=None,
                       street_address='123 Test St')
        with mock.patch('stands.geocoding.nominatim',
                        return_value=self._fake_hit()), \
             mock.patch('stands.management.commands.geocode.time.sleep'):
            call_command('geocode')
        s.refresh_from_db()
        self.assertEqual(float(s.latitude), 19.71)
        self.assertEqual(s.coords_source, Stand.CoordsSource.GEOCODED)
        self.assertEqual(s.geocode_precision, 'house')

    def test_never_overwrites_human_pin(self):
        from django.core.management import call_command
        s = make_stand(street_address='123 Test St',
                       coords_source=Stand.CoordsSource.ADMIN)
        orig = s.latitude
        with mock.patch('stands.geocoding.nominatim',
                        return_value=self._fake_hit()) as fake, \
             mock.patch('stands.management.commands.geocode.time.sleep'):
            call_command('geocode', '--all')
        s.refresh_from_db()
        self.assertEqual(float(s.latitude), float(orig))
        fake.assert_not_called()

    def test_road_level_match_is_rejected(self):
        from django.core.management import call_command
        s = make_stand(latitude=None, longitude=None,
                       street_address='Hoaloha st')
        with mock.patch('stands.geocoding.nominatim',
                        return_value=self._fake_hit('road', 'highway')), \
             mock.patch('stands.management.commands.geocode.time.sleep'):
            call_command('geocode')
        s.refresh_from_db()
        self.assertIsNone(s.latitude)
        self.assertEqual(s.coords_source, '')


class AuthHeaderTests(TestCase):
    """Header sign-in/sign-out controls (base.html)."""

    def test_anonymous_sees_sign_in_button(self):
        r = self.client.get(reverse('stand_list'))
        self.assertContains(r, 'Sign in')
        # POSTs straight to the Google provider, skipping the interstitial
        self.assertContains(r, '/accounts/google/login/')

    def test_authenticated_sees_name_and_sign_out(self):
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create_user(
            username='lani', first_name='Lani', email='lani@example.com')
        self.client.force_login(user)
        r = self.client.get(reverse('stand_list'))
        self.assertContains(r, 'Aloha, Lani')
        self.assertContains(r, 'Sign out')
        self.assertContains(r, reverse('account_logout'))

    def test_sign_out_logs_out(self):
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create_user(username='lani')
        self.client.force_login(user)
        r = self.client.post(reverse('account_logout'))
        self.assertEqual(r.status_code, 302)
        r = self.client.get(reverse('stand_list'))
        self.assertContains(r, 'Sign in')

    def test_login_display_prefers_name_over_lowercase_username(self):
        # Regression: allauth's post-login flash ("signed in as …") defaulted
        # to the auto-generated, lowercased username; ACCOUNT_USER_DISPLAY must
        # show the proper-cased OAuth name instead.
        from django.contrib.auth import get_user_model
        from allauth.account.utils import user_display
        User = get_user_model()
        named = User.objects.create_user(username='matt', first_name='Matthew')
        self.assertEqual(user_display(named), 'Matthew')
        # no first name → email, still never the lowercased username
        emailed = User.objects.create_user(username='kimo', email='kimo@example.com')
        self.assertEqual(user_display(emailed), 'kimo@example.com')

    def test_user_stringifies_by_email_for_admin(self):
        # str(user) is what the admin renders for FK columns / readonly fields /
        # select widgets; it must show the email identity, not the lowercased
        # auto-username (patched in stands/apps.py).
        from django.contrib.auth import get_user_model
        User = get_user_model()
        u = User.objects.create_user(
            username='matthew', email='matt@giampapa.com', first_name='Matthew')
        self.assertEqual(str(u), 'matt@giampapa.com')
        # no email → falls back to a non-empty label (never blank)
        nameless = User.objects.create_user(username='kimo')
        self.assertEqual(str(nameless), 'kimo')


class ClaimFlowTests(TestCase):
    """QR/SMS one-time claim tokens (/claim/<token>/)."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        self.User = get_user_model()
        self.stand = make_stand()
        self.token = self.stand.generate_claim_token()
        self.stand.save()

    def claim_url(self):
        return reverse('stand_claim', args=[self.token])

    def test_anonymous_sees_google_signin_with_next(self):
        r = self.client.get(self.claim_url())
        self.assertContains(r, 'Sign in with Google to claim')
        self.assertContains(r, '/accounts/google/login/')
        from urllib.parse import quote
        # next= brings the baker straight back here after Google
        self.assertContains(r, 'next=' + quote(self.claim_url(), safe=''))

    def test_authenticated_sees_confirm_button(self):
        user = self.User.objects.create_user(username='baker', email='b@x.com')
        self.client.force_login(user)
        r = self.client.get(self.claim_url())
        self.assertContains(r, 'claim it')

    def test_claim_links_owner_and_burns_token(self):
        user = self.User.objects.create_user(username='baker', email='b@x.com')
        self.client.force_login(user)
        r = self.client.post(self.claim_url())
        self.assertRedirects(r, self.stand.get_absolute_url())
        self.stand.refresh_from_db()
        self.assertEqual(self.stand.owner, user)
        self.assertIsNone(self.stand.claim_token)
        self.assertIsNotNone(self.stand.claimed_at)
        # token is one-time: the old URL is dead
        self.assertEqual(self.client.get(self.claim_url()).status_code, 404)

    def test_claim_verifies_stand(self):
        # SPEC-1.1 §6: completing a claim flips unverified -> verified.
        self.stand.verification = Stand.Verification.UNVERIFIED
        self.stand.verified_via = ''
        self.stand.verified_at = None
        self.stand.save(update_fields=['verification', 'verified_via',
                                       'verified_at'])
        user = self.User.objects.create_user(username='baker2', email='b2@x.com')
        self.client.force_login(user)
        self.client.post(self.claim_url())
        self.stand.refresh_from_db()
        self.assertEqual(self.stand.verification, Stand.Verification.VERIFIED)
        self.assertEqual(self.stand.verified_via, Stand.VerifiedVia.CLAIM)
        self.assertIsNotNone(self.stand.verified_at)

    def test_anonymous_post_does_not_claim(self):
        self.client.post(self.claim_url())
        self.stand.refresh_from_db()
        self.assertIsNone(self.stand.owner)
        self.assertEqual(self.stand.claim_token, self.token)

    def test_invalid_token_branded_404(self):
        r = self.client.get(reverse('stand_claim', args=['nope']))
        self.assertEqual(r.status_code, 404)
        self.assertContains(r, 'already been used', status_code=404)
        self.assertContains(r, 'HiloBakeStands', status_code=404)  # header

    def test_used_token_branded_404(self):
        user = self.User.objects.create_user(username='baker9')
        self.client.force_login(user)
        self.client.post(self.claim_url())
        self.client.logout()
        r = self.client.get(self.claim_url())
        self.assertContains(r, 'already been used', status_code=404)

    def test_site_404_is_branded(self):
        r = self.client.get('/stand/never-existed/')
        self.assertEqual(r.status_code, 404)

    def test_admin_action_generates_tokens_skips_owned(self):
        from django.contrib.auth import get_user_model
        admin_user = self.User.objects.create_superuser(
            username='boss', email='boss@x.com', password='pw')
        owner = self.User.objects.create_user(username='o', email='o@x.com')
        fresh = make_stand(name='Fresh', slug='fresh')
        owned = make_stand(name='Owned', slug='owned')
        owned.owner = owner
        owned.save()
        self.client.force_login(admin_user)
        self.client.post('/admin/stands/stand/', {
            'action': 'generate_claim_tokens',
            '_selected_action': [fresh.pk, owned.pk]})
        fresh.refresh_from_db(); owned.refresh_from_db()
        self.assertTrue(fresh.claim_token)
        self.assertIsNone(owned.claim_token)

    def test_admin_single_generate_button(self):
        admin_user = self.User.objects.create_superuser(
            username='boss2', email='boss2@x.com', password='pw')
        fresh = make_stand(name='Solo', slug='solo')
        self.client.force_login(admin_user)
        r = self.client.get(
            f'/admin/stands/stand/{fresh.pk}/generate-claim-token/')
        self.assertEqual(r.status_code, 302)
        fresh.refresh_from_db()
        self.assertTrue(fresh.claim_token)
        # owned stands refuse
        r = self.client.get(
            f'/admin/stands/stand/{self.stand.pk}/generate-claim-token/')
        owner = self.User.objects.create_user(username='own2')
        self.stand.owner = owner
        self.stand.claim_token = None
        self.stand.save()
        self.client.get(
            f'/admin/stands/stand/{self.stand.pk}/generate-claim-token/')
        self.stand.refresh_from_db()
        self.assertIsNone(self.stand.claim_token)


class ClaimFlyerTests(TestCase):
    """QR flyer PDFs from admin (single + bulk)."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        self.User = get_user_model()
        self.admin = self.User.objects.create_superuser(
            username='boss3', email='boss3@x.com', password='pw')
        self.client.force_login(self.admin)

    def test_single_flyer_generates_token_and_pdf(self):
        s = make_stand(name='Flyer Stand', slug='flyer-stand')
        r = self.client.get(f'/admin/stands/stand/{s.pk}/claim-flyer/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'application/pdf')
        self.assertTrue(r.content.startswith(b'%PDF'))
        s.refresh_from_db()
        self.assertTrue(s.claim_token)  # auto-generated

    def test_single_flyer_keeps_existing_token(self):
        s = make_stand(name='Tokened', slug='tokened')
        tok = s.generate_claim_token(); s.save()
        self.client.get(f'/admin/stands/stand/{s.pk}/claim-flyer/')
        s.refresh_from_db()
        self.assertEqual(s.claim_token, tok)  # not rotated

    def test_bulk_flyers_skip_owned(self):
        owner = self.User.objects.create_user(username='ow3')
        a = make_stand(name='A Stand', slug='a-stand')
        b = make_stand(name='B Stand', slug='b-stand')
        b.owner = owner; b.save()
        r = self.client.post('/admin/stands/stand/', {
            'action': 'download_claim_flyers',
            '_selected_action': [a.pk, b.pk]})
        self.assertEqual(r['Content-Type'], 'application/pdf')
        a.refresh_from_db(); b.refresh_from_db()
        self.assertTrue(a.claim_token)
        self.assertIsNone(b.claim_token)

    def test_all_owned_redirects_with_warning(self):
        owner = self.User.objects.create_user(username='ow4')
        c = make_stand(name='C Stand', slug='c-stand')
        c.owner = owner; c.save()
        r = self.client.get(f'/admin/stands/stand/{c.pk}/claim-flyer/')
        self.assertEqual(r.status_code, 302)


class SplitViewTests(TestCase):
    """Desktop split view on the list page (map column + marker data)."""

    def test_list_page_has_marker_data_and_map_container(self):
        s = make_stand()
        s.latitude = 19.7; s.longitude = -155.08; s.save()
        r = self.client.get(reverse('stand_list'))
        self.assertContains(r, 'marker-data')
        self.assertContains(r, 'side-map')
        self.assertContains(r, 'data-lat="19.7')

    def test_unmapped_stand_card_has_no_coords_attr(self):
        s = make_stand(name='No Pin', slug='no-pin')
        s.latitude = None; s.longitude = None; s.save()
        r = self.client.get(reverse('stand_list'))
        self.assertNotContains(r, 'data-lat="')


class NearMeTests(TestCase):
    """Near-me toggle: button + shared geo helpers ship on both pages."""

    def test_list_page_has_near_me_button(self):
        make_stand()
        r = self.client.get(reverse('stand_list'))
        self.assertContains(r, 'id="near-me"')
        self.assertContains(r, 'hbsDistMi')  # shared haversine helper

    def test_map_page_has_near_me_button(self):
        make_stand()
        r = self.client.get(reverse('stand_map'))
        self.assertContains(r, 'id="near-me"')
        self.assertContains(r, 'hbsGeoPos')  # late-boot handoff


class OwnerDashboardTests(TestCase):
    """Slice 1: /my/ dashboard + open/closed-today toggle."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        self.User = get_user_model()
        self.owner = self.User.objects.create_user(username='baker')
        self.stand = make_stand(name='My Bake Stand', slug='my-bake-stand')
        self.stand.owner = self.owner
        self.stand.save()

    def test_anonymous_gets_styled_signin(self):
        r = self.client.get(reverse('my_stands'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Sign in with Google')

    def test_owner_sees_their_stand(self):
        self.client.force_login(self.owner)
        r = self.client.get(reverse('my_stands'))
        self.assertContains(r, 'My Bake Stand')
        self.assertContains(r, "We're open today")

    def test_non_owner_sees_empty_state(self):
        someone = self.User.objects.create_user(username='visitor')
        self.client.force_login(someone)
        r = self.client.get(reverse('my_stands'))
        self.assertContains(r, 'No stands are linked')

    def test_open_today_creates_override_and_opens_stand(self):
        self.client.force_login(self.owner)
        r = self.client.post(reverse('set_today', args=['my-bake-stand']),
                             {'state': 'open'})
        self.assertRedirects(r, reverse('my_stands'))
        self.stand.refresh_from_db()
        self.assertTrue(self.stand.is_open_now())  # open, no times = all day

    def test_closed_today_wins_over_schedule(self):
        from django.utils import timezone
        now = timezone.localtime()
        WeeklyHours.objects.create(
            stand=self.stand, weekday=now.weekday(),
            open_time=datetime.time(0, 0), close_time=datetime.time(23, 59))
        self.client.force_login(self.owner)
        self.client.post(reverse('set_today', args=['my-bake-stand']),
                         {'state': 'closed', 'note': 'Sold out'})
        self.stand.refresh_from_db()
        self.assertFalse(self.stand.is_open_now())
        ov = self.stand.todays_override()
        self.assertEqual(ov.note, 'Sold out')

    def test_clear_returns_to_schedule(self):
        self.client.force_login(self.owner)
        self.client.post(reverse('set_today', args=['my-bake-stand']),
                         {'state': 'open'})
        self.client.post(reverse('set_today', args=['my-bake-stand']),
                         {'state': 'clear'})
        self.assertIsNone(self.stand.todays_override())

    def test_today_button_highlight_follows_override(self):
        """The btn-primary highlight must track today's override, not be
        hardcoded on 'We're open today' (regression: it used to stick)."""
        import re
        self.client.force_login(self.owner)
        url = reverse('my_stands')

        def active_label(html):
            for cls, label in re.findall(
                    r'<button[^>]*class="(btn[^"]*)"[^>]*>(.*?)</button>',
                    html, re.S):
                if 'btn-primary' in cls:
                    return re.sub(r'\s+', ' ', label).strip()
            return None

        # No override yet -> the regular-schedule button is highlighted
        # (the old bug always highlighted 'open' regardless of state)
        self.assertIn('Regular schedule',
                      active_label(self.client.get(url).content.decode()))

        # Open today -> the open button is the highlighted one
        self.client.post(reverse('set_today', args=['my-bake-stand']),
                         {'state': 'open'})
        self.assertIn('open today',
                      active_label(self.client.get(url).content.decode()))

        # Closed today (no note) -> Closed button highlighted, not open
        self.client.post(reverse('set_today', args=['my-bake-stand']),
                         {'state': 'closed'})
        self.assertIn('Closed today',
                      active_label(self.client.get(url).content.decode()))

        # Pau (closed + note) -> Pau button highlighted, not plain Closed
        self.client.post(reverse('set_today', args=['my-bake-stand']),
                         {'state': 'closed', 'note': 'Pau — sold out'})
        self.assertIn('Pau',
                      active_label(self.client.get(url).content.decode()))

        # Clear -> highlight returns to the regular-schedule button
        self.client.post(reverse('set_today', args=['my-bake-stand']),
                         {'state': 'clear'})
        self.assertIn('Regular schedule',
                      active_label(self.client.get(url).content.decode()))

    def test_toggle_is_idempotent_same_day(self):
        self.client.force_login(self.owner)
        self.client.post(reverse('set_today', args=['my-bake-stand']),
                         {'state': 'open'})
        self.client.post(reverse('set_today', args=['my-bake-stand']),
                         {'state': 'closed'})
        self.assertEqual(self.stand.day_overrides.count(), 1)  # update, not dup
        self.assertFalse(self.stand.todays_override().is_open)

    def test_cannot_toggle_someone_elses_stand(self):
        rival = self.User.objects.create_user(username='rival')
        self.client.force_login(rival)
        r = self.client.post(reverse('set_today', args=['my-bake-stand']),
                             {'state': 'open'})
        self.assertEqual(r.status_code, 404)
        self.assertIsNone(self.stand.todays_override())

    def test_anonymous_toggle_redirects_to_signin(self):
        r = self.client.post(reverse('set_today', args=['my-bake-stand']),
                             {'state': 'open'})
        self.assertRedirects(r, reverse('my_stands'))
        self.assertIsNone(self.stand.todays_override())

    def test_header_shows_my_stand_link_for_owners_only(self):
        self.client.force_login(self.owner)
        r = self.client.get(reverse('stand_list'))
        self.assertContains(r, 'My stand')
        someone = self.User.objects.create_user(username='visitor2')
        self.client.force_login(someone)
        r = self.client.get(reverse('stand_list'))
        self.assertNotContains(r, 'My stand')


class EditStandTests(TestCase):
    """Slice 2: owner edits basic info (description/phone/IG/payment)."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        from .models import PaymentMethod
        self.User = get_user_model()
        self.owner = self.User.objects.create_user(username='baker2')
        self.stand = make_stand(name='Edit Me Stand', slug='edit-me-stand')
        self.stand.owner = self.owner
        self.stand.save()
        self.cash = PaymentMethod.objects.create(name='Cash')
        self.venmo = PaymentMethod.objects.create(name='Venmo')
        self.url = reverse('edit_stand', args=['edit-me-stand'])

    def test_anonymous_redirected(self):
        r = self.client.get(self.url)
        self.assertRedirects(r, reverse('my_stands'))

    def test_non_owner_404(self):
        rival = self.User.objects.create_user(username='rival2')
        self.client.force_login(rival)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_form_prefilled(self):
        self.stand.phone = '808-555-1234'
        self.stand.save()
        self.client.force_login(self.owner)
        r = self.client.get(self.url)
        self.assertContains(r, '808-555-1234')
        self.assertContains(r, 'Save changes')

    def _valid_data(self, **extra):
        data = {'location_type': self.stand.location_type,
                'description': 'Fresh malasadas daily.',
                'phone': '808-555-9999',
                'instagram': '@editmestand',
                'payment_methods': [self.cash.pk, self.venmo.pk],
                'status': 'published'}
        data.update(extra)
        return data

    def test_owner_can_update_fields(self):
        self.client.force_login(self.owner)
        r = self.client.post(self.url,
                             self._valid_data(location_type='food_truck'))
        self.assertRedirects(r, reverse('my_stands'))
        self.stand.refresh_from_db()
        self.assertEqual(self.stand.description, 'Fresh malasadas daily.')
        self.assertEqual(self.stand.phone, '808-555-9999')
        self.assertEqual(self.stand.instagram, 'editmestand')  # @ stripped
        self.assertEqual(self.stand.location_type, 'food_truck')
        self.assertEqual(self.stand.payment_methods.count(), 2)
        self.assertEqual(self.stand.updated_by, self.owner)

    def test_name_and_slug_stay_protected(self):
        self.client.force_login(self.owner)
        self.client.post(self.url, self._valid_data(
            name='Hacked Name', slug='oops'))
        self.stand.refresh_from_db()
        self.assertEqual(self.stand.name, 'Edit Me Stand')
        self.assertEqual(self.stand.slug, 'edit-me-stand')

    def test_delisted_is_not_an_owner_choice(self):
        self.client.force_login(self.owner)
        r = self.client.post(self.url, self._valid_data(status='delisted'))
        self.assertEqual(r.status_code, 200)  # form error, nothing saved
        self.stand.refresh_from_db()
        self.assertEqual(self.stand.status, Stand.Status.PUBLISHED)

    def test_hiding_requires_confirmation(self):
        self.client.force_login(self.owner)
        r = self.client.post(self.url, self._valid_data(status='draft'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'hide my stand')  # interstitial shown
        self.stand.refresh_from_db()
        self.assertEqual(self.stand.status, Stand.Status.PUBLISHED)  # unchanged

    def test_confirmed_hide_unlists_stand(self):
        self.client.force_login(self.owner)
        r = self.client.post(self.url, self._valid_data(
            status='draft', confirm_hide='1'))
        self.assertRedirects(r, reverse('my_stands'))
        self.stand.refresh_from_db()
        self.assertEqual(self.stand.status, Stand.Status.DRAFT)
        # gone from the public site
        r = self.client.get(reverse('stand_list'))
        self.assertNotContains(r, 'Edit Me Stand')
        r = self.client.get(self.stand.get_absolute_url())
        self.assertEqual(r.status_code, 404)

    def test_relisting_needs_no_confirmation(self):
        self.stand.status = Stand.Status.DRAFT
        self.stand.save()
        self.client.force_login(self.owner)
        r = self.client.post(self.url, self._valid_data(status='published'))
        self.assertRedirects(r, reverse('my_stands'))
        self.stand.refresh_from_db()
        self.assertEqual(self.stand.status, Stand.Status.PUBLISHED)

    def test_hidden_stand_flagged_on_dashboard(self):
        self.stand.status = Stand.Status.DRAFT
        self.stand.save()
        self.client.force_login(self.owner)
        r = self.client.get(reverse('my_stands'))
        self.assertContains(r, 'Hidden — not listed')

    def test_name_change_links_to_feedback_form(self):
        self.client.force_login(self.owner)
        r = self.client.get(self.url)
        self.assertContains(r, reverse('stand_report',
                                       args=['edit-me-stand']))

    def test_dashboard_links_to_edit(self):
        self.client.force_login(self.owner)
        r = self.client.get(reverse('my_stands'))
        self.assertContains(r, self.url)
        self.assertContains(r, 'Pau!')  # renamed sold-out button


class EditStandSanitizationTests(TestCase):
    """Slice 2b: socials/website/email fields + input sanitization."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        self.User = get_user_model()
        self.owner = self.User.objects.create_user(username='baker3')
        self.stand = make_stand(name='Clean Stand', slug='clean-stand')
        self.stand.owner = self.owner
        self.stand.save()
        self.url = reverse('edit_stand', args=['clean-stand'])
        self.client.force_login(self.owner)

    def _post(self, **extra):
        data = {'location_type': self.stand.location_type,
                'description': 'ok', 'phone': '', 'instagram': '',
                'facebook': '', 'tiktok': '', 'website': '', 'email': '',
                'status': 'published'}
        data.update(extra)
        return self.client.post(self.url, data)

    def test_new_fields_save(self):
        r = self._post(facebook='mybakestand', tiktok='@bakes',
                       website='https://example.com', email='hi@example.com')
        self.assertRedirects(r, reverse('my_stands'))
        self.stand.refresh_from_db()
        self.assertEqual(self.stand.facebook, 'https://www.facebook.com/mybakestand')
        self.assertEqual(self.stand.tiktok, 'bakes')  # @ stripped
        self.assertEqual(self.stand.website, 'https://example.com')
        self.assertEqual(self.stand.email, 'hi@example.com')

    def test_pasted_profile_urls_normalized(self):
        self._post(instagram='https://www.instagram.com/@my.stand/?hl=en',
                   facebook='https://m.facebook.com/My-Page/about',
                   tiktok='https://www.tiktok.com/@tokbaker?lang=en',
                   threads='https://www.threads.com/@my.stand?xmt=1')
        self.stand.refresh_from_db()
        self.assertEqual(self.stand.instagram, 'my.stand')
        self.assertEqual(self.stand.facebook, 'https://www.facebook.com/My-Page')
        self.assertEqual(self.stand.tiktok, 'tokbaker')
        self.assertEqual(self.stand.threads, 'my.stand')

    def test_threads_handle_normalized(self):
        for raw in ['threadsbaker', '@threadsbaker',
                    'threads.com/@threadsbaker',
                    'https://www.threads.net/@threadsbaker']:
            self._post(threads=raw)
            self.stand.refresh_from_db()
            self.assertEqual(self.stand.threads, 'threadsbaker', raw)

    def test_threads_hostile_rejected(self):
        r = self._post(threads='"><script>x</script>')
        self.assertEqual(r.status_code, 200)  # form error, not saved
        self.stand.refresh_from_db()
        self.assertEqual(self.stand.threads, '')

    def test_facebook_shapes_normalized(self):
        from stands.forms import normalize_facebook
        base = 'https://www.facebook.com/'
        cases = {
            'mybakestand': base + 'mybakestand',
            '@MyBakeStand': base + 'MyBakeStand',
            'facebook.com/MyBakeStand': base + 'MyBakeStand',
            'https://www.facebook.com/My-Bake.Stand/': base + 'My-Bake.Stand',
            'https://m.facebook.com/My-Page/about': base + 'My-Page',
            'https://facebook.com/profile.php?id=100012345678901':
                base + 'profile.php?id=100012345678901',
            'fb.com/profile.php?id=42': base + 'profile.php?id=42',
            'facebook.com/pages/Sallys-Bakes/123456789': base + 'pages/Sallys-Bakes/123456789',
            '': '',
            '   ': '',
        }
        for raw, expected in cases.items():
            self.assertEqual(normalize_facebook(raw), expected, raw)

    def test_facebook_full_url_idempotent(self):
        from stands.forms import normalize_facebook
        url = 'https://www.facebook.com/profile.php?id=99'
        self.assertEqual(normalize_facebook(url), url)

    def test_facebook_hostile_rejected(self):
        from django.core.exceptions import ValidationError
        from stands.forms import normalize_facebook
        for bad in ['"><script>x</script>', 'javascript:alert(1)',
                    'facebook.com/profile.php']:
            with self.assertRaises(ValidationError):
                normalize_facebook(bad)

    def test_hostile_handle_rejected(self):
        r = self._post(instagram='javascript:alert(1)')
        self.assertEqual(r.status_code, 200)  # form error
        self.stand.refresh_from_db()
        self.assertEqual(self.stand.instagram, '')
        r = self._post(facebook='"><script>x</script>')
        self.assertEqual(r.status_code, 200)
        self.stand.refresh_from_db()
        self.assertEqual(self.stand.facebook, '')

    def test_hostile_website_rejected(self):
        r = self._post(website='javascript:alert(1)')
        self.assertEqual(r.status_code, 200)
        self.stand.refresh_from_db()
        self.assertEqual(self.stand.website, '')

    def test_bad_phone_rejected(self):
        r = self._post(phone='call me <b>now</b>')
        self.assertEqual(r.status_code, 200)
        self.stand.refresh_from_db()
        self.assertEqual(self.stand.phone, '')
        self._post(phone='(808) 555-1234')
        self.stand.refresh_from_db()
        self.assertEqual(self.stand.phone, '(808) 555-1234')

    def test_description_null_byte_rejected_outright(self):
        # Django's ProhibitNullCharactersValidator fires before our cleaner.
        r = self._post(description='evil\x00payload')
        self.assertEqual(r.status_code, 200)
        self.stand.refresh_from_db()
        self.assertEqual(self.stand.description, '')

    def test_description_control_chars_stripped(self):
        self._post(description='line one\nline two\x08evil')
        self.stand.refresh_from_db()
        self.assertEqual(self.stand.description, 'line one\nline twoevil')

    def test_bad_email_rejected(self):
        r = self._post(email='not-an-email')
        self.assertEqual(r.status_code, 200)
        self.stand.refresh_from_db()
        self.assertEqual(self.stand.email, '')


class EditHoursTests(TestCase):
    """Slice 3: owner edits the weekly hours grid."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        self.User = get_user_model()
        self.owner = self.User.objects.create_user(username='baker4')
        self.stand = make_stand(name='Hours Stand', slug='hours-stand')
        self.stand.owner = self.owner
        self.stand.save()
        self.url = reverse('edit_hours', args=['hours-stand'])

    def _blank_week(self, **extra):
        data = {}
        for d in range(7):
            data[f'open_{d}'] = ''
            data[f'close_{d}'] = ''
        data['irregular_hours_note'] = ''
        data.update(extra)
        return data

    def test_anonymous_redirected(self):
        r = self.client.get(self.url)
        self.assertRedirects(r, reverse('my_stands'))

    def test_non_owner_404(self):
        rival = self.User.objects.create_user(username='rival4')
        self.client.force_login(rival)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_grid_prefilled(self):
        WeeklyHours.objects.create(stand=self.stand, weekday=5,
                                   open_time=datetime.time(7, 0),
                                   close_time=datetime.time(13, 0))
        self.client.force_login(self.owner)
        r = self.client.get(self.url)
        self.assertContains(r, 'value="07:00"')
        self.assertContains(r, 'value="13:00"')

    def test_save_replaces_hours(self):
        WeeklyHours.objects.create(stand=self.stand, weekday=0,
                                   open_time=datetime.time(9, 0),
                                   close_time=datetime.time(17, 0))
        self.client.force_login(self.owner)
        r = self.client.post(self.url, self._blank_week(
            open_5='07:00', close_5='13:00',
            open_6='08:30', close_6='12:00',
            irregular_hours_note='Usually pau by noon'))
        self.assertRedirects(r, reverse('my_stands'))
        self.stand.refresh_from_db()
        hours = list(self.stand.weekly_hours.all())
        self.assertEqual(len(hours), 2)  # Monday row gone, Sat+Sun in
        self.assertEqual(hours[0].weekday, 5)
        self.assertEqual(hours[0].open_time, datetime.time(7, 0))
        self.assertEqual(hours[1].weekday, 6)
        self.assertEqual(self.stand.irregular_hours_note,
                         'Usually pau by noon')
        self.assertEqual(self.stand.updated_by, self.owner)

    def test_all_blank_means_no_regular_hours(self):
        WeeklyHours.objects.create(stand=self.stand, weekday=0,
                                   open_time=datetime.time(9, 0),
                                   close_time=datetime.time(17, 0))
        self.client.force_login(self.owner)
        self.client.post(self.url, self._blank_week())
        self.assertEqual(self.stand.weekly_hours.count(), 0)

    def test_half_filled_day_rejected(self):
        self.client.force_login(self.owner)
        r = self.client.post(self.url, self._blank_week(open_2='09:00'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'leave both blank')
        self.assertEqual(self.stand.weekly_hours.count(), 0)

    def test_close_before_open_rejected(self):
        self.client.force_login(self.owner)
        r = self.client.post(self.url, self._blank_week(
            open_3='14:00', close_3='09:00'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'after opening time')
        self.assertEqual(self.stand.weekly_hours.count(), 0)

    def test_error_keeps_other_days_input(self):
        self.client.force_login(self.owner)
        r = self.client.post(self.url, self._blank_week(
            open_0='07:00', close_0='12:00',   # valid day
            open_3='14:00', close_3='09:00'))  # broken day
        self.assertContains(r, 'value="07:00"')  # not lost on re-render
        self.assertEqual(self.stand.weekly_hours.count(), 0)  # nothing saved

    def test_multi_range_day_warning(self):
        for t in [(7, 0, 9, 0), (15, 0, 18, 0)]:
            WeeklyHours.objects.create(
                stand=self.stand, weekday=4,
                open_time=datetime.time(t[0], t[1]),
                close_time=datetime.time(t[2], t[3]))
        self.client.force_login(self.owner)
        r = self.client.get(self.url)
        self.assertContains(r, 'more than one time range')
        self.assertContains(r, 'Friday')

    def test_garbage_time_rejected(self):
        self.client.force_login(self.owner)
        r = self.client.post(self.url, self._blank_week(
            open_1='garbage', close_1='10:00'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.stand.weekly_hours.count(), 0)

    def test_dashboard_links_to_hours(self):
        self.client.force_login(self.owner)
        r = self.client.get(reverse('my_stands'))
        self.assertContains(r, self.url)


class EditPinTests(TestCase):
    """Slice 4: owner places/moves their map pin."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        self.User = get_user_model()
        self.owner = self.User.objects.create_user(username='baker5')
        self.stand = make_stand(name='Pin Stand', slug='pin-stand')
        self.stand.owner = self.owner
        self.stand.save()
        self.url = reverse('edit_pin', args=['pin-stand'])

    def test_anonymous_redirected(self):
        r = self.client.get(self.url)
        self.assertRedirects(r, reverse('my_stands'))

    def test_non_owner_404(self):
        rival = self.User.objects.create_user(username='rival5')
        self.client.force_login(rival)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_page_renders_with_existing_pin(self):
        self.client.force_login(self.owner)
        r = self.client.get(self.url)
        self.assertContains(r, 'pin-map')
        self.assertContains(r, '19.7')  # prefilled from make_stand

    def test_save_sets_owner_pin_source(self):
        self.client.force_login(self.owner)
        r = self.client.post(self.url, {'latitude': '19.712345',
                                        'longitude': '-155.087654'})
        self.assertRedirects(r, reverse('my_stands'))
        self.stand.refresh_from_db()
        self.assertEqual(str(self.stand.latitude), '19.712345')
        self.assertEqual(str(self.stand.longitude), '-155.087654')
        self.assertEqual(self.stand.coords_source,
                         Stand.CoordsSource.OWNER_PIN)
        self.assertEqual(self.stand.updated_by, self.owner)

    def test_off_island_rejected(self):
        self.client.force_login(self.owner)
        r = self.client.post(self.url, {'latitude': '21.30',     # Oahu
                                        'longitude': '-157.85'})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Big Island')
        self.stand.refresh_from_db()
        self.assertEqual(str(self.stand.latitude), '19.700000')  # unchanged

    def test_missing_coords_rejected(self):
        self.client.force_login(self.owner)
        r = self.client.post(self.url, {'latitude': '', 'longitude': ''})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Place the pin')

    def test_owner_pin_resists_geocoder(self):
        # The geocode command must never touch an owner-placed pin.
        self.client.force_login(self.owner)
        self.client.post(self.url, {'latitude': '19.712345',
                                    'longitude': '-155.087654'})
        self.stand.refresh_from_db()
        # Mirror the geocode command's candidate queryset (handle()):
        candidates = Stand.objects.exclude(
            coords_source__in=[Stand.CoordsSource.OWNER_PIN,
                               Stand.CoordsSource.ADMIN])
        self.assertNotIn(self.stand, candidates)

    def test_dashboard_links_to_pin(self):
        self.client.force_login(self.owner)
        r = self.client.get(reverse('my_stands'))
        self.assertContains(r, self.url)
        self.assertContains(r, 'Move map pin')  # has coords already


class ClaimYourStandTests(TestCase):
    """Info page + the 'Is this your stand?' breadcrumb on unclaimed stands."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        self.User = get_user_model()
        self.stand = make_stand(name='Unclaimed Stand', slug='unclaimed-stand')

    def test_info_page_renders(self):
        r = self.client.get(reverse('claim_your_stand'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Is this your stand?')
        self.assertContains(r, 'matt@hilobakestands.com')
        self.assertContains(r, 'instagram.com/hilobakestands')
        # free + the hide/re-submit honesty + cashbox drop-off all present
        self.assertContains(r, 'free')
        self.assertContains(r, 'cashbox')

    def test_unclaimed_stand_shows_breadcrumb(self):
        r = self.client.get(self.stand.get_absolute_url())
        self.assertContains(r, 'Is this your stand?')
        self.assertContains(r, reverse('claim_your_stand'))

    def test_claimed_stand_hides_breadcrumb(self):
        self.stand.owner = self.User.objects.create_user(username='owner7')
        self.stand.save(update_fields=['owner'])
        r = self.client.get(self.stand.get_absolute_url())
        self.assertNotContains(r, reverse('claim_your_stand'))


class OwnerDetailEntryTests(TestCase):
    """Detail page shows an Edit details entry point to the owner only."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        self.User = get_user_model()
        self.owner = self.User.objects.create_user(username='baker6')
        self.stand = make_stand(name='Entry Stand', slug='entry-stand')
        self.stand.owner = self.owner
        self.stand.save()

    def test_owner_sees_edit_button(self):
        self.client.force_login(self.owner)
        r = self.client.get(self.stand.get_absolute_url())
        self.assertContains(r, 'Edit details')
        self.assertContains(r, reverse('my_stands'))

    def test_visitor_does_not_see_edit_button(self):
        r = self.client.get(self.stand.get_absolute_url())
        self.assertNotContains(r, 'Edit details')

    def test_other_user_does_not_see_edit_button(self):
        other = self.User.objects.create_user(username='visitor6')
        self.client.force_login(other)
        r = self.client.get(self.stand.get_absolute_url())
        self.assertNotContains(r, 'Edit details')

    def test_dashboard_separates_manage_actions(self):
        self.client.force_login(self.owner)
        r = self.client.get(reverse('my_stands'))
        self.assertContains(r, 'manage-actions')


def _test_image_bytes(size=(400, 300), color=(120, 180, 90)):
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', size, color).save(buf, 'JPEG')
    buf.seek(0)
    return buf.getvalue()


def _upload_file(name='snack.jpg', size=(400, 300)):
    from django.core.files.uploadedfile import SimpleUploadedFile
    return SimpleUploadedFile(name, _test_image_bytes(size=size),
                              content_type='image/jpeg')


class SeoTests(TestCase):
    def test_robots_txt(self):
        r = self.client.get('/robots.txt')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'text/plain')
        body = r.content.decode()
        for path in ['/admin/', '/accounts/', '/my/', '/claim/']:
            self.assertIn('Disallow: %s' % path, body)
        self.assertIn('Sitemap: https://hilobakestands.com/sitemap.xml', body)

    def test_security_txt(self):
        r = self.client.get('/.well-known/security.txt')
        self.assertEqual(r.status_code, 200)
        body = r.content.decode()
        self.assertIn('Contact: mailto:matt@hilobakestands.com', body)
        self.assertIn('Expires:', body)

    def test_sitemap_includes_unverified_excludes_hidden(self):
        pub = make_stand(name='Pub', slug='pub')
        unver = make_stand(name='Unver', slug='unver',
                           verification=Stand.Verification.UNVERIFIED)
        draft = make_stand(name='Draft', slug='draft',
                           status=Stand.Status.DRAFT)
        hidden = make_stand(name='Hid', slug='hid', auto_hidden=True)
        r = self.client.get('/sitemap.xml')
        self.assertEqual(r.status_code, 200)
        body = r.content.decode()
        self.assertIn(pub.get_absolute_url(), body)
        self.assertIn(unver.get_absolute_url(), body)   # unverified INCLUDED
        self.assertNotIn(draft.get_absolute_url(), body)
        self.assertNotIn(hidden.get_absolute_url(), body)
        self.assertIn('https://', body)                 # absolute, https

    def test_detail_meta_and_canonical(self):
        s = make_stand(name='Meta Stand', slug='meta-stand',
                       description='Best malasadas in Hilo, fresh daily.')
        r = self.client.get(s.get_absolute_url())
        html = r.content.decode()
        self.assertIn('Best malasadas in Hilo', html)          # meta description
        self.assertIn('property="og:title"', html)
        self.assertIn('Meta Stand — HiloBakeStands', html)     # og:title
        self.assertIn('rel="canonical"', html)
        self.assertIn(s.get_absolute_url(), html)

    def test_head_clean_and_og_inside_head(self):
        # A stray text node in <head> (e.g. a multi-line {# #} that renders)
        # forces the parser to close <head> early, pushing og: tags into
        # <body> where Facebook ignores them. Guard both failure modes.
        html = self.client.get('/').content.decode()
        self.assertNotIn('Per-page views may pass', html)   # comment must not render
        head = html.split('</head>')[0]
        for prop in ['og:title', 'og:description', 'og:image', 'og:url']:
            self.assertIn('property="%s"' % prop, head, prop)

    def test_default_og_image_has_dimensions(self):
        html = self.client.get('/').content.decode()
        self.assertIn('property="og:image:width" content="1200"', html)
        self.assertIn('property="og:image:height" content="1200"', html)
        self.assertIn('property="og:image:type" content="image/png"', html)

    def test_one_h1_per_page(self):
        make_stand(name='H1 Stand', slug='h1-stand')
        for url in ['/', '/map/', '/submit/', '/claim-your-stand/']:
            html = self.client.get(url).content.decode()
            self.assertEqual(html.count('<h1'), 1, url)


class SocialLinksTests(TestCase):
    def test_threads_link_and_brand_icons_render(self):
        s = make_stand(name='Social Stand', slug='social-stand',
                       instagram='igbaker', threads='thbaker',
                       facebook='https://www.facebook.com/fbpage',
                       tiktok='ttbaker')
        r = self.client.get(s.get_absolute_url())
        self.assertContains(r, 'https://www.threads.com/@thbaker')
        self.assertContains(r, '>Threads</a>')
        self.assertContains(r, 'class="sicon"')        # inline brand glyphs
        self.assertContains(r, 'fill="#FF0069"')       # instagram
        self.assertContains(r, 'fill="#0866FF"')       # facebook

    def test_no_threads_pill_when_unset(self):
        s = make_stand(name='No Threads', slug='no-threads')
        r = self.client.get(s.get_absolute_url())
        self.assertNotContains(r, 'threads.com')


class PhotoPipelineTests(TestCase):
    """Slice 5: upload processing, moderation chain, and display."""

    def setUp(self):
        import tempfile
        from django.contrib.auth import get_user_model
        from django.test import override_settings
        self.User = get_user_model()
        self.owner = self.User.objects.create_user(username='baker7')
        self.stand = make_stand(name='Photo Stand', slug='photo-stand')
        self.stand.owner = self.owner
        self.stand.save()
        self.url = reverse('stand_photos', args=['photo-stand'])
        self._media = tempfile.TemporaryDirectory()
        self._ms = override_settings(MEDIA_ROOT=self._media.name)
        self._ms.enable()
        self.addCleanup(self._ms.disable)
        self.addCleanup(self._media.cleanup)
        self.client.force_login(self.owner)

    def test_clean_photo_auto_approves(self):
        with mock.patch('stands.moderation.moderate_image',
                        return_value=('ok', 'safesearch: all VERY_UNLIKELY')) as mod:
            r = self.client.post(self.url, {'photo': _upload_file(),
                                            'caption': 'Mochi tray'})
        self.assertRedirects(r, self.url)
        mod.assert_called_once()
        p = self.stand.photos.get()
        self.assertTrue(p.approved)
        self.assertEqual(p.moderation, p.Moderation.AUTO_APPROVED)
        self.assertIn('VERY_UNLIKELY', p.moderation_detail)
        # shows on the public detail page
        r = self.client.get(self.stand.get_absolute_url())
        self.assertContains(r, p.image.url)

    def test_caption_is_escaped_on_public_page(self):
        """Captions are owner-supplied; they must never render as raw HTML."""
        evil = '<script>alert(1)</script>"><img src=x onerror=alert(2)>'
        with mock.patch('stands.moderation.moderate_image',
                        return_value=('ok', 'safesearch: ok')):
            self.client.post(self.url, {'photo': _upload_file(),
                                        'caption': evil})
        p = self.stand.photos.get()
        self.assertTrue(p.approved)
        r = self.client.get(self.stand.get_absolute_url())
        # rendered as inert, escaped text — not as live markup
        self.assertNotContains(r, '<script>alert(1)</script>')
        self.assertNotContains(r, '<img src=x onerror')
        self.assertContains(r, '&lt;script&gt;')

    def test_caption_stripped_and_length_capped(self):
        """Server-side strip()+[:200] — HTML maxlength is bypassable."""
        with mock.patch('stands.moderation.moderate_image',
                        return_value=('ok', 'safesearch: ok')):
            self.client.post(self.url, {'photo': _upload_file(),
                                        'caption': '  ' + 'x' * 500 + '  '})
        p = self.stand.photos.get()
        self.assertEqual(p.caption, 'x' * 200)

    def test_flagged_photo_held_and_admin_emailed(self):
        from django.core import mail
        with mock.patch('stands.moderation.moderate_image',
                        return_value=('flagged', 'safesearch: adult=LIKELY')):
            self.client.post(self.url, {'photo': _upload_file()})
        p = self.stand.photos.get()
        self.assertFalse(p.approved)
        self.assertEqual(p.moderation, p.Moderation.FLAGGED)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('needs review', mail.outbox[0].subject)
        # NOT on the public page
        r = self.client.get(self.stand.get_absolute_url())
        self.assertNotContains(r, p.image.url)

    def test_moderation_down_means_pending_not_approved(self):
        from django.core import mail
        with mock.patch('stands.moderation.moderate_image',
                        return_value=('unavailable', 'no backend')):
            self.client.post(self.url, {'photo': _upload_file()})
        p = self.stand.photos.get()
        self.assertFalse(p.approved)   # fail SAFE
        self.assertEqual(p.moderation, p.Moderation.PENDING)
        self.assertEqual(len(mail.outbox), 1)

    def test_gallery_cap_enforced(self):
        from stands.models import Photo
        for i in range(6):
            Photo.objects.create(stand=self.stand, image='stands/x.jpg')
        with mock.patch('stands.moderation.moderate_image',
                        return_value=('ok', '')):
            r = self.client.post(self.url, {'photo': _upload_file()},
                                 follow=True)
        self.assertEqual(self.stand.photos.count(), 6)
        self.assertContains(r, 'full')

    def test_non_image_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        bad = SimpleUploadedFile('evil.jpg', b'#!/bin/sh\necho pwned',
                                 content_type='image/jpeg')
        r = self.client.post(self.url, {'photo': bad}, follow=True)
        self.assertEqual(self.stand.photos.count(), 0)
        self.assertContains(r, "look like a photo we")  # msg is HTML-escaped

    def test_tiny_image_rejected(self):
        r = self.client.post(self.url,
                             {'photo': _upload_file(size=(50, 50))},
                             follow=True)
        self.assertEqual(self.stand.photos.count(), 0)
        self.assertContains(r, 'too small')

    def test_exif_stripped_and_resized(self):
        import io
        from PIL import Image
        from stands.images import process_upload
        from django.core.files.uploadedfile import SimpleUploadedFile
        # Build a big image with EXIF
        buf = io.BytesIO()
        img = Image.new('RGB', (3000, 2000), (10, 20, 30))
        exif = img.getexif()
        exif[0x010F] = 'TestCam Make'   # camera metadata stands in for GPS
        exif[0x0110] = 'TestCam Model'  # (same EXIF block; all of it goes)
        img.save(buf, 'JPEG', exif=exif.tobytes())
        up = SimpleUploadedFile('big.jpg', buf.getvalue(),
                                content_type='image/jpeg')
        content, _name = process_upload(up)
        out = Image.open(io.BytesIO(content.file.getvalue()))
        self.assertLessEqual(max(out.size), 1600)
        self.assertEqual(dict(out.getexif()), {})  # all metadata gone

    def test_owner_only(self):
        rival = self.User.objects.create_user(username='rival7')
        self.client.force_login(rival)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_delete_photo_clears_list_thumb(self):
        with mock.patch('stands.moderation.moderate_image',
                        return_value=('ok', '')):
            self.client.post(self.url, {'photo': _upload_file()})
        p = self.stand.photos.get()
        self.client.post(reverse('set_list_photo',
                                 args=['photo-stand', p.pk]))
        self.stand.refresh_from_db()
        self.assertTrue(self.stand.list_thumb)
        self.assertEqual(self.stand.list_photo_id, p.pk)
        self.client.post(reverse('delete_photo',
                                 args=['photo-stand', p.pk]))
        self.stand.refresh_from_db()
        self.assertEqual(self.stand.photos.count(), 0)
        self.assertIsNone(self.stand.list_photo)
        self.assertFalse(self.stand.list_thumb)

    def test_list_thumb_shows_on_list_page(self):
        with mock.patch('stands.moderation.moderate_image',
                        return_value=('ok', '')):
            self.client.post(self.url, {'photo': _upload_file()})
        p = self.stand.photos.get()
        self.client.post(reverse('set_list_photo',
                                 args=['photo-stand', p.pk]))
        r = self.client.get(reverse('stand_list'))
        self.assertContains(r, 'listthumb')
        # The thumbnail must link to the stand page (like the name text).
        import re
        m = re.search(
            r'<a[^>]*class="listthumb-link"[^>]*href="([^"]+)"[^>]*>\s*'
            r'<img[^>]*class="listthumb"', r.content.decode())
        self.assertIsNotNone(m, 'list thumbnail should be wrapped in a link')
        self.assertEqual(m.group(1), self.stand.get_absolute_url())

    def test_unapproved_photo_cannot_be_thumbnail(self):
        with mock.patch('stands.moderation.moderate_image',
                        return_value=('flagged', 'x')):
            self.client.post(self.url, {'photo': _upload_file()})
        p = self.stand.photos.get()
        r = self.client.post(reverse('set_list_photo',
                                     args=['photo-stand', p.pk]))
        self.assertEqual(r.status_code, 404)

    # ----- caption editing + reordering (owner photo management) -----------
    def _mk_photos(self, n):
        """Create n approved photos directly, sort_order 0..n-1."""
        from stands.models import Photo
        return [Photo.objects.create(
            stand=self.stand, image=_upload_file(), approved=True,
            sort_order=i, caption='cap%d' % i) for i in range(n)]

    def test_edit_caption_updates_and_clears(self):
        p = self._mk_photos(1)[0]
        url = reverse('edit_photo_caption', args=['photo-stand', p.pk])
        self.client.post(url, {'caption': '  Fresh malasadas  '})
        p.refresh_from_db()
        self.assertEqual(p.caption, 'Fresh malasadas')   # stripped
        self.client.post(url, {'caption': ''})            # empty clears
        p.refresh_from_db()
        self.assertEqual(p.caption, '')

    def test_edit_caption_truncated_server_side(self):
        p = self._mk_photos(1)[0]
        url = reverse('edit_photo_caption', args=['photo-stand', p.pk])
        self.client.post(url, {'caption': 'y' * 500})
        p.refresh_from_db()
        self.assertEqual(p.caption, 'y' * 200)

    def test_edit_caption_blocked_by_moderation(self):
        p = self._mk_photos(1)[0]
        url = reverse('edit_photo_caption', args=['photo-stand', p.pk])
        self.client.post(url, {'caption': 'I will kill you'})
        p.refresh_from_db()
        self.assertEqual(p.caption, 'cap0')   # unchanged — rejected

    def test_upload_caption_blocked_by_moderation(self):
        # Caption moderation runs BEFORE image work → no photo, no Vision call.
        with mock.patch('stands.moderation.moderate_image') as mod:
            self.client.post(self.url, {'photo': _upload_file(),
                                        'caption': 'I will kill you'})
        mod.assert_not_called()
        self.assertEqual(self.stand.photos.count(), 0)

    def test_edit_caption_non_owner_404(self):
        p = self._mk_photos(1)[0]
        other = self.User.objects.create_user(username='intruder')
        self.client.force_login(other)
        r = self.client.post(
            reverse('edit_photo_caption', args=['photo-stand', p.pk]),
            {'caption': 'mine now'})
        self.assertEqual(r.status_code, 404)

    def test_move_photo_up_and_down(self):
        a, b, c = self._mk_photos(3)
        # move c up -> a, c, b
        self.client.post(reverse('move_photo', args=['photo-stand', c.pk]),
                         {'direction': 'up'})
        order = list(self.stand.photos.values_list('pk', flat=True))
        self.assertEqual(order, [a.pk, c.pk, b.pk])
        # move a down -> c, a, b
        self.client.post(reverse('move_photo', args=['photo-stand', a.pk]),
                         {'direction': 'down'})
        order = list(self.stand.photos.values_list('pk', flat=True))
        self.assertEqual(order, [c.pk, a.pk, b.pk])

    def test_move_noop_at_end(self):
        a, b, c = self._mk_photos(3)
        self.client.post(reverse('move_photo', args=['photo-stand', a.pk]),
                         {'direction': 'up'})   # already first
        order = list(self.stand.photos.values_list('pk', flat=True))
        self.assertEqual(order, [a.pk, b.pk, c.pk])

    def test_move_renumbers_legacy_zeros(self):
        from stands.models import Photo
        a, b, c = self._mk_photos(3)
        Photo.objects.filter(stand=self.stand).update(sort_order=0)  # legacy
        self.client.post(reverse('move_photo', args=['photo-stand', c.pk]),
                         {'direction': 'up'})
        rows = list(self.stand.photos.values_list('sort_order', flat=True))
        self.assertEqual(rows, [0, 1, 2])   # renumbered, contiguous

    def test_move_non_owner_404(self):
        a, _b, _c = self._mk_photos(3)
        other = self.User.objects.create_user(username='intruder2')
        self.client.force_login(other)
        r = self.client.post(reverse('move_photo', args=['photo-stand', a.pk]),
                             {'direction': 'up'})
        self.assertEqual(r.status_code, 404)


class ModerationChainTests(TestCase):
    """Unit tests for the SafeSearch → homelab → unavailable chain."""

    def _vision_response(self, adult='VERY_UNLIKELY', racy='UNLIKELY'):
        import json
        from unittest.mock import MagicMock
        body = MagicMock()
        body.__enter__ = lambda s: s
        body.__exit__ = lambda s, *a: False
        body.read = lambda: json.dumps({'responses': [{
            'safeSearchAnnotation': {
                'adult': adult, 'violence': 'VERY_UNLIKELY',
                'racy': racy, 'spoof': 'UNLIKELY', 'medical': 'UNLIKELY',
            }}]}).encode()
        return body

    def test_vision_clean(self):
        from django.test import override_settings
        from stands.moderation import moderate_image
        with override_settings(VISION_API_KEY='k'):
            with mock.patch('stands.moderation.urllib.request.urlopen',
                            return_value=self._vision_response()):
                verdict, detail = moderate_image(b'img')
        self.assertEqual(verdict, 'ok')
        self.assertIn('safesearch', detail)

    def test_vision_flags_adult(self):
        from django.test import override_settings
        from stands.moderation import moderate_image
        with override_settings(VISION_API_KEY='k'):
            with mock.patch('stands.moderation.urllib.request.urlopen',
                            return_value=self._vision_response(adult='VERY_LIKELY')):
                verdict, _d = moderate_image(b'img')
        self.assertEqual(verdict, 'flagged')

    def test_vision_error_falls_back_to_homelab(self):
        import json
        import urllib.error
        from unittest.mock import MagicMock
        from django.test import override_settings
        from stands.moderation import moderate_image
        homelab = MagicMock()
        homelab.__enter__ = lambda s: s
        homelab.__exit__ = lambda s, *a: False
        homelab.read = lambda: json.dumps({'nsfw': 0.02}).encode()

        calls = []
        def fake_urlopen(req, **kw):
            calls.append(req.full_url)
            if 'vision' in req.full_url:
                raise urllib.error.URLError('quota')
            return homelab
        with override_settings(VISION_API_KEY='k',
                               MODERATION_FALLBACK_URL='http://media/check',
                               MODERATION_FALLBACK_TOKEN='t'):
            with mock.patch('stands.moderation.urllib.request.urlopen',
                            side_effect=fake_urlopen):
                verdict, detail = moderate_image(b'img')
        self.assertEqual(verdict, 'ok')
        self.assertIn('homelab', detail)
        self.assertEqual(len(calls), 2)

    def test_homelab_flags_nsfw(self):
        import json
        from unittest.mock import MagicMock
        from django.test import override_settings
        from stands.moderation import moderate_image
        body = MagicMock()
        body.__enter__ = lambda s: s
        body.__exit__ = lambda s, *a: False
        body.read = lambda: json.dumps({'nsfw': 0.93}).encode()
        with override_settings(VISION_API_KEY='',
                               MODERATION_FALLBACK_URL='http://media/check',
                               MODERATION_FALLBACK_TOKEN='t'):
            with mock.patch('stands.moderation.urllib.request.urlopen',
                            return_value=body):
                verdict, _d = moderate_image(b'img')
        self.assertEqual(verdict, 'flagged')

    def test_nothing_configured_is_unavailable(self):
        from django.test import override_settings
        from stands.moderation import moderate_image
        with override_settings(VISION_API_KEY='',
                               MODERATION_FALLBACK_URL=''):
            verdict, _d = moderate_image(b'img')
        self.assertEqual(verdict, 'unavailable')


class UsageLogMiddlewareTests(TestCase):
    """Privacy-preserving request logging (stands.middleware)."""

    def setUp(self):
        import tempfile
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.logpath = self._dir.name + '/usage.jsonl'
        make_stand(name='Log Stand', slug='log-stand')

    def _rows(self):
        import json
        import os
        if not os.path.exists(self.logpath):
            return []
        with open(self.logpath, encoding='utf-8') as f:
            return [json.loads(line) for line in f if line.strip()]

    def test_logs_request_with_language_and_no_raw_ip(self):
        from django.test import override_settings
        with override_settings(USAGE_LOG_PATH=self.logpath):
            r = self.client.get('/stand/log-stand/',
                                HTTP_ACCEPT_LANGUAGE='ja,en-US;q=0.9',
                                HTTP_X_FORWARDED_FOR='203.0.113.7',
                                REMOTE_ADDR='203.0.113.7')
        self.assertEqual(r.status_code, 200)
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row['path'], '/stand/log-stand/')
        self.assertEqual(row['status'], 200)
        self.assertEqual(row['lang'], 'ja,en-US;q=0.9')
        # IP is hashed, never stored raw.
        self.assertNotIn('203.0.113.7', row['visitor'])
        self.assertEqual(len(row['visitor']), 16)

    def test_same_ip_same_day_hashes_identically(self):
        from django.test import override_settings
        with override_settings(USAGE_LOG_PATH=self.logpath):
            self.client.get('/stand/log-stand/', HTTP_CF_CONNECTING_IP='198.51.100.4')
            self.client.get('/', HTTP_CF_CONNECTING_IP='198.51.100.4')
        rows = self._rows()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['visitor'], rows[1]['visitor'])

    def test_static_paths_are_skipped(self):
        from django.test import override_settings
        with override_settings(USAGE_LOG_PATH=self.logpath):
            self.client.get('/static/stands/hibiscus.svg')
        self.assertEqual(self._rows(), [])

    def test_disabled_when_path_unset(self):
        from django.test import override_settings
        with override_settings(USAGE_LOG_PATH=None):
            r = self.client.get('/stand/log-stand/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self._rows(), [])

    def test_usage_stats_command_reads_log(self):
        from io import StringIO

        from django.core.management import call_command
        from django.test import override_settings
        with override_settings(USAGE_LOG_PATH=self.logpath):
            self.client.get('/stand/log-stand/', HTTP_ACCEPT_LANGUAGE='ja,en;q=0.8')
            self.client.get('/stand/log-stand/', HTTP_ACCEPT_LANGUAGE='en-US,en;q=0.9')
            out = StringIO()
            call_command('usage_stats', '--file', self.logpath, stdout=out)
        text = out.getvalue()
        self.assertIn('Requests:  2', text)
        self.assertIn('Per day', text)
        self.assertIn('ja', text)
        self.assertIn('en', text)

    def test_usage_stats_per_day_dedupes_within_day(self):
        from io import StringIO

        from django.core.management import call_command
        from django.test import override_settings
        with override_settings(USAGE_LOG_PATH=self.logpath):
            # one visitor, two requests, same day -> 1 unique that day
            self.client.get('/stand/log-stand/', HTTP_CF_CONNECTING_IP='192.0.2.5')
            self.client.get('/', HTTP_CF_CONNECTING_IP='192.0.2.5')
            out = StringIO()
            call_command('usage_stats', '--file', self.logpath, stdout=out)
        # the day row should read 2 requests, 1 visitor
        import re
        rows = [ln for ln in out.getvalue().splitlines()
                if re.match(r'\s*\d{4}-\d{2}-\d{2}\s', ln)]
        self.assertEqual(rows[-1].split()[-2:], ['2', '1'])


class ScanStatusTests(TestCase):
    """Scan-to-open/close QR feature. The QR points at a GET landing page that
    must NOT mutate on its own (only its JS POST to set_today does)."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        self.User = get_user_model()
        self.owner = self.User.objects.create_user(username='baker')
        self.stand = make_stand(name='Sugar Wave', slug='sugar-wave',
                                owner=self.owner)

    def _scan(self, action):
        return reverse('scan_status', args=['sugar-wave', action])

    def test_get_does_not_mutate(self):
        """The critical safety property: fetching the scan URL (as a scanner,
        prefetcher, or link previewer would) changes nothing."""
        self.client.force_login(self.owner)
        r = self.client.get(self._scan('open'))
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(self.stand.todays_override())
        self.assertEqual(DayOverride.objects.count(), 0)

    def test_owner_page_carries_the_real_post_form(self):
        self.client.force_login(self.owner)
        r = self.client.get(self._scan('open'))
        self.assertContains(r, reverse('set_today', args=['sugar-wave']))
        self.assertContains(r, 'value="open"')

    def test_mutation_happens_via_set_today_post(self):
        """The JS posts to set_today — that path (already the dashboard's) does
        flip the override."""
        self.client.force_login(self.owner)
        r = self.client.post(reverse('set_today', args=['sugar-wave']),
                             {'state': 'open'})
        self.assertRedirects(r, reverse('my_stands'))
        self.stand.refresh_from_db()
        self.assertTrue(self.stand.is_open_now())

    def test_anonymous_gets_signin_not_404_and_no_mutation(self):
        r = self.client.get(self._scan('open'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Sign in with Google')
        self.assertEqual(DayOverride.objects.count(), 0)

    def test_non_owner_forbidden_and_no_acting_form(self):
        other = self.User.objects.create_user(username='intruder')
        self.client.force_login(other)
        r = self.client.get(self._scan('closed'))
        self.assertEqual(r.status_code, 403)
        # No acting form rendered for a non-owner.
        self.assertNotContains(r, 'id="scanform"', status_code=403)
        self.assertEqual(DayOverride.objects.count(), 0)

    def test_unknown_action_404(self):
        self.client.force_login(self.owner)
        r = self.client.get(self._scan('explode'))
        self.assertEqual(r.status_code, 404)

    def test_dashboard_shows_qr_codes(self):
        self.client.force_login(self.owner)
        r = self.client.get(reverse('my_stands'))
        self.assertContains(r, 'Open / close from your phone')
        # Two inline QR PNGs (open + closed).
        self.assertEqual(r.content.decode().count('data:image/png;base64'), 2)


class OwnerHoursTipTests(TestCase):
    """The /stand/<slug> tip that tells a signed-in owner with no posted hours
    how to set their status (edit hours / manual toggle / QR codes)."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        self.User = get_user_model()
        self.owner = self.User.objects.create_user(username='baker')
        self.stand = make_stand(name='Sugar Wave', slug='sugar-wave',
                                owner=self.owner)

    def test_tip_shown_to_owner_without_hours(self):
        self.client.force_login(self.owner)
        r = self.client.get(self.stand.get_absolute_url())
        self.assertContains(r, 'No regular hours yet?')

    def test_tip_hidden_once_hours_exist(self):
        WeeklyHours.objects.create(
            stand=self.stand, weekday=0,
            open_time=datetime.time(8, 0), close_time=datetime.time(12, 0))
        self.client.force_login(self.owner)
        r = self.client.get(self.stand.get_absolute_url())
        self.assertNotContains(r, 'No regular hours yet?')

    def test_tip_hidden_from_non_owner(self):
        other = self.User.objects.create_user(username='visitor')
        self.client.force_login(other)
        r = self.client.get(self.stand.get_absolute_url())
        self.assertNotContains(r, 'No regular hours yet?')


class AdminClaimMessageTests(TestCase):
    """The admin change page offers a ready-to-send outreach message with the
    claim link filled in (Matthew copies it by hand)."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        User.objects.create_superuser('admin', 'a@b.c', 'pw')
        self.client.login(username='admin', password='pw')

    def _change_url(self, stand):
        return reverse('admin:stands_stand_change', args=[stand.pk])

    def test_message_shows_with_claim_link(self):
        stand = make_stand(name='Sugar Wave', slug='sugar-wave')
        stand.generate_claim_token()
        stand.save(update_fields=['claim_token'])
        r = self.client.get(self._change_url(stand))
        self.assertContains(r, 'Outreach message')
        self.assertContains(r, 'Mahalo')
        self.assertContains(r, stand.claim_token)  # link is embedded
        self.assertContains(r, 'Copy message')

    def test_no_message_once_claimed(self):
        from django.contrib.auth import get_user_model
        owner = get_user_model().objects.create_user(username='baker')
        stand = make_stand(name='Owned Stand', slug='owned-stand', owner=owner)
        stand.generate_claim_token()
        stand.save(update_fields=['claim_token'])
        r = self.client.get(self._change_url(stand))
        self.assertNotContains(r, 'Copy message')


class AdminGeocodeButtonTests(TestCase):
    """The admin per-stand 'Geocode now' button (shares stands.geocoding rules
    with the batch command)."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        User.objects.create_superuser('admin', 'a@b.c', 'pw')
        self.client.login(username='admin', password='pw')

    def _hit(self, addresstype='house', cls='place'):
        return {'lat': '19.71', 'lon': '-155.08',
                'addresstype': addresstype, 'class': cls}

    def _geo_url(self, stand):
        return reverse('admin:stands_stand_geocode', args=[stand.pk])

    def test_button_fills_coords_on_place_match(self):
        s = make_stand(latitude=None, longitude=None,
                       street_address='123 Test St', coords_source='')
        with mock.patch('stands.geocoding.nominatim', return_value=self._hit()):
            r = self.client.get(self._geo_url(s))
        self.assertEqual(r.status_code, 302)  # back to change page
        s.refresh_from_db()
        self.assertEqual(float(s.latitude), 19.71)
        self.assertEqual(s.coords_source, Stand.CoordsSource.GEOCODED)
        self.assertEqual(s.geocode_precision, 'house')

    def test_button_refuses_road_only(self):
        s = make_stand(latitude=None, longitude=None,
                       street_address='Hoaloha st', coords_source='')
        with mock.patch('stands.geocoding.nominatim',
                        return_value=self._hit('road', 'highway')):
            self.client.get(self._geo_url(s))
        s.refresh_from_db()
        self.assertIsNone(s.latitude)
        self.assertEqual(s.coords_source, '')

    def test_button_no_address_does_nothing(self):
        s = make_stand(latitude=None, longitude=None, street_address='',
                       coords_source='')
        with mock.patch('stands.geocoding.nominatim') as fake:
            self.client.get(self._geo_url(s))
        fake.assert_not_called()
        s.refresh_from_db()
        self.assertIsNone(s.latitude)

    def test_change_page_shows_geocode_button(self):
        s = make_stand(street_address='123 Test St')
        r = self.client.get(reverse('admin:stands_stand_change', args=[s.pk]))
        self.assertContains(r, 'Geocode now')


class DirectionsLinkTests(TestCase):
    """Map deep-links must percent-encode the lat,lng comma (%2C) — a raw comma
    works on desktop but Android's app hand-off drops the params."""

    def test_latlng_comma_is_encoded(self):
        s = make_stand(latitude='19.700000', longitude='-155.100000')
        links = s.directions_links()
        self.assertIn('destination=19.700000%2C-155.100000', links['Google Maps'])
        self.assertIn('api=1', links['Google Maps'])
        self.assertIn('%2C', links['Apple Maps'])
        self.assertIn('%2C', links['Waze'])
        # no raw comma left in any generated link
        for url in links.values():
            self.assertNotIn(',', url)

    def test_no_links_without_coords(self):
        s = make_stand(latitude=None, longitude=None)
        self.assertEqual(s.directions_links(), {})


class UnicodeNormalizationTests(TestCase):
    """User-pasted 'fancy' Unicode (math-bold etc.) must be NFKC-folded to plain
    text on input, and must not be a denylist bypass."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        self.user = get_user_model().objects.create_user(username='baker')

    def _submit(self, **over):
        from stands.forms import StandSubmitForm
        data = {'name': 'Plain Stand', 'location_type': Stand.LocationType.BAKE_STAND,
                'description': '', 'street_address': '', 'attendance': 'attended'}
        data.update(over)
        return StandSubmitForm(data)

    def test_name_and_address_are_nfkc_folded(self):
        f = self._submit(name='𝟓𝟎 𝐀𝐡𝐨𝐧𝐚 𝐁𝐚𝐤𝐞𝐬',
                         street_address='𝟓𝟎 𝐀𝐡𝐨𝐧𝐚 𝐏𝐥. 𝐇𝐢𝐥𝐨, 𝐇𝐈')
        self.assertTrue(f.is_valid(), f.errors)
        self.assertEqual(f.cleaned_data['name'], '50 Ahona Bakes')
        self.assertEqual(f.cleaned_data['street_address'], '50 Ahona Pl. Hilo, HI')

    def test_description_is_nfkc_folded(self):
        f = self._submit(description='𝐅𝐫𝐞𝐬𝐡 𝐦𝐚𝐥𝐚𝐬𝐚𝐝𝐚𝐬')
        self.assertTrue(f.is_valid(), f.errors)
        self.assertEqual(f.cleaned_data['description'], 'Fresh malasadas')

    def test_fancy_unicode_does_not_bypass_denylist(self):
        # 'ahole' is a real Hawaiian denylist term; math-bold must still trip it.
        from stands.textmod import text_blocked
        self.assertTrue(text_blocked('𝐚𝐡𝐨𝐥𝐞'))
        f = self._submit(name='𝐚𝐡𝐨𝐥𝐞 stand')
        self.assertFalse(f.is_valid())

    def test_plain_text_unchanged(self):
        f = self._submit(name='Sugar Wave Bakery', description='Loco moco & pork')
        self.assertTrue(f.is_valid(), f.errors)
        self.assertEqual(f.cleaned_data['name'], 'Sugar Wave Bakery')
        self.assertEqual(f.cleaned_data['description'], 'Loco moco & pork')
