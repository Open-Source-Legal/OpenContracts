# Bounding-Box Annotations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `bbox_annotations` field to document import data that resolves bounding-box coordinates to TOKEN_LABEL annotations by matching against PAWLs tokens.

**Architecture:** A standalone pure function `resolve_bbox_annotations()` converts bounding-box entries into standard `labelled_text` entries. Each of the four annotation-bearing import pathways calls this function to merge resolved entries into `labelled_text` before existing annotation import logic runs. No new models, mutations, pipeline stages, or frontend changes.

**Tech Stack:** Python, Django, TypedDict (typing), pytest

**Spec:** `docs/superpowers/specs/2026-03-21-bbox-annotations-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `opencontractserver/utils/bbox_resolution.py` | Create | `BboxAnnotationType` TypedDict + `resolve_bbox_annotations()` pure function |
| `opencontractserver/types/dicts.py` | Modify | Add `bbox_annotations` field to `OpenContractsDocAnnotations` (line 346) and `WorkerDocumentUploadMetadataType` (line 719) |
| `opencontractserver/tests/test_bbox_resolution.py` | Create | Unit tests for the resolution function (no Django, pure pytest) |
| `opencontractserver/tasks/import_tasks.py` | Modify | Integration in `import_document_to_corpus` (line 67) and `_apply_sidecar_annotations` (line 558) |
| `opencontractserver/tasks/import_tasks_v2.py` | Modify | Integration in `_import_document_with_annotations` (line 143) |
| `opencontractserver/worker_uploads/tasks.py` | Modify | Integration before `import_annotations` call (line 301) |
| `docs/upload_methods/bulk_zip_import.md` | Modify | Document `bbox_annotations` in sidecar schema |
| `docs/upload_methods/annotated_document_import.md` | Modify | Document `bbox_annotations` field |
| `docs/upload_methods/corpus_export_import.md` | Modify | Document `bbox_annotations` as import-only |
| `docs/upload_methods/worker_uploads.md` | Modify | Document `bbox_annotations` in metadata |
| `docs/upload_methods/annotation_side_effects.md` | Modify | Add bbox resolution section |
| `docs/upload_methods/index.md` | Modify | Update quick reference if needed |

---

## Task 1: TypedDict and Type Definitions

**Files:**
- Create: `opencontractserver/utils/bbox_resolution.py`
- Modify: `opencontractserver/types/dicts.py:346` and `dicts.py:719`

- [ ] **Step 1: Create `bbox_resolution.py` with the `BboxAnnotationType` TypedDict**

```python
"""
Bounding-box annotation resolution.

Converts bbox_annotations (PDF-point bounding boxes keyed by page) into
standard TOKEN_LABEL annotation dicts by matching against PAWLs tokens.
"""

from __future__ import annotations

import logging
from typing import Optional, Union

from typing_extensions import NotRequired, TypedDict

from opencontractserver.types.dicts import BoundingBoxPythonType

logger = logging.getLogger(__name__)


class BboxAnnotationType(TypedDict):
    """A bounding-box annotation entry in import data."""

    id: NotRequired[Optional[Union[str, int]]]
    annotationLabel: str
    rawText: str
    bounds: dict[str, list[BoundingBoxPythonType]]  # page (str) -> rects
    parent_id: NotRequired[Optional[Union[str, int]]]
    structural: NotRequired[bool]
    long_description: NotRequired[Optional[str]]
```

- [ ] **Step 2: Add `bbox_annotations` field to `OpenContractsDocAnnotations` in `dicts.py`**

In `opencontractserver/types/dicts.py`, add to the `OpenContractsDocAnnotations` class (after the `relationships` field at line 358):

```python
    # Bounding-box annotations resolved to TOKEN_LABEL at import time.
    # See docs/superpowers/specs/2026-03-21-bbox-annotations-design.md
    bbox_annotations: NotRequired[list["BboxAnnotationType"]]
```

Use a string-quoted annotation so no import of `BboxAnnotationType` is needed at
runtime (avoids circular imports):

```python
    bbox_annotations: NotRequired[list["BboxAnnotationType"]]
```

- [ ] **Step 3: Add `bbox_annotations` field to `WorkerDocumentUploadMetadataType` in `dicts.py`**

In `opencontractserver/types/dicts.py`, add to the `WorkerDocumentUploadMetadataType` class (after the `embeddings` field at line 759):

```python
    # Bounding-box annotations resolved to TOKEN_LABEL at import time
    bbox_annotations: NotRequired[list["BboxAnnotationType"]]
