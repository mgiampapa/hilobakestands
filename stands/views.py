import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.core.mail import mail_admins
from django.urls import reverse
from django.utils.translation import gettext as _

from .models import Category, Report, Stand

logger = logging.getLogger(__name__)

TURNSTILE_VERIFY_URL = 'https://challenges.cloudflare.com/turnstile/v0/siteverify'


def turnstile_ok(request):
    """Server-side Turnstile check. Skipped when no secret is configured
    (dev/tests). Fails OPEN on network errors — losing a real report is worse
    than letting one bot through — but fails CLOSED on an invalid token."""
    secret = settings.TURNSTILE_SECRET_KEY
    if not secret:
        return True
    data = urllib.parse.urlencode({
        'secret': secret,
        'response': request.POST.get('cf-turnstile-response', ''),
        'remoteip': request.META.get('HTTP_CF_CONNECTING_IP',
                                     request.META.get('REMOTE_ADDR', '')),
    }).encode()
    try:
        with urllib.request.urlopen(TURNSTILE_VERIFY_URL, data=data,
                                    timeout=5) as resp:
            return json.load(resp).get('success', False)
    except (urllib.error.URLError, TimeoutError, ValueError):
        logger.warning('Turnstile verify unreachable; failing open')
        return True


def _filtered_stands(request):
    """Shared filtering for the list and map views (full filter parity)."""
    # auto_hidden is reserved for the deferred report auto-hide; excluding it
    # here means that machinery, if ever built, withholds stands automatically.
    stands = (Stand.objects.filter(status=Stand.Status.PUBLISHED,
                                   auto_hidden=False)
              .prefetch_related('categories', 'payment_methods',
                                'weekly_hours', 'day_overrides'))

    # Verified-only by default; unverified community submissions are opt-in via
    # ?community=1 (the "show community submissions" toggle).
    show_community = request.GET.get('community') == '1'
    if not show_community:
        stands = stands.filter(verification=Stand.Verification.VERIFIED)

    location_type = request.GET.get('type', '')
    category = request.GET.get('category', '')
    open_now = request.GET.get('open') == 'now'

    if location_type:
        stands = stands.filter(location_type=location_type)
    if category:
        stands = stands.filter(categories__slug=category)

    stands = list(stands)
    if open_now:
        stands = [s for s in stands if s.is_open_now()]

    return stands, {
        'categories': Category.objects.all(),
        'location_types': Stand.LocationType.choices,
        'show_community': show_community,
        'current': {'type': location_type, 'category': category,
                    'open': open_now, 'community': show_community},
    }


def _marker_data(stands):
    return [{
        'name': s.name,
        'lat': float(s.latitude), 'lng': float(s.longitude),
        'url': s.get_absolute_url(),
        'type': str(s.get_location_type_display()),
        'open': s.is_open_now(),
    } for s in stands if s.latitude is not None and s.longitude is not None]


def stand_list(request):
    stands, context = _filtered_stands(request)
    context['stands'] = stands
    # Desktop split view: the side map lazy-loads Leaflet and needs markers.
    context['markers'] = _marker_data(stands)
    return render(request, 'stands/list.html', context)


def stand_map(request):
    stands, context = _filtered_stands(request)
    context['markers'] = _marker_data(stands)
    context['unmapped'] = [s for s in stands if s.latitude is None]
    return render(request, 'stands/map.html', context)


def stand_detail(request, slug):
    # Unverified stands are still viewable by direct link (with a badge); only
    # auto_hidden (deferred) ones 404. status=published still required.
    stand = get_object_or_404(
        Stand.objects.prefetch_related('categories', 'payment_methods',
                                       'weekly_hours', 'photos'),
        slug=slug, status=Stand.Status.PUBLISHED, auto_hidden=False)
    return render(request, 'stands/detail.html', {
        'stand': stand,
        'photos': stand.photos.filter(approved=True),
        'weekdays': dict(stand.weekly_hours.model.WEEKDAYS),
    })


