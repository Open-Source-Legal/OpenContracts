import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from opencontractserver.constants.document_processing import (
    EMBEDDER_BATCH_REQUEST_TIMEOUT_SECONDS,
    EMBEDDER_SINGLE_REQUEST_TIMEOUT_SECONDS,
    MICROSERVICE_EMBEDDER_MAX_BATCH_SIZE,
)
from opencontractserver.pipeline.base.embedder import BaseEmbedder
from opencontractserver.pipeline.base.exceptions import (
    EmbeddingClientError,
    EmbeddingServerError,
)
from opencontractserver.pipeline.base.file_types import FileTypeEnum
from opencontractserver.pipeline.base.settings_schema import (
    PipelineSetting,
    SettingType,
)
from opencontractserver.utils.cloud import maybe_add_cloud_run_auth

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


# ---------------------------------------------------------------------------
# Shared HTTP session
# ---------------------------------------------------------------------------
#
# A module-level ``requests.Session`` (built lazily, behind a lock) gives us
# two things:
#
#   1. **Connection pooling.** Every per-call ``requests.post`` opened a fresh
#      TCP+TLS handshake. With a Session backed by an HTTPAdapter, urllib3
#      reuses keep-alive connections — meaningful when ingest fires
#      thousands of sub-batches against a localhost microservice or, more
#      so, a Cloud Run deployment.
#
#   2. **urllib3-level retry with exponential backoff.** This is a tighter
#      retry loop than celery's outer ``autoretry_for`` (which adds a 60s
#      countdown per attempt). For a transient 502/503/504 / connection
#      reset, urllib3 retries in milliseconds-to-seconds, often masking
#      the blip entirely from the celery layer. ``status_forcelist`` is
#      kept narrow (5xx + 429) so true client errors (4xx) still surface
#      immediately as ``EmbeddingClientError``.
#
# The session is shared across the process because ``requests.Session`` is
# thread-safe for the read-only operations we do (``post``); the lock just
# guards lazy construction. Embedder instances do not hold their own
# Session — that would create N pools per process, defeating the point.

_SESSION_LOCK = threading.Lock()
_SESSION: Optional[requests.Session] = None

# urllib3 Retry config: 3 attempts on 502/503/504/429 + connection-level
# errors, with exponential backoff (1s, 2s, 4s). ``allowed_methods``
# explicitly includes POST since urllib3 defaults to GET-only retries.
# ``raise_on_status=False`` lets the embedder code see the final response
# and decide between EmbeddingClientError / EmbeddingServerError /
# return-None semantics, rather than urllib3 raising opaquely.
_RETRY_CONFIG = Retry(
    total=3,
    connect=3,
    read=3,
    status=3,
    backoff_factor=1.0,
    status_forcelist=(429, 502, 503, 504),
    allowed_methods=frozenset(["POST"]),
    raise_on_status=False,
)


def _get_session() -> requests.Session:
    """Return the process-wide shared session, building it on first use."""
    global _SESSION
    if _SESSION is not None:
        return _SESSION
    with _SESSION_LOCK:
        if _SESSION is None:
            session = requests.Session()
            adapter = HTTPAdapter(
                max_retries=_RETRY_CONFIG,
                # Pool size sized for the highest concurrency any single
                # embedder advertises (currently 4 for OpenAI; 2 for
                # MicroserviceEmbedder gunicorn-worker count). Set to 16
                # to leave headroom for legitimate concurrent ingestion
                # tasks without hitting "Connection pool is full" warnings.
                pool_connections=16,
                pool_maxsize=16,
            )
            session.mount("http://", adapter)
            session.mount("https://", adapter)
            _SESSION = session
    return _SESSION


