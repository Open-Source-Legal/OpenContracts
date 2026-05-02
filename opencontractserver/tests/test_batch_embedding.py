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

    def test_concurrent_sub_batches_fire_in_parallel(self):
        """When ``embed_max_concurrent_sub_batches > 1``, sub-batches run in parallel.

        Asserted by checking that the second sub-batch's embed call
        starts before the first one's call returns. We use a barrier
        with a strict timeout so a serial implementation would deadlock
        and the test would fail.
        """
        import threading

        annots = [_make_mock_annotation(i, f"Text {i}") for i in range(6)]

        class ParallelEmbedder(DummyEmbedder384):
            embed_max_concurrent_sub_batches = 4

        embedder = ParallelEmbedder()
        result = self._make_result()

        barrier = threading.Barrier(parties=2, timeout=5)

        def slow_batch(texts, **kw):
            # Block until a peer thread has also entered this method.
            # If sub-batches ran serially, the second thread never
            # arrives and ``barrier.wait()`` raises BrokenBarrierError.
            barrier.wait()
            return [[0.1] * 384] * len(texts)

        embedder.embed_texts_batch = slow_batch  # type: ignore[assignment]

        # api_batch_size=3 → exactly 2 sub-batches over 6 annotations.
        _batch_embed_text_annotations(
            annots, embedder, "test.ParallelEmbedder", 3, result
        )

        self.assertEqual(result["succeeded"], 6)
        self.assertEqual(result["failed"], 0)

    def test_serial_when_concurrency_is_1(self):
        """Default (serial) path remains intact when concurrency=1."""
        annots = [_make_mock_annotation(i, f"Text {i}") for i in range(6)]
        embedder = DummyEmbedder384()  # default embed_max_concurrent_sub_batches=1
        result = self._make_result()

        _batch_embed_text_annotations(
            annots, embedder, "test.DummyEmbedder384", 3, result
        )

        self.assertEqual(result["succeeded"], 6)

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

    def test_transient_error_does_not_block_on_in_flight_peers(self):
        """Transient HTTP errors short-circuit the executor (issue #1410).

        With ``max_workers > 1`` and a slow peer sub-batch, the previous
        implementation would let the executor's default
        ``shutdown(wait=True, cancel_futures=False)`` block until every
        in-flight peer round-trip finished. The fix re-raises *outside*
        the ``with`` block after explicitly calling
        ``shutdown(wait=False, cancel_futures=True)``.

        The test fans out 4 sub-batches: index 0 raises ``Timeout``
        immediately; the remaining 3 each block on a ``threading.Event``
        that the test never sets. A correct implementation propagates
        the ``Timeout`` quickly (well under the per-call hang); a
        regression would hang until the wait timeout below kicks in.
        """
        import threading
        import time

        never_release = threading.Event()
        call_started = threading.Event()
        # Track whether peer sub-batches were ever cancelled (i.e. never called).
        peer_call_count = [0]

        class FastFailThenBlockEmbedder(DummyEmbedder384):
            embed_max_concurrent_sub_batches = 4
            _calls = [0]
            _calls_lock = threading.Lock()

            def embed_texts_batch(self, texts, **kw):
                with self._calls_lock:
                    self._calls[0] += 1
                    nth = self._calls[0]
                if nth == 1:
                    # First in -> trigger the fast-fail path.
                    call_started.set()
                    raise requests.exceptions.Timeout("simulated timeout")
                # Peer sub-batches: count the call so we can assert that
                # at least one peer started before being abandoned, then
                # block until the test releases (or we time out trying).
                with self._calls_lock:
                    peer_call_count[0] += 1
                # Cap the block at a generous bound so a regression times
                # out the test rather than hanging the whole suite.
                released = never_release.wait(timeout=10.0)
                if not released:
                    return [[0.1] * 384] * len(texts)
                return [[0.1] * 384] * len(texts)

        # 4 sub-batches with api_batch_size=1.
        annots = [_make_mock_annotation(i, f"Text {i}") for i in range(4)]
        result = self._make_result()

        embedder = FastFailThenBlockEmbedder()

        deadline_seconds = 5.0
        start = time.monotonic()
        with self.assertRaises(requests.exceptions.Timeout):
            _batch_embed_text_annotations(
                annots, embedder, "test.FastFailThenBlockEmbedder", 1, result
            )
        elapsed = time.monotonic() - start

        # Always release peers so daemon threads exit cleanly.
        never_release.set()

        # Confirm the first sub-batch actually fired before checking the
        # timing — otherwise a regression that never schedules sub-batch 0
        # would silently pass the elapsed-time check.
        self.assertTrue(
            call_started.is_set(),
            msg="first sub-batch never started; timing assertion would be vacuous",
        )

        # The fast-fail path must complete well inside the 10s peer
        # block. A regression that waits on in-flight peers would take
        # ~10s; we give a generous 5s headroom over scheduling jitter.
        self.assertLess(
            elapsed,
            deadline_seconds,
            msg=(
                f"Fast-fail path took {elapsed:.2f}s; expected < "
                f"{deadline_seconds}s. Executor likely waited on in-flight peers."
            ),
        )

        # At least one peer sub-batch entered ``embed_texts_batch`` before
        # being abandoned — otherwise the executor cancelled every queued
        # sub-batch and the test no longer exercises the in-flight path.
        self.assertGreater(
            peer_call_count[0],
            0,
            msg="no peer sub-batches started; in-flight fast-fail path not exercised",
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

    @patch("requests.Session.post")
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

    @patch("requests.Session.post")
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

    @patch("requests.Session.post")
    def test_server_error_raises(self, mock_post):
        """5xx response raises EmbeddingServerError for Celery retry."""
        embedder = self._make_embedder()
        mock_post.return_value = self._mock_response(500)

        with self.assertRaises(EmbeddingServerError):
            embedder.embed_texts_batch(["hello"])

    @patch("requests.Session.post")
    def test_non_retriable_exception_returns_none(self, mock_post):
        """Non-retriable exception (e.g., builtin ConnectionError) returns None."""
        embedder = self._make_embedder()
        mock_post.side_effect = ConnectionError("Connection refused")

        result = embedder.embed_texts_batch(["hello"])

        self.assertIsNone(result)

    @patch("requests.Session.post")
    def test_timeout_raises_for_retry(self, mock_post):
        """requests.Timeout re-raises for Celery retry."""
        embedder = self._make_embedder()
        mock_post.side_effect = requests.exceptions.Timeout("timed out")

        with self.assertRaises(requests.exceptions.Timeout):
            embedder.embed_texts_batch(["hello"])

    @patch("requests.Session.post")
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

    @patch("requests.Session.post")
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

    @patch("requests.Session.post")
    def test_vector_count_mismatch_returns_none(self, mock_post):
        """Mismatched vector count returns None."""
        embedder = self._make_embedder()
        # Send 3 texts but return only 2 vectors
        vectors = np.array([[0.1] * 384, [0.2] * 384]).tolist()
        mock_post.return_value = self._mock_response(200, vectors)

        result = embedder.embed_texts_batch(["a", "b", "c"])

        self.assertIsNone(result)

    @patch("requests.Session.post")
    def test_malformed_200_missing_embeddings_key(self, mock_post):
        """200 response missing 'embeddings' key returns None."""
        embedder = self._make_embedder()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"vectors": [[0.1] * 384]}  # wrong key
        mock_post.return_value = resp

        result = embedder.embed_texts_batch(["hello"])

        self.assertIsNone(result)

    @patch("requests.Session.post")
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

    @patch("requests.Session.post")
    def test_embed_text_success_1d(self, mock_post):
        """Successful single-text embedding with 1D response."""
        embedder = self._make_embedder()
        vector = [0.1] * 384
        mock_post.return_value = self._mock_response(200, vector)

        result = embedder.embed_text("hello")

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 384)
        mock_post.assert_called_once()

    @patch("requests.Session.post")
    def test_embed_text_success_2d(self, mock_post):
        """Successful single-text embedding with 2D response."""
        embedder = self._make_embedder()
        vector = [[0.1] * 384]
        mock_post.return_value = self._mock_response(200, vector)

        result = embedder.embed_text("hello")

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 384)

    @patch("requests.Session.post")
    def test_embed_text_malformed_200(self, mock_post):
        """200 response missing 'embeddings' key returns None."""
        embedder = self._make_embedder()
        mock_post.return_value = self._mock_response(200, body={"result": "ok"})

        result = embedder.embed_text("hello")

        self.assertIsNone(result)

    @patch("requests.Session.post")
    def test_embed_text_nan_returns_none(self, mock_post):
        """NaN in single-text response returns None."""
        embedder = self._make_embedder()
        mock_post.return_value = self._mock_response(200, [float("nan")] * 384)

        result = embedder.embed_text("hello")

        self.assertIsNone(result)

    @patch("requests.Session.post")
    def test_embed_text_client_error(self, mock_post):
        """4xx response returns None."""
        embedder = self._make_embedder()
        mock_post.return_value = self._mock_response(422)

        result = embedder.embed_text("hello")

        self.assertIsNone(result)

    @patch("requests.Session.post")
    def test_embed_text_server_error(self, mock_post):
        """5xx response returns None."""
        embedder = self._make_embedder()
        mock_post.return_value = self._mock_response(503)

        result = embedder.embed_text("hello")

        self.assertIsNone(result)

    @patch("requests.Session.post")
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


