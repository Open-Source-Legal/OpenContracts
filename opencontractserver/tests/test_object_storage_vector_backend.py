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
from django.core.cache import cache
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

    def test_search_retries_manifest_read_hit_mid_overwrite(self):
        """
        put_bytes overwrites the manifest via delete-then-save, so a reader
        can catch the window where the key is briefly missing. With a
        non-empty WAL, search() must retry the manifest read instead of
        proceeding manifest-less (which would silently drop all segment data
        and misreport the namespace as nearly empty).
        """
        from opencontractserver.vector_search.object_store import ObjectNotFound

        vectors = clustered_vectors(2, 10)
        self.engine.upsert(
            NAMESPACE, [(i, vectors[i].tolist()) for i in range(len(vectors))]
        )
        self.engine.compact(NAMESPACE)  # folded WAL lingers (deferred GC)

        real_get = self.store.get_bytes
        window = {"open": True}

        def mid_overwrite_get(key):
            if key.endswith("manifest.json") and window["open"]:
                window["open"] = False  # the retry lands after the save
                raise ObjectNotFound(key)
            return real_get(key)

        with mock.patch.object(self.store, "get_bytes", side_effect=mid_overwrite_get):
            hits = must(self.engine.search(NAMESPACE, vectors[3].tolist(), 3))
        self.assertEqual(hits[0][0], 3)
        self.assertAlmostEqual(hits[0][1], 1.0, places=3)
        self.assertEqual(len(hits), 3)

    def test_search_survives_compaction_between_wal_list_and_manifest_read(self):
        """
        Regression for the manifest/WAL read-order race: compaction commits
        the manifest before GC'ing folded WAL files, so ``search()`` must
        list the WAL BEFORE reading the manifest. We interleave two full
        compaction cycles between those two reads (the second cycle GC's the
        files the first one folded) — with manifest-first ordering the data
        written before the query would silently vanish from the results.
        """
        vectors = clustered_vectors(2, 10)
        self.engine.upsert(
            NAMESPACE, [(i, vectors[i].tolist()) for i in range(len(vectors))]
        )
        compactor = ObjectStorageVectorEngine(self.store, min_vectors_for_ann=50)
        real_list_wal = self.engine._list_wal

        def list_then_compact_twice(namespace):
            compactor.compact(namespace)  # folds the WAL (GC deferred)
            compactor.compact(namespace)  # GC's the files folded above
            return real_list_wal(namespace)

        with mock.patch.object(
            self.engine, "_list_wal", side_effect=list_then_compact_twice
        ):
            hits = must(self.engine.search(NAMESPACE, vectors[3].tolist(), 3))
        self.assertEqual(hits[0][0], 3)
        self.assertAlmostEqual(hits[0][1], 1.0, places=3)

    def test_partial_gc_failure_cannot_resurrect_tombstoned_ids(self):
        """
        A folded WAL file whose (deferred) GC fails must never be replayed:
        here the lingering file holds an upsert whose id was tombstoned in a
        file that WAS GC'd — replaying the survivor would resurrect the id.
        """
        wal_upsert = self.engine.upsert(NAMESPACE, [(1, sparse_vector((0, 1.0)))])
        self.engine.upsert(NAMESPACE, [(2, sparse_vector((1, 1.0)))])
        self.engine.delete(NAMESPACE, [1])
        self.engine.compact(NAMESPACE)  # gen1: id 1 dead; GC deferred
        real_delete = self.store.delete
        with mock.patch.object(
            self.store,
            "delete",
            side_effect=lambda key: (
                None if key.endswith(wal_upsert) else real_delete(key)
            ),
        ):
            # gen2's deferred GC deletes gen1's folded files — except the
            # upsert of id 1, whose deletion "fails" and lingers.
            self.engine.compact(NAMESPACE)
        hits = must(self.engine.search(NAMESPACE, sparse_vector((0, 1.0)), 5))
        self.assertEqual([h[0] for h in hits], [2])

    def test_wal_tail_count_ignores_folded_lingering_files(self):
        self.engine.upsert(NAMESPACE, [(1, sparse_vector((0, 1.0)))])
        self.engine.upsert(NAMESPACE, [(2, sparse_vector((1, 1.0)))])
        self.assertEqual(self.engine.wal_tail_count(NAMESPACE), 2)
        self.engine.compact(NAMESPACE)
        # GC is deferred: the two folded files still exist in storage, but
        # they no longer count toward the tail (else auto-compaction would
        # re-trigger forever).
        self.assertEqual(len(self.store.list_keys(f"{NAMESPACE}/wal")), 2)
        self.assertEqual(self.engine.wal_tail_count(NAMESPACE), 0)
        self.engine.upsert(NAMESPACE, [(3, sparse_vector((2, 1.0)))])
        self.assertEqual(self.engine.wal_tail_count(NAMESPACE), 1)

    def test_deferred_gc_reclaims_prior_cycle(self):
        self.engine.upsert(NAMESPACE, [(1, sparse_vector((0, 1.0)))])
        self.engine.compact(NAMESPACE)  # gen1: folded WAL + no prior gen yet
        self.engine.upsert(NAMESPACE, [(2, sparse_vector((1, 1.0)))])
        self.engine.compact(NAMESPACE)  # gen2: GC's gen1's folded WAL
        self.engine.compact(NAMESPACE)  # gen3: GC's gen1 segments, gen2 WAL
        wal_files = self.store.list_keys(f"{NAMESPACE}/wal")
        self.assertEqual(wal_files, [])
        # gen1 segment blobs are gone; gen2 blobs (prior generation, one
        # cycle of grace) and gen3 blobs remain.
        self.assertFalse(
            self.store.exists(f"{NAMESPACE}/index/segments/000001/centroids.npy")
        )
        self.assertTrue(
            self.store.exists(f"{NAMESPACE}/index/segments/000002/centroids.npy")
        )
        self.assertTrue(
            self.store.exists(f"{NAMESPACE}/index/segments/000003/centroids.npy")
        )
        hits = must(self.engine.search(NAMESPACE, sparse_vector((0, 1.0)), 5))
        self.assertEqual([h[0] for h in hits], [1, 2])


