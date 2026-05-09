"""
Re-run Reddit-style handle assignment for users missing or eligible for a fresh
handle.

Use cases:
- The curated word list (``handle_wordlists.py``) grew and you want users who
  previously got a numeric-suffixed candidate to re-roll into a clean
  ``adjectiveNoun`` pair.
- A bulk import created users with ``handle=NULL`` (e.g. a fixture loaded with
  ``--no-signals``) and you need to backfill them without re-running the full
  data migration.

Usage::

    python manage.py regenerate_user_handles --dry-run
    python manage.py regenerate_user_handles                 # missing only
    python manage.py regenerate_user_handles --reroll-suffixed
    python manage.py regenerate_user_handles --reroll-all    # destructive
"""

from __future__ import annotations

import logging
import re
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from opencontractserver.users.handle_generator import generate_handle

logger = logging.getLogger(__name__)

# A "suffixed" handle ends in digits — those are the ones the generator
# produces only when the plain ``adjectiveNoun`` namespace was already taken.
_SUFFIXED_PATTERN = re.compile(r"\d+$")


class Command(BaseCommand):
    help = (
        "Assign auto-generated Reddit-style handles to users. "
        "By default only fills users with NULL/empty handles. Use "
        "--reroll-suffixed to additionally re-roll users whose handle ends "
        "in a numeric suffix (i.e. handed out during a collision)."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would change without writing.",
        )
        parser.add_argument(
            "--reroll-suffixed",
            action="store_true",
            help=(
                "Also re-roll users whose existing handle ends in digits. Use "
                "this after enlarging the curated word list."
            ),
        )
        parser.add_argument(
            "--reroll-all",
            action="store_true",
            help=(
                "Re-roll every user, dropping any existing handle. Destructive — "
                "previously surfaced handles change for every user."
            ),
        )

    def handle(self, *args: Any, **options: Any) -> None:
        User = get_user_model()
        dry_run: bool = options["dry_run"]
        reroll_suffixed: bool = options["reroll_suffixed"]
        reroll_all: bool = options["reroll_all"]

        missing = Q(handle__isnull=True) | Q(handle__exact="")
        if reroll_all:
            queryset = User.objects.all()
            mode = "all users"
        elif reroll_suffixed:
            queryset = User.objects.filter(missing | Q(handle__regex=r"\d+$"))
            mode = "suffixed + missing"
        else:
            queryset = User.objects.filter(missing)
            mode = "missing only"

        # The django-guardian Anonymous user is a system account that
        # never surfaces to other users; exclude it from every mode so the
        # backfill stays a no-op for it (and so test fixtures that create a
        # known number of users get the count they expect).
        queryset = queryset.exclude(username="Anonymous").order_by("pk")
        total = queryset.count()
        self.stdout.write(
            f"regenerate_user_handles: mode={mode}, candidates={total}"
            + (" (dry-run)" if dry_run else "")
        )

        if total == 0:
            return

        updated = 0
        with transaction.atomic():
            for user in queryset.iterator():
                old_handle = user.handle
                rerolling = reroll_all or (
                    reroll_suffixed
                    and user.handle
                    and _SUFFIXED_PATTERN.search(str(user.handle))
                )

                # When rerolling, keep the user's own row in scope_qs so its
                # current DB handle blocks generate_handle from re-selecting
                # the same value (the python-only reset below doesn't reach
                # the DB, so excluding the user's pk would let cleverFox42
                # round-trip through the generator and back to itself). For
                # the missing-fill path the row's handle is NULL/empty, which
                # never matches a candidate, so excluding pk is safe and
                # avoids a self-match against an empty string.
                scope_qs = (
                    User.objects.all()
                    if rerolling
                    else User.objects.exclude(pk=user.pk)
                )
                new_handle = generate_handle(scope_qs=scope_qs)

                if dry_run:
                    self.stdout.write(
                        f"  user pk={user.pk} {old_handle!r} -> {new_handle!r}"
                    )
                else:
                    user.handle = new_handle
                    user.save(update_fields=["handle"])
                updated += 1

            if dry_run:
                # Roll back any side effects of ``generate_handle`` queries — the
                # function itself is read-only but staying inside the atomic
                # block keeps us symmetrical with the write path.
                transaction.set_rollback(True)

        verb = "would update" if dry_run else "updated"
        self.stdout.write(self.style.SUCCESS(f"{verb} {updated} user(s)."))
