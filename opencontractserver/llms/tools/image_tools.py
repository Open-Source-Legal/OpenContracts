"""
Image retrieval tools for LLM agents.

Provides tools to access document images for multimodal analysis, with
permission-checked variants for secure access.
"""

import json
import logging
from functools import partial
from typing import Any, Optional, cast

from pydantic import BaseModel, Field

from opencontractserver.annotations.compact_json import iter_page_annotations
from opencontractserver.annotations.models import Annotation
from opencontractserver.documents.models import Document
from opencontractserver.types.dicts import PawlsTokenPythonType
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.pawls_io import (
    TokenView,
    iter_pages,
    load_canonical_v2,
    to_canonical_v2,
)
from opencontractserver.utils.pdf_token_extraction import (
    get_image_as_base64,
    get_image_data_url,
    load_pawls_data,
)
from opencontractserver.utils.permissioning import user_has_permission_for_obj

logger = logging.getLogger(__name__)

# Import async database wrapper
try:
    from channels.db import database_sync_to_async as _database_sync_to_async

    _db_sync_to_async = partial(_database_sync_to_async, thread_sensitive=False)
except ModuleNotFoundError:
    from asgiref.sync import sync_to_async as _sync_to_async

    _db_sync_to_async = partial(_sync_to_async, thread_sensitive=False)


class ImageReference(BaseModel):
    """Reference to an image token in a document."""

    page_index: int = Field(description="0-based page index")
    token_index: int = Field(
        description="0-based token index within the page's tokens array"
    )
    width: float = Field(description="Image width in PDF points")
    height: float = Field(description="Image height in PDF points")
    x: float = Field(description="X coordinate of image in PDF points")
    y: float = Field(description="Y coordinate of image in PDF points")
    format: str = Field(default="jpeg", description="Image format (jpeg, png)")
    image_type: Optional[str] = Field(
        None, description="Type: embedded, cropped, figure"
    )
    alt_text: Optional[str] = Field(None, description="Alt text if available")
    content_hash: Optional[str] = Field(None, description="Content hash for dedup")


class ImageData(BaseModel):
    """Image data ready for LLM consumption."""

    base64_data: str = Field(description="Base64-encoded image data")
    format: str = Field(description="Image format (jpeg, png)")
    data_url: str = Field(description="Data URL for embedding in prompts")
    page_index: int = Field(description="0-based page index")
    token_index: int = Field(
        description="0-based token index within the page's tokens array"
    )


def list_document_images(
    document_id: int,
    page_index: Optional[int] = None,
) -> list[ImageReference]:
    """
    List all image tokens in a document, optionally filtered by page.

    This function returns metadata about image tokens without loading the actual
    image data. Use get_document_image to retrieve specific images.

    Images are stored as tokens with is_image=True in the unified tokens[] array.

    Args:
        document_id: The document ID.
        page_index: Optional page filter (0-based). If None, returns all pages.

    Returns:
        List of ImageReference objects with position and metadata.
    """
    try:
        document = Document.objects.get(pk=document_id)
        pawls_data = load_pawls_data(document)

        if not pawls_data:
            return []

        images: list[ImageReference] = []
        for page in iter_pages(pawls_data):
            if page_index is not None and page.index != page_index:
                continue

            for token_idx, token in enumerate(page.tokens):
                # Only process image tokens
                if not token.is_image:
                    continue

                meta = token.image_meta or {}
                images.append(
                    ImageReference(
                        page_index=page.index,
                        token_index=token_idx,
                        width=token.width,
                        height=token.height,
                        x=token.x,
                        y=token.y,
                        # v2 image-meta short keys: f=format, it=image_type, ch=content_hash
                        format=meta.get("f", "jpeg"),
                        image_type=meta.get("it"),
                        alt_text=None,  # alt_text not currently persisted in v2 image meta
                        content_hash=meta.get("ch"),
                    )
                )

        return images
    except Document.DoesNotExist:
        logger.warning(f"Document {document_id} not found")
        return []
    except Exception as e:
        logger.error(f"Error listing images for document {document_id}: {e}")
        return []


