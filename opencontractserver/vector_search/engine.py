"""
Turbopuffer-style vector search engine on object storage.

Design (see ``docs/architecture/object_storage_vector_search.md``):

- Object storage is the **source of truth for the index**; Postgres remains
  the source of truth for the vectors themselves (``Embedding`` rows), so the
  index can always be rebuilt (``manage.py rebuild_object_vector_index``).
- Each **namespace** (one per parent-kind + embedder + dimension) owns a key
  prefix::

      <namespace>/wal/<seq>.jsonl                     append-only write batches
      <namespace>/index/manifest.json                 current generation pointer
      <namespace>/index/segments/<gen>/centroids.npy  (k, d) float32, unit norm
      <namespace>/index/segments/<gen>/cluster_<i>.npz ids:int64 + vectors:float32

- **Writes** append a WAL file (one PUT, durable on return). Vectors are
  unit-normalised so cosine similarity is a dot product.
- **Reads** are strongly consistent: list the WAL, then load the manifest
  (WAL-first ordering is load-bearing — see ``search()``), probe the
  ``nprobe`` nearest centroid clusters, then exhaustively scan the WAL tail
  (files not folded into the manifest's generation) as an overlay — newest
  write or tombstone for an id wins over any segment entry.
- **Compaction** folds segments + WAL into a new generation: k-means clusters
  the vectors, writes new segment blobs, atomically swaps the manifest (single
  PUT, last-writer-wins). GC is deferred one cycle: committing generation
  N+1 deletes only what generation N superseded, so readers holding manifest
  N can still fetch everything it references. Callers must serialise
  compaction per namespace (the Celery task uses a cache lock).

The engine is deliberately framework-free: it depends only on numpy and the
blob-store primitives in ``object_store.py``, so it is unit-testable without
Django models or a database.
"""

from __future__ import annotations

import io
import json
import logging
import math
import threading
import time
import uuid
from collections import OrderedDict

import numpy as np

from opencontractserver.constants.search import (
    OBJECT_INDEX_CACHE_MAX_ENTRIES,
    OBJECT_INDEX_KMEANS_ITERATIONS,
    OBJECT_INDEX_KMEANS_SEED,
    OBJECT_INDEX_MAX_CENTROIDS,
    OBJECT_INDEX_MIN_VECTORS_FOR_ANN,
    OBJECT_INDEX_NPROBE_MIN,
    OBJECT_INDEX_NPROBE_RATIO,
    VALID_EMBEDDING_DIMS,
)

from .object_store import DjangoStorageObjectStore, ObjectNotFound

logger = logging.getLogger(__name__)

# WAL ops
_OP_UPSERT = "upsert"
_OP_DELETE = "delete"


class _LRUCache:
    """Tiny thread-safe LRU for immutable index artifacts (keyed by generation)."""

    def __init__(self, max_entries: int):
        self._max = max_entries
        self._data: OrderedDict = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            if key not in self._data:
                return None
            self._data.move_to_end(key)
            return self._data[key]

    def put(self, key, value) -> None:
        with self._lock:
            self._data[key] = value
            self._data.move_to_end(key)
            while len(self._data) > self._max:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