```

- [ ] **Step 4: Verify types are importable**

Run:
```bash
docker compose -f test.yml run django python -c "
from opencontractserver.utils.bbox_resolution import BboxAnnotationType
from opencontractserver.types.dicts import OpenContractsDocAnnotations, WorkerDocumentUploadMetadataType
print('All types imported successfully')
"
```

Expected: `All types imported successfully`

- [ ] **Step 5: Commit**

```bash
git add opencontractserver/utils/bbox_resolution.py opencontractserver/types/dicts.py
git commit -m "Add BboxAnnotationType and bbox_annotations field to import types"
```

---

## Task 2: Resolution Function — Core Logic

**Files:**
- Modify: `opencontractserver/utils/bbox_resolution.py`
- Create: `opencontractserver/tests/test_bbox_resolution.py`

- [ ] **Step 1: Write the failing test — single page, single rect, basic token matching**

Create `opencontractserver/tests/test_bbox_resolution.py`:

```python
"""Tests for bbox annotation resolution — pure function, no Django needed."""

import pytest

from opencontractserver.utils.bbox_resolution import resolve_bbox_annotations


def _make_pawls_page(page_index, width, height, tokens):
    """Helper to build a PAWLs page dict."""
    return {
        "page": {"width": width, "height": height, "index": page_index},
        "tokens": [
            {"x": t[0], "y": t[1], "width": t[2], "height": t[3], "text": t[4]}
            for t in tokens
        ],
    }


class TestResolveBboxAnnotations:
    """Core resolution tests."""

    def test_single_page_single_rect_matches_tokens(self):
        """Tokens whose center falls inside the rect are matched."""
        pawls_pages = [
            _make_pawls_page(
                0,
                612.0,
                792.0,
                [
                    # (x, y, width, height, text)
                    (100, 100, 50, 12, "Hello"),   # center (125, 106) — inside rect
                    (160, 100, 60, 12, "World"),   # center (190, 106) — inside rect
                    (400, 100, 40, 12, "Outside"), # center (420, 106) — outside rect
                ],
            )
        ]
        bbox_annotations = [
            {
                "id": "ann-1",
                "annotationLabel": "TEST_LABEL",
                "rawText": "Hello World",
                "bounds": {
                    "0": [{"top": 90, "bottom": 120, "left": 80, "right": 250}]
                },
            }
        ]
        result = resolve_bbox_annotations(pawls_pages, bbox_annotations)

        assert len(result) == 1
        ann = result[0]
        assert ann["annotationLabel"] == "TEST_LABEL"
        assert ann["rawText"] == "Hello World"
        assert ann["annotation_type"] == "TOKEN_LABEL"
        assert ann["page"] == 0

        # annotation_json should have page "0" with two matched tokens
        page_data = ann["annotation_json"]["0"]
        assert len(page_data["tokensJsons"]) == 2
        assert page_data["tokensJsons"][0] == {"pageIndex": 0, "tokenIndex": 0}
        assert page_data["tokensJsons"][1] == {"pageIndex": 0, "tokenIndex": 1}
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
docker compose -f test.yml run django pytest opencontractserver/tests/test_bbox_resolution.py::TestResolveBboxAnnotations::test_single_page_single_rect_matches_tokens -v --no-header
```

Expected: FAIL — `resolve_bbox_annotations` not defined or returns wrong result.

- [ ] **Step 3: Implement `resolve_bbox_annotations`**

Add to `opencontractserver/utils/bbox_resolution.py`:

```python
from opencontractserver.types.dicts import (
    BoundingBoxPythonType,
    OpenContractsAnnotationPythonType,
    OpenContractsSinglePageAnnotationType,
    PawlsPagePythonType,
    TokenIdPythonType,
)


def _token_center(token: dict) -> tuple[float, float]:
    """Compute the center point of a PAWLs token."""
    return (
        token["x"] + token["width"] / 2,
        token["y"] + token["height"] / 2,
    )


def _point_in_rect(cx: float, cy: float, rect: BoundingBoxPythonType) -> bool:
    """Check if a point falls inside a bounding rectangle."""
    return (
        rect["left"] <= cx <= rect["right"]
        and rect["top"] <= cy <= rect["bottom"]
    )


def _token_bounding_box(token: dict) -> BoundingBoxPythonType:
    """Convert a PAWLs token to a BoundingBoxPythonType."""
    return {
        "top": token["y"],
        "bottom": token["y"] + token["height"],
        "left": token["x"],
        "right": token["x"] + token["width"],
    }


def _union_bounding_box(
    boxes: list[BoundingBoxPythonType],
) -> BoundingBoxPythonType:
    """Compute the union bounding box of a list of bounding boxes."""
    return {
        "top": min(b["top"] for b in boxes),
        "bottom": max(b["bottom"] for b in boxes),
        "left": min(b["left"] for b in boxes),
        "right": max(b["right"] for b in boxes),
    }


