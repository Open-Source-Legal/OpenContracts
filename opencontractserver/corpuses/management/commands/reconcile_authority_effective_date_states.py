"""Reconcile derived effective-date review states on authority documents."""

from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from opencontractserver.corpuses.models import Corpus
from opencontractserver.enrichment.authorities import AuthorityCorpusBootstrapper
from opencontractserver.shared.services.base import BaseService
from opencontractserver.types.enums import PermissionTypes

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Backfill UNKNOWN_NEEDS_REVIEW for current authority records that lack "
        "an effective date. Defaults to a non-mutating dry run."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--creator",
            required=True,
            help="Username with UPDATE permission on each authority corpus.",
        )
        parser.add_argument(
            "--corpus-slug",
            action="append",
            required=True,
            dest="corpus_slugs",
            help="Authority corpus slug to reconcile; repeat for multiple corpora.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write missing review states. Without this flag the command is dry-run.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            user = User.objects.get(username=options["creator"])
        except User.DoesNotExist as exc:
            raise CommandError(f"No user named {options['creator']!r}") from exc

        slugs = list(dict.fromkeys(options["corpus_slugs"]))
        dry_run = not options["apply"]
        totals: dict[str, int] = {}

        for slug in slugs:
            corpus = Corpus.objects.visible_to_user(user).filter(slug=slug).first()
            if corpus is None or not BaseService.user_has(
                corpus, user, PermissionTypes.UPDATE
            ):
                raise CommandError(
                    f"Corpus {slug!r} does not exist or is not writable by "
                    f"{user.username!r}."
                )
            summary = (
                AuthorityCorpusBootstrapper.reconcile_effective_date_review_states(
                    corpus=corpus,
                    user=user,
                    dry_run=dry_run,
                )
            )
            for key, value in summary.items():
                totals[key] = totals.get(key, 0) + value
            self.stdout.write(
                f"corpus {slug}: "
                f"authority_documents={summary['authority_documents']} "
                f"would_update={summary['would_update']} "
                f"updated={summary['updated']} "
                f"already_stated={summary['already_stated']}"
            )

        mode = "DRY RUN" if dry_run else "APPLIED"
        self.stdout.write(
            self.style.SUCCESS(
                f"{mode}: corpora={len(slugs)} "
                f"authority_documents={totals.get('authority_documents', 0)} "
                f"would_update={totals.get('would_update', 0)} "
                f"updated={totals.get('updated', 0)}"
            )
        )
