# Bulk ZIP Import

The bulk ZIP import allows uploading many documents at once, preserving folder
structure from the ZIP archive. It also supports optional metadata and
relationship CSV files to set document titles/descriptions and create
inter-document relationships automatically.

## Overview

Upload a ZIP file containing documents organized in folders. The folder
structure is preserved in the target corpus. Two optional CSV files at the ZIP
root provide metadata overrides and document-to-document relationships.

**GraphQL Mutation**: `ImportZipToCorpus`

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `base64FileString` | String | Yes | Base64-encoded ZIP file |
| `corpusId` | ID | Yes | Target corpus |
| `targetFolderId` | ID | No | Subfolder to import into |
| `titlePrefix` | String | No | Prefix prepended to all document titles |
| `description` | String | No | Description applied to all documents |
| `customMeta` | GenericScalar | No | Custom metadata applied to all documents |
| `makePublic` | Boolean | Yes | Public visibility for imported documents |

The import runs asynchronously via Celery and returns a `jobId` for progress
tracking.

## ZIP File Structure

A typical ZIP for import:

```
my-import.zip
+-- contracts/
|   +-- legal/
|   |   +-- agreement.pdf
|   +-- financial/
|       +-- report.pdf
+-- docs/
|   +-- amendment.pdf
+-- readme.txt
+-- meta.csv             (optional)
+-- relationships.csv    (optional)
```

### Supported Document Types in ZIP

All file types registered in the pipeline are accepted. Currently:

- PDF (`.pdf`)
- Word (`.docx`)
- Plain Text (`.txt`)

### Skipped Files

The following are automatically skipped:

- Hidden files (names starting with `.`)
- macOS metadata (`__MACOSX/`, `.DS_Store`)
- Files exceeding size limits
- Unsupported file types
- The `meta.csv` and `relationships.csv` control files themselves

## Metadata File (`meta.csv`)

An optional CSV file at the ZIP root that overrides document titles and
descriptions. Accepted filenames (priority order): `meta.csv`, `META.csv`,
`metadata.csv`, `METADATA.csv`.

### Schema

| Column | Required | Description |
|--------|----------|-------------|
| `source_path` | Yes | Relative path within the ZIP |
| `title` | No | Custom document title |
| `description` | No | Custom document description |

### Example

```csv
source_path,title,description
contracts/legal/agreement.pdf,Master Services Agreement,The main services contract
contracts/financial/report.pdf,Q4 Financial Report,Quarterly financial summary
docs/amendment.pdf,Amendment #1,First amendment to MSA
```

### Behavior

- Empty cells are ignored (defaults are used instead)
- Not all documents need metadata entries -- partial coverage is fine
- If a `titlePrefix` is provided in the mutation, it is prepended to the
  metadata title (e.g., "2024 - Master Services Agreement")

## Relationships File (`relationships.csv`)

An optional CSV file at the ZIP root that creates document-to-document
relationships. Must be named `relationships.csv` or `RELATIONSHIPS.csv`.

### Schema

| Column | Required | Description |
|--------|----------|-------------|
| `source_path` | Yes | Path to source document (relative to ZIP root) |
| `relationship_label` | Yes | Relationship label text (e.g., "AMENDS") |
| `target_path` | Yes | Path to target document (relative to ZIP root) |
| `notes` | No | If present, creates a NOTES relationship instead of RELATIONSHIP |

### Example

```csv
source_path,relationship_label,target_path,notes
contracts/legal/agreement.pdf,AMENDS,docs/amendment.pdf,Amendment to main contract
docs/amendment.pdf,AMENDED_BY,contracts/legal/agreement.pdf,
contracts/legal/agreement.pdf,REFERENCES,contracts/financial/report.pdf,
```

### Path Normalization

Paths in CSV files are normalized to a canonical form:

- Backslashes converted to forward slashes
- Leading `./` removed
- Leading slashes normalized
- Duplicate slashes collapsed

All of these reference the same document:

```
contracts/agreement.pdf
/contracts/agreement.pdf
./contracts/agreement.pdf
contracts\agreement.pdf
```

Path traversal (`..`) is rejected for security.

### Cross-batch Relationships

An endpoint that does not match a file inside the current ZIP is resolved
against documents **already in the corpus** (matched by their path within the
corpus, which equals the ZIP-relative path when no target folder is used). This
lets a `relationships.csv` connect documents that were imported in **separate
batches** — you can upload a ZIP containing *only* a `relationships.csv` to wire
together documents already present in the corpus.

Resolution order for each endpoint:

1. A document imported in the current ZIP (same archive), then
2. A current, non-deleted document already in the corpus that you can access.

Only documents you can already see in the corpus are eligible, so cross-batch
resolution never exposes a document you lacked access to. An endpoint that
matches neither is skipped (and reported), exactly as before.

## Annotation Sidecars