def resolve_bbox_annotations(
    pawls_pages: list[PawlsPagePythonType],
    bbox_annotations: list[BboxAnnotationType],
) -> list[OpenContractsAnnotationPythonType]:
    """
    Resolve bounding-box annotations to TOKEN_LABEL annotations.

    For each bbox annotation, matches PAWLs tokens whose center point falls
    inside any of the annotation's bounding rectangles. Produces standard
    TOKEN_LABEL annotation dicts ready for ``import_doc_annotations``.

    Both input bounding boxes and PAWLs tokens use PDF points (1/72 inch)
    with top-left origin — no coordinate scaling is needed.

    Args:
        pawls_pages: PAWLs page data (list of page dicts with tokens).
        bbox_annotations: Bounding-box annotation entries to resolve.

    Returns:
        List of resolved ``OpenContractsAnnotationPythonType`` dicts with
        ``annotation_type = "TOKEN_LABEL"``.
    """
    pages_by_index: dict[int, dict] = {}
    for page_data in pawls_pages:
        pages_by_index[page_data["page"]["index"]] = page_data

    resolved: list[OpenContractsAnnotationPythonType] = []

    for bbox_ann in bbox_annotations:
        bounds = bbox_ann.get("bounds", {})
        if not bounds:
            logger.warning(
                "Skipping bbox annotation %s: empty bounds",
                bbox_ann.get("id", "<no id>"),
            )
            continue

        annotation_json: dict[str, OpenContractsSinglePageAnnotationType] = {}
        has_text_tokens = False
        has_image_tokens = False

        for page_str, rects in bounds.items():
            page_idx = int(page_str)
            page_data = pages_by_index.get(page_idx)
            if page_data is None:
                logger.warning(
                    "Skipping page %d for bbox annotation %s: "
                    "page index exceeds PAWLs page count (%d)",
                    page_idx,
                    bbox_ann.get("id", "<no id>"),
                    len(pawls_pages),
                )
                continue

            tokens = page_data["tokens"]
            matched_indices: list[int] = []

            for token_idx, token in enumerate(tokens):
                cx, cy = _token_center(token)
                if any(_point_in_rect(cx, cy, rect) for rect in rects):
                    matched_indices.append(token_idx)
                    if token.get("is_image"):
                        has_image_tokens = True
                    else:
                        has_text_tokens = True

            if not matched_indices:
                logger.warning(
                    "No tokens matched on page %d for bbox annotation %s",
                    page_idx,
                    bbox_ann.get("id", "<no id>"),
                )
                continue

            matched_tokens = [tokens[i] for i in matched_indices]
            token_boxes = [_token_bounding_box(t) for t in matched_tokens]

            page_annotation: OpenContractsSinglePageAnnotationType = {
                "bounds": _union_bounding_box(token_boxes),
                "tokensJsons": [
                    TokenIdPythonType(pageIndex=page_idx, tokenIndex=i)
                    for i in matched_indices
                ],
                "rawText": " ".join(t["text"] for t in matched_tokens if t.get("text")),
            }
            annotation_json[page_str] = page_annotation

        if not annotation_json:
            logger.warning(
                "Dropping bbox annotation %s: no tokens matched on any page",
                bbox_ann.get("id", "<no id>"),
            )
            continue

        # page field = minimum page number with matched tokens
        min_page = min(int(p) for p in annotation_json)

        # content_modalities
        modalities: list[str] = []
        if has_text_tokens:
            modalities.append("TEXT")
        if has_image_tokens:
            modalities.append("IMAGE")

        resolved_ann: OpenContractsAnnotationPythonType = {
            "id": bbox_ann.get("id"),
            "annotationLabel": bbox_ann["annotationLabel"],
            "rawText": bbox_ann["rawText"],
            "page": min_page,
            "annotation_json": annotation_json,
            "parent_id": bbox_ann.get("parent_id"),
            "annotation_type": "TOKEN_LABEL",
            "structural": bbox_ann.get("structural", False),
            "content_modalities": modalities,
        }
        if "long_description" in bbox_ann:
            resolved_ann["long_description"] = bbox_ann["long_description"]

        resolved.append(resolved_ann)

    return resolved
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
docker compose -f test.yml run django pytest opencontractserver/tests/test_bbox_resolution.py::TestResolveBboxAnnotations::test_single_page_single_rect_matches_tokens -v --no-header
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add opencontractserver/utils/bbox_resolution.py opencontractserver/tests/test_bbox_resolution.py
git commit -m "Implement resolve_bbox_annotations core logic with first test"
```

---

## Task 3: Resolution Function — Additional Tests

**Files:**
- Modify: `opencontractserver/tests/test_bbox_resolution.py`

- [ ] **Step 1: Write tests for multi-page, edge cases, and content_modalities**

Add these tests to `TestResolveBboxAnnotations` in `test_bbox_resolution.py`:

```python
    def test_multi_page_annotation(self):
        """Annotation spanning two pages produces multi-page annotation_json."""
        pawls_pages = [
            _make_pawls_page(0, 612.0, 792.0, [
                (100, 700, 50, 12, "End"),
            ]),
            _make_pawls_page(1, 612.0, 792.0, [
                (100, 50, 80, 12, "Beginning"),
            ]),
        ]
        bbox_annotations = [
            {
                "id": "mp-1",
                "annotationLabel": "SECTION",
                "rawText": "End to Beginning",
                "bounds": {
                    "0": [{"top": 690, "bottom": 720, "left": 80, "right": 200}],
                    "1": [{"top": 40, "bottom": 70, "left": 80, "right": 200}],
                },
            }
        ]
        result = resolve_bbox_annotations(pawls_pages, bbox_annotations)

        assert len(result) == 1
        ann = result[0]
        assert ann["page"] == 0  # min page
        assert "0" in ann["annotation_json"]
        assert "1" in ann["annotation_json"]
        assert len(ann["annotation_json"]["0"]["tokensJsons"]) == 1
        assert len(ann["annotation_json"]["1"]["tokensJsons"]) == 1

    def test_no_tokens_matched_drops_annotation(self):
        """Annotation with no matching tokens is dropped entirely."""
        pawls_pages = [
            _make_pawls_page(0, 612.0, 792.0, [
                (400, 400, 50, 12, "Far"),
            ])
        ]
        bbox_annotations = [
            {
                "id": "no-match",
                "annotationLabel": "LABEL",
                "rawText": "Ghost",
                "bounds": {
                    "0": [{"top": 0, "bottom": 10, "left": 0, "right": 10}],
                },
            }
        ]
        result = resolve_bbox_annotations(pawls_pages, bbox_annotations)
        assert len(result) == 0

    def test_empty_bounds_drops_annotation(self):
        """Annotation with empty bounds dict is dropped."""
        pawls_pages = [
            _make_pawls_page(0, 612.0, 792.0, [
                (100, 100, 50, 12, "Hello"),
            ])
        ]
        bbox_annotations = [
            {
                "id": "empty",
                "annotationLabel": "LABEL",
                "rawText": "Nothing",
                "bounds": {},
            }
        ]
        result = resolve_bbox_annotations(pawls_pages, bbox_annotations)
        assert len(result) == 0

    def test_page_exceeds_pawls_count_skipped(self):
        """Page number beyond PAWLs data is skipped; other pages still resolve."""
        pawls_pages = [
            _make_pawls_page(0, 612.0, 792.0, [
                (100, 100, 50, 12, "Real"),
            ])
        ]
        bbox_annotations = [
            {
                "id": "partial",
                "annotationLabel": "LABEL",
                "rawText": "Real",
                "bounds": {
                    "0": [{"top": 90, "bottom": 120, "left": 80, "right": 200}],
                    "99": [{"top": 0, "bottom": 10, "left": 0, "right": 10}],
                },
            }
        ]
        result = resolve_bbox_annotations(pawls_pages, bbox_annotations)
        assert len(result) == 1
        assert "0" in result[0]["annotation_json"]
        assert "99" not in result[0]["annotation_json"]

    def test_multiple_rects_on_same_page(self):
        """Multiple rects on one page match tokens from different regions."""
        pawls_pages = [
            _make_pawls_page(0, 612.0, 792.0, [
                (100, 100, 50, 12, "Top"),      # center (125, 106)
                (100, 500, 50, 12, "Bottom"),   # center (125, 506)
                (300, 300, 50, 12, "Middle"),    # center (325, 306) — not matched
            ])
        ]
        bbox_annotations = [
            {
                "id": "multi-rect",
                "annotationLabel": "LABEL",
                "rawText": "Top and Bottom",
                "bounds": {
                    "0": [
                        {"top": 90, "bottom": 120, "left": 80, "right": 200},
                        {"top": 490, "bottom": 520, "left": 80, "right": 200},
                    ],
                },
            }
        ]
        result = resolve_bbox_annotations(pawls_pages, bbox_annotations)
        assert len(result) == 1
        tokens = result[0]["annotation_json"]["0"]["tokensJsons"]
        assert len(tokens) == 2

    def test_preserves_rawtext_from_input(self):
        """Output rawText comes from the input, not from resolved tokens."""
        pawls_pages = [
            _make_pawls_page(0, 612.0, 792.0, [
                (100, 100, 50, 12, "tokenized"),
            ])
        ]
        bbox_annotations = [
            {
                "id": "rt",
                "annotationLabel": "LABEL",
                "rawText": "Custom Display Text",
                "bounds": {
                    "0": [{"top": 90, "bottom": 120, "left": 80, "right": 200}],
                },
            }
        ]
        result = resolve_bbox_annotations(pawls_pages, bbox_annotations)
        assert result[0]["rawText"] == "Custom Display Text"

    def test_parent_id_preserved(self):
        """parent_id from input is passed through to resolved annotation."""
        pawls_pages = [
            _make_pawls_page(0, 612.0, 792.0, [
                (100, 100, 50, 12, "Child"),
            ])
        ]
        bbox_annotations = [
            {
                "id": "child-1",
                "annotationLabel": "LABEL",
                "rawText": "Child",
                "bounds": {
                    "0": [{"top": 90, "bottom": 120, "left": 80, "right": 200}],
                },
                "parent_id": "parent-1",
            }
        ]
        result = resolve_bbox_annotations(pawls_pages, bbox_annotations)
        assert result[0]["parent_id"] == "parent-1"

    def test_long_description_preserved(self):
        """long_description is passed through when present."""
        pawls_pages = [
            _make_pawls_page(0, 612.0, 792.0, [
                (100, 100, 50, 12, "Section"),
            ])
        ]
        bbox_annotations = [
            {
                "id": "sec",
                "annotationLabel": "OC_SECTION",
                "rawText": "Section",
                "long_description": "# Markdown content",
                "bounds": {
                    "0": [{"top": 90, "bottom": 120, "left": 80, "right": 200}],
                },
            }
        ]
        result = resolve_bbox_annotations(pawls_pages, bbox_annotations)
        assert result[0]["long_description"] == "# Markdown content"

    def test_structural_flag_defaults_false(self):
        """structural defaults to False when not specified."""
        pawls_pages = [
            _make_pawls_page(0, 612.0, 792.0, [
                (100, 100, 50, 12, "Token"),
            ])
        ]
        bbox_annotations = [
            {
                "annotationLabel": "LABEL",
                "rawText": "Token",
                "bounds": {
                    "0": [{"top": 90, "bottom": 120, "left": 80, "right": 200}],
                },
            }
        ]
        result = resolve_bbox_annotations(pawls_pages, bbox_annotations)
        assert result[0]["structural"] is False

    def test_image_token_sets_image_modality(self):
        """Image tokens inside bounds set IMAGE in content_modalities."""
        pawls_pages = [
            {
                "page": {"width": 612.0, "height": 792.0, "index": 0},
                "tokens": [
                    {"x": 100, "y": 100, "width": 50, "height": 12, "text": "Text"},
                    {
                        "x": 100, "y": 200, "width": 200, "height": 150, "text": "",
                        "is_image": True, "image_path": "img.jpg", "format": "jpeg",
                    },
                ],
            }
        ]
        bbox_annotations = [
            {
                "id": "mixed",
                "annotationLabel": "LABEL",
                "rawText": "Mixed",
                "bounds": {
                    "0": [{"top": 50, "bottom": 400, "left": 50, "right": 400}],
                },
            }
        ]
        result = resolve_bbox_annotations(pawls_pages, bbox_annotations)
        assert "TEXT" in result[0]["content_modalities"]
        assert "IMAGE" in result[0]["content_modalities"]

    def test_union_bounding_box_in_annotation_json(self):
        """annotation_json bounds should be the union bbox of matched tokens."""
        pawls_pages = [
            _make_pawls_page(0, 612.0, 792.0, [
                (100, 100, 50, 12, "First"),   # box: top=100, bottom=112, left=100, right=150
                (200, 200, 60, 14, "Second"),  # box: top=200, bottom=214, left=200, right=260
            ])
        ]
        bbox_annotations = [
            {
                "id": "union",
                "annotationLabel": "LABEL",
                "rawText": "Both",
                "bounds": {
                    "0": [{"top": 50, "bottom": 300, "left": 50, "right": 300}],
                },
            }
        ]
        result = resolve_bbox_annotations(pawls_pages, bbox_annotations)
        bounds = result[0]["annotation_json"]["0"]["bounds"]
        assert bounds["top"] == 100
        assert bounds["bottom"] == 214
        assert bounds["left"] == 100
        assert bounds["right"] == 260

    def test_overlapping_annotations_resolve_independently(self):
        """Two bbox annotations covering the same tokens each get their own refs."""
        pawls_pages = [
            _make_pawls_page(0, 612.0, 792.0, [
                (100, 100, 50, 12, "Shared"),
            ])
        ]
        bbox_annotations = [
            {
                "id": "a1",
                "annotationLabel": "LABEL_A",
                "rawText": "First",
                "bounds": {
                    "0": [{"top": 90, "bottom": 120, "left": 80, "right": 200}],
                },
            },
            {
                "id": "a2",
                "annotationLabel": "LABEL_B",
                "rawText": "Second",
                "bounds": {
                    "0": [{"top": 90, "bottom": 120, "left": 80, "right": 200}],
                },
            },
        ]
        result = resolve_bbox_annotations(pawls_pages, bbox_annotations)
        assert len(result) == 2
        assert result[0]["annotationLabel"] == "LABEL_A"
        assert result[1]["annotationLabel"] == "LABEL_B"
        # Both reference the same token independently
        assert result[0]["annotation_json"]["0"]["tokensJsons"] == [{"pageIndex": 0, "tokenIndex": 0}]
        assert result[1]["annotation_json"]["0"]["tokensJsons"] == [{"pageIndex": 0, "tokenIndex": 0}]

    def test_empty_input_returns_empty(self):
        """Empty bbox_annotations list returns empty list."""
        pawls_pages = [
            _make_pawls_page(0, 612.0, 792.0, [
                (100, 100, 50, 12, "Token"),
            ])
        ]
        result = resolve_bbox_annotations(pawls_pages, [])
        assert result == []
