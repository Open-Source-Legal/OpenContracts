- **Admin "Ingestion Monitor" dashboard for diagnosing ingestion & import failures.**
  A new superuser-only page at `/admin/ingestion` (linked from the Admin
  Settings hub) surfaces ingestion and import health without exposing any
  document contents:
  - **Document Ingestion tab** — per-document parsing-pipeline status across
    all users (owner username/email, title, MIME type, file size, page count,
    `processing_status`, elapsed time, and the truncated `processing_error`),
    plus the worker/pipeline upload queue (`WorkerDocumentUpload`) with its
    own status filter.
  - **Import Batches tab** — corpus-export ZIP re-import runs
    (`PendingCorpusImport`) enriched with per-run **% documents failed**
    (aggregated from `PendingDocumentAnnotations`), batch start time and
    status; plus bulk document-zip import sessions (`ChunkedUploadSession`)
    with upload progress.
  - Each list is independently status-filterable and paginated (Prev/Next).
  - Backend: new superuser-gated GraphQL fields `adminDocumentIngestion`,
    `adminWorkerUploads`, `adminCorpusImports`, `adminBulkImportSessions`
    (`config/graphql/ingestion_admin_queries.py` +
    `config/graphql/ingestion_admin_types.py`), routed through the service
    layer (`opencontractserver/documents/services/ingestion_admin.py`,
    `WorkerDocumentUploadService.list_all_for_admin`,
    `document_imports.services.list_chunked_sessions_for_admin`). New
    `BaseService.clamp_pagination` helper and `ADMIN_INGESTION_*` constants
    (`opencontractserver/constants/document_processing.py`).
  - Frontend: `frontend/src/components/admin/IngestionMonitor.tsx`, route in
    `App.tsx`, card in `GlobalSettingsPanel`, `formatDuration` util, and table
    width/page-size constants.
  - Tests: `opencontractserver/tests/test_ingestion_admin_queries.py`,
    `frontend/tests/IngestionMonitor.ct.tsx`.
