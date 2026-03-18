"""
Tests for annotations/compact_json.py encode/decode, format detection,
and v1↔v2 conversion helpers.

Includes pure unit tests for the codec functions and integration tests
for the Annotation model's ``save()`` auto-compact behaviour.
"""

from unittest.mock import patch

from django.test import TestCase, override_settings

from opencontractserver.annotations.compact_json import (
    compact_annotation_json,
    decode_token_ranges,
    encode_token_ranges,
    expand_annotation_json,
    has_any_tokens,
    is_compact_format,
    is_span_format,
    iter_page_annotations,
    offset_annotation_json,
)
from opencontractserver.constants.annotations import (
    COMPACT_JSON_MAX_RANGE_SPAN,
    COMPACT_JSON_MAX_TOTAL_TOKENS,
)
from opencontractserver.tests.factories import AnnotationFactory

# ── helpers ──────────────────────────────────────────────────────


def _v1_page(bounds, token_indices, raw_text="hello"):
    """Build a single v1 page entry."""
    return {
        "bounds": bounds,
        "tokensJsons": [{"pageIndex": 0, "tokenIndex": i} for i in token_indices],
        "rawText": raw_text,
    }


# ── encode_token_ranges ─────────────────────────────────────────


class TestEncodeTokenRanges(TestCase):
    """Tests for encode_token_ranges."""

    def test_empty_list(self):
        self.assertEqual(encode_token_ranges([]), "")

    def test_single_item(self):
        self.assertEqual(encode_token_ranges([42]), "42")

    def test_consecutive_range(self):
        self.assertEqual(encode_token_ranges([1, 2, 3, 4, 5]), "1-5")

    def test_multiple_ranges(self):
        self.assertEqual(
            encode_token_ranges([1, 2, 3, 5, 7, 8, 9]),
            "1-3,5,7-9",
        )

    def test_duplicates_are_deduplicated(self):
        # Duplicates are removed before encoding.
        result = encode_token_ranges([3, 3, 3, 5, 5])
        self.assertEqual(result, "3,5")

    def test_unsorted_input_is_sorted(self):
        self.assertEqual(encode_token_ranges([5, 3, 1, 2, 4]), "1-5")

    def test_two_separate_items(self):
        self.assertEqual(encode_token_ranges([10, 20]), "10,20")

    def test_pair_range(self):
        self.assertEqual(encode_token_ranges([7, 8]), "7-8")

    def test_rejects_oversized_input(self):
        """encode_token_ranges raises ValueError when input exceeds limit."""
        oversized = list(range(COMPACT_JSON_MAX_TOTAL_TOKENS + 1))
        with self.assertRaises(ValueError):
            encode_token_ranges(oversized)


# ── decode_token_ranges ─────────────────────────────────────────


class TestDecodeTokenRanges(TestCase):
    """Tests for decode_token_ranges."""

    def test_empty_string(self):
        self.assertEqual(decode_token_ranges(""), [])

    def test_single_number(self):
        self.assertEqual(decode_token_ranges("42"), [42])

    def test_range(self):
        self.assertEqual(decode_token_ranges("1-3"), [1, 2, 3])

    def test_multiple_ranges(self):
        self.assertEqual(
            decode_token_ranges("1-3,5,7-9"),
            [1, 2, 3, 5, 7, 8, 9],
        )

    def test_malformed_non_numeric_skipped(self):
        # Non-numeric parts are silently skipped.
        self.assertEqual(decode_token_ranges("abc,5,x-y"), [5])

    def test_malformed_empty_parts_skipped(self):
        # Leading/trailing commas produce empty strings — skipped.
        self.assertEqual(decode_token_ranges(",5,"), [5])

    def test_negative_span_skipped(self):
        # "10-5" has a negative span → skipped.
        self.assertEqual(decode_token_ranges("10-5,42"), [42])

    def test_boundary_at_max_range_span(self):
        # A range exactly at MAX_RANGE_SPAN should be accepted.
        start = 0
        end = COMPACT_JSON_MAX_RANGE_SPAN  # span == MAX_RANGE_SPAN
        result = decode_token_ranges(f"{start}-{end}")
        self.assertEqual(len(result), COMPACT_JSON_MAX_RANGE_SPAN + 1)
        self.assertEqual(result[0], start)
        self.assertEqual(result[-1], end)

    def test_range_exceeding_max_span_skipped(self):
        start = 0
        end = COMPACT_JSON_MAX_RANGE_SPAN + 1
        result = decode_token_ranges(f"{start}-{end}")
        self.assertEqual(result, [])

    def test_truncation_at_max_total_tokens(self):
        # Build a range string manually (bypassing encode which now rejects
        # oversized inputs) to verify decode truncates gracefully.
        range_str = encode_token_ranges(list(range(COMPACT_JSON_MAX_TOTAL_TOKENS)))
        # Append extra tokens beyond the limit to the already-encoded string.
        extra_start = COMPACT_JSON_MAX_TOTAL_TOKENS
        extra_end = COMPACT_JSON_MAX_TOTAL_TOKENS + 99
        range_str += f",{extra_start}-{extra_end}"
        result = decode_token_ranges(range_str)
        self.assertLessEqual(len(result), COMPACT_JSON_MAX_TOTAL_TOKENS)


