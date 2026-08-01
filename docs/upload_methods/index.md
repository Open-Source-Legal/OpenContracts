# Document Upload Methods

OpenContracts provides several ways to get documents into the system, from
single-file uploads to bulk ZIP imports with metadata and pre-built annotations.
This section covers every supported format, their capabilities, and the side
effects that certain annotation types trigger on import.

## Sections

| Page | Description |
|------|-------------|
| [Supported File Formats](supported_formats.md) | File types accepted for upload, which parsers handle them, and the optional Gotenberg conversion step for everything else |
| [Single Document Upload](single_upload.md) | Uploading individual documents through the UI or API |
| [Bulk ZIP Import](bulk_zip_import.md) | Importing many documents at once with folder structure, metadata, and relationships |
| [Corpus Export/Import](corpus_export_import.md) | Exporting and re-importing full corpuses with annotations, labels, and configuration |
| [Annotated Document Import](annotated_document_import.md) | Importing a single document with pre-built annotations into an existing corpus |
| [Worker Uploads (REST API)](worker_uploads.md) | Token-scoped REST API for external pipelines to push pre-processed documents with annotations and embeddings |
| [Remote Ingest Worker](remote_ingest_worker.md) | Run the full parse + embed pipeline on your own hardware and stream finished documents (with calculated metadata/annotations) to a target instance |
| [Worker Celery Setup](worker_celery_setup.md) | Ops reference: the Celery workers + queues (`celery,worker_uploads,doc_parse`) and Beat a target must run so worker uploads become documents |
| [Annotation Side Effects](annotation_side_effects.md) | Special annotation types that create document indexes, hierarchies, and structural data on import |

## Quick Reference: Which Method to Use

| Scenario | Method |
|----------|--------|
| Upload a few documents for manual annotation | [Single Upload](single_upload.md) |
| Upload hundreds of documents preserving folder organization | [Bulk ZIP Import](bulk_zip_import.md) |
| Bulk-load a very large local PDF tree (100k+ files), resumably -- server parses | [Bulk ZIP Import](bulk_zip_import.md) (`scripts/bulk_import` CLI driver) |
| Bulk-load a very large local tree, offloading parse + embed to your own hardware | [Remote Ingest Worker](remote_ingest_worker.md) (`scripts/remote_ingest` CLI driver) |
| Migrate a fully-annotated corpus to another instance | [Corpus Export/Import](corpus_export_import.md) |
| Programmatically inject a document with pre-built annotations | [Annotated Document Import](annotated_document_import.md) |
| Feed documents from an external processing pipeline via REST API | [Worker Uploads](worker_uploads.md) |
| Build a navigable document index from an external tool | [Annotation Side Effects](annotation_side_effects.md) |