def _v2_token_to_v1_image_dict(token: TokenView) -> dict[str, Any]:
    """Build a v1-key image-token dict for the legacy image helpers.

    ``get_image_as_base64`` / ``get_image_data_url`` were written against the
    v1 ``PawlsTokenPythonType`` shape (``base64_data``/``image_path``/``format``
    long keys). After Phase 2 we keep their contracts intact and feed them a
    small dict reconstructed from a v2 :class:`TokenView`.
    """
    out: dict[str, Any] = {
        "x": token.x,
        "y": token.y,
        "width": token.width,
        "height": token.height,
        "text": token.text,
    }
    if token.is_image:
        out["is_image"] = True
        out.update(token.image_meta_v1 or {})
    return out


def _get_v2_token(
    pawls_data: dict[str, Any],
    page_index: int,
    token_index: int,
) -> Optional[TokenView]:
    """Locate the :class:`TokenView` at ``(page_index, token_index)`` or ``None``.

    Args:
        pawls_data: Canonical v2 PAWLs dict.
        page_index: 0-based page index.
        token_index: 0-based token index within the page.
    """
    pages = pawls_data.get("p")
    if not isinstance(pages, list):
        return None
    if page_index < 0 or page_index >= len(pages):
        return None
    page_dict = pages[page_index]
    if not isinstance(page_dict, dict):
        return None
    rows = page_dict.get("t") or []
    if token_index < 0 or token_index >= len(rows):
        return None
    row = rows[token_index]
    if not isinstance(row, list):
        return None
    return TokenView(row)


def get_document_image(
    document_id: int,
    page_index: int,
    token_index: int,
    pawls_data: Optional[dict[str, Any]] = None,
) -> Optional[ImageData]:
    """
    Get image data for a specific image token in a document.

    Retrieves the actual image data (base64 encoded) for the specified image token.
    The returned ImageData includes a data_url suitable for LLM vision input.

    Images are stored as tokens with is_image=True in the unified tokens[] array.

    Args:
        document_id: The document ID.
        page_index: 0-based page index.
        token_index: 0-based token index within the page's tokens array.
        pawls_data: Optional pre-loaded PAWLs data to avoid re-loading.

    Returns:
        ImageData with base64 content and data URL, or None if not found or not an image token.
    """
    try:
        # Load PAWLs data if not provided. Accept v1 list inputs for backward
        # compatibility — normalize through to_canonical_v2 so all later code
        # works on canonical v2.
        if pawls_data is None:
            document = Document.objects.get(pk=document_id)
            pawls_data = load_pawls_data(document)
        elif isinstance(pawls_data, list):
            pawls_data = to_canonical_v2(pawls_data)

        if not pawls_data:
            return None

        token = _get_v2_token(pawls_data, page_index, token_index)
        if token is None:
            logger.warning(
                f"Token ({page_index}, {token_index}) out of bounds for "
                f"document {document_id}"
            )
            return None

        # Verify this is an image token
        if not token.is_image:
            logger.warning(
                f"Token at index {token_index} on page {page_index} is not an image token"
            )
            return None

        v1_token = cast(PawlsTokenPythonType, _v2_token_to_v1_image_dict(token))
        base64_data = get_image_as_base64(v1_token)
        if not base64_data:
            logger.warning(
                f"Could not get base64 data for image token {token_index} on page {page_index}"
            )
            return None

        data_url = get_image_data_url(v1_token)
        img_format = v1_token.get("format", "jpeg")

        return ImageData(
            base64_data=base64_data,
            format=img_format,
            data_url=data_url or f"data:image/{img_format};base64,{base64_data}",
            page_index=page_index,
            token_index=token_index,
        )
    except Document.DoesNotExist:
        logger.warning(f"Document {document_id} not found")
        return None
    except Exception as e:
        logger.error(f"Error getting image from document {document_id}: {e}")
        return None


