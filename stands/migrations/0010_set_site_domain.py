"""Point the django.contrib.sites Site row at the real domain.

The sitemap framework builds absolute URLs from the current Site's domain, and a
fresh sites install defaults to 'example.com'. Set it from SITE_BASE_URL so
/sitemap.xml emits correct links (and allauth's Site usage is correct too).
Idempotent — update_or_create handles both the default row and a missing one.
"""
from urllib.parse import urlparse

from django.conf import settings
from django.db import migrations


def set_site(apps, schema_editor):
    Site = apps.get_model('sites', 'Site')
    host = urlparse(settings.SITE_BASE_URL).netloc or 'hilobakestands.com'
    Site.objects.update_or_create(
        pk=getattr(settings, 'SITE_ID', 1),
        defaults={'domain': host, 'name': 'HiloBakeStands'})


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('stands', '0009_stand_threads'),
        ('sites', '0001_initial'),
    ]
    operations = [migrations.RunPython(set_site, noop)]
