"""
Multimodal embedders for text and image embeddings via microservices.

This module provides embedders that support both text and image embeddings,
producing vectors in a shared embedding space for cross-modal similarity search.

Available embedders:
- CLIPMicroserviceEmbedder: CLIP ViT-L-14 model (768 dimensions)
- QwenMicroserviceEmbedder: Qwen embedding model (1024 dimensions)

Settings are loaded from PipelineSettings database. Use the management
command `migrate_pipeline_settings` to seed initial values from environment.
"""

import base64
import logging
from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import requests

from opencontractserver.pipeline.base.embedder import BaseEmbedder

# Re-export EmbeddingClientError / EmbeddingServerError at the original module
# path so external embedders that imported them from this module continue to
# work. The canonical location is now
# ``opencontractserver.pipeline.base.exceptions``.
from opencontractserver.pipeline.base.exceptions import (  # noqa: F401
    EmbeddingClientError,
    EmbeddingServerError,
)
from opencontractserver.pipeline.base.file_types import FileTypeEnum
from opencontractserver.pipeline.base.settings_schema import (
    PipelineSetting,
    SettingType,
)
from opencontractserver.types.enums import ContentModality
from opencontractserver.utils.cloud import maybe_add_cloud_run_auth

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class BaseMultimodalMicroserviceEmbedder(BaseEmbedder):
    """
    Abstract base class for multimodal embedders using microservices.

    Supports both text and image embeddings in a shared vector space, enabling
    cross-modal similarity search (e.g., find images similar to text queries).

    Subclasses must define:
        - Settings: A dataclass with url, api_key, and use_cloud_run_iam_auth fields
        - vector_size: Embedding dimension for this model
        - title, description: Human-readable metadata
        - _default_url: Default URL if setting is not configured
        - _get_service_config(): Get service configuration from Settings dataclass

    API Endpoints (expected by all implementations):
        - POST /embeddings: Text embeddings ({"text": "..."})
        - POST /embeddings/image: Image embeddings ({"image": "<base64>"})
        - POST /embeddings/batch: Batch text ({"texts": [...]} max 100)
        - POST /embeddings/image/batch: Batch images ({"images": [...]} max 20)
    """

    dependencies = ["numpy", "requests"]
    supported_file_types = [
        FileTypeEnum.PDF,
        FileTypeEnum.TXT,
        FileTypeEnum.DOCX,
    ]

    # Multimodal support - text and images in same vector space
    supported_modalities = {ContentModality.TEXT, ContentModality.IMAGE}

    # Name of the environment variable / Settings field that drives this
    # microservice's URL. Surfaced in error messages when no URL is
    # configured. Subclasses override with a concrete name (e.g.
    # "EMBEDDINGS_MICROSERVICE_URL").
    url_setting_name: str = ""

    def __init__(self, **kwargs):
        """Initialize the multimodal embedder."""
        super().__init__(**kwargs)
        logger.info(
            f"{self.__class__.__name__} initialized (vector_size={self.vector_size})."
        )

    @property
    @abstractmethod
    def _default_url(self) -> str:
        """Default URL if setting is not configured."""
        pass

    @abstractmethod
    def _get_service_config(self, all_kwargs: dict) -> tuple[str, str, dict]:
        """
        Get service URL, API key, and headers for the microservice.

        Subclasses must implement this to read from their Settings dataclass.

        Args:
            all_kwargs: Keyword arguments that may override settings.

        Returns:
            Tuple of (service_url, api_key, headers)
        """
        pass

    def _embed_text_impl(self, text: str, **all_kwargs) -> Optional[list[float]]:
        """
        Generate text embeddings via POST /embeddings.

        Note on error handling asymmetry with batch methods:
            This method returns None on ALL errors (including 5xx), because single
            annotations are typically processed within Celery tasks that already
            have their own retry logic. Raising here would abort processing of
            remaining annotations in the task.

            In contrast, ``embed_texts_batch()`` and ``embed_images_batch()`` raise
            ``EmbeddingServerError`` on 5xx so the Celery task-level retry decorator
            can fire, since a batch failure affects the entire sub-batch and there
            is no remaining work to preserve.

        Args:
            text: The text content to embed.
            **all_kwargs: All keyword arguments including PIPELINE_SETTINGS
                         and direct call-time arguments.

        Returns:
            Embedding vector as list of floats, or None on error.
        """
        logger.debug(
            f"{self.__class__.__name__} generating text embedding. "
            f"Text length: {len(text)}"
        )

        try:
            service_url, _, headers = self._get_service_config(all_kwargs)

            if not service_url:
                logger.error(
                    f"{self.__class__.__name__}: No service URL configured. "
                    f"Set {self.url_setting_name} in environment or PIPELINE_SETTINGS."
                )
                return None

            response = requests.post(
                f"{service_url}/embeddings",
                json={"text": text},
                headers=headers,
                timeout=30,
            )

            if response.status_code == 200:
                embeddings_array = np.array(response.json()["embeddings"])
                if np.isnan(embeddings_array).any():
                    logger.error(
                        f"Text embedding contains NaN values. "
                        f"Input text length: {len(text)}, "
                        f"first 100 chars: {text[:100]!r}"
                    )
                    return None
                # Handle both 1D (single embedding) and 2D (batch) response formats
                if embeddings_array.ndim == 1:
                    # Service returns 1D array directly: [0.1, 0.2, ...]
                    return embeddings_array.tolist()
                else:
                    # Service returns 2D batch array: [[0.1, 0.2, ...]]
                    return embeddings_array[0].tolist()
            elif 400 <= response.status_code < 500:
                # Client errors (4xx) - don't retry, likely invalid input
                logger.error(
                    f"{self.__class__.__name__} text embedding service returned client error "
                    f"{response.status_code}. Input text length: {len(text)}"
                )
                return None  # Non-retriable error
            else:
                # Server errors (5xx) or unexpected status - worth retrying
                error_msg = (
                    f"{self.__class__.__name__} text embedding service returned status "
                    f"{response.status_code}. This may be a transient error."
                )
                logger.error(error_msg)
                raise EmbeddingServerError(error_msg)  # Retriable error

        except requests.exceptions.Timeout:
            logger.error(
                f"{self.__class__.__name__} service request timed out for text embedding"
            )
            return None
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Failed to connect to {self.__class__.__name__} service: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to generate text embedding: {e}")
            return None

    def _embed_image_impl(
        self, image_base64: str, image_format: str = "jpeg", **all_kwargs
    ) -> Optional[list[float]]:
        """
        Generate image embeddings via POST /embeddings/image.

        Args:
            image_base64: Base64-encoded image data.
            image_format: Image format (jpeg, png, etc.). Currently unused by API.
            **all_kwargs: All keyword arguments including PIPELINE_SETTINGS
                         and direct call-time arguments.

        Returns:
            Embedding vector as list of floats, or None on error.
        """
        logger.debug(
            f"{self.__class__.__name__} generating image embedding. "
            f"Format: {image_format}, Data length: {len(image_base64)}"
        )

        # Validate base64 format before sending to microservice
        try:
            base64.b64decode(image_base64, validate=True)
        except Exception as e:
            logger.error(f"Invalid base64 image data: {e}")
            return None

        try:
            service_url, _, headers = self._get_service_config(all_kwargs)

            if not service_url:
                logger.error(
                    f"{self.__class__.__name__}: No service URL configured. "
                    f"Set {self.url_setting_name} in environment or PIPELINE_SETTINGS."
                )
                return None

            response = requests.post(
                f"{service_url}/embeddings/image",
                json={"image": image_base64},
                headers=headers,
                timeout=30,
            )

            if response.status_code == 200:
                embeddings_array = np.array(response.json()["embeddings"])
                if np.isnan(embeddings_array).any():
                    logger.error(
                        f"Image embedding contains NaN values. "
                        f"Image format: {image_format}, "
                        f"base64 data length: {len(image_base64)}"
                    )
                    return None
                # Handle both 1D (single embedding) and 2D (batch) response formats
                if embeddings_array.ndim == 1:
                    # Service returns 1D array directly: [0.1, 0.2, ...]
                    return embeddings_array.tolist()
                else:
                    # Service returns 2D batch array: [[0.1, 0.2, ...]]
                    return embeddings_array[0].tolist()
            elif 400 <= response.status_code < 500:
                # Client errors (4xx) - don't retry, likely invalid input
                logger.error(
                    f"{self.__class__.__name__} image embedding service returned client error "
                    f"{response.status_code}. Image format: {image_format}, "
                    f"base64 length: {len(image_base64)}"
                )
                return None  # Non-retriable error
            else:
                # Server errors (5xx) or unexpected status - worth retrying
                error_msg = (
                    f"{self.__class__.__name__} image embedding service returned status "
                    f"{response.status_code}. This may be a transient error."
                )
                logger.error(error_msg)
                raise EmbeddingServerError(error_msg)  # Retriable error

        except requests.exceptions.Timeout:
            logger.error(
                f"{self.__class__.__name__} service request timed out for image embedding"
            )
            return None
        except requests.exceptions.ConnectionError as e:
            logger.error(
                f"Failed to connect to {self.__class__.__name__} service for image: {e}"
            )
            return None
        except Exception as e:
            logger.error(f"Failed to generate image embedding: {e}")
            return None

    def embed_texts_batch(
        self, texts: list[str], **direct_kwargs
    ) -> Optional[list[Optional[list[float]]]]:
        """
        Generate embeddings for multiple texts in one request.

        Args:
            texts: List of text strings to embed (max 100).
            **direct_kwargs: Additional keyword arguments.

        Returns:
            List of embedding vectors, or None on error. Per-element
            ``None`` is supported by the base contract but never produced
            by this implementation — partial-batch failures surface as a
            single ``None`` return.
        """
        if len(texts) > 100:
            logger.warning(f"Batch size {len(texts)} exceeds max 100. Truncating.")
            texts = texts[:100]

        merged_kwargs = {**self.get_component_settings(), **direct_kwargs}

        try:
            service_url, _, headers = self._get_service_config(merged_kwargs)

            if not service_url:
                logger.error("No service URL configured for batch text embedding")
                return None

            text_payload: dict[str, Any] = {"texts": texts}
            response = requests.post(
                f"{service_url}/embeddings/batch",
                json=text_payload,
                headers=headers,
                timeout=60,
            )

            if response.status_code == 200:
                embeddings_array = np.array(response.json()["embeddings"])
                # Squeeze to 2D if service returns 3D array (each embedding wrapped)
                if embeddings_array.ndim == 3:
                    if embeddings_array.shape[1] != 1:
                        logger.error(f"Unexpected 3D shape {embeddings_array.shape}")
                        return None
                    embeddings_array = embeddings_array.squeeze(axis=1)
                if np.isnan(embeddings_array).any():
                    nan_indices = np.where(np.isnan(embeddings_array).any(axis=1))[0]
                    logger.error(
                        f"Batch text embeddings contain NaN values at indices: {nan_indices.tolist()}. "
                        f"Batch size: {len(texts)}"
                    )
                    return None
                return embeddings_array.tolist()
            elif 400 <= response.status_code < 500:
                # Client errors (4xx) - not retriable. Raise
                # EmbeddingClientError so callers can distinguish a
                # client-side failure from a parsing error (which still
                # returns None) and record it as a permanent failure
                # without triggering Celery retry.
                error_msg = (
                    f"Batch text embedding service returned client error "
                    f"{response.status_code}. Batch size: {len(texts)}"
                )
                logger.error(error_msg)
                raise EmbeddingClientError(error_msg)
            else:
                # Server errors (5xx) - retriable, re-raise for Celery retry
                error_msg = (
                    f"Batch text embedding service returned status "
                    f"{response.status_code}. This may be a transient error."
                )
                logger.error(error_msg)
                raise EmbeddingServerError(error_msg)

        except (
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
            EmbeddingServerError,
            EmbeddingClientError,
        ):
            # HTTP-specific errors: re-raise so callers can distinguish
            # them from generic parsing errors. Transient errors (5xx,
            # timeouts, connection resets) trigger Celery retry; client
            # errors (4xx) are handled as permanent failures by the
            # batch helper.
            raise
        except Exception as e:
            # Non-retriable errors (malformed data, unexpected parsing, etc.)
            logger.error(f"Failed to generate batch text embeddings: {e}")
            return None

    def embed_images_batch(
        self, images_base64: list[str], **direct_kwargs
    ) -> Optional[list[list[float]]]:
        """
        Generate embeddings for multiple images in one request.

        Args:
            images_base64: List of base64-encoded images (max 20).
            **direct_kwargs: Additional keyword arguments.

        Returns:
            List of embedding vectors, or None on error.
        """
        if len(images_base64) > 20:
            logger.warning(
                f"Batch size {len(images_base64)} exceeds max 20. Truncating."
            )
            images_base64 = images_base64[:20]

        merged_kwargs = {**self.get_component_settings(), **direct_kwargs}

        try:
            service_url, _, headers = self._get_service_config(merged_kwargs)

            if not service_url:
                logger.error("No service URL configured for batch image embedding")
                return None

            image_payload: dict[str, Any] = {"images": images_base64}
            response = requests.post(
                f"{service_url}/embeddings/image/batch",
                json=image_payload,
                headers=headers,
                timeout=120,
            )

            if response.status_code == 200:
                embeddings_array = np.array(response.json()["embeddings"])
                # Squeeze to 2D if service returns 3D array (each embedding wrapped)
                if embeddings_array.ndim == 3:
                    if embeddings_array.shape[1] != 1:
                        logger.error(f"Unexpected 3D shape {embeddings_array.shape}")
                        return None
                    embeddings_array = embeddings_array.squeeze(axis=1)
                if np.isnan(embeddings_array).any():
                    nan_indices = np.where(np.isnan(embeddings_array).any(axis=1))[0]
                    logger.error(
                        f"Batch image embeddings contain NaN values at indices: {nan_indices.tolist()}. "
                        f"Batch size: {len(images_base64)}"
                    )
                    return None
                return embeddings_array.tolist()
            elif 400 <= response.status_code < 500:
                # Client errors (4xx) - not retriable. Raise
                # EmbeddingClientError so callers can distinguish a
                # client-side failure from a parsing error (which still
                # returns None) and record it as a permanent failure
                # without triggering Celery retry.
                error_msg = (
                    f"Batch image embedding service returned client error "
                    f"{response.status_code}. Batch size: {len(images_base64)}"
                )
                logger.error(error_msg)
                raise EmbeddingClientError(error_msg)
            else:
                # Server errors (5xx) - retriable, re-raise for Celery retry
                error_msg = (
                    f"Batch image embedding service returned status "
                    f"{response.status_code}. This may be a transient error."
                )
                logger.error(error_msg)
                raise EmbeddingServerError(error_msg)

        except (
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
            EmbeddingServerError,
            EmbeddingClientError,
        ):
            # HTTP-specific errors: re-raise so callers can distinguish
            # them from generic parsing errors. Transient errors (5xx,
            # timeouts, connection resets) trigger Celery retry; client
            # errors (4xx) are handled as permanent failures by the
            # batch helper.
            raise
        except Exception as e:
            # Non-retriable errors (malformed data, unexpected parsing, etc.)
            logger.error(f"Failed to generate batch image embeddings: {e}")
            return None