def claim_your_stand(request):
    """Static 'how to claim your stand' info page.

    Owners who find their seeded (or community-submitted) listing before they
    get a claim flyer land here from the breadcrumb on unclaimed stands. The
    actual claim still needs a token Matthew hands out — this page just tells
    them how to reach him to get it (SPEC v1.0 Open Q3: owner-initiated claim).
    """
    return render(request, 'stands/claim_your_stand.html')


def stand_report(request, slug):
    stand = get_object_or_404(Stand, slug=slug, status=Stand.Status.PUBLISHED)
    if request.method == 'POST':
        message = request.POST.get('message', '').strip()
        honeypot = request.POST.get('website_url', '')  # spam trap, real users leave blank
        if not turnstile_ok(request):
            messages.error(request, _('Verification failed — please try again.'))
            return redirect(request.path)
        if message and not honeypot:
            report = Report.objects.create(
                stand=stand, message=message[:2000],
                contact=request.POST.get('contact', '').strip()[:200])
            stand.validation_score = max(0, stand.validation_score - 10)
            stand.save(update_fields=['validation_score'])
            admin_url = request.build_absolute_uri(
                reverse('admin:stands_report_change', args=[report.pk]))
            mail_admins(  # never blocks the visitor if SMTP is down
                subject=f'New report: {stand.name}',
                message=(f'Stand: {stand.name}\n'
                         f'Validation score now: {stand.validation_score}\n'
                         f'Contact: {report.contact or "(none)"}\n\n'
                         f'{report.message}\n\n'
                         f'Handle it here: {admin_url}'),
                fail_silently=True)
            messages.success(request, _('Mahalo! Your report has been sent.'))
        return redirect(stand.get_absolute_url())
    return render(request, 'stands/report.html', {
        'stand': stand,
        'turnstile_site_key': settings.TURNSTILE_SITE_KEY,
    })


def stand_claim(request, token):
    """One-time claim link (QR code / SMS / email handout).

    Sign in with Google, confirm, and the stand is yours; the token is
    burned on success. In-person handout of the token IS the verification
    step (SPEC: owner-initiated claims, Matthew verifies in person).
    """
    try:
        stand = Stand.objects.get(claim_token=token)
    except Stand.DoesNotExist:
        return render(request, 'stands/claim_invalid.html', status=404)

    if stand.owner:  # defensive; tokens are burned on claim
        messages.info(request, _('This stand has already been claimed.'))
        return redirect(stand.get_absolute_url())

    if request.method == 'POST' and request.user.is_authenticated:
        from django.utils import timezone
        stand.owner = request.user
        stand.claim_token = None
        stand.claimed_at = timezone.now()
        # Completing a claim also verifies the stand (SPEC-1.1 §6): an operator
        # claiming their own listing flips unverified -> verified. save=False so
        # it lands in the single atomic save below.
        stand.mark_verified(via=Stand.VerifiedVia.CLAIM, save=False)
        stand.save(update_fields=['owner', 'claim_token', 'claimed_at',
                                  'verification', 'verified_via', 'verified_at',
                                  'updated_at'])
        messages.success(request, _(
            'You now manage %(name)s. Use the “Edit details” button to '
            'update your listing.') % {'name': stand.name})
        return redirect(stand.get_absolute_url())

    return render(request, 'stands/claim.html', {'stand': stand})


def _unique_slug(name):
    """Slug from name, guaranteed unique (public submissions can collide)."""
    from django.utils.text import slugify
    base = slugify(name)[:130] or 'stand'
    slug, i = base, 2
    while Stand.objects.filter(slug=slug).exists():
        suffix = '-%d' % i
        slug = base[:130 - len(suffix)] + suffix
        i += 1
    return slug


def _notify_new_submission(request, stand):
    """Email Matthew about a new community submission (never blocks the user)."""
    admin_url = request.build_absolute_uri(
        reverse('admin:stands_stand_change', args=[stand.pk]))
    claim_url = settings.SITE_BASE_URL + stand.claim_url_path
    mail_admins(
        subject=f'New community submission: {stand.name}',
        message=(f'{stand.name} — {stand.get_location_type_display()}\n'
                 f'Submitted by: {stand.created_by.email or stand.created_by}\n'
                 f'Address: {stand.street_address or "(none given)"}\n\n'
                 f'{stand.description or "(no description)"}\n\n'
                 f'Review / verify: {admin_url}\n'
                 f'Claim link to send the owner: {claim_url}'),
        fail_silently=True)


