import re

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from .models import Stand


def _clean_handle(value, domains, pattern, label):
    """Normalize a social handle. Accepts '@name', a full profile URL, or a
    bare name; returns just the name. Domains are matched case-insensitively.

    Output is whitelisted against `pattern` — these values end up inside
    hrefs like https://instagram.com/<handle> on the public detail page, so
    nothing but plain handle characters may survive.
    """
    v = (value or '').strip()
    if not v:
        return ''
    v = re.sub(r'^https?://', '', v, flags=re.I)
    v = re.sub(r'^www\.', '', v, flags=re.I)
    for d in domains:
        if v.lower().startswith(d):
            v = v[len(d):]
            break
    v = v.lstrip('/').split('/')[0].split('?')[0].strip().lstrip('@')
    if not re.fullmatch(pattern, v):
        raise ValidationError(
            _('That does not look like a valid %(label)s — use just the '
              'name, e.g. @mybakestand.') % {'label': label})
    return v


class SanitizedStandFieldsMixin:
    """Input sanitization shared by the owner-edit and public-submit forms.
    Social handles are whitelisted to handle characters (they get interpolated
    into hrefs on the public page), phone is restricted to dial characters, and
    control characters are stripped from free text. Output relies on Django's
    autoescaping."""

    def clean_instagram(self):
        return _clean_handle(self.cleaned_data.get('instagram'),
                             ['instagram.com', 'instagr.am'],
                             r'[A-Za-z0-9._]{1,30}', _('Instagram handle'))

    def clean_tiktok(self):
        return _clean_handle(self.cleaned_data.get('tiktok'),
                             ['tiktok.com'],
                             r'[A-Za-z0-9._]{1,24}', _('TikTok handle'))

    def clean_facebook(self):
        # FB vanity URLs allow dots and hyphens; numeric page IDs too.
        return _clean_handle(self.cleaned_data.get('facebook'),
                             ['facebook.com', 'fb.com', 'm.facebook.com'],
                             r'[A-Za-z0-9.\-]{1,80}', _('Facebook page'))

    def clean_phone(self):
        v = (self.cleaned_data.get('phone') or '').strip()
        if v and not re.fullmatch(r'[0-9+\-(). ]{7,30}', v):
            raise ValidationError(
                _('Phone numbers can only contain digits, spaces, and '
                  '+ - ( ) characters.'))
        return v

    def clean_description(self):
        v = self.cleaned_data.get('description') or ''
        # Strip control characters (keep newlines and tabs); cap length.
        v = ''.join(ch for ch in v if ch in '\n\r\t' or ord(ch) >= 32)
        return v[:2000]


class StandBasicInfoForm(SanitizedStandFieldsMixin, forms.ModelForm):
    """Owner dashboard: the fields an owner may edit directly.

    Owners control their own listing — including type and whether it's
    listed at all (self-service break/closing flow). Hiding a listed stand
    goes through a confirmation step in the view. Name/slug stay
    admin-managed because renames cascade into the slug/URL; the form
    links to the feedback form for that.

    All free-text inputs are sanitized here on the way IN (handles
    whitelisted to handle characters, phone to dial characters, control
    characters stripped from the description); Django's autoescaping
    covers the way OUT.
    """

    # Owner-facing framing of Stand.Status: 'delisted' is an admin state
    # and never offered here.
    OWNER_STATUS_CHOICES = [
        (Stand.Status.PUBLISHED, _('Listed on the site')),
        (Stand.Status.DRAFT, _('Hidden — taking a break or closed')),
    ]

    class Meta:
        model = Stand
        fields = ['location_type', 'description', 'phone', 'instagram',
                  'facebook', 'tiktok', 'website', 'email',
                  'payment_methods', 'status']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 5, 'maxlength': 2000}),
            'payment_methods': forms.CheckboxSelectMultiple,
            'status': forms.RadioSelect,
        }
        labels = {
            'location_type': _('Type of stand'),
            'description': _('Description'),
            'phone': _('Phone'),
            'instagram': _('Instagram handle'),
            'facebook': _('Facebook page'),
            'tiktok': _('TikTok handle'),
            'website': _('Website'),
            'email': _('Email'),
            'payment_methods': _('Payment methods you accept'),
            'status': _('Visibility'),
        }
        help_texts = {
            'instagram': _('Handle or profile link — either works.'),
            'facebook': _('Page name or profile link — either works.'),
            'tiktok': _('Handle or profile link — either works.'),
            'website': _('Full address, starting with https://'),
            'email': _('Shown publicly on your listing.'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.status == Stand.Status.DELISTED:
            # Admin-delisted stands can't self-relist; talk to the admin.
            del self.fields['status']
        else:
            self.fields['status'].choices = self.OWNER_STATUS_CHOICES


class StandSubmitForm(SanitizedStandFieldsMixin, forms.ModelForm):
    """Public 'Submit a stand' form (Slice 2). A logged-in visitor proposes a
    new listing; it's created UNVERIFIED and published, pending Matthew's review
    or an owner claim. Reuses the same input sanitization as the owner form."""

    class Meta:
        model = Stand
        fields = ['name', 'location_type', 'description', 'street_address',
                  'attendance', 'categories', 'payment_methods',
                  'phone', 'instagram', 'facebook', 'tiktok', 'website', 'email']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 5, 'maxlength': 2000}),
            'categories': forms.CheckboxSelectMultiple,
            'payment_methods': forms.CheckboxSelectMultiple,
            'attendance': forms.RadioSelect,
        }
        labels = {
            'name': _('Stand name'),
            'location_type': _('Type'),
            'description': _('What do they sell?'),
            'street_address': _('Address or where to find it'),
            'attendance': _('Staffed or honor stand?'),
            'categories': _('Food categories'),
            'payment_methods': _('Payment accepted (if known)'),
            'instagram': _('Instagram'), 'facebook': _('Facebook'),
            'tiktok': _('TikTok'), 'website': _('Website'), 'email': _('Email'),
        }
        help_texts = {
            'description': _('A sentence or two is plenty.'),
            'street_address': _('A street address geocodes best; a landmark '
                                'works too — you can drop an exact pin next.'),
        }

    def clean_name(self):
        v = (self.cleaned_data.get('name') or '').strip()
        v = ''.join(ch for ch in v if ch == '\t' or ord(ch) >= 32)  # one line
        if not v:
            raise ValidationError(_('Please enter the stand name.'))
        return v[:120]

    def clean_street_address(self):
        v = (self.cleaned_data.get('street_address') or '').strip()
        v = ''.join(ch for ch in v if ch == '\t' or ord(ch) >= 32)
        return v[:200]
