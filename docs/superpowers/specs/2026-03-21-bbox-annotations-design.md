# Bounding-Box Annotations with Token Resolution

**Date**: 2026-03-21
**Status**: Design approved

## Problem

External tools can identify regions in a PDF (headers, sections, clauses) using
bounding boxes from libraries like pdfplumber or PyMuPDF. But they can't produce
`TOKEN_LABEL` annotations because PAWLs token indices don't exist until after
DoclingParser runs. This is a chicken-and-egg problem: annotations need token
indices, tokens don't exist until parsing, parsing happens after import.

## Solution

A new optional `bbox_annotations` field on document import data. Each entry
carries raw bounding-box coordinates keyed by page number. A standalone pure
function resolves these to proper `TOKEN_LABEL` annotations by matching bounding
boxes against PAWLs tokens, then merges the results into `labelled_text` before
the existing annotation import logic runs.

No new annotation types. No new label types. No new API endpoints. No new
pipeline stages. No frontend changes.

## Data Schema

### The `bbox_annotations` Field

A new optional field on two types:

1. `OpenContractsDocAnnotations` (base for `OpenContractDocExport`, sidecar JSON,
   annotated document import, and corpus export/import payloads)
2. `WorkerDocumentUploadMetadataType` (standalone TypedDict for worker uploads —
   does NOT inherit from `OpenContractsDocAnnotations`)

```python
# In OpenContractsDocAnnotations
bbox_annotations: NotRequired[list[BboxAnnotationType]]

# In WorkerDocumentUploadMetadataType (added separately)
bbox_annotations: NotRequired[list[BboxAnnotationType]]
```

### `BboxAnnotationType`

```python
class BboxAnnotationType(TypedDict):
    id: NotRequired[str | int | None]          # local ID for parent_id cross-refs
    annotationLabel: str                        # label name (must exist in text_labels)
    rawText: str                                # required
    bounds: dict[str, list[BoundingBoxPythonType]]  # page number (str) -> list of rects
    parent_id: NotRequired[str | int | None]    # for hierarchical annotations
    structural: NotRequired[bool]               # default false
    long_description: NotRequired[str | None]   # markdown description (e.g. OC_SECTION)
```

Uses the existing `BoundingBoxPythonType` (from `opencontractserver/types/dicts.py`)
for rectangle coordinates — no new rect type needed.

### Coordinate System

- Coordinates in `bounds` are **PDF points** (1/72 inch), **origin top-left**
- This is the same coordinate system as PAWLs tokens (see
  `docs/architecture/pawls-format.md`) — **no coordinate scaling is needed**
