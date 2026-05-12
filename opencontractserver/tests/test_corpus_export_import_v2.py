"""
Comprehensive tests for V2 corpus export/import functionality.

Tests cover:
- Individual export utilities for V2 components
- Individual import utilities for V2 components
- Full V2 round-trip export/import
- V1 backward compatibility
- Edge cases and data integrity
"""

import io
import json
import pathlib
import zipfile
from datetime import datetime
from datetime import timezone as tz
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db.models import Q
from django.test import TransactionTestCase
from django.utils import timezone

from opencontractserver.annotations.compact_json import compact_annotation_json
from opencontractserver.annotations.models import (
    DOC_TYPE_LABEL,
    RELATIONSHIP_LABEL,
    SPAN_LABEL,
    TOKEN_LABEL,
    Annotation,
    AnnotationLabel,
    LabelSet,
    Relationship,
    StructuralAnnotationSet,
)
from opencontractserver.conversations.models import (
    ChatMessage,
    Conversation,
    MessageVote,
)
from opencontractserver.corpuses.models import (
    Corpus,
    CorpusDescriptionRevision,
    CorpusFolder,
    TemporaryFileHandle,
)
from opencontractserver.documents.models import Document, DocumentPath, IngestionSource
from opencontractserver.tasks.export_tasks_v2 import package_corpus_export_v2
from opencontractserver.tasks.import_tasks_v2 import (
    _import_v2_relationships,
    import_corpus_v2,
)
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.users.models import UserExport
from opencontractserver.utils.etl import build_label_lookups
from opencontractserver.utils.export_v2 import (
    package_agent_config,
    package_conversations,
    package_corpus_folders,
    package_document_paths,
    package_md_description_revisions,
    package_structural_annotation_set,
)
from opencontractserver.utils.import_v2 import (
    import_agent_config,
    import_conversations,
    import_corpus_folders,
    import_md_description_revisions,
    import_structural_annotation_set,
)
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()

pytestmark = pytest.mark.django_db


