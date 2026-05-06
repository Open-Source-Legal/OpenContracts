"""
PDF Token Extraction Utility.

This module provides functions to extract word-level tokens and images from PDFs
and calculate which tokens fall within annotation bounding boxes.

Based on the Docsling microservice implementation:
https://github.com/JSv4/Docsling/blob/main/app/core/parser.py

Image extraction capabilities added for LLM image annotation support.
"""

import base64
import gc
import hashlib
import io
import json
import logging
from typing import TYPE_CHECKING, Any, Literal, Optional

import numpy as np
from shapely.geometry import box
from shapely.strtree import STRtree

if TYPE_CHECKING:
    from opencontractserver.documents.models import Document
    from PIL import Image as PILImage

from django.conf import settings

from opencontractserver.types.dicts import (
    BoundingBoxPythonType,
    PawlsPagePythonType,
    PawlsTokenPythonType,
    TokenIdPythonType,
)
from opencontractserver.utils.compact_pawls import expand_pawls_pages

logger = logging.getLogger(__name__)

# Image size limits - use settings with fallback defaults
# These can be overridden via environment variables:
#   MAX_IMAGE_SIZE_BYTES (default: 10MB per image)
#   MAX_TOTAL_IMAGES_SIZE_BYTES (default: 100MB per document)
MAX_IMAGE_SIZE_BYTES = getattr(settings, "MAX_IMAGE_SIZE_BYTES", 10 * 1024 * 1024)
MAX_TOTAL_IMAGES_SIZE_BYTES = getattr(
    settings, "MAX_TOTAL_IMAGES_SIZE_BYTES", 100 * 1024 * 1024
)

# Default DPI for rasterising PDF pages when an embedded image stream cannot be
# decoded directly. Higher values produce sharper crops but proportionally
# larger in-memory page buffers (peak page-render RSS scales as ~DPI^2).
DEFAULT_IMAGE_EXTRACTION_DPI = getattr(settings, "IMAGE_EXTRACTION_DPI", 150)

# After processing this many pages during image extraction, force a full
# garbage collection. This keeps peak RSS bounded by a small constant
# (one rendered page + one decoded image) regardless of document length,
# even when the underlying CPython refcounting doesn't reclaim Poppler /
# PIL buffers promptly. See ``extract_images_from_pdf``.
IMAGE_EXTRACTION_GC_INTERVAL_PAGES = getattr(
    settings, "IMAGE_EXTRACTION_GC_INTERVAL_PAGES", 1
)


def _close_quietly(obj: Any) -> None:
    """Best-effort ``close()`` on PIL Images / BytesIO buffers. Errors swallowed."""
    if obj is None:
        return
    closer = getattr(obj, "close", None)
    if closer is None:
        return
    try:
        closer()
    except Exception:
        pass


def load_pawls_data(document: "Document") -> Optional[list[dict[str, Any]]]:
    """
    Load PAWLs data from a document.

    This is a shared utility for loading PAWLs JSON from a document's
    pawls_parse_file field.

    Args:
        document: The Document instance.

    Returns:
        Parsed PAWLs data as list of page dicts, or None if unavailable.
    """
    pawls_file = document.pawls_parse_file
    if not pawls_file:
        return None

    try:
        pawls_file.open("r")
        try:
            raw_data = json.load(pawls_file)
        finally:
            pawls_file.close()
        return expand_pawls_pages(raw_data)
    except Exception as e:
        logger.error(f"Failed to load PAWLs data for document {document.pk}: {e}")
        return None


def has_extractable_text(pdf_bytes: bytes, min_chars: int = 10) -> bool:
    """
    Check if a PDF has extractable text content.

    This is a detection function only - no OCR is performed. PDFs without
    embedded text (scanned documents) will return False.

    Args:
        pdf_bytes: The raw bytes of the PDF file.
        min_chars: Minimum number of non-whitespace characters to consider
                   the PDF as having extractable text. Default: 10.

    Returns:
        True if the PDF has extractable text, False otherwise.
    """
    try:
        import pdfplumber
    except ImportError:
        logger.warning("pdfplumber not installed. Cannot check for extractable text.")
        return False

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            if not pdf.pages:
                logger.warning("PDF has no pages.")
                return False

            # Check the first few pages for text content
            pages_to_check = min(len(pdf.pages), 3)
            for i in range(pages_to_check):
                try:
                    page_text = pdf.pages[i].extract_text(x_tolerance=2, y_tolerance=2)
                    if page_text and len(page_text.strip()) > min_chars:
                        logger.debug(f"Text found on page {i + 1} using pdfplumber.")
                        return True
                except Exception as page_error:
                    logger.warning(
                        f"Could not extract text from page {i + 1}: {page_error}"
                    )
                    continue

            logger.info(
                f"No significant text found in first {pages_to_check} pages. "
                "PDF may be scanned."
            )
            return False

    except Exception as e:
        logger.error(f"Error checking PDF for extractable text: {e}")
        return False


