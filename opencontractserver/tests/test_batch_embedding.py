"""
Tests for batch embedding functionality.

Tests the batch embedding pipeline: BaseEmbedder.embed_texts_batch(),
_batch_embed_text_annotations(), MicroserviceEmbedder.embed_texts_batch(),
calculate_embeddings_for_annotation_batch() with true batch API calls,
and integration tests for the full Celery task.
"""

import unittest
from typing import Optional
from unittest.mock import MagicMock, patch

import numpy as np
import requests

from opencontractserver.constants.document_processing import (
    MICROSERVICE_EMBEDDER_MAX_BATCH_SIZE,
)
from opencontractserver.pipeline.base.embedder import BaseEmbedder
from opencontractserver.pipeline.base.exceptions import (
    EmbeddingClientError,
    EmbeddingServerError,
)
from opencontractserver.pipeline.base.file_types import FileTypeEnum
from opencontractserver.pipeline.embedders.sent_transformer_microservice import (
    MicroserviceEmbedder,
)
from opencontractserver.tasks.embeddings_task import (
    _batch_embed_text_annotations,
    calculate_embeddings_for_annotation_batch,
)
from opencontractserver.types.enums import ContentModality


class DummyEmbedder384(BaseEmbedder):
    """Minimal test embedder with 384-dim vectors."""

    title = "Dummy 384"
    description = "Test embedder"
    author = "Test"
    dependencies = []
    vector_size = 384
    supported_file_types = [FileTypeEnum.PDF, FileTypeEnum.TXT]

    def _embed_text_impl(self, text: str, **all_kwargs) -> Optional[list[float]]:
        if not text or not text.strip():
            return [0.0] * self.vector_size
        return [0.1] * self.vector_size


class FailingBatchEmbedder(BaseEmbedder):
    """Embedder whose batch method raises a built-in ``ConnectionError``.

    Uses the built-in ``ConnectionError`` (not ``requests.exceptions.ConnectionError``)
    to simulate a generic non-retriable exception.  In the batch embedding task,
    this falls through to the catch-all ``except Exception`` handler and is
    recorded as a permanent per-annotation failure rather than triggering a
    Celery retry.
    """

    title = "Failing Batch"
    description = "Test embedder that fails on batch"
    author = "Test"
    dependencies = []
    vector_size = 384
    supported_file_types = [FileTypeEnum.PDF]

    def _embed_text_impl(self, text: str, **all_kwargs) -> Optional[list[float]]:
        return [0.1] * self.vector_size

    def embed_texts_batch(
        self, texts: list[str], **direct_kwargs
    ) -> Optional[list[Optional[list[float]]]]:
        raise ConnectionError("Service unavailable")


class PartialFailBatchEmbedder(BaseEmbedder):
    """Embedder that returns None for some items in the batch."""

    title = "Partial Fail Batch"
    description = "Returns None for even-indexed texts"
    author = "Test"
    dependencies = []
    vector_size = 384
    supported_file_types = [FileTypeEnum.PDF]

    def _embed_text_impl(self, text: str, **all_kwargs) -> Optional[list[float]]:
        return [0.1] * self.vector_size

    def embed_texts_batch(
        self, texts: list[str], **direct_kwargs
    ) -> Optional[list[Optional[list[float]]]]:
        results = []
        for i, text in enumerate(texts):
            if i % 2 == 0:
                results.append(None)  # Simulate failure for even indices
            else:
                results.append([0.1] * self.vector_size)
        return results


class NullBatchEmbedder(BaseEmbedder):
    """Embedder whose batch method returns None (total failure)."""

    title = "Null Batch"
    description = "Returns None from embed_texts_batch"
    author = "Test"
    dependencies = []
    vector_size = 384
    supported_file_types = [FileTypeEnum.PDF]

    def _embed_text_impl(self, text: str, **all_kwargs) -> Optional[list[float]]:
        return [0.1] * self.vector_size

    def embed_texts_batch(
        self, texts: list[str], **direct_kwargs
    ) -> Optional[list[Optional[list[float]]]]:
        return None


class MismatchCountEmbedder(BaseEmbedder):
    """Embedder that returns fewer vectors than texts sent."""

    title = "Mismatch Count"
    description = "Returns fewer vectors than texts"
    author = "Test"
    dependencies = []
    vector_size = 384
    supported_file_types = [FileTypeEnum.PDF]

    def _embed_text_impl(self, text: str, **all_kwargs) -> Optional[list[float]]:
        return [0.1] * self.vector_size

    def embed_texts_batch(
        self, texts: list[str], **direct_kwargs
    ) -> Optional[list[Optional[list[float]]]]:
        # Return one fewer vector than texts sent
        return [[0.1] * self.vector_size for _ in texts[:-1]]