class TestV2ExportUtilities(TransactionTestCase):
    """Test individual V2 export utility functions."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")

        # Create label set
        self.labelset = LabelSet.objects.create(
            title="Test LabelSet", creator=self.user
        )

        # Create labels
        self.text_label = AnnotationLabel.objects.create(
            text="Test Label",
            description="Test label description",
            label_type=TOKEN_LABEL,
            creator=self.user,
        )
        self.doc_label = AnnotationLabel.objects.create(
            text="Doc Label",
            label_type=DOC_TYPE_LABEL,
            creator=self.user,
        )
        self.rel_label = AnnotationLabel.objects.create(
            text="Rel Label",
            label_type=RELATIONSHIP_LABEL,
            creator=self.user,
        )
        self.labelset.annotation_labels.add(
            self.text_label, self.doc_label, self.rel_label
        )

        # Create corpus
        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            description="Test Description",
            label_set=self.labelset,
            creator=self.user,
            corpus_agent_instructions="Test corpus instructions",
            document_agent_instructions="Test document instructions",
            allow_comments=True,
        )
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.ALL])

    def test_package_structural_annotation_set(self):
        """Test exporting a structural annotation set."""
        # Create structural annotation set
        pawls_content = [
            {"page": {"index": 0, "width": 600, "height": 800}, "tokens": []}
        ]
        txt_content = "Test document content"

        struct_set = StructuralAnnotationSet.objects.create(
            content_hash="test_hash_123",
            parser_name="docling",
            parser_version="1.0",
            page_count=1,
            token_count=10,
            pawls_parse_file=ContentFile(
                json.dumps(pawls_content).encode(), name="pawls.json"
            ),
            txt_extract_file=ContentFile(txt_content.encode(), name="text.txt"),
            creator=self.user,
        )

        # Create structural annotations
        Annotation.objects.create(
            structural_set=struct_set,
            annotation_label=self.text_label,
            raw_text="Test annotation",
            page=0,
            json={"0": {"bounds": {}, "tokensJsons": [], "rawText": "Test"}},
            structural=True,
            creator=self.user,
        )

        # Export
        result = package_structural_annotation_set(struct_set)

        # Verify
        self.assertIsNotNone(result)
        self.assertEqual(result["content_hash"], "test_hash_123")
        self.assertEqual(result["parser_name"], "docling")
        self.assertEqual(result["page_count"], 1)
        self.assertEqual(len(result["structural_annotations"]), 1)
        self.assertEqual(result["txt_content"], txt_content)

    def test_package_corpus_folders(self):
        """Test exporting corpus folder hierarchy."""
        # Create folder hierarchy
        root_folder = CorpusFolder.objects.create(
            corpus=self.corpus,
            name="Root Folder",
            description="Root description",
            creator=self.user,
        )

        CorpusFolder.objects.create(
            corpus=self.corpus,
            name="Child Folder",
            parent=root_folder,
            creator=self.user,
        )

        # Export
        result = package_corpus_folders(self.corpus)

        # Verify
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["name"], "Root Folder")
        self.assertIsNone(result[0]["parent_id"])
        self.assertEqual(result[1]["name"], "Child Folder")
        self.assertIsNotNone(result[1]["parent_id"])

    def test_package_document_paths(self):
        """Test exporting DocumentPath version trees."""
        # Create document
        doc = Document.objects.create(
            title="Test Doc",
            pdf_file_hash="doc_hash_123",
            creator=self.user,
            page_count=1,
        )

        # Create document paths with version history
        path1 = DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            path="/documents/test.pdf",
            version_number=1,
            is_current=False,
            creator=self.user,
        )

        DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            path="/documents/test.pdf",
            version_number=2,
            parent=path1,
            is_current=True,
            creator=self.user,
        )

        # Export
        result = package_document_paths(self.corpus)

        # Verify
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["version_number"], 1)
        self.assertIsNone(result[0]["parent_version_number"])
        self.assertEqual(result[1]["version_number"], 2)
        self.assertEqual(result[1]["parent_version_number"], 1)

    def test_package_agent_config(self):
        """Test exporting agent configuration."""
        result = package_agent_config(self.corpus)

        self.assertEqual(
            result["corpus_agent_instructions"], "Test corpus instructions"
        )
        self.assertEqual(
            result["document_agent_instructions"], "Test document instructions"
        )

    def test_package_md_description_revisions(self):
        """Test exporting markdown description and revisions."""
        # Set markdown description
        md_content = "# Test Corpus\n\nThis is a test."
        self.corpus.md_description.save(
            "description.md", ContentFile(md_content.encode())
        )

        # Create revisions
        CorpusDescriptionRevision.objects.create(
            corpus=self.corpus,
            author=self.user,
            version=1,
            diff="Initial version",
            snapshot=md_content,
            checksum_base="",
            checksum_full="abc123",
        )

        # Export
        current_md, revisions = package_md_description_revisions(self.corpus)

        # Verify
        self.assertEqual(current_md, md_content)
        self.assertEqual(len(revisions), 1)
        self.assertEqual(revisions[0]["version"], 1)

    def test_package_conversations(self):
        """Test exporting conversations and messages."""
        # Create conversation
        conv = Conversation.objects.create(
            chat_with_corpus=self.corpus,
            title="Test Thread",
            conversation_type="thread",
            creator=self.user,
        )

        # Create message
        msg = ChatMessage.objects.create(
            conversation=conv,
            content="Test message",
            msg_type="HUMAN",
            creator=self.user,
        )

        # Create vote
        MessageVote.objects.create(message=msg, vote_type="upvote", creator=self.user)

        # Export
        conversations, messages, votes = package_conversations(self.corpus)

        # Verify
        self.assertEqual(len(conversations), 1)
        self.assertEqual(conversations[0]["title"], "Test Thread")
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["content"], "Test message")
        self.assertEqual(len(votes), 1)
        self.assertEqual(votes[0]["vote_type"], "upvote")


class TestV2ImportUtilities(TransactionTestCase):
    """Test individual V2 import utility functions."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")

        # Create label set
        self.labelset = LabelSet.objects.create(
            title="Test LabelSet", creator=self.user
        )

        # Create labels
        self.text_label = AnnotationLabel.objects.create(
            text="Test Label",
            description="Test label description",
            label_type=TOKEN_LABEL,
            creator=self.user,
        )
        self.labelset.annotation_labels.add(self.text_label)

        # Create corpus
        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            label_set=self.labelset,
            creator=self.user,
        )

    def test_import_structural_annotation_set(self):
        """Test importing a structural annotation set."""
        struct_data = {
            "content_hash": "import_hash_123",
            "parser_name": "docling",
            "parser_version": "1.0",
            "page_count": 1,
            "token_count": 10,
            "pawls_file_content": [
                {"page": {"index": 0, "width": 600, "height": 800}, "tokens": []}
            ],
            "txt_content": "Test content",
            "structural_annotations": [
                {
                    "id": "1",
                    "annotationLabel": "Test Label",
                    "rawText": "Test",
                    "page": 0,
                    "annotation_json": {},
                    "parent_id": None,
                    "annotation_type": "header",
                    "structural": True,
                }
            ],
            "structural_relationships": [],
        }

        label_lookup = {("Test Label", TOKEN_LABEL): self.text_label}

        # Import
        result = import_structural_annotation_set(struct_data, label_lookup, self.user)

        # Verify
        self.assertIsNotNone(result)
        self.assertEqual(result.content_hash, "import_hash_123")
        self.assertEqual(result.structural_annotations.count(), 1)

        # Test deduplication - importing same hash should return existing
        result2 = import_structural_annotation_set(struct_data, label_lookup, self.user)
        self.assertEqual(result.id, result2.id)

    def test_import_corpus_folders(self):
        """Test importing corpus folder hierarchy."""
        folders_data = [
            {
                "id": "folder_1",
                "name": "Root",
                "description": "",
                "color": "#05313d",
                "icon": "folder",
                "tags": [],
                "is_public": False,
                "parent_id": None,
                "path": "Root",
            },
            {
                "id": "folder_2",
                "name": "Child",
                "description": "",
                "color": "#05313d",
                "icon": "folder",
                "tags": ["test"],
                "is_public": False,
                "parent_id": "folder_1",
                "path": "Root/Child",
            },
        ]

        # Import
        result = import_corpus_folders(folders_data, self.corpus, self.user)

        # Verify
        self.assertEqual(len(result), 2)
        self.assertIn("folder_1", result)
        self.assertIn("folder_2", result)

        child = result["folder_2"]
        self.assertEqual(child.name, "Child")
        self.assertEqual(child.parent, result["folder_1"])
        self.assertEqual(child.tags, ["test"])

    def test_import_agent_config(self):
        """Test importing agent configuration."""
        config_data = {
            "corpus_agent_instructions": "Imported corpus instructions",
            "document_agent_instructions": "Imported document instructions",
        }

        # Import
        import_agent_config(config_data, self.corpus)

        # Verify
        self.corpus.refresh_from_db()
        self.assertEqual(
            self.corpus.corpus_agent_instructions, "Imported corpus instructions"
        )
        self.assertEqual(
            self.corpus.document_agent_instructions, "Imported document instructions"
        )

    def test_import_md_description_revisions(self):
        """Test importing markdown description and revisions."""
        md_description = "# Imported Corpus\n\nImported content."
        revisions_data = [
            {
                "version": 1,
                "diff": "Initial",
                "snapshot": md_description,
                "checksum_base": "",
                "checksum_full": "def456",
                "created": timezone.now().isoformat(),
                "author_email": self.user.email,
            }
        ]

        # Import
        import_md_description_revisions(
            md_description, revisions_data, self.corpus, self.user
        )

        # Verify
        self.corpus.refresh_from_db()
        self.assertTrue(self.corpus.md_description.name)

        with self.corpus.md_description.open("r") as f:
            content = f.read()
            self.assertEqual(content, md_description)

        revisions = CorpusDescriptionRevision.objects.filter(corpus=self.corpus)
        self.assertEqual(revisions.count(), 1)

    def test_import_relationships(self):
        """Test importing relationships via _import_v2_relationships."""
        # Create document
        doc = Document.objects.create(title="Test Doc", creator=self.user, page_count=1)

        # Create annotations
        annot1 = Annotation.objects.create(
            document=doc,
            corpus=self.corpus,
            annotation_label=self.text_label,
            raw_text="Source text",
            creator=self.user,
        )
        annot2 = Annotation.objects.create(
            document=doc,
            corpus=self.corpus,
            annotation_label=self.text_label,
            raw_text="Target text",
            creator=self.user,
        )

        # Create relationship label
        rel_label = AnnotationLabel.objects.create(
            text="Relates To",
            description="Test relationship",
            label_type=RELATIONSHIP_LABEL,
            creator=self.user,
        )
        self.labelset.annotation_labels.add(rel_label)

        # Create relationships data
        relationships_data = [
            {
                "id": "rel_1",
                "relationshipLabel": "Relates To",
                "source_annotation_ids": [str(annot1.id)],
                "target_annotation_ids": [str(annot2.id)],
                "structural": False,
            }
        ]

        # Create annotation ID map and label lookup
        annot_id_map = {str(annot1.id): annot1.id, str(annot2.id): annot2.id}
        label_lookup = {("Relates To", RELATIONSHIP_LABEL): rel_label}

        # Import using _import_v2_relationships
        _import_v2_relationships(
            relationships_data,
            self.corpus,
            annot_id_map,
            label_lookup,
            self.user,
        )

        # Verify
        relationships = Relationship.objects.filter(corpus=self.corpus)
        self.assertEqual(relationships.count(), 1)

        rel = relationships.first()
        self.assertEqual(rel.relationship_label, rel_label)
        self.assertEqual(rel.source_annotations.count(), 1)
        self.assertEqual(rel.target_annotations.count(), 1)

    def test_import_conversations(self):
        """Test importing conversations, messages, and votes."""
        # Create conversations data
        conversations_data = [
            {
                "id": "conv_1",
                "title": "Test Conversation",
                "conversation_type": "chat",
                "is_public": False,
                "creator_email": self.user.email,
                "created": timezone.now().isoformat(),
                "modified": timezone.now().isoformat(),
            }
        ]

        # Create messages data
        messages_data = [
            {
                "id": "msg_1",
                "conversation_id": "conv_1",
                "content": "Test message",
                "msg_type": "HUMAN",
                "state": "COMPLETE",
                "agent_type": None,
                "creator_email": self.user.email,
                "created": timezone.now().isoformat(),
            }
        ]

        # Create votes data
        votes_data = [
            {
                "message_id": "msg_1",
                "vote_type": "upvote",
                "creator_email": self.user.email,
                "created": timezone.now().isoformat(),
            }
        ]

        # Import
        import_conversations(
            conversations_data, messages_data, votes_data, self.corpus, self.user
        )

        # Verify conversations
        conversations = Conversation.objects.filter(chat_with_corpus=self.corpus)
        self.assertEqual(conversations.count(), 1)

        conv = conversations.first()
        self.assertEqual(conv.title, "Test Conversation")
        self.assertEqual(conv.conversation_type, "chat")

        # Verify messages
        messages = ChatMessage.objects.filter(conversation=conv)
        self.assertEqual(messages.count(), 1)

        msg = messages.first()
        self.assertEqual(msg.content, "Test message")
        self.assertEqual(msg.msg_type, "HUMAN")

        # Verify votes
        votes = MessageVote.objects.filter(message=msg)
        self.assertEqual(votes.count(), 1)

        vote = votes.first()
        self.assertEqual(vote.vote_type, "upvote")

    def test_import_structural_annotation_set_create_new(self):
        """Test creating a NEW structural annotation set (not reusing existing)."""
        # Create structural set data with unique hash
        struct_data = {
            "content_hash": "unique_new_hash_12345",
            "pawls_file_content": [{"page": {"width": 612, "height": 792, "index": 0}}],
            "txt_content": "Test structural content",
            "structural_annotations": [
                {
                    "id": "struct_annot_1",
                    "annotationLabel": "Test Label",
                    "rawText": "Test",
                    "page": 0,
                    "annotation_json": {},
                    "annotation_type": "TOKEN_LABEL",
                    "structural": True,
                }
            ],
        }

        label_lookup = {("Test Label", TOKEN_LABEL): self.text_label}

        # Import - should CREATE new since hash doesn't exist
        result = import_structural_annotation_set(struct_data, label_lookup, self.user)

        # Verify new structural set was created
        self.assertIsNotNone(result)
        self.assertEqual(result.content_hash, "unique_new_hash_12345")

        # Verify annotation was created
        annots = Annotation.objects.filter(structural_set=result)
        self.assertEqual(annots.count(), 1)
        self.assertEqual(annots.first().raw_text, "Test")

    def test_import_relationships_skip_structural(self):
        """Test that structural relationships are skipped during import."""
        # Create annotations
        doc = Document.objects.create(title="Test Doc", creator=self.user, page_count=1)
        annot1 = Annotation.objects.create(
            document=doc,
            corpus=self.corpus,
            annotation_label=self.text_label,
            raw_text="Source",
            creator=self.user,
        )
        annot2 = Annotation.objects.create(
            document=doc,
            corpus=self.corpus,
            annotation_label=self.text_label,
            raw_text="Target",
            creator=self.user,
        )

        # Create relationship label
        rel_label = AnnotationLabel.objects.create(
            text="Structural Rel",
            description="Test structural relationship",
            label_type=RELATIONSHIP_LABEL,
            creator=self.user,
        )

        # Create relationship data with structural=True
        relationships_data = [
            {
                "id": "rel_1",
                "relationshipLabel": "Structural Rel",
                "source_annotation_ids": [str(annot1.id)],
                "target_annotation_ids": [str(annot2.id)],
                "structural": True,  # This should be skipped
            }
        ]

        annot_id_map = {str(annot1.id): annot1.id, str(annot2.id): annot2.id}
        label_lookup = {("Structural Rel", RELATIONSHIP_LABEL): rel_label}

        # Import using _import_v2_relationships
        _import_v2_relationships(
            relationships_data,
            self.corpus,
            annot_id_map,
            label_lookup,
            self.user,
        )

        # Verify NO relationship was created (structural ones are skipped)
        relationships = Relationship.objects.filter(corpus=self.corpus)
        self.assertEqual(relationships.count(), 0)

    def test_import_structural_annotations_with_parents(self):
        """Test importing structural annotations with parent-child relationships."""
        struct_data = {
            "content_hash": "test_parent_hash_123",
            "pawls_file_content": [{"page": {"width": 612, "height": 792, "index": 0}}],
            "txt_content": "Parent and child annotations",
            "structural_annotations": [
                {
                    "id": "parent_annot_1",
                    "annotationLabel": "Test Label",
                    "rawText": "Parent annotation",
                    "page": 0,
                    "annotation_json": {},
                    "annotation_type": "TOKEN_LABEL",
                    "structural": True,
                    "parent_id": None,
                },
                {
                    "id": "child_annot_2",
                    "annotationLabel": "Test Label",
                    "rawText": "Child annotation",
                    "page": 0,
                    "annotation_json": {},
                    "annotation_type": "TOKEN_LABEL",
                    "structural": True,
                    "parent_id": "parent_annot_1",  # References parent
                },
            ],
        }

        label_lookup = {("Test Label", TOKEN_LABEL): self.text_label}
        result = import_structural_annotation_set(struct_data, label_lookup, self.user)

        self.assertIsNotNone(result)
        self.assertEqual(result.content_hash, "test_parent_hash_123")

        # Check that parent-child relationship was set
        annots = Annotation.objects.filter(structural_set=result).order_by("id")
        self.assertEqual(annots.count(), 2)

        parent_annot = annots[0]
        child_annot = annots[1]

        # Child should have parent set
        self.assertEqual(child_annot.parent_id, parent_annot.id)
        # Parent should have no parent
        self.assertIsNone(parent_annot.parent_id)

    def test_import_structural_relationships(self):
        """Test importing structural relationships between annotations."""
        # Create a relationship label
        rel_label = AnnotationLabel.objects.create(
            text="Causes",
            label_type="RELATIONSHIP_LABEL",
            color="blue",
            description="Causal relationship",
            creator=self.user,
        )
        self.labelset.annotation_labels.add(rel_label)

        struct_data = {
            "content_hash": "test_rel_hash_456",
            "pawls_file_content": [{"page": {"width": 612, "height": 792, "index": 0}}],
            "txt_content": "Annotations with relationships",
            "structural_annotations": [
                {
                    "id": "source_annot_1",
                    "annotationLabel": "Test Label",
                    "rawText": "Source annotation",
                    "page": 0,
                    "annotation_json": {},
                    "annotation_type": "TOKEN_LABEL",
                    "structural": True,
                },
                {
                    "id": "target_annot_2",
                    "annotationLabel": "Test Label",
                    "rawText": "Target annotation",
                    "page": 0,
                    "annotation_json": {},
                    "annotation_type": "TOKEN_LABEL",
                    "structural": True,
                },
            ],
            "structural_relationships": [
                {
                    "relationshipLabel": "Causes",
                    "source_annotation_ids": ["source_annot_1"],
                    "target_annotation_ids": ["target_annot_2"],
                }
            ],
        }

        label_lookup = {
            ("Test Label", TOKEN_LABEL): self.text_label,
            ("Causes", RELATIONSHIP_LABEL): rel_label,
        }
        result = import_structural_annotation_set(struct_data, label_lookup, self.user)

        self.assertIsNotNone(result)

        # Check that relationship was created
        relationships = Relationship.objects.filter(structural_set=result)
        self.assertEqual(relationships.count(), 1)

        rel = relationships.first()
        self.assertEqual(rel.relationship_label, rel_label)
        self.assertTrue(rel.structural)

        # Check source and target annotations are linked
        self.assertEqual(rel.source_annotations.count(), 1)
        self.assertEqual(rel.target_annotations.count(), 1)

    def test_import_structural_set_missing_label(self):
        """Test importing structural annotations with missing label (should skip)."""
        struct_data = {
            "content_hash": "test_missing_label_789",
            "pawls_file_content": [{"page": {"width": 612, "height": 792, "index": 0}}],
            "txt_content": "Test content",
            "structural_annotations": [
                {
                    "id": "annot_1",
                    "annotationLabel": "NonexistentLabel",  # This label doesn't exist
                    "rawText": "Test",
                    "page": 0,
                    "annotation_json": {},
                    "annotation_type": "TOKEN_LABEL",
                    "structural": True,
                },
                {
                    "id": "annot_2",
                    "annotationLabel": "Test Label",  # This one exists
                    "rawText": "Valid",
                    "page": 0,
                    "annotation_json": {},
                    "annotation_type": "TOKEN_LABEL",
                    "structural": True,
                },
            ],
        }

        label_lookup = {
            ("Test Label", TOKEN_LABEL): self.text_label
        }  # Missing "NonexistentLabel"
        result = import_structural_annotation_set(struct_data, label_lookup, self.user)

        self.assertIsNotNone(result)

        # Should only have 1 annotation (the one with valid label)
        annots = Annotation.objects.filter(structural_set=result)
        self.assertEqual(annots.count(), 1)
        self.assertEqual(annots.first().raw_text, "Valid")

    def test_import_relationships_missing_label(self):
        """Test importing relationships with missing label (should skip)."""
        # Create a document first
        doc = Document.objects.create(title="Test Doc", creator=self.user, page_count=1)

        # Create some annotations
        annot1 = Annotation.objects.create(
            annotation_label=self.text_label,
            document=doc,
            corpus=self.corpus,
            creator=self.user,
        )
        annot2 = Annotation.objects.create(
            annotation_label=self.text_label,
            document=doc,
            corpus=self.corpus,
            creator=self.user,
        )

        relationships_data = [
            {
                "relationshipLabel": "NonexistentRelLabel",  # Missing label
                "source_annotation_ids": [str(annot1.id)],
                "target_annotation_ids": [str(annot2.id)],
                "structural": False,
            }
        ]

        annot_id_map = {str(annot1.id): annot1.id, str(annot2.id): annot2.id}
        label_lookup = {
            ("Test Label", TOKEN_LABEL): self.text_label
        }  # Missing "NonexistentRelLabel"

        # Should not raise error, just log warning and skip
        _import_v2_relationships(
            relationships_data,
            self.corpus,
            annot_id_map,
            label_lookup,
            self.user,
        )

        # No relationships should be created
        relationships = Relationship.objects.filter(corpus=self.corpus)
        self.assertEqual(relationships.count(), 0)

    def test_import_structural_relationships_missing_label(self):
        """Test importing structural relationships with missing relationship label."""
        struct_data = {
            "content_hash": "test_missing_rel_label_999",
            "pawls_file_content": [{"page": {"width": 612, "height": 792, "index": 0}}],
            "txt_content": "Test content with relationships",
            "structural_annotations": [
                {
                    "id": "annot_1",
                    "annotationLabel": "Test Label",
                    "rawText": "Source",
                    "page": 0,
                    "annotation_json": {},
                    "annotation_type": "TOKEN_LABEL",
                    "structural": True,
                },
                {
                    "id": "annot_2",
                    "annotationLabel": "Test Label",
                    "rawText": "Target",
                    "page": 0,
                    "annotation_json": {},
                    "annotation_type": "TOKEN_LABEL",
                    "structural": True,
                },
            ],
            "structural_relationships": [
                {
                    "relationshipLabel": "MissingRelLabel",  # This label doesn't exist
                    "source_annotation_ids": ["annot_1"],
                    "target_annotation_ids": ["annot_2"],
                }
            ],
        }

        label_lookup = {
            ("Test Label", TOKEN_LABEL): self.text_label
        }  # Missing "MissingRelLabel"
        result = import_structural_annotation_set(struct_data, label_lookup, self.user)

        self.assertIsNotNone(result)

        # Should have 2 annotations but 0 relationships (missing label)
        annots = Annotation.objects.filter(structural_set=result)
        self.assertEqual(annots.count(), 2)

        relationships = Relationship.objects.filter(structural_set=result)
        self.assertEqual(
            relationships.count(), 0
        )  # No relationship due to missing label