def extract_pawls_tokens_from_pdf(
    pdf_bytes: bytes,
    page_dimensions: Optional[dict[int, tuple[float, float]]] = None,
) -> tuple[
    list[PawlsPagePythonType],
    dict[int, STRtree],
    dict[int, list[PawlsTokenPythonType]],
    dict[int, np.ndarray],
    dict[int, tuple[float, float]],
    str,
]:
    """
    Extract word-level tokens from a PDF with bounding boxes.

    Uses pdfplumber for text extraction. Returns PAWLS-compatible token data
    and spatial indices for intersection queries.

    This function is based on Docsling's _generate_pawls_content() function,
    simplified to remove OCR support.

    Args:
        pdf_bytes: The raw bytes of the PDF file.
        page_dimensions: Optional dict mapping 0-based page index to (width, height)
                        tuples. If provided, coordinates are scaled to match.
                        If None, pdfplumber's native dimensions are used.

    Returns:
        A tuple containing:
        - pawls_pages: List of PawlsPagePythonType with tokens per page
        - spatial_indices: Dict mapping 0-based page index to STRtree spatial index
        - tokens_by_page: Dict mapping 0-based page index to list of tokens
        - token_indices_by_page: Dict mapping 0-based page index to numpy array
                                 of original token indices
        - page_dims: Dict mapping 0-based page index to (width, height) tuple
        - content: Full text content concatenated across pages

    Raises:
        ImportError: If pdfplumber is not installed.
    """
    try:
        import pdfplumber
    except ImportError:
        logger.error("pdfplumber not installed. Install with: pip install pdfplumber")
        raise

    pawls_pages: list[PawlsPagePythonType] = []
    spatial_indices_by_page: dict[int, STRtree] = {}
    tokens_by_page: dict[int, list[PawlsTokenPythonType]] = {}
    token_indices_by_page: dict[int, np.ndarray] = {}
    page_dims: dict[int, tuple[float, float]] = {}
    content_parts: list[str] = []

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            if not pdf.pages:
                logger.warning("PDF has no pages.")
                return (
                    pawls_pages,
                    spatial_indices_by_page,
                    tokens_by_page,
                    token_indices_by_page,
                    page_dims,
                    "",
                )

            for page_num_0based, pdf_page in enumerate(pdf.pages):
                logger.debug(f"Processing page {page_num_0based + 1} with pdfplumber")

                # Get page dimensions
                native_width = float(pdf_page.width)
                native_height = float(pdf_page.height)

                # Use provided dimensions if available, otherwise use native
                if page_dimensions and page_num_0based in page_dimensions:
                    width, height = page_dimensions[page_num_0based]
                    scale_x = width / native_width
                    scale_y = height / native_height
                else:
                    width, height = native_width, native_height
                    scale_x, scale_y = 1.0, 1.0

                page_dims[page_num_0based] = (width, height)

                current_page_tokens: list[PawlsTokenPythonType] = []
                current_page_geometries: list[box] = []
                current_page_token_indices: list[int] = []
                page_content_parts: list[str] = []

                # Extract words using pdfplumber
                # Match Docsling's extraction options for consistency
                words = pdf_page.extract_words(
                    x_tolerance=2,
                    y_tolerance=2,
                    keep_blank_chars=False,
                    use_text_flow=True,
                )

                if not words:
                    logger.debug(f"No words found on page {page_num_0based + 1}.")
                    content_parts.append("")
                    pawls_page: PawlsPagePythonType = {
                        "page": {
                            "width": width,
                            "height": height,
                            "index": page_num_0based,
                        },
                        "tokens": [],
                    }
                    pawls_pages.append(pawls_page)
                    tokens_by_page[page_num_0based] = []
                    token_indices_by_page[page_num_0based] = np.array([], dtype=np.intp)
                    continue

                for token_index, word in enumerate(words):
                    # pdfplumber coordinates: x0, top, x1, bottom (origin top-left)
                    x0 = float(word["x0"]) * scale_x
                    top = float(word["top"]) * scale_y
                    x1 = float(word["x1"]) * scale_x
                    bottom = float(word["bottom"]) * scale_y
                    text = word["text"]

                    # PAWLS uses top-left corner (x, y) and width, height
                    token_x = x0
                    token_y = top
                    token_width = x1 - x0
                    token_height = bottom - top

                    # Skip potentially invalid boxes
                    if token_width <= 0 or token_height <= 0 or not text.strip():
                        continue

                    token: PawlsTokenPythonType = {
                        "x": token_x,
                        "y": token_y,
                        "width": token_width,
                        "height": token_height,
                        "text": text,
                    }
                    current_page_tokens.append(token)
                    page_content_parts.append(text)

                    # Create geometry for STRtree (minx, miny, maxx, maxy)
                    token_bbox = box(
                        token_x, token_y, token_x + token_width, token_y + token_height
                    )
                    current_page_geometries.append(token_bbox)
                    current_page_token_indices.append(len(current_page_tokens) - 1)

                content_parts.append(" ".join(page_content_parts))

                # Build spatial index for the page if tokens were found
                if current_page_geometries:
                    geometries_array = np.array(current_page_geometries)
                    token_indices_array = np.array(
                        current_page_token_indices, dtype=np.intp
                    )
                    spatial_index = STRtree(geometries_array)
                    spatial_indices_by_page[page_num_0based] = spatial_index
                    tokens_by_page[page_num_0based] = current_page_tokens
                    token_indices_by_page[page_num_0based] = token_indices_array
                    logger.debug(
                        f"Built STRtree for page {page_num_0based + 1} with "
                        f"{len(current_page_geometries)} tokens."
                    )
                else:
                    tokens_by_page[page_num_0based] = []
                    token_indices_by_page[page_num_0based] = np.array([], dtype=np.intp)

                # Create PAWLS page structure
                pawls_page = {
                    "page": {
                        "width": width,
                        "height": height,
                        "index": page_num_0based,
                    },
                    "tokens": current_page_tokens,
                }
                pawls_pages.append(pawls_page)

        full_content = "\n".join(content_parts)
        logger.info(f"Extracted tokens from {len(pawls_pages)} pages.")

        return (
            pawls_pages,
            spatial_indices_by_page,
            tokens_by_page,
            token_indices_by_page,
            page_dims,
            full_content,
        )

    except Exception as e:
        logger.error(f"Error extracting tokens from PDF: {e}")
        raise


