"""
Unit tests for ``opencontractserver.utils.vcr_replay``.

These tests stay strictly in-memory — they do NOT make any HTTP calls,
read any cassette from disk, or invoke pydantic-ai. They cover the
helper's public surface:

* ``_normalize_body`` for every input shape VCR may hand it (None,
  bytes, str, dict, other).
* ``_match_llm_body`` mismatch / match behavior, including the
  volatility-stripping that lets a cassette recorded against one DB
  replay against another.
* ``maybe_vcr_cassette`` env-var routing: bypass when unset / "off",
  bypass with a warning when ``OC_LLM_VCR_CASSETTE`` is missing,
  bypass with a warning on unknown mode, and the active path that
  actually constructs a vcr.VCR cassette.

The test for the active path uses a temporary cassette path so we don't
touch the committed fixture cassette. ``maybe_vcr_cassette`` is a
context manager; entering it with no recorded interactions and no
network call means the cassette is a no-op for this test.
"""

from __future__ import annotations

import os
import re
import tempfile
from contextlib import contextmanager
from unittest import TestCase, mock

from opencontractserver.utils.vcr_replay import (
    _LLM_HOSTS,
    _VOLATILE_PATTERNS,
    _match_llm_body,
    _normalize_body,
    ensure_aiohttp_vcr_compat,
    maybe_vcr_cassette,
)


@contextmanager
def env_vars(**vars_to_set: str | None):
    """Set / unset env vars within a ``with`` block, restoring afterward.

    Pass ``None`` to ensure a variable is unset for the duration.
    """
    saved: dict[str, str | None] = {}
    for k, v in vars_to_set.items():
        saved[k] = os.environ.get(k)
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    try:
        yield
    finally:
        for k, prev in saved.items():
            if prev is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = prev


class _FakeReq:
    """Minimal stand-in for vcr.request.Request — only ``.body`` is read."""

    def __init__(self, body):
        self.body = body