class TestV2ImportExceptionHandling(TransactionTestCase):
    """Test exception handling in V2 import functions."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.labelset = LabelSet.objects.create(
            title="Test LabelSet", creator=self.user
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus", label_set=self.labelset, creator=self.user
        )
        self.text_label = AnnotationLabel.objects.create(
            text="Test Label", label_type=TOKEN_LABEL, creator=self.user
        )
        self.labelset.annotation_labels.add(self.text_label)

    @mock.patch(
        "opencontractserver.utils.import_v2.StructuralAnnotationSet.objects.create"
    )
    def test_import_structural_set_exception(self, mock_create):
        """Test import_structural_annotation_set exception handler (lines 185-187)."""
        from opencontractserver.utils.import_v2 import import_structural_annotation_set

        # Force an exception when creating StructuralAnnotationSet
        mock_create.side_effect = Exception("Database error")

        struct_data = {
            "content_hash": "hash123",
            "parser_name": "test_parser",
            "parser_version": "1.0",
            "page_count": 1,
            "token_count": 100,
            "pawls_file_content": [],
            "txt_content": "test",
            "structural_annotations": [],
            "structural_relationships": [],
        }

        label_lookup = {}
        result = import_structural_annotation_set(struct_data, label_lookup, self.user)

        # Should return None on exception
        self.assertIsNone(result)

    @mock.patch("opencontractserver.utils.import_v2.CorpusFolder.objects.create")
    def test_import_corpus_folders_exception(self, mock_create):
        """Test import_corpus_folders exception handler (lines 239-240)."""
        from opencontractserver.utils.import_v2 import import_corpus_folders

        # Force an exception when creating folder
        mock_create.side_effect = Exception("Database error")

        folders_data = [
            {
                "id": "folder1",
                "name": "Test Folder",
                "description": "Test",
                "color": "#05313d",
                "icon": "folder",
                "tags": [],
                "is_public": False,
                "parent_id": None,
                "path": "/Test Folder",
            }
        ]

        result = import_corpus_folders(folders_data, self.corpus, self.user)

        # Should return empty dict on exception
        self.assertEqual(result, {})

    @mock.patch("opencontractserver.tasks.import_tasks_v2.Relationship.objects.create")
    def test_import_relationships_exception(self, mock_create):
        """Test _import_v2_relationships handles exceptions gracefully."""
        # Create annotation for ID mapping
        doc = Document.objects.create(title="Test Doc", creator=self.user, page_count=1)
        annot = Annotation.objects.create(
            annotation_label=self.text_label,
            document=doc,
            corpus=self.corpus,
            creator=self.user,
        )

        # Create a relationship label for the lookup
        rel_label = AnnotationLabel.objects.create(
            text="Test Rel Label",
            label_type=RELATIONSHIP_LABEL,
            creator=self.user,
        )

        # Force an exception when creating Relationship
        mock_create.side_effect = Exception("Database error")

        relationships_data = [
            {
                "id": "rel1",
                "relationshipLabel": "Test Rel Label",
                "source_annotation_ids": [str(annot.id)],
                "target_annotation_ids": [str(annot.id)],
                "structural": False,
            }
        ]

        annot_id_map = {str(annot.id): annot.id}
        label_lookup = {("Test Rel Label", RELATIONSHIP_LABEL): rel_label}

        # Should raise the exception (function doesn't have try/except)
        with self.assertRaises(Exception):
            _import_v2_relationships(
                relationships_data,
                self.corpus,
                annot_id_map,
                label_lookup,
                self.user,
            )

    @mock.patch("opencontractserver.corpuses.models.Corpus.save")
    def test_import_agent_config_exception(self, mock_save):
        """Test import_agent_config exception handler (lines 422-423)."""
        from opencontractserver.utils.import_v2 import import_agent_config

        # Force an exception when saving corpus
        mock_save.side_effect = Exception("Database error")

        agent_config = {
            "corpus_agent_instructions": "Test instructions",
            "document_agent_instructions": "Test doc instructions",
        }

        # Should not raise exception - handles it gracefully
        import_agent_config(agent_config, self.corpus)

    @mock.patch(
        "opencontractserver.tasks.import_tasks_v2._setup_corpus_and_labels",
        side_effect=Exception("Setup failed"),
    )
    def test_import_corpus_exception_handler(self, mock_setup):
        """Test _import_corpus catches exceptions and returns None."""
        from opencontractserver.tasks.import_tasks_v2 import _import_corpus

        result = _import_corpus(
            data_json={"annotated_docs": {}},
            import_zip=None,
            user_obj=self.user,
            seed_corpus_id=None,
            version="2.0",
        )
        self.assertIsNone(result)

    @mock.patch(
        "opencontractserver.tasks.import_tasks_v2.create_document_from_export_data",
        side_effect=Exception("PDF corrupt"),
    )
    def test_import_document_with_annotations_exception(self, mock_create_doc):
        """Test _import_document_with_annotations returns (None, {}) on error."""
        from opencontractserver.tasks.import_tasks_v2 import (
            _import_document_with_annotations,
        )

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("doc.pdf", b"%PDF-1.4 minimal")
        buf.seek(0)

        with zipfile.ZipFile(buf, "r") as zf:
            doc, annot_map = _import_document_with_annotations(
                doc_filename="doc.pdf",
                doc_data={"title": "T", "description": "", "page_count": 1},
                import_zip=zf,
                user_obj=self.user,
                corpus_obj=self.corpus,
                label_lookup={},
                doc_label_lookup={},
            )

        self.assertIsNone(doc)
        self.assertEqual(annot_map, {})

    @mock.patch(
        "opencontractserver.tasks.export_tasks.Notification.objects.create",
        side_effect=Exception("DB error"),
    )
    def test_create_export_notification_exception(self, mock_create):
        """Test _create_export_notification handles exceptions gracefully."""
        from opencontractserver.tasks.export_tasks import _create_export_notification

        export = UserExport.objects.create(backend_lock=False, creator=self.user)
        # Should not raise - handles gracefully
        _create_export_notification(export, "Test Corpus")


class TestV2FullRoundTrip(TransactionTestCase):
    """Test complete V2 export/import round-trip."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")

        # Create comprehensive test corpus
        self.labelset = LabelSet.objects.create(
            title="Test LabelSet", creator=self.user
        )

        self.text_label = AnnotationLabel.objects.create(
            text="Test Label",
            description="Test label description",
            label_type=TOKEN_LABEL,
            creator=self.user,
        )
        self.labelset.annotation_labels.add(self.text_label)

        self.corpus = Corpus.objects.create(
            title="Test Corpus V2",
            description="Test corpus for V2 export/import",
            label_set=self.labelset,
            creator=self.user,
            corpus_agent_instructions="Test instructions",
            post_processors=["test.processor"],
            allow_comments=True,
        )
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.ALL])

        # Create folder
        self.folder = CorpusFolder.objects.create(
            corpus=self.corpus,
            name="Test Folder",
            creator=self.user,
        )

        # Create structural annotation set
        self.struct_set = StructuralAnnotationSet.objects.create(
            content_hash="test_content_hash",
            parser_name="docling",
            page_count=1,
            pawls_parse_file=ContentFile(
                json.dumps([{"page": {"index": 0}, "tokens": []}]).encode(),
                name="pawls.json",
            ),
            txt_extract_file=ContentFile(b"Test content", name="text.txt"),
            creator=self.user,
        )

        # Create structural annotation
        Annotation.objects.create(
            structural_set=self.struct_set,
            annotation_label=self.text_label,
            raw_text="Header",
            structural=True,
            creator=self.user,
        )

        # Create document with structural set
        # Create a minimal valid PDF
        minimal_pdf = (
            b"%PDF-1.4\n"
            b"1 0 obj <</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj <</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
            b"3 0 obj <</Type/Page/Parent 2 0 R/Resources<<>>/MediaBox[0 0 612 792]>>endobj\n"
            b"xref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000056 00000 n\n"
            b"0000000115 00000 n\ntrailer <</Size 4/Root 1 0 R>>\nstartxref\n204\n%%EOF\n"
        )
        self.doc = Document.objects.create(
            title="Test Document",
            pdf_file=ContentFile(minimal_pdf, name="test.pdf"),
            pdf_file_hash="test_content_hash",
            structural_annotation_set=self.struct_set,
            creator=self.user,
            page_count=1,
        )

        # Create document path
        self.doc_path = DocumentPath.objects.create(
            document=self.doc,
            corpus=self.corpus,
            folder=self.folder,
            path="/documents/test.pdf",
            version_number=1,
            creator=self.user,
        )

        # Create user annotation
        self.annot = Annotation.objects.create(
            document=self.doc,
            corpus=self.corpus,
            annotation_label=self.text_label,
            raw_text="Test annotation",
            page=0,
            creator=self.user,
        )

    def test_export_content_modalities(self):
        """Test that content_modalities is included in export when set."""
        # Set content_modalities on the annotation
        self.annot.content_modalities = ["IMAGE"]
        self.annot.save(update_fields=["content_modalities"])

        export = UserExport.objects.create(backend_lock=True, creator=self.user)

        package_corpus_export_v2(
            export_id=export.id,
            corpus_pk=self.corpus.id,
            include_conversations=False,
        )

        export.refresh_from_db()
        with export.file.open("rb") as f:
            with zipfile.ZipFile(f, "r") as zip_ref:
                with zip_ref.open("data.json") as data_file:
                    data = json.load(data_file)

        # Find annotation in exported docs and check content_modalities
        for doc_data in data["annotated_docs"].values():
            for annot_data in doc_data.get("labelled_text", []):
                if annot_data.get("content_modalities"):
                    self.assertEqual(annot_data["content_modalities"], ["IMAGE"])
                    return

        self.fail("content_modalities not found in any exported annotation")

    def test_v2_export_import_round_trip(self):
        """Test full V2 export followed by import."""
        # Create export
        export = UserExport.objects.create(backend_lock=True, creator=self.user)

        # Run export
        package_corpus_export_v2(
            export_id=export.id,
            corpus_pk=self.corpus.id,
            include_conversations=False,
        )

        # Verify export was created
        export.refresh_from_db()
        self.assertIsNotNone(export.file)
        self.assertTrue(export.file.name.endswith("_EXPORT_V2.zip"))

        # Read and verify export content
        with export.file.open("rb") as f:
            with zipfile.ZipFile(f, "r") as zip_ref:
                # Check data.json exists
                self.assertIn("data.json", zip_ref.namelist())

                # Load and verify data.json
                with zip_ref.open("data.json") as data_file:
                    data = json.load(data_file)

                    # Verify version
                    self.assertEqual(data["version"], "2.0")

                    # Verify V2 fields present
                    self.assertIn("structural_annotation_sets", data)
                    self.assertIn("folders", data)
                    self.assertIn("document_paths", data)
                    self.assertIn("agent_config", data)

                    # Verify structural set exported
                    self.assertEqual(len(data["structural_annotation_sets"]), 1)
                    self.assertIn(
                        "test_content_hash", data["structural_annotation_sets"]
                    )

                    # Verify folder exported
                    self.assertEqual(len(data["folders"]), 1)
                    self.assertEqual(data["folders"][0]["name"], "Test Folder")

                    # Verify document path exported
                    self.assertEqual(len(data["document_paths"]), 1)

        # Now test import
        temp_file = TemporaryFileHandle.objects.create()
        export.file.open("rb")
        temp_file.file.save("test_import.zip", export.file)
        export.file.close()

        # Import into new corpus
        imported_corpus_id = import_corpus_v2(
            temporary_file_handle_id=temp_file.id,
            user_id=self.user.id,
            seed_corpus_id=None,
        )

        # Verify import succeeded
        self.assertIsNotNone(imported_corpus_id)

        imported_corpus = Corpus.objects.get(id=imported_corpus_id)
        self.assertEqual(imported_corpus.title, "Test Corpus V2")
        self.assertEqual(imported_corpus.corpus_agent_instructions, "Test instructions")
        self.assertEqual(imported_corpus.post_processors, ["test.processor"])

        # Verify folder imported
        imported_folders = CorpusFolder.objects.filter(corpus=imported_corpus)
        self.assertEqual(imported_folders.count(), 1)
        self.assertEqual(imported_folders.first().name, "Test Folder")

        # Verify structural set reused (not duplicated)
        struct_sets = StructuralAnnotationSet.objects.filter(
            content_hash="test_content_hash"
        )
        self.assertEqual(struct_sets.count(), 1)  # Same one reused

        # Verify document imported
        imported_docs = DocumentPath.objects.filter(
            corpus=imported_corpus, is_current=True, is_deleted=False
        ).values_list("document_id", flat=True)
        self.assertEqual(len(imported_docs), 1)

        # Verify user annotation imported
        imported_annots = Annotation.objects.filter(
            corpus=imported_corpus, structural=False
        )
        self.assertTrue(imported_annots.exists())


