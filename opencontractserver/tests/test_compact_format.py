"""
Tests for compact PAWLS and annotation JSON format converters.

Validates bidirectional conversion between legacy verbose format and
compact format with no data loss.
"""

import json

from django.test import TestCase

from opencontractserver.utils.compact_format import (
    compact_annotation_json,
    compact_bounding_box,
    compact_page,
    compact_pawls,
    compact_token,
    compact_tokens_jsons,
    expand_annotation_json,
    expand_bounding_box,
    expand_page,
    expand_pawls,
    expand_token,
    expand_tokens_jsons,
    is_compact_annotation_json,
    is_compact_bounding_box,
    is_compact_pawls,
    is_compact_tokens_jsons,
    normalize_annotation_json,
    normalize_bounding_box,
    normalize_pawls,
    normalize_tokens_jsons,
    to_compact_annotation_json,
    to_compact_pawls,
    to_compact_tokens_jsons,
)


class TestCompactToken(TestCase):
    """Test token conversion between legacy dict and compact array."""

    def test_compact_token_basic(self):
        token = {"x": 100.5, "y": 200.75, "width": 50.0, "height": 12.0, "text": "Hello"}
        result = compact_token(token)
        self.assertEqual(result, [100.5, 200.75, 50, 12, "Hello"])

    def test_compact_token_rounds_floats(self):
        token = {
            "x": 179.3040000000001,
            "y": 523.123456,
            "width": 18.0,
            "height": 12.0,
            "text": "test",
        }
        result = compact_token(token)
        self.assertEqual(result[0], 179.3)
        self.assertEqual(result[1], 523.12)
        self.assertEqual(result[2], 18)
        self.assertEqual(result[3], 12)

    def test_expand_token_basic(self):
        arr = [100.5, 200.75, 50.0, 12.0, "Hello"]
        result = expand_token(arr)
        self.assertEqual(result["x"], 100.5)
        self.assertEqual(result["y"], 200.75)
        self.assertEqual(result["width"], 50.0)
        self.assertEqual(result["height"], 12.0)
        self.assertEqual(result["text"], "Hello")

    def test_round_trip_token(self):
        token = {"x": 100.5, "y": 200.75, "width": 50.0, "height": 12.0, "text": "Hello"}
        result = expand_token(compact_token(token))
        self.assertAlmostEqual(result["x"], token["x"], places=2)
        self.assertAlmostEqual(result["y"], token["y"], places=2)
        self.assertAlmostEqual(result["width"], token["width"], places=2)
        self.assertAlmostEqual(result["height"], token["height"], places=2)
        self.assertEqual(result["text"], token["text"])


class TestCompactPage(TestCase):
    """Test page conversion between legacy and compact format."""

    def _make_legacy_page(self, index=0, num_tokens=3, has_image=False):
        tokens = [
            {
                "x": 100.0 + i * 50,
                "y": 200.0,
                "width": 40.0,
                "height": 12.0,
                "text": f"word{i}",
            }
            for i in range(num_tokens)
        ]
        if has_image:
            tokens.append(
                {
                    "x": 50.0,
                    "y": 300.0,
                    "width": 200.0,
                    "height": 150.0,
                    "text": "",
                    "is_image": True,
                    "image_path": "docs/123/images/page_0_img_0.jpg",
                    "format": "jpeg",
                    "content_hash": "abc123",
                    "original_width": 800,
                    "original_height": 600,
                    "image_type": "embedded",
                }
            )
        return {
            "page": {"width": 612.0, "height": 792.0, "index": index},
            "tokens": tokens,
        }

    def test_compact_page_basic(self):
        legacy = self._make_legacy_page()
        compact = compact_page(legacy)
        self.assertEqual(compact["p"], [612, 792, 0])
        self.assertEqual(len(compact["t"]), 3)
        self.assertNotIn("im", compact)

    def test_compact_page_with_image(self):
        legacy = self._make_legacy_page(has_image=True)
        compact = compact_page(legacy)
        self.assertIn("im", compact)
        self.assertIn("3", compact["im"])  # Image is 4th token (index 3)
        self.assertEqual(compact["im"]["3"]["p"], "docs/123/images/page_0_img_0.jpg")
        self.assertEqual(compact["im"]["3"]["f"], "jpeg")

    def test_expand_page_basic(self):
        legacy = self._make_legacy_page()
        compact = compact_page(legacy)
        expanded = expand_page(compact)
        self.assertEqual(expanded["page"]["width"], 612.0)
        self.assertEqual(expanded["page"]["height"], 792.0)
        self.assertEqual(expanded["page"]["index"], 0)
        self.assertEqual(len(expanded["tokens"]), 3)
        self.assertEqual(expanded["tokens"][0]["text"], "word0")

    def test_round_trip_page_with_image(self):
        legacy = self._make_legacy_page(has_image=True)
        expanded = expand_page(compact_page(legacy))
        img_token = expanded["tokens"][3]
        self.assertTrue(img_token.get("is_image"))
        self.assertEqual(img_token["image_path"], "docs/123/images/page_0_img_0.jpg")
        self.assertEqual(img_token["format"], "jpeg")
        self.assertEqual(img_token["content_hash"], "abc123")
        self.assertEqual(img_token["original_width"], 800)
        self.assertEqual(img_token["original_height"], 600)
        self.assertEqual(img_token["image_type"], "embedded")

    def test_compact_page_size_reduction(self):
        """Verify compact format is significantly smaller than legacy."""
        legacy = self._make_legacy_page(num_tokens=100)
        legacy_json = json.dumps(legacy)
        compact_json = json.dumps(compact_page(legacy), separators=(",", ":"))
        ratio = len(compact_json) / len(legacy_json)
        self.assertLess(ratio, 0.7, f"Compact should be <70% of legacy size, got {ratio:.1%}")