# ── roundtrip ────────────────────────────────────────────────────


class TestRoundtrip(TestCase):
    """encode → decode and decode → encode roundtrips."""

    def _assert_roundtrip_indices(self, indices):
        """Assert encode(indices) → decode → same sorted unique list."""
        encoded = encode_token_ranges(indices)
        decoded = decode_token_ranges(encoded)
        self.assertEqual(decoded, sorted(set(indices)))

    def test_roundtrip_empty(self):
        self._assert_roundtrip_indices([])

    def test_roundtrip_single(self):
        self._assert_roundtrip_indices([7])

    def test_roundtrip_consecutive(self):
        self._assert_roundtrip_indices([10, 11, 12, 13])

    def test_roundtrip_mixed(self):
        self._assert_roundtrip_indices([1, 2, 3, 10, 20, 21, 22, 50])

    def _assert_roundtrip_string(self, range_str):
        """Assert decode(range_str) → encode → same string."""
        decoded = decode_token_ranges(range_str)
        re_encoded = encode_token_ranges(decoded)
        self.assertEqual(re_encoded, range_str)

    def test_roundtrip_string_empty(self):
        self._assert_roundtrip_string("")

    def test_roundtrip_string_single(self):
        self._assert_roundtrip_string("42")

    def test_roundtrip_string_range(self):
        self._assert_roundtrip_string("1-5")

    def test_roundtrip_string_mixed(self):
        self._assert_roundtrip_string("1-3,5,7-9")


# ── is_compact_format ────────────────────────────────────────────


class TestIsCompactFormat(TestCase):
    """Tests for is_compact_format."""

    def test_v2_data(self):
        self.assertTrue(is_compact_format({"v": 2, "p": {}}))

    def test_v1_data(self):
        self.assertFalse(
            is_compact_format({"0": {"bounds": {}, "tokensJsons": [], "rawText": ""}})
        )

    def test_wrong_version(self):
        self.assertFalse(is_compact_format({"v": 1}))

    def test_none(self):
        self.assertFalse(is_compact_format(None))

    def test_non_dict(self):
        self.assertFalse(is_compact_format("not a dict"))
        self.assertFalse(is_compact_format(42))
        self.assertFalse(is_compact_format([1, 2]))


# ── is_span_format ───────────────────────────────────────────────


class TestIsSpanFormat(TestCase):
    """Tests for is_span_format."""

    def test_valid_span(self):
        self.assertTrue(is_span_format({"start": 0, "end": 10}))

    def test_valid_span_with_text(self):
        self.assertTrue(is_span_format({"start": 0, "end": 10, "text": "hi"}))

    def test_span_with_extra_metadata_keys(self):
        # Span annotations with extra metadata (e.g. from future parsers)
        # should still be detected as spans.
        self.assertTrue(is_span_format({"start": 0, "end": 10, "confidence": 0.95}))
        self.assertTrue(
            is_span_format({"start": 0, "end": 10, "text": "hi", "source": "parser_v2"})
        )

    def test_missing_start(self):
        self.assertFalse(is_span_format({"end": 10}))

    def test_missing_end(self):
        self.assertFalse(is_span_format({"start": 0}))

    def test_non_int_start_end_not_span(self):
        # Values must be ints to distinguish from page-keyed dicts.
        self.assertFalse(is_span_format({"start": "foo", "end": "bar"}))
        self.assertFalse(is_span_format({"start": {}, "end": {}}))

    def test_page_keyed_dict_not_span(self):
        # A v1 page-keyed dict has numeric string keys with dict values —
        # should NOT be detected as a span.
        self.assertFalse(
            is_span_format({"0": {"bounds": {}, "tokensJsons": [], "rawText": ""}})
        )

    def test_non_dict(self):
        self.assertFalse(is_span_format("not a dict"))
        self.assertFalse(is_span_format(None))
        self.assertFalse(is_span_format(42))

    def test_empty_dict(self):
        self.assertFalse(is_span_format({}))


# ── compact_annotation_json ──────────────────────────────────────