```

- [ ] **Step 2: Run all tests**

Run:
```bash
docker compose -f test.yml run django pytest opencontractserver/tests/test_bbox_resolution.py -v --no-header
```

Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
git add opencontractserver/tests/test_bbox_resolution.py
git commit -m "Add comprehensive tests for bbox annotation resolution"
```

---

## Task 4: Integration Helper

**Files:**
- Modify: `opencontractserver/utils/bbox_resolution.py`

Before wiring up the four integration points, create a small helper that each
call site can use. This avoids duplicating the "check for bbox_annotations,
get PAWLs, resolve, merge" pattern four times.

- [ ] **Step 1: Write the failing test for the helper**

Add to `test_bbox_resolution.py`:

```python
from opencontractserver.utils.bbox_resolution import merge_bbox_into_labelled_text


class TestMergeBboxIntoLabelledText:
    """Tests for the merge helper."""

    def test_merges_resolved_into_existing_labelled_text(self):
        """Resolved bbox annotations are appended to existing labelled_text."""
        pawls_pages = [
            _make_pawls_page(0, 612.0, 792.0, [
                (100, 100, 50, 12, "Matched"),
            ])
        ]
        doc_data = {
            "labelled_text": [
                {
                    "id": "existing",
                    "annotationLabel": "EXISTING",
                    "rawText": "Already here",
                    "page": 0,
                    "annotation_json": {},
                    "parent_id": None,
                    "annotation_type": "TOKEN_LABEL",
                    "structural": False,
                }
            ],
            "bbox_annotations": [
                {
                    "id": "bbox-1",
                    "annotationLabel": "LABEL",
                    "rawText": "Matched",
                    "bounds": {
                        "0": [{"top": 90, "bottom": 120, "left": 80, "right": 200}],
                    },
                }
            ],
            "pawls_file_content": pawls_pages,
        }

        merge_bbox_into_labelled_text(doc_data)

        assert len(doc_data["labelled_text"]) == 2
        assert doc_data["labelled_text"][0]["id"] == "existing"
        assert doc_data["labelled_text"][1]["id"] == "bbox-1"

    def test_noop_when_no_bbox_annotations(self):
        """No changes when bbox_annotations is missing."""
        doc_data = {
            "labelled_text": [{"id": "only"}],
        }
        merge_bbox_into_labelled_text(doc_data)
        assert len(doc_data["labelled_text"]) == 1

    def test_noop_when_no_pawls(self):
        """No changes when pawls_file_content is missing (logs warning)."""
        doc_data = {
            "labelled_text": [],
            "bbox_annotations": [
                {
                    "annotationLabel": "LABEL",
                    "rawText": "Text",
                    "bounds": {"0": [{"top": 0, "bottom": 10, "left": 0, "right": 10}]},
                }
            ],
        }
        merge_bbox_into_labelled_text(doc_data)
        assert len(doc_data["labelled_text"]) == 0

    def test_initializes_labelled_text_if_missing(self):
        """Creates labelled_text key if it doesn't exist."""
        pawls_pages = [
            _make_pawls_page(0, 612.0, 792.0, [
                (100, 100, 50, 12, "Token"),
            ])
        ]
        doc_data = {
            "bbox_annotations": [
                {
                    "id": "new",
                    "annotationLabel": "LABEL",
                    "rawText": "Token",
                    "bounds": {
                        "0": [{"top": 90, "bottom": 120, "left": 80, "right": 200}],
                    },
                }
            ],
            "pawls_file_content": pawls_pages,
        }
        merge_bbox_into_labelled_text(doc_data)
        assert len(doc_data["labelled_text"]) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
docker compose -f test.yml run django pytest opencontractserver/tests/test_bbox_resolution.py::TestMergeBboxIntoLabelledText -v --no-header
```

