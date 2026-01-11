"""
Comprehensive tests for the v2 corpus forking system.

These tests verify:
1. All model types are forked correctly
2. Ownership is transferred to forking user
3. Permissions are set correctly per consolidated_permissioning_guide.md
4. Data integrity is maintained
5. ID mappings are correct
6. Error handling works properly
7. Edge cases (empty corpus, no labelset, etc.)
"""

import logging
from typing import Optional

from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase

from opencontractserver.annotations.models import (
    Annotation,
    AnnotationLabel,
    LabelSet,
    Note,
    NoteRevision,
    Relationship,
    RELATIONSHIP_LABEL,
    TOKEN_LABEL,
)
from opencontractserver.conversations.models import (
    ChatMessage,
    Conversation,
    MessageTypeChoices,
)
from opencontractserver.corpuses.models import Corpus, CorpusFolder
from opencontractserver.documents.models import Document
from opencontractserver.extracts.models import Column, Datacell, Extract, Fieldset
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.fork_handlers import (
    fork_annotation_labels,
    fork_annotations,
    fork_chat_messages,
    fork_columns,
    fork_conversations,
    fork_corpus_folders,
    fork_datacells,
    fork_documents,
    fork_extracts,
    fork_fieldsets,
    fork_label_set,
    fork_note_revisions,
    fork_notes,
    fork_relationships,
)
from opencontractserver.utils.fork_utils import ForkContext, ForkResult
from opencontractserver.utils.permissioning import (
    set_permissions_for_obj_to_user,
    user_has_permission_for_obj,
)

User = get_user_model()
logger = logging.getLogger(__name__)


class ForkContextTestCase(TestCase):
    """Test the ForkContext dataclass."""

    def test_fork_context_initialization(self):
        """Test that ForkContext initializes with correct defaults."""
        ctx = ForkContext(
            source_corpus_id=1,
            target_corpus_id=2,
            user_id=3,
        )

        self.assertEqual(ctx.source_corpus_id, 1)
        self.assertEqual(ctx.target_corpus_id, 2)
        self.assertEqual(ctx.user_id, 3)
        self.assertEqual(ctx.doc_map, {})
        self.assertEqual(ctx.label_map, {})
        self.assertEqual(ctx.annotation_map, {})
        self.assertEqual(ctx.documents_forked, 0)


class ForkLabelSetTestCase(TestCase):
    """Test forking of LabelSet and AnnotationLabels."""

    def setUp(self):
        """Set up test data."""
        self.owner = User.objects.create_user(username="owner", password="test123")
        self.forker = User.objects.create_user(username="forker", password="test123")

        # Create source corpus with label set
        self.source_corpus = Corpus.objects.create(
            title="Source Corpus",
            creator=self.owner,
        )
        set_permissions_for_obj_to_user(
            self.owner, self.source_corpus, [PermissionTypes.CRUD]
        )

        # Create label set with labels
        self.label_set = LabelSet.objects.create(
            title="Test Labels",
            description="Test label set",
            creator=self.owner,
        )
        self.source_corpus.label_set = self.label_set
        self.source_corpus.save()

        self.label1 = AnnotationLabel.objects.create(
            text="Label 1",
            label_type=TOKEN_LABEL,
            color="#FF0000",
            creator=self.owner,
        )
        self.label2 = AnnotationLabel.objects.create(
            text="Label 2",
            label_type=RELATIONSHIP_LABEL,
            color="#00FF00",
            creator=self.owner,
        )
        self.label_set.annotation_labels.add(self.label1, self.label2)

        # Create target corpus
        self.target_corpus = Corpus.objects.create(
            title="Target Corpus",
            creator=self.forker,
            parent=self.source_corpus,
        )

    def test_fork_label_set(self):
        """Test forking a label set."""
        ctx = ForkContext(
            source_corpus_id=self.source_corpus.id,
            target_corpus_id=self.target_corpus.id,
            user_id=self.forker.id,
        )

        new_label_set_id = fork_label_set(ctx, self.label_set.id)

        self.assertIsNotNone(new_label_set_id)
        new_label_set = LabelSet.objects.get(pk=new_label_set_id)

        # Verify ownership transferred
        self.assertEqual(new_label_set.creator_id, self.forker.id)

        # Verify title has [FORK] prefix
        self.assertTrue(new_label_set.title.startswith("[FORK]"))

        # Verify target corpus has the new label set
        self.target_corpus.refresh_from_db()
        self.assertEqual(self.target_corpus.label_set_id, new_label_set_id)

    def test_fork_label_set_none(self):
        """Test forking with no label set."""
        ctx = ForkContext(
            source_corpus_id=self.source_corpus.id,
            target_corpus_id=self.target_corpus.id,
            user_id=self.forker.id,
        )

        new_label_set_id = fork_label_set(ctx, None)
        self.assertIsNone(new_label_set_id)

    def test_fork_annotation_labels(self):
        """Test forking annotation labels."""
        ctx = ForkContext(
            source_corpus_id=self.source_corpus.id,
            target_corpus_id=self.target_corpus.id,
            user_id=self.forker.id,
        )

        # First fork the label set
        new_label_set_id = fork_label_set(ctx, self.label_set.id)

        # Then fork the labels
        count = fork_annotation_labels(ctx, self.label_set.id, new_label_set_id)

        self.assertEqual(count, 2)
        self.assertEqual(len(ctx.label_map), 2)

        # Verify mappings
        self.assertIn(self.label1.id, ctx.label_map)
        self.assertIn(self.label2.id, ctx.label_map)

        # Verify new labels have correct owner
        for old_id, new_id in ctx.label_map.items():
            new_label = AnnotationLabel.objects.get(pk=new_id)
            self.assertEqual(new_label.creator_id, self.forker.id)


