- **New ops doc: Celery configuration for worker uploads.**
  `docs/upload_methods/worker_celery_setup.md` documents the queues
  (`celery,worker_uploads`), the mandatory single Beat scheduler, scaling/HA,
  and the env-overridable knobs (`WORKER_UPLOAD_BATCH_SIZE`,
  `WORKER_UPLOAD_STALE_MINUTES`, …) a target instance must run so worker uploads
  actually drain. Linked from `mkdocs.yml`, the worker-uploads REST doc, and the
  remote-ingest-worker doc. Covers the #1 silent failure (uploads accepted but
  no worker on `worker_uploads` → documents never created).
