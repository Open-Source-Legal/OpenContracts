"""Backfill the CAML intelligence block into every corpus's ``Readme.CAML``.

Ensures each corpus composes the live corpus-intelligence overview by default
(see ``opencontractserver/corpuses/caml_intelligence.py``):

* A corpus with **no** ``Readme.CAML`` gets a deterministic structural default
  (title + description + intelligence block).
* A corpus **with** an article gets the block appended only if absent — author
  narrative is preserved and an already-composed article is left untouched.

Idempotent and re-runnable: the work is routed through
:meth:`CorpusService.ensure_readme_caml_default`, which delegates to
``update_description`` (content-identical writes are no-ops). Running twice
never duplicates the block.

The command only ever creates or updates ``Readme.CAML`` documents — it never
deletes a corpus or any other row (deliberately, given a known dev-DB issue
where ``Corpus.delete()`` references a missing ``documents_pendingcorpusimport``
table).
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from opencontractserver.corpuses.caml_intelligence import has_intelligence_block
from opencontractserver.corpuses.models import Corpus
from opencontractserver.corpuses.services.corpus_service import CorpusService
from opencontractserver.corpuses.services.description_cache import read_caml_body


class Command(BaseCommand):
    help = (
        "Ensure every corpus's Readme.CAML contains the intelligence block "
        "(insight-panel / document-graph / ask-across-docs embeds). Appends the "
        "block where missing and creates a structural Readme.CAML where none "
        "exists. Idempotent and re-runnable; never deletes anything."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing any Readme.CAML.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        dry_run: bool = options["dry_run"]

        # Import here (not at module load) to keep the command importable even
        # if the service-layer lookup helper signature shifts.
        from opencontractserver.corpuses.services.corpus_documents import (
            CorpusDocumentService,
        )

        created = 0
        appended = 0
        already_had = 0
        skipped_no_creator = 0

        # ``iterator()`` keeps memory flat over large installs; each corpus is a
        # single independent unit of work so there is no cross-row state.
        corpora = Corpus.objects.select_related("creator").all()
        total = corpora.count()

        for corpus in corpora.iterator():
            actor = corpus.creator
            if actor is None:
                # ``update_description`` is creator-gated; a creator-less corpus
                # (data import edge case) cannot be written through the service.
                skipped_no_creator += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"  skip corpus {corpus.pk} ({corpus.title!r}): no creator"
                    )
                )
                continue

            existing = CorpusDocumentService.get_corpus_caml_articles(
                actor, corpus
            ).first()

            if existing is None:
                outcome = "create"
            elif has_intelligence_block(read_caml_body(existing)):
                already_had += 1
                continue
            else:
                outcome = "append"

            if dry_run:
                self.stdout.write(
                    f"  would {outcome} corpus {corpus.pk} ({corpus.title!r})"
                )
            else:
                result = CorpusService.ensure_readme_caml_default(actor, corpus)
                if not result.ok:
                    self.stdout.write(
                        self.style.ERROR(
                            f"  FAILED corpus {corpus.pk} ({corpus.title!r}): "
                            f"{result.error}"
                        )
                    )
                    continue
                self.stdout.write(f"  {outcome}d corpus {corpus.pk} ({corpus.title!r})")

            if outcome == "create":
                created += 1
            else:
                appended += 1

        verb = "Would update" if dry_run else "Updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} intelligence block across {total} corpora: "
                f"{created} created, {appended} appended, "
                f"{already_had} already had it, "
                f"{skipped_no_creator} skipped (no creator)."
            )
        )