Expected: FAIL — `merge_bbox_into_labelled_text` not defined.

- [ ] **Step 3: Implement `merge_bbox_into_labelled_text`**

Add to `opencontractserver/utils/bbox_resolution.py`:

```python
def merge_bbox_into_labelled_text(doc_data: dict) -> None:
    """
    Resolve ``bbox_annotations`` in *doc_data* and merge into ``labelled_text``.

    Modifies *doc_data* in place. No-op if ``bbox_annotations`` is absent or
    empty, or if ``pawls_file_content`` is not available.

    Args:
        doc_data: Document data dict (``OpenContractDocExport``-shaped or
            worker metadata). Must contain ``pawls_file_content`` for
            resolution to proceed.
    """
    bbox_annotations = doc_data.get("bbox_annotations")
    if not bbox_annotations:
        return

    pawls_pages = doc_data.get("pawls_file_content")
    if not pawls_pages:
        logger.warning(
            "bbox_annotations present but no pawls_file_content available — "
            "skipping bbox resolution"
        )
        return

    resolved = resolve_bbox_annotations(pawls_pages, bbox_annotations)
    if resolved:
        labelled_text = doc_data.get("labelled_text")
        if labelled_text is None:
            doc_data["labelled_text"] = resolved
        else:
            labelled_text.extend(resolved)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
docker compose -f test.yml run django pytest opencontractserver/tests/test_bbox_resolution.py -v --no-header
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add opencontractserver/utils/bbox_resolution.py opencontractserver/tests/test_bbox_resolution.py
git commit -m "Add merge_bbox_into_labelled_text helper for import integration"
```

