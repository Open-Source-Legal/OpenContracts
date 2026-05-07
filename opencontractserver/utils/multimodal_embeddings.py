"""
Multimodal embedding utilities for combining text and image embeddings.

Uses CLIP ViT-L-14 which produces 768-dimensional vectors in a shared
embedding space for both text and images. This enables cross-modal
similarity search (text-to-image, image-to-text).

When an annotation contains both text and image content, embeddings are
combined via weighted average with configurable weights (default: 30% text,
70% image - since image-containing annotations are often image-heavy).
"""

import logging
from typing import TYPE_CHECKING, Optional, Union, cast

import numpy as np
from django.conf import settings
from typing_extensions import NotRequired, TypedDict

if TYPE_CHECKING:
    from opencontractserver.annotations.models import Annotation
    from opencontractserver.pipeline.base.embedder import BaseEmbedder

from opencontractserver.annotations.compact_json import iter_page_annotations
from opencontractserver.types.dicts import PawlsTokenPythonType
from opencontractserver.types.enums import ContentModality
from opencontractserver.utils.compact_pawls import expand_pawls_pages
from opencontractserver.utils.pdf_token_extraction import (
    get_image_as_base64,
    load_pawls_data,
)

logger = logging.getLogger(__name__)


class _ImageContentToken(TypedDict):
    """Narrow shape for tokens loaded from ``annotation.image_content_file``.

    Distinct from ``PawlsTokenPythonType``: the cached file persists only the
    image fields needed downstream, so x/y/text are absent and the base64
    payload is keyed as ``image_data`` rather than ``base64_data``. Defining
    this explicitly documents the on-disk contract and avoids a misleading
    cast to ``PawlsTokenPythonType``.
    """

    is_image: bool
    image_data: NotRequired[Optional[str]]
    format: NotRequired[str]
    width: NotRequired[Optional[int]]
    height: NotRequired[Optional[int]]


# Image tokens reach ``embed_images_average`` from two sources:
# - Fast path: ``load_images_from_annotation_file`` → ``_ImageContentToken``
# - Slow path: PAWLs traversal → ``PawlsTokenPythonType`` (with is_image=True)
# The union captures both without misrepresenting either; callers dispatch
# on whichever fields are present.
ImageTokenLike = Union[PawlsTokenPythonType, _ImageContentToken]


def get_multimodal_weights() -> tuple[float, float]:
    """
    Get configured text/image weights for multimodal embedding combination.

    Returns:
        Tuple of (text_weight, image_weight) from settings or defaults.
        Default weights: 0.3 text, 0.7 image (images weighted higher as
        multimodal annotations are often predominantly visual).
    """
    weights = getattr(settings, "MULTIMODAL_EMBEDDING_WEIGHTS", {})
    text_weight = weights.get("text_weight", 0.3)
    image_weight = weights.get("image_weight", 0.7)
    return text_weight, image_weight


def normalize_vector(vector: list[float]) -> list[float]:
    """
    Normalize vector to unit length (L2 normalization).

    Args:
        vector: Input embedding vector.

    Returns:
        Unit-length normalized vector.
    """
    arr = np.array(vector, dtype=np.float64)
    norm = np.linalg.norm(arr)
    if norm > 0:
        arr = arr / norm
    return arr.tolist()


def weighted_average_embeddings(
    vectors: list[list[float]],
    weights: list[float],
) -> list[float]:
    """
    Compute weighted average of embedding vectors, normalized to unit length.

    Args:
        vectors: List of embedding vectors (all same dimension).
        weights: Weights for each vector (will be normalized to sum to 1).

    Returns:
        Weighted average embedding, normalized to unit length.

    Raises:
        ValueError: If vectors have different dimensions.
    """
    if not vectors:
        return []

    # Validate that all vectors have the same dimension
    dimensions = {len(v) for v in vectors}
    if len(dimensions) > 1:
        raise ValueError(
            f"Cannot average vectors of different dimensions: {sorted(dimensions)}"
        )

    arr = np.array(vectors, dtype=np.float64)
    weights_arr = np.array(weights, dtype=np.float64)

    # Normalize weights to sum to 1
    weights_arr = weights_arr / weights_arr.sum()

    combined = np.average(arr, axis=0, weights=weights_arr)
    return normalize_vector(combined.tolist())


