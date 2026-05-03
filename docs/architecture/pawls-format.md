# PAWLs Format Specification

## Overview

PAWLs (Page-Aware Word-Level Segmentation) is OpenContracts' format for representing document structure with precise token positioning. Each page in a document has tokens (text or image) with bounding box coordinates that enable:

- Precise text selection and annotation
- Image region identification and annotation
- Spatial queries for finding tokens in regions
- Frontend rendering with accurate positioning

## Format Structure

A PAWLs file is a JSON array of page objects:

```json
[
  {
    "page": {
      "width": 612.0,
      "height": 792.0,
      "index": 0
    },
    "tokens": [
      {"x": 100, "y": 100, "width": 50, "height": 12, "text": "Hello"},
      {"x": 160, "y": 100, "width": 60, "height": 12, "text": "World"}
    ]
  },
  {
    "page": {"width": 612.0, "height": 792.0, "index": 1},
    "tokens": [...]
  }
]
```

## Page Object

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| page | object | Yes | Page metadata |
| page.width | float | Yes | Page width in PDF points |
| page.height | float | Yes | Page height in PDF points |
| page.index | int | Yes | 0-based page index |
| tokens | array | Yes | Array of token objects |

## Token Object

Tokens represent either text or images. The `is_image` field distinguishes between them.

### Common Fields (All Tokens)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| x | float | Yes | X coordinate (PDF points, origin top-left) |
| y | float | Yes | Y coordinate (PDF points, origin top-left) |
| width | float | Yes | Token width in PDF points |
| height | float | Yes | Token height in PDF points |
| text | string | Yes | Text content (empty string for images) |

### Image Token Fields

When `is_image` is `true`, the token represents an image:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| is_image | bool | Yes | Must be `true` for image tokens |
| image_path | string | Yes* | Storage path to image file |
| format | string | No | Image format: "jpeg" or "png" |
| content_hash | string | No | SHA-256 hash for deduplication |
| original_width | int | No | Original image width in pixels |
| original_height | int | No | Original image height in pixels |
| image_type | string | No | "embedded" or "cropped" |

*Either `image_path` (preferred) or `base64_data` should be present.

### Text Token Example

```json
{
  "x": 100.5,
  "y": 150.25,
  "width": 45.0,
  "height": 12.0,
  "text": "Revenue"
}
```

### Image Token Example

```json
{
  "x": 50.0,
  "y": 200.0,
  "width": 300.0,
  "height": 200.0,
  "text": "",
  "is_image": true,
  "image_path": "documents/123/images/page_0_img_0.jpg",
  "format": "jpeg",
  "content_hash": "a1b2c3d4e5f6...",
  "original_width": 800,
  "original_height": 533,
  "image_type": "embedded"
}
```

## Coordinate System

- **Origin**: Top-left corner of the page
- **Units**: PDF points (1 point = 1/72 inch)
- **X-axis**: Increases left to right
- **Y-axis**: Increases top to bottom
- **Standard page size**: Letter is 612 x 792 points

## Token References

Annotations reference tokens using `TokenIdPythonType`:

```json
{
  "pageIndex": 0,
  "tokenIndex": 5
}
```

This format works for both text and image tokens since they're in the same array.

## Annotation Integration

### Single Modality Annotation (Text Only)

```json
{
  "tokens_jsons": [
    {"pageIndex": 0, "tokenIndex": 0},
    {"pageIndex": 0, "tokenIndex": 1}
  ],
  "content_modalities": ["TEXT"]
}
```

### Single Modality Annotation (Image Only)

```json
{
  "tokens_jsons": [
    {"pageIndex": 0, "tokenIndex": 15}
  ],
  "content_modalities": ["IMAGE"]
}
```

### Mixed Modality Annotation (Image + Caption)

```json
{
  "tokens_jsons": [
    {"pageIndex": 0, "tokenIndex": 15},
    {"pageIndex": 0, "tokenIndex": 16},
    {"pageIndex": 0, "tokenIndex": 17}
  ],
  "content_modalities": ["IMAGE", "TEXT"]
}
```

