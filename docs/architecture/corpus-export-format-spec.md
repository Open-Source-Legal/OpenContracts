# OpenContracts Corpus Export Format Specification

## Overview

OpenContracts exports a corpus as a **ZIP archive** containing a `data.json`
metadata file alongside the original document files (PDFs, text files, etc.).
Two format versions exist:

| Version | Marker | Notes |
|---------|--------|-------|
| **1.0** | `version` field absent or `"1.0"` | Legacy format. Documents, labels, annotations. |
| **2.0** | `"version": "2.0"` | Full format. Adds structural annotations, folders, versioning, relationships, agent config, conversations. |

V2 is a strict superset of V1 — every V1 export is valid input for a V2
importer, and V1 importers silently ignore V2-only fields.

## ZIP Layout

```
corpus_export.zip
├── data.json                  # All metadata, annotations, labels, etc.
├── document_a.pdf             # Original document files (names match keys
├── document_b.pdf             #   in data.json → annotated_docs)
├── report.txt
└── ...
```

- Every key in `annotated_docs` **must** have a corresponding file at the
  ZIP root with that exact filename.
- `data.json` **must** be present at the ZIP root (not in a subdirectory).
- No subdirectories are expected; all files sit at the root level.

---

## data.json — Top-Level Structure

### V1 (Minimal)

```jsonc
{
  // V1 fields — always required
  "annotated_docs": { ... },       // map<filename, DocumentExport>
  "doc_labels":     { ... },       // map<label_name, LabelDefinition>
  "text_labels":    { ... },       // map<label_name, LabelDefinition>
  "corpus":         { ... },       // CorpusMetadata
  "label_set":      { ... }        // LabelSetMetadata
}
```

### V2 (Full)

```jsonc
{
  "version": "2.0",                               // required for V2

  // ── V1 fields (always required) ──────────────────────────────────
  "annotated_docs":             { ... },           // map<filename, DocumentExport>
  "doc_labels":                 { ... },           // map<label_name, LabelDefinition>
  "text_labels":                { ... },           // map<label_name, LabelDefinition>
  "corpus":                     { ... },           // CorpusMetadata (V2 extended)
  "label_set":                  { ... },           // LabelSetMetadata

  // ── V2 required fields ───────────────────────────────────────────
  "structural_annotation_sets": { ... },           // map<content_hash, StructuralSet>
  "folders":                    [ ... ],           // CorpusFolder[]
  "document_paths":             [ ... ],           // DocumentPath[]
  "relationships":              [ ... ],           // Relationship[]
  "agent_config":               { ... },           // AgentConfig
  "md_description":             "..." | null,      // markdown string or null
  "md_description_revisions":   [ ... ],           // DescriptionRevision[]
  "post_processors":            [ ... ],           // string[] (dotted Python paths)

  // ── V2 optional fields (controlled by export flags) ──────────────
  "conversations":              [ ... ],           // ConversationExport[] (optional)
  "messages":                   [ ... ],           // ChatMessageExport[] (optional)
  "message_votes":              [ ... ],           // MessageVoteExport[] (optional)
  "action_trail":               { ... }            // ActionTrailExport (optional)
}
```

---

## Field Reference

### CorpusMetadata (`corpus`)

| Field | Type | Required | V2 Only | Description |
|-------|------|----------|---------|-------------|
| `id` | int | yes | | Original DB ID (ignored on import) |
| `title` | string | yes | | Corpus title |
| `description` | string | yes | | Plain-text description |
| `icon_name` | string | yes | | Filename of icon (e.g. `"corpus.png"`) |
| `icon_data` | string | yes | | Base64-encoded icon image data |
| `creator` | string | yes | | Email address of the creator |
| `label_set` | string\|int | yes | | ID of the associated label set (ignored on import) |
| `slug` | string\|null | | yes | URL slug |
| `post_processors` | string[] | | yes | Dotted Python paths to post-processors |
| `preferred_embedder` | string\|null | | yes | Embedder identifier |
| `corpus_agent_instructions` | string\|null | | yes | System prompt for corpus-level agent |
| `document_agent_instructions` | string\|null | | yes | System prompt for document-level agent |
| `allow_comments` | bool | | yes | Whether commenting is enabled |

