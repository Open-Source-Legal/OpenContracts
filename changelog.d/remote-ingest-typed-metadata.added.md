- **Remote-ingest enrichment can set TYPED corpus metadata (Column/Datacell), not
  just the freeform `custom_meta` field.** The enrichment stage can now populate
  the document metadata system (`Fieldset` → `Column` → `Datacell` — the UI's
  document-metadata grid, successor to legacy "metadata annotations"):
  - `MetadataService.upsert_document_metadata(corpus, document, user, column_name,
    data_type, value, validation_config=None)`
    (`opencontractserver/extracts/services/metadata.py`) — internal ingestion
    entry point that get-or-creates a manual-entry `Column` in the corpus metadata
    schema (auto-creating the `corpus.metadata_schema` `Fieldset`) and
    update_or_creates the `extract=NULL` `Datacell` (`data={"value": value}`),
    type-validated by `Datacell.clean()`. Reuses the same model path as the
    `SetMetadataValue` GraphQL mutation.
  - Worker-upload accepts a `metadata` list on `WorkerDocumentUploadMetadataType`
    (`opencontractserver/types/dicts.py`, new `WorkerMetadataFieldType`);
    `_process_single_upload` (`opencontractserver/worker_uploads/tasks.py`) sets
    each value via the service; the serializer validates entry shape + data_type.
    A value that violates its column's `data_type` fails the upload instead of
    silently landing a bad value.
  - Driver: `Enrichment.metadata` + `metadata_field(name, value, data_type=…)`
    (`scripts/remote_ingest/enrichers.py`) with client-side type validation
    (`validate_enrichment`) mirroring the server rules; example enrichers updated
    to emit typed metadata (`Contract Number`/`Revision`/`Category` STRING,
    `Effective Date` DATE, `Contract Type` CHOICE). The freeform `custom_meta`
    path remains available for non-schema data.