class TestBaseEmbedderBatchFallback(unittest.TestCase):
    """Test that BaseEmbedder.embed_texts_batch falls back to sequential calls."""

    def test_sequential_fallback(self):
        """Default embed_texts_batch calls embed_text per item."""
        embedder = DummyEmbedder384()
        texts = ["Hello", "World", "Test"]
        results = embedder.embed_texts_batch(texts)

        self.assertIsNotNone(results)
        self.assertEqual(len(results), 3)
        for vec in results:
            self.assertIsNotNone(vec)
            self.assertEqual(len(vec), 384)

    def test_empty_list(self):
        """Empty text list returns empty results."""
        embedder = DummyEmbedder384()
        results = embedder.embed_texts_batch([])
        self.assertIsNotNone(results)
        self.assertEqual(len(results), 0)

    def test_handles_individual_failures(self):
        """If one embed_text call fails, others still proceed."""
        embedder = DummyEmbedder384()

        # Patch embed_text to fail on second call
        original = embedder.embed_text
        call_count = [0]

        def flaky_embed(text, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                raise ValueError("Transient error")
            return original(text, **kwargs)

        embedder.embed_text = flaky_embed
        results = embedder.embed_texts_batch(["a", "b", "c"])

        self.assertEqual(len(results), 3)
        self.assertIsNotNone(results[0])
        self.assertIsNone(results[1])  # Failed
        self.assertIsNotNone(results[2])


def _make_mock_annotation(annot_id, raw_text, content_modalities=None):
    """Create a mock annotation object."""
    annot = MagicMock()
    annot.id = annot_id
    annot.pk = annot_id
    annot.raw_text = raw_text
    annot.content_modalities = content_modalities or [ContentModality.TEXT.value]
    annot.add_embedding = MagicMock(return_value=MagicMock())
    return annot


class TestBatchEmbedTextAnnotations(unittest.TestCase):
    """Test _batch_embed_text_annotations helper function."""

    def _make_result(self):
        return {"succeeded": 0, "failed": 0, "skipped": 0, "errors": []}

    def test_basic_batch(self):
        """All annotations embedded successfully."""
        annots = [
            _make_mock_annotation(1, "Hello world"),
            _make_mock_annotation(2, "Second text"),
            _make_mock_annotation(3, "Third text"),
        ]
        embedder = DummyEmbedder384()
        result = self._make_result()

        _batch_embed_text_annotations(
            annots, embedder, "test.DummyEmbedder384", 50, result
        )

        self.assertEqual(result["succeeded"], 3)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["skipped"], 0)

    def test_empty_text_skipped(self):
        """Annotations with empty/whitespace text are skipped."""
        annots = [
            _make_mock_annotation(1, "Hello"),
            _make_mock_annotation(2, ""),
            _make_mock_annotation(3, "   "),
        ]
        embedder = DummyEmbedder384()
        result = self._make_result()

        _batch_embed_text_annotations(
            annots, embedder, "test.DummyEmbedder384", 50, result
        )

        self.assertEqual(result["succeeded"], 1)
        self.assertEqual(result["skipped"], 2)

    def test_sub_batching(self):
        """Large annotation lists are split into sub-batches."""
        annots = [_make_mock_annotation(i, f"Text {i}") for i in range(10)]
        embedder = DummyEmbedder384()
        result = self._make_result()

        # Use api_batch_size=3 to force multiple sub-batches
        with patch.object(
            embedder, "embed_texts_batch", wraps=embedder.embed_texts_batch
        ) as mock_batch:
            _batch_embed_text_annotations(
                annots, embedder, "test.DummyEmbedder384", 3, result
            )
            # 10 annotations / 3 per batch = 4 calls (3+3+3+1)
            self.assertEqual(mock_batch.call_count, 4)

        self.assertEqual(result["succeeded"], 10)

    def test_batch_api_failure(self):
        """When embed_texts_batch raises, all annotations in that chunk fail."""
        annots = [_make_mock_annotation(i, f"Text {i}") for i in range(3)]
        embedder = FailingBatchEmbedder()
        result = self._make_result()

        _batch_embed_text_annotations(annots, embedder, "test.FailingBatch", 50, result)

        self.assertEqual(result["failed"], 3)
        self.assertEqual(result["succeeded"], 0)

    def test_batch_returns_none(self):
        """When embed_texts_batch returns None, all annotations in chunk fail."""
        annots = [_make_mock_annotation(i, f"Text {i}") for i in range(3)]
        embedder = NullBatchEmbedder()
        result = self._make_result()

        _batch_embed_text_annotations(annots, embedder, "test.NullBatch", 50, result)

        self.assertEqual(result["failed"], 3)

    def test_partial_vector_failures(self):
        """Individual None vectors in batch result are handled per-annotation."""
        annots = [_make_mock_annotation(i, f"Text {i}") for i in range(4)]
        embedder = PartialFailBatchEmbedder()
        result = self._make_result()

        _batch_embed_text_annotations(annots, embedder, "test.PartialFail", 50, result)

        # Even indices (0, 2) return None -> failed; odd (1, 3) succeed
        self.assertEqual(result["succeeded"], 2)
        self.assertEqual(result["failed"], 2)

    def test_add_embedding_failure(self):
        """When add_embedding raises, the annotation is marked as failed."""
        annot = _make_mock_annotation(1, "Some text")
        annot.add_embedding.side_effect = Exception("DB error")

        embedder = DummyEmbedder384()
        result = self._make_result()

        _batch_embed_text_annotations(
            [annot], embedder, "test.DummyEmbedder384", 50, result
        )

        self.assertEqual(result["failed"], 1)
        self.assertEqual(len(result["errors"]), 1)
        self.assertIn("store failed", result["errors"][0])

    def test_vector_count_mismatch(self):
        """When embedder returns fewer vectors than texts, entire chunk fails."""
        annots = [_make_mock_annotation(i, f"Text {i}") for i in range(3)]
        embedder = MismatchCountEmbedder()
        result = self._make_result()

        _batch_embed_text_annotations(
            annots, embedder, "test.MismatchCount", 50, result
        )

        self.assertEqual(result["failed"], 3)
        self.assertEqual(result["succeeded"], 0)
        for error in result["errors"]:
            self.assertIn("vector count mismatch", error)

    def test_transient_timeout_propagates(self):
        """requests.Timeout from embed_texts_batch propagates for Celery retry."""

        class TimeoutEmbedder(DummyEmbedder384):
            def embed_texts_batch(self, texts, **kw):
                raise requests.exceptions.Timeout("timed out")

        annots = [_make_mock_annotation(1, "Hello")]
        result = self._make_result()

        with self.assertRaises(requests.exceptions.Timeout):
            _batch_embed_text_annotations(
                annots, TimeoutEmbedder(), "test.TimeoutEmbedder", 50, result
            )

    def test_transient_connection_error_propagates(self):
        """requests.ConnectionError from embed_texts_batch propagates for retry."""

        class ConnErrorEmbedder(DummyEmbedder384):
            def embed_texts_batch(self, texts, **kw):
                raise requests.exceptions.ConnectionError("refused")

        annots = [_make_mock_annotation(1, "Hello")]
        result = self._make_result()

        with self.assertRaises(requests.exceptions.ConnectionError):
            _batch_embed_text_annotations(
                annots, ConnErrorEmbedder(), "test.ConnErrorEmbedder", 50, result
            )

    def test_transient_server_error_propagates(self):
        """EmbeddingServerError from embed_texts_batch propagates for retry."""

        class ServerErrorEmbedder(DummyEmbedder384):
            def embed_texts_batch(self, texts, **kw):
                raise EmbeddingServerError("503 Service Unavailable")

        annots = [_make_mock_annotation(1, "Hello")]
        result = self._make_result()

        with self.assertRaises(EmbeddingServerError):
            _batch_embed_text_annotations(
                annots, ServerErrorEmbedder(), "test.ServerErrorEmbedder", 50, result
            )

    def test_client_error_recorded_as_permanent_failure(self):
        """EmbeddingClientError from embed_texts_batch is caught and recorded.

        Unlike 5xx (which re-raises to trigger Celery retry), 4xx errors are
        caught inside the batch helper and recorded as permanent per-annotation
        failures. This prevents retries from burning on invalid input that will
        never succeed, while still surfacing the failure in ``result["errors"]``.
        """

        class ClientErrorEmbedder(DummyEmbedder384):
            def embed_texts_batch(self, texts, **kw):
                raise EmbeddingClientError("400 Bad Request")

        annots = [_make_mock_annotation(i, f"Text {i}") for i in range(3)]
        result = self._make_result()

        # Should NOT raise — client errors are swallowed.
        _batch_embed_text_annotations(
            annots, ClientErrorEmbedder(), "test.ClientErrorEmbedder", 50, result
        )

        self.assertEqual(result["failed"], 3)
        self.assertEqual(result["succeeded"], 0)
        self.assertEqual(len(result["errors"]), 3)
        for error in result["errors"]:
            self.assertIn("client error (4xx)", error)