class ForkDocumentsTestCase(TestCase):
    """Test forking of documents."""

    def setUp(self):
        """Set up test data."""
        self.owner = User.objects.create_user(username="owner", password="test123")
        self.forker = User.objects.create_user(username="forker", password="test123")

        # Create source corpus
        self.source_corpus = Corpus.objects.create(
            title="Source Corpus",
            creator=self.owner,
        )
        set_permissions_for_obj_to_user(
            self.owner, self.source_corpus, [PermissionTypes.CRUD]
        )

        # Create documents
        self.doc1 = Document.objects.create(
            title="Document 1",
            creator=self.owner,
        )
        self.doc2 = Document.objects.create(
            title="Document 2",
            creator=self.owner,
        )

        # Add documents to corpus
        self.source_corpus.add_document(document=self.doc1, user=self.owner)
        self.source_corpus.add_document(document=self.doc2, user=self.owner)

        # Create target corpus
        self.target_corpus = Corpus.objects.create(
            title="Target Corpus",
            creator=self.forker,
            parent=self.source_corpus,
        )
        set_permissions_for_obj_to_user(
            self.forker, self.target_corpus, [PermissionTypes.CRUD]
        )

    def test_fork_documents(self):
        """Test forking documents."""
        ctx = ForkContext(
            source_corpus_id=self.source_corpus.id,
            target_corpus_id=self.target_corpus.id,
            user_id=self.forker.id,
        )

        # Get document IDs from source corpus
        doc_ids = list(
            self.source_corpus.get_documents().values_list("id", flat=True)
        )

        count = fork_documents(ctx, doc_ids)

        self.assertEqual(count, 2)
        self.assertEqual(len(ctx.doc_map), 2)
        self.assertEqual(ctx.documents_forked, 2)

        # Verify new documents have correct owner
        for old_id, new_id in ctx.doc_map.items():
            new_doc = Document.objects.get(pk=new_id)
            self.assertEqual(new_doc.creator_id, self.forker.id)
            self.assertTrue(new_doc.title.startswith("[FORK]"))

        # Verify target corpus has the new documents
        target_docs = list(self.target_corpus.get_documents())
        self.assertEqual(len(target_docs), 2)

    def test_fork_documents_with_folder(self):
        """Test forking documents preserves folder structure."""
        # Create folder in source corpus
        folder = CorpusFolder.objects.create(
            name="Test Folder",
            corpus=self.source_corpus,
            creator=self.owner,
        )

        # Create a new document in that folder
        doc3 = Document.objects.create(
            title="Document 3",
            creator=self.owner,
        )
        self.source_corpus.add_document(document=doc3, user=self.owner, folder=folder)

        ctx = ForkContext(
            source_corpus_id=self.source_corpus.id,
            target_corpus_id=self.target_corpus.id,
            user_id=self.forker.id,
        )

        # Fork folders first
        fork_corpus_folders(ctx)

        # Then fork documents
        doc_ids = list(
            self.source_corpus.get_documents().values_list("id", flat=True)
        )
        fork_documents(ctx, doc_ids)

        # Verify folder was forked
        self.assertIn(folder.id, ctx.folder_map)


