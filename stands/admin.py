from django.conf import settings
from django.contrib import admin
from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from .models import (Category, ClaimRequest, DayOverride, PaymentMethod,
                     Photo, Report, Stand, WeeklyHours)

NEEDS_REVIEW_BELOW = 70  # validation_score threshold for admin attention
# Note: users render by EMAIL in the admin via the User.__str__ patch in
# stands/apps.py (owner, created_by, updated_by, photo uploaded_by, etc.).


class NeedsReviewFilter(admin.SimpleListFilter):
    title = 'review status'
    parameter_name = 'review'

    def lookups(self, request, model_admin):
        return [('needs_review', f'Needs review (score < {NEEDS_REVIEW_BELOW})'),
                ('ok', 'Score OK')]

    def queryset(self, request, queryset):
        if self.value() == 'needs_review':
            return queryset.filter(validation_score__lt=NEEDS_REVIEW_BELOW)
        if self.value() == 'ok':
            return queryset.filter(validation_score__gte=NEEDS_REVIEW_BELOW)
        return queryset


class WeeklyHoursInline(admin.TabularInline):
    model = WeeklyHours
    extra = 0


class DayOverrideInline(admin.TabularInline):
    model = DayOverride
    extra = 0


class PhotoInline(admin.TabularInline):
    model = Photo
    extra = 0


@admin.register(Stand)
class StandAdmin(admin.ModelAdmin):
    list_display = ('name', 'location_type', 'status', 'verified_badge',
                    'attendance', 'score_badge', 'open_reports', 'owner',
                    'updated_at')
    list_filter = (NeedsReviewFilter, 'verification', 'status', 'created_via',
                   'location_type', 'attendance', 'categories')
    search_fields = ('name', 'description', 'street_address')
    ordering = ('validation_score', 'name')  # lowest scores first
    prepopulated_fields = {'slug': ('name',)}
    filter_horizontal = ('categories', 'payment_methods')
    inlines = [WeeklyHoursInline, DayOverrideInline, PhotoInline]
    readonly_fields = ('claim_link', 'claimed_at', 'verified_at', 'verified_via',
                       'submitted_at', 'created_at', 'created_by', 'updated_at',
                       'updated_by')
    actions = ['mark_verified', 'publish', 'unpublish',
               'generate_claim_tokens', 'download_claim_flyers']

    def get_changeform_initial_data(self, request):
        # Admin-created stands are a trusted path → default the Add form to
        # Verified (the model default is the fail-safe Unverified for public
        # submissions). Admin can still switch it to Unverified.
        return {'verification': Stand.Verification.VERIFIED}

    def get_queryset(self, request):
        return (super().get_queryset(request)
                .annotate(unhandled_reports=Count(
                    'reports', filter=Q(reports__handled=False))))

    @admin.display(description='Score', ordering='validation_score')
    def score_badge(self, obj):
        color = ('#b91c1c' if obj.validation_score < NEEDS_REVIEW_BELOW
                 else '#b45309' if obj.validation_score < 100 else '#15803d')
        return format_html(
            '<b style="color:{}">{}</b>{}', color, obj.validation_score,
            ' ⚠' if obj.validation_score < NEEDS_REVIEW_BELOW else '')

    @admin.display(description='Open reports', ordering='unhandled_reports')
    def open_reports(self, obj):
        return obj.unhandled_reports or ''

    @admin.display(description='Verified', ordering='verification')
    def verified_badge(self, obj):
        if obj.verification == Stand.Verification.VERIFIED:
            return format_html('<b style="color:#15803d">✓ verified</b>')
        return format_html('<span style="color:#b45309">… unverified</span>')

    @admin.display(description='Claim link')
    def claim_link(self, obj):
        """Plain copyable URL — QR later, but works as-is over SMS/email."""
        if obj.owner:
            return format_html('Claimed by <b>{}</b> at {:%Y-%m-%d %H:%M}',
                               obj.owner, obj.claimed_at or obj.updated_at)
        if not obj.pk:
            return '—'
        gen_url = reverse('admin:stands_stand_generate_claim_token',
                          args=[obj.pk])
        flyer_url = reverse('admin:stands_stand_claim_flyer', args=[obj.pk])
        if not obj.claim_token:
            return format_html(
                '<a class="button" href="{}">Generate claim link</a> '
                '<a class="button" href="{}">Download flyer (PDF)</a>',
                gen_url, flyer_url)
        url = settings.SITE_BASE_URL + obj.claim_url_path
        return format_html(
            '<input type="text" readonly value="{}" size="60" '
            'onclick="this.select()"> '
            '<a class="button" href="{}">Download flyer (PDF)</a> '
            '<a class="button" href="{}">Regenerate</a>',
            url, flyer_url, gen_url)

    def get_urls(self):
        from django.urls import path as url_path
        extra = [
            url_path('<int:pk>/generate-claim-token/',
                     self.admin_site.admin_view(self.generate_single_token),
                     name='stands_stand_generate_claim_token'),
            url_path('<int:pk>/claim-flyer/',
                     self.admin_site.admin_view(self.single_claim_flyer),
                     name='stands_stand_claim_flyer'),
        ]
        return extra + super().get_urls()

    def _flyer_response(self, request, stands, filename):
        """Shared by single + bulk: token up any unowned stand lacking one,
        skip owned stands, return the PDF."""
        from django.http import HttpResponse
        from .flyers import build_flyer_pdf
        ready, skipped = [], 0
        for stand in stands:
            if stand.owner:
                skipped += 1
                continue
            if not stand.claim_token:
                stand.generate_claim_token()
                stand.save(update_fields=['claim_token', 'updated_at'])
            ready.append(stand)
        if skipped:
            self.message_user(
                request, f'{skipped} stand(s) skipped (already claimed).',
                level='WARNING')
        if not ready:
            self.message_user(request, 'Nothing to print — all selected '
                              'stands are already claimed.', level='WARNING')
            from django.http import HttpResponseRedirect
            return HttpResponseRedirect('../../')
        pdf = build_flyer_pdf(ready)
        resp = HttpResponse(pdf, content_type='application/pdf')
        resp['Content-Disposition'] = f'attachment; filename="{filename}"'
        return resp

    def single_claim_flyer(self, request, pk):
        stand = Stand.objects.get(pk=pk)
        if not self.has_change_permission(request, stand):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied
        return self._flyer_response(
            request, [stand], f'claim-flyer-{stand.slug}.pdf')

    @admin.action(description='Download claim flyers (PDF, unowned only)')
    def download_claim_flyers(self, request, queryset):
        return self._flyer_response(
            request, list(queryset.order_by('name')), 'claim-flyers.pdf')

    def generate_single_token(self, request, pk):
        """One-click token for a single stand (change-page button)."""
        from django.http import HttpResponseRedirect
        from django.urls import reverse as url_reverse
        stand = Stand.objects.get(pk=pk)
        if not self.has_change_permission(request, stand):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied
        if stand.owner:
            self.message_user(request, f'{stand.name} is already claimed.',
                              level='WARNING')
        else:
            stand.generate_claim_token()
            stand.save(update_fields=['claim_token', 'updated_at'])
            self.message_user(
                request, f'Claim link ready for {stand.name} — copy it from '
                'the "Claim link" field below.')
        return HttpResponseRedirect(url_reverse(
            'admin:stands_stand_change', args=[pk]))

    @admin.action(description='Generate claim links (unowned stands only)')
    def generate_claim_tokens(self, request, queryset):
        from django.utils.html import format_html_join
        made, skipped = [], 0
        for stand in queryset.order_by('name'):
            if stand.owner:
                skipped += 1
                continue
            stand.generate_claim_token()
            stand.save(update_fields=['claim_token', 'updated_at'])
            made.append(stand)
        if made:
            links = format_html_join(
                '', '<div style="margin:2px 0"><b>{}</b>: '
                '<span style="user-select:all">{}</span></div>',
                ((s.name, settings.SITE_BASE_URL + s.claim_url_path)
                 for s in made))
            msg = format_html(
                '{} claim link(s) generated — copy from here:{}',
                len(made), links)
        else:
            msg = 'No claim links generated.'
        if skipped:
            self.message_user(request,
                              f'{skipped} skipped (already claimed).',
                              level='WARNING')
        self.message_user(request, msg)

    @admin.action(description='Mark selected stands verified')
    def mark_verified(self, request, queryset):
        n = queryset.update(verification=Stand.Verification.VERIFIED,
                            verified_via=Stand.VerifiedVia.ADMIN,
                            verified_at=timezone.now())
        self.message_user(request, f'{n} stand(s) marked verified.')

    @admin.action(description='Publish selected stands')
    def publish(self, request, queryset):
        queryset.update(status='published')

    @admin.action(description='Move selected stands to draft')
    def unpublish(self, request, queryset):
        queryset.update(status='draft')

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        obj.updated_by = request.user
        # Stamp verification metadata when an admin sets/leaves it Verified.
        if (obj.verification == Stand.Verification.VERIFIED
                and not obj.verified_at):
            obj.verified_via = obj.verified_via or Stand.VerifiedVia.ADMIN
            obj.verified_at = timezone.now()
        super().save_model(request, obj, form, change)

    class Media:
        css = {'all': (
            'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css',)}
        js = (
            'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js',
            'stands/admin_map_pin.js')


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ('stand', 'created_at', 'handled', 'message')
    list_filter = ('handled',)
    actions = ['mark_handled']

    @admin.action(description='Mark selected reports handled')
    def mark_handled(self, request, queryset):
        queryset.update(handled=True)


