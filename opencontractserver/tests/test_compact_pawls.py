"""
Unit tests for compact PAWLs v2 format.

Tests encode/decode roundtrips, format detection, edge cases, and image tokens.
"""

from unittest import TestCase

from opencontractserver.utils.compact_pawls import (
    compact_pawls_pages,
    expand_pawls_pages,
    is_compact_pawls_format,
)

# ── Sample data ────────────────────────────────────────────────


_DEFAULT_TOKENS = [
    {"x": 72.0, "y": 720.0, "width": 41.0, "height": 12.0, "text": "Hello"},
    {"x": 120.5, "y": 720.0, "width": 35.2, "height": 12.0, "text": "world"},
]


def _make_v1_page(
    index: int = 0,
    width: float = 612.0,
    height: float = 792.0,
    tokens: list | None = None,
) -> dict:
    return {
        "page": {"width": width, "height": height, "index": index},
        "tokens": _DEFAULT_TOKENS if tokens is None else tokens,
    }


def _make_image_token(include_base64: bool = False) -> dict:
    token = {
        "x": 50.0,
        "y": 100.0,
        "width": 200.0,
        "height": 300.0,
        "text": "",
        "is_image": True,
        "image_path": "user_1/doc_42/images/page_0_img_0.jpg",
        "format": "jpeg",
        "content_hash": "abc123def456",
        "original_width": 800,
        "original_height": 600,
        "image_type": "embedded",
    }
    if include_base64:
        token["base64_data"] = "iVBORw0KGgoAAAANSUhEUg=="
    return token


# ── Tests ──────────────────────────────────────────────────────


class TestFormatDetection(TestCase):
    def test_v1_list_not_compact(self):
        self.assertFalse(is_compact_pawls_format([_make_v1_page()]))

    def test_v2_dict_is_compact(self):
        data = {"v": 2, "p": []}
        self.assertTrue(is_compact_pawls_format(data))

    def test_wrong_version(self):
        self.assertFalse(is_compact_pawls_format({"v": 1, "p": []}))

    def test_missing_p_key(self):
        self.assertFalse(is_compact_pawls_format({"v": 2}))

    def test_none(self):
        self.assertFalse(is_compact_pawls_format(None))

    def test_empty_dict(self):
        self.assertFalse(is_compact_pawls_format({}))


class TestCompactPawlsPages(TestCase):
    def test_compact_none(self):
        self.assertIsNone(compact_pawls_pages(None))

    def test_compact_empty_list(self):
        result = compact_pawls_pages([])
        self.assertTrue(is_compact_pawls_format(result))
        self.assertEqual(result["p"], [])

    def test_compact_single_page(self):
        v1 = [_make_v1_page()]
        result = compact_pawls_pages(v1)

        self.assertTrue(is_compact_pawls_format(result))
        self.assertEqual(result["v"], 2)
        self.assertEqual(len(result["p"]), 1)

        page = result["p"][0]
        self.assertEqual(page["w"], 612.0)
        self.assertEqual(page["h"], 792.0)
        self.assertEqual(len(page["t"]), 2)

        # Check first token
        tok = page["t"][0]
        self.assertEqual(tok[0], 72.0)  # x
        self.assertEqual(tok[1], 720.0)  # y
        self.assertEqual(tok[2], 41.0)  # width
        self.assertEqual(tok[3], 12.0)  # height
        self.assertEqual(tok[4], "Hello")  # text

    def test_compact_idempotent(self):
        """Already compact data should pass through unchanged."""
        v1 = [_make_v1_page()]
        v2 = compact_pawls_pages(v1)
        v2_again = compact_pawls_pages(v2)
        self.assertEqual(v2, v2_again)

    def test_compact_precision_rounding(self):
        """Coordinates should be rounded to 1 decimal place."""
        v1 = [
            _make_v1_page(
                tokens=[
                    {
                        "x": 72.123456,
                        "y": 720.999,
                        "width": 41.06,
                        "height": 12.04,
                        "text": "hi",
                    }
                ]
            )
        ]
        result = compact_pawls_pages(v1)
        tok = result["p"][0]["t"][0]
        self.assertEqual(tok[0], 72.1)
        self.assertEqual(tok[1], 721.0)
        self.assertEqual(tok[2], 41.1)  # 41.06 rounds to 41.1 at 1dp
        self.assertEqual(tok[3], 12.0)  # 12.04 rounds to 12.0

    def test_compact_image_token(self):
        """Image tokens should carry metadata in 6th element."""
        v1 = [_make_v1_page(tokens=[_make_image_token()])]
        result = compact_pawls_pages(v1)

        tok = result["p"][0]["t"][0]
        self.assertEqual(len(tok), 6)
        self.assertEqual(tok[4], "")  # text is empty for images

        meta = tok[5]
        self.assertEqual(meta["p"], "user_1/doc_42/images/page_0_img_0.jpg")
        self.assertEqual(meta["f"], "jpeg")
        self.assertEqual(meta["ch"], "abc123def456")
        self.assertEqual(meta["ow"], 800)
        self.assertEqual(meta["oh"], 600)
        self.assertEqual(meta["it"], "embedded")