## Image Storage

Images are stored separately from the PAWLs file to avoid bloat:

1. **During parsing**: Images are extracted and saved to Django storage (S3, GCS, or filesystem)
2. **In PAWLs**: Only the `image_path` reference is stored
3. **On retrieval**: Image tools load from storage and return base64 data

### Storage Path Convention

```
documents/{document_id}/images/page_{page_idx}_img_{img_idx}.{format}
```

Example: `documents/123/images/page_0_img_0.jpg`

## Content Modalities

The `content_modalities` field on Annotation tracks what types of content are present:

| Value | Description |
|-------|-------------|
| `TEXT` | Contains text tokens |
| `IMAGE` | Contains image tokens |
| `AUDIO` | Contains audio content (future) |
| `TABLE` | Contains table content (future) |
| `VIDEO` | Contains video content (future) |

This enables embedders to efficiently filter annotations they can process.

## Parser Responsibilities

When generating PAWLs data, parsers should:

1. Extract text tokens with accurate bounding boxes
2. Extract images and save to storage
3. Create image tokens in the `tokens[]` array with `is_image: true`
4. For structural annotations (figures, charts):
   - Reference image tokens via `tokens_jsons`
   - Set `content_modalities: ["IMAGE"]`

## Frontend Handling

The frontend should:

1. Check `token.is_image` to identify image tokens
2. Render image tokens with different visual treatment (e.g., border instead of text highlight)
3. Allow selection of both text and image tokens
4. Display mixed annotations spanning both types

## v1 vs v2: Compact PAWLs Format

### Motivation

PAWLs files can be large — a typical 9-page PDF produces ~549 KB of v1 JSON. Since every document stores a PAWLs file (in S3, GCS, or filesystem via the `pawls_parse_file` field on `Document`), the aggregate storage cost is significant. The v2 compact format reduces this by **~67%** (549 KB → 180 KB in measured benchmarks).

### v1 Format (Legacy)

The original format, documented above. A JSON **array** of page objects with verbose, human-readable keys:

```json
[
  {
    "page": {"width": 612.0, "height": 792.0, "index": 0},
    "tokens": [
      {"x": 72.0, "y": 720.0, "width": 41.0, "height": 12.0, "text": "Hello"},
      {"x": 120.5, "y": 720.0, "width": 35.2, "height": 12.0, "text": "world"}
    ]
  }
]
```

**Per text token overhead**: ~105 characters (JSON key names dominate).

### v2 Format (Compact)

A JSON **dict** with a version marker. Tokens become positional arrays; keys are shortened:

```json
{
  "v": 2,
  "p": [
    {
      "w": 612.0,
      "h": 792.0,
      "t": [
        [72.0, 720.0, 41.0, 12.0, "Hello"],
        [120.5, 720.0, 35.2, 12.0, "world"]
      ]
    }
  ]
}
```

**Per text token overhead**: ~37 characters (~65% savings per token).

Image tokens carry a 6th element with compact metadata:

```json
[0.0, 100.0, 200.0, 300.0, "", {"p": "documents/123/images/page_0_img_0.jpg", "f": "jpeg", "ch": "a1b2c3..."}]
```

> **Note:** The presence of a 6th element (the metadata dict) is what distinguishes image tokens from text tokens in v2. On decode, `expand_pawls_pages()` reconstructs the `is_image: true` field from this — v2 does not store `is_image` explicitly.

### Five Compression Techniques

| # | Technique | Savings | Details |
|---|-----------|---------|---------|
| 1 | **Array-based tokens** | ~60% per token | `[x, y, w, h, "text"]` instead of `{"x": …, "y": …, "width": …, "height": …, "text": …}` |
| 2 | **Shortened page keys** | Minor | `w`, `h` instead of `width`, `height` |
| 3 | **Implicit page index** | Minor | Array position *is* the page index — no `"index"` field |
| 4 | **Coordinate precision normalization** | ~5-10% | Floats rounded to 1 decimal place (0.1 PDF points ≈ 0.0014 inches — sub-pixel precision is meaningless) |
| 5 | **Compact image metadata keys** | Variable | `image_path` → `p`, `format` → `f`, `content_hash` → `ch`, etc. |