class TestCompactAnnotationJson(TestCase):
    """Tests for compact_annotation_json (v1 → v2 conversion)."""

    def test_none_returns_none(self):
        self.assertIsNone(compact_annotation_json(None))

    def test_empty_dict_returns_as_is(self):
        # Empty dict is falsy → returned as-is.
        self.assertEqual(compact_annotation_json({}), {})

    def test_non_dict_returns_as_is(self):
        self.assertEqual(compact_annotation_json("string"), "string")

    def test_already_compact_passthrough(self):
        v2 = {"v": 2, "p": {"0": {"b": [1, 2, 3, 4], "t": "0-5"}}}
        result = compact_annotation_json(v2)
        self.assertIs(result, v2)

    def test_span_passthrough(self):
        span = {"start": 5, "end": 20, "text": "hello"}
        result = compact_annotation_json(span)
        self.assertIs(result, span)

    def test_v1_to_v2_conversion(self):
        v1 = {
            "0": {
                "bounds": {"top": 10, "left": 20, "right": 30, "bottom": 40},
                "tokensJsons": [
                    {"pageIndex": 0, "tokenIndex": 1},
                    {"pageIndex": 0, "tokenIndex": 2},
                    {"pageIndex": 0, "tokenIndex": 3},
                    {"pageIndex": 0, "tokenIndex": 5},
                ],
                "rawText": "some text",
            }
        }
        result = compact_annotation_json(v1)

        self.assertEqual(result["v"], 2)
        self.assertIn("0", result["p"])

        page = result["p"]["0"]
        self.assertEqual(page["b"], [10, 20, 30, 40])
        self.assertEqual(page["t"], "1-3,5")

    def test_v1_multipage_conversion(self):
        v1 = {
            "0": _v1_page({"top": 1, "left": 2, "right": 3, "bottom": 4}, [10, 11]),
            "1": _v1_page({"top": 5, "left": 6, "right": 7, "bottom": 8}, [20]),
        }
        result = compact_annotation_json(v1)

        self.assertEqual(result["v"], 2)
        self.assertEqual(result["p"]["0"]["b"], [1, 2, 3, 4])
        self.assertEqual(result["p"]["0"]["t"], "10-11")
        self.assertEqual(result["p"]["1"]["b"], [5, 6, 7, 8])
        self.assertEqual(result["p"]["1"]["t"], "20")

    def test_missing_bounds_keys_default_to_zero(self):
        v1 = {"0": {"bounds": {}, "tokensJsons": []}}
        result = compact_annotation_json(v1)
        self.assertEqual(result["p"]["0"]["b"], [0, 0, 0, 0])

    def test_non_dict_page_data_skipped(self):
        v1 = {"0": "invalid"}
        result = compact_annotation_json(v1)
        self.assertEqual(result, {"v": 2, "p": {}})

    def test_integer_token_indices_accepted(self):
        # tokensJsons can contain bare integers instead of dicts.
        v1 = {"0": {"tokensJsons": [3, 4, 5]}}
        result = compact_annotation_json(v1)
        self.assertEqual(result["p"]["0"]["t"], "3-5")


# ── expand_annotation_json ───────────────────────────────────────


class TestExpandAnnotationJson(TestCase):
    """Tests for expand_annotation_json (v2 → v1 conversion)."""

    def test_non_dict_passthrough(self):
        self.assertIsNone(expand_annotation_json(None))
        self.assertEqual(expand_annotation_json("string"), "string")
        self.assertEqual(expand_annotation_json(42), 42)

    def test_span_passthrough(self):
        span = {"start": 0, "end": 10}
        result = expand_annotation_json(span)
        self.assertIs(result, span)

    def test_already_v1_passthrough(self):
        v1 = {
            "0": {
                "bounds": {"top": 1, "left": 2, "right": 3, "bottom": 4},
                "tokensJsons": [{"pageIndex": 0, "tokenIndex": 1}],
                "rawText": "text",
            }
        }
        result = expand_annotation_json(v1)
        self.assertIs(result, v1)

    def test_v2_to_v1_conversion(self):
        v2 = {
            "v": 2,
            "p": {
                "0": {"b": [10, 20, 30, 40], "t": "1-3,5"},
            },
        }
        result = expand_annotation_json(v2, raw_text="hello world")

        self.assertIn("0", result)
        page = result["0"]
        self.assertEqual(
            page["bounds"],
            {"top": 10, "left": 20, "right": 30, "bottom": 40},
        )
        expected_tokens = [
            {"pageIndex": 0, "tokenIndex": 1},
            {"pageIndex": 0, "tokenIndex": 2},
            {"pageIndex": 0, "tokenIndex": 3},
            {"pageIndex": 0, "tokenIndex": 5},
        ]
        self.assertEqual(page["tokensJsons"], expected_tokens)
        self.assertEqual(page["rawText"], "hello world")

    def test_v2_multipage_expansion(self):
        v2 = {
            "v": 2,
            "p": {
                "0": {"b": [1, 2, 3, 4], "t": "10-11"},
                "3": {"b": [5, 6, 7, 8], "t": "20"},
            },
        }
        result = expand_annotation_json(v2, raw_text="txt")

        self.assertIn("0", result)
        self.assertIn("3", result)
        # Page 0 tokens have pageIndex=0
        self.assertEqual(result["0"]["tokensJsons"][0]["pageIndex"], 0)
        # Page 3 tokens have pageIndex=3
        self.assertEqual(result["3"]["tokensJsons"][0]["pageIndex"], 3)

    def test_v2_missing_bounds_defaults_to_zeros(self):
        v2 = {"v": 2, "p": {"0": {"t": "1"}}}
        result = expand_annotation_json(v2)
        self.assertEqual(
            result["0"]["bounds"],
            {"top": 0, "left": 0, "right": 0, "bottom": 0},
        )

    def test_v2_empty_token_string(self):
        v2 = {"v": 2, "p": {"0": {"b": [0, 0, 0, 0], "t": ""}}}
        result = expand_annotation_json(v2)
        self.assertEqual(result["0"]["tokensJsons"], [])

    def test_v2_token_list_fallback(self):
        # "t" can be a list of ints instead of a range string.
        v2 = {"v": 2, "p": {"0": {"b": [0, 0, 0, 0], "t": [5, 6]}}}
        result = expand_annotation_json(v2)
        self.assertEqual(len(result["0"]["tokensJsons"]), 2)
        self.assertEqual(result["0"]["tokensJsons"][0]["tokenIndex"], 5)

    def test_v2_non_dict_pages_passthrough(self):
        v2 = {"v": 2, "p": "bad"}
        result = expand_annotation_json(v2)
        # Cannot iterate "bad" as a dict → returns original.
        self.assertIs(result, v2)

    def test_v2_non_dict_page_data_skipped(self):
        v2 = {"v": 2, "p": {"0": "invalid", "1": {"b": [0, 0, 0, 0], "t": "1"}}}
        result = expand_annotation_json(v2)
        self.assertNotIn("0", result)
        self.assertIn("1", result)