@admin.register(ClaimRequest)
class ClaimRequestAdmin(admin.ModelAdmin):
    list_display = ('stand', 'user', 'status', 'created_at')
    list_filter = ('status',)


@admin.register(Photo)
class PhotoAdmin(admin.ModelAdmin):
    list_display = ('stand', 'preview', 'caption', 'approved', 'moderation',
                    'moderation_detail', 'uploaded_by', 'created_at')
    list_filter = ('approved', 'moderation')
    readonly_fields = ('moderation', 'moderation_detail', 'moderated_at',
                       'preview')
    actions = ['approve_photos']

    @admin.display(description='Preview')
    def preview(self, obj):
        from django.utils.html import format_html
        if not obj.image:
            return '—'
        return format_html('<img src="{}" style="max-height:80px; '
                           'border-radius:6px">', obj.image.url)

    @admin.action(description='Approve selected photos (manual review)')
    def approve_photos(self, request, queryset):
        from django.utils import timezone
        n = queryset.update(approved=True,
                            moderation=Photo.Moderation.MANUAL,
                            moderated_at=timezone.now())
        self.message_user(request, f'{n} photo(s) approved.')


admin.site.register(Category)
admin.site.register(PaymentMethod)
admin.site.register(DayOverride)

admin.site.site_header = 'HiloBakeStands Admin'
admin.site.site_title = 'HiloBakeStands'
