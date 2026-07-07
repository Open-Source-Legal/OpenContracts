# Object-Storage Vector Search Backend (turbopuffer-style)

**Status:** implemented, opt-in, disabled by default.
**Toggle:** `VECTOR_SEARCH_BACKEND=object_storage` (default `pgvector`).
**Code:** `opencontractserver/vector_search/` (`engine.py`, `object_store.py`,
`router.py`, `hooks.py`), `opencontractserver/tasks/vector_index_tasks.py`,
`opencontractserver/annotations/management/commands/rebuild_object_vector_index.py`.
**Tests:** `opencontractserver/tests/test_object_storage_vector_backend.py`.

## Why

pgvector HNSW indexes live in Postgres RAM/disk and grow with every embedding.
[turbopuffer](https://turbopuffer.com/architecture) demonstrated that vector
search can instead treat **object storage as the source of truth** (~10–100×
cheaper per GB than RAM-resident indexes), accepting a cold-query latency
penalty that tiered caching amortises: cold p50 ≈ 500ms–1s per namespace,
warm p50 ≈ 10–20ms, with strong consistency by default (WAL on object
storage, async indexing, exhaustive scan of the unindexed tail).

This backend brings that architecture to OpenContracts as an **optional,
reversible** alternative to pgvector — Postgres remains the source of truth
for vectors (`Embedding` rows), so the object index is always rebuildable and
flipping the flag back is zero-risk.

## Build on turbopuffer, or from scratch?

Flagged explicitly (this was the design question):

- **turbopuffer is closed-source SaaS.** There is nothing to self-host or
  vendor; "building on turbopuffer" can only mean an HTTP client against
  their hosted API — a non-starter as the *only* option for an MIT-licensed,
  self-hostable platform with users who have data-egress constraints.
- **From scratch is feasible and was done here** (~500 lines of numpy +
  blob-store primitives) because OpenContracts only needs the *architecture*
  (WAL + async indexing + centroid ANN + tail scan), not turbopuffer's scale
  targets (billions of vectors, SPFresh incremental clustering, BM25 on
  object storage). Everything hard about multi-tenant SaaS operation is out
  of scope — namespaces here are per-deployment, and Django/Celery already
  provide the orchestration.
- **A hosted-turbopuffer driver remains easy to add later**: the seam is
  `search_via_object_index()` / `enqueue_embedding_index_sync()` — a driver
  that maps namespace → turbopuffer namespace and implements upsert/query
  against their API would slot into the same
  `VECTOR_SEARCH_BACKEND` dispatch without touching callers.

### Prior open-source art considered

(From the HN discussion of turbopuffer's launch, which asked whether Lucene
prior art covers this.)

- **OpenSearch/Elasticsearch searchable snapshots** — plain Lucene segment
  files on S3 with node-local caching. Proven, but drags in a JVM search
  cluster; the cold path is slow and the operational surface is exactly what
  this feature is trying to avoid for small/medium deployments.
- **Quickwit** — OSS sub-second search on object storage, but designed for
  **append-only** datasets (logs/traces). OpenContracts embeddings are
  mutable (re-embedding, corpus edits, deletes), which is why this design
  follows turbopuffer's LSM-ish shape — WAL upserts/tombstones folded into
  rewritten segments — rather than Quickwit's immutable splits.
- **pgvector itself** — the incumbent default; the HN thread's fair critique
  is that pgvector is fine until index size and write amplification compete
  with your OLTP workload in the same Postgres. The toggle preserves it as
  the default and the permanent fallback.

## Architecture

```
Embedding.objects.store_embedding()          ← single write chokepoint (all producers)
        │  on_commit, only when enabled
        ▼
sync_embedding_to_object_index (Celery)      ← WAL append, fire-and-forget
        │                                       auto-compaction at WAL threshold
        ▼
<prefix>/<namespace>/wal/<ns-timestamp>.jsonl        one PUT per batch, durable
<prefix>/<namespace>/index/manifest.json             generation pointer (atomic swap)
<prefix>/<namespace>/index/segments/<gen>/centroids.npy
<prefix>/<namespace>/index/segments/<gen>/cluster_<i>.npz
        ▲
        │  compact_object_vector_namespace (Celery, cache-lock serialised)
        │  k-means (k = √n, capped), deterministic seed
        ▼
VectorSearchViaEmbeddingMixin.search_by_embedding()  ← single pgvector call site
        │  router.search_via_object_index()
        │  1. manifest GET (consistency roundtrip)
        │  2. centroid GET (LRU-cached per generation) → probe nprobe clusters
        │  3. WAL-tail GETs, replay as overlay (strong consistency)
        │  4. candidate ids → REFILTERED THROUGH THE CALLER'S QUERYSET
        ▼
list[Model instance] with .similarity_score  ← identical contract to pgvector
```

- **Namespace** = `(parent kind, embedder_path, dimension)` — mirroring the
  filters the pgvector path applies (`embedder_path` + `vector_<dim>`
  column). See `router.build_namespace`.
- **Consistency**: reads list the WAL tail **before** reading the manifest —
  this ordering is load-bearing. Compaction commits the new manifest strictly
  before GC'ing folded WAL files, so a WAL-first reader sees either the
  folded files (served from the overlay) or a manifest that already includes
  them; a manifest-first reader could pair an old manifest with an
  already-GC'd tail and silently drop writes. The manifest records the WAL
  files folded into its generation (`folded_wals`); readers skip those when
  building the overlay so lingering folded files are never replayed over
  newer segment state. Net effect: a write is searchable the moment its WAL
  PUT returns (the same "strongly consistent by default" contract turbopuffer
  advertises), with the manifest GET per query as the consistency roundtrip.
- **Compaction** folds segments + WAL into generation N+1; the manifest PUT
  is the atomic commit point. GC is **deferred by one compaction cycle**:
  committing generation N+1 deletes the WAL files and segment blobs that
  generation *N* superseded, never its own — so in-flight readers holding
  manifest N can still fetch every blob it references instead of hitting
  `ObjectNotFound` and falling back to pgvector mid-race. Deletion failures
  are harmless (readers skip folded files via `folded_wals`; dead-generation
  segment blobs are never referenced again). A Django-cache lock serialises
  compactors per namespace — which requires a **shared cache backend**
  (e.g. Redis) in multi-worker deployments; system check `opencontracts.W003`
  warns when the backend is enabled over `LocMemCache`.
- **Caching**: centroid and cluster blobs are immutable per generation and
  held in a per-process LRU (`OBJECT_INDEX_CACHE_MAX_ENTRIES`), giving the
  warm-query tier. Cold queries pay object-storage GETs, exactly as designed.

### Permissions (critical)

The engine stores **only** `(parent_pk, vector)` — no ACLs. Candidate ids are
re-filtered through the **caller's own queryset** (`qs.filter(pk__in=...)`),
so every rule already applied to that queryset — `visible_to_user`,
`MIN(document, corpus)` scoping, structural rules, corpus/document filters in
`CoreAnnotationVectorStore._build_base_queryset` — is enforced by exactly the
same code as the pgvector path. This is post-ANN filtering, so the router
oversamples (`OBJECT_INDEX_FILTER_OVERSAMPLE × top_k`) to keep heavily
filtered querysets full. Rows deleted from Postgres after indexing drop out
at the same refilter (the index tolerates staleness; Postgres is ground
truth).

**Storage exposure caveat:** query-time permissions are enforced by that ORM
re-filter, NOT at the storage layer — the index blobs themselves
(`wal/*.jsonl`, `segments/*/…`) carry no ACL. The
`VECTOR_INDEX_STORAGE_PREFIX` **must live in non-publicly-readable storage**:
a bucket with a public ACL, unsigned URLs, or a CDN custom domain fronting it
would let anyone with bucket read access enumerate raw vectors + parent ids
for private documents, entirely outside Django auth (a larger blast radius
than pgvector, where vectors never leave Postgres). System check
`opencontracts.W004` warns at boot when the backend is enabled over an AWS
storage config showing public-read signals (`AWS_DEFAULT_ACL=public-read*`,
`AWS_QUERYSTRING_AUTH=False`, or `AWS_S3_CUSTOM_DOMAIN`).

### Fallback semantics

Enabling the flag can never make search worse than pgvector: unsupported
models, never-indexed namespaces, and any engine exception all fall back to
the pgvector path inside `search_by_embedding` (logged). So does a **filter
shortfall**: post-ANN filtering has a recall cliff when the caller's queryset
is very selective, so if re-filtering consumes a *truncated* candidate set
(engine returned a full `fetch_n`) without filling `top_k`, the router falls
back to pgvector rather than under-filling; a short result from an
*exhausted* namespace is genuinely complete and is returned as-is
(`router.search_via_object_index`). An invalid `VECTOR_SEARCH_BACKEND` value
fails startup via system check `opencontracts.E002`
(`opencontractserver/shared/checks.py`).

## Storage backends

The engine talks to Django's default file storage through
`DjangoStorageObjectStore` (put/get/list/delete/exists), so the index lives
wherever `STORAGE_BACKEND` points: local disk (`LOCAL`), S3 or any
S3-compatible store like MinIO (`AWS`), or GCS (`GCP`), under
`VECTOR_INDEX_STORAGE_PREFIX` (default `vector-index/`). Verified against
MinIO via the real S3 API — see
`docs/test_scripts/object_storage_vector_backend_minio.md`.

## Operations

```bash
# 1. Build the index while still on pgvector (safe, idempotent):
python manage.py rebuild_object_vector_index            # all embedders
python manage.py rebuild_object_vector_index --embedder-path <path>

# 2. Flip the flag:
VECTOR_SEARCH_BACKEND=object_storage

# 3. Roll back any time:
VECTOR_SEARCH_BACKEND=pgvector
```

New embeddings written while enabled fan out automatically from
`store_embedding`; compaction triggers itself when a namespace's WAL tail
reaches `OBJECT_INDEX_COMPACT_MIN_WAL_FILES`. Tuning knobs (nprobe, k-means
parameters, oversample, thresholds) live in
`opencontractserver/constants/search.py` under *Object-Storage Vector Index
Parameters*.

## Current limitations / future work

- **Vector arm only.** The FTS arm of hybrid search stays in Postgres
  (`search_vector` tsvector), so hybrid/RRF behavior is unchanged. A BM25
  index on object storage (turbopuffer's other half) is future work.
- **Recall on unclustered data.** IVF-style probing depends on cluster
  structure; real embedding corpora have it, uniform random data does not
  (recall test in the suite uses clustered fixtures for this reason). Raise
  `OBJECT_INDEX_NPROBE_RATIO` / `OBJECT_INDEX_NPROBE_MIN` for higher recall.
- **Write visibility lags the Postgres commit.** The WAL PUT happens in a
  Celery task dispatched on transaction commit, not synchronously inside
  `store_embedding` — so "searchable the moment the WAL PUT returns" is
  measured from the task's PUT, and there is a queue-depth-dependent window
  after the Postgres write during which an already-indexed namespace won't
  return the new vector. (pgvector fallback still covers *never-indexed*
  namespaces, not this per-row lag.) turbopuffer's client-synchronous write
  ack does not have this window.
- **WAL ordering across workers uses wall-clock names** (`time.time_ns()`),
  so last-writer-wins between two re-embeds of the same parent on different
  Celery workers is subject to clock skew. Low impact in practice —
  embeddings are regenerated infrequently and deterministically per
  `(parent, embedder)` — and any skew is healed by the next rebuild.
- **No group commit.** Every `store_embedding` costs ~3 object-store
  roundtrips (WAL PUT + the `wal_tail_count` list/manifest reads that decide
  auto-compaction), fired per Celery task per embedding. Bulk backfills
  through the normal write path will generate proportionally high request
  volume — prefer `rebuild_object_vector_index`, which batches hundreds of
  vectors per PUT. turbopuffer group-commits concurrent writers per
  namespace; we could buffer through Redis if PUT volume matters.
- **Sequential WAL-tail GETs.** A query fetches unfolded WAL files one at a
  time (tail is bounded by `OBJECT_INDEX_COMPACT_MIN_WAL_FILES`); fetching
  them concurrently would cut cold/tail latency if p50 matters before
  compaction catches up.
- **Deletes are lazy.** Parent deletions are not tombstoned automatically;
  stale ids are dropped by the ORM refilter at query time and purged on the
  next `rebuild_object_vector_index`/compaction cycle. The refilter only
  protects against *parent* deletion, though: a future code path that
  deletes an `Embedding` row independent of its parent must tombstone the
  namespace entry (`ObjectStorageVectorEngine.delete`) or trigger a rebuild
  — otherwise the stale vector keeps matching its still-alive parent (see
  the note on `EmbeddingManager`).
- **Full recluster per compaction** (k-means from scratch) rather than
  SPFresh-style incremental cluster maintenance — fine up to ~10⁶ vectors
  per namespace, revisit beyond.
- **Per-process memory LRU only** — no shared SSD cache tier between
  workers yet.