def _extract_image_from_pawls(
    pawls_data: dict[str, Any],
    page_index: int,
    token_index: int,
) -> Optional[ImageData]:
    """
    Extract image data directly from PAWLs data structure.

    Helper function for structural annotations that don't have a document_id.

    Args:
        pawls_data: Canonical v2 PAWLs dict (or v1 list, normalized internally).
        page_index: 0-based page index.
        token_index: 0-based token index within the page's tokens array.

    Returns:
        ImageData if the token is an image token, None otherwise.
    """
    try:
        if isinstance(pawls_data, list):
            pawls_data = to_canonical_v2(pawls_data)

        token = _get_v2_token(pawls_data, page_index, token_index)
        if token is None:
            logger.warning(
                f"Token ({page_index}, {token_index}) out of bounds in PAWLs data"
            )
            return None

        # Verify this is an image token
        if not token.is_image:
            return None

        v1_token = cast(PawlsTokenPythonType, _v2_token_to_v1_image_dict(token))
        base64_data = get_image_as_base64(v1_token)
        if not base64_data:
            return None

        data_url = get_image_data_url(v1_token)
        img_format = v1_token.get("format", "jpeg")

        return ImageData(
            base64_data=base64_data,
            format=img_format,
            data_url=data_url or f"data:image/{img_format};base64,{base64_data}",
            page_index=page_index,
            token_index=token_index,
        )
    except Exception as e:
        logger.error(f"Error extracting image from PAWLs: {e}")
        return None


def _load_images_from_annotation_file(annotation: Annotation) -> list[ImageData]:
    """
    Load pre-extracted image data from annotation.image_content_file.

    Args:
        annotation: Annotation with image_content_file populated.

    Returns:
        List of ImageData objects, or empty list on failure.
    """
    try:
        if not annotation.image_content_file:
            return []

        with annotation.image_content_file.open("r") as f:
            data = json.load(f)
            images = data.get("images", [])
            return [
                ImageData(
                    base64_data=img.get("base64", ""),
                    format=img.get("format", "jpeg"),
                    data_url=f"data:image/{img.get('format', 'jpeg')};base64,{img.get('base64', '')}",
                    page_index=img.get("page_index", 0),
                    token_index=img.get("token_index", 0),
                )
                for img in images
                if img.get("base64")
            ]

    except Exception as e:
        logger.error(f"Error loading images from annotation {annotation.pk} file: {e}")
        return []


def get_annotation_images(annotation_id: int) -> list[ImageData]:
    """
    Get all image tokens referenced by an annotation.

    Fast path: If annotation has pre-extracted image_content_file, load from there.
    Fallback: Load from PAWLs data (document or structural_set).

    Annotations reference tokens via tokensJsons in their annotation_json field.
    This function filters for image tokens (is_image=True) and retrieves their
    actual image data.

    Args:
        annotation_id: The annotation ID.

    Returns:
        List of ImageData for image tokens referenced by this annotation.
    """
    try:
        annotation = Annotation.objects.select_related(
            "document", "structural_set"
        ).get(pk=annotation_id)

        # Fast path: check for pre-extracted image content file
        if annotation.image_content_file:
            images = _load_images_from_annotation_file(annotation)
            if images:
                logger.debug(
                    f"Annotation {annotation_id} loaded {len(images)} images from "
                    f"image_content_file (fast path)"
                )
                return images
            # Fall through to PAWLs if file load failed

        document = annotation.document

        # Load PAWLs data from document or structural set (slow path)
        if document:
            pawls_data = load_pawls_data(document)
        elif annotation.structural_set and annotation.structural_set.pawls_parse_file:
            # Structural annotation without document - load from structural_set
            try:
                pawls_data = load_canonical_v2(
                    annotation.structural_set.pawls_parse_file
                )
            except Exception as e:
                logger.error(f"Error loading PAWLs from structural set: {e}")
                pawls_data = None
        else:
            logger.warning(
                f"Annotation {annotation_id} has no document or structural_set with PAWLs"
            )
            return []

        if not pawls_data:
            return []

        images = []
        for page in iter_page_annotations(
            annotation.json or {}, raw_text=annotation.raw_text or ""
        ):
            for token_idx in page.token_indices:
                # For structural annotations, we don't have a document_id
                # but get_document_image can work with pawls_data directly
                if document:
                    img_data = get_document_image(
                        document.pk, page.page_index, token_idx, pawls_data=pawls_data
                    )
                else:
                    # Extract image data directly from pawls_data for structural annotations
                    img_data = _extract_image_from_pawls(
                        pawls_data, page.page_index, token_idx
                    )
                if img_data:
                    images.append(img_data)

        return images
    except Annotation.DoesNotExist:
        logger.warning(f"Annotation {annotation_id} not found")
        return []
    except Exception as e:
        logger.error(f"Error getting annotation images: {e}")
        return []


