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

### The Accessor Layer: Why We Didn't Replace v1 Throughout

Rather than rewriting every consumer to understand v2, we use a **format-agnostic accessor layer**. All code reads PAWLs through `expand_pawls_pages()`, which transparently normalizes either format to v1 shape:

```python
from opencontractserver.utils.compact_pawls import expand_pawls_pages

# Always returns list[PawlsPagePythonType] regardless of input format
pages = expand_pawls_pages(raw_json)
```

This design was chosen over a full v1 replacement for several architectural reasons:

#### 1. Storage is file-based, not column-based

PAWLs data lives in Django `FileField` storage (S3/GCS/filesystem), not in a database column. There is no single SQL migration that can convert all existing files. A backfill job would need to download, re-encode, and re-upload every file — risky and unnecessary when the accessor layer handles both formats.

#### 2. Backward compatibility with zero consumer changes

Dozens of consumers read PAWLs data: LLM tools, PDF redaction, annotation import/export, the frontend REST layer, and more. Rewriting all of them to use v2 arrays would be a large, error-prone change with no functional benefit — they all need the same v1-shaped data structures internally.

#### 3. Incremental adoption without a "big bang" migration

New documents are automatically stored in v2 (all write paths call `compact_pawls_pages()`). Old v1 documents continue to work as-is. Over time, as documents are re-parsed or replaced, the corpus naturally migrates to v2 — no coordinated migration event required.

#### 4. Graceful fallback for edge cases

If a page has more than 100,000 tokens (pathological input), `compact_pawls_pages()` falls back to storing v1 format rather than producing a potentially broken compact file. The read path handles both.

#### 5. Frontend only needs the decoder

The frontend never writes PAWLs — it only fetches and renders. So it only needs `expandPawlsPages()` (the v2 → v1 decoder), which lives in `frontend/src/utils/compactPawls.ts`. The entire frontend codebase continues to work with v1 types (`PageTokens[]`, `Token`).

### Write Paths (Where v2 Encoding Happens)

Primary entry points that persist PAWLs files automatically compact to v2. If any page exceeds `MAX_TOKENS_PER_PAGE` (100,000), the **entire document** falls back to v1 format.

| Write Path | File | What It Does |
|------------|------|--------------|
| Parser output | `opencontractserver/pipeline/base/parser.py` | Compacts after parsing completes |
| Worker uploads | `opencontractserver/worker_uploads/tasks.py` | Compacts imported PAWLs data |
| V2 import | `opencontractserver/utils/import_v2.py` | Compacts during v2 corpus import |
| Legacy import | `opencontractserver/utils/importing.py` | Compacts during legacy corpus import |
| Import tasks | `opencontractserver/tasks/import_tasks.py` | Compacts during async import jobs |

```python
from opencontractserver.utils.compact_pawls import compact_pawls_pages

compact_data = compact_pawls_pages(v1_pages)  # v2 dict (or v1 fallback)
pawls_string = json.dumps(compact_data)
```

### Read Paths (Where v2 Expansion Happens)

Key consumers read through `expand_pawls_pages()`. Run `grep -r expand_pawls_pages` for the full list (~15 files).

| Consumer | File |
|----------|------|
| LLM agent tools | `opencontractserver/llms/tools/core_tools/` |
| Image tools | `opencontractserver/llms/tools/image_tools.py` |
| PDF token extraction | `opencontractserver/utils/pdf_token_extraction.py` |
| Frontend REST fetch | `frontend/src/components/annotator/api/rest.ts` |
| Any code loading `pawls_parse_file` | Via `expand_pawls_pages(json.load(f))` |

### Constants

Defined in `opencontractserver/constants/pawls.py`:

| Constant | Value | Purpose |
|----------|-------|---------|
| `COMPACT_PAWLS_VERSION` | `2` | Version marker in the `"v"` field |
| `COMPACT_PAWLS_COORDINATE_PRECISION` | `1` | Decimal places for coordinate rounding |
| `COMPACT_PAWLS_MAX_TOKENS_PER_PAGE` | `100,000` | Safety guard — exceeding this falls back to v1 |

### Implementation Files

| Layer | File | Direction |
|-------|------|-----------|
| Backend (Python) | `opencontractserver/utils/compact_pawls.py` | Encode + Decode |
| Frontend (TypeScript) | `frontend/src/utils/compactPawls.ts` | Decode only |
| Constants | `opencontractserver/constants/pawls.py` | Shared constants |
| Tests | `opencontractserver/tests/test_compact_pawls.py` | Full round-trip coverage |

### Comparison with Annotation Compact Format

A similar v2 compression strategy exists for annotation JSON payloads in `opencontractserver/annotations/compact_json.py`. It uses the same design principles (version marker, format-agnostic accessor, auto-compact on write) but applies range-encoding for token indices instead of array-based tokens. The annotation format achieves ~75% storage reduction.

## Migration Notes

If processing older documents without image tokens:

- Documents parsed before image support have only text tokens
- `is_image` field will be absent (falsy) for all tokens
- Re-parsing with current parsers will add image tokens

If processing older documents with v1 PAWLs format:

- v1 files on disk are NOT automatically converted — they stay as-is until re-parsed
- All read paths handle both formats transparently via `expand_pawls_pages()`
- New documents are always stored in v2 format automatically

## Related Documentation

- [PAWLs Token Format Walkthrough](../walkthrough/advanced/pawls-token-format.md)
- [Image Token Implementation Plan](../plans/phase-3-unified-image-tokens.md)
- [Pipeline Overview](../pipelines/pipeline_overview.md)