class NormalizeBodyTests(TestCase):
    def test_none_returns_empty_bytes(self):
        self.assertEqual(_normalize_body(None), b"")

    def test_empty_string_returns_empty_bytes(self):
        self.assertEqual(_normalize_body(""), b"")

    def test_bytes_passthrough_when_no_volatile(self):
        body = b'{"foo":"bar"}'
        self.assertEqual(_normalize_body(body), body)

    def test_string_input_is_encoded_then_normalized(self):
        body = '{"ts":1777000000000}'
        out = _normalize_body(body)
        self.assertIsInstance(out, bytes)
        # The 13-digit ms timestamp pattern should have been stripped.
        self.assertIn(b"<volatile>", out)
        self.assertNotIn(b"1777000000000", out)

    def test_dict_input_is_serialized_deterministically(self):
        # Order should not affect the normalized output for the same
        # logical dict.
        a = _normalize_body({"a": 1, "b": 2})
        b = _normalize_body({"b": 2, "a": 1})
        self.assertEqual(a, b)
        self.assertIn(b'"a"', a)

    def test_bytearray_input_is_handled(self):
        body = bytearray(b'{"x":1}')
        out = _normalize_body(body)
        self.assertEqual(out, b'{"x":1}')
        self.assertIsInstance(out, bytes)

    def test_other_type_falls_back_to_repr(self):
        # Coercion of an int — covers the "last-resort" branch so the
        # matcher never raises on unexpected body types.
        out = _normalize_body(42)
        self.assertEqual(out, b"42")

    def test_run_id_timestamp_is_stripped(self):
        body = b"before 1777504812606 after"
        out = _normalize_body(body)
        self.assertEqual(out, b"before <volatile> after")

    def test_django_document_pk_is_stripped(self):
        body = b"document <user_content>foo</user_content> (ID: 56) extra"
        out = _normalize_body(body)
        self.assertIn(b"<volatile>", out)
        self.assertNotIn(b"(ID: 56)", out)

    def test_openai_call_id_is_stripped(self):
        body = b'{"id":"call_GAVRUwuC2ZGQxMezJY7WDVHT","type":"function"}'
        out = _normalize_body(body)
        self.assertIn(b"<volatile>", out)
        self.assertNotIn(b"call_GAVRUwuC2ZGQxMezJY7WDVHT", out)

    def test_tool_call_id_is_stripped(self):
        body = b'{"role":"tool","tool_call_id":"call_AmcD7e7RJpIBnDJu5F1Qjcvj"}'
        out = _normalize_body(body)
        self.assertIn(b"<volatile>", out)
        self.assertNotIn(b"call_AmcD7e7RJpIBnDJu5F1Qjcvj", out)

    def test_uuid_is_stripped(self):
        body = b"annotation 12345678-1234-1234-1234-1234567890ab end"
        out = _normalize_body(body)
        self.assertEqual(out, b"annotation <volatile> end")

    def test_django_pk_fields_in_tool_results_are_stripped(self):
        # The agent echoes tool messages back into the next assistant
        # call. Tool results embed Django auto-increment PKs (annotation,
        # corpus, document, label) that vary across runs even when the
        # underlying retrieved span is identical. Strip them so the
        # cassette matches across record/replay DBs.
        body = (
            b'{"annotation_id":22868,"corpus_id":81,"document_id":null,'
            b'"label_id":340,"id":42,"content":"TITLE"}'
        )
        out = _normalize_body(body)
        for stale in (b"22868", b'"corpus_id":81', b'"label_id":340', b'"id":42'):
            self.assertNotIn(stale, out)
        # Stable values (the actual content) survive.
        self.assertIn(b"TITLE", out)

    def test_similarity_score_floats_are_stripped(self):
        # Hybrid-search scores drift run-to-run by a few decimal places.
        # The matcher must ignore the absolute number so a cassette
        # recorded against one DB replays against a fresh one.
        body = (
            b'{"similarity_score":0.029236022193768675,'
            b'"escaped":"\\"score\\":0.123e-2,\\"foo\\":1"}'
        )
        out = _normalize_body(body)
        self.assertNotIn(b"0.029236022193768675", out)
        self.assertNotIn(b"0.123e-2", out)

    def test_pk_fields_in_escaped_tool_message_are_stripped(self):
        # Tool result payloads are JSON-encoded *inside* the
        # chat-completion request body, so inner quotes appear escaped.
        # The matcher must strip PKs in both the raw and escaped forms.
        body = (
            b'{"role":"tool","content":"[{\\"annotation_id\\":22868,'
            b'\\"corpus_id\\":81,\\"document_id\\":null,'
            b'\\"label_id\\":340,\\"id\\":42,\\"content\\":\\"TITLE\\"}]"}'
        )
        out = _normalize_body(body)
        for stale in (b"22868", b"81", b"340", b"42"):
            # Belt-and-braces: the raw integers should not survive in
            # any of their PK positions.
            self.assertNotIn(b'":' + stale, out)
            self.assertNotIn(b'\\":' + stale, out)
        self.assertIn(b"TITLE", out)

    def test_compiled_volatile_patterns_are_bytes(self):
        # Defense-in-depth: make sure no string regex sneaked in. Bytes
        # patterns are required because the matcher always works on
        # bytes after normalization.
        for pat in _VOLATILE_PATTERNS:
            self.assertIsInstance(pat, re.Pattern)
            self.assertIsInstance(pat.pattern, bytes)


