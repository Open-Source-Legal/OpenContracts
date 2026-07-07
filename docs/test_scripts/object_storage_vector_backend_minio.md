# Test: Object-storage vector backend against MinIO (real S3 API)

## Purpose

Verify that the object-storage vector search engine
(`opencontractserver/vector_search/engine.py`) works end-to-end against a
real S3-compatible object store — WAL append, strong-consistency tail
search, compaction into centroid segments, tombstones, and the expected
bucket key layout — not just against the local filesystem used by the
automated suite.

## Prerequisites

- Docker available.
- Project virtualenv with `requirements/local.txt` installed (django-storages
  `[boto3]` extra provides `S3Boto3Storage` and `boto3`).

## Steps

1. Start MinIO:
   ```bash
   docker run -d --name oc-minio -p 9000:9000 \
     -e MINIO_ROOT_USER=minioadmin -e MINIO_ROOT_PASSWORD=minioadmin \
     minio/minio server /data --address :9000
   curl -s http://localhost:9000/minio/health/live -o /dev/null -w "%{http_code}\n"  # expect 200
   ```
2. Run the smoke script (Django settings `config.settings.test`; no database
   needed). The script:
   - creates bucket `oc-vector-index` via boto3;
   - builds a `DjangoStorageObjectStore` over `S3Boto3Storage`
     (`endpoint_url=http://localhost:9000`, `file_overwrite=False` to match
     production non-overwriting semantics);
   - upserts 200 clustered 384-dim vectors in 4 WAL batches;
   - asserts a pre-compaction (WAL-only) query returns the inserted vector
     with similarity ≈ 1.0 (strong consistency);
   - compacts and asserts full-probe results exactly match numpy brute force;
   - tombstones the top hit and asserts it disappears;
   - lists the bucket and asserts the
     `vector-index/<namespace>/{wal,index/manifest.json,index/segments/...}`
     layout.

   Script source: the engine calls mirror
   `opencontractserver/tests/test_object_storage_vector_backend.py::ObjectStorageVectorEngineTests`,
   with the `FileSystemStorage` swapped for `S3Boto3Storage`.

## Expected Results

- All assertions pass; final output `ALL MINIO SMOKE TESTS PASSED`.
- Bucket listing shows `manifest.json`, `centroids.npy`, and
  `cluster_*.npz` under `index/segments/000001/`, and an empty WAL dir
  after compaction.

Last verified: 2026-07-07 (MinIO `latest`, engine at introduction commit) —
all steps passed.

## Cleanup

```bash
docker rm -f oc-minio
```
