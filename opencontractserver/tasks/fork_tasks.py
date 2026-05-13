"""
Corpus forking as a thin wrapper over the V2 export/import pipeline.

The fork task used to maintain its own ID-remap logic for every cloned
object type (LabelSet, AnnotationLabel, Fieldset, Column, CorpusFolder,
Document, DocumentPath, Annotation, Datacell, Relationship).  That code
silently drifted from the export/import pipeline (missing
``CorpusDescriptionRevision`` history, conversations, ingestion source
lineage; differing behavior on off-labelset annotation labels; etc.).

The current implementation flips the relationship: forking is now defined
as *export the source corpus to an in-memory ZIP, then import it into a
fresh shell corpus*.  Fork-specific tweaks (``[FORK]`` title prefix on
the corpus / labelset / documents, ``parent_id`` lineage, optional
``preferred_embedder`` override) are applied after the import returns.

This guarantees fork ≡ export+import by construction, so any future
addition to the V2 schema flows through to fork automatically.
"""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.db import transaction

from config import celery_app
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.tasks.export_tasks_v2 import build_corpus_v2_zip
from opencontractserver.tasks.import_tasks_v2 import import_corpus_v2_from_bytes

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

User = get_user_model()


@celery_app.task()
def fork_corpus(
    new_corpus_id: str,
    doc_ids: list[str],
    label_set_id: str,
    annotation_ids: list[str],
    folder_ids: list[str],
    relationship_ids: list[str],
    user_id: str,
    metadata_column_ids: list[str] | None = None,
    metadata_datacell_ids: list[str] | None = None,
) -> int | str | None:
    """
    Fork a corpus by round-tripping it through the V2 export/import pipeline.

    Args:
        new_corpus_id: ID of the pre-created shell corpus to populate.  The
            caller (``StartCorpusFork`` mutation or
            ``build_fork_corpus_task``) creates this row with
            ``backend_lock=True`` and ``parent_id`` pointing at the source.
        doc_ids, label_set_id, annotation_ids, folder_ids, relationship_ids,
        metadata_column_ids, metadata_datacell_ids: Retained for backward
            compatibility with queued tasks.  These were used by the old
            inline-cloning implementation; the new export-driven flow
            collects everything it needs from the source corpus directly,
            so the args are effectively informational.

    Returns:
        New corpus ID on success, ``None`` on failure (with ``error=True``
        and ``backend_lock=False`` left on the shell).
    """
    # Retained-arg unused acknowledgements (silences linters; document
    # in body that these are present for queued-task backward compat).
    _ = (
        doc_ids,
        annotation_ids,
        folder_ids,
        relationship_ids,
        metadata_column_ids,
        metadata_datacell_ids,
        label_set_id,
    )

    logger.info(
        "fork_corpus(new_corpus_id=%s, user_id=%s) via export+import",
        new_corpus_id,
        user_id,
    )

    try:
        shell = Corpus.objects.get(pk=new_corpus_id)
        # Validate the user exists up-front so we fail loudly before
        # running an expensive export.  The import path looks the user up
        # again by ID; we don't need to hold a reference here.
        User.objects.get(pk=user_id)
    except (Corpus.DoesNotExist, User.DoesNotExist) as e:
        logger.error("fork_corpus could not load shell or user: %s", e)
        return None

    source_pk = shell.parent_id
    if source_pk is None:
        logger.error(
            "fork_corpus shell %s has no parent_id; cannot infer source corpus",
            new_corpus_id,
        )
        shell.backend_lock = False
        shell.error = True
        shell.save(update_fields=["backend_lock", "error"])
        return None

    # Capture the override the caller stamped on the shell (the
    # StartCorpusFork mutation supports a preferred_embedder override).
    # The import will overwrite preferred_embedder with the source's
    # value, so re-apply this afterwards if it diverges.
    requested_embedder: str | None = shell.preferred_embedder or None

    try:
        # Build the export ZIP outside the write transaction.  It only
        # reads from the DB (and constructs an in-memory ZIP), so it
        # doesn't need to share scope with the import's writes — keeping
        # it outside narrows the lock window to just the import phase,
        # which can run for minutes on large corpora.
        zip_bytes = build_corpus_v2_zip(
            corpus_pk=int(source_pk),
            user_for_visibility=None,  # fork inherits all conversations
            include_conversations=True,
            include_action_trail=False,
        )

        with transaction.atomic():
            imported_id = import_corpus_v2_from_bytes(
                zip_source=zip_bytes,
                user_id=int(user_id),
                seed_corpus_id=int(new_corpus_id),
            )
            if imported_id is None:
                raise RuntimeError(
                    f"V2 import returned None while forking corpus {source_pk}"
                )

            # ``unpack_corpus_from_export`` overwrote the shell's title +
            # preferred_embedder + label_set with the source's values.
            # Re-apply fork semantics on top.
            new_corpus = Corpus.objects.get(pk=imported_id)

            # Fork-prefix semantics:  Always prepend "[FORK] " unconditionally
            # so that multi-generation forks stack the prefix
            # ("[FORK] [FORK] X") — that's the historical fork contract used
            # by the lineage UI to communicate "this came from another fork".
            new_corpus.title = f"[FORK] {new_corpus.title}"
            new_corpus.parent_id = source_pk
            updates: list[str] = ["title", "parent"]

            if (
                requested_embedder
                and requested_embedder != new_corpus.preferred_embedder
            ):
                new_corpus.preferred_embedder = requested_embedder
                updates.append("preferred_embedder")

            new_corpus.backend_lock = False
            updates.append("backend_lock")

            new_corpus.save(update_fields=updates)

            # LabelSet title prefix — matches historical fork behavior.
            label_set = new_corpus.label_set
            if label_set is not None:
                label_set.title = f"[FORK] {label_set.title}"
                label_set.save(update_fields=["title"])

            # Metadata Fieldset name prefix — matches historical fork
            # behavior (and mirrors LabelSet/title handling).
            metadata_fieldset = getattr(new_corpus, "metadata_schema", None)
            if metadata_fieldset is not None:
                metadata_fieldset.name = f"[FORK] {metadata_fieldset.name}"
                metadata_fieldset.save(update_fields=["name"])

            # Document-level fork tweaks:
            #  - re-link source_document for provenance tracking
            #  - prefix titles with "[FORK] "
            # Build a (hash -> source Document) lookup across the SOURCE
            # corpus so the new corpus-isolated copy points back at the
            # original document it was forked from.  This mirrors the
            # provenance that ``corpus.add_document`` used to set on the
            # in-process fork path.
            source_paths = DocumentPath.objects.filter(
                corpus_id=source_pk, is_current=True, is_deleted=False
            ).select_related("document")
            source_by_hash: dict[str, Document] = {
                p.document.pdf_file_hash: p.document
                for p in source_paths
                if p.document.pdf_file_hash
            }
            # Title-based fallback used only when ``pdf_file_hash`` is empty
            # on either side.  Detect ambiguous titles up-front so the fallback
            # can be suppressed for those keys (silently picking "last wins"
            # would assign the wrong source blobs to forked docs).
            source_title_counts: dict[str, int] = {}
            for p in source_paths:
                if p.document.title:
                    source_title_counts[p.document.title] = (
                        source_title_counts.get(p.document.title, 0) + 1
                    )
            ambiguous_titles = {t for t, n in source_title_counts.items() if n > 1}
            if ambiguous_titles:
                logger.warning(
                    "fork_corpus: source corpus %s has %d document(s) with "
                    "duplicate title(s) %s; title-based blob fallback will be "
                    "skipped for these to avoid silent mis-assignment.",
                    source_pk,
                    len(ambiguous_titles),
                    sorted(ambiguous_titles),
                )
            source_by_title: dict[str, Document] = {
                p.document.title: p.document
                for p in source_paths
                if p.document.title and p.document.title not in ambiguous_titles
            }

            for dp in DocumentPath.objects.filter(
                corpus=new_corpus, is_current=True, is_deleted=False
            ).select_related("document"):
                doc = dp.document
                doc_updates: list[str] = []

                # Re-point provenance at the source corpus's copy
                # rather than the transient standalone Document the
                # V2 import path created (correct for export/import,
                # wrong for fork lineage).
                candidate = None
                if doc.pdf_file_hash:
                    candidate = source_by_hash.get(doc.pdf_file_hash)
                if candidate is None and doc.title:
                    candidate = source_by_title.get(doc.title)
                if candidate is not None and doc.source_document_id != candidate.id:
                    doc.source_document = candidate
                    doc_updates.append("source_document")

                # File-blob sharing — fork semantics share storage paths
                # with the source rather than allocating fresh copies.
                # The export/import roundtrip writes new blobs by design,
                # so the ones it just wrote here become orphaned.
                # TODO(#1638): reap or reuse those orphaned blobs instead
                # of relying on storage GC.
                if candidate is not None:
                    if (
                        candidate.pdf_file
                        and candidate.pdf_file.name
                        and (
                            not doc.pdf_file
                            or doc.pdf_file.name != candidate.pdf_file.name
                        )
                    ):
                        doc.pdf_file = candidate.pdf_file
                        doc_updates.append("pdf_file")
                    if (
                        candidate.pawls_parse_file
                        and candidate.pawls_parse_file.name
                        and (
                            not doc.pawls_parse_file
                            or doc.pawls_parse_file.name
                            != candidate.pawls_parse_file.name
                        )
                    ):
                        doc.pawls_parse_file = candidate.pawls_parse_file
                        doc_updates.append("pawls_parse_file")
                    if (
                        candidate.txt_extract_file
                        and candidate.txt_extract_file.name
                        and (
                            not doc.txt_extract_file
                            or doc.txt_extract_file.name
                            != candidate.txt_extract_file.name
                        )
                    ):
                        doc.txt_extract_file = candidate.txt_extract_file
                        doc_updates.append("txt_extract_file")
                    if (
                        candidate.icon
                        and candidate.icon.name
                        and (not doc.icon or doc.icon.name != candidate.icon.name)
                    ):
                        doc.icon = candidate.icon
                        doc_updates.append("icon")
                    if (
                        candidate.md_summary_file
                        and candidate.md_summary_file.name
                        and (
                            not doc.md_summary_file
                            or doc.md_summary_file.name
                            != candidate.md_summary_file.name
                        )
                    ):
                        doc.md_summary_file = candidate.md_summary_file
                        doc_updates.append("md_summary_file")

                doc.title = f"[FORK] {doc.title}"
                doc_updates.append("title")

                if doc_updates:
                    doc.save(update_fields=doc_updates)

        logger.info("fork_corpus succeeded for shell %s", new_corpus_id)
        return new_corpus.id

    except Exception as e:
        logger.error(
            "fork_corpus failed for shell %s: %s", new_corpus_id, e, exc_info=True
        )
        try:
            shell.refresh_from_db()
            shell.backend_lock = False
            shell.error = True
            shell.save(update_fields=["backend_lock", "error"])
        except Exception:
            pass
        return None