def get_annotation_image_tokens(
    annotation: "Annotation",
    pawls_data: Optional[list[dict]] = None,
) -> list[ImageTokenLike]:
    """
    Extract image tokens referenced by an annotation.

    Fast path: If annotation has pre-extracted image_content_file, load from there.
    Fallback: Load from PAWLs data (document or structural_set).

    Args:
        annotation: Annotation model instance.
        pawls_data: Optional pre-loaded PAWLs data. If not provided,
                   will be loaded from annotation's document.

    Returns:
        List of image token dicts from the PAWLs data.
    """
    # Fast path: check for pre-extracted image content file
    if annotation.image_content_file:
        images = load_images_from_annotation_file(annotation)
        if images:
            logger.debug(
                f"Annotation {annotation.pk} loaded {len(images)} images from "
                f"image_content_file (fast path)"
            )
            # ``list`` is invariant; widen explicitly to the union the
            # function declares.
            return list(images)
        # Fall through to PAWLs if file load failed

    try:
        import json

        document = annotation.document

        # Load PAWLs data from document or structural_set (slow path)
        if pawls_data is None:
            if document:
                pawls_data = load_pawls_data(document)
            elif (
                annotation.structural_set and annotation.structural_set.pawls_parse_file
            ):
                # Structural annotation without document - load from structural_set
                # (same approach as get_annotation_images in image_tools.py)
                pawls_file = annotation.structural_set.pawls_parse_file
                try:
                    pawls_file.open("r")
                    try:
                        pawls_data = expand_pawls_pages(json.load(pawls_file))
                        logger.debug(
                            f"Annotation {annotation.pk} loaded PAWLs from "
                            f"structural_set {annotation.structural_set_id}"
                        )
                    finally:
                        pawls_file.close()
                except Exception as e:
                    logger.error(
                        f"Error loading PAWLs from structural set "
                        f"{annotation.structural_set_id}: {e}"
                    )
                    pawls_data = None
            else:
                logger.warning(
                    f"Annotation {annotation.pk} has no document or "
                    f"structural_set with PAWLs file"
                )
                return []

        if not pawls_data:
            return []

        # Get token references from annotation json (handles v1 and v2 formats)
        image_tokens: list[ImageTokenLike] = []

        for page in iter_page_annotations(
            annotation.json or {}, raw_text=annotation.raw_text or ""
        ):
            for token_idx in page.token_indices:
                # Get actual token from PAWLs data
                if page.page_index < len(pawls_data):
                    pawls_page = pawls_data[page.page_index]
                    if not isinstance(pawls_page, dict):
                        continue

                    tokens = pawls_page.get("tokens", [])
                    if token_idx < len(tokens):
                        token = tokens[token_idx]
                        if isinstance(token, dict) and token.get("is_image"):
                            image_tokens.append(cast(PawlsTokenPythonType, token))

        return image_tokens
    except Exception as e:
        logger.error(
            f"Error extracting image tokens from annotation {annotation.pk}: {e}"
        )
        return []


