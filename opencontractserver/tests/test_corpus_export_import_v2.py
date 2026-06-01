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
from tempfile import SpooledTemporaryFile
from typing import cast
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.utils import timezone

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
    CorpusFolder,
    TemporaryFileHandle,
)
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.tasks.export_tasks_v2 import package_corpus_export_v2
from opencontractserver.tasks.import_tasks_v2 import (
    _build_folder_path_lookup,
    _import_v2_relationships,
    _reconstruct_document_paths,
    import_corpus_v2,
)
from opencontractserver.tests._corpus_fixture import build_rich_test_corpus
from opencontractserver.tests._corpus_snapshot import snapshot_corpus
from opencontractserver.types.dicts import (
    AgentConfigExport,
    CorpusFolderExport,
    DocumentPathExport,
    OpenContractsExportDataJsonV2Type,
    OpenContractsRelationshipPythonType,
    StructuralAnnotationSetExport,
)
from opencontractserver.types.enums import AnnotationFilterMode, PermissionTypes
from opencontractserver.users.models import UserExport
from opencontractserver.utils.etl import build_label_lookups
from opencontractserver.utils.export_v2 import (
    package_agent_config,
    package_conversations,
    package_corpus_folders,
    package_document_paths,
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


class TestV2ExportUtilities(TestCase):
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
        # Second annotation carries a ``link_url`` so the export-side
        # ``if annot.link_url: annot_data["link_url"] = ...`` branch in
        # ``package_structural_annotation_set`` is exercised. Without
        # this, the OC_URL passthrough silently drops on round-trip and
        # forked corpora lose their clickable targets.
        Annotation.objects.create(
            structural_set=struct_set,
            annotation_label=self.text_label,
            raw_text="Linked annotation",
            page=0,
            json={"0": {"bounds": {}, "tokensJsons": [], "rawText": "Linked"}},
            structural=True,
            creator=self.user,
            link_url="https://example.com/structural",
        )

        # Export
        result = package_structural_annotation_set(struct_set)

        # Verify
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["content_hash"], "test_hash_123")
        self.assertEqual(result["parser_name"], "docling")
        self.assertEqual(result["page_count"], 1)
        self.assertEqual(len(result["structural_annotations"]), 2)
        self.assertEqual(result["txt_content"], txt_content)
        # The link_url must round-trip on the OC_URL-bearing structural
        # annotation while the plain one is omitted entirely.
        link_urls = [a.get("link_url") for a in result["structural_annotations"]]
        self.assertIn("https://example.com/structural", link_urls)
        # Plain annotation must NOT have the key — absence vs explicit
        # None is the wire-format contract for importers.
        for annot in result["structural_annotations"]:
            if annot["rawText"] == "Test annotation":
                self.assertNotIn("link_url", annot)

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

    # NOTE: the legacy ``test_package_md_description_revisions`` was removed
    # alongside the ``package_md_description_revisions`` helper itself: under
    # the canonical-CAML refactor (export schema V3) the corpus description
    # rides in ``annotated_docs`` as the Readme.CAML Document, so there is no
    # longer a dedicated export path for the legacy field. V2 *import*
    # back-compat (synthesising a Readme.CAML Document from V2 archives) is
    # still covered by ``test_import_md_description_revisions`` below and by
    # the dedicated V2 round-trip cases.

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


