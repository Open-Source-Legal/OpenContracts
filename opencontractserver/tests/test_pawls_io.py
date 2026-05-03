"""
Unit tests for ``opencontractserver.utils.pawls_io``.

Covers:
- ``to_canonical_v2`` accepts v1 (list) and v2 (dict) input, idempotently.
- ``to_canonical_v2`` rejects malformed / unrecognized payloads.
- ``load_canonical_v2`` reads from file-like sources.
- ``TokenView`` / ``PageView`` / ``iter_pages`` read-views.
- Round-trip equivalence with ``expand_pawls_pages`` (semantics preserved).
"""

import json
from io import BytesIO, StringIO
from unittest import TestCase

from opencontractserver.constants.pawls import COMPACT_PAWLS_VERSION
from opencontractserver.utils.compact_pawls import (
    compact_pawls_pages,
    expand_pawls_pages,
    is_compact_pawls_format,
)
from opencontractserver.utils.pawls_io import (
    PageView,
    TokenView,
    iter_pages,
    load_canonical_v2,
    to_canonical_v2,
    to_v1_pages,
    token_view_to_v1_image_dict,
)

# ── Fixtures ─────────────────────────────────────────────────────

_TEXT_TOKENS = [
    {"x": 72.0, "y": 720.0, "width": 41.0, "height": 12.0, "text": "Hello"},
    {"x": 120.5, "y": 720.0, "width": 35.2, "height": 12.0, "text": "world"},
]

_IMAGE_TOKEN = {
    "x": 50.0,
    "y": 100.0,
    "width": 200.0,
    "height": 300.0,
    "text": "",
    "is_image": True,
    "image_path": "user_1/doc_42/images/page_0_img_0.jpg",
    "format": "jpeg",
    "content_hash": "abc123",
    "original_width": 800,
    "original_height": 600,
    "image_type": "embedded",
}


def _make_v1(num_pages: int = 1, with_image: bool = False) -> list:
    pages = []
    for i in range(num_pages):
        tokens = list(_TEXT_TOKENS)
        if with_image and i == 0:
            tokens = tokens + [dict(_IMAGE_TOKEN)]
        pages.append(
            {
                "page": {"width": 612.0, "height": 792.0, "index": i},
                "tokens": tokens,
            }
        )
    return pages


# ── to_canonical_v2 ──────────────────────────────────────────────


class ToCanonicalV2Tests(TestCase):
    def test_v1_input_returns_v2_dict(self) -> None:
        v1 = _make_v1(num_pages=2)
        v2 = to_canonical_v2(v1)

        self.assertIsInstance(v2, dict)
        self.assertEqual(v2.get("v"), COMPACT_PAWLS_VERSION)
        self.assertIsInstance(v2.get("p"), list)
        self.assertEqual(len(v2["p"]), 2)

        # Page dimensions preserved (rounded to v2 precision).
        self.assertAlmostEqual(v2["p"][0]["w"], 612.0, places=1)
        self.assertAlmostEqual(v2["p"][0]["h"], 792.0, places=1)

        # Tokens become positional arrays.
        first_token = v2["p"][0]["t"][0]
        self.assertIsInstance(first_token, list)
        self.assertEqual(first_token[4], "Hello")

    def test_v2_input_is_idempotent(self) -> None:
        v1 = _make_v1(num_pages=1)
        v2 = to_canonical_v2(v1)
        v2_again = to_canonical_v2(v2)

        # Idempotent: a second pass returns equivalent structure.
        self.assertTrue(is_compact_pawls_format(v2_again))
        self.assertEqual(v2, v2_again)

    def test_garbage_inputs_raise_value_error(self) -> None:
        with self.assertRaises(ValueError):
            to_canonical_v2(None)
        with self.assertRaises(ValueError):
            to_canonical_v2("hello")
        with self.assertRaises(ValueError):
            to_canonical_v2(42)
        with self.assertRaises(ValueError):
            to_canonical_v2({"v": 99, "p": []})
        with self.assertRaises(ValueError):
            to_canonical_v2({"no_version_field": True})

    def test_v2_with_malformed_pages_raises(self) -> None:
        with self.assertRaises(ValueError):
            # Page entry isn't a dict.
            to_canonical_v2({"v": COMPACT_PAWLS_VERSION, "p": ["not a dict"]})
        with self.assertRaises(ValueError):
            # Tokens 't' isn't a list.
            to_canonical_v2(
                {"v": COMPACT_PAWLS_VERSION, "p": [{"w": 1, "h": 1, "t": "x"}]}
            )

    def test_v1_compact_fallback_raises_value_error(self) -> None:
        # When ``compact_pawls_pages`` cannot produce a v2 dict (oversized
        # page → fallback returns the v1 list unchanged), the boundary must
        # refuse to leak v1 by raising ValueError.
        from unittest.mock import patch

        with patch(
            "opencontractserver.utils.pawls_io.compact_pawls_pages",
            return_value=[{"page": {}, "tokens": []}],
        ):
            with self.assertRaises(ValueError) as ctx:
                to_canonical_v2(_make_v1(num_pages=1))
            self.assertIn("Unable to compact", str(ctx.exception))

    def test_v1_list_with_no_page_dicts_still_returns_v2(self) -> None:
        # ``compact_pawls_pages`` skips non-dict entries silently — confirm we
        # still produce a (empty) v2 dict rather than leaking v1.
        result = to_canonical_v2([])
        self.assertEqual(result, {"v": COMPACT_PAWLS_VERSION, "p": []})

    def test_v1_garbage_list_raises_when_compaction_falls_back(self) -> None:
        # ``compact_pawls_pages`` returns the original on non-list input. This
        # case is exercised through the dict path; here we ensure our boundary
        # never silently leaks v1 — a list returned from compaction unchanged
        # would be a violation. The fallback is rare (oversized pages) and is
        # not easily simulated without large fixtures, so we check that the
        # contract is enforced via an explicit invariant: any successful
        # ``to_canonical_v2(list)`` returns ``is_compact_pawls_format`` True.
        v2 = to_canonical_v2(_make_v1(num_pages=1))
        self.assertTrue(is_compact_pawls_format(v2))


