"""Stand up a browsable, insight-ready corpus from a folder of documents.

One command takes a directory of PDFs (or any allowed file type) all the way to
a published corpus whose home page surfaces collection intelligence:

    create corpus → import each file (fires parse + embed) → [wait] →
    one-click intelligence setup (reference enrichment + per-doc summaries) →
    [make public]

It is the programmatic twin of the UI flow (create-corpus modal +
``setupCorpusIntelligence``), packaged for bulk / scripted ingestion and for
local demos. Every step routes through the same service layer the GraphQL
mutations use (``import_document_for_user``,
``CorpusIntelligenceSetupService``), so there is no second, weaker code path.

Examples
--------
    # Minimal: create + import, leave parsing to run async.
    python manage.py ingest_corpus --path /data/contracts --title "Contracts"

    # Full demo corpus: 10 files, wait for parsing, enrich, publish.
    python manage.py ingest_corpus \
        --path /data/contracts --title "City Contracts" \
        --limit 10 --wait --enrich --public
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from opencontractserver.corpuses.models import Corpus
from opencontractserver.corpuses.services.corpus_service import CorpusService

# Default real embedder (the per-mimetype default can be a TestEmbedder in some
# installs — pin the microservice embedder so semantic search actually works).
DEFAULT_EMBEDDER = (
    "opencontractserver.pipeline.embedders."
    "sent_transformer_microservice.MicroserviceEmbedder"
)

# Poll cadence + ceiling while waiting for the async parse/embed chain to clear
# each document's backend lock.
_POLL_SECONDS = 10


class Command(BaseCommand):
    help = (
        "Create a corpus, import every document under --path (parse + embed), "
        "and optionally wait, run one-click intelligence setup, and publish. "
        "The end-to-end 'folder of files → insight-ready public corpus' path."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--path",
            required=True,
            help="Directory to ingest (searched recursively for allowed files).",
        )
        parser.add_argument("--title", required=True, help="Corpus title.")
        parser.add_argument(
            "--description", default="", help="Corpus description (optional)."
        )
        parser.add_argument(
            "--owner",
            default=None,
            help="Username of the corpus owner. Defaults to the first superuser.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Import at most N files (sorted by name). Default: all.",
        )
        parser.add_argument(
            "--embedder",
            default=DEFAULT_EMBEDDER,
            help="Dotted path of the corpus's preferred embedder.",
        )
        parser.add_argument(
            "--wait",
            action="store_true",
            help="Block until every document finishes parsing + embedding.",
        )
        parser.add_argument(
            "--enrich",
            action="store_true",
            help=(
                "Run one-click intelligence setup after import (implies --wait, "
                "since enrichment needs parsed documents)."
            ),
        )
        parser.add_argument(
            "--public",
            action="store_true",
            help="Mark the corpus (and its documents) public when done.",
        )
        parser.add_argument(
            "--timeout",
            type=int,
            default=1800,
            help="Max seconds to wait for parsing (with --wait/--enrich).",
        )

    # ------------------------------------------------------------------
    def handle(self, *args: Any, **options: Any) -> None:
        from django.contrib.auth import get_user_model

        from opencontractserver.annotations.models import LabelSet
        from opencontractserver.document_imports.services import (
            import_document_for_user,
        )

        User = get_user_model()

        # --- owner ----------------------------------------------------------
        if options["owner"]:
            owner = User.objects.filter(username=options["owner"]).first()
            if owner is None:
                raise CommandError(f"No user named {options['owner']!r}.")
        else:
            owner = User.objects.filter(is_superuser=True).order_by("id").first()
            if owner is None:
                raise CommandError("No superuser found; pass --owner explicitly.")

        # --- collect files --------------------------------------------------
        root = Path(options["path"]).expanduser()
        if not root.is_dir():
            raise CommandError(f"--path {root} is not a directory.")
        # The extension gate and the log line are derived from the same set, so
        # the reported filter can never drift from the one actually applied.
        # Natively-parsed formats are always accepted; anything else is only
        # accepted when the configured file converter (e.g. Gotenberg) will
        # convert it to PDF first — same eligibility check the upload REST path
        # uses (``resolve_convertible_upload``), so this command actually
        # ingests "any allowed file type" as the docstring above promises,
        # rather than a fixed subset that silently drops e.g. legacy .doc.
        from opencontractserver.pipeline.utils import get_convertible_extensions

        ext_ok = {".pdf", ".txt", ".docx", ".xlsx", ".pptx"} | {
            f".{ext}" for ext in get_convertible_extensions()
        }
        files = sorted(
            p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in ext_ok
        )
        if options["limit"] is not None:
            files = files[: options["limit"]]
        if not files:
            raise CommandError(f"No ingestible files found under {root}.")

        self.stdout.write(
            f"Ingesting {len(files)} file(s) as {owner.username} "
            f"(accepted extensions: {', '.join(sorted(ext_ok))})."
        )

        # --- create corpus --------------------------------------------------
        labelset = LabelSet.objects.filter(is_default=True).first()
        corpus = Corpus.objects.create(
            title=options["title"],
            description=options["description"],
            creator=owner,
            label_set=labelset,
            preferred_embedder=options["embedder"],
        )
        # A bare ORM create() does NOT grant guardian object-level permissions
        # (the Corpus post_save signal only queues branding). Without this the
        # corpus is invisible to its own owner via ``visible_to_user`` (only
        # superusers bypass guardian), so mirror the GraphQL CreateCorpus path.
        CorpusService.grant_creator_permissions(owner, corpus)
        self.stdout.write(
            self.style.SUCCESS(f"Created corpus {corpus.pk} ({corpus.slug!r}).")
        )

        # --- import each file ----------------------------------------------
        doc_ids: list[int] = []
        for path in files:
            res = import_document_for_user(
                user=owner,
                file_bytes=path.read_bytes(),
                filename=path.name,
                title=path.stem,
                description="",
                custom_meta={"source_path": str(path.parent.name)},
                add_to_corpus_id=corpus.pk,
            )
            if res.document is None:
                self.stdout.write(
                    self.style.WARNING(f"  skip {path.name}: {res.error}")
                )
            else:
                doc_ids.append(res.document.id)
                self.stdout.write(f"  + doc {res.document.id}: {path.stem}")

        if not doc_ids:
            raise CommandError("No documents imported; aborting before enrichment.")

        # --- wait for processing -------------------------------------------
        want_wait = options["wait"] or options["enrich"]
        if want_wait:
            self._wait_for_processing(doc_ids, options["timeout"])

        # --- enrich ---------------------------------------------------------
        if options["enrich"]:
            self._enrich(owner, corpus.pk)

        # --- publish --------------------------------------------------------
        if options["public"]:
            corpus.is_public = True
            corpus.save()  # propagate_is_public_to_documents runs on save
            self.stdout.write(self.style.SUCCESS("Marked corpus public."))

        # --- report ---------------------------------------------------------
        corpus.refresh_from_db()
        owner_ident = getattr(owner, "slug", None) or owner.username
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Corpus {corpus.pk}: {len(doc_ids)} docs, "
                f"public={corpus.is_public}. URL path: /c/{owner_ident}/{corpus.slug}"
            )
        )

    # ------------------------------------------------------------------
    def _wait_for_processing(self, doc_ids: list[int], timeout: int) -> None:
        """Poll until every document clears its backend lock (parse + embed done)."""
        from opencontractserver.documents.models import Document

        self.stdout.write(f"Waiting for {len(doc_ids)} document(s) to finish…")
        deadline = time.monotonic() + timeout
        while True:
            docs = list(Document.objects.filter(pk__in=doc_ids))
            present_ids = {d.pk for d in docs}
            # Deleted-during-processing docs are gone from the queryset; they will
            # never become "ready", so count them as settled or the loop stalls
            # until timeout.
            missing = [pk for pk in doc_ids if pk not in present_ids]
            free = sum(1 for d in docs if not d.backend_lock)
            failed = [d.pk for d in docs if d.processing_status == "failed"]
            # A document is settled once it is lock-free, failed, or deleted — a
            # failed/deleted doc never clears its lock the normal way, so waiting
            # for ``free == len(doc_ids)`` would burn the full timeout.
            settled = sum(
                1 for d in docs if not d.backend_lock or d.processing_status == "failed"
            ) + len(missing)
            self.stdout.write(
                f"  {free}/{len(doc_ids)} ready"
                + (f", failed={failed}" if failed else "")
                + (f", missing={missing}" if missing else "")
            )
            if settled >= len(doc_ids):
                if failed or missing:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  done with {len(failed)} failed, {len(missing)} "
                            "missing — continuing."
                        )
                    )
                else:
                    self.stdout.write(self.style.SUCCESS("  all documents processed."))
                return
            if time.monotonic() >= deadline:
                self.stdout.write(
                    self.style.WARNING(
                        f"  timeout after {timeout}s — continuing with "
                        f"{free}/{len(doc_ids)} ready."
                    )
                )
                return
            time.sleep(_POLL_SECONDS)

    # ------------------------------------------------------------------
    def _enrich(self, owner: Any, corpus_pk: int) -> None:
        """Run one-click intelligence setup (reference enrichment + summaries)."""
        from opencontractserver.corpuses.services.intelligence_setup import (
            CorpusIntelligenceSetupService,
        )

        self.stdout.write("Running one-click intelligence setup…")
        result = CorpusIntelligenceSetupService.setup(owner, corpus_pk, request=None)
        if not result.ok:
            self.stdout.write(self.style.ERROR(f"  setup failed: {result.error}"))
            return
        summary = getattr(result, "value", None)
        started = getattr(summary, "reference_analysis_started", None)
        n_docs = getattr(summary, "total_active_documents", None)
        self.stdout.write(
            self.style.SUCCESS(
                f"  setup started (reference weave={started}, "
                f"active docs={n_docs}). Summaries run async."
            )
        )