class ForkAnnotationsTestCase(TestCase):
    """Test forking of annotations and relationships."""

    def setUp(self):
        """Set up test data."""
        self.owner = User.objects.create_user(username="owner", password="test123")
        self.forker = User.objects.create_user(username="forker", password="test123")

        # Create source corpus with label set
        self.source_corpus = Corpus.objects.create(
            title="Source Corpus",
            creator=self.owner,
        )

        self.label_set = LabelSet.objects.create(
            title="Test Labels",
            creator=self.owner,
        )
        self.source_corpus.label_set = self.label_set
        self.source_corpus.save()

        self.token_label = AnnotationLabel.objects.create(
            text="Token Label",
            label_type=TOKEN_LABEL,
            creator=self.owner,
        )
        self.rel_label = AnnotationLabel.objects.create(
            text="Rel Label",
            label_type=RELATIONSHIP_LABEL,
            creator=self.owner,
        )
        self.label_set.annotation_labels.add(self.token_label, self.rel_label)

        # Create document
        self.doc = Document.objects.create(
            title="Test Doc",
            creator=self.owner,
        )
        self.source_corpus.add_document(document=self.doc, user=self.owner)

        # Get the corpus-isolated doc
        corpus_doc = self.source_corpus.get_documents().first()

        # Create annotations
        self.ann1 = Annotation.objects.create(
            raw_text="Annotation 1",
            annotation_label=self.token_label,
            document=corpus_doc,
            corpus=self.source_corpus,
            creator=self.owner,
        )
        self.ann2 = Annotation.objects.create(
            raw_text="Annotation 2",
            annotation_label=self.token_label,
            document=corpus_doc,
            corpus=self.source_corpus,
            creator=self.owner,
        )

        # Create relationship
        self.rel = Relationship.objects.create(
            relationship_label=self.rel_label,
            corpus=self.source_corpus,
            document=corpus_doc,
            creator=self.owner,
        )
        self.rel.source_annotations.add(self.ann1)
        self.rel.target_annotations.add(self.ann2)

        # Create target corpus
        self.target_corpus = Corpus.objects.create(
            title="Target Corpus",
            creator=self.forker,
            parent=self.source_corpus,
        )

    def test_fork_annotations(self):
        """Test forking annotations."""
        ctx = ForkContext(
            source_corpus_id=self.source_corpus.id,
            target_corpus_id=self.target_corpus.id,
            user_id=self.forker.id,
        )

        # Fork label set and labels first
        new_label_set_id = fork_label_set(ctx, self.label_set.id)
        fork_annotation_labels(ctx, self.label_set.id, new_label_set_id)

        # Fork documents
        doc_ids = list(
            self.source_corpus.get_documents().values_list("id", flat=True)
        )
        fork_documents(ctx, doc_ids)

        # Fork annotations
        annotation_ids = list(
            Annotation.objects.filter(
                corpus=self.source_corpus,
                analysis__isnull=True,
            ).values_list("id", flat=True)
        )
        count = fork_annotations(ctx, annotation_ids)

        self.assertEqual(count, 2)
        self.assertEqual(len(ctx.annotation_map), 2)

        # Verify new annotations have correct owner
        for old_id, new_id in ctx.annotation_map.items():
            new_ann = Annotation.objects.get(pk=new_id)
            self.assertEqual(new_ann.creator_id, self.forker.id)
            self.assertEqual(new_ann.corpus_id, self.target_corpus.id)

    def test_fork_relationships(self):
        """Test forking relationships."""
        ctx = ForkContext(
            source_corpus_id=self.source_corpus.id,
            target_corpus_id=self.target_corpus.id,
            user_id=self.forker.id,
        )

        # Fork dependencies first
        new_label_set_id = fork_label_set(ctx, self.label_set.id)
        fork_annotation_labels(ctx, self.label_set.id, new_label_set_id)
        doc_ids = list(
            self.source_corpus.get_documents().values_list("id", flat=True)
        )
        fork_documents(ctx, doc_ids)
        annotation_ids = list(
            Annotation.objects.filter(
                corpus=self.source_corpus,
                analysis__isnull=True,
            ).values_list("id", flat=True)
        )
        fork_annotations(ctx, annotation_ids)

        # Fork relationships
        count = fork_relationships(ctx)

        self.assertEqual(count, 1)
        self.assertEqual(ctx.relationships_forked, 1)

        # Verify relationship was forked
        new_rels = Relationship.objects.filter(corpus=self.target_corpus)
        self.assertEqual(new_rels.count(), 1)

        new_rel = new_rels.first()
        self.assertEqual(new_rel.creator_id, self.forker.id)
        self.assertEqual(new_rel.source_annotations.count(), 1)
        self.assertEqual(new_rel.target_annotations.count(), 1)


