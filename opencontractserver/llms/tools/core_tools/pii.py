"""Agent tool: scan documents for PII via the privacy-filter microservice
and create labeled annotations for each detection.

PDFs receive token-level annotations through PlasmaPDF (TOKEN_LABEL).
Plain-text documents receive character-span annotations (SPAN_LABEL).
"""

from __future__ import annotations

import json as _json
import logging
from collections.abc import Callable
from typing import Any, NamedTuple
from uuid import uuid4

from django.db import transaction
from plasmapdf.models.types import SpanAnnotation, TextSpan

from opencontractserver.annotations.compact_json import (
    compact_annotation_json,
    is_compact_format,
    is_span_format,
)
from opencontractserver.annotations.models import SPAN_LABEL, TOKEN_LABEL, Annotation
from opencontractserver.constants.document_processing import (
    PII_ANNOTATION_BULK_BATCH_SIZE,
    TEXT_MIMETYPES,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.tasks.embeddings_task import (
    calculate_embedding_for_annotation_text,
)
from opencontractserver.utils.files import read_field_file_text

from ._helpers import _db_sync_to_async
from ._privacy_filter_client import Detection, adetect_pii

logger = logging.getLogger(__name__)


# Mapping from privacy-filter entity_group → (label_text, color, icon).
# Labels are auto-created via Corpus.ensure_label_and_labelset on first use.
ENTITY_GROUP_LABELS: dict[str, tuple[str, str, str]] = {
    "private_email": ("PII: Email", "#1f77b4", "mail"),
    "phone_number": ("PII: Phone", "#ff7f0e", "phone"),
    "person_name": ("PII: Person Name", "#2ca02c", "user"),
    "address": ("PII: Address", "#d62728", "home"),
    "account_number": ("PII: Account Number", "#9467bd", "credit card"),
    "url": ("PII: URL", "#8c564b", "linkify"),
    "date": ("PII: Date", "#e377c2", "calendar"),
    "secret": ("PII: Secret", "#7f7f7f", "key"),
}


class _DocTextResult(NamedTuple):
    """Validated document text + linkage info, returned by ``_load_doc_text_sync``."""

    doc: Document
    corpus: Corpus
    doc_text: str
    file_type: str
    pdf_layer: Any  # plasmapdf translation layer for PDFs; None otherwise


def _load_doc_text_sync(document_id: int, corpus_id: int) -> _DocTextResult:
    """Validate document↔corpus linkage and return text + layer for scanning.

    For PDFs the PlasmaPDF translation layer is built here and returned so
    it can be forwarded directly into ``_persist_annotations_sync`` without
    a second PAWLs read.  For non-PDF documents ``pdf_layer`` is ``None``.
    Markdown documents are accepted alongside plain-text — both ride the
    ``TEXT_MIMETYPES`` set so the supported list stays in lockstep with the
    rest of the ingestion pipeline.

    Note: this helper does NOT perform an authorization check. Write
    permission on the corpus is enforced by the agent tool framework via
    the ``requires_write_permission=True`` flag on the registered
    ``ToolDefinition`` (see ``ScanAndAnnotateRegistryTests``). The helper
    is module-private (``_``-prefix) precisely because callers outside
    the tool framework would bypass that gate. Do not promote this
    function to public API without adding an explicit ``user_can`` check
    first.
    """
    try:
        doc = Document.objects.get(pk=document_id)
    except Document.DoesNotExist as exc:
        raise ValueError(f"Document id={document_id} does not exist") from exc

    try:
        corpus = Corpus.objects.get(pk=corpus_id)
    except Corpus.DoesNotExist as exc:
        raise ValueError(f"Corpus id={corpus_id} does not exist") from exc

    # Data-linkage check only — authorization is gated upstream by the agent
    # tool framework (see docstring above). Uses the internal helper to skip
    # the deprecation warning; user-context callers should go through
    # CorpusDocumentService.is_document_in_corpus instead.
    if not corpus._get_active_documents().filter(pk=document_id).exists():
        raise ValueError(
            f"Document id={document_id} is not linked to corpus id={corpus_id}."
        )

    file_type = (doc.file_type or "").lower()
    if not file_type:
        raise ValueError(f"Document id={document_id} has no file_type set.")

    if file_type in TEXT_MIMETYPES:
        if not doc.txt_extract_file:
            raise ValueError(f"Text document id={document_id} lacks txt_extract_file.")
        # errors="replace" keeps this agent tool fault-tolerant: a few
        # undecodable bytes substitute U+FFFD rather than raising
        # UnicodeDecodeError on read.
        doc_text = read_field_file_text(doc.txt_extract_file, errors="replace")
        return _DocTextResult(doc, corpus, doc_text, file_type, None)

    if file_type == "application/pdf":
        if not doc.pawls_parse_file:
            raise ValueError(f"PDF document id={document_id} lacks a PAWLS layer.")
        from plasmapdf.models.PdfDataLayer import build_translation_layer

        from opencontractserver.utils.compact_pawls import expand_pawls_pages

        with doc.pawls_parse_file.open("r") as f:
            pawls_tokens = expand_pawls_pages(_json.load(f))
        pdf_layer = build_translation_layer(pawls_tokens)
        return _DocTextResult(doc, corpus, pdf_layer.doc_text, file_type, pdf_layer)

    raise ValueError(
        f"Unsupported file_type {doc.file_type} for document id={document_id}"
    )


def _queue_embed(pk: int, cid: int) -> Callable[[], None]:
    """Return a no-arg ``transaction.on_commit`` callback bound to ``(pk, cid)``.

    Closure factory used by ``_persist_annotations_sync`` to schedule a
    ``calculate_embedding_for_annotation_text`` Celery task once the
    surrounding atomic block commits. The factory + named inner ``_fire``
    fixes a ``Cannot infer type of lambda`` mypy error we hit when
    registering this inline, and also rebinds ``pk`` / ``cid`` per call so
    the classic late-binding-in-loop bug can't fire. Lives at module scope
    so it isn't redefined on every ``_persist_annotations_sync`` invocation.
    """

    def _fire() -> None:
        calculate_embedding_for_annotation_text.si(
            annotation_id=pk, corpus_id=cid
        ).apply_async(task_id=f"embed-annot-{pk}")

    return _fire


def _persist_annotations_sync(
    *,
    doc: Any,
    corpus: Any,
    pdf_layer: Any,
    creator_id: int,
    corpus_action_id: int | None,
    file_type: str,
    detections: list[Detection],
    doc_text: str,
) -> list[tuple[int, Detection]]:
    """Create one Annotation per detection.

    Returns (annotation_id, detection) pairs for detections that were
    actually persisted. Invalid spans (OOB / inverted) and unknown entity
    groups are skipped with a warning, so the returned list may be shorter
    than ``detections`` — callers derive ``detection_count`` and
    ``by_entity_group`` from this list to keep the response self-consistent.
    """
    label_type_const = TOKEN_LABEL if file_type == "application/pdf" else SPAN_LABEL

    # Pre-create every label the upcoming detections need *outside* the
    # ``transaction.atomic()`` block below. ``ensure_label_and_labelset``
    # *does* wrap its own check-then-create in a ``transaction.atomic()``
    # (see ``corpuses/models.py`` ~line 1318), but with PostgreSQL's
    # default READ COMMITTED isolation that atomic block doesn't prevent
    # the race: two concurrent transactions can both pass
    # ``filter().first()`` *before* either commits the insert, since
    # there is no DB-level uniqueness constraint on
    # ``AnnotationLabel(text, label_type)``. So two concurrent scans on
    # the same fresh corpus *can* still create duplicate labels. We
    # accept that rare duplicate; pre-creating outside the inner atomic
    # block isolates the duplicate to the label table so the much
    # bigger Annotation insert batch isn't rolled back. The inner
    # atomic block only inserts ``Annotation`` rows, which carry no
    # cross-row uniqueness, so it can never fail for a reason caused
    # by a peer scan racing with us. See
    # ``test_persist_annotations_sync_duplicate_label_race`` for the
    # regression guard that documents this accepted-duplicate behavior.
    needed_groups = {
        det["entity_group"]
        for det in detections
        if det["entity_group"] in ENTITY_GROUP_LABELS
    }
    label_cache: dict[str, Any] = {}
    for group in needed_groups:
        label_text, color, icon = ENTITY_GROUP_LABELS[group]
        label_cache[group] = corpus.ensure_label_and_labelset(
            label_text=label_text,
            creator_id=creator_id,
            label_type=label_type_const,
            color=color,
            icon=icon,
        )

    # Build all Annotation instances first, then bulk_create. bulk_create
    # skips the ``post_save`` signal that normally queues embedding work
    # (see ``annotations/signals.py:process_annot_on_create_atomic``), so
    # we queue embeddings manually below — mirroring the established
    # pattern in ``annotations/models.py`` for duplicated annotation sets.
    pending: list[tuple[Annotation, Detection]] = []
    for det in detections:
        start, end = det["start"], det["end"]
        if start < 0 or end > len(doc_text) or start >= end:
            logger.warning(
                "scan_and_annotate_pii: skipping invalid detection "
                "start=%s end=%s len=%s",
                start,
                end,
                len(doc_text),
            )
            continue
        group = det["entity_group"]
        if group not in ENTITY_GROUP_LABELS:
            logger.warning(
                "scan_and_annotate_pii: unknown entity_group=%r from privacy-filter; skipping",
                group,
            )
            continue
        label_obj = label_cache[group]
        if file_type == "application/pdf":
            span = TextSpan(
                id=str(uuid4()), start=start, end=end, text=doc_text[start:end]
            )
            span_annotation = SpanAnnotation(span=span, annotation_label=label_obj.text)
            oc_ann = pdf_layer.create_opencontract_annotation_from_span(span_annotation)
            # ``Annotation.save()`` normally auto-compacts TOKEN_LABEL JSON
            # to v2 format; ``bulk_create`` skips ``save()`` so we run the
            # compaction explicitly here (idempotent — v2 in == v2 out).
            ann_json = oc_ann["annotation_json"]
            if (
                isinstance(ann_json, dict)
                and ann_json
                and not is_compact_format(ann_json)
                and not is_span_format(ann_json)
            ):
                try:
                    ann_json = compact_annotation_json(ann_json)
                except (ValueError, KeyError, TypeError):
                    # Narrow on malformed input only. Other errors
                    # (memory, runtime bugs) propagate so we don't
                    # silently mask real failures.
                    logger.exception(
                        "scan_and_annotate_pii: failed to compact annotation JSON; storing as-is"
                    )
            ann = Annotation(
                raw_text=oc_ann["rawText"],
                page=oc_ann.get("page", 1),
                json=ann_json,
                annotation_label=label_obj,
                document=doc,
                corpus=corpus,
                creator_id=creator_id,
                corpus_action_id=corpus_action_id,
                annotation_type=TOKEN_LABEL,
                structural=False,
            )
        else:
            ann = Annotation(
                raw_text=doc_text[start:end],
                page=1,
                json={"start": start, "end": end},
                annotation_label=label_obj,
                document=doc,
                corpus=corpus,
                creator_id=creator_id,
                corpus_action_id=corpus_action_id,
                annotation_type=SPAN_LABEL,
                structural=False,
            )
        pending.append((ann, det))

    if not pending:
        return []

    annotations = [ann for ann, _ in pending]
    corpus_pk = corpus.pk
    with transaction.atomic():
        # bulk_create returns the same instances with ``pk`` populated
        # (PostgreSQL ``RETURNING``).
        Annotation.objects.bulk_create(
            annotations, batch_size=PII_ANNOTATION_BULK_BATCH_SIZE
        )

        # Queue embeddings on commit so workers never read rows that haven't
        # been committed yet. Registered inside the atomic block so the
        # callbacks are dropped if bulk_create rolls back. Keeps the same
        # task-id-based dedup the post_save signal handler used. The
        # ``_queue_embed`` factory lives at module scope (see above) so it
        # isn't redefined on every call into ``_persist_annotations_sync``.
        for ann in annotations:
            # Explicit raise instead of ``assert`` so the invariant survives
            # production interpreters launched with ``-O`` (which strip
            # asserts). A missing pk would silently collapse every embedding
            # task into a single dedup-key and lose embeddings.
            if ann.pk is None:
                raise RuntimeError(
                    "bulk_create did not populate annotation.pk — "
                    "the database backend must support RETURNING"
                )
            transaction.on_commit(_queue_embed(ann.pk, corpus_pk))

    return [(ann.pk, det) for ann, det in pending]


async def ascan_and_annotate_pii(
    *,
    # context-injected by the tool framework
    document_id: int,
    corpus_id: int,
    creator_id: int,
    corpus_action_id: int | None = None,
    # agent-controllable knobs
    min_score: float = 0.5,
    entity_groups: list[str] | None = None,
    dry_run: bool = False,
    start_char: int | None = None,
    end_char: int | None = None,
) -> dict[str, Any]:
    """Scan ``document_id`` for PII and create labeled annotations.

    Args:
        document_id: Document to scan (injected from context).
        corpus_id: Corpus that owns the document (injected from context).
        creator_id: User credited as annotation creator (injected from context).
        corpus_action_id: Optional triggering corpus action (injected from context).
        min_score: Drop detections with score < this value (default 0.5).
        entity_groups: Optional allowlist (e.g. ``["private_email"]``);
            ``None`` means accept all 8 categories.
        dry_run: If True, return detections without writing annotations.
        start_char, end_char: Optional character range scoping the scan.
            Offsets returned are always global (relative to full doc_text).

    Returns a dict with: document_id, scanned_chars, detection_count,
    by_entity_group, annotation_ids (empty when dry_run), detections (only
    populated when dry_run).
    """
    doc, corpus, doc_text, file_type, pdf_layer = await _db_sync_to_async(
        _load_doc_text_sync
    )(
        document_id, corpus_id
    )  # NamedTuple — fields stay named for IDE/grep

    s = 0 if start_char is None else max(0, min(start_char, len(doc_text)))
    e = len(doc_text) if end_char is None else max(0, min(end_char, len(doc_text)))
    if s >= e:
        return {
            "document_id": document_id,
            "scanned_chars": 0,
            "detection_count": 0,
            "by_entity_group": {},
            "annotation_ids": [],
            "detections": [],
        }

    # Validate the allowlist up-front: silently dropping every detection
    # because the caller passed a typo (e.g. ``"private_emial"``) would be
    # a frustrating failure mode for the LLM.
    allowlist: set[str] | None = None
    if entity_groups:
        unknown = sorted(set(entity_groups) - set(ENTITY_GROUP_LABELS))
        if unknown:
            raise ValueError(
                "Unknown entity_groups: "
                f"{unknown}. Valid groups: {sorted(ENTITY_GROUP_LABELS)}."
            )
        allowlist = set(entity_groups)

    slice_text = doc_text[s:e]
    raw = await adetect_pii(slice_text)

    detections: list[Detection] = []
    for det in raw:
        if det["score"] < float(min_score):
            continue
        if allowlist is not None and det["entity_group"] not in allowlist:
            continue
        g_start = det["start"] + s
        g_end = det["end"] + s
        detections.append(
            Detection(
                entity_group=det["entity_group"],
                score=det["score"],
                start=g_start,
                end=g_end,
                text=doc_text[g_start:g_end],
            )
        )

    by_group: dict[str, int] = {}
    for d in detections:
        by_group[d["entity_group"]] = by_group.get(d["entity_group"], 0) + 1

    if dry_run:
        return {
            "document_id": document_id,
            "scanned_chars": len(slice_text),
            "detection_count": len(detections),
            "by_entity_group": by_group,
            "annotation_ids": [],
            "detections": [dict(d) for d in detections],
        }

    persisted = await _db_sync_to_async(_persist_annotations_sync)(
        doc=doc,
        corpus=corpus,
        pdf_layer=pdf_layer,
        creator_id=creator_id,
        corpus_action_id=corpus_action_id,
        file_type=file_type,
        detections=detections,
        doc_text=doc_text,
    )

    # Derive count + per-group totals from the *persisted* detections so the
    # returned numbers always match ``annotation_ids``. Detections that were
    # filtered out inside ``_persist_annotations_sync`` (OOB spans, unknown
    # groups) would otherwise inflate the counts and confuse the LLM caller.
    new_ids = [pk for pk, _ in persisted]
    persisted_by_group: dict[str, int] = {}
    for _, det in persisted:
        persisted_by_group[det["entity_group"]] = (
            persisted_by_group.get(det["entity_group"], 0) + 1
        )
    return {
        "document_id": document_id,
        "scanned_chars": len(slice_text),
        "detection_count": len(new_ids),
        "by_entity_group": persisted_by_group,
        "annotation_ids": new_ids,
        "detections": [],
    }