def find_tokens_in_bbox(
    bbox: BoundingBoxPythonType,
    page_idx: int,
    spatial_index: Optional[STRtree],
    token_indices: Optional[np.ndarray],
    tokens: Optional[list[PawlsTokenPythonType]] = None,
) -> list[TokenIdPythonType]:
    """
    Find all tokens that intersect with a bounding box.

    Uses spatial indexing (STRtree) to efficiently find tokens that overlap
    with the given bounding box.

    This function is based on the spatial query portion of Docsling's
    convert_docling_item_to_annotation() function.

    Args:
        bbox: The bounding box to find intersecting tokens for.
              Uses {left, top, right, bottom} format.
        page_idx: 0-based page index.
        spatial_index: STRtree spatial index for the page (from extract_pawls_tokens_from_pdf).
        token_indices: Numpy array of token indices for the page.
        tokens: Optional list of tokens for validation (unused, kept for API compatibility).

    Returns:
        List of TokenIdPythonType references ({pageIndex, tokenIndex}) for tokens
        that intersect with the bounding box. Returns empty list if no spatial
        index is available or no tokens intersect.
    """
    if spatial_index is None or token_indices is None:
        logger.debug(f"No spatial index for page {page_idx}, returning empty tokens.")
        return []

    if len(token_indices) == 0:
        return []

    try:
        # Create bbox geometry for query
        left = float(bbox["left"])
        top = float(bbox["top"])
        right = float(bbox["right"])
        bottom = float(bbox["bottom"])

        # Ensure valid bounds
        if left > right:
            left, right = right, left
        if top > bottom:
            top, bottom = bottom, top

        query_bbox = box(left, top, right, bottom)

        # Perform spatial query
        candidate_indices = spatial_index.query(query_bbox)

        if not isinstance(candidate_indices, np.ndarray) or candidate_indices.size == 0:
            return []

        # Filter to only valid indices
        valid_indices = candidate_indices[
            candidate_indices < len(spatial_index.geometries)
        ]

        if len(valid_indices) == 0:
            return []

        # Check for actual intersection (STRtree.query returns bounding box overlaps)
        candidate_geometries = spatial_index.geometries.take(valid_indices)
        intersects_mask = np.array(
            [
                geom.intersects(query_bbox) if geom.is_valid else False
                for geom in candidate_geometries
            ]
        )
        actual_indices = valid_indices[intersects_mask]

        if actual_indices.size == 0:
            return []

        # Map back to token indices and ensure they're valid
        valid_actual_indices = actual_indices[actual_indices < len(token_indices)]
        if valid_actual_indices.size == 0:
            return []

        result_token_indices = token_indices[valid_actual_indices]

        # Create token reference list
        token_refs: list[TokenIdPythonType] = [
            {"pageIndex": page_idx, "tokenIndex": int(idx)}
            for idx in sorted(result_token_indices)
        ]

        return token_refs

    except Exception as e:
        logger.error(f"Error during spatial query for page {page_idx}: {e}")
        return []


# =============================================================================
# Image Storage Functions
# =============================================================================