### LabelSetMetadata (`label_set`)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | int\|string | yes | Original ID (ignored on import) |
| `title` | string | yes | Label set title |
| `description` | string | yes | Label set description |
| `icon_name` | string | yes | Filename of icon |
| `icon_data` | string\|null | yes | Base64-encoded icon image data |
| `creator` | string | yes | Email address of the creator |

### LabelDefinition (`doc_labels.*`, `text_labels.*`)

Each entry in `doc_labels` and `text_labels` is keyed by the label's display
name and contains:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | yes | Original ID (ignored on import) |
| `text` | string | yes | Display name (must match the map key) |
| `label_type` | string | yes | One of: `DOC_TYPE_LABEL`, `TOKEN_LABEL`, `RELATIONSHIP_LABEL`, `SPAN_LABEL` |
| `color` | string | yes | Hex color (e.g. `"#FF0000"`) |
| `description` | string | yes | Human-readable description |
| `icon` | string | yes | Icon identifier |

**Constraints:**
- Labels in `doc_labels` must have `label_type = "DOC_TYPE_LABEL"`.
- Labels in `text_labels` must have `label_type` of `"TOKEN_LABEL"` or `"SPAN_LABEL"`.
- Relationship labels used in `relationships` or structural relationships must
  have `label_type = "RELATIONSHIP_LABEL"` and be present in `text_labels`.

### DocumentExport (`annotated_docs.*`)

Each entry is keyed by the document filename (which must match a file in the ZIP).

| Field | Type | Required | V2 Only | Description |
|-------|------|----------|---------|-------------|
| `title` | string | yes | | Document title |
| `content` | string | yes | | Full extracted text content |
| `description` | string\|null | yes | | Document description |
| `page_count` | int | yes | | Number of pages |
| `pawls_file_content` | PawlsPage[] | yes | | PAWLs token data (see below) |
| `doc_labels` | string[] | yes | | List of document label names (must exist in top-level `doc_labels`) |
| `labelled_text` | Annotation[] | yes | | List of text annotations |
| `relationships` | Relationship[] | | | Document-scoped relationships (V1 style, within a single doc) |
| `file_type` | string\|null | | yes | MIME type (e.g. `"application/pdf"`, `"text/plain"`) |
| `structural_set_hash` | string\|null | | yes | Content hash referencing a key in `structural_annotation_sets` |

### PAWLs Format (`pawls_file_content`)

An array of page objects. See [PAWLs Format Specification](pawls-format.md) for
the complete reference. Summary:

```jsonc
[
  {
    "page": {
      "width": 612.0,      // float, page width in PDF points
      "height": 792.0,     // float, page height in PDF points
      "index": 0           // int, 0-based page index
    },
    "tokens": [
      // Text token
      { "x": 100, "y": 150, "width": 50, "height": 12, "text": "Hello" },
      // Image token (optional)
      {
        "x": 50, "y": 200, "width": 300, "height": 200, "text": "",
        "is_image": true,
        "image_path": "documents/123/images/page_0_img_0.jpg",
        "format": "jpeg",
        "content_hash": "abc123...",
        "original_width": 800,
        "original_height": 533,
        "image_type": "embedded"
      }
    ]
  }
]
```

**Constraints:**
- `page.index` values must be sequential starting from 0.
- Length of the array should equal `page_count` on the parent document.
- Token coordinates must be non-negative and within `page.width` / `page.height`.