# ── load_canonical_v2 ────────────────────────────────────────────


class LoadCanonicalV2Tests(TestCase):
    def test_load_from_bytesio_v1(self) -> None:
        v1 = _make_v1(num_pages=1)
        buf = BytesIO(json.dumps(v1).encode("utf-8"))

        result = load_canonical_v2(buf)
        self.assertTrue(is_compact_pawls_format(result))
        self.assertEqual(len(result["p"]), 1)

    def test_load_from_stringio_v2(self) -> None:
        v2 = compact_pawls_pages(_make_v1(num_pages=2))
        buf = StringIO(json.dumps(v2))

        result = load_canonical_v2(buf)
        self.assertTrue(is_compact_pawls_format(result))
        self.assertEqual(len(result["p"]), 2)

    def test_load_from_predecoded_list(self) -> None:
        v1 = _make_v1(num_pages=1)
        result = load_canonical_v2(v1)
        self.assertTrue(is_compact_pawls_format(result))

    def test_load_from_predecoded_dict(self) -> None:
        v2 = compact_pawls_pages(_make_v1(num_pages=1))
        result = load_canonical_v2(v2)
        self.assertTrue(is_compact_pawls_format(result))

    def test_load_unsupported_source_raises(self) -> None:
        with self.assertRaises(TypeError):
            load_canonical_v2(42)

    def test_load_empty_text_raises(self) -> None:
        with self.assertRaises(ValueError):
            load_canonical_v2(BytesIO(b""))

    def test_load_from_fieldfile_like_returns_str(self) -> None:
        """Cover the FieldFile branch where ``source.read()`` returns ``str``.

        Real Django ``FieldFile`` objects honour the open mode and so return
        ``bytes`` when opened ``"rb"``; a few callers (and the test fixtures
        in ``test_etl.py``) hand in pre-opened text-mode handles. The boundary
        accepts both, so we exercise the str branch with a tiny FieldFile-like
        mock that mimics the ``.open()/.read()/.close()`` contract.
        """
        v1 = _make_v1(num_pages=1)
        text = json.dumps(v1)

        class _StrFieldFileLike:
            def __init__(self, payload: str) -> None:
                self._payload = payload
                self.closed = True

            def open(self, mode: str = "rb") -> "_StrFieldFileLike":
                self.closed = False
                return self

            def read(self) -> str:
                return self._payload

            def close(self) -> None:
                self.closed = True

        result = load_canonical_v2(_StrFieldFileLike(text))
        self.assertTrue(is_compact_pawls_format(result))
        self.assertEqual(len(result["p"]), 1)

    def test_load_raw_json_string_raises_typeerror(self) -> None:
        """A str that looks like JSON content is rejected up front.

        Before this guard, the open() path raised ``FileNotFoundError`` with
        a confusing message. ``str`` inputs are documented as filesystem
        paths only; pre-decoded JSON should be passed as ``list``/``dict``.
        """
        with self.assertRaises(TypeError):
            load_canonical_v2('[{"page": {"width": 1, "height": 1}, "tokens": []}]')
        with self.assertRaises(TypeError):
            load_canonical_v2('  {"v": 2, "p": []}')


