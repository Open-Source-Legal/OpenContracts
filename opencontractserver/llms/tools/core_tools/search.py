"""Tools that search documents and return matches as ``SourceNode`` objects."""

from typing import TYPE_CHECKING
from uuid import uuid4

from opencontractserver.documents.models import Document
from opencontractserver.utils.compact_pawls import expand_pawls_pages

from ._helpers import _db_sync_to_async

if TYPE_CHECKING:
    from opencontractserver.llms.agents.core_agents import SourceNode


def search_exact_text_as_sources(
    document_id: int,
    search_strings: list[str],
    corpus_id: int | None = None,
) -> list["SourceNode"]:
    """Find exact text matches and return them as SourceNode objects.

    This function reuses the same document loading logic as
    :func:`add_annotations_from_exact_strings` but returns source objects
    instead of creating annotations.

    For PDFs: Uses PAWLS layer + PlasmaPDF to get token positions, pages, bounding boxes.
    For Text: Uses txt_extract file to get character spans.

    Parameters
    ----------
    document_id: int
        Primary key of the Document to search.
    search_strings: list[str]
        List of exact strings to find. All occurrences of each string will be found.
    corpus_id: int | None
        Optional corpus context. Used for metadata only (not for validation).

    Returns
    -------
    list[SourceNode]
        Flattened list of all matches as SourceNode objects with:
        - annotation_id: Synthetic negative ID (unique per match)
        - content: The matched text
        - similarity_score: 1.0 (perfect match)
        - metadata: document_id, corpus_id, page, position info, search_string

    Raises
    ------
    ValueError
        If document doesn't exist or has unsupported file type.
    """
    import json

    from plasmapdf.models.PdfDataLayer import build_translation_layer
    from plasmapdf.models.types import SpanAnnotation, TextSpan

    # Import SourceNode from core_agents to avoid circular dependencies
    from opencontractserver.llms.agents.core_agents import SourceNode

    try:
        doc = Document.objects.get(pk=document_id)
    except Document.DoesNotExist as exc:
        raise ValueError(f"Document id={document_id} does not exist") from exc

    file_type = (doc.file_type or "").lower()
    sources: list[SourceNode] = []
    synthetic_id_counter = -1  # Start with negative IDs

    if file_type == "application/pdf":
        if not doc.pawls_parse_file:
            raise ValueError(
                f"PDF document id={document_id} lacks a PAWLS layer; cannot search."
            )

        # Load PAWLS tokens once
        with doc.pawls_parse_file.open("r") as f:
            pawls_tokens = expand_pawls_pages(json.load(f))

        pdf_layer = build_translation_layer(pawls_tokens)
        doc_text = pdf_layer.doc_text

        # Find all matches for each search string
        for search_str in search_strings:
            start_idx = 0
            while True:
                pos = doc_text.find(search_str, start_idx)
                if pos == -1:
                    break

                end_idx = pos + len(search_str)

                # Create TextSpan and SpanAnnotation to get bounding box info
                span = TextSpan(
                    id=str(uuid4()),
                    start=pos,
                    end=end_idx,
                    text=doc_text[pos:end_idx],
                )

                span_annotation = SpanAnnotation(
                    span=span, annotation_label=""  # No label needed for search results
                )

                # Get OpenContracts annotation structure (has page, bounding_box, etc.)
                oc_ann = pdf_layer.create_opencontract_annotation_from_span(
                    span_annotation
                )

                # Build SourceNode
                sources.append(
                    SourceNode(
                        annotation_id=synthetic_id_counter,
                        content=doc_text[pos:end_idx],
                        similarity_score=1.0,  # Perfect match
                        metadata={
                            "document_id": document_id,
                            "corpus_id": corpus_id,
                            "page": oc_ann.get("page", 1),
                            "annotation_json": oc_ann[
                                "annotation_json"
                            ],  # Full MultipageAnnotationJson from PlasmaPDF
                            "search_string": search_str,
                            "char_start": pos,
                            "char_end": end_idx,
                            "bounding_box": oc_ann.get("bounds"),
                            "match_type": "exact_text_pdf",
                        },
                    )
                )

                synthetic_id_counter -= 1
                start_idx = end_idx

    elif file_type in {"application/txt", "text/plain"}:
        if not doc.txt_extract_file:
            raise ValueError(
                f"Text document id={document_id} lacks txt_extract_file; cannot search."
            )

        with doc.txt_extract_file.open("r") as f:
            doc_text = f.read()

        # Find all matches for each search string
        for search_str in search_strings:
            start_idx = 0
            while True:
                pos = doc_text.find(search_str, start_idx)
                if pos == -1:
                    break

                end_idx = pos + len(search_str)

                # Build SourceNode (text files = page 1, no bounding box)
                sources.append(
                    SourceNode(
                        annotation_id=synthetic_id_counter,
                        content=doc_text[pos:end_idx],
                        similarity_score=1.0,  # Perfect match
                        metadata={
                            "document_id": document_id,
                            "corpus_id": corpus_id,
                            "page": 1,
                            "search_string": search_str,
                            "char_start": pos,
                            "char_end": end_idx,
                            "match_type": "exact_text_plain",
                        },
                    )
                )

                synthetic_id_counter -= 1
                start_idx = end_idx

    else:
        raise ValueError(
            f"Unsupported file_type {doc.file_type} for document id={document_id}"
        )

    return sources


async def asearch_exact_text_as_sources(
    document_id: int,
    search_strings: list[str],
    corpus_id: int | None = None,
):
    """Async wrapper around :func:`search_exact_text_as_sources`."""
    return await _db_sync_to_async(search_exact_text_as_sources)(
        document_id=document_id,
        search_strings=search_strings,
        corpus_id=corpus_id,
    )
