"""
Tests for Corpus._markdown_to_plain_text and update_description sync behaviour.

Validates that:
- _markdown_to_plain_text strips common markdown syntax correctly.
- _summarize_for_preview produces short single-line previews suitable for
  card layouts and hero subtitles.
- update_description() keeps the plain-text ``description`` field in sync
  with the versioned ``md_description`` content, and the auto-maintained
  ``description_preview`` field stays in sync via ``Corpus.save()``.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.constants.truncation import (
    MAX_CORPUS_DESCRIPTION_PREVIEW_LENGTH,
)
from opencontractserver.corpuses.models import Corpus

User = get_user_model()


class MarkdownToPlainTextTest(TestCase):
    """Unit tests for Corpus._markdown_to_plain_text static method."""

    def test_strips_headings(self):
        result = Corpus._markdown_to_plain_text("# Title\n\nSome text")
        self.assertEqual(result, "Title\n\nSome text")

    def test_strips_multiple_heading_levels(self):
        md = "## H2\n### H3\n#### H4"
        result = Corpus._markdown_to_plain_text(md)
        self.assertEqual(result, "H2\nH3\nH4")

    def test_strips_bold_and_italic(self):
        result = Corpus._markdown_to_plain_text("Some **bold** and *italic* text")
        self.assertEqual(result, "Some bold and italic text")

    def test_strips_underscore_bold_italic(self):
        result = Corpus._markdown_to_plain_text("__bold__ and _italic_")
        self.assertEqual(result, "bold and italic")

    def test_strips_multiline_bold(self):
        md = "Start **bold\nacross lines** end"
        result = Corpus._markdown_to_plain_text(md)
        self.assertEqual(result, "Start bold\nacross lines end")

    def test_strips_strikethrough(self):
        result = Corpus._markdown_to_plain_text("some ~~deleted~~ text")
        self.assertEqual(result, "some deleted text")

    def test_strips_links(self):
        result = Corpus._markdown_to_plain_text("Click [here](https://example.com) now")
        self.assertEqual(result, "Click here now")

    def test_strips_images(self):
        result = Corpus._markdown_to_plain_text("![alt text](image.png)")
        self.assertEqual(result, "alt text")

    def test_strips_inline_code(self):
        result = Corpus._markdown_to_plain_text("Run `pip install` now")
        self.assertEqual(result, "Run pip install now")

    def test_strips_fenced_code_blocks(self):
        md = "Before\n```python\nprint('hello')\n```\nAfter"
        result = Corpus._markdown_to_plain_text(md)
        self.assertIn("print('hello')", result)
        self.assertNotIn("```", result)

    def test_strips_html_tags(self):
        result = Corpus._markdown_to_plain_text("Text <em>emphasis</em> here")
        self.assertEqual(result, "Text emphasis here")

    def test_strips_blockquotes(self):
        result = Corpus._markdown_to_plain_text("> quoted text")
        self.assertEqual(result, "quoted text")

    def test_strips_horizontal_rules(self):
        md = "Above\n---\nBelow"
        result = Corpus._markdown_to_plain_text(md)
        self.assertIn("Above", result)
        self.assertIn("Below", result)
        self.assertNotIn("---", result)

    def test_strips_unordered_list_markers(self):
        md = "- item one\n- item two"
        result = Corpus._markdown_to_plain_text(md)
        self.assertEqual(result, "item one\nitem two")

    def test_strips_ordered_list_markers(self):
        md = "1. first\n2. second"
        result = Corpus._markdown_to_plain_text(md)
        self.assertEqual(result, "first\nsecond")

    def test_collapses_blank_lines(self):
        md = "A\n\n\n\nB"
        result = Corpus._markdown_to_plain_text(md)
        self.assertEqual(result, "A\n\nB")

    def test_plain_text_passthrough(self):
        text = "Just plain text, no markdown."
        result = Corpus._markdown_to_plain_text(text)
        self.assertEqual(result, text)

    def test_empty_string(self):
        self.assertEqual(Corpus._markdown_to_plain_text(""), "")


class SummarizeForPreviewTest(TestCase):
    """Unit tests for Corpus._summarize_for_preview static method."""

    def test_empty_string_returns_empty(self):
        self.assertEqual(Corpus._summarize_for_preview(""), "")

    def test_short_text_passthrough(self):
        text = "A concise corpus blurb."
        self.assertEqual(Corpus._summarize_for_preview(text), text)

    def test_collapses_internal_whitespace_within_first_paragraph(self):
        text = "First line\nstill first paragraph\nbut joined."
        self.assertEqual(
            Corpus._summarize_for_preview(text),
            "First line still first paragraph but joined.",
        )

    def test_keeps_only_first_paragraph(self):
        text = "Headline blurb.\n\nA second paragraph that should be dropped."
        self.assertEqual(Corpus._summarize_for_preview(text), "Headline blurb.")

    def test_truncates_long_first_paragraph_with_ellipsis(self):
        text = "word " * 200  # ~1000 chars, well over the cap
        result = Corpus._summarize_for_preview(text)
        # Includes the ellipsis character but stays within the cap + 1.
        self.assertTrue(result.endswith("…"))
        self.assertLessEqual(len(result), MAX_CORPUS_DESCRIPTION_PREVIEW_LENGTH + 1)

    def test_truncation_respects_word_boundary(self):
        text = "supercalifragilistic " * 50
        result = Corpus._summarize_for_preview(text)
        # No mid-word slice — the trimmed text should not end with a partial
        # word followed directly by the ellipsis (i.e. should have a space
        # before the ellipsis on the previous boundary).
        body = result.rstrip("…").rstrip()
        # Either ends on a whole token, or we couldn't find a useful
        # boundary and fell back to the hard cut. Both must keep the
        # final token intact for a sensibly long word.
        self.assertTrue(
            body.endswith("supercalifragilistic"),
            f"unexpected truncation: {body!r}",
        )

    def test_exactly_at_cap_is_not_truncated(self):
        """Boundary: text exactly MAX chars long is returned verbatim."""
        text = "a" * MAX_CORPUS_DESCRIPTION_PREVIEW_LENGTH
        self.assertEqual(Corpus._summarize_for_preview(text), text)


class UpdateDescriptionSyncTest(TestCase):
    """Tests that update_description() syncs the plain-text description field."""

    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="test123")
        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            creator=self.user,
            description="old description",
        )

    def test_syncs_plain_text_on_update(self):
        md = "# New Title\n\nSome **bold** content"
        self.corpus.update_description(new_content=md, author=self.user)
        self.corpus.refresh_from_db()
        self.assertEqual(self.corpus.description, "New Title\n\nSome bold content")

    def test_syncs_preview_on_update(self):
        """After update_description, description_preview reflects the new content."""
        md = "# New Title\n\nSome **bold** content"
        self.corpus.update_description(new_content=md, author=self.user)
        self.corpus.refresh_from_db()
        # First paragraph only — second paragraph stripped from preview.
        self.assertEqual(self.corpus.description_preview, "New Title")

    def test_preview_truncates_long_descriptions(self):
        long_md = "x " * 400  # plain-text body ~800 chars
        self.corpus.update_description(new_content=long_md, author=self.user)
        self.corpus.refresh_from_db()
        self.assertTrue(self.corpus.description_preview.endswith("…"))
        self.assertLessEqual(
            len(self.corpus.description_preview),
            MAX_CORPUS_DESCRIPTION_PREVIEW_LENGTH + 1,
        )

    def test_preview_synced_on_direct_description_assignment(self):
        """Direct writes to ``description`` also refresh the preview."""
        self.corpus.description = "Direct write blurb."
        self.corpus.save()
        self.corpus.refresh_from_db()
        self.assertEqual(self.corpus.description_preview, "Direct write blurb.")

    def test_preview_included_when_update_fields_targets_description(self):
        """``save(update_fields=['description'])`` cascades to description_preview."""
        self.corpus.description = "Update fields path."
        self.corpus.save(update_fields=["description"])
        self.corpus.refresh_from_db()
        self.assertEqual(self.corpus.description_preview, "Update fields path.")

    def test_preview_not_persisted_when_update_fields_excludes_description(self):
        """``save(update_fields=['title'])`` must not persist preview changes.

        Complementary to ``test_preview_included_when_update_fields_targets_description``
        — verifies the cascade is scoped strictly to writes that include
        ``description`` in ``update_fields``.
        """
        # Persist a known preview value first.
        self.corpus.description = "Original blurb."
        self.corpus.save()
        original_preview = self.corpus.description_preview

        # Now mutate description in memory but only persist title.
        self.corpus.description = "Different blurb that must not reach DB."
        self.corpus.title = "Renamed Corpus"
        self.corpus.save(update_fields=["title"])
        self.corpus.refresh_from_db()

        # Title was updated; description (and therefore preview) was not.
        self.assertEqual(self.corpus.title, "Renamed Corpus")
        self.assertEqual(self.corpus.description, "Original blurb.")
        self.assertEqual(self.corpus.description_preview, original_preview)

    def test_creates_revision(self):
        from opencontractserver.corpuses.models import CorpusDescriptionRevision

        self.corpus.update_description(new_content="v1 content", author=self.user)
        revisions = CorpusDescriptionRevision.objects.filter(corpus=self.corpus)
        self.assertEqual(revisions.count(), 1)
        self.assertEqual(revisions.first().version, 1)

    def test_no_op_when_content_unchanged(self):
        self.corpus.update_description(new_content="initial", author=self.user)
        result = self.corpus.update_description(new_content="initial", author=self.user)
        self.assertIsNone(result)

    def test_accepts_author_as_int(self):
        self.corpus.update_description(
            new_content="from int author", author=self.user.pk
        )
        self.corpus.refresh_from_db()
        self.assertEqual(self.corpus.description, "from int author")