class TestCompactPawls(TestCase):
    """Test full document PAWLS conversion."""

    def _make_multi_page_document(self, num_pages=3):
        return [
            {
                "page": {"width": 612.0, "height": 792.0, "index": i},
                "tokens": [
                    {
                        "x": 100.0,
                        "y": 200.0 + j * 15,
                        "width": 40.0,
                        "height": 12.0,
                        "text": f"page{i}_word{j}",
                    }
                    for j in range(10)
                ],
            }
            for i in range(num_pages)
        ]

    def test_format_detection_legacy(self):
        legacy = self._make_multi_page_document()
        self.assertFalse(is_compact_pawls(legacy))

    def test_format_detection_compact(self):
        legacy = self._make_multi_page_document()
        compact = compact_pawls(legacy)
        self.assertTrue(is_compact_pawls(compact))

    def test_format_detection_empty(self):
        self.assertFalse(is_compact_pawls([]))

    def test_normalize_legacy_passes_through(self):
        legacy = self._make_multi_page_document()
        result = normalize_pawls(legacy)
        self.assertEqual(len(result), 3)
        self.assertIn("page", result[0])

    def test_normalize_compact_expands(self):
        legacy = self._make_multi_page_document()
        compact = compact_pawls(legacy)
        result = normalize_pawls(compact)
        self.assertEqual(len(result), 3)
        self.assertIn("page", result[0])
        self.assertEqual(result[0]["page"]["index"], 0)

    def test_to_compact_from_legacy(self):
        legacy = self._make_multi_page_document()
        result = to_compact_pawls(legacy)
        self.assertTrue(is_compact_pawls(result))

    def test_to_compact_idempotent(self):
        legacy = self._make_multi_page_document()
        compact = to_compact_pawls(legacy)
        result = to_compact_pawls(compact)
        self.assertEqual(compact, result)

    def test_round_trip_preserves_data(self):
        legacy = self._make_multi_page_document()
        result = normalize_pawls(compact_pawls(legacy))
        for i in range(len(legacy)):
            self.assertEqual(
                result[i]["page"]["index"], legacy[i]["page"]["index"]
            )
            self.assertEqual(
                len(result[i]["tokens"]), len(legacy[i]["tokens"])
            )
            for j in range(len(legacy[i]["tokens"])):
                self.assertEqual(
                    result[i]["tokens"][j]["text"],
                    legacy[i]["tokens"][j]["text"],
                )