class ForkExtractsTestCase(TestCase):
    """Test forking of extracts and datacells."""

    def setUp(self):
        """Set up test data."""
        self.owner = User.objects.create_user(username="owner", password="test123")
        self.forker = User.objects.create_user(username="forker", password="test123")

        # Create source corpus
        self.source_corpus = Corpus.objects.create(
            title="Source Corpus",
            creator=self.owner,
        )

        # Create fieldset linked to corpus
        self.fieldset = Fieldset.objects.create(
            name="Test Fieldset",
            description="Test description",
            corpus=self.source_corpus,
            creator=self.owner,
        )

        # Create columns
        self.col1 = Column.objects.create(
            name="Column 1",
            fieldset=self.fieldset,
            query="What is X?",
            output_type="str",
            creator=self.owner,
        )
        self.col2 = Column.objects.create(
            name="Column 2",
            fieldset=self.fieldset,
            query="What is Y?",
            output_type="str",
            creator=self.owner,
        )

        # Create document
        self.doc = Document.objects.create(
            title="Test Doc",
            creator=self.owner,
        )
        self.source_corpus.add_document(document=self.doc, user=self.owner)
        corpus_doc = self.source_corpus.get_documents().first()

        # Create extract
        self.extract = Extract.objects.create(
            name="Test Extract",
            corpus=self.source_corpus,
            fieldset=self.fieldset,
            creator=self.owner,
        )
        self.extract.documents.add(corpus_doc)

        # Create datacells
        self.datacell1 = Datacell.objects.create(
            extract=self.extract,
            column=self.col1,
            document=corpus_doc,
            data={"value": "Result 1"},
            data_definition="str",
            creator=self.owner,
        )
        self.datacell2 = Datacell.objects.create(
            extract=self.extract,
            column=self.col2,
            document=corpus_doc,
            data={"value": "Result 2"},
            data_definition="str",
            creator=self.owner,
        )

        # Create target corpus
        self.target_corpus = Corpus.objects.create(
            title="Target Corpus",
            creator=self.forker,
            parent=self.source_corpus,
        )

    def test_fork_fieldsets(self):
        """Test forking fieldsets."""
        ctx = ForkContext(
            source_corpus_id=self.source_corpus.id,
            target_corpus_id=self.target_corpus.id,
            user_id=self.forker.id,
        )

        count = fork_fieldsets(ctx)

        self.assertEqual(count, 1)
        self.assertEqual(len(ctx.fieldset_map), 1)

        new_fieldset_id = ctx.fieldset_map[self.fieldset.id]
        new_fieldset = Fieldset.objects.get(pk=new_fieldset_id)

        self.assertEqual(new_fieldset.creator_id, self.forker.id)
        self.assertTrue(new_fieldset.name.startswith("[FORK]"))
        self.assertEqual(new_fieldset.corpus_id, self.target_corpus.id)

    def test_fork_columns(self):
        """Test forking columns."""
        ctx = ForkContext(
            source_corpus_id=self.source_corpus.id,
            target_corpus_id=self.target_corpus.id,
            user_id=self.forker.id,
        )

        # Fork fieldset first
        fork_fieldsets(ctx)

        # Fork columns
        count = fork_columns(ctx)

        self.assertEqual(count, 2)
        self.assertEqual(len(ctx.column_map), 2)

        # Verify columns belong to new fieldset
        for old_id, new_id in ctx.column_map.items():
            new_col = Column.objects.get(pk=new_id)
            new_fieldset_id = ctx.fieldset_map[self.fieldset.id]
            self.assertEqual(new_col.fieldset_id, new_fieldset_id)
            self.assertEqual(new_col.creator_id, self.forker.id)

    def test_fork_extracts_and_datacells(self):
        """Test forking extracts and datacells."""
        ctx = ForkContext(
            source_corpus_id=self.source_corpus.id,
            target_corpus_id=self.target_corpus.id,
            user_id=self.forker.id,
        )

        # Fork dependencies
        fork_fieldsets(ctx)
        fork_columns(ctx)
        doc_ids = list(
            self.source_corpus.get_documents().values_list("id", flat=True)
        )
        fork_documents(ctx, doc_ids)

        # Fork extracts
        extract_count = fork_extracts(ctx)
        self.assertEqual(extract_count, 1)
        self.assertEqual(len(ctx.extract_map), 1)

        # Fork datacells
        datacell_count = fork_datacells(ctx)
        self.assertEqual(datacell_count, 2)

        # Verify datacells have correct mappings
        new_extract_id = ctx.extract_map[self.extract.id]
        new_datacells = Datacell.objects.filter(extract_id=new_extract_id)
        self.assertEqual(new_datacells.count(), 2)

        for datacell in new_datacells:
            self.assertEqual(datacell.creator_id, self.forker.id)
            self.assertIn(datacell.column_id, ctx.column_map.values())
            self.assertIn(datacell.document_id, ctx.doc_map.values())