### Annotation (`labelled_text.*`)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string\|int\|null | yes | Export-local ID (used to link relationships and parent references) |
| `annotationLabel` | string | yes | Name of the label (must exist in `text_labels`) |
| `rawText` | string | yes | The raw text content of the annotation |
| `page` | int | yes | 0-based page index where annotation starts |
| `annotation_json` | object | yes | Positional data (see below) |
| `parent_id` | string\|int\|null | no | Export-local ID of parent annotation |
| `annotation_type` | string\|null | no | `"TOKEN_LABEL"` or `"SPAN_LABEL"` |
| `structural` | bool | yes | Whether this is a structural (parser-generated) annotation |
| `content_modalities` | string[] | no | Content types: `["TEXT"]`, `["IMAGE"]`, or `["TEXT","IMAGE"]` |
| `long_description` | string\|null | no | Markdown description (used by document index annotations; see [Document Index Convention](#document-index-convention)) |

#### `annotation_json` Format

The format depends on the annotation type.

##### Token annotations (`annotation_type = "TOKEN_LABEL"`) — PDF documents

A map of page number (as string key) to page annotation data:

```jsonc
{
  "0": {                                  // page index as string
    "bounds": {
      "top": 100.0,                       // float
      "bottom": 120.0,                    // float
      "left": 50.0,                       // float
      "right": 500.0                      // float
    },
    "tokensJsons": [                      // references into PAWLs tokens array
      { "pageIndex": 0, "tokenIndex": 5 },
      { "pageIndex": 0, "tokenIndex": 6 }
    ],
    "rawText": "January 1, 2025"          // text for this page span
  }
}
```

**Constraints:**
- Page keys must be valid page indices (0 to `page_count - 1`).
- `pageIndex` values in token refs must match the page key.
- `tokenIndex` values must be valid indices into the corresponding page's `tokens` array.
- `bounds` coordinates must be non-negative.

##### Span annotations (`annotation_type = "SPAN_LABEL"`) — Text documents

A simple character-offset span into the document's `content` string:

```jsonc
{
  "start": 0,        // int, 0-based character offset (inclusive)
  "end": 52,         // int, 0-based character offset (exclusive)
  "text": "EXCLUSIVE LICENSE AND PRODUCT DEVELOPMENT AGREEMENT"
}
```

**Constraints:**
- `start` must be ≥ 0.
- `end` must be > `start`.
- `text` must equal `content[start:end]` (the substring at those offsets in the
  document's `content` field).
- `page` on the parent annotation should be `1` (text documents are single-page).

### Relationship (`relationships.*`)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string\|int\|null | yes | Export-local ID |
| `relationshipLabel` | string | yes | Name of the relationship label (must exist in `text_labels` with `label_type = "RELATIONSHIP_LABEL"`) |
| `source_annotation_ids` | (string\|int)[] | yes | Export-local IDs of source annotations |
| `target_annotation_ids` | (string\|int)[] | yes | Export-local IDs of target annotations |
| `structural` | bool | yes | Whether this is a structural relationship |

**Constraints:**
- All referenced annotation IDs must be resolvable — either within the same
  document's `labelled_text` or within a `structural_annotation_sets` entry.
- Must have at least one source and one target annotation.

### StructuralAnnotationSet (`structural_annotation_sets.*`)

Keyed by `content_hash`. Represents shared parser output that multiple documents
can reference. On import, existing sets with the same hash are reused (deduplication).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `content_hash` | string | yes | Unique content hash (SHA-256 of document content) |
| `parser_name` | string\|null | no | Parser that generated this (e.g. `"docling"`) |
| `parser_version` | string\|null | no | Parser version |
| `page_count` | int\|null | no | Number of pages |
| `token_count` | int\|null | no | Total token count |
| `pawls_file_content` | PawlsPage[] | yes | PAWLs token data for the structural layer |
| `txt_content` | string | yes | Full extracted text |
| `structural_annotations` | Annotation[] | yes | Parser-generated structural annotations |
| `structural_relationships` | Relationship[] | yes | Relationships between structural annotations |

### CorpusFolder (`folders.*`)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | yes | Export-local ID |
| `name` | string | yes | Folder name |
| `description` | string | yes | Folder description |
| `color` | string | yes | Hex color code |
| `icon` | string | yes | Icon identifier |
| `tags` | string[] | yes | Tag list |
| `is_public` | bool | yes | Public visibility flag |
| `parent_id` | string\|null | yes | Export-local ID of parent folder, or null for root |
| `path` | string | yes | Full path from root (e.g. `"Contracts/Executed"`) |

**Constraints:**
- `parent_id`, if non-null, must reference another folder's `id` in the same array.
- `path` must be consistent with the folder hierarchy (parent's path is a prefix).
- Folder names must not contain `/`.

### DocumentPath (`document_paths.*`)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `document_ref` | string | yes | Reference to a document: file hash or filename matching an `annotated_docs` key |
| `folder_path` | string\|null | no | Full folder path if assigned (must match a folder's `path`) |
| `path` | string | yes | Document path within the corpus |
| `version_number` | int | yes | Version number (1-based) |
| `parent_version_number` | int\|null | no | Previous version's number |
| `is_current` | bool | yes | Whether this is the active version |
| `is_deleted` | bool | yes | Soft-delete flag |
| `created` | string | yes | ISO 8601 timestamp |

### AgentConfig (`agent_config`)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `corpus_agent_instructions` | string\|null | yes | System prompt for corpus-level agent |
| `document_agent_instructions` | string\|null | yes | System prompt for document-level agent |

### DescriptionRevision (`md_description_revisions.*`)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `version` | int | yes | Revision version number |
| `diff` | string | yes | Unified diff from previous version |
| `snapshot` | string\|null | no | Full snapshot of the description at this version |
| `checksum_base` | string | yes | Checksum of the base (pre-diff) content |
| `checksum_full` | string | yes | Checksum of the full (post-diff) content |
| `created` | string | yes | ISO 8601 timestamp |
| `author_email` | string | yes | Email of the revision author |

### ConversationExport (`conversations.*`) — Optional

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | yes | Export-local ID |
| `title` | string | yes | Conversation title |
| `description` | string | no | Conversation description |
| `conversation_type` | string | yes | `"chat"` or `"thread"` |
| `is_public` | bool | yes | Public visibility |
| `is_locked` | bool | no | Lock flag |
| `is_pinned` | bool | no | Pin flag |
| `creator_email` | string | yes | Email of creator |
| `created` | string | yes | ISO 8601 timestamp |
| `modified` | string | yes | ISO 8601 timestamp |
| `chat_with_document_id` | string\|null | no | Export-local doc ID (corpus-level if null) |
| `chat_with_document_hash` | string\|null | no | Document file hash for cross-system linking |
| `chat_with_corpus` | bool | yes | Whether this is a corpus-level conversation |

### ChatMessageExport (`messages.*`) — Optional

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | yes | Export-local ID |
| `conversation_id` | string | yes | References a conversation's `id` |
| `content` | string | yes | Message content |
| `msg_type` | string | yes | Message type (e.g. `"HUMAN"`, `"AI"`) |
| `state` | string | yes | Message state (e.g. `"completed"`) |
| `agent_type` | string\|null | no | Agent type if AI-generated |
| `data` | object\|null | no | Arbitrary JSON data |
| `parent_message_id` | string\|null | no | For threading, references another message's `id` |
| `creator_email` | string | yes | Email of creator |
| `created` | string | yes | ISO 8601 timestamp |

### MessageVoteExport (`message_votes.*`) — Optional

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `message_id` | string | yes | References a message's `id` |
| `vote_type` | string | yes | Vote type (e.g. `"upvote"`) |
| `creator_email` | string | yes | Email of voter |
| `created` | string | yes | ISO 8601 timestamp |

### ActionTrailExport (`action_trail`) — Optional

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `actions` | CorpusActionExport[] | yes | Action configurations |
| `executions` | ActionExecutionExport[] | yes | Execution history |
| `stats` | ActionTrailStats | yes | Summary statistics |

#### CorpusActionExport

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Export-local ID |
| `name` | string | Action name |
| `action_type` | string | `"fieldset"`, `"analyzer"`, or `"agent"` |
| `trigger` | string | Trigger type (e.g. `"on_document_added"`) |
| `disabled` | bool | Whether disabled |
| `fieldset_id` | string\|null | Fieldset reference |
| `analyzer_id` | string\|null | Analyzer reference |
| `agent_config_id` | string\|null | Agent config reference |
| `task_instructions` | string | Task instructions |
| `pre_authorized_tools` | string[] | Pre-authorized tool names |

#### ActionExecutionExport

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Export-local ID |
| `action_name` | string | Name of the action that was executed |
| `action_type` | string | `"fieldset"`, `"analyzer"`, or `"agent"` |
| `document_id` | string | Reference to the document |
| `status` | string | `"completed"`, `"failed"`, etc. |
| `trigger` | string | What triggered this execution |
| `queued_at` | string\|null | ISO 8601 timestamp |
| `started_at` | string\|null | ISO 8601 timestamp |
| `completed_at` | string\|null | ISO 8601 timestamp |
| `duration_seconds` | float\|null | Execution duration |
| `affected_objects` | array | List of affected object descriptors |
| `error_message` | string | Error message if failed |
| `execution_metadata` | object | Arbitrary metadata |

#### ActionTrailStats

| Field | Type | Description |
|-------|------|-------------|
| `total_executions` | int | Total execution count |
| `completed` | int | Completed count |
| `failed` | int | Failed count |
| `exported_count` | int | How many were included in this export |

---

## Referential Integrity Rules

These rules must hold for a valid export. The `validate_export.py` utility
(described below) checks all of them.

### 1. ZIP ↔ data.json consistency
- Every key in `annotated_docs` must have a matching file in the ZIP.
- `data.json` must be present in the ZIP.

### 2. Label references
- Every name in a document's `doc_labels` array must exist as a key in the
  top-level `doc_labels` map.
- Every annotation's `annotationLabel` must exist as a key in the top-level
  `text_labels` map.
- Every relationship's `relationshipLabel` must exist in `text_labels` with
  `label_type = "RELATIONSHIP_LABEL"`.
- Structural annotation labels must exist in `text_labels`.

### 3. Annotation ID references
- Relationship `source_annotation_ids` and `target_annotation_ids` must
  reference valid annotation `id` values (within the same document for
  document-scoped relationships, or across any document for corpus-level).
- `parent_id` on annotations must reference another annotation's `id` within
  the same scope.

### 4. Structural set references
- A document's `structural_set_hash` (if set) must be a key in
  `structural_annotation_sets`.
- Within a structural set, relationship annotation ID references must resolve
  to annotations in the same structural set.

### 5. Folder hierarchy
- Every `parent_id` in a folder must reference another folder's `id`.
- No circular parent references.
- `path` must be consistent with parent chain (e.g. parent's path + `/` + name).

### 6. DocumentPath references
- `document_ref` must match either a document's file hash or a filename key in
  `annotated_docs`.
- `folder_path` (if set) must match a folder's `path`.

### 7. Conversation references
- `conversation_id` on messages must reference a conversation's `id`.
- `parent_message_id` on messages must reference another message's `id`.
- `message_id` on votes must reference a message's `id`.

### 8. Token index validity
- `tokenIndex` values in `annotation_json.tokensJsons` must be valid indices
  into the corresponding page's `tokens` array in PAWLs data.
- `pageIndex` values must reference valid pages.

---

## Security Limits

The importer enforces these limits (configurable via Django settings):

| Setting | Default | Description |
|---------|---------|-------------|
| `ZIP_MAX_FILE_COUNT` | 1,000 | Max files in the ZIP |
| `ZIP_MAX_TOTAL_SIZE_BYTES` | 500 MB | Max total uncompressed size |
| `ZIP_MAX_SINGLE_FILE_SIZE_BYTES` | 100 MB | Max single file size |
| `ZIP_MAX_COMPRESSION_RATIO` | 100:1 | Max compression ratio (zip bomb guard) |
| `ZIP_MAX_FOLDER_DEPTH` | 20 | Max folder nesting depth |
| `ZIP_MAX_FOLDER_COUNT` | 500 | Max folders per import |
| `ZIP_MAX_PATH_COMPONENT_LENGTH` | 255 | Max characters in a single path segment |
| `ZIP_MAX_PATH_LENGTH` | 1,024 | Max total path length |

---

## Import Behavior Notes

- **Version detection**: The importer reads `data.json["version"]`. If absent
  or `"1.0"`, V1 logic is used. If `"2.0"`, V2 logic is used.
- **ID remapping**: All `id` fields in the export are treated as opaque
  references. On import, new database IDs are assigned and an internal mapping
  is maintained to fix up relationships and parent references.
- **User mapping**: `creator_email` and `author_email` fields are used to look
  up existing users. If no match is found, the importing user is used instead.
- **Structural set deduplication**: If a `content_hash` already exists in the
  target database, the existing set is reused rather than creating a duplicate.
- **Corpus isolation**: Documents are copied into the corpus; edits within one
  corpus do not affect others.
- **Vector embeddings are NOT exported** — they are regenerated on import
  because different deployments may use different embedding models.
- **Timestamps**: `auto_now_add` timestamps on conversations and messages are
  patched post-creation to preserve original values.

---

## Document Index Convention

> **Architecture overview**: For the full design rationale, component map, data
> flow, and agent tool details, see
> [Document Annotation Index](document_annotation_index.md).

OpenContracts supports a **hierarchical document index** (within-document table
of contents) built entirely from annotations. The frontend renders these as a
navigable, collapsible tree with optional markdown descriptions. Downstream
consumers can construct document indexes in an export ZIP and they will be
imported and displayed automatically.

### How It Works

A document index is a set of annotations that:

1. Share a common label with `text = "OC_SECTION"`
2. Use `parent_id` references to form a tree (chapters → sections → subsections)
3. Optionally carry a `long_description` field with markdown content

The frontend `DocumentAnnotationIndex` component queries for annotations with
the `OC_SECTION` label on a given document+corpus and renders them as a tree.

### Building a Document Index in an Export

To include a document index in an `OpenContractDocExport`:

#### Step 1: Define the label

Add an `OC_SECTION` entry to the top-level `text_labels` map:

```jsonc
{
  "text_labels": {
    "OC_SECTION": {
      "id": "label-oc-section",
      "text": "OC_SECTION",
      "label_type": "TOKEN_LABEL",      // TOKEN_LABEL for PDFs, SPAN_LABEL for text docs
      "color": "#6366f1",
      "description": "Document section index entry",
      "icon": "tag"
    }
  }
}
```

> **Note**: Use `"TOKEN_LABEL"` for PDF documents (annotations reference PAWLs
> tokens) and `"SPAN_LABEL"` for plain-text documents (annotations use
> character offsets). If a corpus contains both types, define two labels or use
> `TOKEN_LABEL` and set `annotation_type` per-annotation.

#### Step 2: Create index annotations

Add annotations to the document's `labelled_text` array. Each annotation
represents one section/heading in the document:

```jsonc
{
  "labelled_text": [
    {
      "id": "idx-0",
      "annotationLabel": "OC_SECTION",
      "rawText": "1. Introduction",
      "long_description": "This chapter introduces the **parties** to the agreement and outlines the key terms.",
      "page": 0,
      "annotation_json": { "start": 0, "end": 16, "text": "1. Introduction" },
      "annotation_type": "SPAN_LABEL",
      "parent_id": null,
      "structural": false
    },
    {
      "id": "idx-1",
      "annotationLabel": "OC_SECTION",
      "rawText": "1.1 Definitions",
      "long_description": "Key defined terms used throughout the agreement.",
      "page": 0,
      "annotation_json": { "start": 200, "end": 216, "text": "1.1 Definitions" },
      "annotation_type": "SPAN_LABEL",
      "parent_id": "idx-0",
      "structural": false
    },
    {
      "id": "idx-2",
      "annotationLabel": "OC_SECTION",
      "rawText": "2. License Grant",
      "long_description": null,
      "page": 2,
      "annotation_json": { "start": 1500, "end": 1516, "text": "2. License Grant" },
      "annotation_type": "SPAN_LABEL",
      "parent_id": null,
      "structural": false
    }
  ]
}
```

#### Step 3: Wire hierarchy via `parent_id`

- Set `parent_id` to the `id` of the parent section annotation, or `null` for
  root-level entries.
- The importer resolves `parent_id` references during import via its standard
  ID remapping.
- Circular references are rejected by the frontend (cycle detection) and should
  be avoided.

### Field Reference for Index Annotations

| Field | Value / Convention | Notes |
|-------|-------------------|-------|
| `annotationLabel` | `"OC_SECTION"` | Exact string. The `OC_` prefix is reserved for platform-generated labels. |
| `rawText` | Section title | Displayed as the tree node label (e.g., `"Chapter 1: Introduction"`) |
| `long_description` | Markdown string or `null` | Rendered as expandable rich text below the title. Sanitized with `rehype-sanitize` on display. |
| `page` | 0-based page index | For text docs, use `1`. For PDFs, the page where the section heading appears. |
| `annotation_json` | Token map (PDF) or `TextSpanData` (text) | Must anchor to the actual heading text in the document. See [annotation_json Format](#annotation_json-format). |
| `annotation_type` | `"TOKEN_LABEL"` or `"SPAN_LABEL"` | Must match the label's `label_type` |
| `parent_id` | Export-local ID or `null` | References another `OC_SECTION` annotation's `id` for hierarchy |
| `structural` | `false` | Index annotations are user/agent-generated, not parser-generated |

### Complete Minimal Example (Text Document)

```jsonc
{
  "version": "2.0",
  "corpus": {
    "id": 1,
    "title": "Contract Corpus",
    "description": "Example corpus with document index",
    "icon_name": "corpus.png",
    "icon_data": "",
    "creator": "user@example.com",
    "label_set": "ls-1"
  },
  "label_set": {
    "id": "ls-1",
    "title": "Default Labels",
    "description": "",
    "icon_name": "labelset.png",
    "icon_data": null,
    "creator": "user@example.com"
  },
  "doc_labels": {},
  "text_labels": {
    "OC_SECTION": {
      "id": "label-oc-section",
      "text": "OC_SECTION",
      "label_type": "SPAN_LABEL",
      "color": "#6366f1",
      "description": "Document section index entry",
      "icon": "tag"
    }
  },
  "annotated_docs": {
    "agreement.txt": {
      "title": "License Agreement",
      "content": "EXCLUSIVE LICENSE AND PRODUCT DEVELOPMENT AGREEMENT\n\nThis Agreement is entered into...\n\n1. Definitions\n\nFor purposes of this Agreement...\n\n2. License Grant\n\nSubject to the terms...",
      "description": "Sample license agreement",
      "pawls_file_content": [],
      "page_count": 1,
      "file_type": "text/plain",
      "doc_labels": [],
      "labelled_text": [
        {
          "id": "idx-0",
          "annotationLabel": "OC_SECTION",
          "rawText": "Agreement Header",
          "long_description": "The **master heading** of the license agreement between the two parties.",
          "page": 1,
          "annotation_json": { "start": 0, "end": 52, "text": "EXCLUSIVE LICENSE AND PRODUCT DEVELOPMENT AGREEMENT" },
          "annotation_type": "SPAN_LABEL",
          "parent_id": null,
          "structural": false
        },
        {
          "id": "idx-1",
          "annotationLabel": "OC_SECTION",
          "rawText": "Definitions",
          "long_description": "Defines key terms: *Execution Date*, *Licensed Products*, *Territory*, and *Licensed Technology*.",
          "page": 1,
          "annotation_json": { "start": 69, "end": 83, "text": "1. Definitions" },
          "annotation_type": "SPAN_LABEL",
          "parent_id": "idx-0",
          "structural": false
        },
        {
          "id": "idx-2",
          "annotationLabel": "OC_SECTION",
          "rawText": "License Grant",
          "long_description": null,
          "page": 1,
          "annotation_json": { "start": 125, "end": 141, "text": "2. License Grant" },
          "annotation_type": "SPAN_LABEL",
          "parent_id": "idx-0",
          "structural": false
        }
      ]
    }
  },
  "structural_annotation_sets": {},
  "folders": [],
  "document_paths": [],
  "relationships": [],
  "agent_config": {
    "corpus_agent_instructions": null,
    "document_agent_instructions": null
  },
  "md_description": null,
  "md_description_revisions": [],
  "post_processors": []
}
```

This produces a tree:

```
Agreement Header
├── Definitions
└── License Grant
```

Where "Agreement Header" has a markdown description shown when the user expands
it, "Definitions" has a description with italic terms, and "License Grant" has
no description.

### Limits

| Limit | Value | Notes |
|-------|-------|-------|
| Max index entries per document | 500 | Controlled by `DOCUMENT_ANNOTATION_INDEX_LIMIT` |
| Max tree depth | 4 (default) | Frontend `maxDepth` prop, configurable per-mount |

### Frontend Display Behavior

- The `DocumentAnnotationIndex` component queries for `OC_SECTION` annotations
  and builds a tree from the `parent` FK hierarchy.
- Empty results (no `OC_SECTION` annotations) → component renders nothing.
- Circular parent references → detected and broken; a warning banner is shown.
- `long_description` is rendered as sanitized markdown (via `react-markdown`
  with `rehype-sanitize`). Links, images, and script tags are stripped.
- Clicking a section navigates to the document and selects the annotation,
  triggering the two-phase scroll-to-annotation system.
- In the `DocumentTableOfContents` (multi-doc corpus view), each document
  node can be expanded to reveal its annotation index. The query is lazy —
  only fired when the node is expanded.

---

## Enum Values Reference

### LabelType
`DOC_TYPE_LABEL` | `TOKEN_LABEL` | `RELATIONSHIP_LABEL` | `SPAN_LABEL`

### AnnotationType
`TOKEN_LABEL` | `SPAN_LABEL`

### ContentModality
`TEXT` | `IMAGE` (future: `AUDIO`, `TABLE`, `VIDEO`)

### ConversationType
`chat` | `thread`

### MessageType
`HUMAN` | `AI`

### ActionType
`fieldset` | `analyzer` | `agent`