class TestExpandPawlsPages(TestCase):
    def test_expand_none(self):
        self.assertEqual(expand_pawls_pages(None), [])

    def test_expand_v1_passthrough(self):
        """v1 data (list) should pass through unchanged."""
        v1 = [_make_v1_page()]
        result = expand_pawls_pages(v1)
        self.assertEqual(result, v1)

    def test_expand_empty_v2(self):
        result = expand_pawls_pages({"v": 2, "p": []})
        self.assertEqual(result, [])

    def test_expand_single_page(self):
        v2 = {
            "v": 2,
            "p": [
                {
                    "w": 612.0,
                    "h": 792.0,
                    "t": [[72.0, 720.0, 41.0, 12.0, "Hello"]],
                }
            ],
        }
        result = expand_pawls_pages(v2)

        self.assertEqual(len(result), 1)
        page = result[0]
        self.assertEqual(page["page"]["width"], 612.0)
        self.assertEqual(page["page"]["height"], 792.0)
        self.assertEqual(page["page"]["index"], 0)

        tok = page["tokens"][0]
        self.assertEqual(tok["x"], 72.0)
        self.assertEqual(tok["y"], 720.0)
        self.assertEqual(tok["width"], 41.0)
        self.assertEqual(tok["height"], 12.0)
        self.assertEqual(tok["text"], "Hello")

    def test_expand_image_token(self):
        """Image tokens should restore all metadata fields."""
        v2 = {
            "v": 2,
            "p": [
                {
                    "w": 612.0,
                    "h": 792.0,
                    "t": [
                        [
                            50.0,
                            100.0,
                            200.0,
                            300.0,
                            "",
                            {
                                "p": "path/img.jpg",
                                "f": "jpeg",
                                "ch": "hash123",
                                "ow": 800,
                                "oh": 600,
                                "it": "embedded",
                            },
                        ]
                    ],
                }
            ],
        }
        result = expand_pawls_pages(v2)
        tok = result[0]["tokens"][0]

        self.assertTrue(tok["is_image"])
        self.assertEqual(tok["image_path"], "path/img.jpg")
        self.assertEqual(tok["format"], "jpeg")
        self.assertEqual(tok["content_hash"], "hash123")
        self.assertEqual(tok["original_width"], 800)
        self.assertEqual(tok["original_height"], 600)
        self.assertEqual(tok["image_type"], "embedded")

    def test_expand_unrecognized_format(self):
        """Non-v2 dicts return empty list."""
        self.assertEqual(expand_pawls_pages({"random": "data"}), [])