class TestV1BackwardCompatibility(TransactionTestCase):
    """Test that V1 exports can still be imported."""

    fixtures_path = pathlib.Path(__file__).parent / "fixtures"

    def setUp(self):
        self.user = User.objects.create_user(username="bob", password="12345678")

    def test_v1_export_imports_successfully(self):
        """Test that an old V1 export can be imported with new V2 importer."""
        # Check if V1 test fixture exists
        v1_fixture = self.fixtures_path / "Test_Corpus_EXPORT.zip"
        if not v1_fixture.exists():
            self.skipTest("V1 test fixture not available")

        # Read V1 export
        with open(v1_fixture, "rb") as f:
            zip_content = f.read()

        # Create temporary file
        temp_file = TemporaryFileHandle.objects.create()
        temp_file.file.save("v1_import.zip", ContentFile(zip_content))

        # Import using V2 importer
        imported_corpus_id = import_corpus_v2(
            temporary_file_handle_id=temp_file.id,
            user_id=self.user.id,
            seed_corpus_id=None,
        )

        # Verify import succeeded
        self.assertIsNotNone(imported_corpus_id)

        imported_corpus = Corpus.objects.get(id=imported_corpus_id)
        self.assertIsNotNone(imported_corpus)

        # Verify documents were imported
        docs = Document.objects.filter(
            id__in=DocumentPath.objects.filter(
                corpus=imported_corpus, is_current=True, is_deleted=False
            ).values_list("document_id", flat=True)
        )
        self.assertGreater(docs.count(), 0)

        # Verify annotations were imported
        annots = Annotation.objects.filter(corpus=imported_corpus)
        self.assertGreater(annots.count(), 0)


class TestV2EdgeCases(TransactionTestCase):
    """Test edge cases and error handling."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")

    def test_export_empty_corpus(self):
        """Test exporting an empty corpus."""
        labelset = LabelSet.objects.create(title="Empty Set", creator=self.user)
        corpus = Corpus.objects.create(
            title="Empty Corpus",
            label_set=labelset,
            creator=self.user,
        )

        export = UserExport.objects.create(backend_lock=True, creator=self.user)

        # Should not fail on empty corpus
        package_corpus_export_v2(
            export_id=export.id,
            corpus_pk=corpus.id,
            include_conversations=False,
        )

        # Refresh export to get saved file
        export.refresh_from_db()
        self.assertIsNotNone(export.file)

    def test_export_with_conversations(self):
        """Test exporting corpus with conversations included."""
        labelset = LabelSet.objects.create(title="Test Set", creator=self.user)
        corpus = Corpus.objects.create(
            title="Corpus with Convos",
            label_set=labelset,
            creator=self.user,
        )

        # Create conversation
        Conversation.objects.create(
            chat_with_corpus=corpus,
            title="Test Thread",
            creator=self.user,
        )

        export = UserExport.objects.create(backend_lock=True, creator=self.user)

        # Export with conversations
        package_corpus_export_v2(
            export_id=export.id,
            corpus_pk=corpus.id,
            include_conversations=True,
        )

        # Verify conversations in export
        export.refresh_from_db()
        with export.file.open("rb") as f:
            with zipfile.ZipFile(f, "r") as zip_ref:
                with zip_ref.open("data.json") as data_file:
                    data = json.load(data_file)
                    self.assertIn("conversations", data)
                    self.assertEqual(len(data["conversations"]), 1)

    def test_import_zip_missing_data_json(self):
        """Test importing a ZIP that has no data.json returns None."""
        # Create a ZIP without data.json
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("readme.txt", "no data here")
        buf.seek(0)

        temp_file = TemporaryFileHandle.objects.create()
        temp_file.file.save("bad.zip", ContentFile(buf.getvalue()))

        result = import_corpus_v2(
            temporary_file_handle_id=temp_file.id,
            user_id=self.user.id,
            seed_corpus_id=None,
        )
        self.assertIsNone(result)

    def test_import_corpus_v2_invalid_handle(self):
        """Test import_corpus_v2 with non-existent file handle returns None."""
        result = import_corpus_v2(
            temporary_file_handle_id=999999,
            user_id=self.user.id,
            seed_corpus_id=None,
        )
        self.assertIsNone(result)

    @mock.patch(
        "opencontractserver.tasks.import_tasks_v2._import_corpus",
        side_effect=Exception("boom"),
    )
    def test_import_corpus_v2_exception_in_import_corpus(self, mock_import):
        """Test import_corpus_v2 catches exceptions from _import_corpus."""
        # Build a valid minimal ZIP with data.json
        data = {
            "annotated_docs": {},
            "corpus": {"title": "X"},
            "label_set": {"title": "LS"},
            "doc_labels": {},
            "text_labels": {},
        }
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("data.json", json.dumps(data))
        buf.seek(0)

        temp_file = TemporaryFileHandle.objects.create()
        temp_file.file.save("err.zip", ContentFile(buf.getvalue()))

        result = import_corpus_v2(
            temporary_file_handle_id=temp_file.id,
            user_id=self.user.id,
            seed_corpus_id=None,
        )
        self.assertIsNone(result)

    def test_import_without_optional_fields(self):
        """Test importing V2 export that's missing optional fields."""
        # This tests graceful handling of exports without conversations, etc.
        labelset = LabelSet.objects.create(title="Test Set", creator=self.user)
        corpus = Corpus.objects.create(
            title="Minimal Corpus",
            label_set=labelset,
            creator=self.user,
        )

        export = UserExport.objects.create(backend_lock=True, creator=self.user)

        # Export without conversations
        package_corpus_export_v2(
            export_id=export.id,
            corpus_pk=corpus.id,
            include_conversations=False,
        )

        # Refresh export to get saved file
        export.refresh_from_db()

        # Import
        temp_file = TemporaryFileHandle.objects.create()
        export.file.open("rb")
        temp_file.file.save("minimal.zip", export.file)
        export.file.close()

        imported_id = import_corpus_v2(
            temporary_file_handle_id=temp_file.id,
            user_id=self.user.id,
            seed_corpus_id=None,
        )

        # Should succeed even without optional fields
        self.assertIsNotNone(imported_id)


