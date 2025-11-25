"""
Comprehensive tests for V2 corpus export/import functionality.

Tests cover:
- Individual export utilities for V2 components
- Individual import utilities for V2 components
- Full V2 round-trip export/import
- V1 backward compatibility
- Edge cases and data integrity
"""

import json
import pathlib
import zipfile
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TransactionTestCase
from django.utils import timezone

from opencontractserver.annotations.models import (
    DOC_TYPE_LABEL,
    RELATIONSHIP_LABEL,
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
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.tasks.export_tasks_v2 import package_corpus_export_v2
from opencontractserver.tasks.import_tasks_v2 import import_corpus_v2
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.users.models import UserExport
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
    import_document_paths,
    import_md_description_revisions,
    import_relationships,
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

        label_lookup = {"Test Label": self.text_label}

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

    def test_import_document_paths(self):
        """Test importing DocumentPath version trees."""
        # Create documents
        doc1 = Document.objects.create(
            title="Test Doc 1",
            pdf_file_hash="doc_hash_1",
            creator=self.user,
            page_count=1,
        )
        doc2 = Document.objects.create(
            title="Test Doc 2",
            pdf_file_hash="doc_hash_2",
            creator=self.user,
            page_count=1,
        )

        # Create folder
        folder = CorpusFolder.objects.create(
            corpus=self.corpus, name="Test Folder", creator=self.user
        )

        # Create paths data
        paths_data = [
            {
                "document_ref": "doc_hash_1",
                "folder_path": "Test Folder",
                "path": "/documents/test1.pdf",
                "version_number": 1,
                "parent_version_number": None,
                "is_current": True,
                "is_deleted": False,
                "created": timezone.now().isoformat(),
            },
            {
                "document_ref": "doc_hash_2",
                "folder_path": None,
                "path": "/documents/test2.pdf",
                "version_number": 1,
                "parent_version_number": None,
                "is_current": True,
                "is_deleted": False,
                "created": timezone.now().isoformat(),
            },
        ]

        # Create document map and folder map
        document_map = {"doc_hash_1": doc1, "doc_hash_2": doc2}
        folder_map = {"Test Folder": folder}

        # Import
        import_document_paths(
            paths_data, self.corpus, document_map, folder_map, self.user
        )

        # Verify
        paths = DocumentPath.objects.filter(corpus=self.corpus)
        self.assertEqual(paths.count(), 2)

        path1 = DocumentPath.objects.get(document=doc1, corpus=self.corpus)
        self.assertEqual(path1.folder, folder)
        self.assertTrue(path1.is_current)

        path2 = DocumentPath.objects.get(document=doc2, corpus=self.corpus)
        self.assertIsNone(path2.folder)
        self.assertTrue(path2.is_current)

    def test_import_relationships(self):
        """Test importing relationships."""
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
        label_lookup = {"Relates To": rel_label}
        document_map = {}

        # Import
        import_relationships(
            relationships_data,
            self.corpus,
            document_map,
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

        label_lookup = {"Test Label": self.text_label}

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
        label_lookup = {"Structural Rel": rel_label}
        document_map = {}

        # Import
        import_relationships(
            relationships_data,
            self.corpus,
            document_map,
            annot_id_map,
            label_lookup,
            self.user,
        )

        # Verify NO relationship was created (structural ones are skipped)
        relationships = Relationship.objects.filter(corpus=self.corpus)
        self.assertEqual(relationships.count(), 0)

    def test_import_document_paths_edge_cases(self):
        """Test document path import with missing folder/document references."""
        # Create a folder
        folder = CorpusFolder.objects.create(
            name="Existing Folder", corpus=self.corpus, creator=self.user
        )
        folder_path = folder.get_path()

        # Create one document but not all referenced documents
        doc = Document.objects.create(
            title="Existing Doc",
            creator=self.user,
            page_count=1,
            pdf_file_hash="abc123",
        )

        folder_map = {folder_path: folder}
        document_map = {
            "abc123": doc,
            # "xyz789" intentionally missing
        }

        # Paths data with edge cases
        paths_data = [
            {
                "path": "/existing/doc.pdf",
                "version_number": 1,
                "document_ref": "abc123",  # exists
                "folder_path": folder_path,  # exists
                "is_current": True,
                "is_deleted": False,
            },
            {
                "path": "/missing_folder/doc.pdf",
                "version_number": 1,
                "document_ref": "abc123",  # exists
                # No folder_path - should use None
                "is_current": True,
                "is_deleted": False,
            },
            {
                "path": "/missing_doc.pdf",
                "version_number": 1,
                "document_ref": "xyz789",  # MISSING - should skip
                "is_current": True,
                "is_deleted": False,
            },
        ]

        # Import
        import_document_paths(
            paths_data, self.corpus, document_map, folder_map, self.user
        )

        # Verify paths created
        paths = DocumentPath.objects.filter(corpus=self.corpus)

        # Should have 2 paths (one with existing folder, one with None folder)
        # The third one with missing document should be skipped
        self.assertEqual(paths.count(), 2)

        # Check first path has folder
        path1 = paths.get(path="/existing/doc.pdf")
        self.assertEqual(path1.folder, folder)

        # Check second path has None folder (missing folder reference)
        path2 = paths.get(path="/missing_folder/doc.pdf")
        self.assertIsNone(path2.folder)

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

        label_lookup = {"Test Label": self.text_label}
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

        label_lookup = {"Test Label": self.text_label, "Causes": rel_label}
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

        label_lookup = {"Test Label": self.text_label}  # Missing "NonexistentLabel"
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

        doc.pdf_file_hash = "test_doc_hash_123"
        doc.save()

        document_map = {doc.pdf_file_hash: doc}
        annot_id_map = {str(annot1.id): annot1.id, str(annot2.id): annot2.id}
        label_lookup = {"Test Label": self.text_label}  # Missing "NonexistentRelLabel"

        # Should not raise error, just log warning and skip
        import_relationships(
            relationships_data,
            self.corpus,
            document_map,
            annot_id_map,
            label_lookup,
            self.user,
        )

        # No relationships should be created
        relationships = Relationship.objects.filter(corpus=self.corpus)
        self.assertEqual(relationships.count(), 0)

    def test_import_document_paths_with_parent_version(self):
        """Test importing DocumentPath with parent version reference."""
        # Create two versions of the same document
        doc_v1 = Document.objects.create(
            title="Document V1",
            creator=self.user,
            pdf_file_hash="doc_hash_v1",
        )
        doc_v2 = Document.objects.create(
            title="Document V2",
            creator=self.user,
            pdf_file_hash="doc_hash_v2",
        )

        paths_data = [
            {
                "path": "/test/document.pdf",
                "document_ref": "doc_hash_v1",
                "version_number": 1,
                "parent_version_number": None,  # First version
                "is_current": False,
                "is_deleted": False,
            },
            {
                "path": "/test/document.pdf",
                "document_ref": "doc_hash_v2",
                "version_number": 2,
                "parent_version_number": 1,  # References version 1
                "is_current": True,
                "is_deleted": False,
            },
        ]

        document_map = {"doc_hash_v1": doc_v1, "doc_hash_v2": doc_v2}
        folder_map = {}

        import_document_paths(
            paths_data, self.corpus, document_map, folder_map, self.user
        )

        # Check both paths were created
        paths = DocumentPath.objects.filter(corpus=self.corpus).order_by(
            "version_number"
        )
        self.assertEqual(paths.count(), 2)

        path_v1 = paths[0]
        path_v2 = paths[1]

        # Check version 2 has version 1 as parent
        self.assertEqual(path_v2.parent_id, path_v1.id)
        self.assertIsNone(path_v1.parent_id)

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

        label_lookup = {"Test Label": self.text_label}  # Missing "MissingRelLabel"
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

    @mock.patch("opencontractserver.utils.import_v2.DocumentPath.objects.create")
    def test_import_document_paths_exception(self, mock_create):
        """Test import_document_paths exception handler (lines 327-328)."""
        from opencontractserver.utils.import_v2 import import_document_paths

        # Create a document
        doc = Document.objects.create(
            title="Test Doc",
            creator=self.user,
            page_count=1,
            pdf_file_hash="hash123",
        )

        # Force an exception when creating DocumentPath
        mock_create.side_effect = Exception("Database error")

        paths_data = [
            {
                "document_ref": "hash123",
                "folder_path": None,
                "path": "/test.pdf",
                "version_number": 1,
                "parent_version_number": None,
                "is_current": True,
                "is_deleted": False,
                "created": "2024-01-01T00:00:00Z",
            }
        ]

        document_map = {"hash123": doc}
        folder_map = {}

        # Should not raise exception - handles it gracefully
        import_document_paths(
            paths_data, self.corpus, document_map, folder_map, self.user
        )

    @mock.patch("opencontractserver.utils.import_v2.Relationship.objects.create")
    def test_import_relationships_exception(self, mock_create):
        """Test import_relationships exception handler (lines 394-395)."""
        from opencontractserver.utils.import_v2 import import_relationships

        # Create annotation for ID mapping
        doc = Document.objects.create(title="Test Doc", creator=self.user, page_count=1)
        annot = Annotation.objects.create(
            annotation_label=self.text_label,
            document=doc,
            corpus=self.corpus,
            creator=self.user,
        )

        # Force an exception when creating Relationship
        mock_create.side_effect = Exception("Database error")

        relationships_data = [
            {
                "id": "rel1",
                "relationshipLabel": "Test Label",
                "source_annotation_ids": ["old_id1"],
                "target_annotation_ids": ["old_id2"],
                "structural": False,
            }
        ]

        annot_id_map = {"old_id1": annot.id, "old_id2": annot.id}
        label_lookup = {"Test Label": self.text_label}

        # Should not raise exception - handles it gracefully
        import_relationships(
            relationships_data, self.corpus, {}, annot_id_map, label_lookup, self.user
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