def _nearby_stand(lat, lng, meters=25):
    """An existing published stand within `meters` of (lat, lng), or None —
    a non-blocking duplicate hint for the submit flow (haversine, ~25 stands)."""
    import math
    for s in (Stand.objects.filter(status=Stand.Status.PUBLISHED)
              .exclude(latitude__isnull=True)):
        dlat = math.radians(float(s.latitude) - lat)
        dlng = math.radians(float(s.longitude) - lng)
        a = (math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat))
             * math.cos(math.radians(float(s.latitude))) * math.sin(dlng / 2) ** 2)
        if 2 * 6371000 * math.asin(math.sqrt(a)) <= meters:
            return s
    return None


SUBMIT_DAILY_LIMIT = 5  # public submissions per user per rolling 24h


def submit_stand(request):
    """Public 'Submit a stand' (login-gated). Creates an UNVERIFIED, published
    community listing; Matthew verifies later or the owner claims it. An
    optional map pin (drag/tap/GPS) sets exact coords (owner_pin precedence);
    without one the address is geocoded later by the batch command.

    Anti-abuse (2b): honeypot + per-user daily rate limit + Turnstile here; the
    text denylist (name/description/address) lives in the form."""
    if not request.user.is_authenticated:
        return render(request, 'stands/submit_signin.html')
    from datetime import timedelta
    from decimal import Decimal
    from django.utils import timezone
    from .forms import StandSubmitForm
    ctx = {'turnstile_site_key': settings.TURNSTILE_SITE_KEY}
    if request.method == 'POST':
        # Honeypot: real users never fill this. Drop silently — no create, no
        # tell (a bot thinks it succeeded).
        if request.POST.get('website_url'):
            return redirect('stand_list')
        form = StandSubmitForm(request.POST)
        # Per-user daily rate limit.
        since = timezone.now() - timedelta(days=1)
        recent = Stand.objects.filter(
            created_by=request.user,
            created_via=Stand.CreatedVia.PUBLIC_SUBMIT,
            submitted_at__gte=since).count()
        if recent >= SUBMIT_DAILY_LIMIT:
            messages.error(request, _(
                "You've added several stands today — please come back tomorrow "
                'to add more. Mahalo for the contributions!'))
            return render(request, 'stands/submit.html', {'form': form, **ctx})
        if not turnstile_ok(request):
            messages.error(request, _('Verification failed — please try again.'))
            return render(request, 'stands/submit.html', {'form': form, **ctx})
        if form.is_valid():
            # Optional pin: parse + Big Island bbox check (reuses owner-pin rules)
            lat = lng = None
            lat_raw = request.POST.get('latitude', '').strip()
            lng_raw = request.POST.get('longitude', '').strip()
            if lat_raw and lng_raw:
                try:
                    lat, lng = float(lat_raw), float(lng_raw)
                except ValueError:
                    lat = lng = None
                else:
                    lo, hi = BIG_ISLAND_BOUNDS['lat']
                    wlo, whi = BIG_ISLAND_BOUNDS['lng']
                    if not (lo <= lat <= hi and wlo <= lng <= whi):
                        return render(request, 'stands/submit.html', {
                            'form': form, 'pin_error': _(
                                "That pin doesn't look like it's on the Big "
                                "Island — drag it to the stand and try again."),
                            **ctx})
            # Non-blocking 25m duplicate warning (only when a pin is placed)
            if lat is not None:
                nearby = _nearby_stand(lat, lng)
                if nearby and not request.POST.get('confirm_duplicate'):
                    return render(request, 'stands/submit.html', {
                        'form': form, 'needs_dup_confirm': True,
                        'nearby': nearby, **ctx})
            stand = form.save(commit=False)
            stand.slug = _unique_slug(stand.name)
            stand.status = Stand.Status.PUBLISHED
            stand.verification = Stand.Verification.UNVERIFIED
            stand.created_via = Stand.CreatedVia.PUBLIC_SUBMIT
            stand.created_by = request.user
            stand.updated_by = request.user
            stand.submitted_at = timezone.now()
            if lat is not None:
                stand.latitude = Decimal(f'{lat:.6f}')
                stand.longitude = Decimal(f'{lng:.6f}')
                stand.coords_source = Stand.CoordsSource.OWNER_PIN
            stand.generate_claim_token()  # lets Matthew hand the owner a claim link
            stand.save()
            form.save_m2m()
            _notify_new_submission(request, stand)
            messages.success(request, _(
                'Mahalo! "%(name)s" is submitted and now showing as an '
                'unverified community listing. We may reach out to confirm '
                'details.') % {'name': stand.name})
            return redirect(stand.get_absolute_url())
    else:
        form = StandSubmitForm()
    return render(request, 'stands/submit.html', {'form': form, **ctx})