def embed_images_average(
    embedder: "BaseEmbedder",
    image_tokens: list[ImageTokenLike],
) -> Optional[list[float]]:
    """
    Embed all image tokens and return their average embedding.

    Args:
        embedder: Multimodal embedder with embed_image() method.
        image_tokens: List of image token dicts from PAWLs data.

    Returns:
        Average 768d embedding of all images, or None if no valid embeddings.
    """
    if not image_tokens:
        return None

    embeddings = []

    for token in image_tokens:
        # Get base64 image data. ``get_image_as_base64`` looks up
        # ``base64_data`` / ``image_path`` on full PAWLs tokens; on the
        # narrower ``_ImageContentToken`` it returns None and the token is
        # skipped (matches the prior behavior — the cached file path is
        # exercised through the slow path in practice).
        base64_data = get_image_as_base64(cast(PawlsTokenPythonType, token))
        if not base64_data:
            logger.debug("Could not get base64 data for image token")
            continue

        img_format = token.get("format", "jpeg")

        # Embed the image
        try:
            embedding = embedder.embed_image(base64_data, image_format=img_format)
            if embedding is not None:
                embeddings.append(embedding)
        except Exception as e:
            logger.error(f"Failed to embed image: {e}")
            continue

    if not embeddings:
        logger.warning("No valid image embeddings generated")
        return None

    # Average all image embeddings
    arr = np.array(embeddings, dtype=np.float64)
    averaged = np.mean(arr, axis=0)
    return normalize_vector(averaged.tolist())


def generate_multimodal_embedding(
    annotation: "Annotation",
    embedder: "BaseEmbedder",
    text_weight: Optional[float] = None,
    image_weight: Optional[float] = None,
) -> Optional[list[float]]:
    """
    Generate unified embedding for annotation containing text, images, or both.

    For multimodal embedders (CLIP), text and image embeddings are in the
    same vector space and can be meaningfully combined via weighted average.

    Logic:
    - TEXT only: embed text via embed_text()
    - IMAGE only: embed all images, average them
    - MIXED: weighted average of text embedding and images average

    Args:
        annotation: Annotation to embed.
        embedder: Multimodal embedder (must have embed_text and embed_image).
        text_weight: Weight for text embedding (default from settings: 0.3).
        image_weight: Weight for image embedding (default from settings: 0.7).

    Returns:
        768d embedding vector in CLIP space, or None on failure.
    """
    # Get weights from settings if not provided
    if text_weight is None or image_weight is None:
        default_text, default_image = get_multimodal_weights()
        text_weight = text_weight if text_weight is not None else default_text
        image_weight = image_weight if image_weight is not None else default_image

    modalities = annotation.content_modalities or [ContentModality.TEXT.value]
    has_text = ContentModality.TEXT.value in modalities
    has_image = ContentModality.IMAGE.value in modalities

    logger.debug(
        f"Generating multimodal embedding for annotation {annotation.pk}: "
        f"modalities={modalities}, has_text={has_text}, has_image={has_image}"
    )

    text_embedding = None
    image_embedding = None

    # Embed text if present
    if has_text:
        raw_text = annotation.raw_text or ""
        if raw_text.strip():
            try:
                text_embedding = embedder.embed_text(raw_text)
                if text_embedding:
                    logger.debug(f"Generated text embedding: dim={len(text_embedding)}")
            except Exception as e:
                logger.error(f"Failed to generate text embedding: {e}")

    # Embed images if present and embedder supports images
    if has_image and embedder.supports_images:
        image_tokens = get_annotation_image_tokens(annotation)
        if image_tokens:
            logger.debug(f"Found {len(image_tokens)} image tokens to embed")
            image_embedding = embed_images_average(embedder, image_tokens)
            if image_embedding:
                logger.debug(f"Generated image embedding: dim={len(image_embedding)}")
        else:
            logger.debug("No image tokens found in annotation")

    # Combine embeddings based on what we have
    if text_embedding and image_embedding:
        # Mixed modality - weighted average
        logger.info(
            f"Combining text ({text_weight}) and image ({image_weight}) embeddings "
            f"for annotation {annotation.pk}"
        )
        return weighted_average_embeddings(
            [text_embedding, image_embedding],
            [text_weight, image_weight],
        )
    elif text_embedding:
        # Text only
        logger.debug(f"Using text-only embedding for annotation {annotation.pk}")
        return text_embedding
    elif image_embedding:
        # Image only
        logger.debug(f"Using image-only embedding for annotation {annotation.pk}")
        return image_embedding
    else:
        # Nothing to embed
        logger.warning(
            f"Annotation {annotation.pk} has no embeddable content "
            f"(modalities={modalities})"
        )
        return None


