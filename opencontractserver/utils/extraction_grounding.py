"""
Auto-grounding pipeline for extraction results.

After an LLM extracts data into a Datacell, this module finds the extracted
text values in the source document and creates Annotation objects linked as
sources.  It bridges the text_alignment utility with PlasmaPDF (for PDFs) or
span-based annotations (for text/DOCX).

The grounding is best-effort: if alignment fails for a value, it is silently
skipped — the extraction result is never lost.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from asgiref.sync import sync_to_async

from opencontractserver.constants.extraction import (
    DATACELL_DATA_KEY,
    MAX_GROUNDABLE_STRINGS,
    MIN_GROUNDABLE_LENGTH,
)
from opencontractserver.utils.text_alignment import (
    AlignmentResult,
    align_text_to_document,
)

if TYPE_CHECKING:
    from opencontractserver.annotations.models import Annotation, AnnotationLabel
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.documents.models import Document
    from opencontractserver.extracts.models import Datacell

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Step 1: Extract groundable strings from datacell.data
# ---------------------------------------------------------------------------


def extract_groundable_strings(data: Any) -> list[str]:
    """Recursively extract string values worth grounding from extraction results.

    Walks the extraction result (which may be a primitive, dict, or list)
    and collects string values that are likely to appear verbatim in the
    source document.

    Filters out:
    - Strings shorter than ``MIN_GROUNDABLE_LENGTH``
    - Pure numeric strings
    - Boolean-like strings ("true", "false", "yes", "no")

    Returns at most ``MAX_GROUNDABLE_STRINGS`` unique strings, preserving
    insertion order.
    """
    seen: set[str] = set()
    results: list[str] = []

    def _walk(obj: Any) -> None:
        if len(results) >= MAX_GROUNDABLE_STRINGS:
            return

        if isinstance(obj, str):
            stripped = obj.strip()
            if (
                len(stripped) >= MIN_GROUNDABLE_LENGTH
                and stripped not in seen
                and not _is_non_groundable(stripped)
            ):
                seen.add(stripped)
                results.append(stripped)

        elif isinstance(obj, dict):
            for value in obj.values():
                _walk(value)
                if len(results) >= MAX_GROUNDABLE_STRINGS:
                    return

        elif isinstance(obj, (list, tuple)):
            for item in obj:
                _walk(item)
                if len(results) >= MAX_GROUNDABLE_STRINGS:
                    return

    _walk(data)
    return results


def _is_non_groundable(s: str) -> bool:
    """Return True for strings unlikely to appear verbatim in a document."""
    lower = s.lower()

    # Boolean-like
    if lower in ("true", "false", "yes", "no", "none", "null", "n/a"):
        return True

    # Pure numeric (int or float)
    try:
        float(s.replace(",", ""))
        return True
    except ValueError:
        pass

    return False


# ---------------------------------------------------------------------------
# Step 2: Load document text (format-aware)
# ---------------------------------------------------------------------------


@sync_to_async
def _load_document_text_and_layer(document: Document) -> tuple[str, Any, str]:
    """Load document text and optional PlasmaPDF translation layer.

    Returns:
        (doc_text, pdf_layer_or_none, annotation_type_const)
    """
    from opencontractserver.annotations.models import SPAN_LABEL, TOKEN_LABEL
    from opencontractserver.constants.document_processing import (
        DOCX_MIME_TYPE,
        TEXT_MIMETYPES,
    )
    from opencontractserver.utils.compact_pawls import expand_pawls_pages

    file_type = (document.file_type or "").lower()

    if file_type == "application/pdf":
        if not document.pawls_parse_file:
            raise ValueError(
                f"PDF document id={document.id} lacks a PAWLS layer; "
                "cannot ground extractions."
            )
        from plasmapdf.models.PdfDataLayer import build_translation_layer

        with document.pawls_parse_file.open("r") as f:
            pawls_tokens = expand_pawls_pages(json.load(f))

        pdf_layer = build_translation_layer(pawls_tokens)
        return pdf_layer.doc_text, pdf_layer, TOKEN_LABEL

    elif file_type in TEXT_MIMETYPES or file_type == DOCX_MIME_TYPE:
        if not document.txt_extract_file:
            raise ValueError(
                f"Document id={document.id} (type={file_type}) lacks "
                "txt_extract_file; cannot ground extractions."
            )
        with document.txt_extract_file.open("r") as f:
            doc_text = f.read()

        return doc_text, None, SPAN_LABEL

    else:
        raise ValueError(
            f"Unsupported file_type {file_type!r} for grounding on "
            f"document id={document.id}"
        )


# ---------------------------------------------------------------------------
# Step 3: Create annotations from alignment results
# ---------------------------------------------------------------------------


@sync_to_async
def _create_grounding_annotations(
    alignment_results: list[AlignmentResult],
    document: Document,
    corpus: Corpus,
    creator_id: int,
    pdf_layer: Any,
    annotation_type: str,
) -> list[Annotation]:
    """Create Annotation objects for each alignment result.

    For PDFs, uses PlasmaPDF to generate token-level annotations with
    bounding boxes.  For text/DOCX, creates span annotations with
    character offsets.

    Annotation creation is idempotent: re-running grounding (e.g. after a
    Celery retry) reuses existing OC_EXTRACT_SOURCE annotations with the
    same span coordinates rather than creating duplicates.

    The label/labelset lookup is performed inside the per-annotation
    savepoint so that a transient failure (e.g. a labelset constraint
    violation) only loses the affected annotation instead of aborting the
    whole batch.

    Returns list of saved Annotation instances (may include both newly
    created and previously existing rows on retry).
    """
    from django.db import transaction

    from opencontractserver.annotations.models import (
        SPAN_LABEL,
        TOKEN_LABEL,
    )
    from opencontractserver.constants.annotations import OC_EXTRACT_SOURCE_LABEL

    if not alignment_results:
        return []

    annotations: list[Annotation] = []

    # Cache the label across iterations so the happy path is one DB lookup,
    # not N. Reset on ANY savepoint rollback (not just label-lookup failures):
    # if the label/labelset was created inside this iteration's savepoint and
    # then rolled back due to a downstream failure, the cached reference is
    # stale. ensure_label_and_labelset is idempotent, so the cost of an
    # unnecessary re-fetch after, e.g., a page=None ValueError is one SELECT.
    cached_label: AnnotationLabel | None = None

    for result in alignment_results:
        try:
            with transaction.atomic():
                if cached_label is None:
                    cached_label = corpus.ensure_label_and_labelset(
                        label_text=OC_EXTRACT_SOURCE_LABEL,
                        creator_id=creator_id,
                        label_type=annotation_type,
                    )
                label_obj = cached_label

                if annotation_type == TOKEN_LABEL and pdf_layer is not None:
                    annot = _create_pdf_annotation(
                        result, document, corpus, creator_id, pdf_layer, label_obj
                    )
                elif annotation_type == SPAN_LABEL:
                    annot = _create_span_annotation(
                        result, document, corpus, creator_id, label_obj
                    )
                else:
                    continue

                annotations.append(annot)

        except Exception:
            cached_label = None
            logger.warning(
                "Failed to create grounding annotation for %r "
                "at [%d:%d] in document %d",
                result.query_text[:50],
                result.char_start,
                result.char_end,
                document.id,
                exc_info=True,
            )

    # Deduplicate by primary key, preserving first-seen order.
    #
    # Why this is needed (not a bug masked): ``align_text_to_document``
    # returns at most one ``AlignmentResult`` per query string, but
    # multiple distinct extraction values can legitimately resolve to the
    # same source span — e.g. a column extracted as both
    # ``["Acme Holdings", "Acme Holdings Inc."]`` where each substring
    # gets its own alignment but both anchor on the same token range, or
    # an idempotent re-run where ``get_or_create`` returns the existing
    # row twice for the same phrase.  In both cases the underlying
    # source annotation is the same row, and returning duplicates would
    # make ``len(annotations)`` diverge from ``datacell.sources.count()``
    # (since ``M2M.add()`` is itself idempotent) and break the idempotency
    # invariants that downstream consumers — including the idempotency
    # tests in ``test_extraction_grounding.py`` — rely on.
    seen_pks: set[int] = set()
    deduped: list[Annotation] = []
    for annot in annotations:
        if annot.pk in seen_pks:
            continue
        seen_pks.add(annot.pk)
        deduped.append(annot)
    return deduped


def _create_pdf_annotation(
    result: AlignmentResult,
    document: Document,
    corpus: Corpus,
    creator_id: int,
    pdf_layer: Any,
    label_obj: AnnotationLabel,
) -> Annotation:
    """Create (or fetch) a TOKEN_LABEL annotation for a PDF document via PlasmaPDF.

    Idempotent: returns the existing annotation if one with the same
    document, label, page, and raw text already exists.

    Raises ``ValueError`` inside the savepoint when the annotation cannot
    be created safely (e.g. PlasmaPDF could not determine the page); the
    caller's per-annotation ``try/except`` rolls back the savepoint and
    logs the skip.
    """
    from plasmapdf.models.types import SpanAnnotation, TextSpan

    from opencontractserver.annotations.models import TOKEN_LABEL, Annotation

    span = TextSpan(
        id=str(uuid4()),
        start=result.char_start,
        end=result.char_end,
        text=result.matched_text,
    )
    span_annotation = SpanAnnotation(span=span, annotation_label=label_obj.text)
    oc_ann = pdf_layer.create_opencontract_annotation_from_span(span_annotation)

    page = oc_ann.get("page")
    if page is None:
        # Skipping is preferred over saving with page=1: a wrong page on a
        # multi-page PDF produces a structurally incorrect annotation that
        # confuses users clicking through to the source.  Raising rolls
        # back the savepoint and the outer loop logs it as a failed
        # grounding attempt.
        raise ValueError(
            f"PlasmaPDF could not determine page for span "
            f"[{result.char_start}:{result.char_end}] in document "
            f"{document.id}; skipping grounding annotation."
        )

    # Note: ``json`` (bounding boxes) is in ``defaults``, NOT a lookup key.
    # For PDFs the (document, corpus, label, page, raw_text) tuple already
    # uniquely identifies the span; PlasmaPDF's bounding-box layout is
    # deterministic for stable input, so on Celery retry we want to reuse
    # the existing annotation rather than create a near-duplicate that
    # differs only by bounding-box reformatting. Span annotations key on
    # ``json`` because the char offsets ARE the identity for a text/DOCX
    # document.
    #
    # ``corpus`` IS in the lookup so a multi-corpus document doesn't share
    # a single annotation between unrelated corpora — datacell.sources
    # must point to an annotation whose ``corpus`` matches the extract's
    # corpus, otherwise ``MIN(document_permission, corpus_permission)``
    # falls back to the wrong corpus's permissions.
    #
    # ``creator`` is in the lookup AND in the backing partial UniqueConstraint
    # ``annotation_unique_token_label_grounding_key`` (see Annotation.Meta).
    # The constraint promotes idempotency from a best-effort
    # ``get_or_create`` to a correctness invariant: if two Celery workers
    # race on the same datacell, the loser's CREATE raises IntegrityError
    # and ``get_or_create`` falls back to a SELECT.
    # ``structural=False`` is in the lookup (not just defaults) so the
    # constraint condition (which includes structural=False) and the
    # get_or_create lookup are symmetric — if a stray structural row ever
    # shared the rest of the key tuple, get_or_create wouldn't silently
    # return it and bypass the constraint.
    annot, _ = Annotation.objects.get_or_create(
        document=document,
        corpus=corpus,
        annotation_label=label_obj,
        page=page,
        annotation_type=TOKEN_LABEL,
        raw_text=oc_ann["rawText"],
        creator_id=creator_id,
        is_grounding_source=True,
        structural=False,
        defaults={
            "json": oc_ann["annotation_json"],
        },
    )
    return annot


def _create_span_annotation(
    result: AlignmentResult,
    document: Document,
    corpus: Corpus,
    creator_id: int,
    label_obj: AnnotationLabel,
) -> Annotation:
    """Create (or fetch) a SPAN_LABEL annotation for a text/DOCX document.

    Idempotent: returns the existing annotation if one with the same
    document, label, and span coordinates already exists.

    Note: ``page`` is hardcoded to ``1`` because plain-text and DOCX
    documents don't carry a page-break map through the txt_extract_file
    pipeline, so we cannot derive an accurate page from the character
    offset.  For DOCX in particular this is a known limitation; the field
    serves as a placeholder and the actual location is encoded by the
    character offsets in ``json``.

    Identity key uses ``json={"start": ..., "end": ...}``.

    .. important::
       The ``json`` lookup is **PostgreSQL-specific**.  Django maps
       ``JSONField`` to PostgreSQL ``jsonb`` (structural equality —
       ``{"start": 1, "end": 2}`` matches ``{"end": 2, "start": 1}``)
       but to plain ``TEXT`` on SQLite, where comparison is lexical.
       A future contributor running this pipeline on SQLite would see
       silent ``get_or_create`` misses on dict-key reordering.  The
       project's runtime and test database are both PostgreSQL, so
       this is documented rather than guarded.  We still construct
       the dict in a stable insertion order to keep behaviour
       predictable across backends.

    ``corpus`` IS in the lookup so a multi-corpus document doesn't share
    a single annotation between unrelated corpora — see the parallel
    docstring on ``_create_pdf_annotation`` for the permission rationale.

    ``creator`` is in the lookup AND in the backing partial
    UniqueConstraint ``annotation_unique_span_label_grounding_key`` so
    racing Celery retries collapse to a single row.
    """
    from opencontractserver.annotations.models import SPAN_LABEL, Annotation

    # See sibling note in ``_create_pdf_annotation``: ``structural=False`` is
    # in the lookup so the constraint condition and get_or_create lookup
    # cover the exact same row population.
    annot, _ = Annotation.objects.get_or_create(
        document=document,
        corpus=corpus,
        annotation_label=label_obj,
        annotation_type=SPAN_LABEL,
        raw_text=result.matched_text,
        json={"start": result.char_start, "end": result.char_end},
        creator_id=creator_id,
        is_grounding_source=True,
        structural=False,
        defaults={
            "page": 1,
        },
    )
    return annot


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@sync_to_async
def _resolve_corpus(corpus_id: int) -> Corpus | None:
    """Resolve a corpus ID to a Corpus instance."""
    from opencontractserver.corpuses.models import Corpus

    try:
        return Corpus.objects.get(pk=corpus_id)
    except Corpus.DoesNotExist:
        logger.warning("Corpus id=%d not found for auto-grounding", corpus_id)
        return None


async def ground_extraction_to_annotations(
    datacell: Datacell,
    document: Document,
    corpus: Corpus | int | None,
    user_id: int,
    *,
    fuzzy_threshold: float = 0.75,
    enable_fuzzy: bool = True,
) -> list[Annotation]:
    """Auto-ground a completed Datacell's extracted data to source annotations.

    This is the main entry point.  Call it after ``datacell.data`` has been
    populated with extraction results.

    Steps:
        1. Extract groundable text strings from ``datacell.data``
        2. Load document text (format-aware: PDF/text/DOCX)
        3. Align each string to the document text
        4. Create Annotation objects (TOKEN_LABEL or SPAN_LABEL)
        5. Link annotations to ``datacell.sources`` M2M

    Args:
        datacell: A Datacell with populated ``data`` field.
        document: The source Document.
        corpus: The Corpus instance or corpus ID (int). May be None.
        user_id: Creator ID for the annotations.
        fuzzy_threshold: Minimum similarity for fuzzy matches.
        enable_fuzzy: Whether to attempt fuzzy matching.

    Returns:
        List of created Annotation instances (may be empty).
    """
    if not datacell.data:
        return []

    if corpus is None:
        logger.info(
            "Skipping auto-grounding for datacell %d: no corpus context",
            datacell.id,
        )
        return []

    # Resolve corpus ID to Corpus instance if needed
    if isinstance(corpus, int):
        corpus = await _resolve_corpus(corpus)
        if corpus is None:
            return []

    # 1. Extract groundable strings
    if isinstance(datacell.data, dict):
        raw_data = datacell.data.get(DATACELL_DATA_KEY)
        if raw_data is None and datacell.data:
            logger.debug(
                "Datacell %d data dict has no %r key; available keys: %s",
                datacell.id,
                DATACELL_DATA_KEY,
                list(datacell.data.keys()),
            )
    else:
        raw_data = datacell.data
    groundable = extract_groundable_strings(raw_data)

    if not groundable:
        logger.debug("No groundable strings found in datacell %d", datacell.id)
        return []

    logger.info(
        "Auto-grounding datacell %d: %d groundable strings from extraction",
        datacell.id,
        len(groundable),
    )

    # 2. Load document text + optional PDF layer
    doc_text, pdf_layer, annotation_type = await _load_document_text_and_layer(document)

    # 3. Align strings to document
    alignments = align_text_to_document(
        groundable,
        doc_text,
        fuzzy_threshold=fuzzy_threshold,
        enable_fuzzy=enable_fuzzy,
    )

    if not alignments:
        logger.info(
            "No alignment hits for datacell %d (%d queries tried)",
            datacell.id,
            len(groundable),
        )
        return []

    logger.info(
        "Aligned %d/%d strings for datacell %d",
        len(alignments),
        len(groundable),
        datacell.id,
    )

    # 4. Create annotations
    annotations = await _create_grounding_annotations(
        alignment_results=alignments,
        document=document,
        corpus=corpus,
        creator_id=user_id,
        pdf_layer=pdf_layer,
        annotation_type=annotation_type,
    )

    # 5. Link to datacell
    if annotations:
        await _link_sources(datacell, annotations)
        logger.info(
            "Linked %d source annotations to datacell %d",
            len(annotations),
            datacell.id,
        )

    return annotations


@sync_to_async
def _link_sources(datacell: Datacell, annotations: list[Annotation]) -> None:
    """Add annotation objects to datacell.sources M2M."""
    datacell.sources.add(*annotations)
