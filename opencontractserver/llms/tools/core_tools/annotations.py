"""Tools for duplicating annotations and creating annotations from exact strings."""

import logging
from uuid import uuid4

from typing_extensions import TypedDict

from opencontractserver.utils.compact_pawls import expand_pawls_pages

from ._helpers import _db_sync_to_async

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Annotation duplication helpers                                              #
# --------------------------------------------------------------------------- #


def duplicate_annotations_with_label(
    annotation_ids: list[int],
    *,
    new_label_text: str,
    creator_id: int,
    label_type: str | None = None,
) -> list[int]:
    """Duplicate existing annotations applying *new_label_text* (synchronous).

    This synchronous variant ensures the required label-set and label exist on
    each annotation's corpus *without* relying on any helper methods grafted
    onto the :class:`~opencontractserver.corpuses.models.Corpus` model.

    Parameters
    ----------
    annotation_ids:
        Primary keys of the annotations to duplicate.
    new_label_text:
        The text of the label to assign to the duplicates. Case-sensitive.
    creator_id:
        User identifier recorded as *creator* for both the duplicates and for
        any label/label-set created on-the-fly.
    label_type:
        Optional label type (defaults to ``TOKEN_LABEL`` when *None*).

    Returns
    -------
    list[int]
        Primary keys of the newly created annotations in the same order as the
        input list.
    """

    from django.db import transaction

    from opencontractserver.annotations.models import (
        TOKEN_LABEL,
        Annotation,
        AnnotationLabel,
        LabelSet,
    )

    if label_type is None:
        label_type = TOKEN_LABEL

    # Fetch annotations; keep their database objects in memory while
    # preserving the order of *annotation_ids*.
    annotations = list(
        Annotation.objects.filter(pk__in=annotation_ids).select_related(
            "corpus", "document"
        )
    )

    if len(annotations) != len(annotation_ids):
        missing = set(annotation_ids) - {a.pk for a in annotations}
        raise ValueError(f"Annotation(s) not found: {sorted(missing)}")

    new_ids: list[int] = []
    label_cache: dict[int, AnnotationLabel] = {}

    with transaction.atomic():
        for ann in annotations:
            if ann.corpus_id is None:
                raise ValueError(
                    f"Annotation id={ann.pk} is not associated with a corpus and "
                    "cannot be duplicated with a corpus label."
                )

            corpus = ann.corpus  # already fetched via select_related

            # Obtain / create label for this corpus (use cache to minimise DB chatter).
            label = label_cache.get(corpus.pk)
            if label is None:
                # Ensure corpus has a label-set.
                if corpus.label_set_id is None:
                    corpus.label_set = LabelSet.objects.create(
                        title=f"LabelSet for Corpus {corpus.pk}",
                        description="",
                        creator_id=creator_id,
                    )
                    corpus.save(update_fields=["label_set", "modified"])

                # Look for existing label with given text & type.
                label_qs = corpus.label_set.annotation_labels.filter(
                    text=new_label_text, label_type=label_type
                )
                label = label_qs.first()

                if label is None:
                    label = AnnotationLabel.objects.create(
                        text=new_label_text,
                        label_type=label_type,
                        color="#05313d",
                        description="",
                        icon="tags",
                        creator_id=creator_id,
                    )
                    corpus.label_set.annotation_labels.add(label)

                label_cache[corpus.pk] = label

            # Create the duplicate annotation.
            duplicate = Annotation.objects.create(
                page=ann.page,
                raw_text=ann.raw_text,
                json=ann.json,
                parent=ann.parent,
                annotation_type=ann.annotation_type,
                annotation_label=label,
                document=ann.document,
                corpus=corpus,
                structural=ann.structural,
                creator_id=creator_id,
            )

            new_ids.append(duplicate.pk)

    return new_ids


async def aduplicate_annotations_with_label(
    annotation_ids: list[int],
    *,
    new_label_text: str,
    creator_id: int,
    label_type: str | None = None,
):
    """Async wrapper around :func:`duplicate_annotations_with_label`."""
    return await _db_sync_to_async(duplicate_annotations_with_label)(
        annotation_ids,
        new_label_text=new_label_text,
        creator_id=creator_id,
        label_type=label_type,
    )


# --------------------------------------------------------------------------- #
# Exact-string annotation helper for PDFs                                     #
# --------------------------------------------------------------------------- #


class AnnotationItem(TypedDict):
    """Single annotation request for exact-string matching."""

    label_text: str
    exact_string: str


