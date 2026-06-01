"""Pure-function helpers for the canonical-CAML description cache.

The Readme.CAML Document body is the canonical source for a corpus's
description. ``Corpus.description`` and ``Corpus.description_preview`` are
auto-maintained read-only projections refreshed via signal on Readme.CAML
save. This module is the single derivation point.

Most helpers here are string transforms — no ORM access — so they can be
called safely from data migrations, signal handlers, and import shims.
``read_caml_body`` is the one exception: it reads bytes off a
``Document.txt_extract_file`` FieldFile, so it lives here for DRY (used
by the signal handler in ``corpuses/signals.py`` and the GraphQL
revisions facade in ``config/graphql/corpus_types.py``).
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from opencontractserver.constants.truncation import (
    MAX_CORPUS_DESCRIPTION_PREVIEW_LENGTH,
)
from opencontractserver.utils.files import read_field_file_text

if TYPE_CHECKING:
    from opencontractserver.documents.models import Document

logger = logging.getLogger(__name__)


def markdown_to_plain_text(md: str) -> str:
    """Strip the common markdown constructs and return plain text.

    Relocated from ``Corpus._markdown_to_plain_text`` so the canonical
    derivation has one home.
    """
    if not md:
        return ""
    text = md
    text = re.sub(r"^```[^\n]*\n(.*?)^```", r"\1", text, flags=re.MULTILINE | re.DOTALL)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"_{1,3}(.+?)_{1,3}", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"~~(.+?)~~", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"^>\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[\s]*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[\s]*\d+\.\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def summarize_for_preview(plain_text: str) -> str:
    """First-paragraph excerpt, word-boundary truncation, ellipsis on cut.

    Relocated from ``Corpus._summarize_for_preview`` (PR #1805).
    """
    if not plain_text:
        return ""
    first_paragraph = plain_text.split("\n\n", 1)[0].strip()
    first_paragraph = re.sub(r"\s+", " ", first_paragraph)
    if len(first_paragraph) <= MAX_CORPUS_DESCRIPTION_PREVIEW_LENGTH:
        return first_paragraph
    cut = first_paragraph[:MAX_CORPUS_DESCRIPTION_PREVIEW_LENGTH]
    last_space = cut.rfind(" ")
    if last_space > MAX_CORPUS_DESCRIPTION_PREVIEW_LENGTH // 2:
        cut = cut[:last_space]
    return cut.rstrip() + "…"


def read_caml_body(doc: Document) -> str:
    """Return the Readme.CAML body as text.

    Delegates to :func:`opencontractserver.utils.files.read_field_file_text`,
    which normalises cloud storage backends (S3Boto3Storage /
    GoogleCloudStorage via django-storages #382) that silently return
    ``bytes`` from a text-mode read. The previous hand-rolled
    ``except``-guarded binary fallback never fired for that path because the
    bytes read did not raise — it only caught backends that *raise* on text
    mode — so cloud deployments leaked ``bytes`` into
    ``markdown_to_plain_text`` (``re`` on a bytes-like object) and the
    GraphQL revisions facade. Returns the empty string when the document has
    no ``txt_extract_file``.

    Promoted from a private helper in ``corpuses/signals.py`` so the
    GraphQL ``descriptionRevisions`` facade (which reads the
    txt_extract_file body of each Readme.CAML version-tree sibling) can
    share the same I/O contract as the cache-refresh signal handler.
    """
    if not (doc.txt_extract_file and doc.txt_extract_file.name):
        return ""
    try:
        # ``errors="ignore"`` preserves the prior best-effort decode for a
        # corrupted blob; the outer guard keeps a hard I/O failure from
        # propagating into the signal handler / GraphQL resolver.
        return read_field_file_text(doc.txt_extract_file, errors="ignore")
    except Exception:
        return ""


def compute_cache_from_caml_body(
    body: str | None,
) -> tuple[str, str]:
    """Return ``(plain_text, preview)`` for a Readme.CAML body.

    The single entry point used by the signal handler, the V2 import
    shim, the data migration backfill, and any management command that
    needs to refresh the cache.
    """
    if not body:
        return "", ""
    plain = markdown_to_plain_text(body)
    return plain, summarize_for_preview(plain)


def backfill_caml_doc_for_corpus(
    corpus_pk: int,
    *,
    md_description_body: str,
) -> None:
    """Idempotent per-corpus backfill: ensure a Readme.CAML Document
    exists for the corpus (with a current ``DocumentPath`` linking it),
    and refresh the corpus's cache columns from ``md_description_body``.

    The Document<->Corpus relationship lives on ``DocumentPath`` (the
    Phase-2 corpus-isolation junction introduced by issue #1464);
    creation is routed through
    :func:`opencontractserver.documents.versioning.import_document`,
    the canonical dual-tree versioning workhorse which handles the
    ``Document``, ``DocumentPath``, ``version_tree_id``, and
    ``is_current`` transitions atomically. Lookup of the existing
    Readme.CAML doc goes through
    :meth:`opencontractserver.corpuses.services.corpus_documents.CorpusDocumentService.get_corpus_caml_articles`
    so the DocumentPath join stays consistent with the rest of the
    corpus-scoped read surface.

    Used by:

    * The V2 import shim — passes the legacy ``md_description`` body so
      the canonical CAML doc is synthesised on import.
    * The data migration — migrations operate on the historical model
      registry so they call their own migration-local equivalent rather
      than importing this function. The two implementations share
      semantics (and the same ``compute_cache_from_caml_body``
      derivation) by design; this module is the per-corpus logic spec.

    The Document ``post_save`` signal (``corpuses/signals.py``)
    cascade-refreshes the cache columns whenever the Readme.CAML body
    changes. This helper still writes the cache columns directly via
    :func:`compute_cache_from_caml_body` +
    ``Corpus.objects.filter().update`` because the V2 import shim calls
    it before the on_commit-deferred signal can fire; the duplicate
    update is idempotent.

    Args:
        corpus_pk: Primary key of the corpus to backfill.
        md_description_body: Canonical Readme.CAML body to use as the
            source of truth. An empty string with no existing CAML doc
            is a no-op for the FK but still resets the cache columns.

    Spec:
        ``docs/superpowers/specs/2026-05-27-canonical-caml-description-refactor-design.md``
        section 4.1.
    """
    from opencontractserver.constants.document_processing import (
        CAML_ARTICLE_TITLE,
        MARKDOWN_MIME_TYPE,
    )
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.corpuses.services.corpus_documents import (
        CorpusDocumentService,
    )
    from opencontractserver.documents.versioning import import_document

    corpus = Corpus.objects.get(pk=corpus_pk)
    existing = CorpusDocumentService.get_corpus_caml_articles(
        corpus.creator, corpus
    ).first()

    if existing is None:
        if not md_description_body:
            # No CAML doc, no body to seed one with — explicitly zero
            # the cache columns so the corpus row stays internally
            # consistent (description/preview empty, FK null).
            Corpus.objects.filter(pk=corpus.pk).update(
                description="",
                description_preview="",
                readme_caml_document_id=None,
            )
            return

        doc, _status, _path = import_document(
            corpus=corpus,
            path=CAML_ARTICLE_TITLE,
            content=md_description_body.encode("utf-8"),
            user=corpus.creator,
            file_type=MARKDOWN_MIME_TYPE,
            title=CAML_ARTICLE_TITLE,
        )
        # The doc was just written from md_description_body, so that IS its body.
        cache_body = md_description_body
    else:
        doc = existing
        # An existing Readme.CAML doc is already canonical — its stored body
        # wins over the caller-supplied legacy ``md_description_body`` (which
        # may differ). Deriving the cache from the legacy arg here would write
        # description/preview that don't match the document of record.
        cache_body = read_caml_body(doc)

    plain, preview = compute_cache_from_caml_body(cache_body)
    Corpus.objects.filter(pk=corpus.pk).update(
        description=plain,
        description_preview=preview,
        readme_caml_document_id=doc.pk,
    )


def refresh_description_cache_for_corpus(corpus_id: int) -> None:
    """Recompute and atomically write the cache columns for one corpus.

    Reads the current head of the corpus's Readme.CAML version tree via
    a DocumentPath join — no individual signal can assume the saved
    instance IS still the current head, because a concurrent version-up
    might have already moved it.

    Empty / missing-head case: zero out the cache + FK so the corpus
    row stays internally consistent.

    Public entry point used by the signal handlers in
    ``corpuses/signals.py``, the V2 import shim, the V2 import Celery
    task, and the test corpus fixture.
    """
    from opencontractserver.constants.document_processing import (
        CAML_ARTICLE_TITLE,
        MARKDOWN_MIME_TYPE,
    )
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.documents.models import DocumentPath

    try:
        # Match the signal's ``_is_readme_caml_document`` guard (title +
        # file_type), not the path alone — a current DocumentPath named
        # "Readme.CAML" that points at a non-markdown document is not a
        # canonical CAML doc and must not drive the description cache.
        head_path = (
            DocumentPath.objects.filter(
                corpus_id=corpus_id,
                path=CAML_ARTICLE_TITLE,
                is_current=True,
                is_deleted=False,
                document__file_type=MARKDOWN_MIME_TYPE,
            )
            .select_related("document")
            .first()
        )
        if head_path is None or head_path.document is None:
            Corpus.objects.filter(pk=corpus_id).update(
                description="",
                description_preview="",
                readme_caml_document_id=None,
            )
            return

        body = read_caml_body(head_path.document)
        plain, preview = compute_cache_from_caml_body(body)
        Corpus.objects.filter(pk=corpus_id).update(
            description=plain,
            description_preview=preview,
            readme_caml_document_id=head_path.document_id,
        )
    except Exception:
        logger.exception(
            "Failed to refresh description cache for corpus_id=%s", corpus_id
        )
