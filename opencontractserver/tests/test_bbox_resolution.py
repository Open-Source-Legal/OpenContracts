"""Tests for bbox annotation resolution - pure function, no Django needed."""

from opencontractserver.utils.bbox_resolution import (
    merge_bbox_into_labelled_text,
    resolve_bbox_annotations,
)


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
                    (100, 100, 50, 12, "Hello"),  # center (125, 106) - inside
                    (160, 100, 60, 12, "World"),  # center (190, 106) - inside
                    (400, 100, 40, 12, "Outside"),  # center (420, 106) - outside
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

        page_data = ann["annotation_json"]["0"]
        assert len(page_data["tokensJsons"]) == 2
        assert page_data["tokensJsons"][0] == {"pageIndex": 0, "tokenIndex": 0}
        assert page_data["tokensJsons"][1] == {"pageIndex": 0, "tokenIndex": 1}

    def test_multi_page_annotation(self):
        """Annotation spanning two pages produces multi-page annotation_json."""
        pawls_pages = [
            _make_pawls_page(0, 612.0, 792.0, [(100, 700, 50, 12, "End")]),
            _make_pawls_page(1, 612.0, 792.0, [(100, 50, 80, 12, "Beginning")]),
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
            _make_pawls_page(0, 612.0, 792.0, [(400, 400, 50, 12, "Far")])
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
            _make_pawls_page(0, 612.0, 792.0, [(100, 100, 50, 12, "Hello")])
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
            _make_pawls_page(0, 612.0, 792.0, [(100, 100, 50, 12, "Real")])
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
            _make_pawls_page(
                0,
                612.0,
                792.0,
                [
                    (100, 100, 50, 12, "Top"),  # center (125, 106)
                    (100, 500, 50, 12, "Bottom"),  # center (125, 506)
                    (300, 300, 50, 12, "Middle"),  # center (325, 306) - not matched
                ],
            )
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
            _make_pawls_page(0, 612.0, 792.0, [(100, 100, 50, 12, "tokenized")])
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
            _make_pawls_page(0, 612.0, 792.0, [(100, 100, 50, 12, "Child")])
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
            _make_pawls_page(0, 612.0, 792.0, [(100, 100, 50, 12, "Section")])
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
            _make_pawls_page(0, 612.0, 792.0, [(100, 100, 50, 12, "Token")])
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
                    {
                        "x": 100,
                        "y": 100,
                        "width": 50,
                        "height": 12,
                        "text": "Text",
                    },
                    {
                        "x": 100,
                        "y": 200,
                        "width": 200,
                        "height": 150,
                        "text": "",
                        "is_image": True,
                        "image_path": "img.jpg",
                        "format": "jpeg",
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
            _make_pawls_page(
                0,
                612.0,
                792.0,
                [
                    (100, 100, 50, 12, "First"),
                    (200, 200, 60, 14, "Second"),
                ],
            )
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
            _make_pawls_page(0, 612.0, 792.0, [(100, 100, 50, 12, "Shared")])
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
        assert result[0]["annotation_json"]["0"]["tokensJsons"] == [
            {"pageIndex": 0, "tokenIndex": 0}
        ]
        assert result[1]["annotation_json"]["0"]["tokensJsons"] == [
            {"pageIndex": 0, "tokenIndex": 0}
        ]

    def test_empty_input_returns_empty(self):
        """Empty bbox_annotations list returns empty list."""
        pawls_pages = [
            _make_pawls_page(0, 612.0, 792.0, [(100, 100, 50, 12, "Token")])
        ]
        result = resolve_bbox_annotations(pawls_pages, [])
        assert result == []


class TestMergeBboxIntoLabelledText:
    """Tests for the merge helper."""

    def test_merges_resolved_into_existing_labelled_text(self):
        """Resolved bbox annotations are appended to existing labelled_text."""
        pawls_pages = [
            _make_pawls_page(0, 612.0, 792.0, [(100, 100, 50, 12, "Matched")])
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
        """No changes when pawls_file_content is missing."""
        doc_data = {
            "labelled_text": [],
            "bbox_annotations": [
                {
                    "annotationLabel": "LABEL",
                    "rawText": "Text",
                    "bounds": {
                        "0": [{"top": 0, "bottom": 10, "left": 0, "right": 10}]
                    },
                }
            ],
        }
        merge_bbox_into_labelled_text(doc_data)
        assert len(doc_data["labelled_text"]) == 0

    def test_initializes_labelled_text_if_missing(self):
        """Creates labelled_text key if it doesn't exist."""
        pawls_pages = [
            _make_pawls_page(0, 612.0, 792.0, [(100, 100, 50, 12, "Token")])
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
