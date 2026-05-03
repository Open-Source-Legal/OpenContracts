"""Tools for building hierarchical document indexes from exact-string anchors."""

import logging
from uuid import uuid4

from typing_extensions import NotRequired, TypedDict

from opencontractserver.utils.compact_pawls import expand_pawls_pages

from ._helpers import _db_sync_to_async

logger = logging.getLogger(__name__)


class IndexEntryItem(TypedDict):
    """Single entry for building a hierarchical document index."""

    title: str
    exact_string: str
    long_description: NotRequired[str]
    parent_index: NotRequired[int]  # -1 for root entries, otherwise index into the list


def create_document_index(
    entries: list[IndexEntryItem],
    *,
    document_id: int,
    corpus_id: int,
    creator_id: int,
    corpus_action_id: int | None = None,
) -> list[int]:
    """Create a hierarchical document index from exact string matches.

    Each *entry* is a dict with keys:
    - ``title`` (str): Section heading text.
    - ``exact_string`` (str): The exact text to anchor this section in the
      document.
    - ``long_description`` (str): Markdown summary of the section content.
    - ``parent_index`` (int): Index into *entries* pointing to this entry's
      parent.  Use ``-1`` for root-level entries.

    Annotations are created with the ``OC_SECTION`` label and linked via the
    ``parent`` FK to form a hierarchy.

    .. note::
        ``exact_string`` matching uses the *first* occurrence in the document.
        If the same string appears multiple times, later occurrences cannot be
        targeted.  Use a longer, unique surrounding snippet when ambiguity is
        possible.

    Args:
        entries: List of index entries to create.
        document_id: Target document (injected from context).
        corpus_id: Target corpus (injected from context).
        creator_id: User creating the index (injected from context).
        corpus_action_id: Optional corpus action that triggered this.

    Returns:
        List of created Annotation PKs in the same order as *entries*.
    """

    import json

    from django.db import transaction
    from plasmapdf.models.PdfDataLayer import build_translation_layer
    from plasmapdf.models.types import SpanAnnotation, TextSpan

    from opencontractserver.annotations.models import (
        SPAN_LABEL,
        TOKEN_LABEL,
        Annotation,
    )
    from opencontractserver.constants.annotations import (
        DOCUMENT_ANNOTATION_INDEX_LIMIT,
        OC_SECTION_LABEL,
    )
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.documents.models import Document

    if len(entries) > DOCUMENT_ANNOTATION_INDEX_LIMIT:
        raise ValueError(
            f"entries list ({len(entries)}) exceeds maximum allowed size "
            f"of {DOCUMENT_ANNOTATION_INDEX_LIMIT}."
        )

    # Validate document and corpus.
    try:
        doc = Document.objects.get(pk=document_id)
    except Document.DoesNotExist as exc:
        raise ValueError(f"Document id={document_id} does not exist") from exc

    try:
        corpus = Corpus.objects.get(pk=corpus_id)
    except Corpus.DoesNotExist as exc:
        raise ValueError(f"Corpus id={corpus_id} does not exist") from exc

    if not corpus.get_documents().filter(pk=document_id).exists():
        raise ValueError(
            f"Document id={document_id} is not linked to corpus id={corpus_id}."
        )

    file_type = (doc.file_type or "").lower()
    if not file_type:
        raise ValueError(
            f"Document id={document_id} has no file_type set; cannot create index."
        )

    if file_type == "application/pdf":
        if not doc.pawls_parse_file:
            raise ValueError(
                f"PDF document id={document_id} lacks a PAWLS layer; "
                "cannot create index."
            )
        with doc.pawls_parse_file.open("r") as f:
            pawls_tokens = expand_pawls_pages(json.load(f))

        pdf_layer = build_translation_layer(pawls_tokens)
        doc_text = pdf_layer.doc_text
        label_type_const = TOKEN_LABEL

        def _make_annotation(pos, end_idx, label_obj, title, description):
            span = TextSpan(
                id=str(uuid4()),
                start=pos,
                end=end_idx,
                text=doc_text[pos:end_idx],
            )
            span_annotation = SpanAnnotation(span=span, annotation_label=label_obj.text)
            oc_ann = pdf_layer.create_opencontract_annotation_from_span(span_annotation)
            return Annotation(
                raw_text=title,
                long_description=description,
                page=oc_ann.get("page", 1),
                json=oc_ann["annotation_json"],
                annotation_label=label_obj,
                document=doc,
                corpus=corpus,
                creator_id=creator_id,
                corpus_action_id=corpus_action_id,
                annotation_type=TOKEN_LABEL,
                structural=False,
            )

    elif file_type in {"application/txt", "text/plain"}:
        if not doc.txt_extract_file:
            raise ValueError(
                f"Text document id={document_id} lacks txt_extract_file; "
                "cannot create index."
            )
        with doc.txt_extract_file.open("r") as f:
            doc_text = f.read()

        label_type_const = SPAN_LABEL

        def _make_annotation(pos, end_idx, label_obj, title, description):
            return Annotation(
                raw_text=title,
                long_description=description,
                page=1,
                json={"start": pos, "end": end_idx},
                annotation_label=label_obj,
                document=doc,
                corpus=corpus,
                creator_id=creator_id,
                corpus_action_id=corpus_action_id,
                annotation_type=SPAN_LABEL,
                structural=False,
            )

    else:
        raise ValueError(
            f"Unsupported file_type {doc.file_type} for document id={document_id}"
        )

    # ---- Validate all entries before any DB writes ----

    # Build parent_idx map and check for cycles up-front.
    parent_map: dict[int, int] = {}
    for i, entry in enumerate(entries):
        parent_idx = int(entry.get("parent_index", -1))
        if parent_idx >= 0:
            if parent_idx == i:
                raise ValueError(f"Entry {i} references itself as parent")
            if parent_idx >= len(entries):
                raise ValueError(
                    f"parent_index {parent_idx} out of range for entry {i}"
                )
            parent_map[i] = parent_idx

    for start in parent_map:
        visited: set[int] = set()
        current = start
        while current in parent_map:
            if current in visited:
                raise ValueError(
                    f"Cycle detected in parent_index references "
                    f"involving entry {current}"
                )
            visited.add(current)
            current = parent_map[current]

    # Validate exact strings and build (pos, end_idx) pairs.
    spans: list[tuple[int, int]] = []
    for entry in entries:
        exact_str = str(entry["exact_string"])
        pos = doc_text.find(exact_str)
        if pos == -1:
            raise ValueError(
                f"Exact string not found in document: {repr(exact_str[:80])}"
            )
        if doc_text.find(exact_str, pos + 1) != -1:
            logger.warning(
                "exact_string %r appears multiple times in document "
                "id=%d; anchoring to first occurrence.",
                exact_str[:80],
                document_id,
            )
        spans.append((pos, pos + len(exact_str)))

    # ---- All validation passed — perform DB writes ----

    with transaction.atomic():
        label_obj = corpus.ensure_label_and_labelset(
            label_text=OC_SECTION_LABEL,
            creator_id=creator_id,
            label_type=label_type_const,
        )

        annotations = [
            _make_annotation(
                pos,
                end_idx,
                label_obj,
                str(entry["title"]),
                entry.get("long_description") or None,
            )
            for (pos, end_idx), entry in zip(spans, entries)
        ]
        created = Annotation.objects.bulk_create(annotations)

        # Wire up parent hierarchy in bulk.
        to_update = []
        for i, parent_idx in parent_map.items():
            created[i].parent = created[parent_idx]
            to_update.append(created[i])
        if to_update:
            Annotation.objects.bulk_update(to_update, ["parent"])

    return [a.pk for a in created]


async def acreate_document_index(
    entries: list[IndexEntryItem],
    *,
    document_id: int,
    corpus_id: int,
    creator_id: int,
    corpus_action_id: int | None = None,
) -> list[int]:
    """Async wrapper around :func:`create_document_index`."""
    return await _db_sync_to_async(create_document_index)(
        entries,
        document_id=document_id,
        corpus_id=corpus_id,
        creator_id=creator_id,
        corpus_action_id=corpus_action_id,
    )
