- `enrich_customs_rulings` summary: renamed the misleading
  `documents_skipped_not_pdf` metric to `documents_skipped_unanchorable` (it
  now counts only genuine load/anchoring failures — supported TXT input is
  processed, not skipped) and added `canonical_id_collisions` (distinct ruling
  numbers claimed by more than one document, reported instead of silently
  resolved).
- The customs-enrichment text prefetch pool is now the
  `CUSTOMS_ENRICHMENT_PREFETCH_WORKERS` setting instead of a hardcoded 12 that
  overran the S3 connection pool and logged "connection pool is full" warnings
  on large runs. Default derives `AWS_S3_CONNECTION_POOL_SIZE - 1`, leaving
  the caller thread its own connection slot (`config/settings/base.py`,
  `CustomsRulingCitationService._prefetch_workers`).
