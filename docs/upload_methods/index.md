# Document Upload Methods

OpenContracts provides several ways to get documents into the system, from
single-file uploads to bulk ZIP imports with metadata and pre-built annotations.
This section covers every supported format, their capabilities, and the side
effects that certain annotation types trigger on import.

## Sections

| Page | Description |
|------|-------------|
| [Supported File Formats](supported_formats.md) | File types accepted for upload and which parsers handle them |
| [Single Document Upload](single_upload.md) | Uploading individual documents through the UI or API |
| [Bulk ZIP Import](bulk_zip_import.md) | Importing many documents at once with folder structure, metadata, and relationships |
| [Corpus Export/Import](corpus_export_import.md) | Exporting and re-importing full corpuses with annotations, labels, and configuration |
| [Annotated Document Import](annotated_document_import.md) | Importing a single document with pre-built annotations into an existing corpus |
| [Worker Uploads (REST API)](worker_uploads.md) | Token-scoped REST API for external pipelines to push pre-processed documents with annotations and embeddings |
| [Annotation Side Effects](annotation_side_effects.md) | Special annotation types that create document indexes, hierarchies, and structural data on import |

## Quick Reference: Which Method to Use

| Scenario | Method |
|----------|--------|
| Upload a few documents for manual annotation | [Single Upload](single_upload.md) |
| Upload hundreds of documents preserving folder organization | [Bulk ZIP Import](bulk_zip_import.md) |
| Migrate a fully-annotated corpus to another instance | [Corpus Export/Import](corpus_export_import.md) |
| Programmatically inject a document with pre-built annotations | [Annotated Document Import](annotated_document_import.md) |
| Feed documents from an external processing pipeline via REST API | [Worker Uploads](worker_uploads.md) |
| Build a navigable document index from an external tool | [Annotation Side Effects](annotation_side_effects.md) |