class TestRoundTrip(TestCase):
    def test_roundtrip_text_tokens(self):
        """v1 → compact → expand should preserve all token data."""
        original = [
            _make_v1_page(index=0),
            _make_v1_page(
                index=1,
                width=800.0,
                height=1200.0,
                tokens=[
                    {
                        "x": 10.0,
                        "y": 20.0,
                        "width": 30.0,
                        "height": 40.0,
                        "text": "Page 2",
                    }
                ],
            ),
        ]

        compact = compact_pawls_pages(original)
        self.assertTrue(is_compact_pawls_format(compact))

        expanded = expand_pawls_pages(compact)
        self.assertEqual(len(expanded), 2)

        # Page 1
        self.assertEqual(expanded[0]["page"]["width"], 612.0)
        self.assertEqual(expanded[0]["page"]["height"], 792.0)
        self.assertEqual(expanded[0]["page"]["index"], 0)
        self.assertEqual(len(expanded[0]["tokens"]), 2)
        self.assertEqual(expanded[0]["tokens"][0]["text"], "Hello")
        self.assertEqual(expanded[0]["tokens"][1]["text"], "world")

        # Page 2
        self.assertEqual(expanded[1]["page"]["width"], 800.0)
        self.assertEqual(expanded[1]["page"]["height"], 1200.0)
        self.assertEqual(expanded[1]["page"]["index"], 1)
        self.assertEqual(len(expanded[1]["tokens"]), 1)
        self.assertEqual(expanded[1]["tokens"][0]["text"], "Page 2")

    def test_roundtrip_image_tokens(self):
        """Image tokens survive the roundtrip."""
        img_token = _make_image_token()
        text_token = {
            "x": 72.0,
            "y": 720.0,
            "width": 41.0,
            "height": 12.0,
            "text": "Caption",
        }
        original = [_make_v1_page(tokens=[text_token, img_token])]

        compact = compact_pawls_pages(original)
        expanded = expand_pawls_pages(compact)

        self.assertEqual(len(expanded[0]["tokens"]), 2)

        # Text token
        self.assertEqual(expanded[0]["tokens"][0]["text"], "Caption")
        self.assertNotIn("is_image", expanded[0]["tokens"][0])

        # Image token
        tok = expanded[0]["tokens"][1]
        self.assertTrue(tok["is_image"])
        self.assertEqual(tok["image_path"], img_token["image_path"])
        self.assertEqual(tok["format"], img_token["format"])
        self.assertEqual(tok["content_hash"], img_token["content_hash"])
        self.assertEqual(tok["original_width"], img_token["original_width"])
        self.assertEqual(tok["original_height"], img_token["original_height"])
        self.assertEqual(tok["image_type"], img_token["image_type"])

    def test_roundtrip_image_base64_data(self):
        """Image tokens with base64_data survive the roundtrip."""
        img_token = _make_image_token(include_base64=True)
        original = [_make_v1_page(tokens=[img_token])]

        compact = compact_pawls_pages(original)
        # Verify b64 key is in compact form
        self.assertIn("b64", compact["p"][0]["t"][0][5])

        expanded = expand_pawls_pages(compact)
        tok = expanded[0]["tokens"][0]
        self.assertTrue(tok["is_image"])
        self.assertEqual(tok["base64_data"], "iVBORw0KGgoAAAANSUhEUg==")

    def test_roundtrip_empty_pages(self):
        """Pages with no tokens survive the roundtrip."""
        original = [_make_v1_page(tokens=[])]
        compact = compact_pawls_pages(original)
        expanded = expand_pawls_pages(compact)
        self.assertEqual(len(expanded), 1)
        self.assertEqual(expanded[0]["tokens"], [])

    def test_roundtrip_precision(self):
        """Coordinates are rounded but otherwise stable across roundtrips."""
        original = [
            _make_v1_page(
                tokens=[
                    {
                        "x": 72.15,
                        "y": 720.0,
                        "width": 41.0,
                        "height": 12.0,
                        "text": "test",
                    }
                ]
            )
        ]

        compact = compact_pawls_pages(original)
        expanded = expand_pawls_pages(compact)

        # 72.15 rounds to 72.2 (1 dp)
        self.assertAlmostEqual(expanded[0]["tokens"][0]["x"], 72.2, places=1)

        # Second roundtrip should be stable
        compact2 = compact_pawls_pages(expanded)
        expanded2 = expand_pawls_pages(compact2)
        self.assertEqual(expanded2[0]["tokens"][0]["x"], expanded[0]["tokens"][0]["x"])


class TestEdgeCases(TestCase):
    def test_malformed_token_skipped(self):
        """Tokens with fewer than 5 elements are skipped on expand."""
        v2 = {
            "v": 2,
            "p": [
                {
                    "w": 100.0,
                    "h": 100.0,
                    "t": [
                        [1, 2, 3],  # Too short
                        [72.0, 720.0, 41.0, 12.0, "valid"],
                    ],
                }
            ],
        }
        result = expand_pawls_pages(v2)
        self.assertEqual(len(result[0]["tokens"]), 1)
        self.assertEqual(result[0]["tokens"][0]["text"], "valid")

    def test_max_tokens_per_page_fallback(self):
        """Compacting a page with too many tokens falls back to v1."""
        tokens = [
            {"x": 0, "y": 0, "width": 1, "height": 1, "text": f"t{i}"}
            for i in range(100_001)
        ]
        v1 = [_make_v1_page(tokens=tokens)]
        result = compact_pawls_pages(v1)
        # Should return original v1 data, not compact
        self.assertIs(result, v1)

    def test_non_list_input(self):
        """Non-list, non-dict input returns as-is from compact."""
        result = compact_pawls_pages("not a list")
        self.assertEqual(result, "not a list")

    def test_multi_page_index_preserved(self):
        """Page index in expanded data matches array position."""
        v1 = [_make_v1_page(index=i) for i in range(5)]
        compact = compact_pawls_pages(v1)
        expanded = expand_pawls_pages(compact)

        for i, page in enumerate(expanded):
            self.assertEqual(page["page"]["index"], i)
