# Test: Object-storage vector backend against GCS API (fake-gcs-server)

## Purpose

Verify that the object-storage vector search engine
(`opencontractserver/vector_search/engine.py`) works end-to-end against the
**Google Cloud Storage API** through django-storages'
`GoogleCloudStorage` backend — the path taken when `STORAGE_BACKEND=GCP`.
GCS has no real directories, so `Storage.listdir()` (load-bearing for the
WAL overlay and `wal_tail_count`) is emulated with prefix+delimiter listing;
this test proves that emulation, the manifest delete-then-save overwrite,
and multi-generation deferred GC all behave correctly over the GCS API.

## Prerequisites

- Docker available.
- Project virtualenv with `requirements/local.txt` installed
  (django-storages `[google]` extra provides `GoogleCloudStorage` and
  `google-cloud-storage`).

## Steps

1. Start the GCS emulator:
   ```bash
   docker run -d --name oc-fake-gcs -p 4443:4443 \
     fsouza/fake-gcs-server -scheme http -port 4443 -backend memory
   curl -s http://localhost:4443/storage/v1/b -o /dev/null -w "%{http_code}\n"  # expect 200
   ```
2. Run the smoke script with `STORAGE_EMULATOR_HOST=http://localhost:4443`
   (Django settings `config.settings.test`; no database needed). The script:
   - creates bucket `oc-vector-index` via `google.cloud.storage.Client` with
     `AnonymousCredentials`;
   - builds a `DjangoStorageObjectStore` over
     `GoogleCloudStorage(bucket_name=..., project_id=..., credentials=...)`;
   - upserts 200 clustered 384-dim vectors in 4 WAL batches into a
     run-unique namespace;
   - asserts a pre-compaction (WAL-only) query returns the inserted vector
     with similarity ≈ 1.0 (strong consistency over GCS `listdir`);
   - compacts and asserts full-probe results exactly match numpy brute
     force;
   - tombstones the top hit and asserts it disappears;
   - runs two more compactions and asserts: generation numbers increment,
     the tombstone survives folding, generation N-2's segment blobs are
     GC'd while N-1's remain (deferred GC), and the manifest overwrite
     (delete-then-save on a mutable GCS key) round-trips;
   - asserts `wal_tail_count` counts only unfolded files;
   - lists the bucket via the raw GCS client and asserts the
     `vector-index/<namespace>/{wal,index/manifest.json,index/segments/...}`
     layout.

   Script source: the engine calls mirror
   `opencontractserver/tests/test_object_storage_vector_backend.py::ObjectStorageVectorEngineTests`,
   with the `FileSystemStorage` swapped for `GoogleCloudStorage` against the
   emulator.

## Expected Results

- All assertions pass; final output `ALL GCS SMOKE TESTS PASSED`.
- No engine or adapter code changes were required for GCS — the
  `DjangoStorageObjectStore` primitives (put/get/list/delete/exists) behave
  identically over `GoogleCloudStorage` (its `delete` is NotFound-tolerant
  and `_open` raises `FileNotFoundError`, matching the adapter's contract).

Last verified: 2026-07-07 (fake-gcs-server `latest`, django-storages 1.14.6)
— all steps passed.

## Cleanup

```bash
docker rm -f oc-fake-gcs
```
