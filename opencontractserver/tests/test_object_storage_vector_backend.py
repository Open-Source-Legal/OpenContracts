"""
Tests for the object-storage (turbopuffer-style) vector search backend.

Two layers:

1. ``ObjectStorageVectorEngineTests`` — pure engine tests (no database):
   WAL-only strong consistency, compaction, centroid-ANN parity with brute
   force, tombstones, overwrite ordering, and recall on clustered data.

2. ``ObjectStorageBackendIntegrationTests`` — Django integration: the
   ``VECTOR_SEARCH_BACKEND`` toggle, write-path fan-out from
   ``store_embedding`` (via transaction.on_commit + eager Celery),
   queryset-scoping preservation, pgvector fallback, the rebuild management
   command, and auto-compaction triggering.
"""

import shutil
import tempfile
from unittest import mock

import numpy as np
from django.contrib.auth import get_user_model
from django.core.files.storage import FileSystemStorage
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings

from opencontractserver.documents.models import Document
from opencontractserver.vector_search import router
from opencontractserver.vector_search.engine import ObjectStorageVectorEngine
from opencontractserver.vector_search.object_store import DjangoStorageObjectStore
from opencontractserver.vector_search.router import build_namespace

User = get_user_model()

DIM = 384
EMBEDDER = "test/object-storage-embedder"
NAMESPACE = build_namespace("annotation", EMBEDDER, DIM)


def clustered_vectors(
    n_clusters: int, per_cluster: int, dim: int = DIM, seed: int = 7
) -> np.ndarray:
    """Synthetic embeddings with real cluster structure (unlike pure noise)."""
    rng = np.random.default_rng(seed)
    centers = rng.normal(size=(n_clusters, dim))
    points = np.concatenate(
        [center + 0.05 * rng.normal(size=(per_cluster, dim)) for center in centers]
    ).astype(np.float32)
    return points


def brute_force_top_ids(vectors: np.ndarray, query: np.ndarray, k: int) -> list[int]:
    normed = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
    query_normed = query / np.linalg.norm(query)
    return np.argsort(-(normed @ query_normed))[:k].tolist()


def sparse_vector(*components: tuple[int, float], dim: int = DIM) -> list[float]:
    vector = [0.0] * dim
    for index, value in components:
        vector[index] = value
    return vector


def must(result):
    """Narrow Optional engine results for mypy: fail loudly if None."""
    assert result is not None
    return result


