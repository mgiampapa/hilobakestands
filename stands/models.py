from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _


class Category(models.Model):
    """Food tags: baked goods, plate lunch, shave ice..."""
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=60, unique=True, blank=True)

    class Meta:
        verbose_name_plural = 'categories'
        ordering = ['name']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class PaymentMethod(models.Model):
    """Cash, PayPal, Venmo, CashApp, Credit card."""
    name = models.CharField(max_length=30, unique=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name


class Stand(models.Model):
    class LocationType(models.TextChoices):
        BAKE_STAND = 'bake_stand', _('Bake Stand')
        FOOD_TRUCK = 'food_truck', _('Food Truck')
        POPUP = 'popup', _('Pop-up')
        FARM_STAND = 'farm_stand', _('Farm Stand')

    class Attendance(models.TextChoices):
        ATTENDED = 'attended', _('Attended')
        UNATTENDED = 'unattended', _('Unattended (honor stand)')

    class Status(models.TextChoices):
        DRAFT = 'draft', _('Draft')
        PUBLISHED = 'published', _('Published')
        DELISTED = 'delisted', _('Delisted')

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    location_type = models.CharField(max_length=20, choices=LocationType.choices)
    description = models.TextField(blank=True)
    categories = models.ManyToManyField(Category, blank=True, related_name='stands')

    street_address = models.CharField(max_length=200, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    class CoordsSource(models.TextChoices):
        # Precedence: owner pin > admin > geocoded. The geocode command may
        # only write coords when source is blank or GEOCODED — a human-placed
        # pin is never overwritten by automation.
        OWNER_PIN = 'owner_pin', _('Owner-placed pin')
        ADMIN = 'admin', _('Admin-placed pin')
        GEOCODED = 'geocoded', _('Auto-geocoded from address')

    coords_source = models.CharField(
        max_length=10, choices=CoordsSource.choices, blank=True,
        help_text=_('Where the coordinates came from. Human-placed pins are '
                    'never overwritten by the geocoder.'))
    geocode_precision = models.CharField(
        max_length=30, blank=True,
        help_text=_('Nominatim result type (house, street, hamlet...). '
                    'Rural addresses often resolve to street level only.'))
    geocoded_at = models.DateTimeField(null=True, blank=True)

    attendance = models.CharField(
        max_length=12, choices=Attendance.choices, default=Attendance.ATTENDED,
        help_text=_('For unattended honor stands, hours mean "stocked," not staffed.'))
    irregular_hours_note = models.CharField(
        max_length=300, blank=True,
        help_text=_('Free text for patterns the weekly schedule cannot express. '
                    'Not used by the open-now filter.'))

    payment_methods = models.ManyToManyField(PaymentMethod, blank=True, related_name='stands')

    phone = models.CharField(max_length=30, blank=True)
    instagram = models.CharField(max_length=100, blank=True)
    facebook = models.CharField(max_length=255, blank=True)  # stored as full URL
    tiktok = models.CharField(max_length=100, blank=True)
    website = models.URLField(blank=True)
    email = models.EmailField(blank=True)

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    validation_score = models.PositiveSmallIntegerField(
        default=100,
        help_text=_('Drops when users report problems. Low score triggers admin '
                    'review — never automatic delisting.'))

    internal_notes = models.TextField(
        blank=True,
        help_text=_('Admin-only research notes; never shown publicly.'))

    # --- verification & submission provenance (v1.1) -----------------------
    # Trust is independent of `status` (visibility) and `owner` (control).
    # `created_by` (defined below) records WHO created/submitted the stand.
    class Verification(models.TextChoices):
        UNVERIFIED = 'unverified', _('Unverified')
        VERIFIED = 'verified', _('Verified')

    class CreatedVia(models.TextChoices):
        ADMIN_SEED = 'admin_seed', _('Admin / seed / import')
        PUBLIC_SUBMIT = 'public_submit', _('Public submission')

    class VerifiedVia(models.TextChoices):
        ADMIN = 'admin', _('Admin approval')
        CLAIM = 'claim', _('Owner claim')

    # Fail-SAFE default: a stand is UNVERIFIED until a trusted path proves it.
    # Trusted creation paths (admin save / seed / import) and the claim flow set
    # VERIFIED explicitly; only public submissions are left at this default.
    verification = models.CharField(
        max_length=10, choices=Verification.choices,
        default=Verification.UNVERIFIED,
        help_text=_('Verified stands appear in the default public view; '
                    'unverified (community-submitted) stands are hidden behind '
                    'a toggle.'))
    created_via = models.CharField(
        max_length=15, choices=CreatedVia.choices,
        default=CreatedVia.ADMIN_SEED,
        help_text=_('How this listing entered the system.'))
    submitted_at = models.DateTimeField(
        null=True, blank=True,
        help_text=_('When a public submission arrived (blank for admin/seed).'))
    verified_at = models.DateTimeField(null=True, blank=True, editable=False)
    verified_via = models.CharField(
        max_length=10, choices=VerifiedVia.choices, blank=True)
    auto_hidden = models.BooleanField(
        default=False,
        help_text=_('Reserved for the (deferred) report auto-hide: withholds a '
                    'stand from public view pending review. v1.1 uses manual '
                    'review, so this stays False for now.'))

    def mark_verified(self, via=VerifiedVia.ADMIN, save=True):
        """Flip to verified (used by the admin action and the claim flow)."""
        self.verification = self.Verification.VERIFIED
        self.verified_via = via
        self.verified_at = timezone.now()
        if save:
            self.save(update_fields=['verification', 'verified_via',
                                     'verified_at', 'updated_at'])

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='owned_stands')
    # One-time claim token (QR/SMS/email handout). NOT derived from the slug.
    # Burned (set to NULL) the moment the stand is claimed. editable=False
    # keeps it out of admin forms; admin shows a readonly claim URL instead.
    claim_token = models.CharField(
        max_length=64, null=True, blank=True, unique=True, editable=False)
    claimed_at = models.DateTimeField(null=True, blank=True, editable=False)

    def generate_claim_token(self):
        """Set (or rotate) the one-time claim token. Caller saves."""
        import secrets
        self.claim_token = secrets.token_urlsafe(12)
        return self.claim_token

    @property
    def claim_url_path(self):
        return reverse('stand_claim', args=[self.claim_token]) if self.claim_token else ''

    # List-view thumbnail: a square crop generated from one of the stand's
    # photos (owner picks which). Shown on the list cards at ~100px.
    list_thumb = models.ImageField(upload_to='thumbs/', null=True, blank=True,
                                   editable=False)
    list_photo = models.ForeignKey(
        'Photo', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='+',
        help_text=_('The gallery photo the list thumbnail was made from.'))

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+')
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+')

    class Meta:
        ordering = ['name']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('stand_detail', kwargs={'slug': self.slug})

    # --- hours -------------------------------------------------------------

    def todays_override(self):
        today = timezone.localdate()
        return self.day_overrides.filter(date=today).first()

    def is_open_now(self):
        """Weekly schedule + today's override. Free-text notes never count."""
        now = timezone.localtime()
        override = self.todays_override()
        if override is not None:
            if not override.is_open:
                return False
            if override.open_time is None:
                return True  # marked open with no times = open all day
            close = override.close_time or now.time().max
            return override.open_time <= now.time() <= close
        return self.weekly_hours.filter(
            weekday=now.weekday(),
            open_time__lte=now.time(),
            close_time__gte=now.time(),
        ).exists()

    def osm_embed_url(self):
        if self.latitude is None or self.longitude is None:
            return ''
        from decimal import Decimal
        d = Decimal('0.005')
        return (f'https://www.openstreetmap.org/export/embed.html'
                f'?bbox={self.longitude - d}%2C{self.latitude - d}'
                f'%2C{self.longitude + d}%2C{self.latitude + d}'
                f'&layer=mapnik&marker={self.latitude}%2C{self.longitude}')

    def directions_links(self):
        if self.latitude is None or self.longitude is None:
            return {}
        lat, lng = self.latitude, self.longitude
        return {
            'Google Maps': f'https://www.google.com/maps/dir/?api=1&destination={lat},{lng}',
            'Apple Maps': f'https://maps.apple.com/?daddr={lat},{lng}',
            'Waze': f'https://waze.com/ul?ll={lat},{lng}&navigate=yes',
        }


class WeeklyHours(models.Model):
    WEEKDAYS = [
        (0, _('Monday')), (1, _('Tuesday')), (2, _('Wednesday')), (3, _('Thursday')),
        (4, _('Friday')), (5, _('Saturday')), (6, _('Sunday')),
    ]
    stand = models.ForeignKey(Stand, on_delete=models.CASCADE, related_name='weekly_hours')
    weekday = models.PositiveSmallIntegerField(choices=WEEKDAYS)
    open_time = models.TimeField()
    close_time = models.TimeField()

    class Meta:
        verbose_name_plural = 'weekly hours'
        ordering = ['weekday', 'open_time']

    def __str__(self):
        return f'{self.stand} {self.get_weekday_display()} {self.open_time}-{self.close_time}'


class DayOverride(models.Model):
    """Owner's 'we're open/closed today' toggle. Wins over the weekly schedule."""
    stand = models.ForeignKey(Stand, on_delete=models.CASCADE, related_name='day_overrides')
    date = models.DateField(default=timezone.localdate)
    is_open = models.BooleanField(default=True)
    open_time = models.TimeField(null=True, blank=True)
    close_time = models.TimeField(null=True, blank=True)
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('stand', 'date')]
        ordering = ['-date']

    def __str__(self):
        state = 'open' if self.is_open else 'closed'
        return f'{self.stand} {self.date}: {state}'


