"""Facebook is now stored as a full canonical URL (https://www.facebook.com/...)
instead of a bare handle, so detail.html can render it directly and the messy
shapes (numeric profile.php?id=NNN, /pages/Name/NNN) survive round-tripping.

Two steps:
  1. Widen the column 100 -> 255 (full URLs are longer than handles).
  2. Backfill existing values through normalize_facebook(). Existing data was
     hand-cleaned vanity handles, so this just prefixes the domain. Idempotent:
     anything already starting with http is left alone; anything unparseable is
     left as-is (never crash the migration on legacy data)."""
from django.db import migrations, models


def to_full_urls(apps, schema_editor):
    from stands.forms import normalize_facebook
    from django.core.exceptions import ValidationError
    Stand = apps.get_model('stands', 'Stand')
    for stand in Stand.objects.exclude(facebook='').exclude(facebook__startswith='http'):
        try:
            url = normalize_facebook(stand.facebook)
        except ValidationError:
            continue  # leave odd legacy values untouched for manual review
        if url and url != stand.facebook:
            stand.facebook = url
            stand.save(update_fields=['facebook'])


def noop_reverse(apps, schema_editor):
    # One-way data transform; reversing the schema width is handled below.
    # We don't strip URLs back to handles (lossy for profile.php/pages shapes).
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('stands', '0007_mark_existing_stands_verified'),
    ]
    operations = [
        migrations.AlterField(
            model_name='stand',
            name='facebook',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.RunPython(to_full_urls, noop_reverse),
    ]