### Image Metadata Key Mapping

| v1 Key | v2 Key |
|--------|--------|
| `image_path` | `p` |
| `base64_data` | `b64` |
| `format` | `f` |
| `content_hash` | `ch` |
| `original_width` | `ow` |
| `original_height` | `oh` |
| `image_type` | `it` |

### Format Detection

The two formats are distinguishable by shape:

- **v1**: Top-level value is a JSON **array** (`[{…}, …]`)
- **v2**: Top-level value is a JSON **dict** with `"v": 2` and `"p"` keys

```python
from opencontractserver.utils.compact_pawls import is_compact_pawls_format

is_compact_pawls_format([...])          # False (v1)
is_compact_pawls_format({"v": 2, "p": [...]})  # True (v2)
```

### The Boundary Layer: v2 Internally, v1 Only at I/O Edges

v2 is the canonical runtime format on both backend and frontend. v1 is accepted only at well-defined I/O boundaries:

- **Backend import boundary** — every read path goes through `pawls_io.load_canonical_v2()`, which accepts v1 or v2 wire input and **always returns a v2 dict**. Active runtime code consumes this v2 dict (or its `PageView` / `TokenView` read-views) — never v1.
- **Backend export boundary** — the `OpenContractDocExport.pawls_file_content` and `StructuralAnnotationSetExport.pawls_file_content` wire formats are documented v1. The two export sites convert v2 → v1 via `pawls_io.to_v1_pages()` exactly once, at payload assembly time.
- **Plasmapdf hand-off boundary** — `plasmapdf.build_translation_layer()` is a third-party API that consumes v1 `PawlsPagePythonType` lists. The five call sites that build a translation layer convert v2 → v1 via `pawls_io.to_v1_pages()` at the call boundary.
- **Frontend wire boundary** — `frontend/src/utils/compactPawls.ts` exports `decodeV2Pawls(json)`. It accepts v1 or v2 wire input but always returns v2-canonical typed objects (`CompactPage[]`, `CompactToken[]`). Consumers never see v1 in memory.

```python
from opencontractserver.utils.pawls_io import (
    load_canonical_v2,   # Read boundary: returns v2 dict
    to_canonical_v2,     # Idempotent v1/v2 → v2 (for in-memory inputs)
    iter_pages,          # Yields PageView over a v2 dict
    to_v1_pages,         # Boundary-only: v2 → v1, plasmapdf and export wire
)

canonical = load_canonical_v2(document.pawls_parse_file)
for page in iter_pages(canonical):       # PageView
    for token in page.tokens:            # TokenView
        ...                              # token.x, token.y, token.isImage, …
```

```typescript
import { decodeV2Pawls } from "@/utils/compactPawls";

const pages: CompactPage[] = decodeV2Pawls(rawJsonFromBackend);
// pages[i].width / .height / .tokens[j].x / .text / .isImage / .imageMeta?.p
```

#### Storage is file-based, not column-based

PAWLs data lives in Django `FileField` storage (S3/GCS/filesystem). There is no single SQL migration that converts all existing files. The boundary layer accepts v1 wire input forever — old v1 files on disk continue to work without backfill. New documents are written in v2.

#### Active code is v1-free

Outside the four boundaries listed above, v1-shape data is a bug. Use `to_canonical_v2()` to normalize any in-memory input you don't trust. Use `iter_pages` / `PageView` / `TokenView` for ergonomic v2 reads. Refer to `to_v1_pages()` only at a documented external boundary, with an inline comment explaining the boundary intent.

#### The 100k-tokens-per-page edge case is now strict