class Photo(models.Model):
    class Moderation(models.TextChoices):
        PENDING = 'pending', _('Pending review')
        AUTO_APPROVED = 'auto', _('Auto-approved (moderation passed)')
        FLAGGED = 'flagged', _('Flagged by moderation')
        MANUAL = 'manual', _('Manually reviewed')

    stand = models.ForeignKey(Stand, on_delete=models.CASCADE, related_name='photos')
    image = models.ImageField(upload_to='stands/%Y/%m/')
    caption = models.CharField(max_length=200, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    approved = models.BooleanField(default=False, help_text=_('Manual approval before display.'))
    moderation = models.CharField(
        max_length=10, choices=Moderation.choices, default=Moderation.PENDING,
        help_text=_('Automated moderation outcome. "approved" is the display '
                    'gate; this records how it was decided.'))
    moderation_detail = models.CharField(
        max_length=200, blank=True,
        help_text=_('Scores/categories from the moderation backend.'))
    moderated_at = models.DateTimeField(null=True, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['sort_order', 'id']

    def __str__(self):
        return f'Photo of {self.stand}'


class Report(models.Model):
    """User feedback: closed, moved, gone, wrong info. Lowers validation score."""
    stand = models.ForeignKey(Stand, on_delete=models.CASCADE, related_name='reports')
    message = models.TextField()
    contact = models.CharField(max_length=200, blank=True, help_text=_('Optional email/phone.'))
    created_at = models.DateTimeField(auto_now_add=True)
    handled = models.BooleanField(default=False)
    handled_note = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Report on {self.stand} ({self.created_at:%Y-%m-%d})'


class ClaimRequest(models.Model):
    """Owner-initiated claim. Verified in person (SPEC open question 3)."""
    class Status(models.TextChoices):
        PENDING = 'pending', _('Pending')
        VERIFIED = 'verified', _('Verified in person')
        REJECTED = 'rejected', _('Rejected')

    stand = models.ForeignKey(Stand, on_delete=models.CASCADE, related_name='claims')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    message = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user} claims {self.stand} ({self.status})'