---

## Task 5: Integration — Annotated Document Import

**Files:**
- Modify: `opencontractserver/tasks/import_tasks.py:67-150`

- [ ] **Step 1: Add the integration call**

In `opencontractserver/tasks/import_tasks.py`, in the `import_document_to_corpus` function, add the merge call **before** the `import_doc_annotations` call at line 143.

Add import at top of file:

```python
from opencontractserver.utils.bbox_resolution import merge_bbox_into_labelled_text
```

Then before line 143 (`_annot_id_map, _doc_labels_count = import_doc_annotations(`), add:

```python
        # Resolve bbox_annotations to TOKEN_LABEL if present
        merge_bbox_into_labelled_text(doc_data)
```

The `doc_data` dict already has `pawls_file_content` (it was used to create the document at line 119-124), so the helper will find it.

- [ ] **Step 2: Run existing annotated document import tests to verify no regression**

Run:
```bash
docker compose -f test.yml run django pytest opencontractserver/tests/test_annotated_document_import.py -v --no-header
```

Expected: All existing tests PASS.

- [ ] **Step 3: Commit**

```bash
git add opencontractserver/tasks/import_tasks.py
git commit -m "Integrate bbox resolution into annotated document import"
```

---

## Task 6: Integration — Corpus Export/Import (V2)

