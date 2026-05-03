# Document Annotation Index

## Overview

The document annotation index provides a navigable, hierarchical table of
contents for long documents. It is built entirely from annotations — no new
models — using a dedicated `OC_SECTION` label, the existing `parent` FK for
hierarchy, and an optional `long_description` field for markdown summaries.

The frontend renders these as a collapsible tree with page-number badges,
expandable rich-text descriptions, and click-to-navigate behavior.

### Creation Paths

| Path | Entry point | When |
|------|-------------|------|
| **Agent** | `create_document_index` tool | LLM reads the document and proposes sections |
| **Import** | Standard corpus export ZIP | Downstream tools build indexes offline and import them |
| **Manual** | `CreateAnnotation` mutation | User creates `OC_SECTION` annotations through the UI/API |

---

## Architecture Decisions

### Why `long_description` on Annotation (not a new model)?

- Annotations already carry `raw_text` (literal text), `parent` (hierarchy),
  `annotation_label` (semantic type), and `page` (position).
- Adding `long_description` (nullable TextField) gives markdown summaries
  without a new model or join.
- Annotations already have permissions, corpus/document association, and
  GraphQL types — no new permission plumbing needed.

### Why reuse the Annotation `parent` hierarchy?

- `Annotation.parent` FK already exists with `related_name="children"` and
  CASCADE delete.
- The GraphQL `AnnotationType` already exposes `descendants_tree`,
  `full_tree`, `subtree` resolvers.
- The import pipeline already handles `parent_id` in a two-pass import.

### Index Entry Convention

- Uses a dedicated `AnnotationLabel` with `text="OC_SECTION"` and
  `label_type=TOKEN_LABEL` (PDF) or `SPAN_LABEL` (text docs).
- The `OC_` prefix is a reserved namespace for platform-generated labels
  (future: `OC_CHAPTER`, `OC_GLOSSARY_ENTRY`, etc.).

| Annotation field | Index meaning |
|-----------------|---------------|
| `raw_text` | Section title / heading text |
| `long_description` | Markdown summary of section content |
| `parent` FK | Hierarchy (Chapter → Section → Subsection) |
| `page` | Enables "jump to page" navigation |
| `json` / `tokens_jsons` | Anchors to exact document position |

---

## Components

### Backend

- **Model field**: `Annotation.long_description` — nullable TextField
  (`opencontractserver/annotations/models.py`)
- **GraphQL**: Exposed in `AnnotationType`, accepted in `CreateAnnotation` and
  `UpdateAnnotation` mutations
- **Export/Import**: `OpenContractsAnnotationPythonType` includes
  `long_description: NotRequired[Optional[str]]`, handled in `importing.py`,
  `export_v2.py`, and `etl.py`

### Agent Tool: `create_document_index`

- **File**: `opencontractserver/llms/tools/core_tools/document_indexing.py`
- **Parameters**: `document_id`, `corpus_id`, `creator_id`,
  `index_entries` (list of `{title, long_description, page, exact_string,
  parent_index?}`), optional `corpus_action_id`
- **Behavior**:
  1. Creates or reuses `OC_SECTION` label via `ensure_label_and_labelset()`
  2. Finds exact strings in the document (reuses existing matching logic)
  3. Creates annotations with `raw_text=title`, `long_description=description`
  4. Sets `parent` FK based on `parent_index` to build hierarchy (two-pass:
     create all, then wire parents)
  5. Returns list of created annotation IDs
- **Registered** in `tool_registry.py` with `requires_approval=True`,
  `requires_write_permission=True`

### Frontend: `DocumentAnnotationIndex`

- **File**: `frontend/src/components/corpuses/DocumentAnnotationIndex.tsx`
- Renders a tree from `OC_SECTION` annotations for a given document+corpus
- Each node shows section title (`raw_text`), expandable markdown description
  (`long_description` rendered via `ReactMarkdown` with `rehype-sanitize`)
- Click navigates to the document at the annotation's location
- Expand/collapse with URL-synced state, filter/search, depth limit, circular
  reference detection
- WAI-ARIA TreeView keyboard navigation (ArrowLeft/Right/Up/Down +
  Enter/Space)

### Frontend: `DocumentTableOfContents` Integration

- **File**: `frontend/src/components/corpuses/DocumentTableOfContents.tsx`
- Single-doc corpus → skips document header, shows
  `DocumentAnnotationIndex` directly
- Multi-doc corpus → each document node is expandable; expanding mounts
  `DocumentAnnotationIndex` lazily (avoids N+1 queries on mount)

---

## Data Flow

```
              Agent reads document          Import from ZIP
                     │                           │
                     ▼                           ▼
              create_document_index      import_annotations()
                     │                           │
                     └────────────┬──────────────┘
                                  ▼
                        Annotation Model
                   raw_text = "Chapter 1: Intro"
                   long_description = "This chapter..."
                   parent = <parent annotation>
                   page = 1
                   label = "OC_SECTION"
                                  │
                                  ▼
                  DocumentTableOfContents (hybrid view)
                  ┌─────────────┴──────────────┐
                  │                            │
           1 doc in corpus            N docs in corpus
                  │                            │
      DocumentAnnotationIndex    DocumentTableOfContents
         (section tree)            └── expand doc node ──►
                                     DocumentAnnotationIndex
```

---

## Export / Import Format

For details on how document index annotations are represented in the corpus
export ZIP (`data.json`), see the
[Document Index Convention](corpus-export-format-spec.md#document-index-convention)
section of the Corpus Export Format Specification.

That section covers:

- Label definition (`OC_SECTION` in `text_labels`)
- Annotation structure (`labelled_text` entries with `long_description` and
  `parent_id`)
- Hierarchy wiring via `parent_id`
- A complete minimal example (text document)
- Field reference table for index annotations
- Limits and frontend display behavior

---

## Limits

| Limit | Value | Notes |
|-------|-------|-------|
| Max index entries per document | 500 | Controlled by `DOCUMENT_ANNOTATION_INDEX_LIMIT` |
| Max tree depth | 4 (default) | Frontend `maxDepth` prop, configurable per-mount |

---

## Migration Impact

- One nullable TextField on Annotation — zero-downtime.
- No existing data affected.
- Backward-compatible export format (`NotRequired` field).

## Test Coverage

- **Backend**: Annotation creation with `long_description`, PDF and text doc
  paths, hierarchy wiring, validation (self-reference, out-of-range, cycle
  detection), rollback on error
- **Agent tool**: `create_document_index` with sample PAWLS and text documents
- **Frontend**: 14 component tests covering standalone/embedded modes,
  hierarchy, descriptions, loading/error/empty states, filtering
