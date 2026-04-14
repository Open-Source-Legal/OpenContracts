# Building Document Imports for OpenContracts (with CAML Descriptions)

This guide walks through building a complete document import for OpenContracts — from simple document uploads to fully annotated imports with CAML-powered corpus articles. It covers the three import mechanisms, the sidecar annotation format, and how to author CAML descriptions.

---

## Table of Contents

1. [Import Methods Overview](#1-import-methods-overview)
2. [Bulk ZIP Import (Documents + Folders)](#2-bulk-zip-import)
3. [Sidecar Annotation Files](#3-sidecar-annotation-files)
4. [Labels File](#4-labels-file)
5. [Annotation JSON Formats](#5-annotation-json-formats)
6. [PAWLs Token Format](#6-pawls-token-format)
7. [Corpus Export/Import (Full Roundtrip)](#7-corpus-exportimport)
8. [CAML Corpus Descriptions](#8-caml-corpus-descriptions)
9. [Complete Worked Example](#9-complete-worked-example)
10. [Reference: Security Constraints](#10-reference-security-constraints)

---

## 1. Import Methods Overview

OpenContracts supports three import paths, each suited to different workflows:

| Method | Mutation | Best For |
|--------|----------|----------|
| **Bulk ZIP Import** | `ImportZipToCorpus` | Adding many documents at once, preserving folder structure, optional metadata/relationships |
| **Annotated Document Import** | `UploadAnnotatedDocument` | Programmatic import of a single document with pre-built annotations |
| **Corpus Export/Import** | `UploadCorpusImportZip` | Full corpus backup/restore including annotations, labels, folders, config |

All three run asynchronously via Celery and return a `jobId` for progress tracking.

### Supported Document Formats

| Format | Extension | MIME Type |
|--------|-----------|-----------|
| PDF | `.pdf` | `application/pdf` |
| Plain Text | `.txt` | `text/plain` |
| Word | `.docx` | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` |

The set of supported types is dynamic — query the `supportedMimeTypes` GraphQL endpoint for the current list.

---

## 2. Bulk ZIP Import

### ZIP Layout

```
my-import.zip
├── contracts/
│   ├── legal/
│   │   ├── agreement.pdf
│   │   └── agreement.json       ← sidecar annotation file (optional)
│   └── financial/
│       └── report.pdf
├── docs/
│   └── amendment.pdf
├── labels.json                   ← label definitions (required if sidecars used)
├── meta.csv                      ← document metadata overrides (optional)
└── relationships.csv             ← inter-document relationships (optional)
```

**Key rules:**
- Folder structure is preserved in the corpus
- Hidden files (`.DS_Store`, `__MACOSX/`) are skipped automatically
- Unsupported file types are skipped (not failed)
- If a document path already exists in the corpus, it is upversioned (not duplicated)

### Metadata CSV (`meta.csv`)

Optional. Overrides document titles and descriptions. Accepted filenames: `meta.csv`, `META.csv`, `metadata.csv`, `METADATA.csv`.

```csv
source_path,title,description
contracts/legal/agreement.pdf,Master Services Agreement,The main services contract
contracts/financial/report.pdf,Q4 Financial Report,Quarterly financial summary
```

- Empty cells are ignored (defaults used)
- Partial coverage is fine — not every document needs an entry
- If `titlePrefix` is set in the mutation, it prepends the metadata title

### Relationships CSV (`relationships.csv`)

Optional. Creates document-to-document relationships. Named `relationships.csv` or `RELATIONSHIPS.csv`.

```csv
source_path,relationship_label,target_path,notes
contracts/legal/agreement.pdf,AMENDS,docs/amendment.pdf,Amendment to main contract
docs/amendment.pdf,AMENDED_BY,contracts/legal/agreement.pdf,
```

**Path normalization** is applied automatically:
- Backslashes → forward slashes
- Leading `./` and `/` removed
- Duplicate slashes collapsed
- Path traversal (`..`) rejected

### GraphQL Mutation

```graphql
mutation ImportZip($file: String!, $corpusId: ID!, $makePublic: Boolean!) {
  importZipToCorpus(
    base64FileString: $file
    corpusId: $corpusId
    targetFolderId: null        # optional: import into subfolder
    titlePrefix: ""             # optional: prefix for all titles
    description: ""             # optional: shared description
    customMeta: null            # optional: JSON metadata
    makePublic: $makePublic
  ) {
    ok
    message
    jobId
  }
}
```

### Import Phases

1. **Validation** — Security checks (zip bombs, size limits, path traversal)
2. **Folder Creation** — Directory structure recreated in corpus (reuses existing folders)
3. **Document Import** — Files extracted, documents created, sidecars applied
4. **Relationship Creation** — `relationships.csv` parsed, relationships wired up

---

## 3. Sidecar Annotation Files

A sidecar file is a JSON file with the **same stem** as a document file, placed in the **same directory** inside the ZIP:

```
contracts/agreement.pdf    ← document
contracts/agreement.json   ← sidecar (annotations for this document)
```

Sidecar files are detected automatically by stem-matching during ZIP validation. They are **not** treated as regular document uploads.

### Sidecar JSON Structure

The sidecar follows the `OpenContractDocExport` schema:

```json
{
  "title": "Master Services Agreement",
  "content": "Full extracted text of the document...",
  "description": "Main services contract between parties",
  "page_count": 12,
  "pawls_file_content": [],
  "doc_labels": ["Commercial Contract"],
  "labelled_text": [
    {
      "id": "annot-1",
      "annotationLabel": "PARTY_NAME",
      "rawText": "Acme Corporation",
      "page": 0,
      "annotation_json": {
        "start": 145,
        "end": 162,
        "text": "Acme Corporation"
      },
      "annotation_type": "SPAN_LABEL",
      "parent_id": null,
      "structural": false,
      "long_description": null
    }
  ],
  "relationships": [
    {
      "id": "rel-1",
      "relationshipLabel": "REFERENCES",
      "source_annotation_ids": ["annot-1"],
      "target_annotation_ids": ["annot-2"],
      "structural": false
    }
  ]
}
```

### Field Reference

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | string | Yes | Document title |
| `content` | string | Yes | Full extracted text |
| `description` | string/null | No | Document description |
| `page_count` | int | Yes | Number of pages |
| `pawls_file_content` | list | Yes | PAWLs token data (empty `[]` for text docs) |
| `doc_labels` | list of strings | No | Document-level label names to apply |
| `labelled_text` | list | No | Text/token annotations |
| `relationships` | list | No | Annotation-to-annotation relationships |
| `structural` | bool | No | Whether annotations are structural (parser-generated) |
| `skip_pipeline` | bool | No | If `true`, skip parsing pipeline on import |

### Annotation Fields

Each entry in `labelled_text`:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string/int/null | No | Local ID for cross-referencing within this import |
| `annotationLabel` | string | Yes | Label name (must exist in `labels.json`) |
| `rawText` | string | Yes | The annotated text content |
| `page` | int | Yes | 0-based page index |
| `annotation_json` | object | Yes | Positional data (format depends on type) |
| `annotation_type` | string | Yes | `"TOKEN_LABEL"` or `"SPAN_LABEL"` |
| `parent_id` | string/int/null | No | ID of parent annotation (for hierarchical trees) |
| `structural` | bool | No | Whether parser-generated |
| `long_description` | string/null | No | Markdown description (for document index entries) |
| `content_modalities` | list of strings | No | `["TEXT"]`, `["IMAGE"]`, or `["TEXT", "IMAGE"]` |

### Import Process

Annotations are imported in **two passes**:
1. **Pass 1**: Create all annotation records, building an ID mapping from import-local IDs → new database PKs
2. **Pass 2**: Wire up `parent` FK relationships using the ID mapping

Then relationships are created using the remapped annotation IDs.

### Requirements

- A `labels.json` file **must** be present at the ZIP root if any sidecar contains annotations
- Every `annotationLabel` value in a sidecar must have a matching entry in `labels.json`
- Missing labels cause those annotations to be silently skipped (with a warning in the result)

---

## 4. Labels File

A `labels.json` file at the ZIP root defines all labels used across all sidecar files.

```json
{
  "text_labels": {
    "PARTY_NAME": {
      "id": "label-1",
      "text": "PARTY_NAME",
      "label_type": "TOKEN_LABEL",
      "color": "#FF6B6B",
      "description": "Name of a contracting party",
      "icon": "tag"
    },
    "EFFECTIVE_DATE": {
      "id": "label-2",
      "text": "EFFECTIVE_DATE",
      "label_type": "SPAN_LABEL",
      "color": "#4ECDC4",
      "description": "Date the contract takes effect",
      "icon": "calendar"
    },
    "REFERENCES": {
      "id": "label-3",
      "text": "REFERENCES",
      "label_type": "RELATIONSHIP_LABEL",
      "color": "#95E1D3",
      "description": "Cross-reference between clauses",
      "icon": "link"
    }
  },
  "doc_labels": {
    "Commercial Contract": {
      "id": "doc-label-1",
      "text": "Commercial Contract",
      "label_type": "DOC_TYPE_LABEL",
      "color": "#1A535C",
      "description": "A commercial agreement between parties",
      "icon": "file-text"
    }
  }
}
```

### Label Types

| Label Type | Location | Purpose |
|------------|----------|---------|
| `TOKEN_LABEL` | `text_labels` | Token-level annotations (PDF bounding boxes) |
| `SPAN_LABEL` | `text_labels` | Character-offset annotations (text documents) |
| `RELATIONSHIP_LABEL` | `text_labels` | Labels for annotation-to-annotation relationships |
| `DOC_TYPE_LABEL` | `doc_labels` | Document-level classification labels |

### Label Matching

- On import, labels are matched by name to existing labels in the corpus's label set
- If no match exists, a new label is created
- The `id` field in `labels.json` is ignored on import (used only for internal referencing)

---

## 5. Annotation JSON Formats

The `annotation_json` field format depends on the `annotation_type`.

### SPAN_LABEL (Text Documents)

Character-offset based. Used for `.txt` documents.

```json
{
  "start": 0,
  "end": 52,
  "text": "EXCLUSIVE LICENSE AND PRODUCT DEVELOPMENT AGREEMENT"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `start` | int | 0-based character offset (inclusive) |
| `end` | int | 0-based character offset (exclusive) |
| `text` | string | The text at this span |

### TOKEN_LABEL (PDF Documents)

References PAWLs tokens by page and token index. Two format versions:

**V1 (verbose):**
```json
{
  "0": {
    "bounds": {
      "top": 100.0,
      "bottom": 120.0,
      "left": 50.0,
      "right": 500.0
    },
    "tokensJsons": [
      {"pageIndex": 0, "tokenIndex": 5},
      {"pageIndex": 0, "tokenIndex": 6}
    ],
    "rawText": "January 1, 2025"
  }
}
```

**V2 (compact — preferred):**
```json
{
  "v": 2,
  "p": {
    "0": {
      "b": [100.0, 50.0, 500.0, 120.0],
      "t": "5-6"
    }
  }
}
```

The key is a string page index. `b` is `[top, left, right, bottom]`. `t` is a range-encoded token index string.

Both formats are accepted on import. V1 is automatically compacted to V2 when saved.

---

## 6. PAWLs Token Format

PAWLs (Page-Aware Word-Level Segmentation) represents document structure with precise token positioning. It is required for TOKEN_LABEL annotations on PDFs.

### V1 (verbose)

```json
[
  {
    "page": {"width": 612.0, "height": 792.0, "index": 0},
    "tokens": [
      {"x": 100, "y": 150, "width": 50, "height": 12, "text": "Hello"},
      {"x": 160, "y": 150, "width": 60, "height": 12, "text": "World"}
    ]
  }
]
```

### V2 (compact — 67% smaller)

```json
{
  "v": 2,
  "p": {
    "0": {
      "w": 612.0,
      "h": 792.0,
      "t": [
        [100, 150, 50, 12, "Hello"],
        [160, 150, 60, 12, "World"]
      ]
    }
  }
}
```

**Token fields**: `x`, `y`, `width`, `height` (in PDF points), `text` (content).
Coordinates use top-left origin, Y increases downward.

For most imports you can leave `pawls_file_content` as an empty list `[]` and use SPAN_LABEL annotations instead. PAWLs data is only required for TOKEN_LABEL annotations that reference specific PDF tokens.

---

## 7. Corpus Export/Import

For complete corpus roundtrips (backup/restore/transfer), use the corpus export/import path.

### Export

Right-click a corpus → **Export** → **OpenContracts** format. The export produces a ZIP:

```
corpus_export.zip
├── data.json          # All metadata, annotations, labels, config
├── document_a.pdf     # Original files at ZIP root
├── document_b.pdf
└── ...
```

### data.json Structure (V2)

```json
{
  "version": "2.0",
  "annotated_docs": {
    "document_a.pdf": { "...OpenContractDocExport..." },
    "document_b.pdf": { "...OpenContractDocExport..." }
  },
  "doc_labels": { "...label definitions..." },
  "text_labels": { "...label definitions..." },
  "corpus": { "title": "...", "description": "..." },
  "label_set": { "...label set metadata..." },
  "structural_annotation_sets": {},
  "folders": [],
  "document_paths": [],
  "relationships": [],
  "agent_config": {},
  "md_description": "...CAML source...",
  "md_description_revisions": [],
  "post_processors": []
}
```

### Import Behavior

- **ID remapping**: All IDs are opaque references; new DB IDs are assigned
- **User mapping**: `creator_email` matched to existing users; fallback to importing user
- **Structural deduplication**: Same-hash structural sets are reused
- **Embeddings regenerated**: Not exported (different deployments use different models)

---

## 8. CAML Corpus Descriptions

CAML (Corpus Article Markup Language) is a markdown superset for authoring rich, interactive corpus articles. A CAML description provides the landing page / README for a corpus.

### How CAML Integrates with OpenContracts

- **Storage**: CAML source is stored as a document titled `Readme.CAML` in each corpus
- **In exports**: The CAML source is stored in the `md_description` field of `data.json`
- **Rendering**: The frontend uses `@os-legal/caml` (parser) and `@os-legal/caml-react` (renderer)
- **Editing**: A full-screen CAML editor with live preview is built into the corpus view

### Document Structure

A CAML document has two parts: optional YAML **frontmatter** and a **body** of chapters and blocks.

```
---
(frontmatter)
---

(body with chapters and blocks)
```

### Frontmatter

Lightweight YAML supporting scalars, lists, nested objects, folded strings (`>`), and comments (`#`).

```yaml
---
version: "1.0"

hero:
  kicker: "Contract Analytics Report"
  title:
    - "Force Majeure Clause Analysis"
    - "{2024 Annual Review}"
  subtitle: >
    A comprehensive review of force majeure
    provisions across 500+ commercial contracts.
  stats:
    - "547 contracts analyzed"
    - "14 jurisdictions covered"
    - "89% clause adoption rate"

footer:
  nav:
    - label: Documentation
      href: https://docs.opencontracts.org
  notice: "Copyright 2024"
---
```

| Field | Type | Description |
|-------|------|-------------|
| `hero.kicker` | string | Small text above the title |
| `hero.title` | list | Title lines. Text in `{curly braces}` renders with accent styling |
| `hero.subtitle` | string | Paragraph below the title |
| `hero.stats` | list | Badge-like items below the subtitle |
| `footer.nav` | list | Navigation links (each with `label` and `href`) |
| `footer.notice` | string | Footer notice text |

### Chapters

Chapters are the top-level structural unit, using depth-3 colon fences (`:::`):

```
::: chapter {#findings, theme: dark, gradient: true, centered: true}
>! Section 01
## Key Findings

Prose content here...

:::: cards {columns: 2}
- **Card 1** | meta | #0f766e
  Card body text.
::::

:::
```

| Attribute | Values | Description |
|-----------|--------|-------------|
| `#id` | any string | Section ID for linking (default: `chapter-N`) |
| `theme` | `light`, `dark` | Visual theme |
| `gradient` | `true` | Gradient background |
| `centered` | `true` | Center-aligned text |

**Special lines in chapter prose:**
- `>! text` — Sets chapter kicker (small text above title)
- `## text` — Sets chapter title (first `##` only)

### Block Types

Blocks are nested inside chapters using depth-4 fences (`::::`).

#### Prose (no fence needed)

Standard markdown: `**bold**`, `*italic*`, `[links](url)`, lists, code blocks.

**Pullquotes** use `>>>`:
```
>>> "Contracts executed after March 2020 were 3.4x more
likely to include pandemic-specific language."
```

**Inline directives** for agent processing:
```
The clause was updated significantly. {{@cite sentence}}
```

#### Cards

```
:::: cards {columns: 2}
- **Force Majeure** | 89% adoption | #0f766e
  Updated language for pandemic and cyber events.
  ~ Source: Clause Database v4.2

- **Data Protection** | 94% adoption | #2563eb
  GDPR and CCPA compliance provisions.
::::
```

#### Pills (Metrics)

```
:::: pills
- 247 | **Documents Reviewed** | Q4 2024
  status: Complete | #16a34a
- 94% | **Compliance Rate** | Across jurisdictions
  status: Above Target | #0f766e
::::
```

#### Tabs

```
:::: tabs
::::: tab {label: "North America", status: Active, color: #0f766e}
#### United States {highlight}
Federal regulations analyzed.

§ SEC EDGAR
§ CFPB Regulations
:::::

::::: tab {label: "European Union", color: #7c3aed}
#### GDPR
Data processing reviewed.
:::::
::::
```

#### Timeline

```
:::: timeline
legend:
- Regulatory | #0f766e
- Enforcement | #dc2626

- Jan 2024 | SEC adopts climate rules | Regulatory
- Mar 2024 | CFPB enforcement action | Enforcement
::::
```

#### Map (US State Grid)

**Categorical:**
```
:::: map {type: us}
legend:
- Compliant | #0f766e
- Pending | #f59e0b

- CA | Compliant | 247
- NY | Compliant
- TX | Pending | 56
::::
```

**Heatmap:**
```
:::: map {type: us, mode: heatmap, low: #dbeafe, high: #1e3a8a}
- CA | 1247
- NY | 892
- TX | 634
::::
```

#### Case History

```
:::: case-history
title: SEC v. Meridian Capital Partners LLC
docket: No. 22-cv-04817 (S.D.N.Y.)
status: Affirmed

- District Court | S.D.N.Y. | 2022-06-10 | Motion for TRO | Granted
  Court issued TRO freezing assets.

- Court of Appeals | 2nd Circuit | 2023-11-08 | Appeal | Affirmed
  Panel held disgorgement calculation proper.
::::
```

#### Image

```
:::: image {src: https://example.com/chart.png, size: lg, shape: rounded}
caption: Clause adoption trends
alt: Chart showing adoption rates
::::
```

| Attribute | Values | Description |
|-----------|--------|-------------|
| `src` | URL or protocol scheme | `https://` URLs rendered directly; custom schemes resolved via `resolveImageSrc` callback |
| `size` | `sm` (48px), `md` (96px), `lg` (192px) | Image dimensions |
| `shape` | `native`, `rounded`, `avatar`, `cropped` | Clipping shape |

#### Corpus Stats (Live Data)

```
:::: corpus-stats
- documents | Documents
- annotations | Annotations
- contributors | Contributors
::::
```

Values are bound at render time from corpus metrics, not hardcoded in the CAML source.

#### Annotation & Extract Embeds

```
:::: annotation-embed {ref: @annotation:a7f2}
::::

:::: extract-embed {ref: @extract:e1f3, columns: Name|Date|Status}
::::
```

These embed live annotation data or extract data grids from the corpus directly into the article.

#### CTA (Call to Action)

```
:::: cta
- [View Full Report](#report) {primary}
- [Download Summary](#download)
::::
```

#### Signup

```
:::: signup
title: Stay Informed
button: Subscribe to Updates
Get weekly regulatory updates delivered to your inbox.
::::
```

### Inline Directives

Directives allow agent-powered processing of prose content:

```
{{@agent scope [key=value ...]}}
```

| Part | Required | Description |
|------|----------|-------------|
| `@agent` | Yes | Handler name (e.g., `cite`, `review`, `summarize`) |
| `scope` | Yes | `sentence`, `paragraph`, or `block` |
| `key=value` | No | Optional arguments |

**Examples:**
```
The clause was updated. {{@cite sentence}}
Multiple jurisdictions differ. {{@cite paragraph mode=all limit=5}}
{{@review block reason="stale data"}}
```

Directives are stripped from rendered content and processed by registered handlers at runtime.

---

## 9. Complete Worked Example

Here is a complete example of building a ZIP import with annotated documents and a CAML corpus description.

### Step 1: Create the Labels File

`labels.json`:
```json
{
  "text_labels": {
    "PARTY_NAME": {
      "id": "1",
      "text": "PARTY_NAME",
      "label_type": "SPAN_LABEL",
      "color": "#FF6B6B",
      "description": "Name of a contracting party",
      "icon": "tag"
    },
    "EFFECTIVE_DATE": {
      "id": "2",
      "text": "EFFECTIVE_DATE",
      "label_type": "SPAN_LABEL",
      "color": "#4ECDC4",
      "description": "Effective date of the contract",
      "icon": "calendar"
    },
    "GOVERNING_LAW": {
      "id": "3",
      "text": "GOVERNING_LAW",
      "label_type": "SPAN_LABEL",
      "color": "#45B7D1",
      "description": "Governing law jurisdiction",
      "icon": "scales"
    }
  },
  "doc_labels": {
    "Services Agreement": {
      "id": "d1",
      "text": "Services Agreement",
      "label_type": "DOC_TYPE_LABEL",
      "color": "#1A535C",
      "description": "Master services agreement",
      "icon": "file-text"
    }
  }
}
```

### Step 2: Create Sidecar Annotation Files

`contracts/agreement.json` (sidecar for `contracts/agreement.txt`):
```json
{
  "title": "Master Services Agreement",
  "content": "MASTER SERVICES AGREEMENT\n\nThis Master Services Agreement (the \"Agreement\") is entered into as of January 1, 2025 by and between Acme Corporation (\"Provider\") and Beta Industries (\"Client\").\n\n...\n\nThis Agreement shall be governed by the laws of the State of Delaware.",
  "description": "Services agreement between Acme Corp and Beta Industries",
  "page_count": 1,
  "pawls_file_content": [],
  "doc_labels": ["Services Agreement"],
  "labelled_text": [
    {
      "id": "a1",
      "annotationLabel": "PARTY_NAME",
      "rawText": "Acme Corporation",
      "page": 0,
      "annotation_json": {"start": 89, "end": 105, "text": "Acme Corporation"},
      "annotation_type": "SPAN_LABEL",
      "parent_id": null,
      "structural": false
    },
    {
      "id": "a2",
      "annotationLabel": "PARTY_NAME",
      "rawText": "Beta Industries",
      "page": 0,
      "annotation_json": {"start": 123, "end": 138, "text": "Beta Industries"},
      "annotation_type": "SPAN_LABEL",
      "parent_id": null,
      "structural": false
    },
    {
      "id": "a3",
      "annotationLabel": "EFFECTIVE_DATE",
      "rawText": "January 1, 2025",
      "page": 0,
      "annotation_json": {"start": 65, "end": 80, "text": "January 1, 2025"},
      "annotation_type": "SPAN_LABEL",
      "parent_id": null,
      "structural": false
    },
    {
      "id": "a4",
      "annotationLabel": "GOVERNING_LAW",
      "rawText": "the State of Delaware",
      "page": 0,
      "annotation_json": {"start": 210, "end": 231, "text": "the State of Delaware"},
      "annotation_type": "SPAN_LABEL",
      "parent_id": null,
      "structural": false
    }
  ]
}
```

### Step 3: Create Metadata and Relationships CSVs

`meta.csv`:
```csv
source_path,title,description
contracts/agreement.txt,Master Services Agreement,MSA between Acme Corp and Beta Industries
contracts/amendment.txt,Amendment No. 1,First amendment to the MSA
```

`relationships.csv`:
```csv
source_path,relationship_label,target_path,notes
contracts/amendment.txt,AMENDS,contracts/agreement.txt,First amendment modifying payment terms
```

### Step 4: Assemble the ZIP

```
my-import.zip
├── contracts/
│   ├── agreement.txt
│   ├── agreement.json        ← sidecar annotations
│   ├── amendment.txt
│   └── amendment.json        ← sidecar annotations
├── labels.json
├── meta.csv
└── relationships.csv
```

### Step 5: Create a CAML Description for the Corpus

After import, you can add a CAML article to describe the corpus. This is stored as a document titled `Readme.CAML` or set via the `md_description` field in a corpus export.

```caml
---
version: "1.0"

hero:
  kicker: "Contract Repository"
  title:
    - "Acme-Beta Partnership"
    - "{Contract Collection}"
  subtitle: >
    Complete collection of agreements between
    Acme Corporation and Beta Industries.
  stats:
    - "2 contracts"
    - "1 jurisdiction"

footer:
  notice: "Internal use only"
---

::: chapter {#overview}
>! Section 01
## Collection Overview

This corpus contains the **Master Services Agreement** and its
first amendment between Acme Corporation and Beta Industries.

>>> "All contracts governed by Delaware law with
standard commercial terms."

:::: corpus-stats
- documents | Documents
- annotations | Annotations
::::

:::

::: chapter {#parties, theme: dark}
>! Section 02
## Contracting Parties

:::: cards {columns: 2}
- **Acme Corporation** | Provider | #0f766e
  Technology services provider.
  ~ Delaware incorporation

- **Beta Industries** | Client | #2563eb
  Manufacturing client.
  ~ New York incorporation
::::

:::

::: chapter {#timeline}
>! Section 03
## Contract Timeline

:::: timeline
legend:
- Execution | #0f766e
- Amendment | #f59e0b

- Jan 2025 | Master Services Agreement signed | Execution
- Mar 2025 | Amendment No. 1 executed | Amendment
::::

:::
```

### Step 6: Execute the Import

```bash
# Base64-encode the ZIP
ZIP_B64=$(base64 -w 0 my-import.zip)

# Call the mutation
curl -s -X POST http://localhost:8000/graphql/ \
  -H "Content-Type: application/json" \
  -H "Cookie: sessionid=<your-session-key>" \
  -d "{
    \"query\": \"mutation(\$file: String!, \$corpusId: ID!) { importZipToCorpus(base64FileString: \$file, corpusId: \$corpusId, makePublic: false) { ok message jobId } }\",
    \"variables\": {
      \"file\": \"$ZIP_B64\",
      \"corpusId\": \"<target-corpus-id>\"
    }
  }"
```

---

## 10. Reference: Security Constraints

All limits configurable via Django settings.

| Constraint | Default | Description |
|------------|---------|-------------|
| `ZIP_MAX_FILE_COUNT` | 1,000 | Max files per ZIP |
| `ZIP_MAX_TOTAL_SIZE_BYTES` | 500 MB | Max uncompressed total size |
| `ZIP_MAX_SINGLE_FILE_SIZE_BYTES` | 100 MB | Max single file |
| `ZIP_MAX_COMPRESSION_RATIO` | 100:1 | Zip bomb detection |
| `ZIP_MAX_FOLDER_DEPTH` | 20 | Max nesting depth |
| `ZIP_MAX_FOLDER_COUNT` | 500 | Max folders created |
| `ZIP_MAX_PATH_COMPONENT_LENGTH` | 255 | Max filename length |
| `ZIP_MAX_PATH_LENGTH` | 1,024 | Max total path |
| `ZIP_MAX_SIDECAR_SIZE_BYTES` | 10 MB | Max annotation sidecar JSON |
| `ZIP_DOCUMENT_BATCH_SIZE` | 50 | Batch size for processing |

---

## Quick Reference: Which Import Method to Use

| Scenario | Method |
|----------|--------|
| Upload a batch of raw documents | Bulk ZIP Import |
| Upload documents with pre-computed annotations | Bulk ZIP Import + sidecars + labels.json |
| Programmatically import one annotated document | `UploadAnnotatedDocument` mutation |
| Backup/restore an entire corpus | Corpus Export/Import |
| Transfer a corpus between instances | Corpus Export/Import |
| Add a rich landing page to a corpus | CAML article (Readme.CAML document) |
