# Single Document Upload

The most straightforward way to add documents to OpenContracts is through the
single-upload flow. This supports uploading one or more files at a time, each
processed independently.

## Using the UI

1. Navigate to the **Documents** tab or open a corpus
2. Click the **Action** dropdown and select **Upload Documents**
3. Drag and drop files into the dropzone, or click to browse
4. Edit per-file metadata (title, description, slug) if desired
5. Optionally select a target corpus
6. Click **Upload**

The upload modal is a multi-step wizard: file selection, metadata editing,
optional corpus assignment, and upload confirmation.

### File Constraints

| Constraint | Limit |
|------------|-------|
| Max file size | 100 MB per file |
| Title length | 255 characters |
| Description length | 2,000 characters |
| Slug length | 100 characters |

## Using the GraphQL API

The `UploadDocument` mutation handles single-file uploads:

**Mutation**: `UploadDocument`

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `base64FileString` | String | Yes | Base64-encoded document file |
| `filename` | String | Yes | Original filename |
| `title` | String | Yes | Document title |
| `description` | String | Yes | Document description |
| `customMeta` | GenericScalar | No | Arbitrary JSON metadata |
| `addToCorpusId` | ID | No | Corpus to add the document to |
| `addToFolderId` | ID | No | Target folder within the corpus |
| `slug` | String | No | URL-friendly slug |
| `makePublic` | Boolean | Yes | Whether the document is publicly visible |

This mutation is synchronous -- it creates the document record immediately and
returns the document ID. The document then enters the asynchronous processing
pipeline (parsing, thumbnailing, embedding).

## What Happens After Upload

1. The file is stored and a `Document` record is created
2. The file's MIME type is detected and matched to a registered parser
3. A Celery task is queued to run the processing pipeline:
   - **Parser** extracts text, tokens/bounding boxes, and structural annotations
   - **Thumbnailer** generates a preview image
   - **Embedder** creates vector embeddings for semantic search
4. The document becomes available for viewing and annotation once parsing
   completes

If the document is added to a corpus, a `DocumentPath` record is also created
to track its position within the corpus folder hierarchy.

## Retrying Failed Uploads

If document processing fails (e.g., parser service unavailable), use the
`RetryDocumentProcessing` mutation to re-queue the document for processing
without re-uploading the file.