def my_stands(request):
    """Owner dashboard. Anonymous visitors get a styled Google sign-in
    (POST straight to the provider — skips allauth's bare interstitial,
    same pattern as the claim page and header)."""
    if not request.user.is_authenticated:
        return render(request, 'stands/my_stands_signin.html')
    from django.utils import timezone
    stands = (request.user.owned_stands
              .prefetch_related('weekly_hours', 'day_overrides')
              .order_by('name'))
    today = timezone.localdate()
    rows = [{'stand': s,
             'override': s.day_overrides.filter(date=today).first(),
             'open_now': s.is_open_now()} for s in stands]
    return render(request, 'stands/my_stands.html', {'rows': rows})


def set_today(request, slug):
    """Owner's open/closed-today toggle. Writes a DayOverride for today,
    which is_open_now() already prefers over the weekly schedule."""
    if not request.user.is_authenticated:
        return redirect('my_stands')
    stand = get_object_or_404(Stand, slug=slug, owner=request.user)
    if request.method == 'POST':
        from django.utils import timezone
        today = timezone.localdate()
        state = request.POST.get('state')
        if state == 'clear':
            stand.day_overrides.filter(date=today).delete()
            messages.success(request, _(
                '%(name)s is back on its regular schedule today.')
                % {'name': stand.name})
        elif state in ('open', 'closed'):
            stand.day_overrides.update_or_create(
                date=today,
                defaults={'is_open': state == 'open',
                          'open_time': None, 'close_time': None,
                          'note': request.POST.get('note', '').strip()[:200]})
            messages.success(request, _(
                '%(name)s is marked %(state)s for today.')
                % {'name': stand.name,
                   'state': _('open') if state == 'open' else _('closed')})
    return redirect('my_stands')


def edit_stand(request, slug):
    """Owner dashboard slice 2: edit basic info, type, and visibility.

    Hiding a currently-listed stand requires an explicit confirmation
    (confirm_hide) so nobody unpublishes by accident — the interstitial
    spells out that the stand disappears from the whole site. Re-listing
    needs no confirmation. Name changes go through the feedback form.
    """
    if not request.user.is_authenticated:
        return redirect('my_stands')
    stand = get_object_or_404(Stand, slug=slug, owner=request.user)
    from .forms import StandBasicInfoForm
    was_published = stand.status == Stand.Status.PUBLISHED
    if request.method == 'POST':
        form = StandBasicInfoForm(request.POST, instance=stand)
        if form.is_valid():
            hiding = (was_published and 'status' in form.cleaned_data and
                      form.cleaned_data['status'] != Stand.Status.PUBLISHED)
            if hiding and not request.POST.get('confirm_hide'):
                return render(request, 'stands/edit_stand.html',
                              {'stand': stand, 'form': form,
                               'needs_confirm': True})
            stand = form.save(commit=False)
            stand.updated_by = request.user
            stand.save()
            form.save_m2m()
            if hiding:
                messages.success(request, _(
                    '%(name)s is now hidden from the site. Re-list it here '
                    'whenever you are ready.') % {'name': stand.name})
            else:
                messages.success(request, _('%(name)s has been updated.')
                                 % {'name': stand.name})
            return redirect('my_stands')
    else:
        form = StandBasicInfoForm(instance=stand)
    return render(request, 'stands/edit_stand.html',
                  {'stand': stand, 'form': form})


