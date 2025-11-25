"""
Tests for mention parsing utility.

Tests the HTML parsing and resource linking functionality for @ mentions
in discussion threads.

Part of Issue #623 - @ Mentions Feature (Extended)
"""

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.annotations.models import Annotation
from opencontractserver.conversations.models import ChatMessage, Conversation
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.utils.mention_parser import (
    extract_mentioned_user_ids,
    link_message_to_resources,
    parse_mentions_from_content,
)

User = get_user_model()


class MentionParserTestCase(TestCase):
    """Test mention parsing from HTML content."""

    def test_parse_empty_content(self):
        """Empty content should return empty sets."""
        result = parse_mentions_from_content("")
        self.assertEqual(result["documents"], set())
        self.assertEqual(result["annotations"], set())
        self.assertEqual(result["users"], set())
        self.assertEqual(result["corpuses"], set())

    def test_parse_content_without_mentions(self):
        """Content without mentions should return empty sets."""
        html = "<p>This is a regular message without mentions.</p>"
        result = parse_mentions_from_content(html)
        self.assertEqual(result["documents"], set())
        self.assertEqual(result["annotations"], set())
        self.assertEqual(result["users"], set())
        self.assertEqual(result["corpuses"], set())

    def test_parse_document_mention(self):
        """Should extract document mention from link."""
        markdown = """
        Check out this
        [@document:doc-slug](/d/user/doc-slug)
        """
        result = parse_mentions_from_content(markdown)
        self.assertEqual(result["documents"], {"doc-slug"})
        self.assertEqual(result["annotations"], set())
        self.assertEqual(result["users"], set())

    def test_parse_annotation_mention(self):
        """Should extract annotation mention from link."""
        markdown = """
        See annotation
        [@annotation:456](/d/user/doc?ann=456&structural=true)
        """
        result = parse_mentions_from_content(markdown)
        self.assertEqual(result["documents"], set())
        self.assertEqual(result["annotations"], {"456"})
        self.assertEqual(result["users"], set())

    def test_parse_user_mention(self):
        """Should extract user mention from markdown link."""
        markdown = """
        Hey
        [@john](/users/john-doe)
        """
        result = parse_mentions_from_content(markdown)
        self.assertEqual(result["documents"], set())
        self.assertEqual(result["annotations"], set())
        self.assertEqual(result["users"], {"john-doe"})

    def test_parse_corpus_mention(self):
        """Should extract corpus mention from link."""
        markdown = """
        Check
        [@corpus:my-corpus](/c/user/my-corpus)
        """
        result = parse_mentions_from_content(markdown)
        self.assertEqual(result["corpuses"], {"my-corpus"})
        self.assertEqual(result["documents"], set())
        self.assertEqual(result["annotations"], set())
        self.assertEqual(result["users"], set())

    def test_parse_multiple_mentions(self):
        """Should extract all mention types from mixed content."""
        markdown = """
        Hey
        [@john](/users/john-doe),
        check out
        [@document:doc](/d/user/doc)
        and especially
        [@annotation:3](/d/user/doc?ann=3)
        in
        [@corpus:corpus](/c/user/corpus)
        """
        result = parse_mentions_from_content(markdown)
        self.assertEqual(result["users"], {"john-doe"})
        self.assertEqual(result["documents"], {"doc"})
        self.assertEqual(result["annotations"], {"3"})
        self.assertEqual(result["corpuses"], {"corpus"})

    def test_parse_duplicate_mentions(self):
        """Should deduplicate multiple mentions of same resource."""
        markdown = """
        [@doc](/d/user/doc-slug)
        some text
        [@doc](/d/user/doc-slug)
        """
        result = parse_mentions_from_content(markdown)
        self.assertEqual(result["documents"], {"doc-slug"})  # Only one slug

    def test_parse_mention_with_incomplete_path(self):
        """Should skip mentions with incomplete URL paths."""
        markdown = """
        [@document:no-slug](/d/user)
        """
        result = parse_mentions_from_content(markdown)
        # Path has only 3 parts (/d/user), needs at least 4 for standalone doc
        self.assertEqual(result["documents"], set())  # Skipped

    def test_parse_mention_with_unknown_path_pattern(self):
        """Should ignore links that don't match known patterns."""
        markdown = """
        [@unknown](/unknown/path/here)
        """
        # Should not raise exception
        result = parse_mentions_from_content(markdown)
        # Unknown pattern not added to any set
        self.assertEqual(result["documents"], set())
        self.assertEqual(result["annotations"], set())
        self.assertEqual(result["users"], set())
        self.assertEqual(result["corpuses"], set())

    def test_extract_mentioned_user_ids_convenience(self):
        """Should extract only user slugs for notifications."""
        markdown = """
        [@alice](/users/alice-smith)
        [@bob](/users/bob-jones)
        [@doc](/d/user/doc-slug)
        """
        user_slugs = extract_mentioned_user_ids(markdown)
        self.assertEqual(user_slugs, {"alice-smith", "bob-jones"})  # Only users