class TestLabelTypeExportCompleteness(TransactionTestCase):
    """Test that all label types (TOKEN, DOC, SPAN, RELATIONSHIP) are exported."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")

        self.labelset = LabelSet.objects.create(
            title="Test LabelSet", creator=self.user
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            label_set=self.labelset,
            creator=self.user,
        )
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.ALL])

        # Create labels of all types
        self.token_label = AnnotationLabel.objects.create(
            text="Token Label", label_type=TOKEN_LABEL, creator=self.user
        )
        self.doc_label = AnnotationLabel.objects.create(
            text="Doc Label", label_type=DOC_TYPE_LABEL, creator=self.user
        )
        self.span_label = AnnotationLabel.objects.create(
            text="Span Label", label_type=SPAN_LABEL, creator=self.user
        )
        self.rel_label = AnnotationLabel.objects.create(
            text="Rel Label", label_type=RELATIONSHIP_LABEL, creator=self.user
        )
        self.labelset.annotation_labels.add(
            self.token_label, self.doc_label, self.span_label, self.rel_label
        )

        # Create a document
        minimal_pdf = b"%PDF-1.4 minimal"
        self.doc = Document.objects.create(
            title="Test Doc",
            pdf_file=ContentFile(minimal_pdf, name="test.pdf"),
            creator=self.user,
            page_count=1,
        )
        DocumentPath.objects.create(
            document=self.doc,
            corpus=self.corpus,
            path="/test.pdf",
            version_number=1,
            creator=self.user,
        )

        # Create annotations with TOKEN_LABEL and SPAN_LABEL
        Annotation.objects.create(
            document=self.doc,
            corpus=self.corpus,
            annotation_label=self.token_label,
            raw_text="Token text",
            creator=self.user,
        )
        Annotation.objects.create(
            document=self.doc,
            corpus=self.corpus,
            annotation_label=self.span_label,
            raw_text="Span text",
            creator=self.user,
        )
        Annotation.objects.create(
            document=self.doc,
            corpus=self.corpus,
            annotation_label=self.doc_label,
            annotation_type=DOC_TYPE_LABEL,
            creator=self.user,
        )

        # Create a relationship using the RELATIONSHIP_LABEL
        annot1 = Annotation.objects.create(
            document=self.doc,
            corpus=self.corpus,
            annotation_label=self.token_label,
            raw_text="Source",
            creator=self.user,
        )
        annot2 = Annotation.objects.create(
            document=self.doc,
            corpus=self.corpus,
            annotation_label=self.token_label,
            raw_text="Target",
            creator=self.user,
        )
        rel = Relationship.objects.create(
            corpus=self.corpus,
            document=self.doc,
            relationship_label=self.rel_label,
            creator=self.user,
        )
        rel.source_annotations.add(annot1)
        rel.target_annotations.add(annot2)

    def test_build_label_lookups_includes_all_types(self):
        """Verify that build_label_lookups exports SPAN_LABEL and RELATIONSHIP_LABEL."""
        lookups = build_label_lookups(corpus_id=self.corpus.id)

        text_labels = lookups["text_labels"]
        doc_labels = lookups["doc_labels"]

        # Collect all label types from text_labels
        text_label_types = {v["label_type"] for v in text_labels.values()}
        doc_label_types = {v["label_type"] for v in doc_labels.values()}

        # TOKEN_LABEL, SPAN_LABEL, and RELATIONSHIP_LABEL should be in text_labels
        self.assertIn("TOKEN_LABEL", text_label_types)
        self.assertIn("SPAN_LABEL", text_label_types)
        self.assertIn("RELATIONSHIP_LABEL", text_label_types)

        # DOC_TYPE_LABEL should be in doc_labels
        self.assertIn("DOC_TYPE_LABEL", doc_label_types)

    def test_roundtrip_preserves_all_label_types(self):
        """Full roundtrip test verifying all label types survive export/import."""
        export = UserExport.objects.create(backend_lock=True, creator=self.user)

        package_corpus_export_v2(
            export_id=export.id,
            corpus_pk=self.corpus.id,
        )

        export.refresh_from_db()

        # Read export data
        with export.file.open("rb") as f:
            with zipfile.ZipFile(f, "r") as zip_ref:
                with zip_ref.open("data.json") as data_file:
                    data = json.load(data_file)

        # Verify text_labels contains all non-DOC types
        text_label_types = {v["label_type"] for v in data["text_labels"].values()}
        self.assertIn("TOKEN_LABEL", text_label_types)
        self.assertIn("SPAN_LABEL", text_label_types)
        self.assertIn("RELATIONSHIP_LABEL", text_label_types)

        # Verify doc_labels contains DOC_TYPE_LABEL
        doc_label_types = {v["label_type"] for v in data["doc_labels"].values()}
        self.assertIn("DOC_TYPE_LABEL", doc_label_types)

        # Import and verify labels are reconstructed
        temp_file = TemporaryFileHandle.objects.create()
        export.file.open("rb")
        temp_file.file.save("test_labels.zip", export.file)
        export.file.close()

        imported_corpus_id = import_corpus_v2(
            temporary_file_handle_id=temp_file.id,
            user_id=self.user.id,
            seed_corpus_id=None,
        )
        self.assertIsNotNone(imported_corpus_id)

        imported_corpus = Corpus.objects.get(id=imported_corpus_id)
        imported_labels = imported_corpus.label_set.annotation_labels.all()
        imported_label_types = set(imported_labels.values_list("label_type", flat=True))

        self.assertIn(TOKEN_LABEL, imported_label_types)
        self.assertIn(DOC_TYPE_LABEL, imported_label_types)
        self.assertIn(SPAN_LABEL, imported_label_types)
        self.assertIn(RELATIONSHIP_LABEL, imported_label_types)


class TestDocumentFileTypeRoundTrip(TransactionTestCase):
    """Test that document file_type is preserved through export/import."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.labelset = LabelSet.objects.create(
            title="Test LabelSet", creator=self.user
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            label_set=self.labelset,
            creator=self.user,
        )
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.ALL])

    def test_file_type_in_export(self):
        """Verify file_type is included in exported document data."""
        doc = Document.objects.create(
            title="Test Text Doc",
            file_type="text/plain",
            pdf_file=ContentFile(b"plain text content", name="test.txt"),
            creator=self.user,
            page_count=1,
        )
        DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            path="/test.txt",
            version_number=1,
            creator=self.user,
        )

        export = UserExport.objects.create(backend_lock=True, creator=self.user)
        package_corpus_export_v2(
            export_id=export.id,
            corpus_pk=self.corpus.id,
        )

        export.refresh_from_db()
        with export.file.open("rb") as f:
            with zipfile.ZipFile(f, "r") as zip_ref:
                with zip_ref.open("data.json") as data_file:
                    data = json.load(data_file)

        # Check that file_type is present in exported doc data
        for doc_data in data["annotated_docs"].values():
            self.assertEqual(doc_data["file_type"], "text/plain")


class TestConversationExportEnhancements(TransactionTestCase):
    """Test enhanced conversation export features."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass", email="test@test.com"
        )
        self.labelset = LabelSet.objects.create(
            title="Test LabelSet", creator=self.user
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            label_set=self.labelset,
            creator=self.user,
        )
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.ALL])

        # Create a document for doc-level conversations
        minimal_pdf = b"%PDF-1.4 minimal"
        self.doc = Document.objects.create(
            title="Test Doc",
            pdf_file=ContentFile(minimal_pdf, name="test.pdf"),
            creator=self.user,
            page_count=1,
        )
        self.doc_path = DocumentPath.objects.create(
            document=self.doc,
            corpus=self.corpus,
            path="/test.pdf",
            version_number=1,
            creator=self.user,
        )

    def test_doc_level_conversations_exported(self):
        """Verify document-level conversations are included in export."""
        # Create corpus-level conversation
        Conversation.objects.create(
            chat_with_corpus=self.corpus,
            title="Corpus Thread",
            creator=self.user,
        )

        # Create document-level conversation
        Conversation.objects.create(
            chat_with_document=self.doc,
            title="Doc Thread",
            creator=self.user,
        )

        conversations, messages, votes = package_conversations(
            self.corpus, document_ids=[self.doc.id]
        )

        self.assertEqual(len(conversations), 2)
        titles = {c["title"] for c in conversations}
        self.assertIn("Corpus Thread", titles)
        self.assertIn("Doc Thread", titles)

        # Verify doc-level conversation has document reference
        doc_conv_data = next(c for c in conversations if c["title"] == "Doc Thread")
        self.assertIsNotNone(doc_conv_data["chat_with_document_id"])

    def test_conversation_description_exported(self):
        """Verify conversation description is included in export."""
        Conversation.objects.create(
            chat_with_corpus=self.corpus,
            title="Thread with Desc",
            description="This is a description",
            creator=self.user,
        )

        conversations, _, _ = package_conversations(self.corpus)

        self.assertEqual(len(conversations), 1)
        self.assertEqual(conversations[0]["description"], "This is a description")

    def test_message_parent_and_data_exported(self):
        """Verify parent_message and data fields are exported."""
        conv = Conversation.objects.create(
            chat_with_corpus=self.corpus,
            title="Threaded",
            creator=self.user,
        )

        parent_msg = ChatMessage.objects.create(
            conversation=conv,
            content="Parent message",
            msg_type="HUMAN",
            data={"key": "value"},
            creator=self.user,
        )

        ChatMessage.objects.create(
            conversation=conv,
            content="Reply",
            msg_type="HUMAN",
            parent_message=parent_msg,
            creator=self.user,
        )

        _, messages, _ = package_conversations(self.corpus)

        self.assertEqual(len(messages), 2)

        # Find parent and child
        parent_data = next(m for m in messages if m["content"] == "Parent message")
        child_data = next(m for m in messages if m["content"] == "Reply")

        self.assertIsNone(parent_data["parent_message_id"])
        self.assertEqual(parent_data["data"], {"key": "value"})
        self.assertEqual(child_data["parent_message_id"], parent_data["id"])

    def test_conversation_import_timestamps_preserved(self):
        """Verify timestamps survive import despite auto_now_add fields."""
        from datetime import timedelta

        original_time = timezone.now() - timedelta(days=30)

        conversations_data = [
            {
                "id": "conv_1",
                "title": "Old Conversation",
                "conversation_type": "chat",
                "is_public": False,
                "creator_email": self.user.email,
                "chat_with_corpus": True,
                "created": original_time.isoformat(),
                "modified": original_time.isoformat(),
            }
        ]

        messages_data = [
            {
                "id": "msg_1",
                "conversation_id": "conv_1",
                "content": "Old message",
                "msg_type": "HUMAN",
                "state": "COMPLETE",
                "creator_email": self.user.email,
                "created": original_time.isoformat(),
            }
        ]

        import_conversations(
            conversations_data, messages_data, [], self.corpus, self.user
        )

        conv = Conversation.objects.filter(chat_with_corpus=self.corpus).first()
        self.assertIsNotNone(conv)

        # Timestamps should be close to the original (within a second)
        self.assertAlmostEqual(
            conv.created_at.timestamp(),
            original_time.timestamp(),
            delta=1.0,
        )

        msg = ChatMessage.objects.filter(conversation=conv).first()
        self.assertIsNotNone(msg)
        self.assertAlmostEqual(
            msg.created_at.timestamp(),
            original_time.timestamp(),
            delta=1.0,
        )

    def test_conversation_import_parent_message_relinked(self):
        """Verify parent_message re-linking works on import."""
        conversations_data = [
            {
                "id": "conv_1",
                "title": "Threaded Conv",
                "conversation_type": "thread",
                "is_public": False,
                "creator_email": self.user.email,
                "chat_with_corpus": True,
                "created": timezone.now().isoformat(),
                "modified": timezone.now().isoformat(),
            }
        ]

        messages_data = [
            {
                "id": "msg_parent",
                "conversation_id": "conv_1",
                "content": "Parent",
                "msg_type": "HUMAN",
                "state": "COMPLETE",
                "parent_message_id": None,
                "creator_email": self.user.email,
                "created": timezone.now().isoformat(),
            },
            {
                "id": "msg_child",
                "conversation_id": "conv_1",
                "content": "Reply",
                "msg_type": "HUMAN",
                "state": "COMPLETE",
                "parent_message_id": "msg_parent",
                "creator_email": self.user.email,
                "created": timezone.now().isoformat(),
            },
        ]

        import_conversations(
            conversations_data, messages_data, [], self.corpus, self.user
        )

        messages = ChatMessage.objects.filter(
            conversation__chat_with_corpus=self.corpus
        ).order_by("created_at")
        self.assertEqual(messages.count(), 2)

        parent = messages.filter(content="Parent").first()
        child = messages.filter(content="Reply").first()

        self.assertIsNone(parent.parent_message)
        self.assertEqual(child.parent_message_id, parent.id)

    def test_conversation_import_description_and_flags(self):
        """Verify description, is_locked, is_pinned survive import."""
        conversations_data = [
            {
                "id": "conv_1",
                "title": "Annotated Conv",
                "description": "Important discussion",
                "conversation_type": "thread",
                "is_public": True,
                "is_locked": True,
                "is_pinned": True,
                "creator_email": self.user.email,
                "chat_with_corpus": True,
                "created": timezone.now().isoformat(),
                "modified": timezone.now().isoformat(),
            }
        ]

        import_conversations(conversations_data, [], [], self.corpus, self.user)

        conv = Conversation.objects.filter(chat_with_corpus=self.corpus).first()
        self.assertEqual(conv.description, "Important discussion")
        self.assertTrue(conv.is_locked)
        self.assertTrue(conv.is_pinned)


class TestReconstructDocumentPaths(TransactionTestCase):
    """Test _reconstruct_document_paths covers all branches."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.labelset = LabelSet.objects.create(
            title="Test LabelSet", creator=self.user
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            label_set=self.labelset,
            creator=self.user,
        )

        # Create a document with a known hash
        self.doc = Document.objects.create(
            title="Test Doc",
            pdf_file_hash="hash_abc",
            creator=self.user,
            page_count=1,
        )

        # Add document to corpus (creates a DocumentPath)
        self.corpus_doc, _, self.doc_path = self.corpus.add_document(
            document=self.doc, user=self.user
        )

        # Create a folder for the corpus
        self.folder = CorpusFolder.objects.create(
            corpus=self.corpus,
            name="MyFolder",
            creator=self.user,
        )

    def test_updates_path_version_and_folder(self):
        """Test that path, version_number, and folder are updated."""
        from opencontractserver.tasks.import_tasks_v2 import _reconstruct_document_paths

        doc_hash_map = {"hash_abc": self.corpus_doc}

        document_paths_data = [
            {
                "document_ref": "hash_abc",
                "path": "/custom/path/doc.pdf",
                "version_number": 5,
                "folder_path": "MyFolder",
                "is_current": True,
                "is_deleted": False,
            }
        ]

        _reconstruct_document_paths(document_paths_data, self.corpus, doc_hash_map)

        # Reload DocumentPath
        updated_path = DocumentPath.objects.filter(
            corpus=self.corpus, document=self.corpus_doc
        ).first()
        self.assertEqual(updated_path.path, "/custom/path/doc.pdf")
        self.assertEqual(updated_path.version_number, 5)
        self.assertEqual(updated_path.folder, self.folder)

    def test_skips_non_current_paths(self):
        """Test that non-current paths are skipped."""
        from opencontractserver.tasks.import_tasks_v2 import _reconstruct_document_paths

        doc_hash_map = {"hash_abc": self.corpus_doc}
        original_path = self.doc_path.path

        document_paths_data = [
            {
                "document_ref": "hash_abc",
                "path": "/should/not/apply",
                "version_number": 99,
                "is_current": False,
                "is_deleted": False,
            }
        ]

        _reconstruct_document_paths(document_paths_data, self.corpus, doc_hash_map)

        # Path should remain unchanged
        self.doc_path.refresh_from_db()
        self.assertEqual(self.doc_path.path, original_path)

    def test_skips_deleted_paths(self):
        """Test that deleted paths are skipped."""
        from opencontractserver.tasks.import_tasks_v2 import _reconstruct_document_paths

        doc_hash_map = {"hash_abc": self.corpus_doc}
        original_path = self.doc_path.path

        document_paths_data = [
            {
                "document_ref": "hash_abc",
                "path": "/should/not/apply",
                "is_current": True,
                "is_deleted": True,
            }
        ]

        _reconstruct_document_paths(document_paths_data, self.corpus, doc_hash_map)

        self.doc_path.refresh_from_db()
        self.assertEqual(self.doc_path.path, original_path)

    def test_skips_missing_document_ref(self):
        """Test that paths with unknown document_ref are skipped."""
        from opencontractserver.tasks.import_tasks_v2 import _reconstruct_document_paths

        doc_hash_map = {"hash_abc": self.corpus_doc}

        document_paths_data = [
            {
                "document_ref": "unknown_hash",
                "path": "/should/not/apply",
                "is_current": True,
                "is_deleted": False,
            }
        ]

        _reconstruct_document_paths(document_paths_data, self.corpus, doc_hash_map)

        # No error, path unchanged
        self.doc_path.refresh_from_db()

    def test_skips_missing_existing_path(self):
        """Test that paths are skipped when no DocumentPath exists for the doc."""
        from opencontractserver.tasks.import_tasks_v2 import _reconstruct_document_paths

        # Create a second doc that has no DocumentPath in this corpus
        other_doc = Document.objects.create(
            title="Other Doc",
            pdf_file_hash="hash_other",
            creator=self.user,
            page_count=1,
        )

        doc_hash_map = {"hash_other": other_doc}

        document_paths_data = [
            {
                "document_ref": "hash_other",
                "path": "/some/path",
                "is_current": True,
                "is_deleted": False,
            }
        ]

        # Should not raise
        _reconstruct_document_paths(document_paths_data, self.corpus, doc_hash_map)

    def test_no_updates_when_values_match(self):
        """Test that no save is performed when exported values match existing."""
        from opencontractserver.tasks.import_tasks_v2 import _reconstruct_document_paths

        doc_hash_map = {"hash_abc": self.corpus_doc}

        # Pass the same path and version_number that already exist
        document_paths_data = [
            {
                "document_ref": "hash_abc",
                "path": self.doc_path.path,
                "version_number": self.doc_path.version_number,
                "is_current": True,
                "is_deleted": False,
            }
        ]

        _reconstruct_document_paths(document_paths_data, self.corpus, doc_hash_map)

        # No changes expected
        self.doc_path.refresh_from_db()

    def test_folder_path_not_found(self):
        """Test that unmatched folder_path is silently ignored."""
        from opencontractserver.tasks.import_tasks_v2 import _reconstruct_document_paths

        doc_hash_map = {"hash_abc": self.corpus_doc}

        document_paths_data = [
            {
                "document_ref": "hash_abc",
                "path": "/new/path",
                "folder_path": "NonexistentFolder",
                "is_current": True,
                "is_deleted": False,
            }
        ]

        _reconstruct_document_paths(document_paths_data, self.corpus, doc_hash_map)

        updated_path = DocumentPath.objects.filter(
            corpus=self.corpus, document=self.corpus_doc
        ).first()
        self.assertEqual(updated_path.path, "/new/path")
        # folder should not be set
        self.assertIsNone(updated_path.folder)