def _save_image_to_storage(
    image_bytes: bytes,
    storage_path: str,
    page_idx: int,
    img_idx: int,
    image_format: str,
) -> Optional[str]:
    """
    Save image bytes to Django storage (S3, GCS, local filesystem).

    Uses Django's default_storage backend, which may be local filesystem,
    S3, GCS, or any other configured storage backend.

    Args:
        image_bytes: The raw image bytes to save.
        storage_path: Base path for storing images (e.g., "documents/123/images").
        page_idx: 0-based page index.
        img_idx: 0-based image index within the page.
        image_format: Image format ("jpeg" or "png").

    Returns:
        The full storage path where the image was saved (e.g.,
        "documents/123/images/page_0_img_1.jpg"), or None on failure.
        This path can be used with `_load_image_from_storage()` to retrieve
        the image later.
    """
    try:
        from django.core.files.base import ContentFile
        from django.core.files.storage import default_storage

        # Build the filename
        extension = "jpg" if image_format == "jpeg" else image_format
        filename = f"page_{page_idx}_img_{img_idx}.{extension}"
        full_path = f"{storage_path}/{filename}"

        # Save to storage
        saved_path = default_storage.save(full_path, ContentFile(image_bytes))
        logger.debug(f"Saved image to storage: {saved_path}")
        return saved_path

    except Exception as e:
        logger.warning(f"Failed to save image to storage: {e}")
        return None


def _load_image_from_storage(image_path: str) -> Optional[bytes]:
    """
    Load image bytes from Django storage.

    Args:
        image_path: The storage path to the image.

    Returns:
        The raw image bytes, or None if loading fails.
    """
    try:
        from django.core.files.storage import default_storage

        with default_storage.open(image_path, "rb") as f:
            return f.read()

    except Exception as e:
        logger.warning(f"Failed to load image from storage '{image_path}': {e}")
        return None


# =============================================================================
# Image Extraction Functions
# =============================================================================


def extract_images_from_pdf(
    pdf_bytes: bytes,
    min_width: int = 50,
    min_height: int = 50,
    max_images_per_page: int = 20,
    image_format: Literal["jpeg", "png"] = "jpeg",
    jpeg_quality: int = 85,
    storage_path: Optional[str] = None,
    dpi: int = DEFAULT_IMAGE_EXTRACTION_DPI,
) -> dict[int, list[PawlsTokenPythonType]]:
    """
    Extract embedded images from a PDF as unified image tokens.

    Uses pdfplumber to detect embedded images and extracts them. If a storage_path
    is provided, images are saved to storage and referenced by path (recommended
    to avoid PAWLs file bloat). Otherwise, images are embedded as base64.

    Image tokens are returned as unified PawlsTokenPythonType with is_image=True,
    allowing them to be stored alongside text tokens in the PAWLs format and
    referenced using the same TokenIdPythonType.

    Memory bound (issue #1498):
        Pages are processed one at a time. When a page contains embedded images
        whose streams cannot be decoded directly, the page is rasterised at most
        ONCE per call (regardless of how many images live on it) and the
        rendered buffer is closed before moving to the next page. PIL Image and
        BytesIO buffers are explicitly closed; pdfplumber's per-page parse cache
        is flushed; and ``gc.collect()`` runs every
        ``IMAGE_EXTRACTION_GC_INTERVAL_PAGES`` pages.

        Peak working set per call is therefore ::

            len(pdf_bytes) + 1 rendered page + 1 decoded image bytes

        and is independent of total page count, so a 30-page document and a
        300-page document of similar shape have the same RSS profile.

    Args:
        pdf_bytes: The raw bytes of the PDF file.
        min_width: Minimum image width in pixels to include (default: 50).
        min_height: Minimum image height in pixels to include (default: 50).
        max_images_per_page: Maximum number of images to extract per page (default: 20).
        image_format: Output format for extracted images ("jpeg" or "png").
        jpeg_quality: JPEG quality if using jpeg format (1-100, default: 85).
        storage_path: Base path for storing images (e.g., "user_123/doc_456/images").
                     If provided, images are saved to storage and referenced by path.
                     If None, images are embedded as base64 (not recommended for large docs).
        dpi: Resolution for rasterising pages whose embedded image streams
             cannot be decoded directly. Page-render RSS scales as ~DPI^2.

    Returns:
        Dict mapping 0-based page index to list of PawlsTokenPythonType (image tokens).
        Each image token has is_image=True and text="" to identify it as an image.
    """
    try:
        import pdfplumber
        from PIL import Image  # noqa: F401 - imported to verify PIL is installed
    except ImportError as e:
        logger.error(f"Required library not installed: {e}")
        return {}

    images_by_page: dict[int, list[PawlsTokenPythonType]] = {}

    # Track total size across all images for document-level limit
    total_images_size = 0
    size_limit_reached = False
    num_pages_processed = 0

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            num_pages = len(pdf.pages)
            for page_idx in range(num_pages):
                # Check if we've hit the document-level size limit
                if size_limit_reached:
                    images_by_page[page_idx] = []
                    continue

                page = pdf.pages[page_idx]
                page_images, page_size_added, hit_size_limit = _extract_images_for_page(
                    page=page,
                    page_idx=page_idx,
                    pdf_bytes=pdf_bytes,
                    min_width=min_width,
                    min_height=min_height,
                    max_images_per_page=max_images_per_page,
                    image_format=image_format,
                    jpeg_quality=jpeg_quality,
                    storage_path=storage_path,
                    dpi=dpi,
                    running_total_size=total_images_size,
                )

                images_by_page[page_idx] = page_images
                total_images_size += page_size_added
                if hit_size_limit:
                    size_limit_reached = True

                # Release pdfplumber's per-page parse cache (text/image lookup
                # tables) so cumulative RSS doesn't grow as we iterate.
                if hasattr(page, "flush_cache"):
                    try:
                        page.flush_cache()
                    except Exception:
                        pass
                # Drop the local reference so refcounting can reclaim it
                # before the next iteration.
                del page

                num_pages_processed += 1
                # Force a collection so Poppler subprocess buffers and PIL
                # image buffers get reclaimed before the next page render,
                # keeping peak RSS bounded.
                if (
                    IMAGE_EXTRACTION_GC_INTERVAL_PAGES > 0
                    and num_pages_processed % IMAGE_EXTRACTION_GC_INTERVAL_PAGES == 0
                ):
                    gc.collect()

        logger.info(
            f"Extracted images from {num_pages_processed} pages: "
            f"{sum(len(imgs) for imgs in images_by_page.values())} total images"
        )

    except Exception as e:
        logger.error(f"Error extracting images from PDF: {e}")

    return images_by_page