class MatchLlmBodyTests(TestCase):
    def test_identical_bytes_match(self):
        a = _FakeReq(b'{"x":1}')
        b = _FakeReq(b'{"x":1}')
        # No raise == match. ``_match_llm_body`` is annotated -> None,
        # so we just call it and rely on absence of AssertionError.
        _match_llm_body(a, b)

    def test_identical_after_volatility_strip(self):
        # Different RUN_ID timestamps but otherwise identical body.
        a = _FakeReq(b"prefix 1777504812606 suffix")
        b = _FakeReq(b"prefix 1777999999999 suffix")
        _match_llm_body(a, b)

    def test_different_bodies_raise(self):
        a = _FakeReq(b"alpha")
        b = _FakeReq(b"beta")
        with self.assertRaises(AssertionError):
            _match_llm_body(a, b)

    def test_string_body_matches_equivalent_bytes(self):
        # vcrpy may pass either, depending on the source of the request.
        a = _FakeReq(b"hello")
        b = _FakeReq("hello")
        _match_llm_body(a, b)

    def test_none_body_matches_empty(self):
        a = _FakeReq(None)
        b = _FakeReq(b"")
        _match_llm_body(a, b)

    def test_volatility_strip_works_across_call_id_changes(self):
        a = _FakeReq(b'{"tool_call_id":"call_AAAAAAAAA"}')
        b = _FakeReq(b'{"tool_call_id":"call_ZZZZZZZZZ"}')
        _match_llm_body(a, b)

    def test_different_doc_ids_match_after_strip(self):
        a = _FakeReq(b"document foo (ID: 55) extra")
        b = _FakeReq(b"document foo (ID: 99) extra")
        _match_llm_body(a, b)

    def test_real_substantive_difference_still_fails(self):
        # Past the volatility strip, real prompt differences must still
        # produce a mismatch. This guards against the matcher becoming
        # too permissive by accident.
        a = _FakeReq(b'{"prompt":"What is the title?"}')
        b = _FakeReq(b'{"prompt":"Summarize the document"}')
        with self.assertRaises(AssertionError):
            _match_llm_body(a, b)


class MaybeVcrCassetteTests(TestCase):
    """Env-var routing for ``maybe_vcr_cassette``.

    Each test enters the context manager and asserts on the yielded
    value (None for the bypass paths, an actual cassette object on the
    active path).
    """

    def test_unset_mode_is_bypass(self):
        with env_vars(OC_LLM_VCR_MODE=None, OC_LLM_VCR_CASSETTE=None):
            with maybe_vcr_cassette() as ctx:
                self.assertIsNone(ctx)

    def test_empty_mode_is_bypass(self):
        with env_vars(OC_LLM_VCR_MODE="", OC_LLM_VCR_CASSETTE="/tmp/x.yaml"):
            with maybe_vcr_cassette() as ctx:
                self.assertIsNone(ctx)

    def test_off_mode_is_bypass(self):
        with env_vars(OC_LLM_VCR_MODE="off", OC_LLM_VCR_CASSETTE="/tmp/x.yaml"):
            with maybe_vcr_cassette() as ctx:
                self.assertIsNone(ctx)

    def test_none_disabled_mode_is_bypass(self):
        # We use the special-case "none-disabled" name because plain
        # "none" collides with vcr's ``record_mode='none'`` (replay).
        with env_vars(
            OC_LLM_VCR_MODE="none-disabled", OC_LLM_VCR_CASSETTE="/tmp/x.yaml"
        ):
            with maybe_vcr_cassette() as ctx:
                self.assertIsNone(ctx)

    def test_record_mode_without_cassette_path_warns_and_bypasses(self):
        with env_vars(OC_LLM_VCR_MODE="record", OC_LLM_VCR_CASSETTE=None):
            with mock.patch(
                "opencontractserver.utils.vcr_replay.logger"
            ) as mock_logger:
                with maybe_vcr_cassette() as ctx:
                    self.assertIsNone(ctx)
                self.assertTrue(mock_logger.warning.called)

    def test_unknown_mode_warns_and_bypasses(self):
        with env_vars(
            OC_LLM_VCR_MODE="oops",
            OC_LLM_VCR_CASSETTE="/tmp/x.yaml",
        ):
            with mock.patch(
                "opencontractserver.utils.vcr_replay.logger"
            ) as mock_logger:
                with maybe_vcr_cassette() as ctx:
                    self.assertIsNone(ctx)
                self.assertTrue(mock_logger.warning.called)

    def test_record_mode_yields_active_cassette(self):
        # The happy path: with both env vars set and a sensible mode,
        # we get a real cassette back. We use a tmpdir so we never
        # touch the committed fixture cassette.
        with tempfile.TemporaryDirectory() as td:
            cass_path = os.path.join(td, "test-cassette.yaml")
            with env_vars(
                OC_LLM_VCR_MODE="record",
                OC_LLM_VCR_CASSETTE=cass_path,
            ):
                with maybe_vcr_cassette() as ctx:
                    self.assertIsNotNone(ctx)
                    # Cassette objects expose .requests as a sequence.
                    self.assertTrue(hasattr(ctx, "requests"))

    def test_replay_mode_yields_active_cassette_when_file_missing(self):
        # Replay mode against a missing cassette is technically valid —
        # the cassette is empty. Any subsequent request would raise, but
        # entering the context manager should succeed.
        with tempfile.TemporaryDirectory() as td:
            cass_path = os.path.join(td, "missing.yaml")
            with env_vars(
                OC_LLM_VCR_MODE="replay",
                OC_LLM_VCR_CASSETTE=cass_path,
            ):
                with maybe_vcr_cassette() as ctx:
                    self.assertIsNotNone(ctx)