# ── full v1 → v2 → v1 roundtrip ─────────────────────────────────


class TestFullConversionRoundtrip(TestCase):
    """Test that compact(expand(data)) and expand(compact(data)) are stable."""

    def test_v1_compact_then_expand(self):
        v1 = {
            "0": {
                "bounds": {"top": 10, "left": 20, "right": 30, "bottom": 40},
                "tokensJsons": [
                    {"pageIndex": 0, "tokenIndex": 1},
                    {"pageIndex": 0, "tokenIndex": 2},
                    {"pageIndex": 0, "tokenIndex": 5},
                ],
                "rawText": "hello",
            }
        }
        v2 = compact_annotation_json(v1)
        restored = expand_annotation_json(v2, raw_text="hello")

        self.assertEqual(restored["0"]["bounds"], v1["0"]["bounds"])
        self.assertEqual(restored["0"]["tokensJsons"], v1["0"]["tokensJsons"])
        self.assertEqual(restored["0"]["rawText"], "hello")

    def test_v2_expand_then_compact(self):
        v2 = {
            "v": 2,
            "p": {
                "0": {"b": [10, 20, 30, 40], "t": "1-3,5"},
            },
        }
        v1 = expand_annotation_json(v2, raw_text="")
        re_compacted = compact_annotation_json(v1)

        self.assertEqual(re_compacted["v"], 2)
        self.assertEqual(re_compacted["p"]["0"]["b"], v2["p"]["0"]["b"])
        self.assertEqual(re_compacted["p"]["0"]["t"], v2["p"]["0"]["t"])


# ── save() auto-compact integration tests ────────────────────────


class TestAnnotationSaveAutoCompact(TestCase):
    """Integration tests for the Annotation.save() auto-compact path."""

    def test_save_compacts_v1_json_to_v2(self):
        """Saving a TOKEN_LABEL annotation with v1 JSON auto-compacts to v2."""
        v1_json = {
            "0": {
                "bounds": {"top": 10, "left": 20, "right": 30, "bottom": 40},
                "tokensJsons": [
                    {"pageIndex": 0, "tokenIndex": 1},
                    {"pageIndex": 0, "tokenIndex": 2},
                    {"pageIndex": 0, "tokenIndex": 3},
                ],
                "rawText": "hello world",
            }
        }
        annot = AnnotationFactory(json=v1_json)

        # After save the stored JSON must be v2 compact format.
        annot.refresh_from_db()
        self.assertTrue(is_compact_format(annot.json))
        self.assertEqual(annot.json["v"], 2)
        self.assertEqual(annot.json["p"]["0"]["t"], "1-3")
        self.assertEqual(annot.json["p"]["0"]["b"], [10, 20, 30, 40])

    def test_save_does_not_recompact_v2(self):
        """Saving an already-v2 annotation does not mutate the JSON."""
        v2_json = {"v": 2, "p": {"0": {"b": [1, 2, 3, 4], "t": "5-10"}}}
        annot = AnnotationFactory(json=v2_json)

        annot.refresh_from_db()
        self.assertEqual(annot.json, v2_json)

    @override_settings(VALIDATE_ANNOTATION_JSON=False)
    def test_save_does_not_compact_span(self):
        """Span annotations are left unchanged by the auto-compact path.

        Validation is disabled because this deliberately assigns span JSON
        to a TOKEN_LABEL annotation to exercise the span-detection guard
        in the auto-compact path.
        """
        span_json = {"start": 0, "end": 100}
        annot = AnnotationFactory(json=span_json)

        annot.refresh_from_db()
        self.assertEqual(annot.json, span_json)

    @patch(
        "opencontractserver.annotations.models.compact_annotation_json",
        side_effect=ValueError("boom"),
    )
    def test_save_exception_guard_logs_and_stores_as_is(self, mock_compact):
        """If compact_annotation_json raises, save() succeeds with original JSON."""
        v1_json = {
            "0": {
                "bounds": {"top": 0, "left": 0, "right": 0, "bottom": 0},
                "tokensJsons": [{"pageIndex": 0, "tokenIndex": 1}],
                "rawText": "",
            }
        }
        # Should not raise — exception is caught and logged.
        annot = AnnotationFactory(json=v1_json)

        annot.refresh_from_db()
        # v1 JSON stored as-is since compaction failed.
        self.assertFalse(is_compact_format(annot.json))
        self.assertIn("0", annot.json)


# ── clean() validation integration tests ─────────────────────────


