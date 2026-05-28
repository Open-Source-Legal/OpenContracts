"""Pure-function helpers for the canonical-CAML description cache.

The Readme.CAML Document body is the canonical source for a corpus's
description. ``Corpus.description`` and ``Corpus.description_preview`` are
auto-maintained read-only projections refreshed via signal on Readme.CAML
save. This module is the single derivation point.

No ORM access — everything is a string transform so the helpers can be
called safely from data migrations, signal handlers, and import shims.
"""

from __future__ import annotations

import re

from opencontractserver.constants.truncation import (
    MAX_CORPUS_DESCRIPTION_PREVIEW_LENGTH,
)


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
    """Idempotent per-corpus backfill: create the Readme.CAML doc if
    missing and refresh the cache columns.

    Lives in this module so the data migration (whose filename starts
    with a digit and cannot be ``import``-ed normally) can re-use the
    logic, and tests can exercise it directly without importlib.
    Uses the live model registry (NOT ``apps.get_model``) — callers
    inside Django data migrations should use the migration-local
    ``backfill_all`` instead, which goes through the historical models.
    """
    import uuid

    from django.core.files.base import ContentFile

    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.documents.models import Document

    corpus = Corpus.objects.get(pk=corpus_pk)
    doc = Document.objects.filter(
        corpus=corpus,
        title="Readme.CAML",
        file_type="text/markdown",
    ).first()
    if doc is None and md_description_body:
        doc = Document.objects.create(
            corpus=corpus,
            title="Readme.CAML",
            file_type="text/markdown",
            creator=corpus.creator,
            version_tree_id=uuid.uuid4(),
        )
        doc.txt_extract_file.save(
            "Readme.CAML.md",
            ContentFile(md_description_body.encode("utf-8")),
            save=True,
        )
    if doc is not None:
        plain, preview = compute_cache_from_caml_body(md_description_body)
        Corpus.objects.filter(pk=corpus.pk).update(
            description=plain,
            description_preview=preview,
            readme_caml_document_id=doc.pk,
        )