def _extract_images_for_page(
    page: Any,
    page_idx: int,
    pdf_bytes: bytes,
    min_width: int,
    min_height: int,
    max_images_per_page: int,
    image_format: Literal["jpeg", "png"],
    jpeg_quality: int,
    storage_path: Optional[str],
    dpi: int,
    running_total_size: int,
) -> tuple[list[PawlsTokenPythonType], int, bool]:
    """
    Extract images from a single PDF page with bounded peak memory.

    Memory contract: at most ONE rendered page image and ONE decoded image
    buffer are alive at any moment within this function. The page is
    rasterised lazily — only when at least one image on the page can't be
    decoded directly from its embedded stream — and is closed before this
    function returns.

    Args:
        page: pdfplumber Page object.
        page_idx: 0-based page index.
        pdf_bytes: Raw PDF bytes (used only if rasterisation is needed).
        min_width / min_height / max_images_per_page / image_format /
        jpeg_quality / storage_path / dpi: forwarded from
        ``extract_images_from_pdf``.
        running_total_size: total image bytes accumulated across previous
            pages, used to enforce ``MAX_TOTAL_IMAGES_SIZE_BYTES``.

    Returns:
        Tuple of (page_images, bytes_added, hit_size_limit).
    """
    from PIL import Image

    page_images: list[PawlsTokenPythonType] = []
    bytes_added = 0
    hit_size_limit = False
    rendered_page: Optional["PILImage.Image"] = None

    try:
        page_width = float(page.width)
        page_height = float(page.height)

        if not hasattr(page, "images") or not page.images:
            return page_images, bytes_added, hit_size_limit

        for img_idx, img_info in enumerate(page.images[:max_images_per_page]):
            pil_image: Optional["PILImage.Image"] = None
            img_bytes_io: Optional[io.BytesIO] = None
            try:
                # pdfplumber image info contains: x0, top, x1, bottom, etc.
                x0 = float(img_info.get("x0", 0))
                top = float(img_info.get("top", 0))
                x1 = float(img_info.get("x1", page_width))
                bottom = float(img_info.get("bottom", page_height))

                # Calculate dimensions
                width = x1 - x0
                height = bottom - top

                # Skip images that are too small
                if width < min_width or height < min_height:
                    logger.debug(
                        f"Skipping small image on page {page_idx}: " f"{width}x{height}"
                    )
                    continue

                # Method 1: Try to get image stream directly
                if "stream" in img_info:
                    stream = img_info["stream"]
                    if hasattr(stream, "get_data"):
                        try:
                            raw_data = stream.get_data()
                            pil_image = Image.open(io.BytesIO(raw_data))
                        except Exception:
                            pil_image = None

                # Method 2: Crop from a rendered page. Render the page lazily
                # and ONCE; reuse the rendered buffer for every remaining
                # image on this page so we don't pay an O(images) rendering
                # cost or memory spike.
                if pil_image is None:
                    if rendered_page is None:
                        rendered_page = _render_pdf_page(pdf_bytes, page_idx, dpi)
                    if rendered_page is not None:
                        pil_image = _crop_region_from_rendered_page(
                            rendered_page,
                            x0,
                            top,
                            x1,
                            bottom,
                            page_width,
                            page_height,
                        )

                if pil_image is None:
                    logger.debug(
                        f"Could not extract image {img_idx} on page {page_idx}"
                    )
                    continue

                # Convert to target format
                img_bytes_io = io.BytesIO()
                if image_format == "jpeg":
                    # Convert to RGB for JPEG (no alpha channel).
                    # Close the original before rebinding so the pre-conversion
                    # buffer is released and not leaked when pil_image is later
                    # closed in the finally block below.
                    if pil_image.mode in ("RGBA", "LA", "P"):
                        converted = pil_image.convert("RGB")
                        _close_quietly(pil_image)
                        pil_image = converted
                    pil_image.save(img_bytes_io, format="JPEG", quality=jpeg_quality)
                else:
                    pil_image.save(img_bytes_io, format="PNG")

                image_bytes = img_bytes_io.getvalue()
                image_size = len(image_bytes)

                # Check individual image size limit
                if image_size > MAX_IMAGE_SIZE_BYTES:
                    logger.warning(
                        f"Skipping oversized image on page {page_idx}: "
                        f"{image_size} bytes exceeds {MAX_IMAGE_SIZE_BYTES} limit"
                    )
                    continue

                # Check document-level total size limit
                if (
                    running_total_size + bytes_added + image_size
                    > MAX_TOTAL_IMAGES_SIZE_BYTES
                ):
                    logger.warning(
                        f"Document image size limit reached "
                        f"({MAX_TOTAL_IMAGES_SIZE_BYTES} bytes), "
                        f"stopping extraction at page {page_idx}"
                    )
                    hit_size_limit = True
                    break

                bytes_added += image_size

                # Calculate content hash for deduplication
                content_hash = hashlib.sha256(image_bytes).hexdigest()

                # Create unified image token with is_image=True and text=""
                image_token: PawlsTokenPythonType = {
                    "x": x0,
                    "y": top,
                    "width": width,
                    "height": height,
                    "text": "",  # Required field, empty for images
                    "is_image": True,  # Identifies this as an image token
                    "format": image_format,
                    "original_width": pil_image.width,
                    "original_height": pil_image.height,
                    "content_hash": content_hash,
                    "image_type": "embedded",
                }

                # Save to storage if path provided, otherwise embed base64
                if storage_path:
                    saved_path = _save_image_to_storage(
                        image_bytes,
                        storage_path,
                        page_idx,
                        img_idx,
                        image_format,
                    )
                    if saved_path:
                        image_token["image_path"] = saved_path
                    else:
                        # Fallback to base64 if storage fails
                        image_token["base64_data"] = base64.b64encode(
                            image_bytes
                        ).decode("utf-8")
                else:
                    # No storage path - embed as base64 (not recommended)
                    image_token["base64_data"] = base64.b64encode(image_bytes).decode(
                        "utf-8"
                    )

                page_images.append(image_token)
                logger.debug(
                    f"Extracted image {img_idx} on page {page_idx}: "
                    f"{pil_image.width}x{pil_image.height}"
                )

            except Exception as img_error:
                logger.warning(
                    f"Error extracting image {img_idx} on page {page_idx}: "
                    f"{img_error}"
                )
                continue
            finally:
                # Release per-image buffers eagerly. Without this, the largest
                # images (10MB+ encoded, larger decoded) live until the next
                # iteration's `pil_image = ...` rebind, doubling peak RSS.
                _close_quietly(pil_image)
                _close_quietly(img_bytes_io)
    finally:
        # Close the rendered page once we've processed every image on it.
        # The rendered buffer is the largest single allocation in this loop
        # (~6-10MB at 150 DPI for US letter, quadratic in DPI), so freeing
        # it before returning is what keeps cross-page peak RSS bounded.
        _close_quietly(rendered_page)

    return page_images, bytes_added, hit_size_limit


