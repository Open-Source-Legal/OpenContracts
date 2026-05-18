# Core Data Model

This document provides a high-level overview of OpenContracts' core Django models, their relationships, and primary use cases.

---

## Entity Relationship Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                    DOCUMENT LAYER                                    │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│  ┌──────────────┐         ┌──────────────┐         ┌──────────────────────────┐    │
│  │   Document   │◄───────►│    Corpus    │◄───────►│      CorpusFolder        │    │
│  │              │  M:N    │              │  1:N    │   (hierarchical tree)    │    │
│  └──────┬───────┘         └──────┬───────┘         └──────────────────────────┘    │
│         │                        │                                                  │
│         │ 1:N                    │ 1:N                                              │
│         ▼                        ▼                                                  │
│  ┌──────────────┐         ┌──────────────┐                                         │
│  │ DocumentPath │         │  LabelSet    │                                         │
│  │ (versioning) │         │              │                                         │
│  └──────────────┘         └──────┬───────┘                                         │
│                                  │ M:N                                              │
│                                  ▼                                                  │
│                           ┌──────────────┐                                         │
│                           │AnnotationLabel│                                         │
│                           └──────────────┘                                         │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                  ANNOTATION LAYER                                    │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│  ┌──────────────┐         ┌──────────────┐         ┌──────────────────────────┐    │
│  │  Annotation  │◄───────►│ Relationship │         │ StructuralAnnotationSet  │    │
│  │              │  M:N    │ (annotation) │         │   (corpus-isolated)      │    │
│  └──────┬───────┘         └──────────────┘         └──────────────────────────┘    │
│         │                                                                           │
│         │ 1:N                                                                       │
│         ▼                                                                           │
│  ┌──────────────┐                                                                  │
│  │     Note     │                                                                  │
│  │ (comments)   │                                                                  │
│  └──────────────┘                                                                  │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────┐
│                               DOCUMENT RELATIONSHIPS                                 │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│  ┌──────────────┐                           ┌──────────────┐                       │
│  │   Document   │◄─────────────────────────►│   Document   │                       │
│  │   (source)   │    DocumentRelationship   │   (target)   │                       │
│  └──────────────┘                           └──────────────┘                       │
│                                                                                     │
│  Types: RELATIONSHIP (labeled link) | NOTES (free-form notes between docs)         │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                  ANALYSIS LAYER                                      │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│  ┌──────────────┐         ┌──────────────┐         ┌──────────────┐               │
│  │   Analyzer   │────────►│   Analysis   │────────►│  Annotation  │               │
│  │  (template)  │  1:N    │  (instance)  │  1:N    │ (AI-created) │               │
│  └──────────────┘         └──────────────┘         └──────────────┘               │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                  EXTRACT LAYER                                       │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│  ┌──────────────┐         ┌──────────────┐         ┌──────────────┐               │
│  │   Fieldset   │────────►│    Column    │         │   Datacell   │               │
│  │ (schema def) │  1:N    │  (field def) │◄───────►│   (value)    │               │
│  └──────────────┘         └──────────────┘   1:N   └──────────────┘               │
│         │                                                 │                        │
│         │ 1:N                                             │ N:1                    │
│         ▼                                                 ▼                        │
│  ┌──────────────┐                                 ┌──────────────┐               │
│  │   Extract    │◄───────────────────────────────►│   Document   │               │
│  │  (job run)   │              M:N                │              │               │
│  └──────────────┘                                 └──────────────┘               │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Core Models

### Document Layer

#### Document
**Location:** `opencontractserver/documents/models.py`

The central model representing an uploaded document (typically PDF).

| Field | Description |
|-------|-------------|
| `title` | Document title |
| `description` | Document description |
| `pdf_file` | The uploaded PDF file |
| `txt_extract_file` | Extracted plain text |
| `pawls_parse_file` | PAWLS JSON with token positions |
| `page_count` | Number of pages |
| `file_type` | MIME type (default: `application/pdf`) |
| `version_tree_id` | Groups all versions of the same logical document |
| `is_current` | True for the newest version |