# =============================================================================
# Permission-Checked Versions
# =============================================================================


def list_document_images_with_permission(
    user,
    document_id: int,
    page_index: Optional[int] = None,
) -> list[ImageReference]:
    """
    Permission-checked version of list_document_images.

    Verifies the user has READ permission on the document before listing images.

    Args:
        user: The user requesting access.
        document_id: The document ID.
        page_index: Optional page filter (0-based).

    Returns:
        List of ImageReference objects if permitted, empty list otherwise.
    """
    try:
        document = Document.objects.get(pk=document_id)
        if not user_has_permission_for_obj(
            user, document, PermissionTypes.READ, include_group_permissions=True
        ):
            logger.warning(f"User {user} lacks permission for document {document_id}")
            return []
        return list_document_images(document_id, page_index)
    except Document.DoesNotExist:
        return []  # Same response for missing or unauthorized (IDOR protection)


def get_document_image_with_permission(
    user,
    document_id: int,
    page_index: int,
    token_index: int,
) -> Optional[ImageData]:
    """
    Permission-checked version of get_document_image.

    Verifies the user has READ permission on the document before retrieving
    image data.

    Args:
        user: The user requesting access.
        document_id: The document ID.
        page_index: 0-based page index.
        token_index: 0-based token index within the page's tokens array.

    Returns:
        ImageData if permitted and found, None otherwise.
    """
    try:
        document = Document.objects.get(pk=document_id)
        if not user_has_permission_for_obj(
            user, document, PermissionTypes.READ, include_group_permissions=True
        ):
            logger.warning(f"User {user} lacks permission for document {document_id}")
            return None
        return get_document_image(document_id, page_index, token_index)
    except Document.DoesNotExist:
        return None  # Same response for missing or unauthorized (IDOR protection)