class TestOpenAIEmbedderBatch(unittest.TestCase):
    """Test OpenAIEmbedder.embed_texts_batch native override.

    The override calls OpenAI's /v1/embeddings endpoint with an array
    ``input`` so a batch of N texts costs ⌈N/batch_size⌉ HTTP calls
    rather than the BaseEmbedder fallback's N serial round-trips.
    """

    def _make_embedder(self, model="text-embedding-3-small", dimensions=1536):
        from opencontractserver.pipeline.embedders.openai_embedder import (
            OpenAIEmbedder,
        )

        embedder = OpenAIEmbedder()
        embedder._settings = OpenAIEmbedder.Settings(
            openai_api_key="test-key",
            openai_embedding_model=model,
            openai_embedding_dimensions=dimensions,
            openai_api_base_url="",
        )
        return embedder

    def _mock_client(self, return_data):
        """Build a mock openai.OpenAI client that returns ``return_data``."""
        client = MagicMock()
        response = MagicMock()
        response.data = return_data
        client.embeddings.create.return_value = response
        return client

    def _datum(self, vec, idx=0):
        d = MagicMock()
        d.embedding = vec
        d.index = idx
        return d

    def test_empty_list_returns_empty(self):
        embedder = self._make_embedder()
        self.assertEqual(embedder.embed_texts_batch([]), [])

    def test_single_http_call_per_batch(self):
        embedder = self._make_embedder()
        vec1 = [0.1] * 1536
        vec2 = [0.2] * 1536
        client = self._mock_client([self._datum(vec1, 0), self._datum(vec2, 1)])
        with patch.object(embedder, "_build_client", return_value=client):
            result = embedder.embed_texts_batch(["hello", "world"])

        self.assertIsNotNone(result)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], vec1)
        self.assertEqual(result[1], vec2)
        client.embeddings.create.assert_called_once()
        call_kwargs = client.embeddings.create.call_args.kwargs
        self.assertEqual(call_kwargs["input"], ["hello", "world"])
        self.assertEqual(call_kwargs["model"], "text-embedding-3-small")
        self.assertEqual(call_kwargs["dimensions"], 1536)

    def test_dimensions_omitted_for_ada_002(self):
        embedder = self._make_embedder(model="text-embedding-ada-002")
        client = self._mock_client([self._datum([0.1] * 1536, 0)])
        with patch.object(embedder, "_build_client", return_value=client):
            embedder.embed_texts_batch(["hello"])

        call_kwargs = client.embeddings.create.call_args.kwargs
        self.assertNotIn("dimensions", call_kwargs)
        self.assertEqual(call_kwargs["model"], "text-embedding-ada-002")

    def test_dimensions_passed_for_3_large(self):
        embedder = self._make_embedder(model="text-embedding-3-large", dimensions=3072)
        client = self._mock_client([self._datum([0.1] * 3072, 0)])
        with patch.object(embedder, "_build_client", return_value=client):
            embedder.embed_texts_batch(["hello"])

        call_kwargs = client.embeddings.create.call_args.kwargs
        self.assertEqual(call_kwargs["dimensions"], 3072)

    def test_empty_inputs_filtered_and_rethreaded_as_none(self):
        """Empty/whitespace texts must be filtered from the wire request
        but appear as None at their original positions in the result.

        The OpenAI API rejects empty strings, so we cannot send them.
        Critical that we re-thread the gaps so caller indexing matches.
        """
        embedder = self._make_embedder()
        # Inputs: index 0 = valid, 1 = empty, 2 = whitespace, 3 = valid
        v0 = [0.1] * 1536
        v3 = [0.3] * 1536
        client = self._mock_client([self._datum(v0, 0), self._datum(v3, 1)])
        with patch.object(embedder, "_build_client", return_value=client):
            result = embedder.embed_texts_batch(["hello", "", "   ", "world"])

        self.assertEqual(len(result), 4)
        self.assertEqual(result[0], v0)
        self.assertIsNone(result[1])
        self.assertIsNone(result[2])
        self.assertEqual(result[3], v3)
        # Wire request should only contain the two non-empty texts.
        call_kwargs = client.embeddings.create.call_args.kwargs
        self.assertEqual(call_kwargs["input"], ["hello", "world"])

    def test_all_empty_inputs_skip_wire_call(self):
        """All-empty input must skip the API call entirely."""
        embedder = self._make_embedder()
        client = self._mock_client([])
        with patch.object(embedder, "_build_client", return_value=client):
            result = embedder.embed_texts_batch(["", "  ", "\t"])

        self.assertEqual(result, [None, None, None])
        client.embeddings.create.assert_not_called()

    def test_count_mismatch_fails_whole_batch(self):
        """Defensive guard: refuse to silently realign on a count mismatch."""
        embedder = self._make_embedder()
        # Send 3 inputs but mock returns 2 — must yield None, not partial.
        client = self._mock_client(
            [self._datum([0.1] * 1536, 0), self._datum([0.2] * 1536, 1)]
        )
        with patch.object(embedder, "_build_client", return_value=client):
            result = embedder.embed_texts_batch(["a", "b", "c"])

        self.assertIsNone(result)

    def test_authentication_error_returns_none(self):
        import openai

        embedder = self._make_embedder()
        client = MagicMock()
        client.embeddings.create.side_effect = openai.AuthenticationError(
            message="bad key",
            response=MagicMock(status_code=401),
            body=None,
        )
        with patch.object(embedder, "_build_client", return_value=client):
            result = embedder.embed_texts_batch(["hello"])

        self.assertIsNone(result)

    def test_rate_limit_error_re_raises_for_celery_retry(self):
        """RateLimitError after SDK retries propagates so celery can retry.

        The OpenAI SDK already absorbed up to ``OPENAI_CLIENT_MAX_RETRIES``
        of these internally with Retry-After-honouring exponential
        backoff; if we still saw it, the rate-limit window is wider
        than the SDK budget and we want celery's autoretry_for=(Exception,)
        to take over with a fresh backoff. Returning None on RateLimitError
        (the old behaviour) made the whole batch silently fail without
        triggering a celery retry.
        """
        import openai

        embedder = self._make_embedder()
        client = MagicMock()
        client.embeddings.create.side_effect = openai.RateLimitError(
            message="slow down",
            response=MagicMock(status_code=429),
            body=None,
        )
        with patch.object(embedder, "_build_client", return_value=client):
            with self.assertRaises(openai.RateLimitError):
                embedder.embed_texts_batch(["hello"])

    def test_api_timeout_re_raises_for_celery_retry(self):
        import openai

        embedder = self._make_embedder()
        client = MagicMock()
        client.embeddings.create.side_effect = openai.APITimeoutError(
            request=MagicMock()
        )
        with patch.object(embedder, "_build_client", return_value=client):
            with self.assertRaises(openai.APITimeoutError):
                embedder.embed_texts_batch(["hello"])

    def test_api_connection_error_re_raises_for_celery_retry(self):
        import openai

        embedder = self._make_embedder()
        client = MagicMock()
        client.embeddings.create.side_effect = openai.APIConnectionError(
            request=MagicMock()
        )
        with patch.object(embedder, "_build_client", return_value=client):
            with self.assertRaises(openai.APIConnectionError):
                embedder.embed_texts_batch(["hello"])

    def test_api_batch_size_default_is_256(self):
        """OpenAIEmbedder advertises a 256-input sub-batch cap.

        Production sub-batch carving in
        ``calculate_embeddings_for_annotation_batch`` reads
        ``embedder.api_batch_size`` to size sub-batches. 256 is sized
        for paragraph chunks at ~1500 chars each → ~96K tokens per
        wire request, well under OpenAI's 8M-token-per-request batch
        cap and the 2048-input cap.
        """
        from opencontractserver.pipeline.embedders.openai_embedder import (
            OpenAIEmbedder,
        )

        self.assertEqual(OpenAIEmbedder.api_batch_size, 256)

    def test_embed_max_concurrent_sub_batches_default_is_4(self):
        """OpenAIEmbedder allows up to 4 in-flight sub-batches."""
        from opencontractserver.pipeline.embedders.openai_embedder import (
            OpenAIEmbedder,
        )

        self.assertEqual(OpenAIEmbedder.embed_max_concurrent_sub_batches, 4)

    def test_client_built_with_max_retries(self):
        """The OpenAI client must be built with ``max_retries`` set so the
        SDK rides out brief 429/5xx blips with exponential backoff.
        """
        import openai

        embedder = self._make_embedder()
        with patch("openai.OpenAI") as mock_openai_ctor:
            embedder._build_client()
            mock_openai_ctor.assert_called_once()
            kwargs = mock_openai_ctor.call_args.kwargs
            self.assertIn("max_retries", kwargs)
            # Sanity: must be >= the historical default (2) and finite.
            self.assertGreaterEqual(kwargs["max_retries"], 2)
            # Avoid unused-import warning.
            _ = openai

    def test_bad_request_returns_none(self):
        import openai

        embedder = self._make_embedder()
        client = MagicMock()
        client.embeddings.create.side_effect = openai.BadRequestError(
            message="bad input",
            response=MagicMock(status_code=400),
            body=None,
        )
        with patch.object(embedder, "_build_client", return_value=client):
            result = embedder.embed_texts_batch(["hello"])

        self.assertIsNone(result)

    def test_long_input_truncated_to_8k_token_budget(self):
        """Inputs over ~30K chars are truncated to stay under 8192 tokens.

        Mirrors the per-text path's char-side truncation; the API would
        otherwise return a 400 'maximum context length' for a single
        oversized input and tank the whole batch.
        """
        embedder = self._make_embedder()
        long_text = "x" * 50000
        client = self._mock_client([self._datum([0.1] * 1536, 0)])
        with patch.object(embedder, "_build_client", return_value=client):
            embedder.embed_texts_batch([long_text])

        call_kwargs = client.embeddings.create.call_args.kwargs
        self.assertEqual(len(call_kwargs["input"][0]), 30000)


