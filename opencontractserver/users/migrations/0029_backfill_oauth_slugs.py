# Data migration: replace OAuth-sub-derived user slugs with handle-based slugs.
#
# When a social/OAuth user was first created, User.save() used ``username``
# (the raw provider sub, e.g. ``google-oauth2|114688...``) as the slug base.
# sanitize_slug() stripped the ``|`` but kept the provider prefix, producing
# slugs like ``google-oauth2114688257717759010643`` that were then stored
# in the public ``slug`` field and surfaced on the leaderboard.
#
# This migration detects those slugs — users where ``|`` appears in username
# and sanitize_slug(username) matches the stored slug — and regenerates them
# from the user's handle (already backfilled by 0028).

from django.db import migrations
from django.db.models import Q


def _is_oauth_derived_slug(username: str, slug: str) -> bool:
    """Return True when ``slug`` was clearly derived from the OAuth ``username``."""
    if not username or "|" not in username:
        return False
    from opencontractserver.shared.slug_utils import sanitize_slug

    sanitized = sanitize_slug(username, max_length=64)
    if not sanitized:
        return False
    # Direct match (no collision suffix) or slug begins with the sanitized
    # prefix (collision-suffixed variant like ``google-oauth2...-2``).
    return slug == sanitized or slug.startswith(sanitized + "-")


def backfill_oauth_slugs(apps, schema_editor):
    from opencontractserver.shared.slug_utils import generate_unique_slug

    User = apps.get_model("users", "User")
    db = schema_editor.connection.alias

    # Candidates: social or pipe-username users who already have a handle to
    # use as the new slug base.
    candidates = (
        User.objects.using(db)
        .exclude(username="Anonymous")
        .filter(
            Q(is_social_user=True) | Q(username__contains="|"),
            slug__isnull=False,
            handle__isnull=False,
        )
        .exclude(handle__exact="")
    )

    for user in candidates.iterator():
        if not _is_oauth_derived_slug(user.username or "", user.slug or ""):
            continue

        scope_qs = User.objects.using(db).exclude(pk=user.pk)
        new_slug = generate_unique_slug(
            base_value=user.handle,
            scope_qs=scope_qs,
            slug_field="slug",
            max_length=64,
            fallback_prefix="user",
        )
        user.slug = new_slug
        user.save(update_fields=["slug"])


def reverse_backfill(apps, schema_editor):
    # The original OAuth-derived slugs are unrecoverable without keeping a
    # copy; this reverse is intentionally a no-op.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0028_backfill_user_handles"),
    ]

    operations = [
        migrations.RunPython(backfill_oauth_slugs, reverse_code=reverse_backfill),
    ]