class CLIPMicroserviceEmbedder(BaseMultimodalMicroserviceEmbedder):
    """
    Multimodal embedder using CLIP ViT-L-14 via microservice.

    Produces 768-dimensional vectors in a shared text-image embedding space.

    Settings are loaded from PipelineSettings database. Use the management
    command `migrate_pipeline_settings` to seed initial values from environment.
    """

    title = "CLIP Microservice Embedder"
    description = (
        "Generates embeddings for text and images using CLIP ViT-L-14. "
        "Produces 768-dimensional vectors in a shared embedding space for cross-modal search."
    )
    author = "OpenContracts"
    vector_size = 768

    @dataclass
    class Settings:
        """Configuration schema for CLIPMicroserviceEmbedder."""

        clip_embedder_url: str = field(
            default="http://multimodal-embedder:8000",
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.REQUIRED,
                    required=True,
                    description="URL of the CLIP embedding microservice",
                    env_var="MULTIMODAL_EMBEDDER_URL",
                )
            },
        )
        clip_embedder_api_key: str = field(
            default="",
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.SECRET,
                    required=False,
                    description="API key for the CLIP embedding service (optional)",
                    env_var="MULTIMODAL_EMBEDDER_API_KEY",
                )
            },
        )
        use_cloud_run_iam_auth: bool = field(
            default=False,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Force Google Cloud Run IAM authentication",
                )
            },
        )

    @property
    def _default_url(self) -> str:
        return "http://multimodal-embedder:8000"

    def _get_service_config(self, all_kwargs: dict) -> tuple[str, str, dict]:
        """
        Get service URL, API key, and headers for the CLIP microservice.

        Reads configuration from the Settings dataclass populated from
        PipelineSettings database. Keyword arguments can override settings.

        Args:
            all_kwargs: Keyword arguments that may override settings.

        Returns:
            Tuple of (service_url, api_key, headers)
        """
        s = self.settings
        if s is None:
            # Settings not loaded - use dataclass defaults
            s = self.Settings()

        service_url = all_kwargs.get("clip_embedder_url", s.clip_embedder_url)
        api_key = all_kwargs.get("clip_embedder_api_key", s.clip_embedder_api_key)
        use_cloud_run_iam_auth = bool(
            all_kwargs.get("use_cloud_run_iam_auth", s.use_cloud_run_iam_auth)
        )

        # Build headers
        headers: dict[str, str | bytes] = {"Content-Type": "application/json"}
        if api_key:
            headers["X-API-Key"] = api_key

        # Add Cloud Run IAM auth if applicable
        headers = maybe_add_cloud_run_auth(
            service_url, headers, force=use_cloud_run_iam_auth
        )

        return service_url, api_key, headers