class TestBuildLabelLookupsEdgeCases(TransactionTestCase):
    """Test edge cases in build_label_lookups for relationship label gathering."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.labelset = LabelSet.objects.create(
            title="Test LabelSet", creator=self.user
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            label_set=self.labelset,
            creator=self.user,
        )

    def test_analyses_only_with_no_analysis_ids(self):
        """Test ANALYSES_ONLY mode with analysis_ids=None returns empty."""
        result = build_label_lookups(
            corpus_id=self.corpus.id,
            analysis_ids=None,
            annotation_filter_mode="ANALYSES_ONLY",
        )

        # Should return empty lookups since no analyses specified
        self.assertEqual(result["text_labels"], {})
        self.assertEqual(result["doc_labels"], {})

    def test_corpus_labelset_plus_analyses_with_no_analysis_ids(self):
        """Test CORPUS_LABELSET_PLUS_ANALYSES mode with no analysis_ids."""
        # Create a label and annotation in the corpus
        label = AnnotationLabel.objects.create(
            text="CorpusLabel",
            label_type=TOKEN_LABEL,
            creator=self.user,
        )
        self.labelset.annotation_labels.add(label)

        doc = Document.objects.create(title="Test Doc", creator=self.user, page_count=1)
        Annotation.objects.create(
            document=doc,
            corpus=self.corpus,
            annotation_label=label,
            raw_text="test",
            creator=self.user,
        )

        result = build_label_lookups(
            corpus_id=self.corpus.id,
            analysis_ids=None,
            annotation_filter_mode="CORPUS_LABELSET_PLUS_ANALYSES",
        )

        # Should include corpus labels only (no analyses to add)
        self.assertGreater(len(result["text_labels"]), 0)


class TestDocumentPathExportFallback(TransactionTestCase):
    """Test package_document_paths fallback when doc has pdf_file but no hash."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.labelset = LabelSet.objects.create(
            title="Test LabelSet", creator=self.user
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            label_set=self.labelset,
            creator=self.user,
        )

    def test_document_ref_uses_filename_when_no_hash(self):
        """Test document_ref falls back to filename when hash is missing."""
        doc = Document.objects.create(
            title="No Hash Doc",
            pdf_file=ContentFile(b"dummy content", name="my_document.pdf"),
            pdf_file_hash="",  # Empty hash
            creator=self.user,
            page_count=1,
        )

        DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            path="/docs/my_document.pdf",
            version_number=1,
            creator=self.user,
        )

        result = package_document_paths(self.corpus)

        self.assertEqual(len(result), 1)
        # Should fall back to the pdf_file basename.  Django's storage
        # backend appends a random suffix on collision (e.g.
        # ``my_document_WjIl9b4.pdf``), so match on the stem + extension
        # rather than the original filename verbatim.
        doc_ref = result[0]["document_ref"]
        self.assertTrue(doc_ref.startswith("my_document"))
        self.assertTrue(doc_ref.endswith(".pdf"))


