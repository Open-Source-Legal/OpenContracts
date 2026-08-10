- Stopped large embedding backlogs from stalling indefinitely on the CPU-only
  microservice embedder (`opencontractserver/constants/document_processing.py`).
  `EMBEDDER_BATCH_REQUEST_TIMEOUT_SECONDS` was 60s while a batch of 100
  long texts — whole ordinance sections or statute chapters, as produced by
  authority-pack ingestion — routinely takes longer than that on CPU. The
  client retried the *entire* batch three times, so each task burned ~3 minutes
  and requeued without progress. Observed on a real ingest: a ~2,800-task queue
  draining at ~1 task/min with a continuous retry storm, and semantic search
  returning "no results from either arm" because no annotation ever got an
  embedding.

  The timeout is now 300s, and the microservice batch cap drops from 100 to 32
  (`MICROSERVICE_EMBEDDER_MAX_BATCH_SIZE`, with `EMBEDDING_API_BATCH_SIZE`
  lowered from 50 to 32 to keep the `documents.E001` system check satisfied), so
  a slow batch finishes once instead of being redone three times. Measured on
  the same queue after the change: retries dropped from continuous to **zero**
  and throughput rose from ~4 to ~117 completed tasks per 4 minutes.