class QwenMicroserviceEmbedder(BaseMultimodalMicroserviceEmbedder):
    """
    Multimodal embedder using Qwen embedding model via microservice.

    Produces 1024-dimensional vectors in a shared text-image embedding space.

    Settings are loaded from PipelineSettings database. Use the management
    command `migrate_pipeline_settings` to seed initial values from environment.
    """

    title = "Qwen Microservice Embedder"
    description = (
        "Generates embeddings for text and images using Qwen embedding model. "
        "Produces 1024-dimensional vectors in a shared embedding space for cross-modal search."
    )
    author = "OpenContracts"
    vector_size = 1024

    @dataclass
    class Settings:
        """Configuration schema for QwenMicroserviceEmbedder."""

        qwen_embedder_url: str = field(
            default="http://qwen-embedder:8000",
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.REQUIRED,
                    required=True,
                    description="URL of the Qwen embedding microservice",
                    env_var="QWEN_EMBEDDER_URL",
                )
            },
        )
        qwen_embedder_api_key: str = field(
            default="",
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.SECRET,
                    required=False,
                    description="API key for the Qwen embedding service (optional)",
                    env_var="QWEN_EMBEDDER_API_KEY",
                )
            },
        )
        use_cloud_run_iam_auth: bool = field(
            default=False,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Force Google Cloud Run IAM authentication",
                )
            },
        )

    @property
    def _default_url(self) -> str:
        return "http://qwen-embedder:8000"

    def _get_service_config(self, all_kwargs: dict) -> tuple[str, str, dict]:
        """
        Get service URL, API key, and headers for Qwen microservice.

        Reads configuration from the Settings dataclass populated from
        PipelineSettings database. Keyword arguments can override settings.

        Args:
            all_kwargs: Keyword arguments that may override settings.

        Returns:
            Tuple of (service_url, api_key, headers)
        """
        s = self.settings
        if s is None:
            # Settings not loaded - use dataclass defaults
            s = self.Settings()

        service_url = all_kwargs.get("qwen_embedder_url", s.qwen_embedder_url)
        api_key = all_kwargs.get("qwen_embedder_api_key", s.qwen_embedder_api_key)
        use_cloud_run_iam_auth = bool(
            all_kwargs.get("use_cloud_run_iam_auth", s.use_cloud_run_iam_auth)
        )

        # Build headers
        headers: dict[str, str | bytes] = {"Content-Type": "application/json"}
        if api_key:
            headers["X-API-Key"] = api_key

        # Apply Cloud Run IAM auth if enabled
        headers = maybe_add_cloud_run_auth(service_url, headers, use_cloud_run_iam_auth)

        return service_url, api_key, headers