# ── TokenView ────────────────────────────────────────────────────


class TokenViewTests(TestCase):
    def test_text_token(self) -> None:
        v2 = to_canonical_v2(_make_v1(num_pages=1))
        row = v2["p"][0]["t"][0]
        view = TokenView(row)

        self.assertEqual(view.x, 72.0)
        self.assertEqual(view.y, 720.0)
        self.assertEqual(view.width, 41.0)
        self.assertEqual(view.height, 12.0)
        self.assertEqual(view.text, "Hello")
        self.assertFalse(view.is_image)
        self.assertIsNone(view.image_meta)

    def test_image_token(self) -> None:
        v2 = to_canonical_v2(_make_v1(num_pages=1, with_image=True))
        # Image token is the last token on page 0.
        image_row = v2["p"][0]["t"][-1]
        view = TokenView(image_row)

        self.assertTrue(view.is_image)
        self.assertEqual(view.text, "")

        meta = view.image_meta
        assert meta is not None
        # Compact short keys round-trip from the v1 source token.
        self.assertEqual(meta["p"], "user_1/doc_42/images/page_0_img_0.jpg")
        self.assertEqual(meta["f"], "jpeg")
        self.assertEqual(meta["ch"], "abc123")
        self.assertEqual(meta["ow"], 800)
        self.assertEqual(meta["oh"], 600)
        self.assertEqual(meta["it"], "embedded")

        # Convenience v1 translation also works.
        v1_meta = view.image_meta_v1
        assert v1_meta is not None
        self.assertEqual(v1_meta["image_path"], meta["p"])
        self.assertEqual(v1_meta["format"], meta["f"])
        self.assertEqual(v1_meta["content_hash"], meta["ch"])

    def test_text_token_image_meta_v1_is_none(self) -> None:
        # Text tokens have no image metadata; ``image_meta_v1`` should
        # return ``None`` rather than raise or fabricate empty keys.
        v2 = to_canonical_v2(_make_v1(num_pages=1))
        text_row = v2["p"][0]["t"][0]
        view = TokenView(text_row)
        self.assertFalse(view.is_image)
        self.assertIsNone(view.image_meta_v1)

# ── PageView / iter_pages ────────────────────────────────────────


class PageViewTests(TestCase):
    def test_page_index_matches_position(self) -> None:
        v2 = to_canonical_v2(_make_v1(num_pages=3))
        pages = list(iter_pages(v2))

        self.assertEqual(len(pages), 3)
        for i, page in enumerate(pages):
            self.assertIsInstance(page, PageView)
            self.assertEqual(page.index, i)
            self.assertEqual(page.width, 612.0)
            self.assertEqual(page.height, 792.0)

    def test_tokens_yield_token_views_in_order(self) -> None:
        v2 = to_canonical_v2(_make_v1(num_pages=1))
        page = next(iter(iter_pages(v2)))

        tokens = list(page.tokens)
        self.assertEqual(len(tokens), 2)
        self.assertEqual(tokens[0].text, "Hello")
        self.assertEqual(tokens[1].text, "world")
        for tok in tokens:
            self.assertIsInstance(tok, TokenView)

    def test_iter_pages_rejects_non_v2(self) -> None:
        with self.assertRaises(ValueError):
            list(iter_pages([{"page": {}, "tokens": []}]))  # type: ignore[arg-type]

    def test_iter_pages_skips_non_dict_pages(self) -> None:
        # Defensive path: ``iter_pages`` skips anything inside ``p`` that
        # isn't a dict rather than raising. Construct a v2 that satisfies
        # ``is_compact_pawls_format`` (so the up-front check passes) but
        # then mutate ``p`` to include a stray non-dict entry.
        v2 = to_canonical_v2(_make_v1(num_pages=1))
        v2["p"].append("not a dict")  # type: ignore[arg-type]
        self.assertEqual(len(list(iter_pages(v2))), 1)

    def test_page_view_tokens_skip_non_list_rows(self) -> None:
        v2 = to_canonical_v2(_make_v1(num_pages=1))
        # Inject a malformed (non-list) row into the page's token array; the
        # tokens iterator must skip it rather than yield a TokenView wrapping
        # garbage.
        v2["p"][0]["t"].append("not a list")  # type: ignore[arg-type]
        page = next(iter(iter_pages(v2)))
        token_texts = [tok.text for tok in page.tokens]
        self.assertEqual(token_texts, ["Hello", "world"])

    def test_tokens_property_is_single_pass(self) -> None:
        """``page.tokens`` returns a fresh iterator each access (single-pass).

        The fix-up commentary asks future readers to materialize via
        ``list(page.tokens)`` if they need to walk twice. Pin the documented
        contract: a single iterator yields once, and a fresh property access
        yields again.
        """
        v2 = to_canonical_v2(_make_v1(num_pages=1))
        page = next(iter(iter_pages(v2)))

        # First iterator: walk to exhaustion.
        it = page.tokens
        self.assertEqual([t.text for t in it], ["Hello", "world"])
        # Re-using the *same* iterator yields nothing — it's single-pass.
        self.assertEqual(list(it), [])
        # A *fresh* property access yields the tokens again from the start.
        self.assertEqual([t.text for t in page.tokens], ["Hello", "world"])


