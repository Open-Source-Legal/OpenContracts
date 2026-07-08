"""
Fast test embedder for unit/integration tests.

This embedder returns deterministic fake vectors without requiring any external
services. It's used as the DEFAULT_EMBEDDER in test settings to ensure tests
run quickly and reliably.

For tests that need to verify actual embedder service connectivity (integration
tests), explicitly instantiate the real embedder class (e.g., MicroserviceEmbedder
or CLIPMicroserviceEmbedder) rather than relying on the default.
"""

import hashlib
import logging
from typing import Optional

from opencontractserver.pipeline.base.embedder import BaseEmbedder
from opencontractserver.pipeline.base.file_types import FileTypeEnum
from opencontractserver.types.enums import ContentModality

logger = logging.getLogger(__name__)


class TestEmbedder(BaseEmbedder):
    """
    A fast, deterministic embedder for testing.

    Returns fake embedding vectors based on a hash of the input text.
    This ensures:
    - Same text always produces same embedding (deterministic)
    - Different texts produce different embeddings (distinguishable)
    - No external service dependencies (fast and reliable)

    Vector size is 384 to match MicroserviceEmbedder (sentence-transformers).
    """

    title = "Test Embedder"
    description = "Fast deterministic embedder for unit and integration tests."
    author = "OpenContracts"
    dependencies = []
    vector_size = 384  # Match MicroserviceEmbedder dimension
    supported_file_types = [
        FileTypeEnum.PDF,
        FileTypeEnum.TXT,
        FileTypeEnum.DOCX,
    ]
    supported_modalities = {ContentModality.TEXT}

    def _embed_text_impl(self, text: str, **all_kwargs) -> Optional[list[float]]:
        """
        Generate a deterministic fake embedding from text.

        Uses MD5 hash of the text to generate reproducible vectors.
        The hash bytes are used to seed the vector values.

        Args:
            text: The text to embed.
            **all_kwargs: Ignored (for API compatibility).

        Returns:
            A list of 384 floats representing the fake embedding.
        """
        if not text or not text.strip():
            logger.debug("TestEmbedder received empty text, returning zero vector")
            return [0.0] * self.vector_size

        # Generate deterministic hash from text
        text_hash = hashlib.md5(text.encode("utf-8")).digest()

        # Extend hash to fill vector size
        # MD5 produces 16 bytes, we need 384 floats
        # Repeat the hash pattern and convert to floats in range [-1, 1]
        vector = []
        for i in range(self.vector_size):
            byte_val = text_hash[i % len(text_hash)]
            # Convert byte (0-255) to float (-1 to 1)
            float_val = (byte_val / 127.5) - 1.0
            vector.append(float_val)

        logger.debug(
            f"TestEmbedder generated {self.vector_size}-dim vector for "
            f"text of length {len(text)}"
        )
        return vector


class TestMultimodalEmbedder(BaseEmbedder):
    """
    A fast, deterministic multimodal embedder for testing.

    Supports both text and image embeddings with deterministic outputs.
    Vector size is 768 to match CLIPMicroserviceEmbedder (CLIP ViT-L-14).
    """

    title = "Test Multimodal Embedder"
    description = "Fast deterministic multimodal embedder for testing."
    author = "OpenContracts"
    dependencies = []
    vector_size = 768  # Match CLIPMicroserviceEmbedder dimension
    supported_file_types = [
        FileTypeEnum.PDF,
        FileTypeEnum.TXT,
        FileTypeEnum.DOCX,
    ]
    supported_modalities = {ContentModality.TEXT, ContentModality.IMAGE}

    def _embed_text_impl(self, text: str, **all_kwargs) -> Optional[list[float]]:
        """Generate a deterministic fake text embedding."""
        if not text or not text.strip():
            return [0.0] * self.vector_size

        text_hash = hashlib.md5(text.encode("utf-8")).digest()
        vector = []
        for i in range(self.vector_size):
            byte_val = text_hash[i % len(text_hash)]
            float_val = (byte_val / 127.5) - 1.0
            vector.append(float_val)

        return vector

    def _embed_image_impl(
        self, image_base64: str, image_format: str = "jpeg", **all_kwargs
    ) -> Optional[list[float]]:
        """Generate a deterministic fake image embedding."""
        if not image_base64:
            return [0.0] * self.vector_size

        # Use hash of base64 data (just first 1000 chars for speed)
        image_hash = hashlib.md5(image_base64[:1000].encode("utf-8")).digest()
        vector = []
        for i in range(self.vector_size):
            byte_val = image_hash[i % len(image_hash)]
            # Offset slightly from text embeddings to distinguish modalities
            float_val = ((byte_val + 64) % 256 / 127.5) - 1.0
            vector.append(float_val)

        return vector
