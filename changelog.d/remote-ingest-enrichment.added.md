- **Remote-ingest pre-processing / enrichment stage.** The remote-ingest worker
  (`scripts/remote_ingest/`) can now run pluggable enrichers that CALCULATE and
  INJECT extra artifacts onto each document after parsing and before
  embedding+upload, so injected annotations are embedded and ingested like the
  parser's own:
  - `scripts/remote_ingest/enrichers.py` — an `EnricherContext` (exposes the
    parsed export + text, plus correctness helpers `find_token_matches(regex)`
    and `token_annotation(label, match)` that build a valid `annotation_json`),
    an `Enrichment` result type (structured `custom_meta`, `title`/`description`,
    `doc_labels`, injected `annotations`, `relationships`, label definitions),
    a dotted-path loader (`--enricher module:callable` / `OC_ENRICHERS`), and
    `validate_enrichment()` which enforces the worker-upload correctness rules
    (valid token indices, label definitions present, unique ids, resolvable
    relationship references) so a buggy enricher fails the document loudly
    instead of shipping a broken annotation.
  - `scripts/remote_ingest/example_enrichers.py` — three runnable examples
    (filename → `custom_meta`, detected dates → TOKEN_LABEL annotations,
    content → DOC_TYPE_LABEL).
  - Driver wiring (`oc_remote_ingest.py`): enrichment runs in `_process_one`
    before embedding (injected annotations get embedded) and folds into the
    worker-upload metadata; new `--enricher` flag / `OC_ENRICHERS` env.
- **Worker-upload accepts structured document metadata.** Added an optional
  `custom_meta` field to `WorkerDocumentUploadMetadataType`
  (`opencontractserver/types/dicts.py`); `_process_single_upload`
  (`opencontractserver/worker_uploads/tasks.py`) now writes it to
  `Document.custom_meta` (on both the standalone doc and the corpus-isolated
  copy) and the serializer validates it is a JSON object. Previously worker
  uploads could attach categorical metadata only via `doc_labels`; arbitrary
  structured metadata (jurisdiction, parsed dates, contract number, …) now
  round-trips.