def _render_pdf_page(
    pdf_bytes: bytes,
    page_idx: int,
    dpi: int = DEFAULT_IMAGE_EXTRACTION_DPI,
) -> Optional["PILImage.Image"]:
    """
    Rasterise a single PDF page to a PIL Image at ``dpi``.

    Separated from cropping so that callers iterating over many image bounds on
    the same page render the page exactly once and reuse the buffer. Returning
    a PIL Image transfers ownership: the caller is responsible for ``close()``.
    """
    try:
        from pdf2image import convert_from_bytes
        from PIL import Image  # noqa: F401 - imported to verify PIL is installed
    except ImportError:
        logger.warning("pdf2image or PIL not installed for page rendering")
        return None

    try:
        images = convert_from_bytes(
            pdf_bytes,
            first_page=page_idx + 1,  # pdf2image uses 1-based indexing
            last_page=page_idx + 1,
            dpi=dpi,
        )
        return images[0] if images else None
    except Exception as e:
        logger.warning(f"Error rendering PDF page {page_idx}: {e}")
        return None


def _crop_region_from_rendered_page(
    rendered_page: "PILImage.Image",
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    page_width: float,
    page_height: float,
) -> Optional["PILImage.Image"]:
    """
    Crop a region from an already-rendered PDF page, scaling PDF points to
    pixel coordinates. Caller retains ownership of ``rendered_page``; the
    returned crop is a new image the caller must close.
    """
    try:
        img_width, img_height = rendered_page.size

        # Calculate scale factors
        scale_x = img_width / page_width
        scale_y = img_height / page_height

        # Convert PDF coordinates to pixel coordinates
        px_x0 = int(x0 * scale_x)
        px_y0 = int(y0 * scale_y)
        px_x1 = int(x1 * scale_x)
        px_y1 = int(y1 * scale_y)

        # Ensure valid crop bounds
        px_x0 = max(0, min(px_x0, img_width - 1))
        px_y0 = max(0, min(px_y0, img_height - 1))
        px_x1 = max(px_x0 + 1, min(px_x1, img_width))
        px_y1 = max(px_y0 + 1, min(px_y1, img_height))

        return rendered_page.crop((px_x0, px_y0, px_x1, px_y1))
    except Exception as e:
        logger.warning(f"Error cropping rendered PDF page: {e}")
        return None