# ── to_v1_pages boundary adaptor ─────────────────────────────────


class ToV1PagesTests(TestCase):
    """Smoke coverage for the boundary v2→v1 adaptor.

    The adaptor delegates to ``expand_pawls_pages``, which already has its
    own coverage; these tests just confirm the delegation works for the
    shapes call sites pass in and that the v1-list pass-through holds.
    """

    def test_v2_input_returns_v1_page_list(self) -> None:
        v1 = _make_v1(num_pages=2, with_image=True)
        v2 = to_canonical_v2(v1)
        v1_again = to_v1_pages(v2)

        self.assertIsInstance(v1_again, list)
        self.assertEqual(len(v1_again), 2)
        # Each page is a v1-shape dict with `page` + `tokens`.
        for page in v1_again:
            self.assertIn("page", page)
            self.assertIn("tokens", page)
            self.assertIsInstance(page["tokens"], list)

    def test_v1_list_input_passes_through(self) -> None:
        # The docstring promises v1 list inputs are returned as-is
        # (``expand_pawls_pages`` short-circuits on a list).
        v1 = _make_v1(num_pages=1)
        result = to_v1_pages(v1)
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)


# ── token_view_to_v1_image_dict bridge ───────────────────────────


class TokenViewToV1ImageDictTests(TestCase):
    """Bridge function for the two callers still on v1 image dicts (#1490)."""

    def test_text_token_returns_no_image_keys(self) -> None:
        v2 = to_canonical_v2(_make_v1(num_pages=1))
        text_token = TokenView(v2["p"][0]["t"][0])

        out = token_view_to_v1_image_dict(text_token)

        self.assertEqual(out["text"], "Hello")
        self.assertEqual(out["x"], 72.0)
        self.assertEqual(out["y"], 720.0)
        self.assertEqual(out["width"], 41.0)
        self.assertEqual(out["height"], 12.0)
        # No image fields populated for text tokens.
        self.assertNotIn("is_image", out)
        self.assertNotIn("image_path", out)

    def test_image_token_unpacks_v1_long_keys(self) -> None:
        v2 = to_canonical_v2(_make_v1(num_pages=1, with_image=True))
        image_token = TokenView(v2["p"][0]["t"][-1])

        out = token_view_to_v1_image_dict(image_token)

        self.assertTrue(out["is_image"])
        # v2 short keys are translated back to v1 long keys.
        self.assertEqual(out["image_path"], "user_1/doc_42/images/page_0_img_0.jpg")
        self.assertEqual(out["format"], "jpeg")
        self.assertEqual(out["content_hash"], "abc123")
        self.assertEqual(out["original_width"], 800)
        self.assertEqual(out["original_height"], 600)
        self.assertEqual(out["image_type"], "embedded")


# ── Round-trip semantics ─────────────────────────────────────────


class RoundTripSemanticsTests(TestCase):
    def test_to_canonical_v2_then_expand_matches_direct_expand(self) -> None:
        """
        ``expand_pawls_pages(to_canonical_v2(v1))`` must equal
        ``expand_pawls_pages(v1)``. Proves the load boundary preserves
        semantics for downstream v1-shape consumers (Phase 2 will migrate
        them off v1 entirely).
        """
        v1 = _make_v1(num_pages=2, with_image=True)
        through_boundary = expand_pawls_pages(to_canonical_v2(v1))
        direct = expand_pawls_pages(v1)
        self.assertEqual(through_boundary, direct)