@pytest.mark.django_db
class MentionLinkingTestCase(TestCase):
    """Test linking mentions to ChatMessage instances."""

    def setUp(self):
        """Create test data."""
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            creator=self.user,
        )
        self.conversation = Conversation.objects.create(
            title="Test Thread",
            conversation_type="thread",
            chat_with_corpus=self.corpus,
            creator=self.user,
        )
        # Create document without adding to corpus to avoid signal issues in tests
        self.document = Document.objects.create(
            title="Test Document",
            creator=self.user,
            description="Test doc",
            slug="test-document-slug",
        )

        # Create annotation (requires document with PDF file)
        # For simplicity, we'll create without PDF and handle DoesNotExist
        self.annotation = Annotation.objects.create(
            annotation_label=None,  # Simplified for test
            document=self.document,
            corpus=self.corpus,
            creator=self.user,
            raw_text="Test annotation text",
            page=1,
        )

    def test_link_no_mentions(self):
        """Should handle message with no mentions gracefully."""
        message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="HUMAN",
            content="<p>Regular message</p>",
            creator=self.user,
        )

        mentioned_ids = {"documents": set(), "annotations": set(), "users": set()}
        result = link_message_to_resources(message, mentioned_ids)

        self.assertEqual(result["documents_linked"], 0)
        self.assertEqual(result["annotations_linked"], 0)
        self.assertIsNone(message.source_document)
        self.assertEqual(message.source_annotations.count(), 0)

    def test_link_single_document(self):
        """Should link first mentioned document as source_document."""
        message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="HUMAN",
            content="<p>Test message</p>",
            creator=self.user,
        )

        mentioned_ids = {
            "documents": {self.document.slug},
            "annotations": set(),
            "users": set(),
        }
        result = link_message_to_resources(message, mentioned_ids)

        message.refresh_from_db()
        self.assertEqual(result["documents_linked"], 1)
        self.assertEqual(message.source_document, self.document)

    def test_link_multiple_documents_takes_first(self):
        """Should link only first document when multiple mentioned."""
        doc2 = Document.objects.create(
            title="Second Document",
            creator=self.user,
            description="Test",
            slug="second-document-slug",
        )

        message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="HUMAN",
            content="<p>Test message</p>",
            creator=self.user,
        )

        mentioned_ids = {
            "documents": {self.document.slug, doc2.slug},
            "annotations": set(),
            "users": set(),
        }
        result = link_message_to_resources(message, mentioned_ids)

        message.refresh_from_db()
        self.assertEqual(result["documents_linked"], 1)
        # Should link to first one in set (order may vary but should be one of them)
        self.assertIn(message.source_document, [self.document, doc2])

    def test_link_single_annotation(self):
        """Should link annotation via ManyToMany."""
        message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="HUMAN",
            content="<p>Test message</p>",
            creator=self.user,
        )

        mentioned_ids = {
            "documents": set(),
            "annotations": {str(self.annotation.pk)},
            "users": set(),
        }
        result = link_message_to_resources(message, mentioned_ids)

        self.assertEqual(result["annotations_linked"], 1)
        self.assertEqual(message.source_annotations.count(), 1)
        self.assertIn(self.annotation, message.source_annotations.all())

    def test_link_multiple_annotations(self):
        """Should link all mentioned annotations via ManyToMany."""
        ann2 = Annotation.objects.create(
            annotation_label=None,
            document=self.document,
            corpus=self.corpus,
            creator=self.user,
            raw_text="Second annotation",
            page=2,
        )

        message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="HUMAN",
            content="<p>Test message</p>",
            creator=self.user,
        )

        mentioned_ids = {
            "documents": set(),
            "annotations": {str(self.annotation.pk), str(ann2.pk)},
            "users": set(),
        }
        result = link_message_to_resources(message, mentioned_ids)

        self.assertEqual(result["annotations_linked"], 2)
        self.assertEqual(message.source_annotations.count(), 2)
        self.assertIn(self.annotation, message.source_annotations.all())
        self.assertIn(ann2, message.source_annotations.all())

    def test_link_nonexistent_document(self):
        """Should handle gracefully when document doesn't exist."""
        message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="HUMAN",
            content="<p>Test message</p>",
            creator=self.user,
        )

        mentioned_ids = {
            "documents": {"nonexistent-document-slug"},  # Non-existent slug
            "annotations": set(),
            "users": set(),
        }
        result = link_message_to_resources(message, mentioned_ids)

        message.refresh_from_db()
        self.assertEqual(result["documents_linked"], 0)
        self.assertIsNone(message.source_document)

    def test_link_nonexistent_annotations(self):
        """Should handle gracefully when annotations don't exist."""
        message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="HUMAN",
            content="<p>Test message</p>",
            creator=self.user,
        )

        mentioned_ids = {
            "documents": set(),
            "annotations": {"99999", "88888"},  # Non-existent IDs
            "users": set(),
        }
        result = link_message_to_resources(message, mentioned_ids)

        self.assertEqual(result["annotations_linked"], 0)
        self.assertEqual(message.source_annotations.count(), 0)

    def test_link_mixed_resources(self):
        """Should link both documents and annotations together."""
        message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="HUMAN",
            content="<p>Test message</p>",
            creator=self.user,
        )

        mentioned_ids = {
            "documents": {self.document.slug},
            "annotations": {str(self.annotation.pk)},
            "users": set(),
        }
        result = link_message_to_resources(message, mentioned_ids)

        message.refresh_from_db()
        self.assertEqual(result["documents_linked"], 1)
        self.assertEqual(result["annotations_linked"], 1)
        self.assertEqual(message.source_document, self.document)
        self.assertIn(self.annotation, message.source_annotations.all())

    def test_link_counts_users_and_corpuses(self):
        """Should count (but not link) users and corpuses."""
        message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="HUMAN",
            content="<p>Test message</p>",
            creator=self.user,
        )

        mentioned_ids = {
            "documents": set(),
            "annotations": set(),
            "users": {"1", "2", "3"},
            "corpuses": {"101", "102"},
        }
        result = link_message_to_resources(message, mentioned_ids)

        self.assertEqual(result["users_mentioned"], 3)
        self.assertEqual(result["corpuses_mentioned"], 2)
        # No actual linking for these types yet
        self.assertEqual(result["documents_linked"], 0)
        self.assertEqual(result["annotations_linked"], 0)

    def test_link_handles_invalid_document_slug_gracefully(self):
        """Should handle invalid document slug without crashing."""
        message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="HUMAN",
            content="<p>Test message</p>",
            creator=self.user,
        )

        # Use a slug that doesn't exist
        mentioned_ids = {
            "documents": {"nonexistent-slug-12345"},
            "annotations": set(),
            "users": set(),
        }
        result = link_message_to_resources(message, mentioned_ids)

        message.refresh_from_db()
        self.assertEqual(result["documents_linked"], 0)
        self.assertIsNone(message.source_document)

    def test_link_handles_annotation_errors_gracefully(self):
        """Should handle annotation linking errors without crashing."""
        message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="HUMAN",
            content="<p>Test message</p>",
            creator=self.user,
        )

        # Mix of valid and invalid annotation IDs
        mentioned_ids = {
            "documents": set(),
            "annotations": {str(self.annotation.pk), "99999", "88888"},
            "users": set(),
        }
        result = link_message_to_resources(message, mentioned_ids)

        # Should link the valid one
        self.assertEqual(result["annotations_linked"], 1)
        self.assertIn(self.annotation, message.source_annotations.all())