def _crop_pdf_region(
    pdf_bytes: bytes,
    page_idx: int,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    page_width: float,
    page_height: float,
    dpi: int = DEFAULT_IMAGE_EXTRACTION_DPI,
) -> Optional["PILImage.Image"]:
    """
    Crop a specific region from a PDF page by rendering it first.

    This is a fallback method when embedded image streams cannot be extracted
    directly from the PDF. Each call rasterises the page; callers that need
    multiple crops from the same page should instead call ``_render_pdf_page``
    once and ``_crop_region_from_rendered_page`` per crop.

    Args:
        pdf_bytes: The raw bytes of the PDF file.
        page_idx: 0-based page index.
        x0, y0, x1, y1: Bounding box coordinates in PDF points.
        page_width, page_height: Full page dimensions in PDF points.
        dpi: Resolution for rendering (default: ``DEFAULT_IMAGE_EXTRACTION_DPI``).

    Returns:
        PIL Image of the cropped region, or None on failure.
    """
    rendered_page = _render_pdf_page(pdf_bytes, page_idx, dpi)
    if rendered_page is None:
        return None
    try:
        return _crop_region_from_rendered_page(
            rendered_page, x0, y0, x1, y1, page_width, page_height
        )
    finally:
        # The rendered page buffer is large (~6-10MB at 150 DPI for US letter,
        # quadratic in DPI). Release it as soon as the crop is taken so the
        # caller's working set doesn't accumulate one rendered page per crop.
        _close_quietly(rendered_page)


def crop_image_from_pdf(
    pdf_bytes: bytes,
    page_idx: int,
    bbox: BoundingBoxPythonType,
    page_width: float,
    page_height: float,
    image_format: Literal["jpeg", "png"] = "jpeg",
    jpeg_quality: int = 85,
    dpi: int = 150,
    storage_path: Optional[str] = None,
    img_idx: int = 0,
) -> Optional[PawlsTokenPythonType]:
    """
    Crop a specific bounding box region from a PDF page as a unified image token.

    This is useful for extracting figure/image regions identified by parsers
    like LlamaParse or Docling that provide bounding boxes for visual elements.

    The returned image token is a unified PawlsTokenPythonType with is_image=True,
    allowing it to be stored alongside text tokens and referenced using
    TokenIdPythonType.

    Args:
        pdf_bytes: The raw bytes of the PDF file.
        page_idx: 0-based page index.
        bbox: Bounding box in PDF coordinates {left, top, right, bottom}.
        page_width: Page width in PDF points.
        page_height: Page height in PDF points.
        image_format: Output format ("jpeg" or "png").
        jpeg_quality: JPEG quality (1-100).
        dpi: Resolution for rendering (default: 150).
        storage_path: Base path for storing images. If provided, cropped images
                     are saved to storage and referenced by path (recommended).
                     If None, images are embedded as base64.
        img_idx: Image index for filename generation when using storage_path.

    Returns:
        PawlsTokenPythonType with is_image=True and cropped image data,
        or None on failure.
    """
    # Note: PIL availability is checked in _crop_pdf_region
    try:
        left = float(bbox["left"])
        top = float(bbox["top"])
        right = float(bbox["right"])
        bottom = float(bbox["bottom"])

        # Ensure valid bounds
        if left > right:
            left, right = right, left
        if top > bottom:
            top, bottom = bottom, top

        width = right - left
        height = bottom - top

        # Crop the region
        pil_image = _crop_pdf_region(
            pdf_bytes, page_idx, left, top, right, bottom, page_width, page_height, dpi
        )

        if pil_image is None:
            return None

        # Convert to target format
        img_bytes_io = io.BytesIO()
        if image_format == "jpeg":
            # Close the original before rebinding so the pre-conversion
            # buffer is not leaked when the reference is rebound.
            if pil_image.mode in ("RGBA", "LA", "P"):
                converted = pil_image.convert("RGB")
                _close_quietly(pil_image)
                pil_image = converted
            pil_image.save(img_bytes_io, format="JPEG", quality=jpeg_quality)
        else:
            pil_image.save(img_bytes_io, format="PNG")
        _close_quietly(pil_image)

        image_bytes = img_bytes_io.getvalue()
        _close_quietly(img_bytes_io)

        # Check image size limit
        if len(image_bytes) > MAX_IMAGE_SIZE_BYTES:
            logger.warning(
                f"Cropped image on page {page_idx} exceeds size limit: "
                f"{len(image_bytes)} bytes > {MAX_IMAGE_SIZE_BYTES}"
            )
            return None

        content_hash = hashlib.sha256(image_bytes).hexdigest()

        # Create unified image token with is_image=True and text=""
        # This allows the cropped image to be stored alongside text tokens
        # and referenced using TokenIdPythonType
        image_token: PawlsTokenPythonType = {
            "x": left,
            "y": top,
            "width": width,
            "height": height,
            "text": "",  # Required field, empty for images
            "is_image": True,  # Identifies this as an image token
            "format": image_format,
            "original_width": pil_image.width,
            "original_height": pil_image.height,
            "content_hash": content_hash,
            "image_type": "cropped",
        }

        # Save to storage if path provided, otherwise embed base64
        if storage_path:
            # Use "cropped" prefix to distinguish from embedded images
            saved_path = _save_image_to_storage(
                image_bytes,
                storage_path,
                page_idx,
                img_idx,
                image_format,
            )
            if saved_path:
                image_token["image_path"] = saved_path
            else:
                # Fallback to base64 if storage fails
                image_token["base64_data"] = base64.b64encode(image_bytes).decode(
                    "utf-8"
                )
        else:
            # No storage path - embed as base64 (not recommended for large images)
            image_token["base64_data"] = base64.b64encode(image_bytes).decode("utf-8")

        return image_token

    except Exception as e:
        logger.error(f"Error cropping image from PDF: {e}")
        return None


