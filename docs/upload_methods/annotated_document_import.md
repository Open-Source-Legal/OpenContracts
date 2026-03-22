# Annotated Document Import

The annotated document import lets you add a single document with pre-built
annotations directly into an existing corpus. This is useful for
programmatic workflows where an external tool has already analyzed a document
and produced annotation data.

## GraphQL Mutation

**Mutation**: `UploadAnnotatedDocument`

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `targetCorpusId` | ID | Yes | Corpus to import into |
| `documentImportData` | String | Yes | JSON string matching the import schema below |

The import runs asynchronously via a Celery task (`import_document_to_corpus`).

## Import Data Schema

The `documentImportData` JSON string must conform to the
`OpenContractsAnnotatedDocumentImportType` structure:

| Field | Type | Description |
|-------|------|-------------|
| `doc_data` | object | Document export data (same structure as a single entry in `annotated_docs` from a corpus export) |
| `pdf_base64` | string | Base64-encoded document file content |
| `pdf_name` | string | Filename for the document |
| `doc_labels` | map | Document-level label definitions keyed by label name |
| `text_labels` | map | Text annotation label definitions keyed by label name |
| `relationships` | list (optional) | Annotation-to-annotation relationships |

### The `doc_data` Object

This follows the same `OpenContractDocExport` structure used in corpus exports:

| Field | Type | Description |
|-------|------|-------------|
| `title` | string | Document title |
| `content` | string | Full extracted text |
| `description` | string or null | Document description |
| `page_count` | int | Number of pages |
| `pawls_file_content` | list | PAWLs token data (can be empty for text documents) |
| `doc_labels` | list of strings | Document label names to apply |
| `labelled_text` | list | Text annotations (see below) |
| `structural` | bool | Whether this contains structural annotations |

### Annotations in `labelled_text`

Each annotation follows the standard annotation format:

| Field | Type | Description |
|-------|------|-------------|
| `id` | string/int/null | Local ID for cross-referencing within the import |
| `annotationLabel` | string | Label name (must exist in the `text_labels` map) |
| `rawText` | string | The annotated text |
| `page` | int | 0-based page index |
| `annotation_json` | object | Positional data (token refs for PDFs, character offsets for text) |
| `parent_id` | string/int/null | ID of parent annotation (for hierarchical annotations) |
| `annotation_type` | string or null | `"TOKEN_LABEL"` or `"SPAN_LABEL"` |
| `structural` | bool | Whether this is a structural annotation |
| `long_description` | string or null | Markdown description (used for document index entries) |

## Import Process

1. The document file is decoded from base64 and stored
2. Labels are created or matched to existing labels in the corpus's label set
3. The document record is created with extracted text and PAWLs data
4. Annotations are created in two passes:
   - **First pass**: Create all annotation records, building an ID mapping from
     import-local IDs to new database IDs
   - **Second pass**: Wire up `parent` FK relationships using the ID mapping
5. Relationships between annotations are created using the remapped IDs
6. The document is added to the corpus

## Bounding-Box Annotations (`bbox_annotations`)

An optional field that lets external tools provide PDF bounding-box coordinates
instead of PAWLs token indices. At import time, bounding boxes are matched
against PAWLs tokens (center-point containment) and converted to standard
`TOKEN_LABEL` annotations.

This solves the chicken-and-egg problem where annotations need PAWLs token
indices, but token indices require parsing the document first.

### Schema

The `bbox_annotations` array sits alongside `labelled_text` in the import data:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `annotationLabel` | string | Yes | Label name (must exist in `text_labels`) |
| `rawText` | string | Yes | Display text for the annotation |
| `bounds` | object | Yes | Page-keyed bounding rects (see below) |
| `id` | string/int | No | Local ID for `parent_id` cross-references |
| `parent_id` | string/int | No | Parent annotation ID (for hierarchies) |
| `structural` | boolean | No | Default `false` |
| `long_description` | string | No | Markdown content (e.g., for `OC_SECTION`) |

### Bounds Format

`bounds` is a dict keyed by 0-based page number (as string), each value an
array of bounding rectangles in **PDF points** (1/72 inch, origin top-left):

```json
{
  "bounds": {
    "0": [{"top": 72.5, "bottom": 84.3, "left": 50.0, "right": 300.0}],
    "1": [{"top": 72.5, "bottom": 84.3, "left": 50.0, "right": 150.0}]
  }
}
```

Multiple rectangles per page support wrapped or multi-line text. Multi-page
bounds support annotations that span page breaks.

### Resolution Behavior

- A token is matched if its **center point** falls inside any bounding rectangle
- Matched tokens become a standard `TOKEN_LABEL` `annotation_json`
- The input `rawText` is preserved (not replaced by resolved token text)
- If no tokens match on any page, the annotation is dropped with a warning
- `parent_id` cross-references work across `bbox_annotations` and `labelled_text`

## Use Cases

- **External NLP pipelines**: Run annotation models outside OpenContracts and
  import the results
- **Data migration**: Move annotated documents from another system
- **Programmatic index building**: Create documents with `OC_SECTION`
  annotations for navigable document indexes (see
  [Annotation Side Effects](annotation_side_effects.md))
- **Batch annotation**: Pre-annotate documents before human review

## Relation to Corpus Export Format

The annotated document import schema is intentionally compatible with the corpus
export format. A single entry from a corpus export's `annotated_docs` map can be
used directly as the `doc_data` field, making it straightforward to extract
individual documents from an export and re-import them elsewhere.

For the full annotation format specification, see the
[Corpus Export Format Specification](../architecture/corpus-export-format-spec.md).