@override_settings(VALIDATE_ANNOTATION_JSON=True)
class TestAnnotationCleanValidation(TestCase):
    """Integration tests for the Annotation.clean() JSON validation."""

    def test_clean_accepts_valid_v2_compact_json(self):
        """clean() passes for a well-formed v2 compact annotation."""
        v2_json = {"v": 2, "p": {"0": {"b": [1, 2, 3, 4], "t": "5-10"}}}
        annot = AnnotationFactory(json=v2_json)
        # clean() should not raise
        annot.clean()

    def test_clean_accepts_valid_v1_legacy_json(self):
        """clean() passes for a well-formed v1 legacy annotation."""
        v1_json = {
            "0": {
                "bounds": {"top": 1, "left": 2, "right": 3, "bottom": 4},
                "tokensJsons": [{"pageIndex": 0, "tokenIndex": 0}],
                "rawText": "hello",
            }
        }
        # save() auto-compacts, so build the annotation then set JSON directly
        annot = AnnotationFactory()
        annot.json = v1_json
        annot.clean()

    def test_clean_rejects_v2_with_non_dict_page_entry(self):
        """clean() raises when a v2 page entry is not a dict."""
        bad_json = {"v": 2, "p": {"0": "not_a_dict"}}
        annot = AnnotationFactory()
        annot.json = bad_json
        with self.assertRaises(ValueError, msg="v2 page entries must be dicts"):
            annot.clean()

    def test_clean_rejects_v2_missing_b_or_t(self):
        """clean() raises when a v2 page entry is missing 'b' or 't'."""
        bad_json = {"v": 2, "p": {"0": {"b": [0, 0, 0, 0]}}}
        annot = AnnotationFactory()
        annot.json = bad_json
        with self.assertRaises(ValueError, msg="must contain 'b' (bounds) and 't'"):
            annot.clean()

    def test_clean_accepts_v1_with_partial_keys(self):
        """clean() accepts v1 page entries with partial keys (shallow check).

        Auto-compaction in save() handles normalization of incomplete v1 data.
        """
        partial_json = {"0": {"bounds": {"top": 0, "left": 0, "right": 0, "bottom": 0}}}
        annot = AnnotationFactory()
        annot.json = partial_json
        annot.clean()  # should not raise


# ── bulk_update bypass documentation test ─────────────────────────


class TestBulkUpdateBypassesAutoCompact(TestCase):
    """Document that QuerySet.update() bypasses save() auto-compaction.

    This is an inherent Django limitation: ``QuerySet.update()`` and
    ``bulk_update()`` write directly to the database without calling
    ``save()``.  v1 JSON written via these paths stays v1.
    """

    def test_queryset_update_does_not_compact_v1(self):
        """Annotation.objects.filter().update(json=v1) stores v1 as-is."""
        from opencontractserver.annotations.models import Annotation

        annot = AnnotationFactory()
        v1_json = {
            "0": {
                "bounds": {"top": 1, "left": 2, "right": 3, "bottom": 4},
                "tokensJsons": [{"pageIndex": 0, "tokenIndex": 1}],
                "rawText": "test",
            }
        }
        Annotation.objects.filter(pk=annot.pk).update(json=v1_json)

        annot.refresh_from_db()
        # The JSON should remain v1 because update() bypasses save().
        self.assertFalse(is_compact_format(annot.json))
        self.assertIn("0", annot.json)
        self.assertIn("bounds", annot.json["0"])


# ── iter_page_annotations ────────────────────────────────────────