class TestMicroserviceEmbedderBatch(unittest.TestCase):
    """Test MicroserviceEmbedder.embed_texts_batch with mocked HTTP calls."""

    def _make_embedder(self):
        """Create a MicroserviceEmbedder with settings populated.

        Directly sets ``_settings`` because PipelineComponentBase normally
        loads settings from the database via ``get_component_settings()``,
        which is unavailable in unit tests without Django.
        """
        embedder = MicroserviceEmbedder()
        embedder._settings = MicroserviceEmbedder.Settings(
            embeddings_microservice_url="http://test-service:8080",
        )
        return embedder

    def _mock_response(self, status_code, embeddings=None):
        """Create a mock requests.Response."""
        resp = MagicMock()
        resp.status_code = status_code
        if embeddings is not None:
            resp.json.return_value = {"embeddings": embeddings}
        return resp

    @patch(
        "opencontractserver.pipeline.embedders.sent_transformer_microservice.requests.post"
    )
    def test_successful_batch(self, mock_post):
        """Successful batch returns list of vectors."""
        embedder = self._make_embedder()
        vectors = np.array([[0.1] * 384, [0.2] * 384]).tolist()
        mock_post.return_value = self._mock_response(200, vectors)

        result = embedder.embed_texts_batch(["hello", "world"])

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 2)
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        self.assertIn("/embeddings/batch", call_kwargs[0][0])

    @patch(
        "opencontractserver.pipeline.embedders.sent_transformer_microservice.requests.post"
    )
    def test_client_error_raises(self, mock_post):
        """4xx response raises EmbeddingClientError.

        Batch methods raise EmbeddingClientError on 4xx so callers can
        distinguish a client-side failure ("we sent bad data") from a
        parsing error that still returns None. The batch task helper
        swallows it and records permanent per-annotation failures
        without triggering Celery retry.
        """
        embedder = self._make_embedder()
        mock_post.return_value = self._mock_response(400)

        with self.assertRaises(EmbeddingClientError):
            embedder.embed_texts_batch(["hello"])

    @patch(
        "opencontractserver.pipeline.embedders.sent_transformer_microservice.requests.post"
    )
    def test_server_error_raises(self, mock_post):
        """5xx response raises EmbeddingServerError for Celery retry."""
        embedder = self._make_embedder()
        mock_post.return_value = self._mock_response(500)

        with self.assertRaises(EmbeddingServerError):
            embedder.embed_texts_batch(["hello"])

    @patch(
        "opencontractserver.pipeline.embedders.sent_transformer_microservice.requests.post"
    )
    def test_non_retriable_exception_returns_none(self, mock_post):
        """Non-retriable exception (e.g., builtin ConnectionError) returns None."""
        embedder = self._make_embedder()
        mock_post.side_effect = ConnectionError("Connection refused")

        result = embedder.embed_texts_batch(["hello"])

        self.assertIsNone(result)

    @patch(
        "opencontractserver.pipeline.embedders.sent_transformer_microservice.requests.post"
    )
    def test_timeout_raises_for_retry(self, mock_post):
        """requests.Timeout re-raises for Celery retry."""
        embedder = self._make_embedder()
        mock_post.side_effect = requests.exceptions.Timeout("timed out")

        with self.assertRaises(requests.exceptions.Timeout):
            embedder.embed_texts_batch(["hello"])

    @patch(
        "opencontractserver.pipeline.embedders.sent_transformer_microservice.requests.post"
    )
    def test_connection_error_raises_for_retry(self, mock_post):
        """requests.ConnectionError re-raises for Celery retry."""
        embedder = self._make_embedder()
        mock_post.side_effect = requests.exceptions.ConnectionError("refused")

        with self.assertRaises(requests.exceptions.ConnectionError):
            embedder.embed_texts_batch(["hello"])

    def test_exceeding_max_batch_size_raises(self):
        """Exceeding max batch size raises ValueError."""
        embedder = self._make_embedder()
        texts = [f"text {i}" for i in range(MICROSERVICE_EMBEDDER_MAX_BATCH_SIZE + 1)]

        with self.assertRaises(ValueError) as ctx:
            embedder.embed_texts_batch(texts)
        self.assertIn("exceeds maximum", str(ctx.exception))

    def test_empty_list_returns_empty(self):
        """Empty input returns empty list without HTTP call."""
        embedder = self._make_embedder()
        result = embedder.embed_texts_batch([])
        self.assertEqual(result, [])

    def test_no_service_url_returns_none(self):
        """Missing service URL returns None."""
        embedder = MicroserviceEmbedder()
        embedder._settings = MicroserviceEmbedder.Settings(
            embeddings_microservice_url="",
        )
        result = embedder.embed_texts_batch(["hello"])
        self.assertIsNone(result)

    @patch(
        "opencontractserver.pipeline.embedders.sent_transformer_microservice.requests.post"
    )
    def test_3d_response_squeezed(self, mock_post):
        """3D response array is squeezed to 2D."""
        embedder = self._make_embedder()
        # Some services return 3D: [[[0.1, 0.2, ...]], [[0.3, 0.4, ...]]]
        vectors_3d = [[[0.1] * 384], [[0.2] * 384]]
        mock_post.return_value = self._mock_response(200, vectors_3d)

        result = embedder.embed_texts_batch(["a", "b"])

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 2)
        self.assertEqual(len(result[0]), 384)

    @patch(
        "opencontractserver.pipeline.embedders.sent_transformer_microservice.requests.post"
    )
    def test_vector_count_mismatch_returns_none(self, mock_post):
        """Mismatched vector count returns None."""
        embedder = self._make_embedder()
        # Send 3 texts but return only 2 vectors
        vectors = np.array([[0.1] * 384, [0.2] * 384]).tolist()
        mock_post.return_value = self._mock_response(200, vectors)

        result = embedder.embed_texts_batch(["a", "b", "c"])

        self.assertIsNone(result)

    @patch(
        "opencontractserver.pipeline.embedders.sent_transformer_microservice.requests.post"
    )
    def test_malformed_200_missing_embeddings_key(self, mock_post):
        """200 response missing 'embeddings' key returns None."""
        embedder = self._make_embedder()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"vectors": [[0.1] * 384]}  # wrong key
        mock_post.return_value = resp

        result = embedder.embed_texts_batch(["hello"])

        self.assertIsNone(result)

    @patch(
        "opencontractserver.pipeline.embedders.sent_transformer_microservice.requests.post"
    )
    def test_nan_values_handled_per_item(self, mock_post):
        """NaN values in individual embeddings return None for those items only."""
        embedder = self._make_embedder()
        vec_good = [0.1] * 384
        vec_nan = [float("nan")] * 384
        vectors = [vec_good, vec_nan, vec_good]
        mock_post.return_value = self._mock_response(200, vectors)

        result = embedder.embed_texts_batch(["a", "b", "c"])

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 3)
        self.assertIsNotNone(result[0])
        self.assertIsNone(result[1])  # NaN item
        self.assertIsNotNone(result[2])


