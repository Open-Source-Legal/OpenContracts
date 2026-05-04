"""
Utility functions for annotation processing.

This module provides helper functions for working with annotations,
including content modality detection and token analysis.
"""

import json
import logging
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from opencontractserver.documents.models import Document

from opencontractserver.annotations.compact_json import iter_page_annotations
from opencontractserver.types.enums import ContentModality
from opencontractserver.utils.compact_pawls import expand_pawls_pages

logger = logging.getLogger(__name__)


def compute_content_modalities(
    tokens_jsons: list[dict[str, Any]],
    document: Optional["Document"] = None,
    pawls_data: Optional[list[dict[str, Any]]] = None,
) -> list[str]:
    """
    Compute the content modalities present in an annotation based on its tokens.

    Analyzes the referenced tokens to determine what types of content
    (text, images, etc.) are present in the annotation.

    Args:
        tokens_jsons: List of token references with {pageIndex, tokenIndex} format.
        document: Optional Document instance to load PAWLs data from.
                 If not provided, pawls_data must be supplied.
        pawls_data: Optional pre-loaded PAWLs data (list of page dicts).
                   If not provided, will be loaded from document.

    Returns:
        List of modality strings (e.g., ["TEXT"], ["IMAGE"], ["TEXT", "IMAGE"]).
        Returns ["TEXT"] as default if tokens cannot be analyzed.

    Example:
        >>> tokens = [{"pageIndex": 0, "tokenIndex": 0}, {"pageIndex": 0, "tokenIndex": 5}]
        >>> modalities = compute_content_modalities(tokens, document=doc)
        >>> print(modalities)  # ["TEXT", "IMAGE"] if tokenIndex 5 is an image
    """
    if not tokens_jsons:
        # No tokens referenced, default to TEXT for backward compatibility
        return [ContentModality.TEXT.value]

    # Load PAWLs data if not provided
    if pawls_data is None:
        if document is None:
            logger.warning(
                "compute_content_modalities: No document or pawls_data provided, "
                "defaulting to TEXT"
            )
            return [ContentModality.TEXT.value]

        pawls_content = document.pawls_parse_file
        if not pawls_content:
            return [ContentModality.TEXT.value]

        try:
            if hasattr(pawls_content, "read"):
                pawls_content.open("r")
                try:
                    pawls_data = expand_pawls_pages(json.load(pawls_content))
                finally:
                    pawls_content.close()
            else:
                pawls_data = expand_pawls_pages(pawls_content)
        except Exception as e:
            logger.error(f"Failed to load PAWLs data: {e}")
            return [ContentModality.TEXT.value]

    # Track which modalities are present
    has_text = False
    has_image = False

    for token_ref in tokens_jsons:
        if not isinstance(token_ref, dict):
            continue

        page_idx = token_ref.get("pageIndex")
        token_idx = token_ref.get("tokenIndex")

        if page_idx is None or token_idx is None:
            continue

        # Bounds check
        if page_idx < 0 or page_idx >= len(pawls_data):
            continue

        page = pawls_data[page_idx]
        if not isinstance(page, dict):
            continue

        tokens = page.get("tokens", [])
        if token_idx < 0 or token_idx >= len(tokens):
            continue

        token = tokens[token_idx]
        if not isinstance(token, dict):
            continue

        # Check if this is an image token
        if token.get("is_image"):
            has_image = True
        else:
            has_text = True

        # Early exit if we've found both
        if has_text and has_image:
            break

    # Build modality list
    modalities = []
    if has_text:
        modalities.append(ContentModality.TEXT.value)
    if has_image:
        modalities.append(ContentModality.IMAGE.value)

    # Default to TEXT if no modalities detected (backward compatibility)
    if not modalities:
        modalities = [ContentModality.TEXT.value]

    return modalities


def update_annotation_modalities(
    annotation: Any,
    document: Optional["Document"] = None,
    pawls_data: Optional[list[dict[str, Any]]] = None,
    save: bool = True,
) -> list[str]:
    """
    Update an annotation's content_modalities field based on its tokens.

    Convenience function that computes modalities and updates the annotation.

    Args:
        annotation: Annotation model instance.
        document: Optional Document instance (uses annotation.document if not provided).
        pawls_data: Optional pre-loaded PAWLs data.
        save: Whether to save the annotation after updating (default True).

    Returns:
        The computed modality list.
    """
    # Get document from annotation if not provided
    if document is None:
        document = getattr(annotation, "document", None)

    # Get tokens from annotation's json field (handles both v1 and v2 formats)
    annotation_json = annotation.json or {}
    all_tokens: list[dict[str, int]] = []

    for page in iter_page_annotations(
        annotation_json, raw_text=getattr(annotation, "raw_text", "") or ""
    ):
        all_tokens.extend(
            {"pageIndex": page.page_index, "tokenIndex": idx}
            for idx in page.token_indices
        )

    # Compute modalities
    modalities = compute_content_modalities(
        all_tokens, document=document, pawls_data=pawls_data
    )

    # Update annotation
    annotation.content_modalities = modalities

    if save:
        annotation.save(update_fields=["content_modalities"])

    return modalities