class TestIterPageAnnotations(TestCase):
    """Tests for iter_page_annotations (format-agnostic accessor)."""

    def test_v1_single_page(self):
        v1 = {
            "0": {
                "bounds": {"top": 10, "left": 20, "right": 30, "bottom": 40},
                "tokensJsons": [
                    {"pageIndex": 0, "tokenIndex": 1},
                    {"pageIndex": 0, "tokenIndex": 2},
                    {"pageIndex": 0, "tokenIndex": 5},
                ],
                "rawText": "hello",
            }
        }
        pages = list(iter_page_annotations(v1, raw_text="fallback"))
        self.assertEqual(len(pages), 1)
        page = pages[0]
        self.assertEqual(page.page_index, 0)
        self.assertEqual(
            page.bounds, {"top": 10, "left": 20, "right": 30, "bottom": 40}
        )
        self.assertEqual(page.token_indices, [1, 2, 5])
        # v1 per-page rawText takes precedence over the parameter
        self.assertEqual(page.raw_text, "hello")

    def test_v1_multi_page(self):
        v1 = {
            "0": _v1_page(
                {"top": 0, "left": 0, "right": 0, "bottom": 0}, [1, 2], "page0"
            ),
            "3": _v1_page(
                {"top": 1, "left": 1, "right": 1, "bottom": 1}, [10, 11], "page3"
            ),
        }
        pages = list(iter_page_annotations(v1))
        self.assertEqual(len(pages), 2)
        self.assertEqual(pages[0].page_index, 0)
        self.assertEqual(pages[0].token_indices, [1, 2])
        self.assertEqual(pages[0].raw_text, "page0")
        self.assertEqual(pages[1].page_index, 3)
        self.assertEqual(pages[1].token_indices, [10, 11])

    def test_v2_single_page(self):
        v2 = {"v": 2, "p": {"0": {"b": [10, 20, 30, 40], "t": "1-2,5"}}}
        pages = list(iter_page_annotations(v2, raw_text="hello"))
        self.assertEqual(len(pages), 1)
        page = pages[0]
        self.assertEqual(page.page_index, 0)
        self.assertEqual(
            page.bounds, {"top": 10, "left": 20, "right": 30, "bottom": 40}
        )
        self.assertEqual(page.token_indices, [1, 2, 5])
        self.assertEqual(page.raw_text, "hello")

    def test_v2_multi_page(self):
        v2 = {
            "v": 2,
            "p": {
                "0": {"b": [0, 0, 0, 0], "t": "1-3"},
                "5": {"b": [1, 1, 1, 1], "t": "10,20"},
            },
        }
        pages = list(iter_page_annotations(v2, raw_text="txt"))
        self.assertEqual(len(pages), 2)
        self.assertEqual(pages[0].page_index, 0)
        self.assertEqual(pages[0].token_indices, [1, 2, 3])
        self.assertEqual(pages[1].page_index, 5)
        self.assertEqual(pages[1].token_indices, [10, 20])

    def test_span_yields_nothing(self):
        span = {"start": 0, "end": 100}
        pages = list(iter_page_annotations(span))
        self.assertEqual(pages, [])

    def test_none_yields_nothing(self):
        pages = list(iter_page_annotations(None))
        self.assertEqual(pages, [])

    def test_empty_dict_yields_nothing(self):
        pages = list(iter_page_annotations({}))
        self.assertEqual(pages, [])

    def test_non_dict_input_yields_nothing(self):
        pages = list(iter_page_annotations("string"))
        self.assertEqual(pages, [])
        pages = list(iter_page_annotations(42))
        self.assertEqual(pages, [])

    def test_v1_missing_bounds_gets_zeros(self):
        v1 = {"0": {"tokensJsons": [{"pageIndex": 0, "tokenIndex": 1}]}}
        pages = list(iter_page_annotations(v1))
        self.assertEqual(len(pages), 1)
        self.assertEqual(
            pages[0].bounds, {"top": 0, "left": 0, "right": 0, "bottom": 0}
        )

    def test_v2_missing_bounds_gets_zeros(self):
        v2 = {"v": 2, "p": {"0": {"t": "1-3"}}}
        pages = list(iter_page_annotations(v2))
        self.assertEqual(len(pages), 1)
        self.assertEqual(
            pages[0].bounds, {"top": 0, "left": 0, "right": 0, "bottom": 0}
        )

    def test_v1_raw_text_fallback(self):
        """v1 page with no rawText uses the parameter as fallback."""
        v1 = {
            "0": {
                "bounds": {"top": 0, "left": 0, "right": 0, "bottom": 0},
                "tokensJsons": [],
            }
        }
        pages = list(iter_page_annotations(v1, raw_text="fallback"))
        self.assertEqual(pages[0].raw_text, "fallback")

    def test_v1_v2_produce_same_results(self):
        """The accessor yields identical data from v1 and v2 representations."""
        v1 = {
            "0": {
                "bounds": {"top": 10, "left": 20, "right": 30, "bottom": 40},
                "tokensJsons": [
                    {"pageIndex": 0, "tokenIndex": 1},
                    {"pageIndex": 0, "tokenIndex": 2},
                    {"pageIndex": 0, "tokenIndex": 3},
                ],
                "rawText": "hello",
            }
        }
        v2 = compact_annotation_json(v1)
        pages_v1 = list(iter_page_annotations(v1))
        pages_v2 = list(iter_page_annotations(v2, raw_text="hello"))

        self.assertEqual(len(pages_v1), len(pages_v2))
        for p1, p2 in zip(pages_v1, pages_v2):
            self.assertEqual(p1.page_index, p2.page_index)
            self.assertEqual(p1.bounds, p2.bounds)
            self.assertEqual(p1.token_indices, p2.token_indices)
            self.assertEqual(p1.raw_text, p2.raw_text)


# ── offset_annotation_json ───────────────────────────────────────