- Page numbers in the `bounds` dict are 0-based, as strings (matching
  TOKEN_LABEL's `annotation_json` convention)

### Full Example

```json
{
  "bbox_annotations": [
    {
      "id": "ch1",
      "annotationLabel": "OC_SECTION",
      "rawText": "Chapter 1. General Corporation Law",
      "long_description": "Covers formation, powers, registered agents...",
      "bounds": {
        "4": [
          {"top": 230.5, "bottom": 248.0, "left": 185.0, "right": 425.0}
        ],
        "5": [
          {"top": 72.0, "bottom": 84.0, "left": 50.0, "right": 150.0}
        ]
      },
      "parent_id": null,
      "structural": false
    },
    {
      "id": "s1.1",
      "annotationLabel": "OC_SECTION",
      "rawText": "1.1 Definitions",
      "bounds": {
        "5": [
          {"top": 100.0, "bottom": 112.0, "left": 50.0, "right": 200.0}
        ]
      },
      "parent_id": "ch1",
      "structural": false
    }
  ]
}
```

## Resolution Algorithm

### Function Signature

```python
def resolve_bbox_annotations(
    pawls_pages: list[PawlsPagePythonType],
    bbox_annotations: list[BboxAnnotationType],
) -> list[OpenContractsAnnotationPythonType]:
```

Pure function. No database access, no side effects. Takes PAWLs page data and
bbox annotation dicts, returns fully-formed `labelled_text`-style entries ready
to pass into `import_doc_annotations`.

### Per-Annotation Steps

For each entry in `bbox_annotations`:

1. **For each page in `bounds`:**
   - Get the PAWLs page data (tokens array). Both PAWLs tokens and the input
     bounding boxes use PDF points with top-left origin — no coordinate
     transformation is needed.
   - For each token on that page, compute center point:
     - `cx = token.x + token.width / 2`
     - `cy = token.y + token.height / 2`
   - Token matches if its center falls inside any of the bounding rectangles
     for that page (i.e., `left <= cx <= right` and `top <= cy <= bottom`)
   - Collect matched token indices, sorted

2. **Build TOKEN_LABEL `annotation_json`:** A dict keyed by page string. Each
   page value is an `OpenContractsSinglePageAnnotationType` with:
   - `tokensJsons`: list of `TokenIdPythonType` (`{"pageIndex": p, "tokenIndex": i}`)
     for each matched token
   - `bounds`: the union bounding box of all matched tokens on that page
     (min top/left, max bottom/right of matched token bounding boxes)
   - `rawText`: concatenation of matched token texts on that page, joined by
     spaces

3. **Set `page`:** The minimum page number across all pages in `bounds` that
   have at least one matched token. This is consistent with how existing
   multi-page TOKEN_LABEL annotations use `page` as the "first page."

4. **Preserve `rawText`:** The input `rawText` from the bbox annotation entry is
   used as the output annotation's `rawText`. The external tool chose it
   deliberately (it might be a cleaned-up or canonical version). The per-page
   `rawText` inside `annotation_json` uses the token-derived text, but the
   top-level `rawText` preserves the caller's intent. This matches how
   `OC_SECTION` annotations already work.

5. **Set `content_modalities`:** Based on matched token types:
   - If any matched token has `is_image=True`: include `"IMAGE"`
   - If any matched token is a text token: include `"TEXT"`
   - Result is one of: `["TEXT"]`, `["IMAGE"]`, or `["TEXT", "IMAGE"]`

6. **Emit** a standard `OpenContractsAnnotationPythonType` dict with
   `annotation_type = "TOKEN_LABEL"`.

### Edge Cases

| Case | Behavior |
|------|----------|
| No tokens match any rect on a page | Log warning, skip that page (annotation may be partial) |
| No tokens match across ALL pages | Log warning, drop the annotation entirely |
| Page number in `bounds` exceeds PAWLs page count | Log warning, skip that page |
| Image tokens (`is_image=True`) inside bounds | Include — they have bounding boxes and are valid targets |
| Empty `bounds` dict | Drop annotation, log warning |
| Multiple annotations overlap same tokens | Fine — each annotation gets its own token references independently |

### File Location

`opencontractserver/utils/bbox_resolution.py` — contains `resolve_bbox_annotations()`
and `BboxAnnotationType` TypedDict.

## Integration Points

### Approach

Standalone utility function called at each integration point. Every pathway
follows the same 3-step pattern:

1. Extract `bbox_annotations` from import data (if present)
2. Get PAWLs data (from document record or import payload)
3. Call `resolve_bbox_annotations`, merge results into `labelled_text`

No new Celery tasks. No new model fields. No new API endpoints.

### Prerequisite: PAWLs Data Must Be Available

`bbox_annotations` resolution requires PAWLs token data. This is available in
all four pathways, but with an important distinction in the bulk ZIP sidecar
flow (see below).

### Bulk ZIP Import (Sidecar Flow)

In `_apply_sidecar_annotations` in `import_tasks.py`:

**`skip_pipeline: true` case (primary):** The sidecar contains
`pawls_file_content`, and the document is created directly from sidecar data
without running the parser. PAWLs data is available immediately.

1. Check if sidecar `doc_data` has a `bbox_annotations` field
2. Resolve against `doc_data["pawls_file_content"]`
3. Merge resolved entries into `doc_data["labelled_text"]`
4. Proceed with existing `import_doc_annotations` call unchanged

**Non-`skip_pipeline` case:** The document goes through the parser pipeline
asynchronously. PAWLs data does not exist on the document at the time
`_apply_sidecar_annotations` runs — the parser hasn't finished yet. In this
case:

- If `bbox_annotations` is present but no PAWLs data is available: **log a
  warning and skip bbox resolution**. The regular `labelled_text` annotations
  (which already carry pre-resolved token indices) are imported normally.
- This is documented as a limitation: `bbox_annotations` in sidecars requires
  `skip_pipeline: true` (or the sidecar must include `pawls_file_content`).

`parent_id` cross-references between bbox annotations and regular
`labelled_text` annotations work naturally — they share the same ID namespace
and get remapped together in `import_doc_annotations`.

### Annotated Document Import

In the `import_document_to_corpus` task:

1. After document creation (PAWLs data is in `doc_data.pawls_file_content`)
2. If `bbox_annotations` present, resolve against inline PAWLs
3. Merge into `labelled_text`
4. Existing annotation import proceeds unchanged

### Corpus Export/Import

In the corpus import task (`import_tasks_v2.py`), for each document in
`annotated_docs`:

1. Check for `bbox_annotations` on the document entry
2. PAWLs data is in `pawls_file_content` on the same entry
3. Resolve and merge into `labelled_text` before `import_doc_annotations`

On **export**: no change needed. Resolved annotations are standard TOKEN_LABEL.
`bbox_annotations` is transient input-only data that never persists in the
database and is never exported.

### Worker Uploads

In the worker upload batch processor:

1. Check metadata for `bbox_annotations`
2. PAWLs data is in `pawls_file_content` in the same metadata
3. Resolve and merge into `labelled_text`
4. Existing annotation creation proceeds unchanged

## What Changes Where

### New Code

| File | What |
|------|------|
| `opencontractserver/utils/bbox_resolution.py` | `resolve_bbox_annotations()` pure function + `BboxAnnotationType` TypedDict |
| `opencontractserver/tests/test_bbox_resolution.py` | Unit tests for resolution (pure function, no Django needed) |

### Modified Code (Types)

| File | What |
|------|------|
| `opencontractserver/types/dicts.py` | Add `bbox_annotations` as `NotRequired` field on `OpenContractsDocAnnotations` AND separately on `WorkerDocumentUploadMetadataType` |

### Modified Code (Integration Points)

| File | What |
|------|------|
| `opencontractserver/tasks/import_tasks.py` | Sidecar flow + annotated document import: resolve + merge before `import_doc_annotations` |
| `opencontractserver/tasks/import_tasks_v2.py` | Corpus import: resolve + merge for each document in `annotated_docs` |
| Worker upload batch processor | Resolve + merge before annotation creation |

### Documentation Updates

| File | What |
|------|------|
| `docs/upload_methods/bulk_zip_import.md` | Document `bbox_annotations` in sidecar JSON schema; note `skip_pipeline` requirement |
| `docs/upload_methods/annotated_document_import.md` | Document `bbox_annotations` field in import data schema |
| `docs/upload_methods/corpus_export_import.md` | Document `bbox_annotations` as accepted input (import-only, not exported) |
| `docs/upload_methods/worker_uploads.md` | Document `bbox_annotations` in optional metadata fields |
| `docs/upload_methods/annotation_side_effects.md` | Add section on bbox resolution behavior |
| `docs/upload_methods/index.md` | Update quick reference if needed |
| Final review pass over all `docs/upload_methods/` files | Ensure consistency and cross-references |

### What Doesn't Change

- Annotation model — no new fields, no new annotation types
- Label model — no new label types
- GraphQL schema — no new mutations or types
- Frontend — resolved annotations are standard TOKEN_LABEL
- Pipeline stages — resolution is not a pipeline stage
- Export logic — `bbox_annotations` is input-only, never persisted or exported