**Key relationships:**
- Many-to-many with `Corpus` via `DocumentPath` (sole source of truth for corpus membership)
- The legacy M2M field `Corpus.documents` has been removed (Issue #835)
- One-to-many with `Annotation`
- One-to-many with `DocumentPath` (version history and corpus membership)
- Self-referential via `DocumentRelationship`

**Adding documents to corpuses:**
Use `corpus.add_document(document=doc, user=user)` or `CorpusObjsService.add_document_to_corpus()`.
Never use `corpus.documents.add()` directly as it bypasses versioning and creates inconsistent state.

---

#### Corpus
**Location:** `opencontractserver/corpuses/models.py`

A collection of documents with shared labels and analysis configuration.

| Field | Description |
|-------|-------------|
| `title` | Corpus name |
| `description` | Corpus description |
| `label_set` | Associated label definitions |
| `is_public` | Whether publicly accessible |

**Key relationships:**
- Many-to-many with `Document`
- One-to-many with `CorpusFolder`
- One-to-many with `Analysis`
- One-to-many with `Extract`

---

#### CorpusFolder
**Location:** `opencontractserver/corpuses/models.py`

Hierarchical folder structure within a corpus for organizing documents.

| Field | Description |
|-------|-------------|
| `title` | Folder name |
| `parent` | Parent folder (TreeNode) |
| `corpus` | Owning corpus |

**Uses:** Provides file-system-like organization for documents within a corpus.

---

#### DocumentPath
**Location:** `opencontractserver/documents/models.py`

Tracks document lifecycle events in the dual-tree versioning architecture.

| Field | Description |
|-------|-------------|
| `document` | Points to specific Document version |
| `corpus` | Owning corpus |
| `folder` | Current folder location |
| `path` | Full filesystem-like path |
| `version_number` | Increments on content changes |
| `is_current` | True for current filesystem state |
| `is_deleted` | Soft delete flag |

**Uses:** Enables version history, move tracking, and soft deletion.

---

#### DocumentRelationship
**Location:** `opencontractserver/documents/models.py`

Represents relationships between documents (e.g., notes, links).

| Field | Description |
|-------|-------------|
| `source_document` | Source document |
| `target_document` | Target document |
| `relationship_type` | `"RELATIONSHIP"` or `"NOTES"` |
| `annotation_label` | Label defining relationship meaning (required for RELATIONSHIP type) |
| `corpus` | Optional corpus scope |
| `data` | JSON payload (for notes content, metadata) |

**Uses:**
- **RELATIONSHIP type:** Labeled, semantic links between documents (e.g., "references", "amends", "supersedes")
- **NOTES type:** Free-form notes/comments attached between two documents

---

### Annotation Layer

#### AnnotationLabel
**Location:** `opencontractserver/annotations/models.py`

Defines a type of annotation or relationship with visual styling.

| Field | Description |
|-------|-------------|
| `text` | Label display name |
| `label_type` | `TOKEN_LABEL`, `SPAN_LABEL`, `DOC_TYPE_LABEL`, or `RELATIONSHIP_LABEL` |
| `color` | Hex color for UI |
| `icon` | Icon identifier |
| `description` | Label description |

---

#### LabelSet
**Location:** `opencontractserver/annotations/models.py`

A collection of labels that can be applied to a corpus.

| Field | Description |
|-------|-------------|
| `title` | Labelset name |
| `description` | Labelset description |
| `annotation_labels` | M2M to AnnotationLabel |

---

#### Annotation
**Location:** `opencontractserver/annotations/models.py`

A labeled region within a document.

| Field | Description |
|-------|-------------|
| `document` | Parent document |
| `corpus` | Parent corpus |
| `annotation_label` | The label applied |
| `annotation_type` | `TOKEN_LABEL` or `SPAN_LABEL` |
| `page` | Page number |
| `raw_text` | Extracted text content |
| `json` | Position data (see [annotation_json.md](./annotation_json.md)) |
| `structural` | True for parser-created structural annotations |
| `analysis` | If created by an analysis |

**Uses:** Highlights and labels specific regions of text/tokens in documents.

---

#### Relationship (Annotation)
**Location:** `opencontractserver/annotations/models.py`

Links annotations together (not to be confused with DocumentRelationship).

| Field | Description |
|-------|-------------|
| `relationship_label` | Label defining the relationship |
| `source_annotations` | M2M source annotations |
| `target_annotations` | M2M target annotations |
| `document` | Parent document |
| `corpus` | Parent corpus |
| `structural` | True for structural relationships |

**Uses:** Connects annotations (e.g., "clause X references clause Y").

---

#### StructuralAnnotationSet
**Location:** `opencontractserver/annotations/models.py`

Immutable, corpus-isolated structural annotations for a document.

| Field | Description |
|-------|-------------|
| `content_hash` | Format: `{sha256_hash}_{corpus_id}` (max 128 chars) |
| `parser_name` | Parser that created annotations |
| `parser_version` | Parser version |
| `pawls_parse_file` | Corpus-specific PAWLS data |

**Uses:** Each corpus gets its own copy of structural annotations when a document is added. This ensures complete corpus isolation - no data is shared across corpus boundaries. When a document is added to a new corpus, its structural annotation set is duplicated.

---

#### Note
**Location:** `opencontractserver/annotations/models.py`

User comments attached to documents or annotations.

| Field | Description |
|-------|-------------|
| `title` | Note title |
| `content` | Markdown content |
| `document` | Parent document |
| `annotation` | Optional parent annotation |
| `parent` | Parent note (for threading) |

---

### Analysis Layer

#### Analyzer
**Location:** `opencontractserver/analyzer/models.py`

A template/definition for document analysis (NLP pipeline, ML model, etc.).

| Field | Description |
|-------|-------------|
| `analyzer_id` | Unique identifier |
| `description` | What the analyzer does |
| `task_name` | Celery task to execute |
| `host_gremlin` | Gremlin endpoint (if applicable) |

---

#### Analysis
**Location:** `opencontractserver/analyzer/models.py`

An instance of running an Analyzer against a corpus.

| Field | Description |
|-------|-------------|
| `analyzer` | The analyzer template |
| `corpus` | Target corpus |
| `analyzed_documents` | Documents processed |
| `status` | Processing status |

**Uses:** Tracks ML/NLP analysis runs and their created annotations.

---

### Extract Layer

#### Fieldset
**Location:** `opencontractserver/extracts/models.py`

Schema definition for structured data extraction.

| Field | Description |
|-------|-------------|
| `name` | Fieldset name |
| `description` | What data is extracted |

---

#### Column
**Location:** `opencontractserver/extracts/models.py`

A single field definition within a Fieldset.

| Field | Description |
|-------|-------------|
| `fieldset` | Parent fieldset |
| `name` | Column name |
| `query` | Extraction query/prompt |
| `output_type` | Expected data type |

---

#### Extract
**Location:** `opencontractserver/extracts/models.py`

A job that extracts structured data from documents using a Fieldset.

| Field | Description |
|-------|-------------|
| `corpus` | Source corpus |
| `fieldset` | Schema to use |
| `documents` | M2M target documents |

---

#### Datacell
**Location:** `opencontractserver/extracts/models.py`

A single extracted value for a Column from a Document.

| Field | Description |
|-------|-------------|
| `column` | The field definition |
| `document` | Source document |
| `data` | Extracted value (JSON) |
| `sources` | M2M annotations supporting the value |

---

## Permission Model

OpenContracts uses django-guardian for object-level permissions.

| Model | Permission Model |
|-------|------------------|
| Document | Direct guardian permissions |
| Corpus | Direct guardian permissions |
| DocumentRelationship | Direct guardian permissions |
| Annotation | Inherits from document + corpus |
| Relationship (annotation) | Inherits from document + corpus |

For annotations and annotation relationships:
```
Effective Permission = MIN(document_permission, corpus_permission)
```

See [consolidated_permissioning_guide.md](../../permissioning/consolidated_permissioning_guide.md) for details.

---

## Related Documentation

- [Annotation JSON Schemas](./annotation_json.md) - JSON payload formats for annotations
- [Document Versioning](../document_versioning.md) - Dual-tree versioning architecture
- [Structural vs Non-Structural Annotations](../structural_vs_non_structural_annotations.md) - Parser-created vs user-created
- [Permissioning Guide](../../permissioning/consolidated_permissioning_guide.md) - Full permission system documentation
