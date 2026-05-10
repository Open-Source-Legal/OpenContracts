# Data migration backfilling auto-assigned display handles for existing users.
# Uses ``opencontractserver.users.handle_generator`` so the same logic powers
# ad-hoc reruns via the ``regenerate_user_handles`` management command if the
# curated word list grows.

from django.db import migrations
from django.db.models import Q


def backfill_handles(apps, schema_editor):
    """Assign a unique handle to every user lacking one."""
    # NOTE: Deliberately imports live application code (not a historical
    # snapshot). Safe because ``generate_handle`` is pure logic with a
    # stable signature — if the module is ever moved or renamed, update
    # this import accordingly.
    from opencontractserver.users.handle_generator import generate_handle

    User = apps.get_model("users", "User")

    # Operate on the historical model so the migration is safe under
    # ``--fake`` / ``--check`` and respects the active schema editor's DB.
    db = schema_editor.connection.alias

    # The django-guardian Anonymous user is a system account that never
    # surfaces to other users — never assign it a handle so this migration
    # stays in sync with the User.save() / management-command exclusions.
    missing = (
        User.objects.using(db)
        .filter(Q(handle__isnull=True) | Q(handle__exact=""))
        .exclude(username="Anonymous")
    )
    for user in missing.iterator():
        # ``generate_handle`` checks uniqueness against the current snapshot of
        # the table; we exclude this user's own pk so it doesn't see its own
        # (still-empty) row as a collision target. ``RunPython`` wraps the
        # whole migration in a single transaction; under PostgreSQL READ
        # COMMITTED the connection sees its own uncommitted writes, so each
        # ``user.save()`` is visible to the next iteration's
        # ``generate_handle`` query without a per-row commit.
        scope_qs = User.objects.using(db).exclude(pk=user.pk)
        user.handle = generate_handle(scope_qs=scope_qs)
        user.save(update_fields=["handle"])


def reverse_backfill(apps, schema_editor):
    """Clear all auto-assigned handles. Reversible counterpart of ``backfill_handles``."""
    User = apps.get_model("users", "User")
    db = schema_editor.connection.alias
    User.objects.using(db).update(handle=None)


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0027_user_handle"),
    ]

    operations = [
        migrations.RunPython(backfill_handles, reverse_code=reverse_backfill),
    ]
