# Worker Document Upload System

## Overview

The Worker Document Upload System allows external document processing workers
(such as custom Docling pipelines, LlamaParse wrappers, or bespoke NLP services)
to submit **pre-processed** documents directly into an OpenContracts corpus via a
REST API. This enables headless, automated ingestion at scale without
requiring the documents to pass through the built-in parsing pipeline.

## Architecture

```
External Worker                OpenContracts
┌──────────────┐   REST API    ┌─────────────────────┐
│  Docling /   │──────────────>│  /api/worker-uploads │
│  LlamaParse  │  WorkerKey    │  /documents/         │
│  Custom NLP  │  Auth Header  │                      │
└──────────────┘               │  ┌───────────────┐   │
                               │  │ Staging Table  │   │
                               │  │ (DB queue)     │   │
                               │  └───────┬───────┘   │
                               │          │            │
                               │  ┌───────▼───────┐   │
                               │  │ Celery Worker  │   │
                               │  │ (batch proc.)  │   │
                               │  └───────┬───────┘   │
                               │          │            │
                               │  ┌───────▼───────┐   │
                               │  │ Document +     │   │
                               │  │ Annotations +  │   │
                               │  │ Embeddings     │   │
                               │  └───────────────┘   │
                               └─────────────────────┘
```

## Setup (Four Steps)

### Step 1: Create a Worker Account

Worker accounts are service accounts that represent an external processing
worker. They are managed by superusers through the Admin Settings panel.

1. Navigate to **Admin Settings** > **Worker Accounts**.
2. Click **Create Worker Account**.
3. Enter a descriptive **Name** (e.g., `docling-worker-prod`) and an optional
   description.
4. Click **Create Account**.

The worker account will be created with an associated system user. This user
has an unusable password and cannot log in directly.

### Step 2: Create a Corpus Access Token

Access tokens are scoped to a specific corpus and grant upload permissions
to a worker account.

1. Navigate to the **Corpus Settings** page for the target corpus.
2. Scroll to the **Worker Access Tokens** section.
3. Click **Create Access Token**.
4. Select the **Worker Account** to grant access.
5. Optionally set an **expiration** (in days) and a **rate limit** (requests
   per minute; 0 = unlimited).
6. Click **Create Token**.
7. **Copy the displayed token immediately** — it will only be shown once.

The token is stored as a SHA-256 hash. The plaintext cannot be recovered.

### Step 3: Upload Documents via REST API

Workers authenticate using the `WorkerKey` authorization scheme:

```bash
curl -X POST https://your-instance.example.com/api/worker-uploads/documents/ \
  -H "Authorization: WorkerKey <your-plaintext-token>" \
  -F "file=@/path/to/document.pdf" \
  -F "metadata=$(cat <<'EOF'
{
  "title": "Contract Agreement 2024",
  "content": "Full text content of the document...",
  "page_count": 12,
  "pawls_file_content": [
    {
      "page": {"width": 612, "height": 792, "index": 0},
      "tokens": [
        {"x": 72, "y": 72, "width": 50, "height": 12, "text": "Contract"}
      ]
    }
  ],
  "description": "Annual service agreement",
  "file_type": "application/pdf"
}
EOF
)"
```

A successful upload returns `202 Accepted`:

```json
{
  "upload_id": "a1b2c3d4-...",
  "status": "PENDING",
  "message": "Upload accepted for processing."
}
```

### Step 4: Monitor Upload Status

Check the status of individual uploads or list all uploads for the token:

```bash
# Single upload status
curl https://your-instance.example.com/api/worker-uploads/documents/<upload-id>/ \
  -H "Authorization: WorkerKey <your-token>"

# List all uploads (with optional status filter)
curl "https://your-instance.example.com/api/worker-uploads/documents/list/?status=COMPLETED" \
  -H "Authorization: WorkerKey <your-token>"
```

Upload statuses:
- **PENDING** — Queued for processing
- **PROCESSING** — Currently being processed by a Celery worker
- **COMPLETED** — Successfully imported into the corpus
- **FAILED** — Processing failed (check `error_message`)