def edit_hours(request, slug):
    """Owner dashboard slice 3: weekly hours as a 7-day grid.

    One open/close range per day (blank = closed) — covers every real
    listing; the model supports multiple ranges per day, so if an admin
    ever set those, the grid shows the first range and warns that saving
    replaces the rest. Saving wipes and recreates the stand's WeeklyHours
    in one transaction. The open/closed-today toggle still wins over all
    of this (DayOverride beats schedule in is_open_now).
    """
    import datetime as dt

    from django.db import transaction

    from .models import WeeklyHours

    if not request.user.is_authenticated:
        return redirect('my_stands')
    stand = get_object_or_404(Stand, slug=slug, owner=request.user)

    weekdays = WeeklyHours.WEEKDAYS
    existing = {}
    multi_range_days = []
    for h in stand.weekly_hours.all():  # ordered weekday, open_time
        if h.weekday in existing:
            if h.weekday not in multi_range_days:
                multi_range_days.append(h.weekday)
            continue
        existing[h.weekday] = h

    def parse(raw):
        raw = (raw or '').strip()
        if not raw:
            return None
        return dt.time.fromisoformat(raw)  # "HH:MM" from <input type=time>

    if request.method == 'POST':
        rows, errors = [], {}
        for num, label in weekdays:
            try:
                open_t = parse(request.POST.get(f'open_{num}'))
                close_t = parse(request.POST.get(f'close_{num}'))
            except ValueError:
                errors[num] = _('Enter times as HH:MM.')
                rows.append((num, request.POST.get(f'open_{num}', ''),
                             request.POST.get(f'close_{num}', '')))
                continue
            if (open_t is None) != (close_t is None):
                errors[num] = _('Enter both times, or leave both blank '
                                'for a closed day.')
            elif open_t is not None and close_t <= open_t:
                errors[num] = _('Closing time must be after opening time.')
            rows.append((num, open_t, close_t))
        note = (request.POST.get('irregular_hours_note', '').strip()[:300])
        if not errors:
            with transaction.atomic():
                stand.weekly_hours.all().delete()
                WeeklyHours.objects.bulk_create([
                    WeeklyHours(stand=stand, weekday=num,
                                open_time=o, close_time=c)
                    for num, o, c in rows if o is not None])
                stand.irregular_hours_note = note
                stand.updated_by = request.user
                stand.save(update_fields=['irregular_hours_note',
                                          'updated_by', 'updated_at'])
            messages.success(request, _(
                'Hours for %(name)s have been updated.')
                % {'name': stand.name})
            return redirect('my_stands')
        # Re-render with the submitted values and per-day errors.
        grid = [{'num': num, 'label': label,
                 'open': request.POST.get(f'open_{num}', ''),
                 'close': request.POST.get(f'close_{num}', ''),
                 'error': errors.get(num)} for num, label in weekdays]
        return render(request, 'stands/edit_hours.html', {
            'stand': stand, 'grid': grid, 'note': note,
            'multi_range_days': []})

    grid = [{'num': num, 'label': label,
             'open': existing[num].open_time.strftime('%H:%M')
                     if num in existing else '',
             'close': existing[num].close_time.strftime('%H:%M')
                      if num in existing else '',
             'error': None} for num, label in weekdays]
    return render(request, 'stands/edit_hours.html', {
        'stand': stand, 'grid': grid,
        'note': stand.irregular_hours_note,
        'multi_range_days': [dict(weekdays)[d] for d in multi_range_days]})


# Generous Big Island bounding box for owner-placed pins.
BIG_ISLAND_BOUNDS = {'lat': (18.7, 20.5), 'lng': (-156.4, -154.5)}


