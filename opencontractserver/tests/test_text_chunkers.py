"""Unit tests for the pluggable text-chunking strategies (issue #1348).

The tests deliberately avoid spaCy-backed strategies so they run fast and
stay CI-friendly; SentenceChunker continues to be exercised end-to-end by
``test_txt_ingestor_pipeline.py``.
"""

from __future__ import annotations

from unittest import TestCase

from opencontractserver.pipeline.parsers.text_chunkers import (
    PARAGRAPH_CHUNK_LABEL,
    SLIDING_WINDOW_CHUNK_LABEL,
    BaseTextChunker,
    ParagraphChunker,
    SlidingWindowChunker,
    TextChunk,
    available_chunker_names,
    get_chunker,
    register_chunker,
)


class TextChunkOffsetsMixin:
    """Shared assertions that every chunk's offsets match the source text."""

    def assert_offsets_consistent(
        self,
        chunks: list[TextChunk],
        source: str,
    ) -> None:
        for chunk in chunks:
            assert (
                0 <= chunk.start < chunk.end <= len(source)
            ), f"chunk offsets out of range: {chunk}"
            # The emitted text must exactly equal the span it claims to cover
            # so downstream highlighting and embedding line up with the
            # original document.
            assert (
                source[chunk.start : chunk.end] == chunk.text
            ), f"chunk.text does not match source span: {chunk}"


class ParagraphChunkerTests(TextChunkOffsetsMixin, TestCase):
    """Behaviour tests for :class:`ParagraphChunker`."""

    def test_splits_on_blank_lines(self) -> None:
        text = "Alpha line one.\nAlpha line two.\n\nBeta stands alone.\n\n\nGamma last."
        chunks = list(ParagraphChunker().chunk(text))
        self.assertEqual(len(chunks), 3)
        self.assertEqual(chunks[0].text, "Alpha line one.\nAlpha line two.")
        self.assertEqual(chunks[1].text, "Beta stands alone.")
        self.assertEqual(chunks[2].text, "Gamma last.")
        for chunk in chunks:
            self.assertEqual(chunk.label, PARAGRAPH_CHUNK_LABEL)
        self.assert_offsets_consistent(chunks, text)

    def test_tolerates_whitespace_only_separators(self) -> None:
        text = "Para one line one.\nPara one line two.\n   \n  \nPara two only line."
        chunks = list(ParagraphChunker().chunk(text))
        self.assertEqual(len(chunks), 2)
        self.assertIn("Para one line one.", chunks[0].text)
        self.assertEqual(chunks[1].text, "Para two only line.")
        self.assert_offsets_consistent(chunks, text)

    def test_returns_single_chunk_when_no_blank_lines(self) -> None:
        text = "One paragraph, no blank lines here at all."
        chunks = list(ParagraphChunker().chunk(text))
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].text, text)
        self.assert_offsets_consistent(chunks, text)

    def test_empty_input_emits_nothing(self) -> None:
        self.assertEqual(list(ParagraphChunker().chunk("")), [])

    def test_min_chars_filters_short_paragraphs(self) -> None:
        text = "Header\n\nA meaningful paragraph of text.\n\n**\n\nEnd."
        chunks = list(ParagraphChunker(min_chars=10).chunk(text))
        # Only the meaningful paragraph clears min_chars=10.
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].text, "A meaningful paragraph of text.")
        self.assert_offsets_consistent(chunks, text)

    def test_max_chars_splits_long_paragraph(self) -> None:
        # Single paragraph well over max_chars.
        long_para = "word " * 200  # 1000 chars (last has trailing space)
        chunks = list(ParagraphChunker(max_chars=100).chunk(long_para.strip()))
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertEqual(chunk.label, PARAGRAPH_CHUNK_LABEL)
            # Word-boundary snapping may push a chunk slightly past max_chars
            # but it should stay bounded by window_size + one word.
            self.assertLessEqual(len(chunk.text), 100 + len("word "))
        self.assert_offsets_consistent(chunks, long_para.strip())

    def test_invalid_args(self) -> None:
        with self.assertRaises(ValueError):
            ParagraphChunker(min_chars=-1)
        with self.assertRaises(ValueError):
            ParagraphChunker(max_chars=0)