def get_image_as_base64(
    image_token: PawlsTokenPythonType,
) -> Optional[str]:
    """
    Get the base64-encoded image data from a unified image token.

    This function retrieves image data for LLM consumption. It first checks for
    inline base64 data, then falls back to loading from storage if an image_path
    is provided.

    Image tokens are unified PawlsTokenPythonType with is_image=True. They may
    contain either base64_data (inline) or image_path (storage reference).

    Args:
        image_token: A unified PawlsTokenPythonType with is_image=True,
                    containing either base64_data or image_path.

    Returns:
        Base64-encoded image data string, or None if not available.
    """
    # First check for inline base64 data (small thumbnails, legacy)
    if "base64_data" in image_token and image_token["base64_data"]:
        return image_token["base64_data"]

    # Load from storage if image_path is provided (preferred method)
    if "image_path" in image_token and image_token["image_path"]:
        image_bytes = _load_image_from_storage(image_token["image_path"])
        if image_bytes:
            return base64.b64encode(image_bytes).decode("utf-8")
        else:
            logger.warning(
                f"Failed to load image from storage: {image_token['image_path']}"
            )
            return None

    return None


def get_image_data_url(
    image_token: PawlsTokenPythonType,
) -> Optional[str]:
    """
    Get the image as a data URL suitable for embedding in HTML or LLM prompts.

    Image tokens are unified PawlsTokenPythonType with is_image=True.

    Args:
        image_token: A unified PawlsTokenPythonType with is_image=True,
                    containing either base64_data or image_path.

    Returns:
        Data URL string (e.g., "data:image/jpeg;base64,..."), or None if not available.
    """
    base64_data = get_image_as_base64(image_token)
    if not base64_data:
        return None

    img_format = image_token.get("format", "jpeg")
    mime_type = f"image/{img_format}"

    return f"data:{mime_type};base64,{base64_data}"


def find_image_tokens_in_bounds(
    bounds: BoundingBoxPythonType,
    page_idx: int,
    image_tokens: list[PawlsTokenPythonType],
    token_offset: int = 0,
) -> list[TokenIdPythonType]:
    """
    Find image tokens that overlap with a bounding box.

    This is a shared utility for finding image tokens that intersect with an
    annotation's bounding box. Used by parsers to link figure/image annotations
    to their corresponding image tokens in the unified PAWLs format.

    Args:
        bounds: The annotation bounding box {left, top, right, bottom}.
        page_idx: 0-based page index.
        image_tokens: List of :class:`PawlsTokenPythonType` image tokens with
                     ``x``, ``y``, ``width``, ``height`` fields and
                     ``is_image=True``.
        token_offset: The starting token index for image tokens in the unified
                     tokens array. Images are typically appended after text tokens,
                     so this offset accounts for the text token count.

    Returns:
        List of TokenIdPythonType references for overlapping image tokens.
    """
    if not image_tokens:
        return []

    token_refs: list[TokenIdPythonType] = []
    ann_left = float(bounds["left"])
    ann_top = float(bounds["top"])
    ann_right = float(bounds["right"])
    ann_bottom = float(bounds["bottom"])

    for img_idx, img_data in enumerate(image_tokens):
        img_left = float(img_data["x"])
        img_top = float(img_data["y"])
        img_right = img_left + float(img_data["width"])
        img_bottom = img_top + float(img_data["height"])

        # Check for overlap (standard AABB intersection test)
        if (
            ann_left < img_right
            and ann_right > img_left
            and ann_top < img_bottom
            and ann_bottom > img_top
        ):
            # Calculate the token index for this image
            token_index = token_offset + img_idx
            token_refs.append({"pageIndex": page_idx, "tokenIndex": token_index})

    return token_refs