class TestMicroserviceEmbedderSingleText(unittest.TestCase):
    """Test MicroserviceEmbedder._embed_text_impl and _get_service_config."""

    def _make_embedder(self, api_key="", use_cloud_run=False):
        embedder = MicroserviceEmbedder()
        embedder._settings = MicroserviceEmbedder.Settings(
            embeddings_microservice_url="http://test-service:8080",
            vector_embedder_api_key=api_key,
            use_cloud_run_iam_auth=use_cloud_run,
        )
        return embedder

    def _mock_response(self, status_code, embeddings=None, body=None):
        resp = MagicMock()
        resp.status_code = status_code
        if body is not None:
            resp.json.return_value = body
        elif embeddings is not None:
            resp.json.return_value = {"embeddings": embeddings}
        return resp

    @patch(
        "opencontractserver.pipeline.embedders.sent_transformer_microservice.requests.post"
    )
    def test_embed_text_success_1d(self, mock_post):
        """Successful single-text embedding with 1D response."""
        embedder = self._make_embedder()
        vector = [0.1] * 384
        mock_post.return_value = self._mock_response(200, vector)

        result = embedder.embed_text("hello")

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 384)
        mock_post.assert_called_once()

    @patch(
        "opencontractserver.pipeline.embedders.sent_transformer_microservice.requests.post"
    )
    def test_embed_text_success_2d(self, mock_post):
        """Successful single-text embedding with 2D response."""
        embedder = self._make_embedder()
        vector = [[0.1] * 384]
        mock_post.return_value = self._mock_response(200, vector)

        result = embedder.embed_text("hello")

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 384)

    @patch(
        "opencontractserver.pipeline.embedders.sent_transformer_microservice.requests.post"
    )
    def test_embed_text_malformed_200(self, mock_post):
        """200 response missing 'embeddings' key returns None."""
        embedder = self._make_embedder()
        mock_post.return_value = self._mock_response(200, body={"result": "ok"})

        result = embedder.embed_text("hello")

        self.assertIsNone(result)

    @patch(
        "opencontractserver.pipeline.embedders.sent_transformer_microservice.requests.post"
    )
    def test_embed_text_nan_returns_none(self, mock_post):
        """NaN in single-text response returns None."""
        embedder = self._make_embedder()
        mock_post.return_value = self._mock_response(200, [float("nan")] * 384)

        result = embedder.embed_text("hello")

        self.assertIsNone(result)

    @patch(
        "opencontractserver.pipeline.embedders.sent_transformer_microservice.requests.post"
    )
    def test_embed_text_client_error(self, mock_post):
        """4xx response returns None."""
        embedder = self._make_embedder()
        mock_post.return_value = self._mock_response(422)

        result = embedder.embed_text("hello")

        self.assertIsNone(result)

    @patch(
        "opencontractserver.pipeline.embedders.sent_transformer_microservice.requests.post"
    )
    def test_embed_text_server_error(self, mock_post):
        """5xx response returns None."""
        embedder = self._make_embedder()
        mock_post.return_value = self._mock_response(503)

        result = embedder.embed_text("hello")

        self.assertIsNone(result)

    @patch(
        "opencontractserver.pipeline.embedders.sent_transformer_microservice.requests.post"
    )
    def test_embed_text_exception(self, mock_post):
        """Network exception returns None."""
        embedder = self._make_embedder()
        mock_post.side_effect = ConnectionError("timeout")

        result = embedder.embed_text("hello")

        self.assertIsNone(result)

    def test_get_service_config_with_api_key(self):
        """API key is included in headers when provided."""
        embedder = self._make_embedder(api_key="test-key-123")
        url, headers = embedder._get_service_config(
            {"embeddings_microservice_url": "http://test:8080"}
        )
        self.assertEqual(headers["X-API-Key"], "test-key-123")

    def test_get_service_config_without_api_key(self):
        """No API key header when key is empty."""
        embedder = self._make_embedder()
        url, headers = embedder._get_service_config(
            {"embeddings_microservice_url": "http://test:8080"}
        )
        self.assertNotIn("X-API-Key", headers)
        self.assertEqual(url, "http://test:8080")

    def test_get_service_config_kwargs_override(self):
        """Kwargs override settings values."""
        embedder = self._make_embedder()
        url, headers = embedder._get_service_config(
            {"embeddings_microservice_url": "http://override:9090"}
        )
        self.assertEqual(url, "http://override:9090")

    def test_get_service_config_fallback_to_settings(self):
        """Falls back to settings when kwargs don't provide overrides."""
        embedder = self._make_embedder()
        url, headers = embedder._get_service_config({})
        self.assertEqual(url, "http://test-service:8080")