**Files:**
- Modify: `opencontractserver/tasks/import_tasks_v2.py:143-219`

- [ ] **Step 1: Add the integration call**

In `opencontractserver/tasks/import_tasks_v2.py`, in `_import_document_with_annotations`, add the merge call **before** `import_doc_annotations` at line 202.

Add import at top of file:

```python
from opencontractserver.utils.bbox_resolution import merge_bbox_into_labelled_text
```

Then before line 202 (`annot_id_map, _doc_labels_count = import_doc_annotations(`), add:

```python
            # Resolve bbox_annotations to TOKEN_LABEL if present
            merge_bbox_into_labelled_text(doc_data)
```

The `doc_data` dict has `pawls_file_content` from the export data.

- [ ] **Step 2: Run existing corpus import tests to verify no regression**

Run:
```bash
docker compose -f test.yml run django pytest opencontractserver/tests/test_corpus_export_import_v2.py opencontractserver/tests/test_corpus_import.py -v --no-header
```

Expected: All existing tests PASS.

- [ ] **Step 3: Commit**

```bash
git add opencontractserver/tasks/import_tasks_v2.py
git commit -m "Integrate bbox resolution into corpus export/import v2"
```

---

## Task 7: Integration — Bulk ZIP Sidecar Flow

**Files:**
- Modify: `opencontractserver/tasks/import_tasks.py:558-653`

- [ ] **Step 1: Add the integration call**

In `_apply_sidecar_annotations`, add the merge call **before** `import_doc_annotations` at line 603.

The sidecar `doc_data` will have `pawls_file_content` when `skip_pipeline: true` was used. When the pipeline runs (non-skip case), `pawls_file_content` won't be in `doc_data`, and `merge_bbox_into_labelled_text` will no-op with a warning.

Before line 600 (`# Import annotations onto the corpus document`), add:

```python
        # Resolve bbox_annotations to TOKEN_LABEL if present.
        # Requires pawls_file_content in doc_data (skip_pipeline case).
        merge_bbox_into_labelled_text(doc_data)
```

The import for `merge_bbox_into_labelled_text` was already added in Task 5.

- [ ] **Step 2: Run existing sidecar import tests to verify no regression**

Run:
```bash
docker compose -f test.yml run django pytest opencontractserver/tests/test_sidecar_import.py -v --no-header
```

Expected: All existing tests PASS.

- [ ] **Step 3: Commit**

```bash
git add opencontractserver/tasks/import_tasks.py
git commit -m "Integrate bbox resolution into bulk ZIP sidecar import"
```

---

## Task 8: Integration — Worker Uploads

**Files:**
- Modify: `opencontractserver/worker_uploads/tasks.py:300-307`

- [ ] **Step 1: Add the integration call**

In `_process_single_upload`, add the merge call **before** `import_annotations` at line 301.

Add import at top of file:

```python
from opencontractserver.utils.bbox_resolution import merge_bbox_into_labelled_text
```

Then before line 300 (`# 5. Import text annotations`), add:

```python
        # Resolve bbox_annotations to TOKEN_LABEL if present
        merge_bbox_into_labelled_text(metadata)
```

The `metadata` dict has `pawls_file_content` (line 239).

- [ ] **Step 2: Run existing worker upload tests to verify no regression**

Run:
```bash
docker compose -f test.yml run django pytest opencontractserver/tests/test_worker_uploads.py -v --no-header
```

Expected: All existing tests PASS.

- [ ] **Step 3: Commit**

```bash
git add opencontractserver/worker_uploads/tasks.py
git commit -m "Integrate bbox resolution into worker upload processing"
```

---

## Task 9: Documentation Updates