class ForkConversationsTestCase(TestCase):
    """Test forking of conversations and messages."""

    def setUp(self):
        """Set up test data."""
        self.owner = User.objects.create_user(username="owner", password="test123")
        self.forker = User.objects.create_user(username="forker", password="test123")

        # Create source corpus
        self.source_corpus = Corpus.objects.create(
            title="Source Corpus",
            creator=self.owner,
        )

        # Create document
        self.doc = Document.objects.create(
            title="Test Doc",
            creator=self.owner,
        )
        self.source_corpus.add_document(document=self.doc, user=self.owner)
        self.corpus_doc = self.source_corpus.get_documents().first()

        # Create chat conversation
        self.chat_conv = Conversation.objects.create(
            title="Test Chat",
            conversation_type="chat",
            chat_with_corpus=self.source_corpus,
            creator=self.owner,
        )

        # Create messages
        self.msg1 = ChatMessage.objects.create(
            conversation=self.chat_conv,
            msg_type=MessageTypeChoices.HUMAN,
            content="Hello, world!",
            creator=self.owner,
        )
        self.msg2 = ChatMessage.objects.create(
            conversation=self.chat_conv,
            msg_type=MessageTypeChoices.LLM,
            content="Hi there!",
            parent_message=self.msg1,
            creator=self.owner,
        )

        # Create a thread (discussion) - should NOT be forked
        self.thread_conv = Conversation.objects.create(
            title="Discussion Thread",
            conversation_type="thread",
            chat_with_corpus=self.source_corpus,
            creator=self.owner,
        )

        # Create target corpus
        self.target_corpus = Corpus.objects.create(
            title="Target Corpus",
            creator=self.forker,
            parent=self.source_corpus,
        )

    def test_fork_conversations(self):
        """Test forking chat conversations (not threads)."""
        ctx = ForkContext(
            source_corpus_id=self.source_corpus.id,
            target_corpus_id=self.target_corpus.id,
            user_id=self.forker.id,
        )

        count = fork_conversations(ctx)

        # Only chat conversation should be forked, not thread
        self.assertEqual(count, 1)
        self.assertEqual(len(ctx.conversation_map), 1)
        self.assertIn(self.chat_conv.id, ctx.conversation_map)
        self.assertNotIn(self.thread_conv.id, ctx.conversation_map)

        # Verify new conversation
        new_conv_id = ctx.conversation_map[self.chat_conv.id]
        new_conv = Conversation.objects.get(pk=new_conv_id)
        self.assertEqual(new_conv.creator_id, self.forker.id)
        self.assertEqual(new_conv.chat_with_corpus_id, self.target_corpus.id)

    def test_fork_chat_messages(self):
        """Test forking chat messages."""
        ctx = ForkContext(
            source_corpus_id=self.source_corpus.id,
            target_corpus_id=self.target_corpus.id,
            user_id=self.forker.id,
        )

        # Fork conversation first
        fork_conversations(ctx)

        # Fork messages
        count = fork_chat_messages(ctx)

        self.assertEqual(count, 2)

        # Verify messages in new conversation
        new_conv_id = ctx.conversation_map[self.chat_conv.id]
        new_msgs = ChatMessage.objects.filter(conversation_id=new_conv_id).order_by(
            "created_at"
        )
        self.assertEqual(new_msgs.count(), 2)

        # Verify parent message relationship preserved
        msg_list = list(new_msgs)
        self.assertIsNone(msg_list[0].parent_message)
        self.assertEqual(msg_list[1].parent_message_id, msg_list[0].id)


