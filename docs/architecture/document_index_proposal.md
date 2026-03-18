# Document Annotation Index — Architecture Reference

## Overview

The document annotation index provides a navigable hierarchical table of contents for long documents using annotations with markdown descriptions. The system supports:

1. **Within-document TOC**: Annotations marking sections/chapters with `long_description` (markdown summaries), connected via the existing `parent` FK on Annotation for hierarchy
2. **Corpus-level hybrid view**: Single-doc corpora show the document's annotation index directly; multi-doc corpora show the existing document tree with drill-down into per-document annotation indexes
3. **Two creation paths**: (a) Agent reads full document text and creates the index via `create_document_index`, (b) Deterministic import via the existing export format extended with `long_description`

---

## Architecture Decisions

### Why `long_description` on Annotation (not a new model)?
- Annotations already have `raw_text` (literal text), `parent` (hierarchy), `annotation_label` (semantic type), and `page` (position)
- Adding `long_description` (nullable TextField) gives markdown summaries without a new model or join
- The existing parent-child tree on Annotation is exactly the hierarchy needed
- Annotations already have permissions, corpus/document association, and GraphQL types

### Why reuse the Annotation `parent` hierarchy?
- `Annotation.parent` FK already exists with `related_name="children"` and CASCADE delete
- The GraphQL AnnotationType already exposes `descendants_tree`, `full_tree`, `subtree` resolvers
- Import pipeline already handles `parent_id` in two-pass import
- No new model or relationship type needed

### Index Entry Convention
- Uses a dedicated `AnnotationLabel` with `text="OC_SECTION"` and `label_type=TOKEN_LABEL` (or `SPAN_LABEL` for text docs)
- The `OC_` prefix is a namespace for platform-generated labels (future: `OC_CHAPTER`, `OC_GLOSSARY_ENTRY`, etc.)
- `raw_text` = section title/heading text
- `long_description` = markdown summary of section content
- `parent` FK = hierarchy (Chapter → Section → Subsection)
- `page` = enables "jump to page" navigation
- `json`/`tokens_jsons` = anchors to exact document positions

---

## Components

### Backend Data Model
- **Model field**: `Annotation.long_description` — nullable TextField (`opencontractserver/annotations/models.py`)
- **GraphQL**: Exposed in `AnnotationType`, accepted in `CreateAnnotation` and `UpdateAnnotation` mutations
- **Export/Import**: `OpenContractsAnnotationPythonType` includes `long_description: NotRequired[Optional[str]]`, handled in `importing.py`, `export_v2.py`, and `etl.py`

### Agent Tool: `create_document_index`
- **File**: `opencontractserver/llms/tools/core_tools.py`
- **Parameters**: `document_id`, `corpus_id`, `creator_id`, `index_entries` (list of `{title, long_description, page, exact_string, parent_index?}`), optional `corpus_action_id`
- **Behavior**:
  1. Creates/reuses `OC_SECTION` label via `ensure_label_and_labelset()`
  2. Finds exact strings in document (reuses existing matching logic)
  3. Creates annotations with `raw_text=title`, `long_description=description`
  4. Sets `parent` FK based on `parent_index` to build hierarchy (two-pass: create all, then wire parents)
  5. Returns list of created annotation IDs
- **Registered** in `tool_registry.py` with `requires_approval=True`, `requires_write_permission=True`

### Frontend: `DocumentAnnotationIndex`
- **File**: `frontend/src/components/corpuses/DocumentAnnotationIndex.tsx`
- Renders a tree from `OC_SECTION` annotations for a given document+corpus
- Each node shows section title (`raw_text`), expandable markdown description (`long_description` rendered via `ReactMarkdown` with `rehype-sanitize`)
- Click navigates to document at the annotation's location
- Expand/collapse with URL-synced state, filter/search, depth limit, circular reference detection
- WAI-ARIA TreeView keyboard navigation (ArrowLeft/Right/Up/Down + Enter/Space)

### Frontend: `DocumentTableOfContents` Integration
- **File**: `frontend/src/components/corpuses/DocumentTableOfContents.tsx`
- Single-doc corpus → skips document header, shows `DocumentAnnotationIndex` directly
- Multi-doc corpus → each document node is expandable; expanding mounts `DocumentAnnotationIndex` lazily (avoids N+1 queries on mount)

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

## Migration Impact
- One nullable TextField on Annotation — zero-downtime
- No existing data affected
- Backward compatible export format (NotRequired field)

## Test Coverage
- **Backend**: Annotation creation with `long_description`, PDF and text doc paths, hierarchy wiring, validation (self-reference, out-of-range, cycle detection), rollback on error
- **Agent tool**: `create_document_index` with sample PAWLS and text documents
- **Frontend**: 14 component tests covering standalone/embedded modes, hierarchy, descriptions, loading/error/empty states, filtering