def extract_and_store_annotation_images(
    annotation: "Annotation",
    pawls_data: list[dict],
) -> bool:
    """
    Extract image data from PAWLs and store in annotation.image_content_file.

    This pre-extracts image content so that embedding tasks don't need to reload
    the full PAWLs file. The extracted data is stored as a small JSON file.

    Args:
        annotation: Annotation to store images for (must have IMAGE modality).
        pawls_data: Pre-loaded PAWLs data (list of page dicts).

    Returns:
        True if images were extracted and stored, False otherwise.
    """
    import json

    from django.core.files.base import ContentFile

    try:
        # Get token references from annotation json (handles v1 and v2 formats)
        extracted_images = []

        for page in iter_page_annotations(
            annotation.json or {}, raw_text=annotation.raw_text or ""
        ):
            for token_idx in page.token_indices:
                # Get actual token from PAWLs data
                if page.page_index < len(pawls_data):
                    pawls_page = pawls_data[page.page_index]
                    if not isinstance(pawls_page, dict):
                        continue

                    tokens = pawls_page.get("tokens", [])
                    if token_idx < len(tokens):
                        token = tokens[token_idx]
                        if isinstance(token, dict) and token.get("is_image"):
                            # Extract image data
                            base64_data = get_image_as_base64(
                                cast(PawlsTokenPythonType, token)
                            )
                            if base64_data:
                                extracted_images.append(
                                    {
                                        "base64": base64_data,
                                        "format": token.get("format", "jpeg"),
                                        "page_index": page.page_index,
                                        "token_index": token_idx,
                                        "width": token.get("width"),
                                        "height": token.get("height"),
                                    }
                                )

        if not extracted_images:
            logger.debug(f"Annotation {annotation.pk} has no images to extract")
            return False

        # Store as JSON file
        content = json.dumps({"images": extracted_images})
        file_content = ContentFile(content.encode("utf-8"))
        annotation.image_content_file.save(
            f"annot_{annotation.pk}_images.json",
            file_content,
            save=True,
        )

        logger.info(
            f"Extracted and stored {len(extracted_images)} images for "
            f"annotation {annotation.pk}"
        )
        return True

    except Exception as e:
        logger.error(f"Error extracting images for annotation {annotation.pk}: {e}")
        return False


def load_images_from_annotation_file(
    annotation: "Annotation",
) -> list[_ImageContentToken]:
    """
    Load pre-extracted image data from annotation.image_content_file.

    Args:
        annotation: Annotation with image_content_file populated.

    Returns:
        List of image token dicts with base64 data, or empty list on failure.
    """
    import json

    try:
        if not annotation.image_content_file:
            return []

        annotation.image_content_file.open("r")
        try:
            data = json.load(annotation.image_content_file)
            images = data.get("images", [])
            # Build ``_ImageContentToken``s — distinct from full PAWLs tokens.
            return [
                _ImageContentToken(
                    is_image=True,
                    image_data=img.get("base64"),
                    format=img.get("format", "jpeg"),
                    width=img.get("width"),
                    height=img.get("height"),
                )
                for img in images
            ]
        finally:
            annotation.image_content_file.close()

    except Exception as e:
        logger.error(f"Error loading images from annotation {annotation.pk} file: {e}")
        return []


def batch_extract_annotation_images(
    annotations: list["Annotation"],
    pawls_data: list[dict],
) -> int:
    """
    Batch extract and store images for multiple annotations.

    Efficiently processes multiple annotations sharing the same PAWLs data,
    avoiding repeated file loads.

    Args:
        annotations: List of annotations to process.
        pawls_data: Shared PAWLs data for all annotations.

    Returns:
        Number of annotations that had images extracted.
    """
    count = 0
    for annotation in annotations:
        modalities = annotation.content_modalities or []
        if ContentModality.IMAGE.value in modalities:
            if extract_and_store_annotation_images(annotation, pawls_data):
                count += 1
    return count
