"""Management-command adapter for the reusable authority-pack service."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from opencontractserver.enrichment.services.authority_pack_service import (
    AuthorityPackService,
    _ValidatedCorpus,
)

User = get_user_model()

# Kept importable for older tests and third-party commands which built validated
# declarations before invoking the loader.  The implementation lives in the
# service; this module contains no second copy of it.
__all__ = ["Command", "_ValidatedCorpus"]


class Command(AuthorityPackService, BaseCommand):
    help = (
        "Load an authority pack (taxonomy + per-area content + personas) from a "
        "pack directory containing a pack.yaml manifest. Idempotent and re-runnable."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--path", required=True, help="Pack directory (contains pack.yaml)."
        )
        parser.add_argument(
            "--creator", required=True, help="Username owning the seeded corpora."
        )
        parser.add_argument(
            "--public",
            action="store_true",
            help="Publish each corpus so its authorities resolve for all users.",
        )
        parser.add_argument(
            "--no-relink",
            action="store_true",
            help="Skip the reactive re-link of corpora citing the seeded keys.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            creator = User.objects.get(username=options["creator"])
        except User.DoesNotExist as exc:
            raise CommandError(f"No user named {options['creator']!r}") from exc

        result = AuthorityPackService.install_path(
            Path(options["path"]),
            creator=creator,
            make_public=options["public"],
            relink=not options["no_relink"],
        )
        if result.taxonomy_summary is not None:
            namespaces = result.taxonomy_summary["namespaces"]
            equivalences = result.taxonomy_summary["equivalences"]
            self.stdout.write(
                self.style.SUCCESS(
                    "taxonomy loaded: "
                    f"namespaces created={namespaces['created']} "
                    f"updated={namespaces['updated']} "
                    "skipped_foreign_baseline="
                    f"{namespaces['skipped_foreign_baseline']} "
                    f"total={namespaces['total']}; "
                    f"equivalences created={equivalences['created']} "
                    f"updated={equivalences['updated']} "
                    f"total={equivalences['total']}"
                )
            )
            if namespaces["skipped_foreign_baseline"]:
                self.stdout.write(
                    self.style.WARNING(
                        f"{namespaces['skipped_foreign_baseline']} prefix(es) "
                        "already owned by another baseline origin were left "
                        "untouched (first writer wins) — see the log for the "
                        "colliding prefixes."
                    )
                )

        for summary in result.corpus_summaries:
            self.stdout.write(
                self.style.SUCCESS(
                    f"corpus {summary['corpus_id']} ({summary['title']}): "
                    f"{summary['documents_created']} created, "
                    f"{summary['documents_updated']} updated, "
                    f"{summary['documents_metadata_updated']} metadata-updated, "
                    f"{summary['documents_skipped']} skipped, "
                    f"{summary['documents_restamped']} restamped."
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                "relationships loaded: "
                + ", ".join(
                    f"{key}={value}"
                    for key, value in result.relationship_summary.items()
                )
            )
        )
        if result.relink_summary is not None:
            relink = result.relink_summary
            self.stdout.write(
                self.style.SUCCESS(
                    f"Re-link: {relink['corpora_relinked']}/"
                    f"{relink['corpora_checked']} corpora upgraded, "
                    f"{relink['law_references_linked']} references linked, "
                    f"{relink['links_restamped']} links restamped, "
                    f"{relink['corpora_failed']} failures."
                )
            )