class EnsureAiohttpVcrCompatTests(TestCase):
    """Regression for issue #1920 / kevin1024/vcrpy#995.

    aiohttp 3.14 removed ``aiohttp.streams.AsyncStreamReaderMixin``, which the
    pinned vcrpy 8.1.1 aiohttp stub subclasses at module-evaluation time. vcrpy
    imports that stub lazily when a cassette is entered, so under aiohttp >= 3.14
    every VCR cassette entry raises ``AttributeError``. The compat shim restores
    the symbol so cassette entry works again.
    """

    def test_mixin_symbol_present_after_shim(self):
        try:
            from aiohttp import streams
        except ModuleNotFoundError:  # pragma: no cover - aiohttp always present
            self.skipTest("aiohttp not installed")

        had_real_symbol = hasattr(streams, "AsyncStreamReaderMixin")
        original = getattr(streams, "AsyncStreamReaderMixin", None)

        # Keep the test self-contained: restore the module to whatever state it
        # was in before this test ran (the shim may add the symbol below).
        def _restore() -> None:
            if had_real_symbol:
                setattr(streams, "AsyncStreamReaderMixin", original)
            elif hasattr(streams, "AsyncStreamReaderMixin"):
                delattr(streams, "AsyncStreamReaderMixin")

        self.addCleanup(_restore)

        ensure_aiohttp_vcr_compat()

        # Whichever aiohttp is installed, the symbol must exist afterward so
        # vcrpy's MockStream class statement can evaluate.
        self.assertTrue(hasattr(streams, "AsyncStreamReaderMixin"))
        if had_real_symbol:
            # Under aiohttp < 3.14 the real mixin must be left untouched.
            self.assertIs(getattr(streams, "AsyncStreamReaderMixin"), original)

    def test_shim_is_idempotent(self):
        # Called twice (conftest + maybe_vcr_cassette both invoke it) must not
        # raise or swap the symbol out from under a prior call.
        ensure_aiohttp_vcr_compat()
        try:
            from aiohttp import streams
        except ModuleNotFoundError:  # pragma: no cover - aiohttp always present
            self.skipTest("aiohttp not installed")
        first = getattr(streams, "AsyncStreamReaderMixin")
        ensure_aiohttp_vcr_compat()
        self.assertIs(getattr(streams, "AsyncStreamReaderMixin"), first)

    def test_vcr_cassette_entry_works(self):
        # The real contract: vcrpy imports its aiohttp stub lazily when a
        # cassette is entered (vcr/patch.py builds its patchers). Under aiohttp
        # >= 3.14 that stub subclasses the removed AsyncStreamReaderMixin and
        # raises AttributeError. With the shim applied, entering an (empty)
        # cassette must succeed. (`import vcr` alone does NOT trigger the stub,
        # which is why this enters a cassette rather than just importing.)
        ensure_aiohttp_vcr_compat()
        import vcr

        with tempfile.TemporaryDirectory() as td:
            with vcr.VCR().use_cassette(os.path.join(td, "regression.yaml")):
                pass


class LlmHostsTests(TestCase):
    """Sanity check for the host allowlist."""

    def test_openai_in_allowlist(self):
        self.assertIn("api.openai.com", _LLM_HOSTS)

    def test_anthropic_in_allowlist(self):
        self.assertIn("api.anthropic.com", _LLM_HOSTS)

    def test_localhost_not_in_allowlist(self):
        # We never want to intercept the embedder microservice or
        # internal localhost calls accidentally.
        self.assertNotIn("localhost", _LLM_HOSTS)
        self.assertNotIn("127.0.0.1", _LLM_HOSTS)