## Metadata Format Reference

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `title` | string | Document title |
| `content` | string | Full text content |
| `page_count` | integer | Number of pages |
| `pawls_file_content` | array | PAWLs-format token data with bounding boxes |

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `description` | string | Document description |
| `file_type` | string | MIME type (default: `application/pdf`) |
| `target_path` | string | Corpus path for organization |
| `target_folder_path` | string | Folder hierarchy (auto-creates folders) |
| `text_labels` | object | Label definitions `{name: {text, label_type, color, ...}}` |
| `doc_labels_definitions` | object | Document label definitions |
| `doc_labels` | array | Document label names to apply |
| `labelled_text` | array | Pre-annotated text spans |
| `relationships` | array | Relationships between annotations |
| `embeddings` | object | Pre-computed vector embeddings |

### Embeddings Format

```json
{
  "embeddings": {
    "embedder_path": "opencontractserver.pipeline.embedders.sent_transformer_encoder.SentenceTransformerEncoder",
    "document_embedding": [0.1, 0.2, ...],
    "annotation_embeddings": {
      "annotation-id-1": [0.1, 0.2, ...],
      "annotation-id-2": [0.3, 0.4, ...]
    }
  }
}
```

Supported embedding dimensions: 384, 768, 1024, 1536, 3072.

### Labelled Text Format

```json
{
  "labelled_text": [
    {
      "id": "unique-annotation-id",
      "annotationLabel": "CLAUSE",
      "rawText": "The parties agree to...",
      "page": 0,
      "annotation_json": {
        "0": {"tokensJsons": [{"pageIndex": 0, "tokenIndex": 5}], "rawText": "..."}
      },
      "annotation_type": "TOKEN_LABEL",
      "structural": false
    }
  ]
}
```

## Rate Limiting

Rate limiting is configured per access token:

- **0** (default): Unlimited uploads
- **N > 0**: Maximum N requests per minute (best-effort enforcement)

Rate limit state is tracked per-token using the database. When the limit is
exceeded, the API returns `429 Too Many Requests`.

## Error Handling

### Common HTTP Status Codes

| Code | Meaning |
|------|---------|
| `202` | Upload accepted for processing |
| `400` | Invalid request (bad metadata, missing fields) |
| `401` | Authentication failed (invalid/expired token) |
| `413` | File too large (default limit: 256 MB) |
| `429` | Rate limit exceeded |
| `500` | Internal server error |

### Failed Upload Recovery

Uploads that become stuck in `PROCESSING` status are automatically recovered
by a periodic Celery task (`recover_stalled_uploads`). Uploads stalled for
longer than `WORKER_UPLOAD_STALE_MINUTES` (default: 15 minutes) are reset
to `PENDING` for reprocessing.

## Security Model

1. **Token Hashing**: Tokens are stored as SHA-256 hashes. Plaintext is
   shown exactly once at creation time.
2. **Corpus Scoping**: Each token grants access to exactly one corpus.
   Tokens cannot be used to upload to other corpora.
3. **Worker Account Isolation**: Worker accounts have associated system
   users with unusable passwords (cannot log in to the UI).
4. **Document Ownership**: Documents uploaded by workers are owned by the
   **corpus creator**, not the worker service account.
5. **Permission Inheritance**: Uploaded documents inherit the corpus's
   permission model automatically.
6. **Token Revocation**: Revoking a token immediately blocks future uploads.
   Deactivating a worker account implicitly revokes all its tokens.

## Configuration

The following environment variables control worker upload behavior:

| Variable | Default | Description |
|----------|---------|-------------|
| `WORKER_UPLOAD_BATCH_SIZE` | `50` | Uploads processed per batch |
| `MAX_WORKER_UPLOAD_SIZE_BYTES` | `268435456` (256 MB) | Maximum file size |
| `WORKER_UPLOAD_STALE_MINUTES` | `15` | Minutes before stalled upload recovery |
| `MAX_WORKER_METADATA_SIZE_BYTES` | `524288000` (500 MB) | Maximum metadata size |