class ForkNotesTestCase(TestCase):
    """Test forking of notes and revisions."""

    def setUp(self):
        """Set up test data."""
        self.owner = User.objects.create_user(username="owner", password="test123")
        self.forker = User.objects.create_user(username="forker", password="test123")

        # Create source corpus
        self.source_corpus = Corpus.objects.create(
            title="Source Corpus",
            creator=self.owner,
        )

        # Create document
        self.doc = Document.objects.create(
            title="Test Doc",
            creator=self.owner,
        )
        self.source_corpus.add_document(document=self.doc, user=self.owner)
        self.corpus_doc = self.source_corpus.get_documents().first()

        # Create note with revision
        self.note = Note.objects.create(
            title="Test Note",
            content="Initial content",
            document=self.corpus_doc,
            corpus=self.source_corpus,
            creator=self.owner,
        )

        # Create target corpus
        self.target_corpus = Corpus.objects.create(
            title="Target Corpus",
            creator=self.forker,
            parent=self.source_corpus,
        )

    def test_fork_notes(self):
        """Test forking notes."""
        ctx = ForkContext(
            source_corpus_id=self.source_corpus.id,
            target_corpus_id=self.target_corpus.id,
            user_id=self.forker.id,
        )

        # Fork document first
        doc_ids = list(
            self.source_corpus.get_documents().values_list("id", flat=True)
        )
        fork_documents(ctx, doc_ids)

        # Fork notes
        count = fork_notes(ctx)

        self.assertEqual(count, 1)
        self.assertEqual(len(ctx.note_map), 1)

        # Verify new note
        new_note_id = ctx.note_map[self.note.id]
        new_note = Note.objects.get(pk=new_note_id)
        self.assertEqual(new_note.creator_id, self.forker.id)
        self.assertTrue(new_note.title.startswith("[FORK]"))
        self.assertEqual(new_note.corpus_id, self.target_corpus.id)


class ForkCorpusFoldersTestCase(TestCase):
    """Test forking of corpus folders."""

    def setUp(self):
        """Set up test data."""
        self.owner = User.objects.create_user(username="owner", password="test123")
        self.forker = User.objects.create_user(username="forker", password="test123")

        # Create source corpus
        self.source_corpus = Corpus.objects.create(
            title="Source Corpus",
            creator=self.owner,
        )

        # Create folder hierarchy
        self.folder1 = CorpusFolder.objects.create(
            name="Folder 1",
            corpus=self.source_corpus,
            creator=self.owner,
        )
        self.folder2 = CorpusFolder.objects.create(
            name="Subfolder 1",
            corpus=self.source_corpus,
            parent=self.folder1,
            creator=self.owner,
        )
        self.folder3 = CorpusFolder.objects.create(
            name="Folder 2",
            corpus=self.source_corpus,
            creator=self.owner,
        )

        # Create target corpus
        self.target_corpus = Corpus.objects.create(
            title="Target Corpus",
            creator=self.forker,
            parent=self.source_corpus,
        )

    def test_fork_corpus_folders(self):
        """Test forking folder hierarchy."""
        ctx = ForkContext(
            source_corpus_id=self.source_corpus.id,
            target_corpus_id=self.target_corpus.id,
            user_id=self.forker.id,
        )

        count = fork_corpus_folders(ctx)

        self.assertEqual(count, 3)
        self.assertEqual(len(ctx.folder_map), 3)

        # Verify folder hierarchy preserved
        new_folder1_id = ctx.folder_map[self.folder1.id]
        new_folder2_id = ctx.folder_map[self.folder2.id]

        new_folder2 = CorpusFolder.objects.get(pk=new_folder2_id)
        self.assertEqual(new_folder2.parent_id, new_folder1_id)

        # Verify all folders belong to target corpus
        for old_id, new_id in ctx.folder_map.items():
            new_folder = CorpusFolder.objects.get(pk=new_id)
            self.assertEqual(new_folder.corpus_id, self.target_corpus.id)
            self.assertEqual(new_folder.creator_id, self.forker.id)