class TestCompactAnnotationJson(TestCase):
    """Test annotation JSON conversion."""

    def _make_legacy_annotation(self, pages=1, tokens_per_page=5):
        result = {}
        for p in range(pages):
            result[str(p)] = {
                "bounds": {
                    "top": 100 + p * 50,
                    "bottom": 120 + p * 50,
                    "left": 50,
                    "right": 200,
                },
                "tokensJsons": [
                    {"pageIndex": p, "tokenIndex": i}
                    for i in range(tokens_per_page)
                ],
                "rawText": f"Text on page {p}",
            }
        return result

    def test_format_detection_legacy(self):
        legacy = self._make_legacy_annotation()
        self.assertFalse(is_compact_annotation_json(legacy))

    def test_format_detection_compact(self):
        legacy = self._make_legacy_annotation()
        compact = compact_annotation_json(legacy)
        self.assertTrue(is_compact_annotation_json(compact))

    def test_compact_annotation_basic(self):
        legacy = self._make_legacy_annotation()
        compact = compact_annotation_json(legacy)
        page_0 = compact["0"]
        self.assertEqual(page_0["b"], [50, 100, 200, 120])
        self.assertEqual(page_0["t"], [0, 1, 2, 3, 4])
        self.assertEqual(page_0["r"], "Text on page 0")

    def test_expand_annotation_basic(self):
        legacy = self._make_legacy_annotation()
        compact = compact_annotation_json(legacy)
        expanded = expand_annotation_json(compact)
        page_0 = expanded["0"]
        self.assertEqual(page_0["bounds"]["left"], 50)
        self.assertEqual(page_0["bounds"]["top"], 100)
        self.assertEqual(len(page_0["tokensJsons"]), 5)
        self.assertEqual(page_0["tokensJsons"][0]["pageIndex"], 0)
        self.assertEqual(page_0["tokensJsons"][0]["tokenIndex"], 0)

    def test_round_trip_preserves_data(self):
        legacy = self._make_legacy_annotation(pages=3, tokens_per_page=10)
        expanded = expand_annotation_json(compact_annotation_json(legacy))
        for p in range(3):
            key = str(p)
            self.assertEqual(
                expanded[key]["bounds"], legacy[key]["bounds"]
            )
            self.assertEqual(
                len(expanded[key]["tokensJsons"]),
                len(legacy[key]["tokensJsons"]),
            )
            self.assertEqual(
                expanded[key]["rawText"], legacy[key]["rawText"]
            )
            for i in range(10):
                self.assertEqual(
                    expanded[key]["tokensJsons"][i]["pageIndex"],
                    legacy[key]["tokensJsons"][i]["pageIndex"],
                )
                self.assertEqual(
                    expanded[key]["tokensJsons"][i]["tokenIndex"],
                    legacy[key]["tokensJsons"][i]["tokenIndex"],
                )

    def test_normalize_none(self):
        self.assertIsNone(normalize_annotation_json(None))

    def test_normalize_empty(self):
        self.assertEqual(normalize_annotation_json({}), {})

    def test_to_compact_none(self):
        self.assertIsNone(to_compact_annotation_json(None))

    def test_to_compact_idempotent(self):
        legacy = self._make_legacy_annotation()
        compact = to_compact_annotation_json(legacy)
        result = to_compact_annotation_json(compact)
        self.assertEqual(compact, result)

    def test_annotation_size_reduction(self):
        """Verify compact annotation JSON is significantly smaller."""
        legacy = self._make_legacy_annotation(pages=5, tokens_per_page=50)
        legacy_json = json.dumps(legacy)
        compact_json = json.dumps(
            compact_annotation_json(legacy), separators=(",", ":")
        )
        ratio = len(compact_json) / len(legacy_json)
        self.assertLess(
            ratio, 0.5,
            f"Compact should be <50% of legacy size, got {ratio:.1%}"
        )


class TestCompactBoundingBox(TestCase):
    """Test bounding box conversion."""

    def test_compact_bounding_box(self):
        bbox = {"top": 10, "bottom": 20, "left": 5, "right": 50}
        result = compact_bounding_box(bbox)
        self.assertEqual(result, [5, 10, 50, 20])

    def test_expand_bounding_box(self):
        arr = [5, 10, 50, 20]
        result = expand_bounding_box(arr)
        self.assertEqual(result["left"], 5)
        self.assertEqual(result["top"], 10)
        self.assertEqual(result["right"], 50)
        self.assertEqual(result["bottom"], 20)

    def test_is_compact_bbox(self):
        self.assertTrue(is_compact_bounding_box([1, 2, 3, 4]))
        self.assertFalse(is_compact_bounding_box({"top": 1}))
        self.assertFalse(is_compact_bounding_box([1, 2, 3]))

    def test_normalize_legacy(self):
        bbox = {"top": 10, "bottom": 20, "left": 5, "right": 50}
        result = normalize_bounding_box(bbox)
        self.assertEqual(result, bbox)

    def test_normalize_compact(self):
        result = normalize_bounding_box([5, 10, 50, 20])
        self.assertEqual(result["left"], 5)
        self.assertEqual(result["top"], 10)


class TestCompactTokensJsons(TestCase):
    """Test standalone TokenId list conversion."""

    def test_compact_tokens_jsons(self):
        tokens = [
            {"pageIndex": 0, "tokenIndex": 5},
            {"pageIndex": 0, "tokenIndex": 6},
            {"pageIndex": 1, "tokenIndex": 0},
        ]
        result = compact_tokens_jsons(tokens)
        self.assertEqual(result, [[0, 5], [0, 6], [1, 0]])

    def test_expand_tokens_jsons(self):
        compact = [[0, 5], [0, 6], [1, 0]]
        result = expand_tokens_jsons(compact)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["pageIndex"], 0)
        self.assertEqual(result[0]["tokenIndex"], 5)

    def test_is_compact(self):
        self.assertTrue(is_compact_tokens_jsons([[0, 5]]))
        self.assertFalse(is_compact_tokens_jsons([{"pageIndex": 0}]))
        self.assertFalse(is_compact_tokens_jsons([]))

    def test_normalize(self):
        compact = [[0, 5], [1, 3]]
        result = normalize_tokens_jsons(compact)
        self.assertEqual(result[0]["pageIndex"], 0)
        self.assertEqual(result[0]["tokenIndex"], 5)

    def test_to_compact_idempotent(self):
        legacy = [{"pageIndex": 0, "tokenIndex": 5}]
        compact = to_compact_tokens_jsons(legacy)
        result = to_compact_tokens_jsons(compact)
        self.assertEqual(compact, result)