class SlidingWindowChunkerTests(TextChunkOffsetsMixin, TestCase):
    """Behaviour tests for :class:`SlidingWindowChunker`."""

    def test_fixed_window_covers_text_with_overlap(self) -> None:
        # 400-character text — pick window/overlap that produce >1 chunk.
        text = "abcdefghij" * 40  # 400 chars, no whitespace
        chunker = SlidingWindowChunker(
            window_size=100, overlap=20, respect_word_boundaries=False
        )
        chunks = list(chunker.chunk(text))
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertEqual(chunk.label, SLIDING_WINDOW_CHUNK_LABEL)
        # Neighbours overlap by exactly ``overlap`` characters when
        # word-boundary snapping is disabled.
        for prev, curr in zip(chunks, chunks[1:]):
            self.assertEqual(prev.end - curr.start, 20)
        # The last chunk reaches the end of the text.
        self.assertEqual(chunks[-1].end, len(text))
        self.assert_offsets_consistent(chunks, text)

    def test_respects_word_boundaries(self) -> None:
        text = "alpha beta gamma delta epsilon zeta eta theta iota kappa"
        chunker = SlidingWindowChunker(
            window_size=15, overlap=3, respect_word_boundaries=True
        )
        chunks = list(chunker.chunk(text))
        self.assertGreater(len(chunks), 1)
        # No chunk should end in the middle of a word.
        for chunk in chunks:
            if chunk.end < len(text):
                self.assertTrue(
                    text[chunk.end].isspace(),
                    f"chunk ended mid-word: {chunk!r}",
                )
        self.assert_offsets_consistent(chunks, text)

    def test_short_text_yields_single_chunk(self) -> None:
        text = "short"
        chunks = list(SlidingWindowChunker(window_size=100, overlap=10).chunk(text))
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].text, text)
        self.assert_offsets_consistent(chunks, text)

    def test_empty_text_emits_nothing(self) -> None:
        self.assertEqual(
            list(SlidingWindowChunker(window_size=100, overlap=0).chunk("")),
            [],
        )

    def test_invalid_args(self) -> None:
        with self.assertRaises(ValueError):
            SlidingWindowChunker(window_size=0)
        with self.assertRaises(ValueError):
            SlidingWindowChunker(window_size=100, overlap=-1)
        with self.assertRaises(ValueError):
            SlidingWindowChunker(window_size=100, overlap=100)
        with self.assertRaises(ValueError):
            SlidingWindowChunker(window_size=100, overlap=200)


class ChunkerRegistryTests(TestCase):
    """Registry lookup + spec parsing."""

    def test_builtin_strategies_are_registered(self) -> None:
        names = available_chunker_names()
        self.assertIn("paragraph", names)
        self.assertIn("sliding_window", names)
        self.assertIn("sentence", names)

    def test_get_chunker_by_name_returns_default_configured_instance(self) -> None:
        chunker = get_chunker("paragraph")
        self.assertIsInstance(chunker, ParagraphChunker)

    def test_get_chunker_forwards_kwargs(self) -> None:
        chunker = get_chunker(
            {"name": "sliding_window", "window_size": 50, "overlap": 5}
        )
        assert isinstance(chunker, SlidingWindowChunker)  # narrows type for mypy
        self.assertEqual(chunker.window_size, 50)
        self.assertEqual(chunker.overlap, 5)

    def test_unknown_name_raises(self) -> None:
        with self.assertRaises(ValueError):
            get_chunker("not_a_real_strategy")

    def test_spec_missing_name_key_raises(self) -> None:
        with self.assertRaises(ValueError):
            get_chunker({"window_size": 100})

    def test_spec_wrong_type_raises(self) -> None:
        with self.assertRaises(ValueError):
            get_chunker(42)  # type: ignore[arg-type]

    def test_duplicate_registration_raises(self) -> None:
        class ReusedName(BaseTextChunker):
            name = "paragraph"  # already registered
            label = "X"

            def chunk(self, text):
                return []

        with self.assertRaises(ValueError):
            register_chunker(ReusedName)

    def test_empty_name_registration_raises(self) -> None:
        class NoName(BaseTextChunker):
            name = ""
            label = "X"

            def chunk(self, text):
                return []

        with self.assertRaises(ValueError):
            register_chunker(NoName)