def add_annotations_from_exact_strings(
    items: list[AnnotationItem],
    *,
    document_id: int,
    corpus_id: int,
    creator_id: int,
    corpus_action_id: int | None = None,
) -> list[int]:
    """Create annotations for exact string matches in documents.

    Each *item* is a dict with keys:
    - ``label_text`` (str): The label to apply.
    - ``exact_string`` (str): The exact text to find in the document.

    Args:
        document_id: The document to annotate (injected from context).
        corpus_id: The corpus the document belongs to (injected from context).
        creator_id: The user creating annotations (injected from context).
        corpus_action_id: Optional corpus action that triggered this (injected from context).

    • PDF (application/pdf): builds token‐level annotations (TOKEN_LABEL) via PlasmaPDF.
    • Plain-text (application/txt, text/plain): builds span annotations (SPAN_LABEL).

    Other file types raise ``ValueError``.
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
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.documents.models import Document

    # Collect (label_text, exact_string) pairs for the single doc/corpus.
    tuples: list[tuple[str, str]] = []
    for item in items:
        tuples.append((str(item["label_text"]), str(item["exact_string"])))

    created_ids: list[int] = []

    doc_id = document_id

    # Validate document & corpus linkage.
    try:
        doc = Document.objects.get(pk=doc_id)
    except Document.DoesNotExist as exc:
        raise ValueError(f"Document id={doc_id} does not exist") from exc

    try:
        corpus = Corpus.objects.get(pk=corpus_id)
    except Corpus.DoesNotExist as exc:
        raise ValueError(f"Corpus id={corpus_id} does not exist") from exc

    # Data-linkage check only — permission is gated upstream by the tool
    # framework. Uses the internal helper to skip the deprecation warning;
    # user-context callers should go through
    # CorpusObjsService.is_document_in_corpus instead.
    if not corpus._get_active_documents().filter(pk=doc_id).exists():
        raise ValueError(
            f"Document id={doc_id} is not linked to corpus id={corpus_id}."
        )

    file_type = (doc.file_type or "").lower()
    if not file_type:
        raise ValueError(
            f"Document id={doc_id} has no file_type set; cannot create index."
        )

    if file_type == "application/pdf":
        if not doc.pawls_parse_file:
            raise ValueError(
                f"PDF document id={doc_id} lacks a PAWLS layer; cannot annotate."
            )

        # Load PAWLS tokens once per document.
        with doc.pawls_parse_file.open("r") as f:
            pawls_tokens = expand_pawls_pages(json.load(f))

        pdf_layer = build_translation_layer(pawls_tokens)
        doc_text = pdf_layer.doc_text

        label_type_const = TOKEN_LABEL

        def _create_annotation(pos: int, end_idx: int, label_obj):
            span = TextSpan(
                id=str(uuid4()), start=pos, end=end_idx, text=doc_text[pos:end_idx]
            )
            span_annotation = SpanAnnotation(span=span, annotation_label=label_obj.text)
            oc_ann = pdf_layer.create_opencontract_annotation_from_span(span_annotation)

            return Annotation(
                raw_text=oc_ann["rawText"],
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
                f"Text document id={doc_id} lacks txt_extract_file; cannot annotate."
            )
        with doc.txt_extract_file.open("r") as f:
            doc_text = f.read()

        label_type_const = SPAN_LABEL

        def _create_annotation(pos: int, end_idx: int, label_obj):
            return Annotation(
                raw_text=doc_text[pos:end_idx],
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
            f"Unsupported file_type {doc.file_type} for document id={doc_id}"
        )

    # Common creation loop (works for both PDF and text).
    with transaction.atomic():
        for label_text, exact_str in tuples:
            label_obj = corpus.ensure_label_and_labelset(
                label_text=label_text,
                creator_id=creator_id,
                label_type=label_type_const,
            )

            start_idx = 0
            while True:
                pos = doc_text.find(exact_str, start_idx)
                if pos == -1:
                    break

                end_idx = pos + len(exact_str)

                annot_obj = _create_annotation(pos, end_idx, label_obj)
                annot_obj.save()

                created_ids.append(annot_obj.pk)

                start_idx = end_idx

    return created_ids


async def aadd_annotations_from_exact_strings(
    items: list[AnnotationItem],
    *,
    document_id: int,
    corpus_id: int,
    creator_id: int,
    corpus_action_id: int | None = None,
):
    """Async wrapper around :func:`add_annotations_from_exact_strings`."""
    return await _db_sync_to_async(add_annotations_from_exact_strings)(
        items,
        document_id=document_id,
        corpus_id=corpus_id,
        creator_id=creator_id,
        corpus_action_id=corpus_action_id,
    )