class MicroserviceEmbedder(BaseEmbedder):
    """
    Embedder that generates embeddings by calling an external microservice.

    Settings are loaded from PipelineSettings database. Use the management
    command `migrate_pipeline_settings` to seed initial values from environment.
    """

    title = "Microservice Embedder"
    description = "Generates embeddings using a vector embeddings microservice."
    author = "OpenContracts Team"
    dependencies = ["numpy", "requests"]
    vector_size = 384  # Default embedding size
    supported_file_types = [
        FileTypeEnum.PDF,
        FileTypeEnum.TXT,
        FileTypeEnum.DOCX,
    ]

    # The local microservice caps batch size at MICROSERVICE_EMBEDDER_MAX_BATCH_SIZE
    # (server-side env var ``MAX_TEXTS_PER_BATCH``, default 100). Raising
    # past it causes the service to 400 with "exceeds maximum"; pin
    # api_batch_size to the cap so we use the full per-call capacity.
    api_batch_size = MICROSERVICE_EMBEDDER_MAX_BATCH_SIZE

    # The reference deployment runs gunicorn with --workers 2, so up to
    # two HTTP requests can be processed truly in parallel (each worker
    # has its own SentenceTransformer process). Setting concurrency to
    # 2 fills both workers without queueing. Operators with a bigger
    # gunicorn fleet can override at the class level.
    embed_max_concurrent_sub_batches = 2

    @dataclass
    class Settings:
        """Configuration schema for MicroserviceEmbedder."""

        embeddings_microservice_url: str = field(
            default="",
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.REQUIRED,
                    required=True,
                    description="URL of the embeddings microservice",
                    env_var="EMBEDDINGS_MICROSERVICE_URL",
                )
            },
        )
        vector_embedder_api_key: str = field(
            default="",
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.SECRET,
                    required=False,
                    description="API key for the embeddings microservice (optional)",
                    env_var="VECTOR_EMBEDDER_API_KEY",
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

    def __init__(self, **kwargs):
        """Initialize MicroserviceEmbedder with settings from PipelineSettings."""
        super().__init__(**kwargs)
        logger.info("MicroserviceEmbedder initialized.")

    def _get_service_config(self, all_kwargs: dict) -> tuple[str, dict]:
        """
        Get service URL and headers for the microservice.

        Callers are responsible for pre-merging component settings into
        ``all_kwargs`` before calling this method.  In ``_embed_text_impl``
        the base class ``embed_text()`` does the merge; in ``embed_texts_batch``
        the merge is explicit since it overrides the base class directly.

        Args:
            all_kwargs: Keyword arguments that may override settings.

        Returns:
            Tuple of (service_url, headers)
        """
        s = self.settings if self.settings is not None else self.Settings()

        service_url = all_kwargs.get(
            "embeddings_microservice_url", s.embeddings_microservice_url
        )
        api_key = all_kwargs.get("vector_embedder_api_key", s.vector_embedder_api_key)
        use_cloud_run_iam_auth = bool(
            all_kwargs.get("use_cloud_run_iam_auth", s.use_cloud_run_iam_auth)
        )

        headers: dict[str, str | bytes] = {"Content-Type": "application/json"}
        if api_key:
            headers["X-API-Key"] = api_key

        headers = maybe_add_cloud_run_auth(
            service_url, headers, force=use_cloud_run_iam_auth
        )

        return service_url, headers

    def _embed_text_impl(self, text: str, **all_kwargs) -> Optional[list[float]]:
        """
        Generate embeddings from text using the microservice.

        Args:
            text: The text content to embed.
            **all_kwargs: Additional kwargs that can override settings.

        Returns:
            Embedding as a list of floats, or None if an error occurs.
        """
        logger.debug(
            f"MicroserviceEmbedder received text for embedding. Effective kwargs: {all_kwargs}"
        )
        try:
            service_url, headers = self._get_service_config(all_kwargs)

            response = _get_session().post(
                f"{service_url}/embeddings",
                json={"text": text},
                headers=headers,
                timeout=EMBEDDER_SINGLE_REQUEST_TIMEOUT_SECONDS,
            )

            if response.status_code == 200:
                body = response.json()
                if "embeddings" not in body:
                    logger.error(
                        f"Malformed 200 response: missing 'embeddings' key. "
                        f"Keys received: {list(body.keys())}"
                    )
                    return None
                embeddings_array = np.array(body["embeddings"])
                if np.isnan(embeddings_array).any():
                    logger.error("Embedding contains NaN values")
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
                    f"Microservice returned client error {response.status_code}. "
                    f"Input text length: {len(text)}"
                )
                return None  # Non-retriable error
            else:
                # Server errors (5xx) or unexpected status - worth logging distinctly
                logger.error(
                    f"Microservice returned server error {response.status_code}. "
                    f"This may be a transient error."
                )
                return None
        except Exception as e:
            logger.error(
                f"MicroserviceEmbedder - failed to generate embeddings due to error: {e}"
            )
            return None

    def embed_texts_batch(
        self, texts: list[str], **direct_kwargs
    ) -> Optional[list[Optional[list[float]]]]:
        """
        Generate embeddings for multiple texts in one HTTP request.

        Uses the microservice's /embeddings/batch endpoint for better throughput
        than sequential single-text calls.

        Args:
            texts: List of text strings to embed.
            **direct_kwargs: Additional keyword arguments.

        Returns:
            List of embedding vectors (None per item on failure),
            or None if the entire batch fails.

        Raises:
            ValueError: If len(texts) exceeds MICROSERVICE_EMBEDDER_MAX_BATCH_SIZE.
        """
        if not self.supports_text:
            logger.warning(
                f"{self.__class__.__name__} does not support text embeddings."
            )
            return None

        if not texts:
            return []

        if len(texts) > MICROSERVICE_EMBEDDER_MAX_BATCH_SIZE:
            raise ValueError(
                f"Batch size {len(texts)} exceeds maximum "
                f"{MICROSERVICE_EMBEDDER_MAX_BATCH_SIZE}. "
                f"Callers must sub-batch before calling embed_texts_batch()."
            )

        merged_kwargs = {**self.get_component_settings(), **direct_kwargs}

        try:
            service_url, headers = self._get_service_config(merged_kwargs)

            if not service_url:
                logger.error("No service URL configured for batch text embedding")
                return None

            payload: dict[str, Any] = {"texts": texts}
            response = _get_session().post(
                f"{service_url}/embeddings/batch",
                json=payload,
                headers=headers,
                timeout=EMBEDDER_BATCH_REQUEST_TIMEOUT_SECONDS,
            )

            if response.status_code == 200:
                body = response.json()
                if "embeddings" not in body:
                    logger.error(
                        f"Malformed 200 response: missing 'embeddings' key. "
                        f"Keys received: {list(body.keys())}"
                    )
                    return None
                embeddings_array = np.array(body["embeddings"])
                if embeddings_array.ndim == 3:
                    if embeddings_array.shape[1] != 1:
                        logger.error(f"Unexpected 3D shape {embeddings_array.shape}")
                        return None
                    embeddings_array = embeddings_array.squeeze(axis=1)

                if len(embeddings_array) != len(texts):
                    logger.error(
                        f"Vector count mismatch: sent {len(texts)} texts, "
                        f"received {len(embeddings_array)} vectors"
                    )
                    return None

                # Handle NaN values per-item rather than failing the whole batch
                results: list[Optional[list[float]]] = []
                for i, row in enumerate(embeddings_array):
                    if np.isnan(row).any():
                        logger.error(
                            f"Embedding at index {i} contains NaN values, "
                            f"returning None for this item"
                        )
                        results.append(None)
                    else:
                        results.append(row.tolist())
                return results
            elif 400 <= response.status_code < 500:
                # Client errors (4xx) - not retriable, likely invalid input.
                # Raise EmbeddingClientError so callers can distinguish a
                # client-side failure ("we sent bad data") from a caller-side
                # `None` return ("call completed with no vectors"). Callers
                # must NOT re-raise this at the Celery task level since it
                # would burn retries on a permanent failure.
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
