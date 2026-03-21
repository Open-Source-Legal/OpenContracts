# Annotation Side Effects on Import

Certain annotation types and fields trigger special behavior when documents are
imported. This page covers the two most important side effects: structural
annotations that produce shared parser data, and `OC_SECTION` annotations that
build a navigable document index.

## Structural Annotations

### What They Are

Structural annotations are parser-generated layout annotations that describe
a document's structure -- headings, sections, paragraphs, tables, figures, etc.
They are created automatically during document parsing and are marked with
`structural = true`.

### Side Effects on Import

When a document with structural annotations is imported (via corpus export or
annotated document import):

1. **Read-only enforcement**: Structural annotations cannot be edited by
   regular users. Only superusers can modify them. This prevents accidental
   changes to parser-generated layout data.

2. **StructuralAnnotationSet creation**: Structural annotations are grouped
   into a `StructuralAnnotationSet` identified by a content hash (SHA-256 of
   the document content). This set includes:
   - The PAWLs parse data (tokens and bounding boxes)
   - The extracted text layer
   - All structural annotations and their relationships
   - Parser name and version metadata

3. **Deduplication across documents**: If two documents have identical content
   (same content hash), they share the same `StructuralAnnotationSet`. On
   import, if a set with the matching hash already exists in the database, it
   is reused rather than duplicated.

4. **Corpus isolation**: Each corpus gets its own copy of structural annotation
   sets. The `StructuralAnnotationSet.duplicate()` method creates
   corpus-specific copies when needed, allowing different embedders per corpus
   without interference.

5. **Structural relationships**: Relationships between structural annotations
   (e.g., a heading "contains" a paragraph) are also marked as structural and
   follow the same immutability and sharing rules.

### In Export Format

In a V2 corpus export, structural annotations appear in two places:

- **`structural_annotation_sets`**: A top-level map keyed by content hash,
  containing the shared annotation data
- **`structural_set_hash`**: A field on each document referencing its
  structural annotation set

This separation avoids duplicating structural data when multiple documents share
the same content.

## Document Index Annotations (`OC_SECTION`)

### What They Are

OpenContracts supports building a hierarchical table of contents *inside* a
document using a special annotation label called `OC_SECTION`. These
annotations represent sections, chapters, or headings and form a navigable tree
in the frontend.

### How the Index Is Built

A document index is a set of annotations that:

1. Share the `OC_SECTION` label
2. Use the `parent_id` field to form a hierarchy (chapters containing sections
   containing subsections)
3. Optionally carry a `long_description` field with markdown content describing
   the section

### Side Effects on Import

When annotations with `annotationLabel = "OC_SECTION"` are imported:

1. **Automatic tree rendering**: The frontend `DocumentAnnotationIndex`
   component detects `OC_SECTION` annotations and renders them as a
   collapsible tree in the document sidebar. No additional configuration is
   needed.

2. **Parent-child hierarchy via `parent_id`**: The importer resolves `parent_id`
   references in a two-pass process:
   - **Pass 1**: All annotations are created, and a mapping from import-local
     IDs to new database IDs is built
   - **Pass 2**: `parent` FK relationships are set using the ID mapping

   This means you can reference parent annotations by their export-local ID and
   the importer handles the remapping.

3. **Click-to-navigate**: Each index entry is anchored to a position in the
   document (via `annotation_json`). Clicking a section in the tree navigates
   to that location.

4. **Expandable markdown descriptions**: If `long_description` is set, the
   section node in the tree can be expanded to show rendered markdown content
   (sanitized with `rehype-sanitize`).

### Creating a Document Index in an Import

There are three ways to create a document index:

| Method | Description |
|--------|-------------|
| **Agent tool** | The `create_document_index` tool lets an LLM agent read a document and propose sections |
| **Corpus export/import** | Include `OC_SECTION` annotations in the export ZIP |
| **Annotated document import** | Include `OC_SECTION` annotations in the `labelled_text` array |

### Label Definition

The `OC_SECTION` label must be defined in `text_labels`:

```json
{
  "OC_SECTION": {
    "id": "label-oc-section",
    "text": "OC_SECTION",
    "label_type": "TOKEN_LABEL",
    "color": "#6366f1",
    "description": "Document section index entry",
    "icon": "tag"
  }
}
```

Use `TOKEN_LABEL` for PDF documents (annotations reference PAWLs tokens) and
`SPAN_LABEL` for plain-text documents (annotations use character offsets).

### Annotation Structure

Each index entry is an annotation in `labelled_text`:

```json
{
  "id": "idx-0",
  "annotationLabel": "OC_SECTION",
  "rawText": "1. Introduction",
  "long_description": "This chapter introduces the parties and key terms.",
  "page": 0,
  "annotation_json": { "start": 0, "end": 16, "text": "1. Introduction" },
  "annotation_type": "SPAN_LABEL",
  "parent_id": null,
  "structural": false
}
```

| Field | Convention |
|-------|-----------|
| `annotationLabel` | Must be `"OC_SECTION"` (the `OC_` prefix is reserved for platform labels) |
| `rawText` | Displayed as the tree node label |
| `long_description` | Rendered as expandable markdown below the title; `null` for no description |
| `page` | 0-based page index for PDFs; `1` for text documents |
| `parent_id` | Export-local ID of the parent section, or `null` for root-level entries |
| `structural` | Should be `false` (index annotations are user/agent-generated) |

### Hierarchy via `parent_id`

Set `parent_id` to the `id` of the parent section annotation to build the tree:

```json
[
  { "id": "ch1", "rawText": "Chapter 1", "parent_id": null },
  { "id": "s1.1", "rawText": "1.1 Definitions", "parent_id": "ch1" },
  { "id": "s1.2", "rawText": "1.2 Scope", "parent_id": "ch1" },
  { "id": "ch2", "rawText": "Chapter 2", "parent_id": null }
]
```

This produces:

```
Chapter 1
+-- 1.1 Definitions
+-- 1.2 Scope
Chapter 2
```

Circular references are detected by the frontend and result in a warning banner.

### Limits

| Limit | Default | Notes |
|-------|---------|-------|
| Max index entries per document | 500 | Controlled by `DOCUMENT_ANNOTATION_INDEX_LIMIT` |
| Max tree depth | 4 | Frontend `maxDepth` prop, configurable per-mount |

## Document-to-Document Relationships

In addition to annotation-level side effects, the bulk ZIP import can create
**document-level relationships** via the `relationships.csv` file. These are
distinct from annotation relationships and represent connections between whole
documents (e.g., "agreement.pdf AMENDS amendment.pdf").

Two relationship types are available:

| Type | When Used |
|------|-----------|
| `RELATIONSHIP` | Default. A labeled, directional link between two documents. |
| `NOTES` | Created when the `notes` column in `relationships.csv` is non-empty. |

Document relationships appear in the corpus UI and can be traversed to navigate
between related documents.

For the complete export format specification, see
[Corpus Export Format Specification](../architecture/corpus-export-format-spec.md).

For the full document annotation index architecture, see
[Document Annotation Index](../architecture/document_annotation_index.md).