def edit_pin(request, slug):
    """Owner dashboard slice 4: drag (or tap, or GPS) the stand's map pin.

    Saves coords_source=owner_pin, which outranks admin and geocoded pins
    and is never overwritten by the geocode command.
    """
    if not request.user.is_authenticated:
        return redirect('my_stands')
    stand = get_object_or_404(Stand, slug=slug, owner=request.user)
    error = None
    if request.method == 'POST':
        try:
            lat = float(request.POST.get('latitude', ''))
            lng = float(request.POST.get('longitude', ''))
        except ValueError:
            error = _('Place the pin on the map before saving.')
        else:
            lo, hi = BIG_ISLAND_BOUNDS['lat']
            wlo, whi = BIG_ISLAND_BOUNDS['lng']
            if not (lo <= lat <= hi and wlo <= lng <= whi):
                error = _("That spot doesn't look like it's on the Big "
                          "Island — drag the pin to your stand and try again.")
            else:
                from decimal import Decimal
                stand.latitude = Decimal(f'{lat:.6f}')
                stand.longitude = Decimal(f'{lng:.6f}')
                stand.coords_source = Stand.CoordsSource.OWNER_PIN
                stand.updated_by = request.user
                stand.save(update_fields=['latitude', 'longitude',
                                          'coords_source', 'updated_by',
                                          'updated_at'])
                messages.success(request, _(
                    'Map pin for %(name)s has been saved.')
                    % {'name': stand.name})
                return redirect('my_stands')
    return render(request, 'stands/edit_pin.html',
                  {'stand': stand, 'error': error})


MAX_GALLERY_PHOTOS = 6


def _moderate_and_store(request, stand, content, caption):
    """Create the Photo row and run the moderation chain on it."""
    from django.utils import timezone

    from .models import Photo
    from .moderation import moderate_image

    photo = Photo(stand=stand, caption=caption,
                  uploaded_by=request.user,
                  sort_order=stand.photos.count())
    photo.image.save('photo.jpg', content, save=False)

    verdict, detail = moderate_image(content.file.getvalue()
                                     if hasattr(content.file, 'getvalue')
                                     else bytes(content.read()))
    photo.moderation_detail = detail[:200]
    photo.moderated_at = timezone.now()
    if verdict == 'ok':
        photo.approved = True
        photo.moderation = Photo.Moderation.AUTO_APPROVED
    elif verdict == 'flagged':
        photo.moderation = Photo.Moderation.FLAGGED
    else:  # unavailable → pending, fail safe
        photo.moderation = Photo.Moderation.PENDING
    photo.save()

    if verdict != 'ok':
        admin_url = request.build_absolute_uri(
            reverse('admin:stands_photo_change', args=[photo.pk]))
        mail_admins(
            subject=f'Photo needs review: {stand.name}',
            message=(f'Stand: {stand.name}\nOutcome: {verdict}\n'
                     f'Detail: {detail}\nUploaded by: {request.user}\n\n'
                     f'Review it here: {admin_url}'),
            fail_silently=True)
    return photo, verdict


def stand_photos(request, slug):
    """Owner dashboard slice 5: photo gallery management.

    Upload (processed + moderated), delete, and pick the list thumbnail.
    Display gate stays Photo.approved; clean moderation auto-approves.
    """
    from django.core.exceptions import ValidationError

    from .images import process_upload

    if not request.user.is_authenticated:
        return redirect('my_stands')
    stand = get_object_or_404(Stand, slug=slug, owner=request.user)

    from .forms import PhotoCaptionForm

    if request.method == 'POST':
        upload = request.FILES.get('photo')
        caption_form = PhotoCaptionForm(request.POST)
        if not upload:
            messages.error(request, _('Pick a photo to upload first.'))
        elif stand.photos.count() >= MAX_GALLERY_PHOTOS:
            messages.error(request, _(
                'Your gallery is full (%(n)s photos) — delete one to make '
                'room.') % {'n': MAX_GALLERY_PHOTOS})
        elif not caption_form.is_valid():
            # Caption text moderation (denylist/threat) before any image work.
            messages.error(request, caption_form.errors['caption'][0])
        else:
            try:
                content, _name = process_upload(upload)
            except ValidationError as e:
                messages.error(request, e.message)
            else:
                _photo, verdict = _moderate_and_store(
                    request, stand,
                    content, caption_form.cleaned_data['caption'])
                if verdict == 'ok':
                    messages.success(request, _(
                        'Photo added — it is live on your listing.'))
                else:
                    messages.info(request, _(
                        "Photo uploaded. It needs a quick review before it "
                        "shows publicly — we've been notified and it "
                        "usually doesn't take long."))
        return redirect('stand_photos', slug=stand.slug)

    return render(request, 'stands/photos.html', {
        'stand': stand,
        'photos': stand.photos.all(),
        'max_photos': MAX_GALLERY_PHOTOS,
    })


