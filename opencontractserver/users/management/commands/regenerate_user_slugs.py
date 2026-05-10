"""
Replace OAuth-sub-derived user slugs with handle-based slugs.

Social-login users received slugs derived from their OAuth ``username``
(e.g. ``google-oauth2114688257717759010643``) because ``User.save()``
previously used ``username`` as the slug base.  This command detects those
users and regenerates their slugs from their Reddit-style display handle.

Usage::

    python manage.py regenerate_user_slugs --dry-run
    python manage.py regenerate_user_slugs
"""

from __future__ import annotations

import logging
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from opencontractserver.shared.slug_utils import generate_unique_slug, sanitize_slug

logger = logging.getLogger(__name__)


def _is_oauth_derived_slug(username: str, slug: str) -> bool:
    """Return True when *slug* was derived from the OAuth *username*."""
    if not username or "|" not in username:
        return False
    sanitized = sanitize_slug(username, max_length=64)
    if not sanitized:
        return False
    return slug == sanitized or slug.startswith(sanitized + "-")


class Command(BaseCommand):
    help = (
        "Regenerate OAuth-sub-derived user slugs using the user's display handle. "
        "Only affects social/OAuth users whose current slug matches their sanitized "
        "username (i.e. the slug leaks the OAuth provider and account ID)."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would change without writing.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        User = get_user_model()
        dry_run: bool = options["dry_run"]

        candidates = (
            User.objects.filter(
                Q(is_social_user=True) | Q(username__contains="|"),
                slug__isnull=False,
                handle__isnull=False,
            )
            .exclude(username="Anonymous")
            .exclude(handle__exact="")
            .order_by("pk")
        )

        affected = [
            u
            for u in candidates.iterator()
            if _is_oauth_derived_slug(u.username or "", u.slug or "")
        ]

        self.stdout.write(
            f"regenerate_user_slugs: candidates={len(affected)}"
            + (" (dry-run)" if dry_run else "")
        )

        if not affected:
            return

        updated = 0
        with transaction.atomic():
            for user in affected:
                old_slug = user.slug
                scope_qs = User.objects.exclude(pk=user.pk)
                new_slug = generate_unique_slug(
                    base_value=user.handle or "user",
                    scope_qs=scope_qs,
                    slug_field="slug",
                    max_length=64,
                    fallback_prefix="user",
                )
                if dry_run:
                    self.stdout.write(
                        f"  user pk={user.pk} slug {old_slug!r} -> {new_slug!r}"
                    )
                else:
                    user.slug = new_slug
                    user.save(update_fields=["slug"])
                updated += 1

            if dry_run:
                transaction.set_rollback(True)

        verb = "would update" if dry_run else "updated"
        self.stdout.write(self.style.SUCCESS(f"{verb} {updated} user(s)."))