**Files:**
- Modify: `docs/upload_methods/bulk_zip_import.md`
- Modify: `docs/upload_methods/annotated_document_import.md`
- Modify: `docs/upload_methods/corpus_export_import.md`
- Modify: `docs/upload_methods/worker_uploads.md`
- Modify: `docs/upload_methods/annotation_side_effects.md`
- Modify: `docs/upload_methods/index.md`

- [ ] **Step 1: Update `annotated_document_import.md`**

Add a new section after "Import Data Schema" documenting `bbox_annotations`:

```markdown
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
```

- [ ] **Step 2: Update `bulk_zip_import.md`**

Add a section after "Relationships File" documenting bbox support in sidecars:

```markdown
## Bounding-Box Annotations in Sidecars

Sidecar JSON files can include a `bbox_annotations` array alongside
`labelled_text`. These are resolved to `TOKEN_LABEL` annotations at import
time by matching bounding-box coordinates against PAWLs tokens.

**Requirement:** `bbox_annotations` in sidecars requires `skip_pipeline: true`
in the sidecar data (meaning the sidecar also provides `pawls_file_content`).
When the parser pipeline runs (non-skip case), PAWLs data is not yet available
at sidecar application time, so bbox resolution is skipped.

See [Annotated Document Import](annotated_document_import.md#bounding-box-annotations-bbox_annotations)
for the full schema and resolution behavior.
```

- [ ] **Step 3: Update `corpus_export_import.md`**

Add a note in the "Importing a Corpus" section:

```markdown
### Bounding-Box Annotations

Each document entry in `annotated_docs` can include a `bbox_annotations` array.
These are resolved to `TOKEN_LABEL` annotations at import time using the
document's `pawls_file_content`. This is an import-only feature — corpus exports
never contain `bbox_annotations` (resolved annotations are standard
`TOKEN_LABEL`).

See [Annotated Document Import](annotated_document_import.md#bounding-box-annotations-bbox_annotations)
for the full schema.
```

- [ ] **Step 4: Update `worker_uploads.md`**

Add to the "Optional Metadata Fields" table:

```markdown
| `bbox_annotations` | array | Bounding-box annotations resolved to TOKEN_LABEL at import time (see [schema](annotated_document_import.md#bounding-box-annotations-bbox_annotations)) |
```

- [ ] **Step 5: Update `annotation_side_effects.md`**

Add a new section:

```markdown
## Bounding-Box Resolution

When documents are imported with a `bbox_annotations` field, a resolution step
converts bounding-box coordinates to standard `TOKEN_LABEL` annotations by
matching against PAWLs tokens. This runs at import time across all four
annotation-bearing import pathways:

- **Annotated Document Import** — resolves against inline `pawls_file_content`
- **Corpus Export/Import** — resolves against per-document `pawls_file_content`
- **Worker Uploads** — resolves against metadata `pawls_file_content`
- **Bulk ZIP Sidecars** — resolves when `skip_pipeline: true` (PAWLs in sidecar)

Resolved annotations are indistinguishable from annotations created through any
other pathway — they are standard `TOKEN_LABEL` entries with proper token
references. No unresolved bounding-box data is stored in the database.

See [Annotated Document Import](annotated_document_import.md#bounding-box-annotations-bbox_annotations)
for the full schema and resolution algorithm.
```

- [ ] **Step 6: Review `index.md`**

Check if the quick reference table needs updating. The `bbox_annotations` feature
doesn't add a new import method — it's a capability within existing methods. Add
a footnote or row if helpful:

```markdown
| Provide bounding-box coordinates instead of token indices | [Bounding-Box Annotations](annotated_document_import.md#bounding-box-annotations-bbox_annotations) |
```

- [ ] **Step 7: Final review pass over all `docs/upload_methods/` files**

Read all files in the directory and verify:
- Cross-references between docs are consistent
- No stale information contradicts the new feature
- Terminology is consistent (`bbox_annotations`, not `bbox_labels` or `bounding_box_annotations`)

- [ ] **Step 8: Commit**

```bash
git add docs/upload_methods/
git commit -m "Document bbox_annotations across all upload method docs"
```

---

## Task 10: Full Test Suite Verification

- [ ] **Step 1: Run all bbox resolution tests**

```bash
docker compose -f test.yml run django pytest opencontractserver/tests/test_bbox_resolution.py -v --no-header
```

Expected: All tests PASS.

- [ ] **Step 2: Run all import-related tests**

```bash
docker compose -f test.yml run django pytest opencontractserver/tests/test_annotated_document_import.py opencontractserver/tests/test_corpus_export_import_v2.py opencontractserver/tests/test_corpus_import.py opencontractserver/tests/test_sidecar_import.py opencontractserver/tests/test_worker_uploads.py opencontractserver/tests/test_import_utils.py -v --no-header
```

Expected: All tests PASS.

- [ ] **Step 3: Run pre-commit hooks**

```bash
pre-commit run --all-files
```

Expected: All checks PASS.

- [ ] **Step 4: Commit any formatting fixes**

```bash
git add -u && git commit -m "Fix formatting from pre-commit hooks"
```

(Only if pre-commit made changes.)