class TestOffsetAnnotationJson(TestCase):
    """Tests for offset_annotation_json."""

    def test_v1_offset(self):
        v1 = {
            "0": {
                "bounds": {"top": 0, "left": 0, "right": 0, "bottom": 0},
                "tokensJsons": [
                    {"pageIndex": 0, "tokenIndex": 1},
                    {"pageIndex": 0, "tokenIndex": 2},
                ],
                "rawText": "text",
            }
        }
        result = offset_annotation_json(v1, 5)
        self.assertIn("5", result)
        self.assertNotIn("0", result)
        # Token refs should also be offset
        for tok in result["5"]["tokensJsons"]:
            self.assertEqual(tok["pageIndex"], 5)

    def test_v2_offset(self):
        v2 = {"v": 2, "p": {"0": {"b": [1, 2, 3, 4], "t": "1-3"}}}
        result = offset_annotation_json(v2, 10)
        self.assertEqual(result["v"], 2)
        self.assertIn("10", result["p"])
        self.assertNotIn("0", result["p"])
        # Token ranges are untouched (no pageIndex in v2)
        self.assertEqual(result["p"]["10"]["t"], "1-3")

    def test_zero_offset_returns_same(self):
        v2 = {"v": 2, "p": {"0": {"b": [1, 2, 3, 4], "t": "1-3"}}}
        result = offset_annotation_json(v2, 0)
        self.assertIs(result, v2)

    def test_span_returned_unchanged(self):
        span = {"start": 0, "end": 100}
        result = offset_annotation_json(span, 5)
        self.assertEqual(result, span)

    def test_non_dict_returned_unchanged(self):
        self.assertIsNone(offset_annotation_json(None, 5))
        self.assertEqual(offset_annotation_json("str", 5), "str")

    def test_v1_multi_page_offset(self):
        v1 = {
            "0": _v1_page({"top": 0, "left": 0, "right": 0, "bottom": 0}, [1, 2]),
            "1": _v1_page({"top": 0, "left": 0, "right": 0, "bottom": 0}, [3, 4]),
        }
        result = offset_annotation_json(v1, 3)
        self.assertIn("3", result)
        self.assertIn("4", result)
        self.assertNotIn("0", result)
        self.assertNotIn("1", result)

    def test_preserves_format_v1(self):
        """v1 input produces v1 output."""
        v1 = {"0": _v1_page({"top": 0, "left": 0, "right": 0, "bottom": 0}, [1])}
        result = offset_annotation_json(v1, 1)
        self.assertFalse(is_compact_format(result))
        self.assertIn("tokensJsons", result["1"])

    def test_preserves_format_v2(self):
        """v2 input produces v2 output."""
        v2 = {"v": 2, "p": {"0": {"b": [0, 0, 0, 0], "t": "1"}}}
        result = offset_annotation_json(v2, 1)
        self.assertTrue(is_compact_format(result))


# ── has_any_tokens ───────────────────────────────────────────────


class TestHasAnyTokens(TestCase):
    """Tests for has_any_tokens."""

    def test_v1_with_tokens(self):
        v1 = {"0": _v1_page({"top": 0, "left": 0, "right": 0, "bottom": 0}, [1, 2])}
        self.assertTrue(has_any_tokens(v1))

    def test_v2_with_tokens(self):
        v2 = {"v": 2, "p": {"0": {"b": [0, 0, 0, 0], "t": "1-3"}}}
        self.assertTrue(has_any_tokens(v2))

    def test_v1_no_tokens(self):
        v1 = {
            "0": {
                "bounds": {"top": 0, "left": 0, "right": 0, "bottom": 0},
                "tokensJsons": [],
                "rawText": "",
            }
        }
        self.assertFalse(has_any_tokens(v1))

    def test_v2_no_tokens(self):
        v2 = {"v": 2, "p": {"0": {"b": [0, 0, 0, 0], "t": ""}}}
        self.assertFalse(has_any_tokens(v2))

    def test_span_has_tokens(self):
        self.assertTrue(has_any_tokens({"start": 0, "end": 100}))

    def test_none_no_tokens(self):
        self.assertFalse(has_any_tokens(None))

    def test_empty_dict_no_tokens(self):
        self.assertFalse(has_any_tokens({}))


# ── Additional coverage for edge/error paths ─────────────────────


class TestDecodeEdgePaths(TestCase):
    """Cover decode_token_ranges error handling and truncation logging."""

    @patch("opencontractserver.annotations.compact_json.logger")
    def test_truncation_emits_warning_log(self, mock_logger):
        """Verify that decode_token_ranges logs a warning when truncating."""
        # Build a range string with many small ranges that collectively exceed
        # MAX_TOTAL_TOKENS.  Each range must be <= MAX_RANGE_SPAN.
        step = COMPACT_JSON_MAX_RANGE_SPAN
        parts = []
        total = 0
        i = 0
        while total < COMPACT_JSON_MAX_TOTAL_TOKENS + 100:
            end = i + step - 1
            parts.append(f"{i}-{end}")
            total += step
            i = end + 1
        range_str = ",".join(parts)
        decode_token_ranges(range_str)
        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args[0][0]
        self.assertIn("truncated", call_args)

    def test_single_value_truncation(self):
        """Decode truncates when individual values exceed the limit."""
        # Build a string of individual comma-separated values beyond the limit.
        vals = ",".join(str(i) for i in range(COMPACT_JSON_MAX_TOTAL_TOKENS + 10))
        result = decode_token_ranges(vals)
        self.assertLessEqual(len(result), COMPACT_JSON_MAX_TOTAL_TOKENS)