def delete_photo(request, slug, pk):
    if not request.user.is_authenticated:
        return redirect('my_stands')
    stand = get_object_or_404(Stand, slug=slug, owner=request.user)
    photo = get_object_or_404(stand.photos, pk=pk)
    if request.method == 'POST':
        if stand.list_photo_id == photo.pk:
            stand.list_thumb.delete(save=False)
            stand.list_photo = None
            stand.save(update_fields=['list_thumb', 'list_photo',
                                      'updated_at'])
        photo.image.delete(save=False)
        photo.delete()
        messages.success(request, _('Photo deleted.'))
    return redirect('stand_photos', slug=stand.slug)


def set_list_photo(request, slug, pk):
    """Generate the square list-view thumbnail from a chosen gallery photo."""
    from .images import make_list_thumb

    if not request.user.is_authenticated:
        return redirect('my_stands')
    stand = get_object_or_404(Stand, slug=slug, owner=request.user)
    photo = get_object_or_404(stand.photos, pk=pk, approved=True)
    if request.method == 'POST':
        content, _name = make_list_thumb(photo.image)
        stand.list_thumb.delete(save=False)
        stand.list_thumb.save('thumb.jpg', content, save=False)
        stand.list_photo = photo
        stand.updated_by = request.user
        stand.save(update_fields=['list_thumb', 'list_photo', 'updated_by',
                                  'updated_at'])
        messages.success(request, _(
            'That photo is now your thumbnail on the list page.'))
    return redirect('stand_photos', slug=stand.slug)


def edit_photo_caption(request, slug, pk):
    """Edit a gallery photo's caption (= public figcaption + image alt) after
    upload. Same text moderation as the upload path and the stand free-text
    fields, via PhotoCaptionForm. An empty caption clears it."""
    from .forms import PhotoCaptionForm

    if not request.user.is_authenticated:
        return redirect('my_stands')
    stand = get_object_or_404(Stand, slug=slug, owner=request.user)
    photo = get_object_or_404(stand.photos, pk=pk)
    if request.method == 'POST':
        form = PhotoCaptionForm(request.POST)
        if form.is_valid():
            photo.caption = form.cleaned_data['caption']
            photo.save(update_fields=['caption'])
            messages.success(request, _('Caption updated.'))
        else:
            messages.error(request, form.errors['caption'][0])
    return redirect('stand_photos', slug=stand.slug)


def move_photo(request, slug, pk):
    """Reorder a gallery photo up/down. Swaps with its neighbour, then
    renumbers ALL of the stand's photos sequentially — this self-heals legacy
    rows that share sort_order=0. Public detail + dashboard both order by
    sort_order, so the new order shows everywhere."""
    from .models import Photo

    if not request.user.is_authenticated:
        return redirect('my_stands')
    stand = get_object_or_404(Stand, slug=slug, owner=request.user)
    get_object_or_404(stand.photos, pk=pk)  # 404 if not this stand's photo
    if request.method == 'POST':
        direction = request.POST.get('direction')
        photos = list(stand.photos.all())  # Meta ordering: sort_order, id
        idx = next((i for i, p in enumerate(photos) if p.pk == pk), None)
        if idx is not None:
            swap = idx - 1 if direction == 'up' else (
                idx + 1 if direction == 'down' else None)
            if swap is not None and 0 <= swap < len(photos):
                photos[idx], photos[swap] = photos[swap], photos[idx]
        for i, p in enumerate(photos):
            p.sort_order = i
        Photo.objects.bulk_update(photos, ['sort_order'])
    return redirect('stand_photos', slug=stand.slug)