class TestV2ImportUtilities(TestCase):
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
        result = import_structural_annotation_set(
            cast(StructuralAnnotationSetExport, struct_data), label_lookup, self.user
        )

        # Verify
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.content_hash, "import_hash_123")
        self.assertEqual(result.structural_annotations.count(), 1)

        # Test deduplication - importing same hash should return existing
        result2 = import_structural_annotation_set(
            cast(StructuralAnnotationSetExport, struct_data), label_lookup, self.user
        )
        assert result2 is not None
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
        result = import_corpus_folders(
            cast(list[CorpusFolderExport], folders_data), self.corpus, self.user
        )

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
        import_agent_config(cast(AgentConfigExport, config_data), self.corpus)

        # Verify
        self.corpus.refresh_from_db()
        self.assertEqual(
            self.corpus.corpus_agent_instructions, "Imported corpus instructions"
        )
        self.assertEqual(
            self.corpus.document_agent_instructions, "Imported document instructions"
        )

    def test_import_md_description_revisions(self):
        """V2 back-compat: md_description + revisions synthesize a Readme.CAML
        Document and version-tree siblings on import.

        Post-Task 14 the shim no longer touches the legacy
        ``corpus.md_description`` FileField / ``CorpusDescriptionRevision``
        rows — both were dropped in favor of the canonical CAML doc.
        """
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

        # Import (wrap in captureOnCommitCallbacks so the post_save signal
        # fires its on_commit cache refresh before we read back the cache).
        with self.captureOnCommitCallbacks(execute=True):
            import_md_description_revisions(
                md_description, revisions_data, self.corpus, self.user
            )

        # Readme.CAML head exists with the imported body.
        head_path = DocumentPath.objects.filter(
            corpus=self.corpus,
            path="Readme.CAML",
            is_current=True,
            is_deleted=False,
        ).first()
        self.assertIsNotNone(head_path)
        assert head_path is not None
        self.assertEqual(head_path.document.title, "Readme.CAML")
        self.assertEqual(head_path.document.file_type, "text/markdown")

        # Cache columns refreshed via post_save signal.
        self.corpus.refresh_from_db()
        self.assertEqual(
            self.corpus.description, "Imported Corpus\n\nImported content."
        )

        # Version-tree contains the head + the replayed revision sibling.
        tree_id = head_path.document.version_tree_id
        siblings = Document.objects.filter(version_tree_id=tree_id)
        self.assertEqual(siblings.count(), 2)

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
        annot_id_map: dict[str | int, int] = {
            str(annot1.id): annot1.id,
            str(annot2.id): annot2.id,
        }
        label_lookup = {("Relates To", RELATIONSHIP_LABEL): rel_label}

        # Import using _import_v2_relationships
        _import_v2_relationships(
            cast(list[OpenContractsRelationshipPythonType], relationships_data),
            self.corpus,
            annot_id_map,
            label_lookup,
            self.user,
        )

        # Verify
        relationships = Relationship.objects.filter(corpus=self.corpus)
        self.assertEqual(relationships.count(), 1)

        rel = relationships.first()
        assert rel is not None
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
        assert conv is not None
        self.assertEqual(conv.title, "Test Conversation")
        self.assertEqual(conv.conversation_type, "chat")

        # Verify messages
        messages = ChatMessage.objects.filter(conversation=conv)
        self.assertEqual(messages.count(), 1)

        msg = messages.first()
        assert msg is not None
        self.assertEqual(msg.content, "Test message")
        self.assertEqual(msg.msg_type, "HUMAN")

        # Verify votes
        votes = MessageVote.objects.filter(message=msg)
        self.assertEqual(votes.count(), 1)

        vote = votes.first()
        assert vote is not None
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
        result = import_structural_annotation_set(
            cast(StructuralAnnotationSetExport, struct_data), label_lookup, self.user
        )

        # Verify new structural set was created
        self.assertIsNotNone(result)
        assert result is not None
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

        annot_id_map: dict[str | int, int] = {
            str(annot1.id): annot1.id,
            str(annot2.id): annot2.id,
        }
        label_lookup = {("Structural Rel", RELATIONSHIP_LABEL): rel_label}

        # Import using _import_v2_relationships
        _import_v2_relationships(
            cast(list[OpenContractsRelationshipPythonType], relationships_data),
            self.corpus,
            annot_id_map,
            label_lookup,
            self.user,
        )

        # Verify NO relationship was created (structural ones are skipped)
        relationships = Relationship.objects.filter(corpus=self.corpus)
        self.assertEqual(relationships.count(), 0)

    def test_import_relationships_skip_when_endpoint_missing(self):
        """
        Regression guard: a relationship whose source/target annotation
        was not imported (e.g. because its document was excluded) must
        be silently dropped rather than raising or creating a dangling
        relationship.

        Replaces the equivalent assertion the old fork suite carried
        (``test_relationship_skipped_when_no_mapped_annotations``); fork
        now delegates this to the V2 importer.
        """
        doc = Document.objects.create(title="Test Doc", creator=self.user, page_count=1)
        annot1 = Annotation.objects.create(
            document=doc,
            corpus=self.corpus,
            annotation_label=self.text_label,
            raw_text="Source only",
            creator=self.user,
        )

        rel_label = AnnotationLabel.objects.create(
            text="Missing Endpoint Rel",
            description="Test rel with missing target",
            label_type=RELATIONSHIP_LABEL,
            creator=self.user,
        )

        # The id "missing_target_id" deliberately is not in the
        # ``annot_id_map`` — simulating an annotation that was filtered
        # out of the export (or whose import failed earlier).
        relationships_data = [
            {
                "id": "rel_1",
                "relationshipLabel": "Missing Endpoint Rel",
                "source_annotation_ids": [str(annot1.id)],
                "target_annotation_ids": ["missing_target_id"],
                "structural": False,
            },
            {
                "id": "rel_2",
                "relationshipLabel": "Missing Endpoint Rel",
                "source_annotation_ids": ["missing_source_id"],
                "target_annotation_ids": [str(annot1.id)],
                "structural": False,
            },
        ]

        annot_id_map: dict[str | int, int] = {str(annot1.id): annot1.id}
        label_lookup = {("Missing Endpoint Rel", RELATIONSHIP_LABEL): rel_label}

        # Should not raise.
        _import_v2_relationships(
            cast(list[OpenContractsRelationshipPythonType], relationships_data),
            self.corpus,
            annot_id_map,
            label_lookup,
            self.user,
        )

        # Both relationships had a missing endpoint, so neither should
        # have been persisted.
        self.assertEqual(
            Relationship.objects.filter(corpus=self.corpus).count(),
            0,
            "Relationships with missing source/target annotation must be dropped",
        )

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
        result = import_structural_annotation_set(
            cast(StructuralAnnotationSetExport, struct_data), label_lookup, self.user
        )

        self.assertIsNotNone(result)
        assert result is not None
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
        result = import_structural_annotation_set(
            cast(StructuralAnnotationSetExport, struct_data), label_lookup, self.user
        )

        self.assertIsNotNone(result)

        # Check that relationship was created
        relationships = Relationship.objects.filter(structural_set=result)
        self.assertEqual(relationships.count(), 1)

        rel = relationships.first()
        assert rel is not None
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
        result = import_structural_annotation_set(
            cast(StructuralAnnotationSetExport, struct_data), label_lookup, self.user
        )

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

        annot_id_map: dict[str | int, int] = {
            str(annot1.id): annot1.id,
            str(annot2.id): annot2.id,
        }
        label_lookup = {
            ("Test Label", TOKEN_LABEL): self.text_label
        }  # Missing "NonexistentRelLabel"

        # Should not raise error, just log warning and skip
        _import_v2_relationships(
            cast(list[OpenContractsRelationshipPythonType], relationships_data),
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
        result = import_structural_annotation_set(
            cast(StructuralAnnotationSetExport, struct_data), label_lookup, self.user
        )

        self.assertIsNotNone(result)

        # Should have 2 annotations but 0 relationships (missing label)
        annots = Annotation.objects.filter(structural_set=result)
        self.assertEqual(annots.count(), 2)

        relationships = Relationship.objects.filter(structural_set=result)
        self.assertEqual(
            relationships.count(), 0
        )  # No relationship due to missing label


class TestV2FolderPathReconstruction(TestCase):
    """
    Regression coverage for ``_reconstruct_document_paths`` folder lookup.

    The export side may write either:
      * ``get_path()``-style (name-joined) paths into both
        ``folder.path`` and ``document_paths.folder_path`` (canonical
        ``utils/export_v2.py`` exporter), or
      * slug-joined / arbitrary paths (third-party exporters such as
        EDGAR scrapers that build the ZIP themselves).

    Either is fine — the only invariant the importer requires is that
    ``folder.path`` and ``document_paths.folder_path`` use the **same**
    convention within a single export.  These tests pin that contract.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="reconuser", password="pw")
        self.labelset = LabelSet.objects.create(title="LS", creator=self.user)
        self.corpus = Corpus.objects.create(
            title="Recon Corpus", label_set=self.labelset, creator=self.user
        )

        # Build a 3-folder hierarchy that mirrors the EDGAR-style export:
        # one ``8-K/A`` name contains a slash to also lock down the
        # ambiguity it would create for any naive get_path()-only lookup.
        self.f_root = CorpusFolder.objects.create(
            corpus=self.corpus, name="Filings", creator=self.user
        )
        self.f_eight_k_a = CorpusFolder.objects.create(
            corpus=self.corpus,
            name="8-K/A",
            parent=self.f_root,
            creator=self.user,
        )
        self.f_leaf = CorpusFolder.objects.create(
            corpus=self.corpus,
            name="2025-06-03",
            parent=self.f_eight_k_a,
            creator=self.user,
        )

        # Create one corpus-isolated Document + DocumentPath per document
        # so ``_reconstruct_document_paths`` has a row to update.
        self.doc = Document.objects.create(
            title="Recon Doc",
            pdf_file_hash="hash-recon-1",
            creator=self.user,
            page_count=1,
        )
        self.doc_path = DocumentPath.objects.create(
            document=self.doc,
            corpus=self.corpus,
            folder=None,
            path="/placeholder.pdf",
            version_number=1,
            creator=self.user,
        )

        self.doc_hash_to_corpus_doc = {"hash-recon-1": self.doc}

        # ``folder_export_id_to_obj`` mirrors what ``import_corpus_folders``
        # returns: keyed by the export's ``id`` field.
        self.folder_export_id_to_obj = {
            "fld-root": self.f_root,
            "fld-8ka": self.f_eight_k_a,
            "fld-leaf": self.f_leaf,
        }

    def _folders_data(self, exporter: str) -> list[CorpusFolderExport]:
        """Build a ``folders_data`` payload with the given exporter style.

        ``"canonical"`` reproduces what ``package_corpus_folders`` writes
        today (name-joined via ``get_path()``).  ``"slug"`` reproduces what
        an EDGAR-scraper-style exporter writes (slug-joined paths that do
        not match ``get_path()``).
        """
        if exporter == "canonical":
            return [
                {
                    "id": "fld-root",
                    "name": "Filings",
                    "description": "",
                    "color": "#05313d",
                    "icon": "folder",
                    "tags": [],
                    "is_public": False,
                    "parent_id": None,
                    "path": "Filings",
                },
                {
                    "id": "fld-8ka",
                    "name": "8-K/A",
                    "description": "",
                    "color": "#05313d",
                    "icon": "folder",
                    "tags": [],
                    "is_public": False,
                    "parent_id": "fld-root",
                    "path": "Filings/8-K/A",
                },
                {
                    "id": "fld-leaf",
                    "name": "2025-06-03",
                    "description": "",
                    "color": "#05313d",
                    "icon": "folder",
                    "tags": [],
                    "is_public": False,
                    "parent_id": "fld-8ka",
                    "path": "Filings/8-K/A/2025-06-03",
                },
            ]
        if exporter == "slug":
            return [
                {
                    "id": "fld-root",
                    "name": "Filings",
                    "description": "",
                    "color": "#05313d",
                    "icon": "folder",
                    "tags": [],
                    "is_public": False,
                    "parent_id": None,
                    "path": "filings",
                },
                {
                    "id": "fld-8ka",
                    "name": "8-K/A",
                    "description": "",
                    "color": "#05313d",
                    "icon": "folder",
                    "tags": [],
                    "is_public": False,
                    "parent_id": "fld-root",
                    "path": "filings/8-k-a",
                },
                {
                    "id": "fld-leaf",
                    "name": "2025-06-03",
                    "description": "",
                    "color": "#05313d",
                    "icon": "folder",
                    "tags": [],
                    "is_public": False,
                    "parent_id": "fld-8ka",
                    "path": "filings/8-k-a/2025-06-03",
                },
            ]
        raise ValueError(f"unknown exporter style: {exporter}")

    def _document_paths_data(self, folder_path: str | None) -> list[DocumentPathExport]:
        return [
            {
                "document_ref": "hash-recon-1",
                "folder_path": folder_path,
                "path": "/Filings/8-K/A/2025-06-03/doc.pdf",
                "version_number": 1,
                "parent_version_number": None,
                "is_current": True,
                "is_deleted": False,
                "created": timezone.now().isoformat(),
            }
        ]

    def test_build_lookup_indexes_both_get_path_and_export_path(self):
        """The helper accepts whichever string the exporter wrote."""
        folders_data = self._folders_data("slug")
        lookup = _build_folder_path_lookup(folders_data, self.folder_export_id_to_obj)

        # Slug keys (what document_paths.folder_path will hold in this zip)
        self.assertIs(lookup["filings"], self.f_root)
        self.assertIs(lookup["filings/8-k-a"], self.f_eight_k_a)
        self.assertIs(lookup["filings/8-k-a/2025-06-03"], self.f_leaf)

        # get_path() keys still resolve in case a future export uses
        # the canonical convention alongside slug paths.
        self.assertIs(lookup[self.f_root.get_path()], self.f_root)
        self.assertIs(lookup[self.f_leaf.get_path()], self.f_leaf)

    def test_build_lookup_skips_folders_that_failed_to_import(self):
        """Folders missing from the id map are silently skipped (already logged)."""
        folders_data = self._folders_data("slug")
        # Drop one entry from the map as if import_corpus_folders had logged
        # an error and returned without that folder.
        partial_map = dict(self.folder_export_id_to_obj)
        partial_map.pop("fld-leaf")

        lookup = _build_folder_path_lookup(folders_data, partial_map)
        self.assertNotIn("filings/8-k-a/2025-06-03", lookup)
        self.assertIn("filings/8-k-a", lookup)

    def test_canonical_name_joined_folder_path_resolves(self):
        """Regression guard: canonical ``get_path()``-style exports still work."""
        _reconstruct_document_paths(
            document_paths_data=self._document_paths_data(
                folder_path=self.f_leaf.get_path(),
            ),
            corpus_obj=self.corpus,
            doc_hash_to_corpus_doc=self.doc_hash_to_corpus_doc,
            folders_data=self._folders_data("canonical"),
            folder_export_id_to_obj=self.folder_export_id_to_obj,
        )

        self.doc_path.refresh_from_db()
        self.assertEqual(self.doc_path.folder, self.f_leaf)

    def test_slug_joined_folder_path_resolves(self):
        """Primary fix: third-party slug-joined ``folder_path`` resolves.

        Before the fix this DocumentPath would silently stay at
        ``folder=NULL`` because the importer only indexed by
        ``get_path()``.
        """
        _reconstruct_document_paths(
            document_paths_data=self._document_paths_data(
                folder_path="filings/8-k-a/2025-06-03",
            ),
            corpus_obj=self.corpus,
            doc_hash_to_corpus_doc=self.doc_hash_to_corpus_doc,
            folders_data=self._folders_data("slug"),
            folder_export_id_to_obj=self.folder_export_id_to_obj,
        )

        self.doc_path.refresh_from_db()
        self.assertEqual(self.doc_path.folder, self.f_leaf)

    def test_unresolved_folder_path_logs_warning_and_leaves_root(self):
        """Operators get a breadcrumb when the conventions don't line up."""
        with self.assertLogs(
            "opencontractserver.tasks.import_tasks_v2", level="WARNING"
        ) as captured:
            _reconstruct_document_paths(
                document_paths_data=self._document_paths_data(
                    folder_path="some/path/the/exporter/invented",
                ),
                corpus_obj=self.corpus,
                doc_hash_to_corpus_doc=self.doc_hash_to_corpus_doc,
                folders_data=self._folders_data("slug"),
                folder_export_id_to_obj=self.folder_export_id_to_obj,
            )

        # Document stays at the corpus root rather than getting silently
        # mis-attached.
        self.doc_path.refresh_from_db()
        self.assertIsNone(self.doc_path.folder)

        joined = "\n".join(captured.output)
        self.assertIn("some/path/the/exporter/invented", joined)
        self.assertIn(f"corpus {self.corpus.id}", joined)

    def test_build_lookup_skips_empty_exported_path(self):
        """An empty ``folder.path`` string is treated as absent, not registered.

        Indexing ``""`` would silently fuse every empty-path folder onto a
        single key and let documents land in whichever folder happened to be
        processed last.  The ``if key:`` guard in ``_register`` prevents that;
        ``get_path()`` keys still resolve normally.
        """
        folders_data = self._folders_data("canonical")
        # Mutate the root entry's ``path`` to the empty string — mimics a
        # malformed export.
        for entry in folders_data:
            if entry["id"] == "fld-root":
                entry["path"] = ""

        lookup = _build_folder_path_lookup(folders_data, self.folder_export_id_to_obj)
        self.assertNotIn("", lookup)
        # ``get_path()`` for the root folder is still indexed, so resolution
        # via the canonical key continues to work.
        self.assertIs(lookup[self.f_root.get_path()], self.f_root)

    def test_build_lookup_warns_on_key_collision(self):
        """Two folders sharing a lookup key are surfaced loudly.

        Construct a synthetic collision: a sibling's exported ``path`` value
        is set to the leaf folder's ``get_path()``.  Last writer wins, but
        the WARNING makes the silent mis-attribution grep-able.
        """
        folders_data = self._folders_data("canonical")
        leaf_canonical = self.f_leaf.get_path()
        # Force the ``Filings`` root export entry to claim the same lookup key
        # as the leaf folder's canonical ``get_path()``.
        for entry in folders_data:
            if entry["id"] == "fld-root":
                entry["path"] = leaf_canonical

        with self.assertLogs(
            "opencontractserver.tasks.import_tasks_v2", level="WARNING"
        ) as captured:
            lookup = _build_folder_path_lookup(
                folders_data, self.folder_export_id_to_obj
            )

        joined = "\n".join(captured.output)
        self.assertIn("Folder path key collision", joined)
        self.assertIn(repr(leaf_canonical), joined)
        # Last writer wins — whichever folder registered the key second
        # (iteration order over ``folders_data``) owns the lookup entry.
        self.assertIn(lookup[leaf_canonical], {self.f_root, self.f_leaf})


class TestV2ImportExceptionHandling(TestCase):
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

        label_lookup: dict = {}
        result = import_structural_annotation_set(
            cast(StructuralAnnotationSetExport, struct_data), label_lookup, self.user
        )

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

        result = import_corpus_folders(
            cast(list[CorpusFolderExport], folders_data), self.corpus, self.user
        )

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

        annot_id_map: dict[str | int, int] = {str(annot.id): annot.id}
        label_lookup = {("Test Rel Label", RELATIONSHIP_LABEL): rel_label}

        # Should raise the exception (function doesn't have try/except)
        with self.assertRaises(Exception):
            _import_v2_relationships(
                cast(list[OpenContractsRelationshipPythonType], relationships_data),
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
        import_agent_config(cast(AgentConfigExport, agent_config), self.corpus)

    @mock.patch(
        "opencontractserver.tasks.import_tasks_v2._setup_corpus_and_labels",
        side_effect=Exception("Setup failed"),
    )
    def test_import_corpus_exception_handler(self, mock_setup):
        """Test _import_corpus catches exceptions and returns None."""
        from opencontractserver.tasks.import_tasks_v2 import _import_corpus

        result = _import_corpus(
            data_json=cast(OpenContractsExportDataJsonV2Type, {"annotated_docs": {}}),
            # Test forces ``_setup_corpus_and_labels`` to raise before the
            # ZIP is ever opened, so a real ZipFile is unnecessary here.
            import_zip=cast(zipfile.ZipFile, None),
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


class TestV2FullRoundTrip(TestCase):
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
        assert export.file.name is not None
        self.assertTrue(export.file.name.endswith("_EXPORT_V2.zip"))

        # Read and verify export content
        with export.file.open("rb") as f:
            with zipfile.ZipFile(f, "r") as zip_ref:
                # Check data.json exists
                self.assertIn("data.json", zip_ref.namelist())

                # Load and verify data.json
                with zip_ref.open("data.json") as data_file:
                    data = json.load(data_file)

                    # Verify version — V3 is the current emit schema
                    # (canonical-CAML refactor, Task 12).
                    self.assertEqual(data["version"], "3.0")

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


class TestV1BackwardCompatibility(TestCase):
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


class TestV2EdgeCases(TestCase):
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

    @override_settings(EXPORT_SPOOL_MAX_SIZE_BYTES=1)
    def test_build_zip_disk_rollover_produces_valid_archive(self):
        """Force the SpooledTemporaryFile to spill to disk and round-trip cleanly.

        With ``EXPORT_SPOOL_MAX_SIZE_BYTES=1`` the spool rolls over to an
        on-disk file almost immediately (every write past the first byte
        is on disk). This exercises the memory-fix's actual purpose:

        1. ``build_corpus_v2_zip`` honours the override (the threshold is
           read lazily — a stale module-level capture would silently keep
           the 100 MB default and never spill).
        2. The buffer ``_rolled`` flag flips to ``True``, confirming we
           hit the disk path rather than the in-memory short-circuit.
        3. The archive is still a valid zipfile after rollover, and a
           full import succeeds — i.e. the central directory is written
           and the rewind to offset 0 happens after the close.
        """
        from opencontractserver.tasks.export_tasks_v2 import build_corpus_v2_zip
        from opencontractserver.tasks.import_tasks_v2 import (
            import_corpus_v2_from_bytes,
        )

        labelset = LabelSet.objects.create(title="Rollover Set", creator=self.user)
        corpus = Corpus.objects.create(
            title="Rollover Corpus",
            label_set=labelset,
            creator=self.user,
        )

        # Use as a context manager to exercise the documented lifetime
        # pattern (the function's docstring tells callers to ``with`` the
        # returned buffer); a try/finally + .close() would test the same
        # bytes but not the contract.
        with build_corpus_v2_zip(
            corpus_pk=corpus.id,
            user_for_visibility=None,
            include_conversations=False,
        ) as zip_buffer:
            self.assertIsInstance(zip_buffer, SpooledTemporaryFile)
            # ``_rolled`` is the documented internal flag SpooledTemporaryFile
            # flips when it crosses ``max_size``. Asserting on it is the
            # cleanest way to prove we actually exercised the disk path —
            # any in-memory short-circuit would leave it False. The attribute
            # exists at runtime but is absent from the typeshed stub, so the
            # access is ignored narrowly.
            self.assertTrue(
                zip_buffer._rolled,  # type: ignore[attr-defined]
                "spool did not roll over even with max_size=1; the override "
                "is being ignored (likely a stale module-level constant "
                "capture)",
            )

            with zipfile.ZipFile(zip_buffer, "r") as zf:
                self.assertIn("data.json", zf.namelist())

            zip_buffer.seek(0)
            imported_id = import_corpus_v2_from_bytes(
                zip_source=zip_buffer,
                user_id=self.user.id,
                seed_corpus_id=None,
            )
            self.assertIsNotNone(imported_id)

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


class TestLabelTypeExportCompleteness(TestCase):
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


class TestDocumentFileTypeRoundTrip(TestCase):
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


class TestConversationExportEnhancements(TestCase):
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
        assert conv is not None

        # Timestamps should be close to the original (within a second)
        self.assertAlmostEqual(
            conv.created_at.timestamp(),
            original_time.timestamp(),
            delta=1.0,
        )

        msg = ChatMessage.objects.filter(conversation=conv).first()
        self.assertIsNotNone(msg)
        assert msg is not None
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
        assert parent is not None
        assert child is not None

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
        assert conv is not None
        self.assertEqual(conv.description, "Important discussion")
        self.assertTrue(conv.is_locked)
        self.assertTrue(conv.is_pinned)


class TestReconstructDocumentPaths(TestCase):
    """Test _reconstruct_document_paths covers all branches."""

    folders_data: list[CorpusFolderExport]

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

        # Folder lookup wiring that mirrors what the production caller
        # gets back from ``import_corpus_folders``. Tests that don't
        # exercise folder resolution can still pass these through; only
        # the folder-specific tests vary the contents.
        self.folders_data = [
            {
                "id": "fld-myfolder",
                "name": "MyFolder",
                "description": "",
                "color": "#05313d",
                "icon": "folder",
                "tags": [],
                "is_public": False,
                "parent_id": None,
                "path": "MyFolder",
            }
        ]
        self.folder_export_id_to_obj = {"fld-myfolder": self.folder}

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

        _reconstruct_document_paths(
            cast(list[DocumentPathExport], document_paths_data),
            self.corpus,
            doc_hash_map,
            self.folders_data,
            self.folder_export_id_to_obj,
        )

        # Reload DocumentPath
        updated_path = DocumentPath.objects.filter(
            corpus=self.corpus, document=self.corpus_doc
        ).first()
        assert updated_path is not None
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

        _reconstruct_document_paths(
            cast(list[DocumentPathExport], document_paths_data),
            self.corpus,
            doc_hash_map,
            self.folders_data,
            self.folder_export_id_to_obj,
        )

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

        _reconstruct_document_paths(
            cast(list[DocumentPathExport], document_paths_data),
            self.corpus,
            doc_hash_map,
            self.folders_data,
            self.folder_export_id_to_obj,
        )

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

        _reconstruct_document_paths(
            cast(list[DocumentPathExport], document_paths_data),
            self.corpus,
            doc_hash_map,
            self.folders_data,
            self.folder_export_id_to_obj,
        )

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
        _reconstruct_document_paths(
            cast(list[DocumentPathExport], document_paths_data),
            self.corpus,
            doc_hash_map,
            self.folders_data,
            self.folder_export_id_to_obj,
        )

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

        _reconstruct_document_paths(
            cast(list[DocumentPathExport], document_paths_data),
            self.corpus,
            doc_hash_map,
            self.folders_data,
            self.folder_export_id_to_obj,
        )

        # No changes expected
        self.doc_path.refresh_from_db()

    def test_folder_path_not_found(self):
        """Test that unmatched folder_path leaves the document at root."""
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

        # The miss is also logged as a warning now; suppress it so this
        # test's intent (path applied, folder stays NULL) stays focused.
        with self.assertLogs(
            "opencontractserver.tasks.import_tasks_v2", level="WARNING"
        ):
            _reconstruct_document_paths(
                cast(list[DocumentPathExport], document_paths_data),
                self.corpus,
                doc_hash_map,
                self.folders_data,
                self.folder_export_id_to_obj,
            )

        updated_path = DocumentPath.objects.filter(
            corpus=self.corpus, document=self.corpus_doc
        ).first()
        assert updated_path is not None
        self.assertEqual(updated_path.path, "/new/path")
        # folder should not be set
        self.assertIsNone(updated_path.folder)


class TestBuildLabelLookupsEdgeCases(TestCase):
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
            annotation_filter_mode=AnnotationFilterMode.ANALYSES_ONLY,
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
            annotation_filter_mode=AnnotationFilterMode.CORPUS_LABELSET_PLUS_ANALYSES,
        )

        # Should include corpus labels only (no analyses to add)
        self.assertGreater(len(result["text_labels"]), 0)


class TestDocumentPathExportFallback(TestCase):
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


class TestConversationImportDocHashRelinking(TestCase):
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
        assert conv is not None
        self.assertEqual(conv.chat_with_document, self.doc)
        self.assertIsNone(conv.chat_with_corpus)


class TestV2ThreeRoundTripDataIntegrity(TestCase):
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
        # Delegate the rich-fixture build to the shared helper so
        # both this test and the fork parity tests stay aligned.
        self.corpus = build_rich_test_corpus(self.user)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _snapshot(self, corpus: Corpus) -> dict:
        """Delegate to the shared :func:`snapshot_corpus` helper."""
        return snapshot_corpus(corpus)

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