class TestConversationImportDocHashRelinking(TransactionTestCase):
    """Test import_conversations with document hash re-linking."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass", email="test@test.com"
        )
        self.labelset = LabelSet.objects.create(
            title="Test LabelSet", creator=self.user
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            label_set=self.labelset,
            creator=self.user,
        )

        self.doc = Document.objects.create(
            title="Target Doc",
            pdf_file_hash="doc_hash_xyz",
            creator=self.user,
            page_count=1,
        )

    def test_doc_level_conversation_relinked_via_hash(self):
        """Test that doc-level conversations are re-linked using doc hash."""
        conversations_data = [
            {
                "id": "conv_doc",
                "title": "Doc-level Conversation",
                "conversation_type": "chat",
                "is_public": False,
                "chat_with_corpus": False,
                "chat_with_document_hash": "doc_hash_xyz",
                "creator_email": self.user.email,
                "created": timezone.now().isoformat(),
                "modified": timezone.now().isoformat(),
            }
        ]

        doc_hash_map = {"doc_hash_xyz": self.doc}

        import_conversations(
            conversations_data,
            [],
            [],
            self.corpus,
            self.user,
            doc_hash_to_doc=doc_hash_map,
        )

        conv = Conversation.objects.filter(title="Doc-level Conversation").first()
        self.assertIsNotNone(conv)
        self.assertEqual(conv.chat_with_document, self.doc)
        self.assertIsNone(conv.chat_with_corpus)


# Minimal valid PDF used by the multi-roundtrip fixture.  Defined at module
# scope so both setUp and helper methods can read it without re-typing the
# byte literal.
_MINIMAL_PDF_BYTES = (
    b"%PDF-1.4\n"
    b"1 0 obj <</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj <</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
    b"3 0 obj <</Type/Page/Parent 2 0 R/Resources<<>>/MediaBox[0 0 612 792]>>endobj\n"
    b"xref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000056 00000 n\n"
    b"0000000115 00000 n\ntrailer <</Size 4/Root 1 0 R>>\nstartxref\n204\n%%EOF\n"
)


class TestV2ThreeRoundTripDataIntegrity(TransactionTestCase):
    """
    Three-time export/import roundtrip with no data loss for in-scope features.

    Per docs/architecture/corpus_export_import_v2.md, every V2 feature except
    the documented exceptions (vector embeddings, ingestion-source credentials,
    per-object permissions, historical DocumentPath versions, action-trail
    import) must survive an unlimited number of export→import roundtrips
    without drift.  This test exercises 3 sequential roundtrips and asserts
    that a normalized snapshot of the corpus is identical at every stage.
    """

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="rtuser",
            password="testpass",
            email="rtuser@example.com",
        )

        # ----- Labels & label set ---------------------------------------
        self.labelset = LabelSet.objects.create(
            title="Roundtrip LabelSet",
            description="LabelSet for 3x roundtrip integrity test",
            creator=self.user,
        )

        self.token_label = AnnotationLabel.objects.create(
            text="RT Token Label",
            description="A token label",
            color="#abcdef",
            label_type=TOKEN_LABEL,
            creator=self.user,
        )
        self.span_label = AnnotationLabel.objects.create(
            text="RT Span Label",
            description="A span label",
            color="#fedcba",
            label_type=SPAN_LABEL,
            creator=self.user,
        )
        self.doc_label = AnnotationLabel.objects.create(
            text="RT Doc Label",
            description="A doc-type label",
            color="#112233",
            label_type=DOC_TYPE_LABEL,
            creator=self.user,
        )
        self.rel_label = AnnotationLabel.objects.create(
            text="RT Rel Label",
            description="A relationship label",
            color="#445566",
            label_type=RELATIONSHIP_LABEL,
            creator=self.user,
        )
        self.labelset.annotation_labels.add(
            self.token_label, self.span_label, self.doc_label, self.rel_label
        )

        # ----- Corpus ---------------------------------------------------
        self.corpus = Corpus.objects.create(
            title="Roundtrip Corpus",
            description="Rich fixture for 3x roundtrip integrity test",
            label_set=self.labelset,
            creator=self.user,
            corpus_agent_instructions="Corpus-level instructions for RT",
            document_agent_instructions="Document-level instructions for RT",
            post_processors=["pp.one", "pp.two"],
            allow_comments=True,
        )
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.ALL])

        # ----- Folder hierarchy: root → child ----------------------------
        self.root_folder = CorpusFolder.objects.create(
            corpus=self.corpus,
            name="Root",
            description="root folder",
            color="#aa0000",
            icon="folder",
            tags=["root", "rt"],
            creator=self.user,
        )
        self.child_folder = CorpusFolder.objects.create(
            corpus=self.corpus,
            name="Child",
            description="child folder",
            color="#00aa00",
            icon="folder",
            tags=["child"],
            parent=self.root_folder,
            creator=self.user,
        )

        # ----- Structural annotation set shared across two documents ----
        pawls_payload = [
            {
                "page": {"index": 0, "width": 612, "height": 792},
                "tokens": [
                    {"x": 10, "y": 10, "width": 50, "height": 12, "text": "Hello"},
                    {"x": 70, "y": 10, "width": 50, "height": 12, "text": "World"},
                ],
            }
        ]
        self.struct_set = StructuralAnnotationSet.objects.create(
            content_hash="rt_struct_hash",
            parser_name="docling",
            parser_version="9.9",
            page_count=1,
            token_count=2,
            pawls_parse_file=ContentFile(
                json.dumps(pawls_payload).encode("utf-8"),
                name="pawls.json",
            ),
            txt_extract_file=ContentFile(
                b"Hello World extracted text", name="text.txt"
            ),
            creator=self.user,
        )
        # Parent + child structural annotation (covers parent_id linkage)
        self.struct_parent = Annotation.objects.create(
            structural_set=self.struct_set,
            annotation_label=self.token_label,
            raw_text="Hello",
            page=0,
            json={
                "0": {
                    "bounds": {"left": 10, "top": 10, "right": 60, "bottom": 22},
                    "tokensJsons": [{"pageIndex": 0, "tokenIndex": 0}],
                    "rawText": "Hello",
                }
            },
            annotation_type="header",
            structural=True,
            long_description="Top-of-doc heading",
            creator=self.user,
        )
        self.struct_child = Annotation.objects.create(
            structural_set=self.struct_set,
            annotation_label=self.token_label,
            raw_text="World",
            page=0,
            json={
                "0": {
                    "bounds": {"left": 70, "top": 10, "right": 120, "bottom": 22},
                    "tokensJsons": [{"pageIndex": 0, "tokenIndex": 1}],
                    "rawText": "World",
                }
            },
            annotation_type="paragraph",
            structural=True,
            parent=self.struct_parent,
            creator=self.user,
        )
        # Structural relationship between the two
        struct_rel = Relationship.objects.create(
            structural_set=self.struct_set,
            relationship_label=self.rel_label,
            structural=True,
            creator=self.user,
        )
        struct_rel.source_annotations.set([self.struct_parent.id])
        struct_rel.target_annotations.set([self.struct_child.id])

        # ----- Ingestion source -----------------------------------------
        # IngestionSource uses non-standard permission codenames
        # (create_/read_/update_/remove_ instead of permission_ingestionsource);
        # the importer doesn't grant guardian perms either, so skip manual
        # set_permissions_for_obj_to_user here — visibility flows through
        # the (creator, name) uniqueness used by _import_ingestion_sources.
        self.ingestion_source = IngestionSource.objects.create(
            name="rt_crawler",
            source_type="crawler",
            config={"endpoint": "https://example.invalid/feed"},
            active=True,
            creator=self.user,
        )

        # ----- Two documents, both sharing the structural set ----------
        self.doc_a = Document.objects.create(
            title="Doc A",
            description="First doc",
            pdf_file=ContentFile(_MINIMAL_PDF_BYTES, name="doc_a.pdf"),
            pdf_file_hash="rt_doc_a_hash",
            file_type="application/pdf",
            page_count=1,
            structural_annotation_set=self.struct_set,
            creator=self.user,
        )
        self.doc_b = Document.objects.create(
            title="Doc B",
            description="Second doc",
            pdf_file=ContentFile(_MINIMAL_PDF_BYTES, name="doc_b.pdf"),
            pdf_file_hash="rt_doc_b_hash",
            file_type="application/pdf",
            page_count=1,
            structural_annotation_set=self.struct_set,
            creator=self.user,
        )
        set_permissions_for_obj_to_user(self.user, self.doc_a, [PermissionTypes.ALL])
        set_permissions_for_obj_to_user(self.user, self.doc_b, [PermissionTypes.ALL])

        # ----- DocumentPaths --------------------------------------------
        DocumentPath.objects.create(
            document=self.doc_a,
            corpus=self.corpus,
            folder=self.root_folder,
            path="/documents/doc_a.pdf",
            version_number=1,
            ingestion_source=self.ingestion_source,
            external_id="ext-A-1",
            ingestion_metadata={"source_run": "abc123"},
            creator=self.user,
        )
        DocumentPath.objects.create(
            document=self.doc_b,
            corpus=self.corpus,
            folder=self.child_folder,
            path="/documents/doc_b.pdf",
            version_number=1,
            creator=self.user,
        )

        # ----- User annotations -----------------------------------------
        # Token annotation on doc A
        self.annot_a_tok = Annotation.objects.create(
            document=self.doc_a,
            corpus=self.corpus,
            annotation_label=self.token_label,
            raw_text="Doc A first annotation",
            page=0,
            json={
                "0": {
                    "bounds": {"left": 10, "top": 30, "right": 100, "bottom": 42},
                    "tokensJsons": [{"pageIndex": 0, "tokenIndex": 0}],
                    "rawText": "Doc A first annotation",
                }
            },
            annotation_type="paragraph",
            creator=self.user,
        )
        # Span annotation on doc A
        self.annot_a_span = Annotation.objects.create(
            document=self.doc_a,
            corpus=self.corpus,
            annotation_label=self.span_label,
            raw_text="A span on doc A",
            page=0,
            json={"start": 0, "end": 14},
            annotation_type="span",
            creator=self.user,
        )
        # Token annotation on doc B (with content_modalities & long_description)
        self.annot_b_tok = Annotation.objects.create(
            document=self.doc_b,
            corpus=self.corpus,
            annotation_label=self.token_label,
            raw_text="Doc B annotation",
            page=0,
            json={
                "0": {
                    "bounds": {"left": 20, "top": 50, "right": 200, "bottom": 62},
                    "tokensJsons": [{"pageIndex": 0, "tokenIndex": 0}],
                    "rawText": "Doc B annotation",
                }
            },
            annotation_type="paragraph",
            content_modalities=["TEXT"],
            long_description="Long-form analysis of the doc B clause",
            creator=self.user,
        )
        # Child annotation parented to annot_b_tok — exercises parent_id
        # remapping during import (non-structural path).
        self.annot_b_child = Annotation.objects.create(
            document=self.doc_b,
            corpus=self.corpus,
            annotation_label=self.token_label,
            raw_text="Doc B child clause",
            page=0,
            json={
                "0": {
                    "bounds": {"left": 220, "top": 50, "right": 280, "bottom": 62},
                    "tokensJsons": [{"pageIndex": 0, "tokenIndex": 1}],
                    "rawText": "Doc B child clause",
                }
            },
            annotation_type="paragraph",
            parent=self.annot_b_tok,
            creator=self.user,
        )
        # Doc-type annotation on doc A
        self.annot_a_doctype = Annotation.objects.create(
            document=self.doc_a,
            corpus=self.corpus,
            annotation_label=self.doc_label,
            annotation_type=DOC_TYPE_LABEL,
            creator=self.user,
        )

        # ----- Cross-document relationship (corpus-level) ---------------
        # Source on doc A's token annotation, target on doc B's token annotation.
        # Per package_relationships(), the relationship is filtered by either
        # document_id__in (any document in corpus) OR corpus=corpus.
        self.cross_rel = Relationship.objects.create(
            corpus=self.corpus,
            document=self.doc_a,
            relationship_label=self.rel_label,
            structural=False,
            creator=self.user,
        )
        self.cross_rel.source_annotations.set([self.annot_a_tok.id])
        self.cross_rel.target_annotations.set([self.annot_b_tok.id])

        # ----- Markdown description & revisions -------------------------
        self.md_text = (
            "# Roundtrip Corpus\n\nA test corpus for export round-tripping.\n"
        )
        self.corpus.md_description.save(
            "description.md", ContentFile(self.md_text.encode("utf-8"))
        )
        CorpusDescriptionRevision.objects.create(
            corpus=self.corpus,
            author=self.user,
            version=1,
            diff="Initial markdown description",
            snapshot=self.md_text,
            checksum_base="",
            checksum_full="rev-1-checksum",
        )
        CorpusDescriptionRevision.objects.create(
            corpus=self.corpus,
            author=self.user,
            version=2,
            diff="Minor edit",
            snapshot=self.md_text,
            checksum_base="rev-1-checksum",
            checksum_full="rev-2-checksum",
        )

        # ----- Conversations, messages, votes ---------------------------
        # Distinct historical timestamps so we can verify the importer's
        # explicit .update() bypass of auto_now_add preserves them across
        # roundtrips.
        self._conv_ts_corpus = datetime(2024, 1, 2, 3, 4, 5, tzinfo=tz.utc)
        self._conv_ts_doc = datetime(2024, 1, 3, 8, 30, 15, tzinfo=tz.utc)
        self._msg_ts_parent = datetime(2024, 1, 2, 3, 5, 0, tzinfo=tz.utc)
        self._msg_ts_child = datetime(2024, 1, 2, 3, 6, 30, tzinfo=tz.utc)
        self._msg_ts_doc = datetime(2024, 1, 3, 9, 0, 0, tzinfo=tz.utc)
        self._vote_ts = datetime(2024, 1, 2, 3, 7, 45, tzinfo=tz.utc)

        self.corpus_conv = Conversation.objects.create(
            chat_with_corpus=self.corpus,
            title="Corpus chat",
            description="A corpus-level conversation",
            conversation_type="chat",
            is_public=True,
            is_locked=False,
            is_pinned=True,
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, self.corpus_conv, [PermissionTypes.ALL]
        )
        self.doc_conv = Conversation.objects.create(
            chat_with_document=self.doc_a,
            title="Doc A chat",
            description="A doc-level conversation",
            conversation_type="chat",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(self.user, self.doc_conv, [PermissionTypes.ALL])

        self.msg_parent = ChatMessage.objects.create(
            conversation=self.corpus_conv,
            content="Hello, corpus assistant",
            msg_type="HUMAN",
            state="completed",
            data={"meta": "user msg"},
            creator=self.user,
        )
        self.msg_child = ChatMessage.objects.create(
            conversation=self.corpus_conv,
            content="Hi, here's a reply",
            msg_type="LLM",
            state="completed",
            parent_message=self.msg_parent,
            data={"meta": "llm msg"},
            creator=self.user,
        )
        self.doc_msg = ChatMessage.objects.create(
            conversation=self.doc_conv,
            content="What's in doc A?",
            msg_type="HUMAN",
            state="completed",
            creator=self.user,
        )
        MessageVote.objects.create(
            message=self.msg_child, vote_type="upvote", creator=self.user
        )

        # Patch auto_now_add / auto_now timestamps so the snapshot can
        # verify the importer preserves these across roundtrips.  Use
        # ``.update()`` because auto_now_add ignores .save() updates.
        Conversation.all_objects.filter(pk=self.corpus_conv.pk).update(
            created_at=self._conv_ts_corpus, updated_at=self._conv_ts_corpus
        )
        Conversation.all_objects.filter(pk=self.doc_conv.pk).update(
            created_at=self._conv_ts_doc, updated_at=self._conv_ts_doc
        )
        ChatMessage.all_objects.filter(pk=self.msg_parent.pk).update(
            created_at=self._msg_ts_parent
        )
        ChatMessage.all_objects.filter(pk=self.msg_child.pk).update(
            created_at=self._msg_ts_child
        )
        ChatMessage.all_objects.filter(pk=self.doc_msg.pk).update(
            created_at=self._msg_ts_doc
        )
        MessageVote.objects.filter(message=self.msg_child).update(
            created_at=self._vote_ts
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _snapshot(self, corpus: Corpus) -> dict:
        """
        Build a normalized snapshot of a corpus that should be identical
        across export-import roundtrips for in-scope features.  IDs are
        deliberately excluded — they change every import.  Counts and
        content-based keys are used instead.
        """
        # Active corpus-isolated documents via DocumentPath
        active_paths = list(
            DocumentPath.objects.filter(
                corpus=corpus, is_current=True, is_deleted=False
            ).select_related("document", "folder", "ingestion_source")
        )
        # Map document → its current active path
        active_docs = [p.document for p in active_paths]

        # Annotations: keyed by (doc_title, label_text, label_type, raw_text,
        # annotation_type) so we can compare without depending on IDs.
        # We additionally roll up per-key json/long_description/modalities so
        # any drift in those fields shows up as a snapshot diff.
        annotations_summary: dict[tuple, dict] = {}
        # parent_pairs records (child raw_text, parent raw_text) for all
        # non-structural annotations.  Independent of IDs.
        user_annot_parent_pairs: list[tuple[str, str | None]] = []
        for doc in active_docs:
            qs = Annotation.objects.filter(
                document=doc, corpus=corpus, structural=False
            ).select_related("annotation_label", "parent")
            for annot in qs:
                key = (
                    doc.title,
                    annot.annotation_label.text if annot.annotation_label else "",
                    (
                        annot.annotation_label.label_type
                        if annot.annotation_label
                        else ""
                    ),
                    annot.raw_text or "",
                    annot.annotation_type or "",
                )
                entry = annotations_summary.setdefault(
                    key,
                    {
                        "count": 0,
                        "long_descriptions": [],
                        "content_modalities": [],
                        "json_blobs": [],
                    },
                )
                entry["count"] += 1
                entry["long_descriptions"].append(annot.long_description or "")
                entry["content_modalities"].append(
                    sorted(annot.content_modalities or [])
                )
                # Normalize JSON via the compact format used at export
                # time.  ``compact_annotation_json`` is idempotent (already
                # compact / span data passes through unchanged), so this
                # collapses pre-export v1 dicts and post-import v2 dicts
                # to a single canonical representation without losing
                # information.
                entry["json_blobs"].append(
                    json.dumps(
                        compact_annotation_json(annot.json) or {},
                        sort_keys=True,
                        default=str,
                    )
                )
                user_annot_parent_pairs.append(
                    (
                        annot.raw_text or "",
                        annot.parent.raw_text if annot.parent else None,
                    )
                )
        # Normalize for stable comparison
        for entry in annotations_summary.values():
            entry["long_descriptions"].sort()
            entry["content_modalities"].sort()
            entry["json_blobs"].sort()
        user_annot_parent_pairs.sort()

        # Structural annotation set – we expect exactly the shared one,
        # deduped by content_hash.  Count structural annotations / rels.
        struct_set_hashes = sorted(
            {
                d.structural_annotation_set.content_hash
                for d in active_docs
                if d.structural_annotation_set
            }
        )
        struct_summary: dict[str, dict] = {}
        for h in struct_set_hashes:
            # The set with this hash is shared; pick any.
            s = StructuralAnnotationSet.objects.filter(content_hash=h).first()
            if not s:
                continue
            struct_annotations = list(
                Annotation.objects.filter(structural_set=s).select_related(
                    "annotation_label"
                )
            )
            struct_relationships = list(Relationship.objects.filter(structural_set=s))
            # Capture parent relationships by raw_text pairs to avoid IDs
            parent_pairs = sorted(
                [
                    (a.raw_text, a.parent.raw_text if a.parent else None)
                    for a in struct_annotations
                ]
            )
            # Inspect the actual stored files (pawls + txt) to assert the
            # parsing payload itself is preserved.
            pawls_content = ""
            if s.pawls_parse_file and s.pawls_parse_file.name:
                with s.pawls_parse_file.open("r") as f:
                    pawls_content = f.read()
            txt_content = ""
            if s.txt_extract_file and s.txt_extract_file.name:
                with s.txt_extract_file.open("r") as f:
                    txt_content = f.read()

            struct_summary[h] = {
                "parser_name": s.parser_name,
                "parser_version": s.parser_version,
                "page_count": s.page_count,
                "token_count": s.token_count,
                "annotation_count": len(struct_annotations),
                "annotation_raw_texts": sorted(
                    a.raw_text or "" for a in struct_annotations
                ),
                "annotation_types": sorted(
                    a.annotation_type or "" for a in struct_annotations
                ),
                "annotation_long_descriptions": sorted(
                    a.long_description or "" for a in struct_annotations
                ),
                "annotation_labels": sorted(
                    a.annotation_label.text if a.annotation_label else ""
                    for a in struct_annotations
                ),
                # Normalize structural annotation JSON to compact form so
                # baseline (which uses v1 multipage dict) and post-roundtrip
                # state (which is stored compact) compare equal.
                "annotation_json_blobs": sorted(
                    json.dumps(
                        compact_annotation_json(a.json) or {},
                        sort_keys=True,
                        default=str,
                    )
                    for a in struct_annotations
                ),
                "parent_pairs": parent_pairs,
                "relationship_count": len(struct_relationships),
                "pawls_normalized": pawls_content,
                "txt_content": txt_content,
            }

        # Folders normalized by path
        folders = list(
            CorpusFolder.objects.filter(corpus=corpus).select_related("parent")
        )
        folder_summary = sorted(
            (
                f.get_path(),
                f.name,
                f.description,
                f.color,
                f.icon,
                tuple(f.tags or []),
            )
            for f in folders
        )

        # DocumentPaths by (doc_title, path, folder_path, version_number)
        path_summary = sorted(
            (
                p.document.title,
                p.path,
                p.folder.get_path() if p.folder else None,
                p.version_number,
                p.ingestion_source.name if p.ingestion_source else None,
                p.external_id or "",
                tuple(sorted((p.ingestion_metadata or {}).items())),
            )
            for p in active_paths
        )

        # Relationships (corpus-level / non-structural)
        # Reconstruct source/target by raw_text + doc_title to avoid IDs.
        non_struct_rels = (
            Relationship.objects.filter(corpus=corpus, structural=False)
            .select_related("relationship_label")
            .order_by("id")
        )
        relationship_summary = []
        for rel in non_struct_rels:
            src = sorted(
                (
                    a.document.title,
                    a.raw_text or "",
                    a.annotation_label.text if a.annotation_label else "",
                )
                for a in rel.source_annotations.select_related(
                    "document", "annotation_label"
                ).all()
            )
            tgt = sorted(
                (
                    a.document.title,
                    a.raw_text or "",
                    a.annotation_label.text if a.annotation_label else "",
                )
                for a in rel.target_annotations.select_related(
                    "document", "annotation_label"
                ).all()
            )
            relationship_summary.append(
                {
                    "label": (
                        rel.relationship_label.text if rel.relationship_label else ""
                    ),
                    "structural": rel.structural,
                    "sources": src,
                    "targets": tgt,
                }
            )

        # Markdown description content
        md_content = ""
        if corpus.md_description and corpus.md_description.name:
            with corpus.md_description.open("r") as f:
                md_content = f.read()

        revisions = list(
            CorpusDescriptionRevision.objects.filter(corpus=corpus).order_by("version")
        )
        revision_summary = [
            {
                "version": r.version,
                "diff": r.diff,
                "snapshot": r.snapshot,
                "checksum_base": r.checksum_base,
                "checksum_full": r.checksum_full,
            }
            for r in revisions
        ]

        # Conversations + messages + votes
        convs = list(
            Conversation.objects.filter(
                Q(chat_with_corpus=corpus) | Q(chat_with_document__in=active_docs)
            )
            .select_related("chat_with_document")
            .order_by("id")
        )
        conv_summary = []
        for c in convs:
            msgs = list(
                ChatMessage.objects.filter(conversation=c).order_by("created_at")
            )
            msg_summary = [
                {
                    "content": m.content or "",
                    "msg_type": m.msg_type,
                    "state": m.state,
                    "data": m.data,
                    "parent_content": (
                        m.parent_message.content if m.parent_message else None
                    ),
                    "created_at": m.created_at.isoformat(),
                    "vote_types": sorted(
                        (v.vote_type, v.created_at.isoformat())
                        for v in MessageVote.objects.filter(message=m)
                    ),
                }
                for m in msgs
            ]
            conv_summary.append(
                {
                    "title": c.title or "",
                    "description": c.description or "",
                    "conversation_type": c.conversation_type or "chat",
                    "is_public": c.is_public,
                    "is_locked": c.is_locked,
                    "is_pinned": c.is_pinned,
                    "chat_with_corpus": c.chat_with_corpus_id == corpus.id,
                    "chat_with_document_title": (
                        c.chat_with_document.title if c.chat_with_document else None
                    ),
                    "created_at": c.created_at.isoformat(),
                    "updated_at": c.updated_at.isoformat(),
                    "messages": msg_summary,
                }
            )
        # Sort by title to make order stable across imports
        conv_summary.sort(key=lambda c: (c["title"], c["chat_with_corpus"]))

        # Ingestion sources used by any active path
        used_source_names = sorted(
            {p.ingestion_source.name for p in active_paths if p.ingestion_source}
        )

        # Labelset / labels reduced to text+type pairs (IDs change)
        label_pairs = sorted(
            (
                label.text,
                label.label_type,
            )
            for label in corpus.label_set.annotation_labels.all().distinct()
        )

        return {
            "corpus": {
                "title": corpus.title,
                "description": corpus.description,
                "corpus_agent_instructions": corpus.corpus_agent_instructions,
                "document_agent_instructions": corpus.document_agent_instructions,
                "post_processors": list(corpus.post_processors or []),
                "allow_comments": corpus.allow_comments,
            },
            "labelset_title": corpus.label_set.title,
            "labelset_description": corpus.label_set.description,
            "labels": label_pairs,
            "doc_titles": sorted(d.title or "" for d in active_docs),
            "doc_hashes": sorted(d.pdf_file_hash or "" for d in active_docs),
            "doc_file_types": sorted(d.file_type or "" for d in active_docs),
            "doc_descriptions": sorted(d.description or "" for d in active_docs),
            "active_doc_count": len(active_docs),
            "annotations_summary": dict(sorted(annotations_summary.items())),
            "user_annot_parent_pairs": user_annot_parent_pairs,
            "struct_summary": struct_summary,
            "folders": sorted(folder_summary),
            "paths": path_summary,
            "relationships": relationship_summary,
            "md_description": md_content,
            "revisions": revision_summary,
            "conversations": conv_summary,
            "ingestion_sources": used_source_names,
        }

    def _roundtrip(self, corpus: Corpus) -> Corpus:
        """Export `corpus` to a V2 ZIP and import it into a new corpus.

        Returns the newly imported Corpus.
        """
        export = UserExport.objects.create(backend_lock=True, creator=self.user)
        package_corpus_export_v2(
            export_id=export.id,
            corpus_pk=corpus.id,
            include_conversations=True,
        )
        export.refresh_from_db()
        self.assertIsNotNone(export.file, "Export should have produced a file")

        # Hand the ZIP off to the importer via a fresh TemporaryFileHandle
        temp_file = TemporaryFileHandle.objects.create()
        with export.file.open("rb") as f:
            temp_file.file.save("rt.zip", ContentFile(f.read()))

        imported_id = import_corpus_v2(
            temporary_file_handle_id=temp_file.id,
            user_id=self.user.id,
            seed_corpus_id=None,
        )
        self.assertIsNotNone(imported_id, "Importer returned None — import failed")
        return Corpus.objects.get(id=imported_id)

    # ------------------------------------------------------------------ #
    # Test
    # ------------------------------------------------------------------ #

    def test_three_roundtrips_preserve_in_scope_state(self) -> None:
        """Export+import 3 times; in-scope state should be identical at each stage."""
        baseline = self._snapshot(self.corpus)

        round1 = self._roundtrip(self.corpus)
        snap1 = self._snapshot(round1)

        round2 = self._roundtrip(round1)
        snap2 = self._snapshot(round2)

        round3 = self._roundtrip(round2)
        snap3 = self._snapshot(round3)

        # Each top-level slice is compared individually so any drift
        # produces a focused failure rather than one giant dict diff.
        for key in baseline.keys():
            self.assertEqual(
                snap1[key],
                baseline[key],
                msg=f"Round 1 lost data in '{key}'",
            )
            self.assertEqual(
                snap2[key],
                baseline[key],
                msg=f"Round 2 lost data in '{key}'",
            )
            self.assertEqual(
                snap3[key],
                baseline[key],
                msg=f"Round 3 lost data in '{key}'",
            )

        # Structural annotation set should remain a SINGLE row across all
        # roundtrips — dedup by content_hash is the headline V2 invariant.
        self.assertEqual(
            StructuralAnnotationSet.objects.filter(
                content_hash="rt_struct_hash"
            ).count(),
            1,
            msg="StructuralAnnotationSet duplicated across roundtrips — "
            "content_hash dedup broke",
        )
