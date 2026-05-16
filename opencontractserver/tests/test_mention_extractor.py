"""Unit tests for the shared mention extractor.

Pure-parse layer: no DB, no permissions. These tests pin the
markdown link grammar documented in docs/architecture/rich_mentions.md
plus the legacy text patterns that the resolver also supports.
"""

from django.test import SimpleTestCase

from opencontractserver.llms.agents.mention_extractor import (
    ExtractedMention,
    extract_agent_mentions,
    extract_mentions,
)


class ExtractMentionsTests(SimpleTestCase):
    def test_extracts_global_agent_mention(self):
        body = "Please [@research-bot](/agents/research-bot) take a look."
        mentions = extract_mentions(body)
        self.assertEqual(len(mentions), 1)
        self.assertIsInstance(mentions[0], ExtractedMention)
        self.assertEqual(mentions[0].type, "agent")
        self.assertEqual(mentions[0].slug, "research-bot")
        self.assertEqual(mentions[0].corpus_slug, None)
        self.assertEqual(mentions[0].url, "/agents/research-bot")
        self.assertEqual(mentions[0].label, "@research-bot")

    def test_extracts_corpus_scoped_agent_mention(self):
        body = "Ask [@auditor](/c/acme-corp/agents/auditor) please."
        mentions = extract_mentions(body)
        self.assertEqual(len(mentions), 1)
        self.assertEqual(mentions[0].type, "agent")
        self.assertEqual(mentions[0].slug, "auditor")
        self.assertEqual(mentions[0].corpus_slug, "acme-corp")

    def test_extracts_corpus_scoped_agent_mention_long_form(self):
        # Long form: ``/c/{creator-slug}/{corpus-slug}/agents/{slug}`` (5 parts).
        # ``_classify_url`` derives ``corpus_slug`` from the segment immediately
        # preceding ``agents/{slug}`` regardless of how deep that segment sits,
        # so the longer creator-prefixed URL also resolves correctly.
        body = "Ask [@audit-bot](/c/jdoe/acme-corp/agents/audit-bot) please."
        mentions = extract_mentions(body)
        self.assertEqual(len(mentions), 1)
        self.assertEqual(mentions[0].type, "agent")
        self.assertEqual(mentions[0].slug, "audit-bot")
        self.assertEqual(mentions[0].corpus_slug, "acme-corp")

    def test_corpus_agent_url_pattern_is_pinned_to_4_or_5_parts(self):
        # A path with an extra trailing segment past ``agents/{slug}`` must
        # NOT be classified as a corpus-scoped agent mention.  Without the
        # explicit length pin the previous ``len(parts) >= 4`` heuristic
        # would have matched and produced a wrong (corpus_slug, slug)
        # pair from ``parts[-3:]``.
        body = "garbled [link](/c/x/agents/foo/agents/bar) here."
        mentions = extract_mentions(body)
        # Either silently dropped or classified as something else — but
        # never as a corpus-scoped agent mention with the wrong fields.
        agent_mentions = [m for m in mentions if m.type == "agent"]
        self.assertEqual(agent_mentions, [])

    def test_extracts_corpus_mention(self):
        body = "See [Acme corpus](/c/jdoe/acme-corp) for context."
        mentions = extract_mentions(body)
        self.assertEqual(len(mentions), 1)
        self.assertEqual(mentions[0].type, "corpus")
        self.assertEqual(mentions[0].slug, "acme-corp")

    def test_extracts_document_in_corpus_mention(self):
        body = "Read [Spec doc](/d/jdoe/acme-corp/spec-doc) closely."
        mentions = extract_mentions(body)
        self.assertEqual(len(mentions), 1)
        self.assertEqual(mentions[0].type, "document")
        self.assertEqual(mentions[0].slug, "spec-doc")
        self.assertEqual(mentions[0].corpus_slug, "acme-corp")

    def test_extracts_standalone_document_mention(self):
        body = "Read [Spec doc](/d/jdoe/spec-doc) closely."
        mentions = extract_mentions(body)
        self.assertEqual(len(mentions), 1)
        self.assertEqual(mentions[0].type, "document")
        self.assertEqual(mentions[0].slug, "spec-doc")
        self.assertEqual(mentions[0].corpus_slug, None)

    def test_extracts_annotation_mention_plain_id(self):
        body = "See [paragraph 3](/d/jdoe/acme-corp/spec-doc?ann=42) here."
        mentions = extract_mentions(body)
        self.assertEqual(len(mentions), 1)
        self.assertEqual(mentions[0].type, "annotation")
        self.assertEqual(mentions[0].id, 42)

    def test_extracts_annotation_mention_relay_id(self):
        # base64("AnnotationType:7") == "QW5ub3RhdGlvblR5cGU6Nw=="
        body = "See [paragraph 3](/d/jdoe/acme-corp/spec-doc?ann=QW5ub3RhdGlvblR5cGU6Nw==) here."
        mentions = extract_mentions(body)
        self.assertEqual(len(mentions), 1)
        self.assertEqual(mentions[0].type, "annotation")
        self.assertEqual(mentions[0].id, 7)

    def test_extracts_user_mention(self):
        body = "ping [@alice](/users/alice)"
        mentions = extract_mentions(body)
        self.assertEqual(len(mentions), 1)
        self.assertEqual(mentions[0].type, "user")
        self.assertEqual(mentions[0].slug, "alice")

    def test_extracts_multiple_mentions_in_order(self):
        body = (
            "First [@bob](/users/bob) then [@research-bot](/agents/research-bot) "
            "and finally [Acme](/c/jdoe/acme-corp)."
        )
        mentions = extract_mentions(body)
        self.assertEqual([m.type for m in mentions], ["user", "agent", "corpus"])

    def test_deduplicates_identical_urls(self):
        body = (
            "ping [@research-bot](/agents/research-bot) "
            "again [@research-bot](/agents/research-bot)"
        )
        mentions = extract_mentions(body)
        self.assertEqual(len(mentions), 1)

    def test_ignores_non_mention_links(self):
        body = "see [Google](https://google.com) for more"
        self.assertEqual(extract_mentions(body), [])

    def test_extract_agent_mentions_filters_to_agents_only(self):
        body = "[Acme](/c/jdoe/acme-corp) and [@research-bot](/agents/research-bot)"
        mentions = extract_agent_mentions(body)
        self.assertEqual([m.type for m in mentions], ["agent"])

    def test_extracts_legacy_text_pattern_corpus(self):
        body = "Look at @corpus:acme-corp for context"
        mentions = extract_mentions(body)
        self.assertEqual(len(mentions), 1)
        self.assertEqual(mentions[0].type, "corpus")
        self.assertEqual(mentions[0].slug, "acme-corp")

    def test_legacy_combined_corpus_document_does_not_double_emit_corpus(self):
        body = "Look at @corpus:acme-corp/document:spec-doc here."
        mentions = extract_mentions(body)
        self.assertEqual(len(mentions), 1)
        self.assertEqual(mentions[0].type, "document")
        self.assertEqual(mentions[0].slug, "spec-doc")
        self.assertEqual(mentions[0].corpus_slug, "acme-corp")

    def test_annotation_url_with_garbage_ann_falls_back_to_document(self):
        body = "[oops](/d/jdoe/acme-corp/spec-doc?ann=garbage)"
        mentions = extract_mentions(body)
        self.assertEqual(len(mentions), 1)
        # Falls through to doc-in-corpus branch (annotation classifier returns None)
        self.assertEqual(mentions[0].type, "document")
        self.assertEqual(mentions[0].slug, "spec-doc")
        self.assertEqual(mentions[0].corpus_slug, "acme-corp")

    def test_unknown_path_shape_is_ignored(self):
        body = "[strange](/foo/bar/baz/qux/quux)"
        self.assertEqual(extract_mentions(body), [])

    def test_too_few_path_segments_ignored(self):
        body = "[short](/d/only)"
        self.assertEqual(extract_mentions(body), [])

    def test_empty_body_returns_empty_list(self):
        self.assertEqual(extract_mentions(""), [])
        self.assertEqual(extract_mentions(None), [])
