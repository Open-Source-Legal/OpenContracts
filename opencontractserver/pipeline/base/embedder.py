import logging
from abc import ABC, abstractmethod
from typing import ClassVar, Optional

import requests

from opencontractserver.pipeline.base.file_types import FileTypeEnum
from opencontractserver.types.enums import ContentModality
from opencontractserver.utils.logging import redact_sensitive_kwargs

from .base_component import PipelineComponentBase

logger = logging.getLogger(__name__)


class BaseEmbedder(PipelineComponentBase, ABC):
    """
    Abstract base class for embedders. Embedders should inherit from this class.
    Handles automatic loading of settings from Django settings.PIPELINE_SETTINGS.

    Embedders can support different modalities via the `supported_modalities` attribute:
    - Text-only (default): `supported_modalities = {ContentModality.TEXT}`
    - Multimodal: `supported_modalities = {ContentModality.TEXT, ContentModality.IMAGE}`

    To create a multimodal embedder:
    1. Set `supported_modalities = {ContentModality.TEXT, ContentModality.IMAGE}`
    2. Implement `_embed_image_impl()` in addition to `_embed_text_impl()`

    Convenience properties `is_multimodal`, `supports_text`, and `supports_images`
    are derived from `supported_modalities`.
    """

    vector_size: int = 0  # Provide the data shape of the returned embeddings.
    supported_file_types: ClassVar[list[FileTypeEnum]] = []

    # Single source of truth for modality support
    # Override in subclasses to add multimodal support
    supported_modalities: ClassVar[set[ContentModality]] = {ContentModality.TEXT}

    # ------------------------------------------------------------------ #
    # Batch-embedding tunables (override per subclass)
    # ------------------------------------------------------------------ #
    #
    # ``api_batch_size``: maximum number of inputs sent in one
    # ``embed_texts_batch`` call to the underlying provider. The
    # ``calculate_embeddings_for_annotation_batch`` task reads this when
    # carving annotations into sub-batches. Defaults to the global
    # ``EMBEDDING_API_BATCH_SIZE`` constant; subclasses pick a value
    # appropriate for the provider's published batch limit and the
    # subclass's typical input-token budget.
    #
    # ``embed_max_concurrent_sub_batches``: how many sub-batches the
    # embedding task is allowed to fly in parallel against the provider.
    # 1 means strictly sequential (the historical behaviour). Subclasses
    # that talk to a high-throughput hosted API can raise this to push
    # ingest wall-clock down. The task uses a thread pool, so concurrent
    # sub-batches share the same Python process — keep this modest
    # (4-8 is usually enough; higher just pressures provider RPM).
    #
    # Both are class attributes (not instance settings) so they don't
    # need to round-trip through ``PipelineSettings`` for what's a static
    # provider characteristic. Override at class definition time.
    api_batch_size: int = 50
    embed_max_concurrent_sub_batches: int = 1

    # Convenience properties derived from supported_modalities
    @property
    def is_multimodal(self) -> bool:
        """Whether this embedder supports multiple modalities."""
        return len(self.supported_modalities) > 1

    @property
    def supports_text(self) -> bool:
        """Whether this embedder supports text input."""
        return ContentModality.TEXT in self.supported_modalities

    @property
    def supports_images(self) -> bool:
        """Whether this embedder supports image input."""
        return ContentModality.IMAGE in self.supported_modalities

    def get_supported_modalities_as_strings(self) -> list[str]:
        """
        Returns a list of content modalities this embedder supports as strings.

        Returns:
            List of supported modality strings (e.g., ["TEXT"], ["TEXT", "IMAGE"]).
        """
        return ContentModality.to_strings(self.supported_modalities)

    def supports_modalities(self, modalities: list[str]) -> bool:
        """
        Check if this embedder supports all the given content modalities.

        This is useful for filtering annotations before embedding - if an annotation
        contains modalities the embedder doesn't support, it should be skipped.

        Args:
            modalities: List of modality strings to check (e.g., ["TEXT", "IMAGE"]).

        Returns:
            True if the embedder supports ALL given modalities, False otherwise.
        """
        if not modalities:
            return True  # Empty modality list is always supported

        try:
            required = ContentModality.from_strings(modalities)
            return required.issubset(self.supported_modalities)
        except ValueError:
            return False  # Unknown modality requested

    def __init__(self, **kwargs):
        """
        Initializes the Embedder.
        Kwargs are passed to the superclass constructor (PipelineComponentBase).
        """
        super().__init__(**kwargs)

    @abstractmethod
    def _embed_text_impl(self, text: str, **all_kwargs) -> Optional[list[float]]:
        """
        Abstract internal method to generate embeddings from text.
        Concrete subclasses must implement this method.

        Args:
            text (str): The text content to embed.
            **all_kwargs: All keyword arguments, including those from
                          PIPELINE_SETTINGS and direct call-time arguments.

        Returns:
            Optional[List[float]]: The embeddings as a list of floats, or None if an error occurs.
        """
        pass

    def _embed_image_impl(
        self, image_base64: str, image_format: str = "jpeg", **all_kwargs
    ) -> Optional[list[float]]:
        """
        Internal method to generate embeddings from an image.
        Override this method in multimodal embedders that support image input.

        Args:
            image_base64 (str): Base64-encoded image data.
            image_format (str): Image format (e.g., "jpeg", "png", "webp").
            **all_kwargs: All keyword arguments, including those from
                          PIPELINE_SETTINGS and direct call-time arguments.

        Returns:
            Optional[List[float]]: The embeddings as a list of floats, or None if
                                   an error occurs or images are not supported.
        """
        if not self.supports_images:
            logger.warning(
                f"{self.__class__.__name__} does not support image embeddings. "
                "Add ContentModality.IMAGE to supported_modalities and implement "
                "_embed_image_impl()."
            )
            return None
        raise NotImplementedError(
            f"{self.__class__.__name__} has ContentModality.IMAGE in "
            "supported_modalities but _embed_image_impl() is not implemented."
        )

    def embed_text(self, text: str, **direct_kwargs) -> Optional[list[float]]:
        """
        Generates embeddings from text, automatically injecting settings from PIPELINE_SETTINGS.

        Args:
            text (str): The text content to embed.
            **direct_kwargs: Arbitrary keyword arguments that may be provided
                             for specific embedder functionalities at call time.
                             These will override settings from PIPELINE_SETTINGS.

        Returns:
            Optional[List[float]]: The embeddings as a list of floats, or None if an error occurs.
        """
        if not self.supports_text:
            logger.warning(
                f"{self.__class__.__name__} does not support text embeddings."
            )
            return None
        merged_kwargs = {**self.get_component_settings(), **direct_kwargs}
        logger.info(
            f"Calling _embed_text_impl with merged kwargs: "
            f"{redact_sensitive_kwargs(merged_kwargs)}"
        )
        return self._embed_text_impl(text, **merged_kwargs)

    def embed_image(
        self, image_base64: str, image_format: str = "jpeg", **direct_kwargs
    ) -> Optional[list[float]]:
        """
        Generates embeddings from an image, automatically injecting settings from PIPELINE_SETTINGS.

        Args:
            image_base64 (str): Base64-encoded image data.
            image_format (str): Image format (e.g., "jpeg", "png", "webp").
            **direct_kwargs: Arbitrary keyword arguments that may be provided
                             for specific embedder functionalities at call time.
                             These will override settings from PIPELINE_SETTINGS.

        Returns:
            Optional[List[float]]: The embeddings as a list of floats, or None if
                                   an error occurs or images are not supported.
        """
        if not self.supports_images:
            logger.warning(
                f"{self.__class__.__name__} does not support image embeddings. "
                f"supported_modalities={self.supported_modalities}"
            )
            return None
        merged_kwargs = {**self.get_component_settings(), **direct_kwargs}
        logger.info(
            f"Calling _embed_image_impl with merged kwargs: "
            f"{redact_sensitive_kwargs(merged_kwargs)}"
        )
        return self._embed_image_impl(image_base64, image_format, **merged_kwargs)

    def embed_texts_batch(
        self, texts: list[str], **direct_kwargs
    ) -> Optional[list[Optional[list[float]]]]:
        """
        Generate embeddings for multiple texts in one call.

        The default implementation calls embed_text() sequentially for each text.
        Subclasses (e.g., microservice-based embedders) should override this to
        use a true batch API endpoint for better throughput.

        .. warning::

            The sequential fallback re-raises transient HTTP exceptions
            (``requests.exceptions.Timeout``, ``requests.exceptions.ConnectionError``)
            so that callers (e.g., Celery tasks) can trigger retries. Subclasses
            that make HTTP calls should override this method to get the same
            behaviour for any additional transient exception types they define.

        Args:
            texts: List of text strings to embed.
            **direct_kwargs: Additional keyword arguments passed to the embedder.

        Returns:
            List of embedding vectors (or None per item on failure),
            or None if the entire batch fails.
        """
        if not self.supports_text:
            logger.warning(
                f"{self.__class__.__name__} does not support text embeddings."
            )
            return None

        if not texts:
            return []

        results: list[Optional[list[float]]] = []
        for text in texts:
            try:
                results.append(self.embed_text(text, **direct_kwargs))
            except (
                requests.exceptions.Timeout,
                requests.exceptions.ConnectionError,
            ):
                # Transient HTTP errors must propagate so callers can retry.
                raise
            except Exception as e:
                logger.error(
                    f"{self.__class__.__name__} failed to embed text "
                    f"(length={len(text)}): {e}"
                )
                results.append(None)
        return results

    def embed_text_and_image(
        self,
        text: str,
        image_base64: str,
        image_format: str = "jpeg",
        **direct_kwargs,
    ) -> Optional[list[float]]:
        """
        Generates embeddings from both text and image combined.
        This is useful for multimodal models that can jointly encode text and images.

        Default implementation returns None. Override in multimodal embedders
        that support joint text-image encoding.

        Args:
            text (str): The text content to embed.
            image_base64 (str): Base64-encoded image data.
            image_format (str): Image format (e.g., "jpeg", "png", "webp").
            **direct_kwargs: Arbitrary keyword arguments.

        Returns:
            Optional[List[float]]: The joint embeddings, or None if not supported.
        """
        if not self.is_multimodal:
            logger.warning(
                f"{self.__class__.__name__} is not a multimodal embedder. "
                "Cannot generate joint text-image embeddings."
            )
            return None
        # Default: not implemented, subclasses can override
        logger.warning(
            f"{self.__class__.__name__} does not implement joint text-image embedding. "
            "Consider embedding text and image separately."
        )
        return None