class TestMicroserviceEmbedderHardening(unittest.TestCase):
    """Cover the production hardening on MicroserviceEmbedder:

    - shared ``requests.Session`` with urllib3 retry + connection pool
    - bumped ``embed_max_concurrent_sub_batches`` to fill gunicorn workers
    - ``api_batch_size`` pinned to the service-side cap

    These knobs collectively determine how aggressive (and how robust)
    we are against the local sentence-transformer microservice; the
    tests pin the values so an accidental revert to the old single-
    request, no-retry, no-pooling behaviour fails loudly in CI.
    """

    def test_api_batch_size_matches_service_cap(self):
        """``api_batch_size`` must equal the service-side MAX_TEXTS_PER_BATCH cap.

        Sending a larger batch trips a 400 from the service ("exceeds
        maximum"); pinning to the cap uses the full per-call capacity
        without ever asking for more than the service will accept.
        """
        from opencontractserver.constants.document_processing import (
            MICROSERVICE_EMBEDDER_MAX_BATCH_SIZE,
        )

        self.assertEqual(
            MicroserviceEmbedder.api_batch_size,
            MICROSERVICE_EMBEDDER_MAX_BATCH_SIZE,
        )

    def test_concurrency_matches_gunicorn_workers(self):
        """``embed_max_concurrent_sub_batches`` lines up with gunicorn --workers.

        The reference deployment uses ``gunicorn --workers 2`` so two
        in-flight requests can be processed truly in parallel (one per
        worker process). Setting the embedder concurrency higher just
        queues at the service; setting it lower wastes the second
        worker. 2 is the sweet spot for the default deployment.
        """
        self.assertEqual(MicroserviceEmbedder.embed_max_concurrent_sub_batches, 2)

    def test_shared_session_is_singleton_per_process(self):
        """``_get_session()`` returns the same Session on repeated calls.

        Connection pooling and the retry config live on the Session;
        building a fresh one per call would defeat both. The lazy
        singleton is the load-bearing guarantee.
        """
        from opencontractserver.pipeline.embedders import (
            sent_transformer_microservice as svc,
        )

        # Reset to exercise the lazy-build path then verify identity.
        with svc._SESSION_LOCK:
            svc._SESSION = None

        s1 = svc._get_session()
        s2 = svc._get_session()
        self.assertIs(s1, s2)

    def test_session_has_urllib3_retry_on_5xx_and_429(self):
        """The Session's HTTPAdapter mounts a Retry config covering
        429/502/503/504 with ``status_forcelist`` — the 'transient'
        bucket — but NOT 4xx, which must surface as
        ``EmbeddingClientError`` immediately.
        """
        from opencontractserver.pipeline.embedders import (
            sent_transformer_microservice as svc,
        )

        with svc._SESSION_LOCK:
            svc._SESSION = None

        session = svc._get_session()
        adapter = session.get_adapter("http://localhost/")
        retry = adapter.max_retries
        self.assertGreaterEqual(retry.total, 1)
        self.assertIn(429, retry.status_forcelist)
        self.assertIn(502, retry.status_forcelist)
        self.assertIn(503, retry.status_forcelist)
        self.assertIn(504, retry.status_forcelist)
        # 4xx (other than 429) must NOT be in the retry list — those
        # are permanent failures that should bubble up as
        # EmbeddingClientError.
        self.assertNotIn(400, retry.status_forcelist)
        self.assertNotIn(401, retry.status_forcelist)

    def test_session_retry_allows_post(self):
        """urllib3 defaults retries to GET-only; we must allow POST since
        every embedding endpoint is POST.
        """
        from opencontractserver.pipeline.embedders import (
            sent_transformer_microservice as svc,
        )

        with svc._SESSION_LOCK:
            svc._SESSION = None

        session = svc._get_session()
        adapter = session.get_adapter("http://localhost/")
        retry = adapter.max_retries
        # urllib3 stores allowed_methods as a frozenset of upper-cased verbs.
        self.assertIn("POST", set(retry.allowed_methods))

    def test_session_pool_is_sized_for_concurrency(self):
        """Pool size must comfortably exceed the highest embedder concurrency.

        Otherwise ingest under load logs "Connection pool is full,
        discarding connection" warnings and pays a fresh handshake
        cost per evicted connection.
        """
        from opencontractserver.pipeline.embedders import (
            sent_transformer_microservice as svc,
        )

        with svc._SESSION_LOCK:
            svc._SESSION = None

        session = svc._get_session()
        adapter = session.get_adapter("http://localhost/")
        # Headroom check: must fit OpenAI's 4 + Microservice's 2 + slop.
        self.assertGreaterEqual(adapter._pool_maxsize, 8)