class TestIterPageAnnotationsEdgePaths(TestCase):
    """Cover iter_page_annotations edge cases for both v1 and v2."""

    def test_v2_non_numeric_page_key_defaults_to_zero(self):
        """v2 page key that can't be parsed as int defaults to page_index=0."""
        v2 = {"v": 2, "p": {"abc": {"b": [1, 2, 3, 4], "t": "5"}}}
        pages = list(iter_page_annotations(v2, raw_text="test"))
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0].page_index, 0)

    def test_v1_non_numeric_page_key_defaults_to_zero(self):
        """v1 page key that can't be parsed as int defaults to page_index=0."""
        v1 = {
            "abc": {
                "bounds": {"top": 0, "left": 0, "right": 0, "bottom": 0},
                "tokensJsons": [{"pageIndex": 0, "tokenIndex": 1}],
                "rawText": "",
            }
        }
        pages = list(iter_page_annotations(v1))
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0].page_index, 0)

    def test_v2_non_dict_page_data_skipped(self):
        """Non-dict page data entries in v2 are silently skipped."""
        v2 = {
            "v": 2,
            "p": {
                "0": "not_a_dict",
                "1": {"b": [0, 0, 0, 0], "t": "1"},
            },
        }
        pages = list(iter_page_annotations(v2, raw_text=""))
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0].page_index, 1)

    def test_v1_non_dict_page_data_skipped(self):
        """Non-dict page data entries in v1 are silently skipped."""
        v1 = {
            "0": "not_a_dict",
            "1": _v1_page({"top": 0, "left": 0, "right": 0, "bottom": 0}, [1]),
        }
        pages = list(iter_page_annotations(v1))
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0].page_index, 1)

    def test_v2_token_list_fallback(self):
        """v2 page with t as a list instead of string is handled."""
        v2 = {"v": 2, "p": {"0": {"b": [0, 0, 0, 0], "t": [3, 4, 5]}}}
        pages = list(iter_page_annotations(v2, raw_text=""))
        self.assertEqual(pages[0].token_indices, [3, 4, 5])

    def test_v2_non_string_non_list_token_defaults_empty(self):
        """v2 page with t as unexpected type yields empty token_indices."""
        v2 = {"v": 2, "p": {"0": {"b": [0, 0, 0, 0], "t": 42}}}
        pages = list(iter_page_annotations(v2, raw_text=""))
        self.assertEqual(pages[0].token_indices, [])

    def test_v2_non_dict_p_yields_nothing(self):
        """v2 with non-dict p value yields no pages."""
        v2 = {"v": 2, "p": "not_a_dict"}
        pages = list(iter_page_annotations(v2))
        self.assertEqual(pages, [])

    def test_v1_mixed_token_formats(self):
        """v1 page with mixed dict and bare int token refs."""
        v1 = {
            "0": {
                "bounds": {"top": 0, "left": 0, "right": 0, "bottom": 0},
                "tokensJsons": [
                    {"pageIndex": 0, "tokenIndex": 1},
                    3,
                    {"pageIndex": 0, "tokenIndex": 5},
                ],
                "rawText": "",
            }
        }
        pages = list(iter_page_annotations(v1))
        self.assertEqual(pages[0].token_indices, [1, 3, 5])

    def test_v1_bounds_non_dict_gets_zeros(self):
        """v1 page where bounds is a non-dict value gets zero bounds."""
        v1 = {"0": {"bounds": "invalid", "tokensJsons": [], "rawText": ""}}
        pages = list(iter_page_annotations(v1))
        self.assertEqual(
            pages[0].bounds, {"top": 0, "left": 0, "right": 0, "bottom": 0}
        )


class TestExpandEdgePaths(TestCase):
    """Cover expand_annotation_json edge cases."""

    def test_v2_non_numeric_page_key_defaults_to_zero(self):
        """Expand v2 with non-numeric page key uses pageIndex=0 in tokens."""
        v2 = {"v": 2, "p": {"abc": {"b": [1, 2, 3, 4], "t": "5"}}}
        result = expand_annotation_json(v2, raw_text="test")
        self.assertIn("abc", result)
        self.assertEqual(result["abc"]["tokensJsons"][0]["pageIndex"], 0)

    def test_v2_token_type_none_yields_empty(self):
        """Expand v2 page where t is None yields empty tokensJsons."""
        v2 = {"v": 2, "p": {"0": {"b": [0, 0, 0, 0], "t": None}}}
        result = expand_annotation_json(v2)
        self.assertEqual(result["0"]["tokensJsons"], [])


class TestOffsetEdgePaths(TestCase):
    """Cover offset_annotation_json edge cases."""

    def test_v1_non_numeric_page_key_preserved(self):
        """v1 page with non-numeric key is preserved as-is."""
        v1 = {"abc": {"bounds": {"top": 0, "left": 0, "right": 0, "bottom": 0}}}
        result = offset_annotation_json(v1, 5)
        self.assertIn("abc", result)

    def test_v2_non_numeric_page_key_preserved(self):
        """v2 page with non-numeric key is preserved as-is."""
        v2 = {"v": 2, "p": {"abc": {"b": [0, 0, 0, 0], "t": "1"}}}
        result = offset_annotation_json(v2, 5)
        self.assertIn("abc", result["p"])


class TestCompactEdgePaths(TestCase):
    """Cover compact_annotation_json edge cases."""

    def test_bounds_non_dict_defaults_to_zeros(self):
        """v1 page where bounds is not a dict gets [0,0,0,0]."""
        v1 = {"0": {"bounds": "invalid", "tokensJsons": []}}
        result = compact_annotation_json(v1)
        self.assertEqual(result["p"]["0"]["b"], [0, 0, 0, 0])

    def test_tokens_jsons_missing_yields_no_t_key(self):
        """v1 page with no tokensJsons still produces a page entry."""
        v1 = {"0": {"bounds": {"top": 1, "left": 2, "right": 3, "bottom": 4}}}
        result = compact_annotation_json(v1)
        self.assertIn("0", result["p"])
        self.assertEqual(result["p"]["0"]["b"], [1, 2, 3, 4])