def get_annotation_images_with_permission(
    user,
    annotation_id: int,
) -> list[ImageData]:
    """
    Permission-checked version of get_annotation_images.

    Follows the consolidated permissioning guide:
    1. Effective Permission = MIN(document_permission, corpus_permission)
    2. Privacy model: created_by_analysis/created_by_extract require source permission
    3. Structural annotations bypass privacy (always visible if doc/corpus readable)
    4. IDOR protection: same response for missing or unauthorized

    Args:
        user: The user requesting access.
        annotation_id: The annotation ID.

    Returns:
        List of ImageData if permitted, empty list otherwise.
    """
    try:
        annotation = Annotation.objects.select_related(
            "document",
            "corpus",
            "structural_set",
            "created_by_analysis",
            "created_by_extract",
        ).get(pk=annotation_id)

        # Superusers bypass all checks
        if user.is_superuser:
            return get_annotation_images(annotation_id)

        # === PRIVACY MODEL CHECK ===
        # Non-structural annotations with created_by_analysis or created_by_extract
        # are private to that source object
        if not annotation.structural:
            if annotation.created_by_analysis_id:
                # Require READ permission on the analysis
                if not user_has_permission_for_obj(
                    user,
                    annotation.created_by_analysis,
                    PermissionTypes.READ,
                    include_group_permissions=True,
                ):
                    logger.debug(
                        f"User {user} lacks analysis permission for private annotation {annotation_id}"
                    )
                    return []  # IDOR protection

            if annotation.created_by_extract_id:
                # Require READ permission on the extract
                if not user_has_permission_for_obj(
                    user,
                    annotation.created_by_extract,
                    PermissionTypes.READ,
                    include_group_permissions=True,
                ):
                    logger.debug(
                        f"User {user} lacks extract permission for private annotation {annotation_id}"
                    )
                    return []  # IDOR protection

        # === DOCUMENT + CORPUS PERMISSION CHECK ===
        # Formula: Effective Permission = MIN(document_permission, corpus_permission)

        # Handle structural annotations without document reference
        if not annotation.document and not annotation.corpus:
            if annotation.structural_set:
                # Find any document that uses this structural set and user has access to
                accessible_doc = (
                    Document.objects.filter(
                        structural_annotation_set=annotation.structural_set
                    )
                    .visible_to_user(user)  # type: ignore[attr-defined]
                    .first()
                )
                if not accessible_doc:
                    logger.debug(
                        f"User {user} lacks permission for structural annotation {annotation_id}"
                    )
                    return []  # IDOR protection
                # User has access to at least one document using this structural set
                return get_annotation_images(annotation_id)
            else:
                logger.warning(
                    f"Annotation {annotation_id} has no document, corpus, or structural_set"
                )
                return []  # IDOR protection

        # Check document permission (if document exists)
        if annotation.document:
            if not user_has_permission_for_obj(
                user,
                annotation.document,
                PermissionTypes.READ,
                include_group_permissions=True,
            ):
                logger.debug(
                    f"User {user} lacks document permission for annotation {annotation_id}"
                )
                return []  # IDOR protection

        # Check corpus permission (if corpus exists) - MIN rule requires BOTH
        if annotation.corpus:
            if not user_has_permission_for_obj(
                user,
                annotation.corpus,
                PermissionTypes.READ,
                include_group_permissions=True,
            ):
                logger.debug(
                    f"User {user} lacks corpus permission for annotation {annotation_id}"
                )
                return []  # IDOR protection

        return get_annotation_images(annotation_id)
    except Annotation.DoesNotExist:
        return []  # Same response for missing or unauthorized (IDOR protection)


# =============================================================================
# Async Versions
# =============================================================================


async def alist_document_images(
    document_id: int,
    page_index: Optional[int] = None,
) -> list[ImageReference]:
    """Async version of list_document_images."""
    return await _db_sync_to_async(list_document_images)(
        document_id=document_id,
        page_index=page_index,
    )


async def aget_document_image(
    document_id: int,
    page_index: int,
    token_index: int,
) -> Optional[ImageData]:
    """Async version of get_document_image."""
    return await _db_sync_to_async(get_document_image)(
        document_id=document_id,
        page_index=page_index,
        token_index=token_index,
    )


async def aget_annotation_images(annotation_id: int) -> list[ImageData]:
    """Async version of get_annotation_images."""
    return await _db_sync_to_async(get_annotation_images)(
        annotation_id=annotation_id,
    )


async def alist_document_images_with_permission(
    user,
    document_id: int,
    page_index: Optional[int] = None,
) -> list[ImageReference]:
    """Async version of list_document_images_with_permission."""
    return await _db_sync_to_async(list_document_images_with_permission)(
        user=user,
        document_id=document_id,
        page_index=page_index,
    )


async def aget_document_image_with_permission(
    user,
    document_id: int,
    page_index: int,
    token_index: int,
) -> Optional[ImageData]:
    """Async version of get_document_image_with_permission."""
    return await _db_sync_to_async(get_document_image_with_permission)(
        user=user,
        document_id=document_id,
        page_index=page_index,
        token_index=token_index,
    )


async def aget_annotation_images_with_permission(
    user,
    annotation_id: int,
) -> list[ImageData]:
    """Async version of get_annotation_images_with_permission."""
    return await _db_sync_to_async(get_annotation_images_with_permission)(
        user=user,
        annotation_id=annotation_id,
    )
