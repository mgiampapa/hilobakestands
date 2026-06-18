import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from .models import Stand

logger = logging.getLogger(__name__)


def url_domain_blocked(url):
    """True if the URL's domain is classified as malware or adult content by
    Cloudflare's '1.1.1.3 for Families' resolver (blocked domains resolve to
    0.0.0.0). Queried over DNS-over-HTTPS (family.cloudflare-dns.com) so there's
    no extra dependency or raw-DNS plumbing.

    Fails OPEN on any network error: a submitted link is verification-gated
    anyway, so a transient DoH blip shouldn't reject a real stand. Domain-level
    (not per-path), which matches how the category data works.
    """
    host = (urllib.parse.urlparse(url).hostname or '').strip()
    if not host:
        return False
    query = urllib.parse.urlencode({'name': host, 'type': 'A'})
    req = urllib.request.Request(
        'https://family.cloudflare-dns.com/dns-query?' + query,
        headers={'Accept': 'application/dns-json'})
    try:
        with urllib.request.urlopen(req, timeout=4) as resp:
            payload = json.load(resp)
    except (urllib.error.URLError, TimeoutError, ValueError):
        logger.warning('Cloudflare family DoH unreachable; allowing %s', host)
        return False
    # Blocked domains are sinkholed to 0.0.0.0 (type 1 = A record) AND tagged
    # with Extended DNS Error 17 ("Filtered") in Comment. Match either signal —
    # robust if the sinkhole format ever changes.
    answers = payload.get('Answer') or []
    if any(a.get('type') == 1 and a.get('data') == '0.0.0.0' for a in answers):
        return True
    comment = payload.get('Comment')
    if isinstance(comment, list):
        comment = ' '.join(comment)
    return 'ede(17)' in (comment or '').lower()


_BLOCKED_TEXT_MSG = _(
    "Sorry — that contains language we can't accept. Please revise it.")


def _reject_if_blocked(*texts):
    """Raise if any text trips the denylist/threat filter (stands.textmod) —
    the always-on first layer of the TextModerator. Applied to every submitter
    free-text field (name, description, address)."""
    from .textmod import text_blocked
    if text_blocked(*texts):
        raise ValidationError(_BLOCKED_TEXT_MSG)


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


_FB_INVALID = _('That does not look like a valid Facebook page — paste the '
                'page link, e.g. facebook.com/mybakestand.')


def normalize_facebook(value):
    """Parse any Facebook reference into a canonical full URL.

    Accepts a bare vanity name, a full/partial profile URL (any of
    facebook.com / fb.com / m.facebook.com / www., http(s) optional), a numeric
    `profile.php?id=NNN`, or a `pages/Name/NNN` link. Returns
    `https://www.facebook.com/...` or '' when blank.

    The URL is rebuilt from validated components — only matched characters are
    re-emitted — so nothing untrusted survives into the rendered href. Raises
    ValidationError on anything unrecognizable. Shared by the owner-edit and
    public-submit forms AND the spreadsheet importer (the original source of
    dirty Facebook data, which set the field directly and bypassed cleaning).
    """
    v = (value or '').strip()
    if not v:
        return ''
    v = re.sub(r'^https?://', '', v, flags=re.I)      # drop scheme
    v = re.sub(r'^(www\.|m\.)+', '', v, flags=re.I)    # drop www./m.
    for d in ('facebook.com', 'fb.com'):               # drop a known domain
        if v.lower().startswith(d):
            v = v[len(d):]
            break
    v = v.lstrip('/')
    base = 'https://www.facebook.com/'
    m = re.match(r'profile\.php\?id=(\d+)', v, flags=re.I)        # numeric id
    if m:
        return base + 'profile.php?id=' + m.group(1)
    m = re.match(r'pages/([A-Za-z0-9.\-]{1,80})/(\d+)', v, flags=re.I)  # /pages/
    if m:
        return base + 'pages/' + m.group(1) + '/' + m.group(2)
    vanity = v.split('/')[0].split('?')[0].lstrip('@')           # vanity name
    if re.fullmatch(r'[A-Za-z0-9.\-]{1,80}', vanity) and vanity.lower() != 'profile.php':
        return base + vanity
    raise ValidationError(_FB_INVALID)


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
        # FB is messier than IG/TikTok (vanity names, numeric profile.php?id,
        # /pages/Name/ID) — normalize to a full canonical URL stored as-is.
        return normalize_facebook(self.cleaned_data.get('facebook'))

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
        v = v[:2000]
        _reject_if_blocked(v)
        return v

    def clean_website(self):
        url = self.cleaned_data.get('website') or ''
        if url and url_domain_blocked(url):
            raise ValidationError(
                _('That website is flagged as adult or unsafe content, so it '
                  "can't be added. Leave it blank or use a different link."))
        return url


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

    # Bare domain OK, assume http:// (see StandSubmitForm).
    website = forms.URLField(
        required=False, assume_scheme='http', label=_('Website'))

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

    # Accept a bare domain (or domain/path) and assume http:// — no reason to
    # make people type the scheme; their server redirects to https if it wants.
    website = forms.URLField(
        required=False, assume_scheme='http', label=_('Website'))

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
            'categories': _('Select all that apply.'),
        }

    def clean_name(self):
        v = (self.cleaned_data.get('name') or '').strip()
        v = ''.join(ch for ch in v if ch == '\t' or ord(ch) >= 32)  # one line
        if not v:
            raise ValidationError(_('Please enter the stand name.'))
        v = v[:120]
        _reject_if_blocked(v)
        return v

    def clean_street_address(self):
        v = (self.cleaned_data.get('street_address') or '').strip()
        v = ''.join(ch for ch in v if ch == '\t' or ord(ch) >= 32)
        v = v[:200]
        _reject_if_blocked(v)
        return v