def _normalize(matrix: np.ndarray) -> np.ndarray:
    """Unit-normalise rows; zero rows stay zero (cosine sim 0 against anything)."""
    norms = np.linalg.norm(matrix, axis=-1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def _kmeans(vectors: np.ndarray, k: int, iterations: int, seed: int) -> np.ndarray:
    """
    Plain Lloyd's k-means over unit vectors, deterministic via ``seed``.
    Returns (k, d) unit-normalised centroids. Empty clusters are re-seeded
    from the points furthest from their assigned centroid.
    """
    rng = np.random.default_rng(seed)
    n = vectors.shape[0]
    centroids = vectors[rng.choice(n, size=k, replace=False)].copy()
    for _ in range(iterations):
        # Cosine assignment: vectors and centroids are unit norm.
        sims = vectors @ centroids.T  # (n, k)
        assignment = np.argmax(sims, axis=1)
        best_sims = sims[np.arange(n), assignment]
        # Ascending: worst-fit points first, for empty-cluster reseeding.
        worst_fit_order = np.argsort(best_sims)
        reseed_cursor = 0
        for cluster_idx in range(k):
            members = vectors[assignment == cluster_idx]
            if len(members) == 0:
                # Re-seed from successive worst-fit points so multiple empty
                # clusters in one iteration don't collapse onto one seed.
                centroids[cluster_idx] = vectors[worst_fit_order[reseed_cursor]]
                reseed_cursor += 1
            else:
                centroids[cluster_idx] = members.mean(axis=0)
        centroids = _normalize(centroids)
    return centroids


class ObjectStorageVectorEngine:
    """WAL + segment + centroid-ANN engine over an object store."""

    def __init__(
        self,
        store: DjangoStorageObjectStore,
        *,
        nprobe_min: int = OBJECT_INDEX_NPROBE_MIN,
        nprobe_ratio: float = OBJECT_INDEX_NPROBE_RATIO,
        kmeans_iterations: int = OBJECT_INDEX_KMEANS_ITERATIONS,
        max_centroids: int = OBJECT_INDEX_MAX_CENTROIDS,
        min_vectors_for_ann: int = OBJECT_INDEX_MIN_VECTORS_FOR_ANN,
        cache_max_entries: int = OBJECT_INDEX_CACHE_MAX_ENTRIES,
    ):
        self.store = store
        self.nprobe_min = nprobe_min
        self.nprobe_ratio = nprobe_ratio
        self.kmeans_iterations = kmeans_iterations
        self.max_centroids = max_centroids
        self.min_vectors_for_ann = min_vectors_for_ann
        self._cache = _LRUCache(cache_max_entries)

    # ------------------------------------------------------------------ keys
    @staticmethod
    def _wal_dir(namespace: str) -> str:
        return f"{namespace}/wal"

    @staticmethod
    def _manifest_key(namespace: str) -> str:
        return f"{namespace}/index/manifest.json"

    @staticmethod
    def _segment_prefix(namespace: str, generation: int) -> str:
        return f"{namespace}/index/segments/{generation:06d}"

    # ------------------------------------------------------------- write path
    def upsert(self, namespace: str, docs: list[tuple[int, list[float]]]) -> str:
        """
        Durably append one WAL batch of ``(id, vector)`` upserts.
        Returns the WAL file name written.
        """
        if not docs:
            raise ValueError("upsert requires at least one (id, vector) pair")
        dims = {len(vector) for _, vector in docs}
        if len(dims) != 1 or next(iter(dims)) not in VALID_EMBEDDING_DIMS:
            raise ValueError(f"Invalid or mixed vector dimensions in batch: {dims}")
        entries = [
            {"op": _OP_UPSERT, "id": int(doc_id), "v": [float(x) for x in vector]}
            for doc_id, vector in docs
        ]
        return self._append_wal(namespace, entries)

    def delete(self, namespace: str, ids: list[int]) -> str:
        """Durably append tombstones for ``ids``. Returns the WAL file name."""
        if not ids:
            raise ValueError("delete requires at least one id")
        entries = [{"op": _OP_DELETE, "id": int(doc_id)} for doc_id in ids]
        return self._append_wal(namespace, entries)

    def _append_wal(self, namespace: str, entries: list[dict]) -> str:
        # Time-ordered, collision-free name: WAL files replay in name order.
        name = f"{time.time_ns():020d}-{uuid.uuid4().hex[:8]}.jsonl"
        payload = "\n".join(json.dumps(entry) for entry in entries).encode("utf-8")
        self.store.put_bytes(f"{self._wal_dir(namespace)}/{name}", payload)
        return name

    # -------------------------------------------------------------- read path
    def namespace_exists(self, namespace: str) -> bool:
        return (
            self.store.exists(self._manifest_key(namespace))
            or len(self._list_wal(namespace)) > 0
        )

    def wal_tail_count(self, namespace: str) -> int:
        """
        Number of WAL files NOT yet folded into the current generation.
        Folded-but-not-yet-GC'd files (GC is deferred one compaction cycle)
        don't count — they'd otherwise re-trigger auto-compaction forever.
        """
        wal_names = self._list_wal(namespace)
        if not wal_names:
            return 0
        folded = self._folded_wals(self._load_manifest(namespace))
        return len([name for name in wal_names if name not in folded])

    def search(
        self, namespace: str, query_vector: list[float], top_k: int
    ) -> list[tuple[int, float]] | None:
        """
        Return up to ``top_k`` ``(id, cosine_similarity)`` pairs, best first,
        or ``None`` if the namespace has never been written (callers fall back
        to another backend in that case).

        Strong consistency: WAL entries not yet folded into segments are
        scanned exhaustively and override segment data per id.
        """
        # ORDERING MATTERS: list the WAL BEFORE reading the manifest.
        # Compaction commits the new manifest strictly before GC'ing the WAL
        # files it folded, so a reader that lists the WAL first sees either
        # (a) the folded files still present (their data is served from the
        # overlay, and the manifest's folded_wals list prevents replaying
        # them over the newer segments), or (b) the files already gone, in
        # which case the manifest it reads next must already include the
        # generation that folded them. Reading manifest-first would open a
        # window where an old manifest is paired with an already-GC'd WAL
        # tail — silently dropping those writes.
        wal_names = self._list_wal(namespace)
        manifest = self._load_manifest(namespace)
        if manifest is None and not wal_names:
            return None

        query = _normalize(np.asarray(query_vector, dtype=np.float32))
        overlay = self._load_wal_overlay(
            namespace, wal_names, exclude=self._folded_wals(manifest)
        )

        scored: dict[int, float] = {}
        if manifest is not None and manifest["cluster_count"] > 0:
            generation = manifest["generation"]
            centroids = self._load_centroids(namespace, generation)
            cluster_sims = centroids @ query
            nprobe = self._effective_nprobe(len(centroids))
            probe_order = np.argsort(-cluster_sims)[:nprobe]
            for cluster_idx in probe_order:
                ids, vectors = self._load_cluster(
                    namespace, generation, int(cluster_idx)
                )
                sims = vectors @ query
                for doc_id, sim in zip(ids.tolist(), sims.tolist()):
                    if doc_id in overlay:
                        continue  # superseded by a newer WAL upsert/tombstone
                    scored[doc_id] = sim

        for doc_id, vector in overlay.items():
            if vector is not None:
                scored[doc_id] = float(vector @ query)

        ranked = sorted(scored.items(), key=lambda kv: (-kv[1], kv[0]))
        return ranked[:top_k]

    def _effective_nprobe(self, cluster_count: int) -> int:
        by_ratio = math.ceil(cluster_count * self.nprobe_ratio)
        return max(1, min(cluster_count, max(self.nprobe_min, by_ratio)))

    # -------------------------------------------------------------- compaction
    def compact(self, namespace: str) -> dict:
        """
        Fold current segments + WAL tail into a new generation.

        NOT concurrency-safe with itself: callers must hold a per-namespace
        lock (see ``compact_object_vector_namespace``). Concurrent *writes*
        are safe — WAL files that appear after the listing below simply stay
        in the tail for the next compaction.
        """
        wal_names = self._list_wal(namespace)
        manifest = self._load_manifest(namespace)
        if manifest is None and not wal_names:
            return {"namespace": namespace, "skipped": True, "reason": "empty"}

        # WAL files already folded into the current generation but whose GC
        # failed must NOT be replayed: their entries are older than the
        # segment state and would roll ids back (or resurrect tombstoned
        # ones). They are re-listed in the new manifest and re-GC'd below.
        folded_prior = self._folded_wals(manifest)

        # Materialise current state: segments first, then WAL overlay in order.
        state: dict[int, np.ndarray] = {}
        dimension = manifest["dimension"] if manifest else None
        if manifest is not None:
            generation = manifest["generation"]
            for cluster_idx in range(manifest["cluster_count"]):
                ids, vectors = self._load_cluster(namespace, generation, cluster_idx)
                for pos, doc_id in enumerate(ids.tolist()):
                    state[doc_id] = vectors[pos]
        overlay = self._load_wal_overlay(namespace, wal_names, exclude=folded_prior)
        for doc_id, vector in overlay.items():
            if vector is None:
                state.pop(doc_id, None)
            else:
                state[doc_id] = vector
                dimension = int(vector.shape[0])

        new_generation = (manifest["generation"] + 1) if manifest else 1
        segment_prefix = self._segment_prefix(namespace, new_generation)

        if state:
            ids = np.asarray(sorted(state.keys()), dtype=np.int64)
            vectors = np.stack([state[doc_id] for doc_id in ids.tolist()]).astype(
                np.float32
            )
            count = len(ids)
            if count < self.min_vectors_for_ann:
                k = 1
            else:
                k = min(self.max_centroids, max(1, int(math.sqrt(count))))
            if k == 1:
                centroids = _normalize(vectors.mean(axis=0, keepdims=True))
                assignment = np.zeros(count, dtype=np.int64)
            else:
                centroids = _kmeans(
                    vectors, k, self.kmeans_iterations, OBJECT_INDEX_KMEANS_SEED
                )
                assignment = np.argmax(vectors @ centroids.T, axis=1)
            for cluster_idx in range(k):
                mask = assignment == cluster_idx
                self._put_cluster(segment_prefix, cluster_idx, ids[mask], vectors[mask])
            buf = io.BytesIO()
            np.save(buf, centroids)
            self.store.put_bytes(f"{segment_prefix}/centroids.npy", buf.getvalue())
            cluster_count = k
        else:
            count = 0
            cluster_count = 0

        new_manifest = {
            "generation": new_generation,
            "dimension": dimension,
            "count": count,
            "cluster_count": cluster_count,
            # Every WAL file whose data is reflected in this generation.
            # Readers skip these when building the overlay so their stale
            # entries are never replayed over newer segment state (and racing
            # readers that listed the WAL just before this commit don't
            # double-apply them).
            "folded_wals": wal_names,
            # Segment blobs superseded by this commit; GC'd one cycle later.
            "prior_generation": (
                {
                    "generation": manifest["generation"],
                    "cluster_count": manifest["cluster_count"],
                }
                if manifest is not None
                else None
            ),
        }
        # Single PUT = the atomic commit point of the new generation.
        self.store.put_bytes(
            self._manifest_key(namespace),
            json.dumps(new_manifest).encode("utf-8"),
        )

        # DEFERRED garbage collection: delete only what the *previous*
        # manifest superseded (its folded WAL files and its prior
        # generation's segment blobs), not what this commit just superseded.
        # In-flight readers holding the previous manifest can therefore still
        # fetch every blob it references — one full compaction cycle of grace
        # — instead of hitting ObjectNotFound and burning a pgvector fallback
        # per racing query. Deletion failures are harmless: folded WAL files
        # are skipped by readers via folded_wals, and orphaned segment blobs
        # of dead generations are never referenced again.
        for name in folded_prior:
            self.store.delete(f"{self._wal_dir(namespace)}/{name}")
        prior_generation = manifest.get("prior_generation") if manifest else None
        if prior_generation:
            old_prefix = self._segment_prefix(namespace, prior_generation["generation"])
            self.store.delete(f"{old_prefix}/centroids.npy")
            for cluster_idx in range(prior_generation["cluster_count"]):
                self.store.delete(f"{old_prefix}/cluster_{cluster_idx:05d}.npz")

        return {
            "namespace": namespace,
            "generation": new_generation,
            "count": count,
            "cluster_count": cluster_count,
            "folded_wal_files": len(
                [name for name in wal_names if name not in folded_prior]
            ),
        }

    # ---------------------------------------------------------------- loaders
    def _list_wal(self, namespace: str) -> list[str]:
        return self.store.list_keys(self._wal_dir(namespace))

    def _load_manifest(self, namespace: str) -> dict | None:
        try:
            raw = self.store.get_bytes(self._manifest_key(namespace))
        except ObjectNotFound:
            return None
        return json.loads(raw)

    @staticmethod
    def _folded_wals(manifest: dict | None) -> set[str]:
        """WAL file names already folded into the manifest's generation."""
        if manifest is None:
            return set()
        return set(manifest.get("folded_wals", []))

    def _load_wal_overlay(
        self,
        namespace: str,
        wal_names: list[str],
        exclude: set[str] | None = None,
    ) -> dict[int, np.ndarray | None]:
        """
        Replay WAL files in name (= time) order into ``id -> unit vector`` with
        ``None`` marking tombstones. Later entries win. Files in ``exclude``
        (already folded into the current generation) are skipped — replaying
        them would apply stale entries over newer segment state.
        """
        overlay: dict[int, np.ndarray | None] = {}
        for name in wal_names:
            if exclude and name in exclude:
                continue
            try:
                raw = self.store.get_bytes(f"{self._wal_dir(namespace)}/{name}")
            except ObjectNotFound:
                continue  # deleted by a concurrent compaction; its data is in segments
            for line in raw.decode("utf-8").splitlines():
                if not line.strip():
                    continue
                entry = json.loads(line)
                if entry["op"] == _OP_DELETE:
                    overlay[entry["id"]] = None
                else:
                    vector = np.asarray(entry["v"], dtype=np.float32)
                    overlay[entry["id"]] = _normalize(vector)
        return overlay

    def _load_centroids(self, namespace: str, generation: int) -> np.ndarray:
        cache_key = (self.store.prefix, namespace, generation, "centroids")
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        raw = self.store.get_bytes(
            f"{self._segment_prefix(namespace, generation)}/centroids.npy"
        )
        centroids = np.load(io.BytesIO(raw))
        self._cache.put(cache_key, centroids)
        return centroids

    def _load_cluster(
        self, namespace: str, generation: int, cluster_idx: int
    ) -> tuple[np.ndarray, np.ndarray]:
        cache_key = (self.store.prefix, namespace, generation, cluster_idx)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        raw = self.store.get_bytes(
            f"{self._segment_prefix(namespace, generation)}"
            f"/cluster_{cluster_idx:05d}.npz"
        )
        data = np.load(io.BytesIO(raw))
        result = (data["ids"], data["vectors"])
        self._cache.put(cache_key, result)
        return result

    def _put_cluster(
        self,
        segment_prefix: str,
        cluster_idx: int,
        ids: np.ndarray,
        vectors: np.ndarray,
    ) -> None:
        buf = io.BytesIO()
        np.savez(buf, ids=ids, vectors=vectors)
        self.store.put_bytes(
            f"{segment_prefix}/cluster_{cluster_idx:05d}.npz", buf.getvalue()
        )

    def clear_caches(self) -> None:
        self._cache.clear()