A document may ship a co-located JSON **sidecar** (same name, `.json`
extension — e.g. `agreement.pdf` + `agreement.json`) describing producer
annotations to attach. Each annotation is a *dumb anchor*: a `label` + the
`rawText` to find, plus a location hint (PDF `page` + `bbox`, or text
`start`/`end`). The document is parsed normally and the annotations are
re-anchored onto the freshly-produced text/PAWLs layer after ingest, so the
anchors survive re-parsing.

### Sidecar Schema

```json
{
  "annotations": [
    {
      "id": 1,
      "label": "OC_SECTION",
      "rawText": "Article 1 — Definitions",
      "page": 0,
      "bbox": {"left": 50, "top": 50, "right": 300, "bottom": 70},
      "link_url": "https://example.com/ref",
      "data": {"canonical_name": "France", "lat": 46.0, "lng": 2.0}
    },
    {
      "id": 2,
      "label": "OC_CLAUSE",
      "rawText": "indemnification obligations",
      "start": 1234,
      "end": 1261
    }
  ],
  "doc_labels": ["Contract"],
  "relationships": [
    {
      "id": "r1",
      "relationshipLabel": "OC_PARENT_CHILD",
      "source_annotation_ids": [1],
      "target_annotation_ids": [2]
    }
  ]
}
```

| Field | Scope | Description |
|-------|-------|-------------|
| `annotations[].label` | required | Resolves against `labels.json`/the corpus label set |
| `annotations[].rawText` | required | The text to (re-)anchor onto — the source of truth |
| `annotations[].page` + `bbox` | PDF | Location hint for token-based anchoring |
| `annotations[].start` + `end` | text | Character-offset hint for span anchoring |
| `annotations[].link_url` | optional | Click-through target for `OC_URL` hyperlink annotations |
| `annotations[].data` | optional | Structured sidecar persisted to `Annotation.data` (e.g. geocoded `OC_COUNTRY`/`OC_STATE`/`OC_CITY` payloads) |
| `relationships[]` | optional | Annotation-to-annotation edges (see below) |

### Annotation-to-annotation Relationships

The optional `relationships` list declares edges **between annotations in the
same sidecar**. Each entry carries a `relationshipLabel` (auto-created as a
`RELATIONSHIP_LABEL` if it doesn't exist — e.g. `OC_PARENT_CHILD`,
`OC_SUBTREE_GROUP`) and `source_annotation_ids` / `target_annotation_ids` that
reference the sidecar annotations' own `id`s. Relationships are wired after the
annotations are re-anchored, using the producer-id → new-annotation map. An edge
whose endpoints did not survive anchoring is dropped and recorded on the import
report, never silently lost.

## Security Constraints

| Constraint | Default | Description |
|------------|---------|-------------|
| `ZIP_MAX_FILE_COUNT` | 1,000 | Max files per ZIP |
| `ZIP_MAX_TOTAL_SIZE_BYTES` | 500 MB | Max uncompressed total size |
| `ZIP_MAX_SINGLE_FILE_SIZE_BYTES` | 100 MB | Max single file size |
| `ZIP_MAX_COMPRESSION_RATIO` | 100:1 | Zip bomb detection threshold |
| `ZIP_MAX_FOLDER_DEPTH` | 20 | Max nesting depth |
| `ZIP_MAX_FOLDER_COUNT` | 500 | Max folders created |
| `ZIP_MAX_PATH_COMPONENT_LENGTH` | 255 | Max filename length |
| `ZIP_MAX_PATH_LENGTH` | 1,024 | Max total path length |

All limits are configurable via Django settings.

## Import Phases

The import proceeds through four phases:

### Phase 1: Validation

The ZIP is scanned for security violations (size limits, zip bombs, path
traversal) before any files are extracted. A `ZipManifest` is produced listing
valid files, skipped files, and any errors.

### Phase 2: Folder Creation

Folder structure from the ZIP is created in the corpus in a single transaction.
Existing folders with matching names are reused, not duplicated.

### Phase 3: Document Import

Each valid file is extracted and created as a document. If a document path
already exists in the corpus, a new version is created (upversioning) rather
than failing.

### Phase 4: Relationship Creation

If a `relationships.csv` is present, document relationships are created.
Annotation labels are created or reused via the corpus's label set. Missing
source/target documents are logged and skipped -- a malformed relationships file
does not fail the overall import.

## Flat ZIP Upload (Without Corpus)

There is also a simpler `UploadDocumentsZip` mutation that uploads a ZIP of
documents without targeting a specific corpus and without preserving folder
structure. Documents are created as standalone items. The same security
constraints apply.

## Error Handling

The import uses graceful degradation:

- **Validation failures** (zip bomb, too many files) block the entire import
- **Individual file errors** (unsupported type, too large) skip that file and
  continue
- **Relationship errors** (missing source/target document) skip that
  relationship and continue
- The import result includes detailed counts of processed, skipped, errored,
  and upversioned files

For implementation details (code snippets, task result schema, file locations,
and testing commands), see the
[Bulk Import Architecture](../architecture/bulk-import.md).
