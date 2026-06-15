- Hardened the Phase 0+1 authority-discovery surface after review:
  `CorpusReference.authority_type`/`detection_tier` and
  `AuthorityNamespace.authority_type` now carry `choices=` so invalid values are
  rejected at the Admin/serializer layer; `AuthorityNamespace.save()` refuses the
  incoherent `is_global=True` + `authority_corpus` combination
  (`opencontractserver/annotations/models.py`); the `0083` classification
  backfill flushes via batched `bulk_update` instead of one `save()` per row to
  avoid timing out large deployments; `EnrichmentService.discover()` /
  `discover_authorities` gained an optional `max_documents` cap that reports
  `documents_total` / `documents_truncated` so the bound is never silent; and the
  `0082`/`0085` namespace seed bodies moved to
  `opencontractserver/enrichment/_namespace_seed.py`, replacing the
  `importlib.import_module` of one migration from another.