class DjangoStorageObjectStoreTests(SimpleTestCase):
    """The overwrite semantics of the blob-store adapter."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        self.storage = FileSystemStorage(location=self.tmpdir)
        self.store = DjangoStorageObjectStore(self.storage, prefix="vector-index")

    def test_put_bytes_overwrites_existing_blob(self):
        self.store.put_bytes("ns/manifest.json", b"one")
        self.store.put_bytes("ns/manifest.json", b"two")
        self.assertEqual(self.store.get_bytes("ns/manifest.json"), b"two")
        self.assertEqual(self.store.list_keys("ns"), ["manifest.json"])

    def test_put_bytes_retries_when_racing_writer_uniquifies_save(self):
        """
        Last-writer-wins under contention: a racer re-creates the key between
        our delete and save, so Django uniquifies our name. put_bytes must
        discard the stray blob, retry, and leave exactly one blob — ours.
        """
        from django.core.files.base import ContentFile

        real_save = self.storage.save
        calls = {"count": 0}

        def racing_save(name, content, *args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                # Simulate a concurrent writer landing first: the key exists
                # again by the time our save runs, forcing uniquification.
                real_save(name, ContentFile(b"racer"))
            return real_save(name, content)

        with mock.patch.object(self.storage, "save", side_effect=racing_save):
            self.store.put_bytes("ns/manifest.json", b"ours")
        self.assertEqual(self.store.get_bytes("ns/manifest.json"), b"ours")
        # No stray uniquified blobs left behind.
        self.assertEqual(self.store.list_keys("ns"), ["manifest.json"])

    def test_put_bytes_raises_when_overwrite_retries_exhausted(self):
        """
        Sustained contention (= a breached compaction lock) must fail loudly:
        a compaction whose manifest never persisted cannot report success.
        """
        from django.core.files.base import ContentFile

        from opencontractserver.vector_search.object_store import (
            ObjectStoreWriteError,
        )

        real_save = self.storage.save

        def always_racing_save(name, content, *args, **kwargs):
            if not self.storage.exists(name):
                real_save(name, ContentFile(b"racer"))
            return real_save(name, content)

        with mock.patch.object(self.storage, "save", side_effect=always_racing_save):
            with self.assertRaises(ObjectStoreWriteError):
                self.store.put_bytes("ns/manifest.json", b"ours")


class VectorSearchSystemCheckTests(SimpleTestCase):
    """The opencontracts.E002/W003 settings checks."""

    def test_invalid_backend_value_raises_e002(self):
        from opencontractserver.shared.checks import check_vector_search_backend

        with override_settings(VECTOR_SEARCH_BACKEND="bogus"):
            issues = check_vector_search_backend(None)
        self.assertEqual([issue.id for issue in issues], ["opencontracts.E002"])

    def test_valid_backend_values_pass_e002(self):
        from opencontractserver.shared.checks import check_vector_search_backend

        for value in ("pgvector", "object_storage"):
            with override_settings(VECTOR_SEARCH_BACKEND=value):
                self.assertEqual(check_vector_search_backend(None), [])

    def test_locmem_cache_with_object_backend_warns_w003(self):
        from opencontractserver.shared.checks import check_vector_search_cache

        locmem = {
            "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
        }
        with override_settings(VECTOR_SEARCH_BACKEND="object_storage", CACHES=locmem):
            issues = check_vector_search_cache(None)
            self.assertEqual([issue.id for issue in issues], ["opencontracts.W003"])
        # pgvector (default) never warns, whatever the cache backend.
        with override_settings(VECTOR_SEARCH_BACKEND="pgvector", CACHES=locmem):
            self.assertEqual(check_vector_search_cache(None), [])

    def test_public_storage_signals_warn_w004(self):
        from opencontractserver.shared.checks import (
            check_vector_index_storage_exposure,
        )

        # Each public-read signal triggers the warning on its own.
        for public_signal in (
            {"AWS_DEFAULT_ACL": "public-read"},
            {"AWS_QUERYSTRING_AUTH": False},
            {"AWS_S3_CUSTOM_DOMAIN": "cdn.example.com"},
        ):
            with override_settings(
                VECTOR_SEARCH_BACKEND="object_storage",
                STORAGE_BACKEND="AWS",
                **public_signal,
            ):
                issues = check_vector_index_storage_exposure(None)
                self.assertEqual(
                    [issue.id for issue in issues],
                    ["opencontracts.W004"],
                    public_signal,
                )
        # Private signed-URL config passes; so does any non-AWS backend and
        # the default pgvector backend.
        with override_settings(
            VECTOR_SEARCH_BACKEND="object_storage",
            STORAGE_BACKEND="AWS",
            AWS_QUERYSTRING_AUTH=True,
        ):
            self.assertEqual(check_vector_index_storage_exposure(None), [])
        with override_settings(
            VECTOR_SEARCH_BACKEND="object_storage", STORAGE_BACKEND="LOCAL"
        ):
            self.assertEqual(check_vector_index_storage_exposure(None), [])
        with override_settings(
            VECTOR_SEARCH_BACKEND="pgvector",
            STORAGE_BACKEND="AWS",
            AWS_QUERYSTRING_AUTH=False,
        ):
            self.assertEqual(check_vector_index_storage_exposure(None), [])
        # GCS public-read signals are covered too.
        for gcs_signal in (
            {"GS_DEFAULT_ACL": "publicRead"},
            {"GS_QUERYSTRING_AUTH": False},
        ):
            with override_settings(
                VECTOR_SEARCH_BACKEND="object_storage",
                STORAGE_BACKEND="GCP",
                **gcs_signal,
            ):
                issues = check_vector_index_storage_exposure(None)
                self.assertEqual(
                    [issue.id for issue in issues],
                    ["opencontracts.W004"],
                    gcs_signal,
                )
        with override_settings(
            VECTOR_SEARCH_BACKEND="object_storage",
            STORAGE_BACKEND="GCP",
            GS_QUERYSTRING_AUTH=True,
        ):
            self.assertEqual(check_vector_index_storage_exposure(None), [])


class ObjectStorageBackendIntegrationTests(TestCase):
    """The toggle, write-path fan-out, scoping, fallback, and rebuild."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        router.reset_default_engine()
        self.addCleanup(router.reset_default_engine)
        # Compaction lock/pending markers live in the (locmem) cache and would
        # otherwise leak between tests sharing a namespace.
        cache.clear()
        self.addCleanup(cache.clear)
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

    def test_rebuild_command_dry_run_reports_without_writing(self):
        import io as io_module

        # Backend off during creation: no on_commit hook, so nothing is in
        # the object store yet — exactly the pre-flip state --dry-run previews.
        doc = Document.objects.create(title="Dry", creator=self.user)
        doc.add_embedding(EMBEDDER, sparse_vector((0, 1.0)))
        with self.object_backend_settings():
            out = io_module.StringIO()
            call_command("rebuild_object_vector_index", "--dry-run", stdout=out)
            namespace = build_namespace("document", EMBEDDER, DIM)
            self.assertIn(f"[dry-run] {namespace}: would replay 1", out.getvalue())
            engine = router.get_default_engine()
            # Nothing written: no WAL files, no manifest.
            self.assertEqual(engine._list_wal(namespace), [])
            self.assertIsNone(engine._load_manifest(namespace))

    def test_rebuild_command_respects_compaction_lock(self):
        """
        The rebuild command must never compact concurrently with an
        auto-compaction: holding the per-namespace lock makes it replay the
        WAL but skip compaction (deferred to the next cycle).
        """
        import io as io_module

        from opencontractserver.tasks.vector_index_tasks import compact_lock_key

        with self.object_backend_settings():
            with self.captureOnCommitCallbacks(execute=True):
                doc = Document.objects.create(title="Locked", creator=self.user)
                doc.add_embedding(EMBEDDER, sparse_vector((0, 1.0)))
            namespace = build_namespace("document", EMBEDDER, DIM)
            cache.add(compact_lock_key(namespace), "1", timeout=60)
            try:
                out = io_module.StringIO()
                call_command("rebuild_object_vector_index", stdout=out)
                self.assertIn("compaction is already running", out.getvalue())
                engine = router.get_default_engine()
                # WAL replayed but no generation committed by the command.
                self.assertIsNone(engine._load_manifest(namespace))
                self.assertGreater(engine.wal_tail_count(namespace), 0)
            finally:
                cache.delete(compact_lock_key(namespace))

    def test_toggle_serves_core_annotation_vector_store_callers(self):
        """
        End-to-end through a real caller (CoreAnnotationVectorStore, the
        store behind GraphQL semantic search / agents / MCP): with the
        backend enabled, its vector search is served from the object index
        without ever touching pgvector's CosineDistance.
        """
        from opencontractserver.annotations.models import Annotation
        from opencontractserver.llms.vector_stores.core_vector_stores import (
            CoreAnnotationVectorStore,
            VectorSearchQuery,
        )

        # Must be a real, loadable embedder class path: the store resolves it
        # and silently substitutes the default embedder for unknown paths,
        # which would route the query to a different namespace.
        embedder_path = (
            "opencontractserver.pipeline.embedders.test_embedder.TestEmbedder"
        )
        with self.object_backend_settings():
            with self.captureOnCommitCallbacks(execute=True):
                doc = Document.objects.create(title="Host doc", creator=self.user)
                anno_hit = Annotation.objects.create(
                    document=doc, creator=self.user, raw_text="close annotation"
                )
                anno_miss = Annotation.objects.create(
                    document=doc, creator=self.user, raw_text="far annotation"
                )
                # Overwrites the signal-created TestEmbedder embeddings with
                # known sparse vectors (same embedder_path -> same rows).
                anno_hit.add_embedding(embedder_path, sparse_vector((0, 1.0)))
                anno_miss.add_embedding(embedder_path, sparse_vector((1, 1.0)))

            store = CoreAnnotationVectorStore(
                user_id=self.user.id,
                document_id=doc.id,
                embedder_path=embedder_path,
                embed_dim=DIM,
            )
            query = VectorSearchQuery(
                query_embedding=sparse_vector((0, 1.0)),
                similarity_top_k=2,
                mode="vector",
            )
            with mock.patch(
                "opencontractserver.shared.mixins.CosineDistance",
                side_effect=AssertionError("pgvector path must not be used"),
            ):
                results = store.search(query)
        self.assertEqual(
            [result.annotation.pk for result in results],
            [anno_hit.pk, anno_miss.pk],
        )
        self.assertGreater(results[0].similarity_score, 0.99)

    def test_non_indexed_parent_kinds_do_not_fan_out(self):
        """
        Read/write symmetry (round 12): conversation embeddings' read path
        bypasses the mixin (own inline pgvector implementation), so their
        writes must not fan out to the object index — that would be pure
        write amplification with no read benefit. The hook skips them
        before any Celery task is queued.
        """
        from opencontractserver.annotations.models import Embedding
        from opencontractserver.conversations.models import Conversation

        with self.object_backend_settings():
            conversation = Conversation.objects.create(creator=self.user, title="Chat")
            with mock.patch(
                "opencontractserver.tasks.vector_index_tasks"
                ".sync_embedding_to_object_index.si"
            ) as mock_signature:
                with self.captureOnCommitCallbacks(execute=True):
                    Embedding.objects.store_embedding(
                        creator=self.user,
                        dimension=DIM,
                        vector=sparse_vector((0, 1.0)),
                        embedder_path=EMBEDDER,
                        conversation_id=conversation.pk,
                    )
            mock_signature.assert_not_called()
            # Document embeddings (an indexed kind) DO fan out.
            doc = Document.objects.create(title="Indexed", creator=self.user)
            with mock.patch(
                "opencontractserver.tasks.vector_index_tasks"
                ".sync_embedding_to_object_index.si"
            ) as mock_signature:
                with self.captureOnCommitCallbacks(execute=True):
                    Embedding.objects.store_embedding(
                        creator=self.user,
                        dimension=DIM,
                        vector=sparse_vector((0, 1.0)),
                        embedder_path=EMBEDDER,
                        document_id=doc.pk,
                    )
            mock_signature.assert_called_once()

    def test_fetch_cap_binds_for_abusive_top_k(self):
        """
        Regression (round 11): fetch_n must be bounded by
        OBJECT_INDEX_MAX_FETCH_CANDIDATES even when top_k exceeds the cap —
        the earlier max(top_k, CAP) formulation collapsed the cap to top_k
        exactly when the cap was needed (caller-controlled top_k reaches this
        path unbounded, e.g. from GraphQL search resolvers).
        """
        from opencontractserver.constants.search import (
            OBJECT_INDEX_MAX_FETCH_CANDIDATES,
        )

        with self.object_backend_settings():
            with self.captureOnCommitCallbacks(execute=True):
                self._make_documents()
            engine = router.get_default_engine()
            requested: dict[str, int] = {}
            real_search = engine.search

            def spying_search(namespace, query_vector, top_k):
                requested["fetch_n"] = top_k
                return real_search(namespace, query_vector, top_k)

            with mock.patch.object(engine, "search", side_effect=spying_search):
                results = Document.objects.search_by_embedding(
                    sparse_vector((0, 1.0)),
                    EMBEDDER,
                    top_k=OBJECT_INDEX_MAX_FETCH_CANDIDATES * 10,
                )
        self.assertEqual(requested["fetch_n"], OBJECT_INDEX_MAX_FETCH_CANDIDATES)
        # Only 3 documents exist (< fetch_n): the namespace was exhausted, so
        # the short result set is complete — served without fallback.
        self.assertEqual(len(results), 3)

    def test_compaction_enqueued_once_per_threshold_crossing(self):
        """
        The pending-marker gate: during a write burst past the threshold,
        only the writer that claims the marker enqueues a compaction task —
        not every subsequent write (compaction storm).
        """
        with self.object_backend_settings():
            with mock.patch(
                "opencontractserver.tasks.vector_index_tasks"
                ".OBJECT_INDEX_COMPACT_MIN_WAL_FILES",
                1,
            ), mock.patch(
                "opencontractserver.tasks.vector_index_tasks"
                ".compact_object_vector_namespace.si"
            ) as mock_signature:
                # Compaction never actually runs (si is mocked), so the WAL
                # tail stays >= threshold for all three writes.
                self._make_documents()
            self.assertEqual(mock_signature.call_count, 1)

    def test_filter_shortfall_falls_back_to_pgvector(self):
        """
        A heavily-filtered queryset can exhaust the oversampled candidate set
        without filling top_k (post-ANN filtering's recall cliff). The router
        must detect the truncated-candidates shortfall and fall back to
        pgvector, which fills top_k via SQL — keeping "enabling the backend
        never returns worse results than pgvector" true.
        """
        with self.object_backend_settings():
            with self.captureOnCommitCallbacks(execute=True):
                # 10 high-similarity docs owned by the OTHER user swamp the
                # candidate set (fetch_n = top_k 2 * oversample 4 = 8 < 10).
                for i in range(10):
                    noise = Document.objects.create(
                        title=f"Noise {i}", creator=self.other_user
                    )
                    noise.add_embedding(
                        EMBEDDER, sparse_vector((0, 1.0), (i + 2, 0.01))
                    )
                # The caller's two docs rank far below all of them.
                mine_close = Document.objects.create(
                    title="Mine close", creator=self.user
                )
                mine_close.add_embedding(EMBEDDER, sparse_vector((0, 0.3), (1, 0.9)))
                mine_far = Document.objects.create(title="Mine far", creator=self.user)
                mine_far.add_embedding(EMBEDDER, sparse_vector((1, 1.0)))

            results = Document.objects.filter(
                creator=self.user
                # DocumentQuerySet carries the vector-search mixin at runtime.
            ).search_by_embedding(  # type: ignore[attr-defined]
                sparse_vector((0, 1.0)), EMBEDDER, top_k=2
            )
        # Without the shortfall rule the object path would return [] here
        # (all 8 fetched candidates belong to other_user and are filtered).
        self.assertEqual([doc.pk for doc in results], [mine_close.pk, mine_far.pk])
