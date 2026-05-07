"""
Coverage tests for the typing-graduated ``pii_highlighter_claude`` task.

The PR #1482 typing fix renamed ``claude_response`` -> ``claude_blocks`` and
added a ``hasattr(resp, "text")`` filter so non-text content blocks (e.g.
``ToolUseBlock``) are skipped before the join.  These tests exercise the new
filter directly via the inner function (bypassing the celery decorator) so
we don't have to stand up a Document + Analysis fixture just to assert the
post-Anthropic response handling.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings


def _get_inner_pii_function():
    """Return the underlying ``pii_highlighter_claude`` function.

    The celery ``shared_task`` decorator + ``functools.wraps`` chain stores
    the original wrapper under ``.run``; the doc_analyzer_task decorator's
    ``wrapper`` is what we need.  We call it directly with kwargs to avoid
    the wrapper's Document/Analysis lookups (which require DB fixtures).
    """
    from opencontractserver.tasks import doc_analysis_tasks  # noqa: F401

    # Re-import the module-level inner fn through the decorator's closure.
    # The decorator returns the celery Task whose ``.run`` is the wrapper,
    # whose ``__wrapped__`` is the original ``pii_highlighter_claude``.
    # mypy can't narrow ``shared_task`` -> ``run`` so suppress at the lookup.
    task = doc_analysis_tasks.pii_highlighter_claude
    wrapper = task.run  # type: ignore[attr-defined]
    inner = wrapper.__wrapped__
    return inner


class PiiHighlighterClaudeBlocksFilterTestCase(TestCase):
    """Verify the ``hasattr(resp, "text")`` block filter works correctly."""

    @override_settings(
        ANALYZER_KWARGS={
            "opencontractserver.tasks.doc_analysis_tasks.pii_highlighter_claude": {
                "ANTHROPIC_API_KEY": "test-key"
            }
        }
    )
    def test_filters_out_blocks_without_text_attribute(self):
        """ToolUseBlock-like blocks (no ``.text``) must be filtered out."""
        inner = _get_inner_pii_function()

        # Build a fake Anthropic response: one TextBlock-like + one
        # ToolUseBlock-like (no ``.text``).  The filter must keep only the
        # text block.
        text_block = SimpleNamespace(text="John Doe signed on 2024-01-01")
        tool_use_block = SimpleNamespace(
            id="tu_1",
            name="some_tool",
            input={"foo": "bar"},
        )
        # Sanity: tool_use_block has no .text attribute
        self.assertFalse(hasattr(tool_use_block, "text"))

        fake_response = SimpleNamespace(content=[text_block, tool_use_block])
        fake_client = MagicMock()
        fake_client.messages.create.return_value = fake_response

        with patch("anthropic.Anthropic", return_value=fake_client):
            doc_labels, span_pairs, metadata, success = inner(
                pdf_text_extract="John Doe signed on 2024-01-01 for $5000.",
                pdf_pawls_extract=None,
            )

        # The text block content joined into a string should locate the
        # snippet in the source text and produce one span pair.
        self.assertTrue(success)
        self.assertEqual(doc_labels, [])
        # The tool-use block was silently dropped — only the text-block line
        # was searchable, so we expect a single (TextSpan, "REDACTED") pair.
        self.assertEqual(len(span_pairs), 1)
        span, label = span_pairs[0]
        self.assertEqual(label, "REDACTED")
        self.assertIn("start", span)
        self.assertIn("end", span)

    @override_settings(
        ANALYZER_KWARGS={
            "opencontractserver.tasks.doc_analysis_tasks.pii_highlighter_claude": {
                "ANTHROPIC_API_KEY": "test-key"
            }
        }
    )
    def test_only_tool_use_blocks_yields_empty_response(self):
        """If every block lacks ``.text`` the join produces empty string and
        the task short-circuits with the empty-response error path."""
        inner = _get_inner_pii_function()

        tool_only = SimpleNamespace(id="tu", name="t", input={})
        fake_response = SimpleNamespace(content=[tool_only])
        fake_client = MagicMock()
        fake_client.messages.create.return_value = fake_response

        with patch("anthropic.Anthropic", return_value=fake_client):
            doc_labels, span_pairs, metadata, success = inner(
                pdf_text_extract="some pdf text",
                pdf_pawls_extract=None,
            )

        self.assertFalse(success)
        self.assertEqual(doc_labels, [])
        self.assertEqual(span_pairs, [])
        # Metadata should report the empty-response error.
        self.assertEqual(len(metadata), 1)
        self.assertIn("error", metadata[0]["data"])
        self.assertIn("Empty response", metadata[0]["data"]["error"])

    @override_settings(
        ANALYZER_KWARGS={
            "opencontractserver.tasks.doc_analysis_tasks.pii_highlighter_claude": {
                "ANTHROPIC_API_KEY": "test-key"
            }
        }
    )
    def test_multiple_text_blocks_joined_with_newlines(self):
        """Multiple text blocks must be joined with ``\\n`` for the splitlines step."""
        inner = _get_inner_pii_function()

        block_a = SimpleNamespace(text="Alice Smith")
        block_b = SimpleNamespace(text="Bob Jones")
        fake_response = SimpleNamespace(content=[block_a, block_b])
        fake_client = MagicMock()
        fake_client.messages.create.return_value = fake_response

        # The source text contains both names so each becomes a span pair.
        source_text = "Alice Smith and Bob Jones met today."

        with patch("anthropic.Anthropic", return_value=fake_client):
            _, span_pairs, _, success = inner(
                pdf_text_extract=source_text,
                pdf_pawls_extract=None,
            )

        self.assertTrue(success)
        self.assertEqual(len(span_pairs), 2)
        labels = {label for _, label in span_pairs}
        self.assertEqual(labels, {"REDACTED"})

    @override_settings(
        ANALYZER_KWARGS={
            "opencontractserver.tasks.doc_analysis_tasks.pii_highlighter_claude": {
                "ANTHROPIC_API_KEY": "test-key"
            }
        }
    )
    def test_none_content_treated_as_empty_blocks(self):
        """When ``response.content`` is None the ``or []`` fallback applies."""
        inner = _get_inner_pii_function()

        fake_response = SimpleNamespace(content=None)
        fake_client = MagicMock()
        fake_client.messages.create.return_value = fake_response

        with patch("anthropic.Anthropic", return_value=fake_client):
            _, span_pairs, metadata, success = inner(
                pdf_text_extract="some text",
                pdf_pawls_extract=None,
            )

        self.assertFalse(success)
        self.assertEqual(span_pairs, [])
        self.assertIn("Empty response", metadata[0]["data"]["error"])

    def test_no_text_extract_returns_error(self):
        """Empty pdf_text_extract short-circuits before calling Anthropic."""
        inner = _get_inner_pii_function()

        doc_labels, span_pairs, metadata, success = inner(
            pdf_text_extract=None,
            pdf_pawls_extract=None,
        )
        self.assertFalse(success)
        self.assertEqual(span_pairs, [])
        self.assertIn("No PDF text supplied", metadata[0]["data"]["error"])

    @override_settings(ANALYZER_KWARGS={})
    def test_no_anthropic_api_key_returns_error(self):
        """Missing API key is reported via the error metadata channel.

        Pre-clear ``ANTHROPIC_API_KEY`` so the env-var fallback can't
        unexpectedly satisfy the check during a developer's local run.
        """
        import os

        inner = _get_inner_pii_function()

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            doc_labels, span_pairs, metadata, success = inner(
                pdf_text_extract="hello world",
                pdf_pawls_extract=None,
            )

        self.assertFalse(success)
        self.assertEqual(span_pairs, [])
        self.assertIn("Anthropic API key not found", metadata[0]["data"]["error"])