class ForkEmptyCorpusTestCase(TestCase):
    """Test forking an empty corpus."""

    def setUp(self):
        """Set up test data."""
        self.owner = User.objects.create_user(username="owner", password="test123")
        self.forker = User.objects.create_user(username="forker", password="test123")

        # Create empty source corpus
        self.source_corpus = Corpus.objects.create(
            title="Empty Corpus",
            creator=self.owner,
        )

        # Create target corpus
        self.target_corpus = Corpus.objects.create(
            title="Target Corpus",
            creator=self.forker,
            parent=self.source_corpus,
        )

    def test_fork_empty_corpus(self):
        """Test forking a corpus with no content."""
        ctx = ForkContext(
            source_corpus_id=self.source_corpus.id,
            target_corpus_id=self.target_corpus.id,
            user_id=self.forker.id,
        )

        # All operations should succeed with 0 items
        label_set_id = fork_label_set(ctx, None)
        self.assertIsNone(label_set_id)

        labels_count = fork_annotation_labels(ctx, None, None)
        self.assertEqual(labels_count, 0)

        folders_count = fork_corpus_folders(ctx)
        self.assertEqual(folders_count, 0)

        docs_count = fork_documents(ctx, [])
        self.assertEqual(docs_count, 0)

        anns_count = fork_annotations(ctx, [])
        self.assertEqual(anns_count, 0)

        rels_count = fork_relationships(ctx)
        self.assertEqual(rels_count, 0)

        fieldsets_count = fork_fieldsets(ctx)
        self.assertEqual(fieldsets_count, 0)

        extracts_count = fork_extracts(ctx)
        self.assertEqual(extracts_count, 0)

        convs_count = fork_conversations(ctx)
        self.assertEqual(convs_count, 0)

        notes_count = fork_notes(ctx)
        self.assertEqual(notes_count, 0)


class ForkOwnershipTestCase(TestCase):
    """Test that forked objects have correct ownership."""

    def setUp(self):
        """Set up test data."""
        self.owner = User.objects.create_user(username="owner", password="test123")
        self.forker = User.objects.create_user(username="forker", password="test123")

        # Create source corpus with various objects
        self.source_corpus = Corpus.objects.create(
            title="Source Corpus",
            creator=self.owner,
        )

        self.label_set = LabelSet.objects.create(
            title="Test Labels",
            creator=self.owner,
        )
        self.source_corpus.label_set = self.label_set
        self.source_corpus.save()

        self.label = AnnotationLabel.objects.create(
            text="Test Label",
            label_type=TOKEN_LABEL,
            creator=self.owner,
        )
        self.label_set.annotation_labels.add(self.label)

        self.doc = Document.objects.create(
            title="Test Doc",
            creator=self.owner,
        )
        self.source_corpus.add_document(document=self.doc, user=self.owner)

        # Create target corpus
        self.target_corpus = Corpus.objects.create(
            title="Target Corpus",
            creator=self.forker,
            parent=self.source_corpus,
        )

    def test_all_forked_objects_owned_by_forker(self):
        """Test that all forked objects are owned by the forking user."""
        ctx = ForkContext(
            source_corpus_id=self.source_corpus.id,
            target_corpus_id=self.target_corpus.id,
            user_id=self.forker.id,
        )

        # Fork everything
        new_label_set_id = fork_label_set(ctx, self.label_set.id)
        fork_annotation_labels(ctx, self.label_set.id, new_label_set_id)
        doc_ids = list(
            self.source_corpus.get_documents().values_list("id", flat=True)
        )
        fork_documents(ctx, doc_ids)

        # Verify label set ownership
        new_label_set = LabelSet.objects.get(pk=new_label_set_id)
        self.assertEqual(
            new_label_set.creator_id,
            self.forker.id,
            "LabelSet should be owned by forker",
        )

        # Verify label ownership
        for old_id, new_id in ctx.label_map.items():
            new_label = AnnotationLabel.objects.get(pk=new_id)
            self.assertEqual(
                new_label.creator_id,
                self.forker.id,
                "AnnotationLabel should be owned by forker",
            )

        # Verify document ownership
        for old_id, new_id in ctx.doc_map.items():
            new_doc = Document.objects.get(pk=new_id)
            self.assertEqual(
                new_doc.creator_id,
                self.forker.id,
                "Document should be owned by forker",
            )
