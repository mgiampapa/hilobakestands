"""Backfill: every stand that exists before public submissions launch was
curated by Matthew (seed / import / admin), so mark them all VERIFIED. New
public submissions (v1.1 Slice 2) will be created at the model's fail-safe
UNVERIFIED default instead. Public view is unchanged on deploy."""
from django.db import migrations
from django.utils import timezone


def mark_existing_verified(apps, schema_editor):
    Stand = apps.get_model('stands', 'Stand')
    Stand.objects.all().update(
        verification='verified',
        created_via='admin_seed',
        verified_via='admin',
        verified_at=timezone.now(),
    )


def unmark(apps, schema_editor):
    # Reverse: undo the backfill (return to the fail-safe default state).
    Stand = apps.get_model('stands', 'Stand')
    Stand.objects.all().update(
        verification='unverified', verified_via='', verified_at=None)


class Migration(migrations.Migration):
    dependencies = [
        ('stands', '0006_stand_auto_hidden_stand_created_via_and_more'),
    ]
    operations = [migrations.RunPython(mark_existing_verified, unmark)]
