"""XML sitemap for search engines.

Scope decision (Matthew, 2026-06-18): INCLUDE unverified stands. The existing
controls (login-gated submit, Turnstile, denylist, manual review off the email
notifications) plus low volume make this safe, and indexing community
submissions helps discovery. So the stand sitemap mirrors the public list's
visibility — published + not auto_hidden — and does NOT filter on verification.
Owner-only (/my/, /claim/) and draft/delisted stands are excluded.
"""
from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from .models import Stand


class StandSitemap(Sitemap):
    changefreq = 'weekly'
    priority = 0.7
    protocol = 'https'

    def items(self):
        return Stand.objects.filter(
            status=Stand.Status.PUBLISHED, auto_hidden=False)

    def lastmod(self, obj):
        return obj.updated_at

    # location() defaults to obj.get_absolute_url()


class StaticViewSitemap(Sitemap):
    changefreq = 'monthly'
    priority = 0.5
    protocol = 'https'

    def items(self):
        return ['stand_list', 'submit_stand', 'claim_your_stand']

    def location(self, name):
        return reverse(name)


sitemaps = {
    'stands': StandSitemap,
    'static': StaticViewSitemap,
}
