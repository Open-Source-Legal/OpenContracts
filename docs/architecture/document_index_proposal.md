# Document Index Feature - Design Proposal

## Overview

Build a navigable hierarchical index for long documents using annotations with markdown descriptions. The system supports:

1. **Within-document TOC**: Annotations marking sections/chapters with `long_description` (markdown summaries), connected via the existing `parent` FK on Annotation for hierarchy
2. **Corpus-level hybrid view**: Single-doc corpora show the document's annotation index on CorpusHome; multi-doc corpora show the existing document tree with drill-down into per-document annotation indexes
3. **Two creation paths**: (a) Agent reads full document text and creates the index from scratch, (b) Deterministic import via the existing export format extended with `long_description`

---

## Architecture Decisions

### Why `long_description` on Annotation (not a new model)?
- Annotations already have `raw_text` (literal text), `parent` (hierarchy), `annotation_label` (semantic type), and `page` (position)
- Adding `long_description` (nullable TextField) gives markdown summaries without a new model or join
- The existing parent-child tree on Annotation is exactly the hierarchy we need
- Annotations already have permissions, corpus/document association, and GraphQL types

### Why reuse the Annotation `parent` hierarchy?
- `Annotation.parent` FK already exists with `related_name="children"` and CASCADE delete
- The GraphQL AnnotationType already exposes `descendants_tree`, `full_tree`, `subtree` resolvers
- Import pipeline already handles `parent_id` in two-pass import
- No new model or relationship type needed

### Index Entry Convention
- Use a dedicated `AnnotationLabel` with `text="OC_SECTION"` and `label_type=TOKEN_LABEL` (or `SPAN_LABEL` for text docs)
- The `OC_` prefix is a namespace for platform-generated labels (future: `OC_CHAPTER`, `OC_GLOSSARY_ENTRY`, etc.)
- `raw_text` = section title/heading text
- `long_description` = markdown summary of section content
- `parent` FK = hierarchy (Chapter → Section → Subsection)
- `page` = enables "jump to page" navigation
- `json`/`tokens_jsons` = anchors to exact document positions

---

## Implementation Steps

### Phase 1: Backend Data Model

**1.1 Add `long_description` to Annotation model**
- File: `opencontractserver/annotations/models.py`
- Add: `long_description = django.db.models.TextField(null=True, blank=True)` after `raw_text`
- Migration: Simple nullable field addition, zero-downtime, no data migration

**1.2 Expose in GraphQL types**
- File: `config/graphql/annotation_types.py`
- Add `long_description` to `AnnotationType` (auto-resolved from model field)

**1.3 Update GraphQL mutations**
- Allow `long_description` in create/update annotation mutations
- Respect existing permission checks

**1.4 Extend export/import types**
- File: `opencontractserver/types/dicts.py` — Add `long_description: NotRequired[Optional[str]]` to `OpenContractsAnnotationPythonType`
- File: `opencontractserver/utils/importing.py` — Read `long_description` during import
- File: `opencontractserver/utils/export_v2.py` / `etl.py` — Include in export

### Phase 2: Agent Tool for Index Creation

**2.1 New agent tool: `create_document_index`**
- File: `opencontractserver/llms/tools/core_tools.py`
- Agent reads the full document text, identifies logical sections, creates hierarchical index
- Parameters:
  - `document_id`, `corpus_id`, `creator_id`
  - `index_entries`: List of `{title, long_description, page, exact_string, parent_index?}` where `parent_index` references another entry in the same list for hierarchy
  - `corpus_action_id` (optional)
- Behavior:
  1. Creates/reuses "Document Index Entry" label
  2. Finds exact strings in document (reuses existing matching logic)
  3. Creates annotations with `raw_text=title`, `long_description=description`
  4. Sets `parent` FK based on `parent_index` to build hierarchy
  5. Returns list of created annotation IDs
- Requires approval gate

**2.2 Register in tool registry**
- File: `opencontractserver/llms/tools/tool_registry.py`
- `requires_approval=True`, `requires_write_permission=True`

### Phase 3: Frontend — Document Annotation Index Component

**3.1 New GraphQL query**
- File: `frontend/src/graphql/queries.ts`
- `GET_DOCUMENT_ANNOTATION_INDEX` — fetches annotations labeled "Document Index Entry" for a document+corpus, including `long_description`, parent hierarchy, `page`, `raw_text`

**3.2 New component: `DocumentAnnotationIndex`**
- File: `frontend/src/components/corpuses/DocumentAnnotationIndex.tsx`
- Mirrors `DocumentTableOfContents` patterns:
  - Recursive tree rendering from annotation parent-child hierarchy
  - Each node: section title (`raw_text`), expandable markdown description (`long_description`)
  - Click navigates to page/annotation in document viewer
  - Expand/collapse with URL-synced state
  - Filter/search on titles and descriptions
  - Depth limit + circular reference detection

**3.3 Hybrid view in CorpusHome**
- Files: `CorpusHome.tsx`, `CorpusDetailsView.tsx`
- Single-doc corpus → show `DocumentAnnotationIndex` instead of `DocumentTableOfContents`
- Multi-doc corpus → show `DocumentTableOfContents` at top level; clicking a document expands to show its `DocumentAnnotationIndex` inline as nested children
- Seamless drill-down: corpus → document → section → subsection

**3.4 Document viewer integration**
- Clicking an index entry opens document at correct page
- Scrolls to and highlights the target annotation (reuses existing two-phase scroll system)

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
                   label = "Document Index Entry"
                                  │
                                  ▼
                     CorpusHome (hybrid view)
                  ┌─────────────┴──────────────┐
                  │                            │
           1 doc in corpus            N docs in corpus
                  │                            │
      DocumentAnnotationIndex    DocumentTableOfContents
         (section tree)            └── drill into doc ──►
                                     DocumentAnnotationIndex
```

## Migration Impact
- One new nullable TextField on Annotation — zero-downtime
- No existing data affected
- Backward compatible export format (NotRequired field)

## Testing Strategy
- Backend: Test annotation creation with `long_description`, test export/import round-trip
- Agent: Test `create_document_index` tool with sample documents
- Frontend: Component test for `DocumentAnnotationIndex` with mock data
- Integration: E2E test showing index creation and navigation