Previously, a page exceeding `COMPACT_PAWLS_MAX_TOKENS_PER_PAGE` (100,000) would silently fall back to v1 format on disk. The new `to_canonical_v2()` boundary instead **raises `ValueError`** in that case, refusing to leak v1 past the load boundary. This is an extraordinarily rare condition; the trade-off is loud-failure over silent storage-invariant violation.

### Write Paths (v2 on Disk)

All persist sites route through `pawls_io.to_canonical_v2()` and serialize the result. Output is always v2 (or fails loudly per the rule above).

| Write Path | File |
|------------|------|
| Parser output | `opencontractserver/pipeline/base/parser.py` |
| Worker uploads | `opencontractserver/worker_uploads/tasks.py` |
| V2 import | `opencontractserver/utils/import_v2.py` |
| Legacy import | `opencontractserver/utils/importing.py` |
| Import tasks | `opencontractserver/tasks/import_tasks.py` |

### Read Paths (v2 in Memory)

All read paths route through `pawls_io.load_canonical_v2()` and consume v2. Run `grep -r load_canonical_v2 opencontractserver/` for the full list.

| Consumer | File |
|----------|------|
| LLM agent tools | `opencontractserver/llms/tools/core_tools/` |
| Image tools | `opencontractserver/llms/tools/image_tools.py` |
| PDF token extraction | `opencontractserver/utils/pdf_token_extraction.py` |
| Multimodal embeddings | `opencontractserver/utils/multimodal_embeddings.py` |
| Doc analyzer decorators | `opencontractserver/shared/decorators.py` |
| FUNSD export, extraction grounding, etl | `opencontractserver/tasks/`, `opencontractserver/utils/` |
| Frontend REST fetch | `frontend/src/components/annotator/api/rest.ts` |

### Constants

Defined in `opencontractserver/constants/pawls.py`:

| Constant | Value | Purpose |
|----------|-------|---------|
| `COMPACT_PAWLS_VERSION` | `2` | Version marker in the `"v"` field |
| `COMPACT_PAWLS_COORDINATE_PRECISION` | `1` | Decimal places for coordinate rounding |
| `COMPACT_PAWLS_MAX_TOKENS_PER_PAGE` | `100,000` | Boundary refuses to leak v1; exceeding this raises `ValueError` |

### Implementation Files

| Layer | File | Role |
|-------|------|------|
| Backend boundary | `opencontractserver/utils/pawls_io.py` | Single load boundary; v1↔v2 adaptors; `PageView`/`TokenView` |
| Backend codec | `opencontractserver/utils/compact_pawls.py` | Low-level encode/decode primitives (used by `pawls_io`) |
| Frontend decoder | `frontend/src/utils/compactPawls.ts` | `decodeV2Pawls` — wire-tolerant, v2-canonical output |
| Constants | `opencontractserver/constants/pawls.py` | Shared constants |
| Tests | `opencontractserver/tests/test_pawls_io.py`, `test_compact_pawls.py`, `frontend/src/utils/__tests__/compactPawls.test.ts` | Boundary + codec coverage |

### Comparison with Annotation Compact Format

A similar v2 compression strategy exists for annotation JSON payloads in `opencontractserver/annotations/compact_json.py`. It uses the same design principles (version marker, format-agnostic accessor, auto-compact on write) but applies range-encoding for token indices instead of array-based tokens. The annotation format achieves ~75% storage reduction.

## Migration Notes

If processing older documents without image tokens:

- Documents parsed before image support have only text tokens
- `is_image` field will be absent (falsy) for all tokens
- Re-parsing with current parsers will add image tokens

If processing older documents with v1 PAWLs format:

- v1 files on disk are NOT automatically converted — they stay as-is until re-parsed
- All read paths handle the wire format transparently via `pawls_io.load_canonical_v2()`, which converts v1 → v2 at the boundary
- New documents are always stored in v2 format automatically

## Related Documentation

- [PAWLs Token Format Walkthrough](../walkthrough/advanced/pawls-token-format.md)
- [Image Token Implementation Plan](../plans/phase-3-unified-image-tokens.md)
- [Pipeline Overview](../pipelines/pipeline_overview.md)