class TestCalculateEmbeddingsForAnnotationBatch(unittest.TestCase):
    """Integration tests for the calculate_embeddings_for_annotation_batch task.

    Note: These tests call the task function directly (not via Celery) so
    ``self`` (the bound task instance) is not injected.  Paths that use
    ``self.retry()`` or ``self.update_state()`` are therefore untested here;
    the current batch path does not use those APIs.
    """

    def _mock_objects(self, annotations):
        """Build a mock manager whose select_related().filter() yields annotations."""
        mock_qs = MagicMock()
        mock_qs.filter.return_value = mock_qs
        mock_qs.__iter__ = lambda self_: iter(annotations)

        mock_mgr = MagicMock()
        mock_mgr.select_related.return_value = mock_qs
        return mock_mgr

    @patch("opencontractserver.tasks.embeddings_task.get_component_by_name")
    @patch("opencontractserver.tasks.embeddings_task.Annotation")
    def test_batch_path_text_only(self, mock_ann_cls, mock_get_component):
        """Explicit embedder_path routes text-only annotations through batch path."""
        annots = [
            _make_mock_annotation(1, "Hello world"),
            _make_mock_annotation(2, "Second text"),
        ]
        mock_ann_cls.objects = self._mock_objects(annots)
        mock_get_component.return_value = DummyEmbedder384

        result = calculate_embeddings_for_annotation_batch(
            annotation_ids=[1, 2],
            embedder_path="test.DummyEmbedder384",
        )

        self.assertEqual(result["total"], 2)
        self.assertEqual(result["succeeded"], 2)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["skipped"], 0)
        for annot in annots:
            annot.add_embedding.assert_called_once()

    @patch("opencontractserver.tasks.embeddings_task.get_component_by_name")
    def test_batch_path_empty_ids(self, mock_get_component):
        """Empty annotation_ids returns immediately with zero counts."""
        result = calculate_embeddings_for_annotation_batch(
            annotation_ids=[],
            embedder_path="test.DummyEmbedder384",
        )

        self.assertEqual(result["total"], 0)
        self.assertEqual(result["succeeded"], 0)
        mock_get_component.assert_not_called()

    @patch("opencontractserver.tasks.embeddings_task.get_component_by_name")
    @patch("opencontractserver.tasks.embeddings_task.Annotation")
    def test_batch_path_missing_annotations(self, mock_ann_cls, mock_get_component):
        """Annotations not found in DB are counted as skipped."""
        annot1 = _make_mock_annotation(1, "Hello")
        mock_ann_cls.objects = self._mock_objects([annot1])
        mock_get_component.return_value = DummyEmbedder384

        result = calculate_embeddings_for_annotation_batch(
            annotation_ids=[1, 2, 3],
            embedder_path="test.DummyEmbedder384",
        )

        self.assertEqual(result["total"], 3)
        self.assertEqual(result["succeeded"], 1)
        self.assertEqual(result["skipped"], 2)

    @patch("opencontractserver.tasks.embeddings_task.get_component_by_name")
    @patch("opencontractserver.tasks.embeddings_task.Annotation")
    def test_batch_path_embedder_load_failure(self, mock_ann_cls, mock_get_component):
        """Failing to load the embedder class fails all annotations."""
        mock_get_component.side_effect = ImportError("Module not found")

        result = calculate_embeddings_for_annotation_batch(
            annotation_ids=[1, 2],
            embedder_path="nonexistent.Embedder",
        )

        self.assertEqual(result["total"], 2)
        self.assertEqual(result["failed"], 2)
        self.assertIn("Failed to load embedder", result["errors"][0])

    @patch("opencontractserver.tasks.embeddings_task.get_component_by_name")
    @patch("opencontractserver.tasks.embeddings_task.Annotation")
    def test_batch_path_with_batch_failure(self, mock_ann_cls, mock_get_component):
        """Batch embed failure marks all annotations as failed."""
        annots = [_make_mock_annotation(i, f"Text {i}") for i in range(3)]
        mock_ann_cls.objects = self._mock_objects(annots)
        mock_get_component.return_value = FailingBatchEmbedder

        result = calculate_embeddings_for_annotation_batch(
            annotation_ids=[0, 1, 2],
            embedder_path="test.FailingBatchEmbedder",
        )

        self.assertEqual(result["total"], 3)
        self.assertEqual(result["failed"], 3)
        self.assertEqual(result["succeeded"], 0)

    @patch("opencontractserver.tasks.embeddings_task.get_component_by_name")
    @patch("opencontractserver.tasks.embeddings_task.Annotation")
    def test_batch_path_valueerror_fails_fast(self, mock_ann_cls, mock_get_component):
        """ValueError from contract violation fails immediately without retry."""

        class RaisingEmbedder(DummyEmbedder384):
            def embed_texts_batch(self, texts, **kw):
                raise ValueError("Batch size exceeds maximum")

        annots = [_make_mock_annotation(i, f"Text {i}") for i in range(3)]
        mock_ann_cls.objects = self._mock_objects(annots)
        mock_get_component.return_value = RaisingEmbedder

        result = calculate_embeddings_for_annotation_batch(
            annotation_ids=[0, 1, 2],
            embedder_path="test.RaisingEmbedder",
        )

        self.assertEqual(result["total"], 3)
        self.assertEqual(result["failed"], 3)
        self.assertTrue(
            any("Contract violation" in e for e in result["errors"]),
            f"Expected 'Contract violation' in errors: {result['errors']}",
        )

    @patch("opencontractserver.tasks.embeddings_task._create_embedding_for_annotation")
    @patch("opencontractserver.tasks.embeddings_task.get_component_by_name")
    @patch("opencontractserver.tasks.embeddings_task.Annotation")
    def test_multimodal_partition_path(
        self, mock_ann_cls, mock_get_component, mock_create_embed
    ):
        """Multimodal embedder partitions annotations into text-only batch + individual multimodal."""

        class MultimodalDummyEmbedder(DummyEmbedder384):
            """Embedder that advertises multimodal support.

            NOTE: Uses class-attribute overrides for test brevity.
            Production embedders should instead set
            ``supported_modalities = {ContentModality.TEXT, ContentModality.IMAGE}``
            so that ``is_multimodal`` / ``supports_images`` are derived automatically.
            """

            is_multimodal = True
            supports_images = True

        text_annot_1 = _make_mock_annotation(1, "Pure text annotation")
        text_annot_2 = _make_mock_annotation(2, "Another text annotation")
        image_annot = _make_mock_annotation(
            3,
            "Annotation with image",
            content_modalities=[
                ContentModality.TEXT.value,
                ContentModality.IMAGE.value,
            ],
        )

        all_annots = [text_annot_1, text_annot_2, image_annot]
        mock_ann_cls.objects = self._mock_objects(all_annots)
        mock_get_component.return_value = MultimodalDummyEmbedder
        mock_create_embed.return_value = True

        result = calculate_embeddings_for_annotation_batch(
            annotation_ids=[1, 2, 3],
            embedder_path="test.MultimodalDummyEmbedder",
        )

        self.assertEqual(result["total"], 3)
        self.assertEqual(result["succeeded"], 3)
        self.assertEqual(result["failed"], 0)

        # Text-only annotations should go through batch path (add_embedding called)
        text_annot_1.add_embedding.assert_called_once()
        text_annot_2.add_embedding.assert_called_once()

        # Multimodal annotation should go through _create_embedding_for_annotation
        mock_create_embed.assert_called_once()
        call_args = mock_create_embed.call_args
        self.assertEqual(call_args[0][0], image_annot)
        self.assertEqual(call_args[0][2], "test.MultimodalDummyEmbedder")

    @patch("opencontractserver.tasks.embeddings_task._create_embedding_for_annotation")
    @patch("opencontractserver.tasks.embeddings_task.get_component_by_name")
    @patch("opencontractserver.tasks.embeddings_task.Annotation")
    def test_multimodal_partition_individual_failure(
        self, mock_ann_cls, mock_get_component, mock_create_embed
    ):
        """Multimodal annotation failure is recorded without failing text-only annotations."""

        class MultimodalDummyEmbedder(DummyEmbedder384):
            # Class-attribute overrides for test brevity; see note in
            # test_multimodal_partition_path for production guidance.
            is_multimodal = True
            supports_images = True

        text_annot = _make_mock_annotation(1, "Pure text")
        image_annot = _make_mock_annotation(
            2,
            "Image annotation",
            content_modalities=[ContentModality.IMAGE.value],
        )

        mock_ann_cls.objects = self._mock_objects([text_annot, image_annot])
        mock_get_component.return_value = MultimodalDummyEmbedder
        mock_create_embed.return_value = False  # Multimodal embedding fails

        result = calculate_embeddings_for_annotation_batch(
            annotation_ids=[1, 2],
            embedder_path="test.MultimodalDummyEmbedder",
        )

        self.assertEqual(result["total"], 2)
        self.assertEqual(result["succeeded"], 1)  # text-only succeeded
        self.assertEqual(result["failed"], 1)  # multimodal failed
        text_annot.add_embedding.assert_called_once()

    @patch("opencontractserver.tasks.embeddings_task.get_component_by_name")
    @patch("opencontractserver.tasks.embeddings_task.Annotation")
    def test_transient_error_propagates_to_task(self, mock_ann_cls, mock_get_component):
        """EmbeddingServerError escapes the full task for Celery retry.

        _batch_embed_text_annotations re-raises transient errors, and
        calculate_embeddings_for_annotation_batch must NOT catch them so
        that the Celery autoretry_for=(Exception,) decorator can fire.
        """

        class RetriableEmbedder(DummyEmbedder384):
            def embed_texts_batch(self, texts, **kw):
                raise EmbeddingServerError("503 from upstream")

        annots = [_make_mock_annotation(1, "Hello")]
        mock_ann_cls.objects = self._mock_objects(annots)
        mock_get_component.return_value = RetriableEmbedder

        with self.assertRaises(EmbeddingServerError):
            calculate_embeddings_for_annotation_batch(
                annotation_ids=[1],
                embedder_path="test.RetriableEmbedder",
            )

    @patch("opencontractserver.tasks.embeddings_task.get_component_by_name")
    @patch("opencontractserver.tasks.embeddings_task.Annotation")
    def test_transient_timeout_propagates_to_task(
        self, mock_ann_cls, mock_get_component
    ):
        """requests.Timeout escapes the full task for Celery retry."""

        class TimeoutEmbedder(DummyEmbedder384):
            def embed_texts_batch(self, texts, **kw):
                raise requests.exceptions.Timeout("timed out")

        annots = [_make_mock_annotation(1, "Hello")]
        mock_ann_cls.objects = self._mock_objects(annots)
        mock_get_component.return_value = TimeoutEmbedder

        with self.assertRaises(requests.exceptions.Timeout):
            calculate_embeddings_for_annotation_batch(
                annotation_ids=[1],
                embedder_path="test.TimeoutEmbedder",
            )

    @patch("opencontractserver.tasks.embeddings_task._apply_dual_embedding_strategy")
    @patch("opencontractserver.tasks.embeddings_task.Annotation")
    def test_dual_strategy_path(self, mock_ann_cls, mock_dual_strategy):
        """Without explicit embedder_path, uses dual embedding strategy."""
        annot = _make_mock_annotation(1, "Hello")
        annot.corpus_id = 10
        mock_ann_cls.objects = self._mock_objects([annot])

        result = calculate_embeddings_for_annotation_batch(
            annotation_ids=[1],
            corpus_id=10,
            embedder_path=None,
        )

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["succeeded"], 1)
        mock_dual_strategy.assert_called_once()

    @patch("opencontractserver.tasks.embeddings_task._apply_dual_embedding_strategy")
    @patch("opencontractserver.tasks.embeddings_task.Annotation")
    def test_dual_strategy_path_failure(self, mock_ann_cls, mock_dual_strategy):
        """Dual strategy exception marks annotation as failed."""
        annot = _make_mock_annotation(1, "Hello")
        annot.corpus_id = 10
        mock_ann_cls.objects = self._mock_objects([annot])
        mock_dual_strategy.side_effect = RuntimeError("Embedder crashed")

        result = calculate_embeddings_for_annotation_batch(
            annotation_ids=[1],
            corpus_id=10,
            embedder_path=None,
        )

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["failed"], 1)
        self.assertIn("Embedder crashed", result["errors"][0])