class ObjectStorageVectorEngineTests(SimpleTestCase):
    """Engine-level behavior against a local filesystem object store."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        self.store = DjangoStorageObjectStore(
            FileSystemStorage(location=self.tmpdir), prefix="vector-index"
        )
        # min_vectors_for_ann lowered so small fixtures exercise clustering.
        self.engine = ObjectStorageVectorEngine(self.store, min_vectors_for_ann=50)
        # Full-probe twin: visits every cluster, so results must be exact.
        self.full_probe = ObjectStorageVectorEngine(
            self.store,
            min_vectors_for_ann=50,
            nprobe_ratio=1.0,
            nprobe_min=10_000,
        )

    def test_unknown_namespace_returns_none(self):
        self.assertIsNone(self.engine.search(NAMESPACE, [1.0] * DIM, 5))

    def test_wal_only_search_is_strongly_consistent(self):
        """Writes are searchable immediately, before any compaction/index."""
        vectors = clustered_vectors(2, 10)
        self.engine.upsert(
            NAMESPACE, [(i, vectors[i].tolist()) for i in range(len(vectors))]
        )
        hits = must(self.engine.search(NAMESPACE, vectors[3].tolist(), 3))
        self.assertEqual(hits[0][0], 3)
        self.assertAlmostEqual(hits[0][1], 1.0, places=3)

    def test_later_wal_upsert_wins(self):
        self.engine.upsert(NAMESPACE, [(1, sparse_vector((0, 1.0)))])
        self.engine.upsert(NAMESPACE, [(1, sparse_vector((1, 1.0)))])
        hits = must(self.engine.search(NAMESPACE, sparse_vector((0, 1.0)), 1))
        # Old value replaced: similarity against the new orthogonal vector is 0.
        self.assertEqual(hits[0][0], 1)
        self.assertAlmostEqual(hits[0][1], 0.0, places=5)

    def test_compaction_folds_wal_and_matches_brute_force(self):
        vectors = clustered_vectors(6, 50)  # 300 vectors -> k-means path
        for start in range(0, len(vectors), 40):
            batch = [
                (i, vectors[i].tolist())
                for i in range(start, min(start + 40, len(vectors)))
            ]
            self.engine.upsert(NAMESPACE, batch)
        stats = self.engine.compact(NAMESPACE)
        self.assertEqual(stats["count"], len(vectors))
        self.assertGreater(stats["cluster_count"], 1)
        self.assertEqual(self.engine.wal_tail_count(NAMESPACE), 0)

        query = clustered_vectors(1, 1, seed=99)[0]
        expected = brute_force_top_ids(vectors, query, 10)
        hits = [
            h[0] for h in must(self.full_probe.search(NAMESPACE, query.tolist(), 10))
        ]
        self.assertEqual(hits, expected)

    def test_default_nprobe_recall_on_clustered_data(self):
        vectors = clustered_vectors(8, 40)
        self.engine.upsert(
            NAMESPACE, [(i, vectors[i].tolist()) for i in range(len(vectors))]
        )
        self.engine.compact(NAMESPACE)
        # Query near an existing point: its cluster must be probed.
        query = vectors[123] + 0.01
        expected = set(brute_force_top_ids(vectors, query, 10))
        hits = {h[0] for h in must(self.engine.search(NAMESPACE, query.tolist(), 10))}
        recall = len(hits & expected) / 10
        self.assertGreaterEqual(recall, 0.9)

    def test_wal_tail_overrides_segments(self):
        """Post-compaction writes are visible without waiting for recompaction."""
        vectors = clustered_vectors(4, 30)
        self.engine.upsert(
            NAMESPACE, [(i, vectors[i].tolist()) for i in range(len(vectors))]
        )
        self.engine.compact(NAMESPACE)

        probe = self.full_probe
        target = brute_force_top_ids(vectors, vectors[5], 2)
        # Tombstone the best hit, flip the runner-up to the opposite direction.
        probe.delete(NAMESPACE, [target[0]])
        probe.upsert(NAMESPACE, [(target[1], (-vectors[target[1]]).tolist())])

        hits = [h[0] for h in must(probe.search(NAMESPACE, vectors[5].tolist(), 5))]
        self.assertNotIn(target[0], hits)
        self.assertNotIn(target[1], hits)

        # Compaction preserves exactly that state.
        stats = probe.compact(NAMESPACE)
        self.assertEqual(stats["count"], len(vectors) - 1)
        hits_after = [
            h[0] for h in must(probe.search(NAMESPACE, vectors[5].tolist(), 5))
        ]
        self.assertEqual(hits, hits_after)

    def test_compaction_is_deterministic(self):
        vectors = clustered_vectors(4, 30)
        self.engine.upsert(
            NAMESPACE, [(i, vectors[i].tolist()) for i in range(len(vectors))]
        )
        self.engine.compact(NAMESPACE)
        first = self.full_probe.search(NAMESPACE, vectors[0].tolist(), 10)
        self.engine.compact(NAMESPACE)
        self.full_probe.clear_caches()
        second = self.full_probe.search(NAMESPACE, vectors[0].tolist(), 10)
        self.assertEqual(first, second)

    def test_mixed_dimension_batch_rejected(self):
        with self.assertRaises(ValueError):
            self.engine.upsert(NAMESPACE, [(1, [1.0] * 384), (2, [1.0] * 768)])

    def test_invalid_dimension_rejected(self):
        with self.assertRaises(ValueError):
            self.engine.upsert(NAMESPACE, [(1, [1.0] * 3)])

    def test_namespace_slug_collisions_disambiguated(self):
        ns_a = build_namespace("annotation", "acme/embedder:v1", DIM)
        ns_b = build_namespace("annotation", "acme/embedder v1", DIM)
        self.assertNotEqual(ns_a, ns_b)


class ObjectStorageBackendIntegrationTests(TestCase):
    """The toggle, write-path fan-out, scoping, fallback, and rebuild."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        router.reset_default_engine()
        self.addCleanup(router.reset_default_engine)
        self.user = User.objects.create_user(username="owner", password="pw")
        self.other_user = User.objects.create_user(username="other", password="pw")

    def object_backend_settings(self):
        """Route default storage to a per-test tmpdir + enable the backend."""
        return override_settings(
            VECTOR_SEARCH_BACKEND="object_storage",
            STORAGES={
                "default": {
                    "BACKEND": "django.core.files.storage.FileSystemStorage",
                    "OPTIONS": {"location": self.tmpdir},
                },
                "staticfiles": {
                    "BACKEND": ("django.contrib.staticfiles.storage.StaticFilesStorage")
                },
            },
        )

    def _make_documents(self) -> tuple[Document, Document, Document]:
        """Three docs whose vectors rank a > b > c against ``sparse (0, 1.0)``."""
        doc_a = Document.objects.create(title="A", creator=self.user, is_public=True)
        doc_b = Document.objects.create(title="B", creator=self.user, is_public=True)
        doc_c = Document.objects.create(title="C", creator=self.user, is_public=True)
        with self.captureOnCommitCallbacks(execute=True):
            doc_a.add_embedding(EMBEDDER, sparse_vector((0, 1.0)))
            doc_b.add_embedding(EMBEDDER, sparse_vector((0, 0.8), (1, 0.6)))
            doc_c.add_embedding(EMBEDDER, sparse_vector((1, 1.0)))
        return doc_a, doc_b, doc_c

    def test_default_backend_is_pgvector_and_object_path_untouched(self):
        with mock.patch.object(
            router, "search_via_object_index", side_effect=AssertionError
        ):
            doc_a, doc_b, _ = self._make_documents()
            results = Document.objects.search_by_embedding(
                sparse_vector((0, 1.0)), EMBEDDER, top_k=2
            )
        self.assertEqual([doc.pk for doc in results], [doc_a.pk, doc_b.pk])
        self.assertAlmostEqual(results[0].similarity_score, 1.0, places=3)

    def test_toggle_on_serves_ranking_from_object_index(self):
        with self.object_backend_settings():
            doc_a, doc_b, doc_c = self._make_documents()
            # pgvector must not be touched when the object index serves the hit.
            with mock.patch(
                "opencontractserver.shared.mixins.CosineDistance",
                side_effect=AssertionError("pgvector path used"),
            ):
                results = Document.objects.search_by_embedding(
                    sparse_vector((0, 1.0)), EMBEDDER, top_k=3
                )
        self.assertEqual([doc.pk for doc in results], [doc_a.pk, doc_b.pk, doc_c.pk])
        self.assertAlmostEqual(results[0].similarity_score, 1.0, places=3)
        self.assertAlmostEqual(results[1].similarity_score, 0.8, places=3)
        self.assertAlmostEqual(results[2].similarity_score, 0.0, places=3)

    def test_queryset_scoping_is_preserved(self):
        """Ids come from the shared index, but the caller's queryset filters."""
        with self.object_backend_settings():
            doc_a, doc_b, doc_c = self._make_documents()
            doc_other = Document.objects.create(
                title="Other", creator=self.other_user, is_public=False
            )
            with self.captureOnCommitCallbacks(execute=True):
                doc_other.add_embedding(EMBEDDER, sparse_vector((0, 0.9)))

            results = Document.objects.filter(
                creator=self.user
                # DocumentQuerySet carries the vector-search mixin at runtime.
            ).search_by_embedding(  # type: ignore[attr-defined]
                sparse_vector((0, 1.0)), EMBEDDER, top_k=3
            )
        result_pks = [doc.pk for doc in results]
        self.assertNotIn(doc_other.pk, result_pks)
        # doc_c (similarity 0, but owned by self.user) fills the freed slot —
        # exactly what the pgvector path would return for this queryset.
        self.assertEqual(result_pks, [doc_a.pk, doc_b.pk, doc_c.pk])

    def test_deleted_rows_dropped_by_orm_refilter(self):
        with self.object_backend_settings():
            doc_a, doc_b, _ = self._make_documents()
            doc_a.delete()  # index still holds doc_a's vector (stale)
            results = Document.objects.search_by_embedding(
                sparse_vector((0, 1.0)), EMBEDDER, top_k=2
            )
        self.assertEqual(results[0].pk, doc_b.pk)

    def test_unindexed_namespace_falls_back_to_pgvector(self):
        # Embeddings created while the toggle is OFF -> no object index.
        doc_a, doc_b, _ = self._make_documents()
        with self.object_backend_settings():
            results = Document.objects.search_by_embedding(
                sparse_vector((0, 1.0)), EMBEDDER, top_k=2
            )
        self.assertEqual([doc.pk for doc in results], [doc_a.pk, doc_b.pk])

    def test_engine_error_falls_back_to_pgvector(self):
        doc_a, _, _ = self._make_documents()
        with self.object_backend_settings():
            with mock.patch.object(
                ObjectStorageVectorEngine, "search", side_effect=RuntimeError("boom")
            ):
                results = Document.objects.search_by_embedding(
                    sparse_vector((0, 1.0)), EMBEDDER, top_k=1
                )
        self.assertEqual(results[0].pk, doc_a.pk)

    def test_rebuild_command_indexes_preexisting_embeddings(self):
        # Create embeddings with the backend disabled...
        doc_a, doc_b, doc_c = self._make_documents()
        with self.object_backend_settings():
            call_command("rebuild_object_vector_index", "--embedder-path", EMBEDDER)
            with mock.patch(
                "opencontractserver.shared.mixins.CosineDistance",
                side_effect=AssertionError("pgvector path used"),
            ):
                results = Document.objects.search_by_embedding(
                    sparse_vector((0, 1.0)), EMBEDDER, top_k=3
                )
        self.assertEqual([doc.pk for doc in results], [doc_a.pk, doc_b.pk, doc_c.pk])
        # Rebuild always compacts: the namespace has an indexed generation.
        namespace = build_namespace("document", EMBEDDER, DIM)
        engine = router.get_default_engine()
        with self.object_backend_settings():
            self.assertEqual(engine.wal_tail_count(namespace), 0)

    def test_auto_compaction_triggers_at_wal_threshold(self):
        with self.object_backend_settings():
            with mock.patch(
                "opencontractserver.tasks.vector_index_tasks"
                ".OBJECT_INDEX_COMPACT_MIN_WAL_FILES",
                2,
            ):
                self._make_documents()  # 3 upserts -> threshold crossed at #2
            namespace = build_namespace("document", EMBEDDER, DIM)
            engine = router.get_default_engine()
            # Compaction fired mid-stream: an indexed generation exists with at
            # least the first two vectors, and only the post-compaction write
            # can remain in the WAL tail.
            manifest = must(engine._load_manifest(namespace))
            self.assertGreaterEqual(manifest["count"], 2)
            self.assertLessEqual(engine.wal_tail_count(namespace), 1)
