"""
Tests for corpus document actions and the direct invocation architecture.

Architecture Overview:
---------------------
Corpus actions (analyzers, fieldsets, agents) should only run AFTER documents
are fully processed (parsed, thumbnailed). This is achieved through direct
invocation in the document lifecycle methods:

1. When a document is ADDED to a corpus via add_document() or import_document():
   - If document is READY (backend_lock=False): trigger actions immediately
   - If document is PROCESSING (backend_lock=True): actions will be triggered
     when set_doc_lock_state() unlocks the document

2. When document processing COMPLETES (set_doc_lock_state unlocks):
   - Query DocumentPath to find all corpuses the document belongs to
   - Trigger ADD_DOCUMENT actions for each corpus

This uses DocumentPath as the source of truth for corpus membership (not M2M).

See docs/architecture/agent_corpus_actions_design.md for full details.
"""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.analyzer.models import Analysis, Analyzer, GremlinEngine
from opencontractserver.corpuses.models import Corpus, CorpusAction, CorpusActionTrigger
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.extracts.models import Column, Extract, Fieldset
from opencontractserver.tasks.corpus_tasks import process_corpus_action

User = get_user_model()


@pytest.mark.django_db
class TestCorpusDocumentActions(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)
        self.document = Document.objects.create(
            title="Test Document", creator=self.user
        )
        self.task_based_analyzer = Analyzer.objects.create(
            description="Test Analyzer", creator=self.user, task_name="not.a.real.task"
        )
        self.gremlin_engine = GremlinEngine.objects.create(
            url="http://test-gremlin-engine.com", creator=self.user
        )
        # Create an Analyzer
        self.analyzer = Analyzer.objects.create(
            id="don't do a thing",
            description="Test Analyzer",
            creator=self.user,
            host_gremlin=self.gremlin_engine,
        )
        self.fieldset = Fieldset.objects.create(name="Test Fieldset", creator=self.user)
        self.column = Column.objects.create(
            fieldset=self.fieldset,
            name="Test Column",
            query="Test Query",
            output_type="str",
            creator=self.user,
        )

    @patch("opencontractserver.tasks.corpus_tasks.process_corpus_action.delay")
    @patch("opencontractserver.corpuses.models.transaction.on_commit")
    def test_add_document_triggers_actions_for_ready_doc(
        self, mock_on_commit, mock_task
    ):
        """
        Test that add_document() directly triggers corpus actions when the
        document is ready (backend_lock=False).
        """
        # Make on_commit execute the callback immediately for testing
        mock_on_commit.side_effect = lambda func: func()

        # Create a ready document (not locked)
        ready_doc = Document.objects.create(
            title="Ready Document",
            creator=self.user,
            backend_lock=False,  # Ready for processing
        )

        # Add the ready document to corpus
        added_doc, status, doc_path = self.corpus.add_document(
            document=ready_doc, user=self.user
        )

        # Verify the DocumentPath was created properly
        self.assertIsNotNone(doc_path)
        self.assertEqual(doc_path.corpus, self.corpus)
        self.assertEqual(doc_path.document, added_doc)
        self.assertTrue(doc_path.is_current)
        self.assertFalse(doc_path.is_deleted)

        # add_document() should have directly triggered process_corpus_action
        # because the document is ready (backend_lock=False)
        mock_task.assert_called_once_with(
            corpus_id=self.corpus.id,
            document_ids=[added_doc.id],
            user_id=self.user.id,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
        )

    @patch("opencontractserver.tasks.corpus_tasks.process_corpus_action.delay")
    def test_add_document_skips_actions_for_locked_doc(self, mock_task):
        """
        Test that add_document() does NOT trigger actions when the document
        is still processing (backend_lock=True). Actions will be triggered
        later by set_doc_lock_state when processing completes.
        """
        # Create a locked document (simulating one still being parsed)
        locked_doc = Document.objects.create(
            title="Locked Document",
            creator=self.user,
            backend_lock=True,  # Still processing
        )

        # Add the locked document to corpus
        added_doc, status, doc_path = self.corpus.add_document(
            document=locked_doc, user=self.user
        )

        # add_document() should NOT have triggered process_corpus_action
        # because the document is still locked (actions deferred to set_doc_lock_state)
        mock_task.assert_not_called()

    @patch("opencontractserver.tasks.corpus_tasks.process_corpus_action.delay")
    def test_set_doc_lock_state_triggers_actions_via_document_path(self, mock_task):
        """
        Test that set_doc_lock_state triggers corpus actions using DocumentPath
        as the source of truth (not M2M relationship).
        """
        from opencontractserver.tasks.doc_tasks import set_doc_lock_state

        # Create a locked document
        doc = Document.objects.create(
            title="Test Doc",
            creator=self.user,
            backend_lock=True,
        )

        # Create DocumentPath linking doc to corpus (source of truth)
        DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            path="/test/doc.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )

        # Unlock the document (simulating processing completion)
        set_doc_lock_state(locked=False, doc_id=doc.id)

        # Should have triggered process_corpus_action using DocumentPath lookup
        mock_task.assert_called_once_with(
            corpus_id=self.corpus.id,
            document_ids=[doc.id],
            user_id=self.corpus.creator.id,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
        )

    @patch("opencontractserver.tasks.corpus_tasks.process_corpus_action.delay")
    def test_set_doc_lock_state_no_corpus_no_action(self, mock_task):
        """
        Test that set_doc_lock_state does NOT trigger actions if the document
        has no DocumentPath records (not in any corpus).
        """
        from opencontractserver.tasks.doc_tasks import set_doc_lock_state

        # Create a document NOT in any corpus (no DocumentPath)
        doc = Document.objects.create(
            title="Orphan Doc",
            creator=self.user,
            backend_lock=True,
        )

        # Unlock the document
        set_doc_lock_state(locked=False, doc_id=doc.id)

        # Should NOT have triggered any corpus actions
        mock_task.assert_not_called()

    @patch("opencontractserver.tasks.corpus_tasks.process_corpus_action.delay")
    def test_set_doc_lock_state_triggers_for_multiple_corpuses(self, mock_task):
        """
        Test that when a document has DocumentPath records in multiple corpuses,
        set_doc_lock_state triggers actions for ALL of them.
        """
        from opencontractserver.tasks.doc_tasks import set_doc_lock_state

        # Create a second corpus
        corpus2 = Corpus.objects.create(title="Second Corpus", creator=self.user)

        # Create a locked document
        doc = Document.objects.create(
            title="Multi-corpus Doc",
            creator=self.user,
            backend_lock=True,
        )

        # Create DocumentPath records for both corpuses
        DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            path="/test/doc.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )
        DocumentPath.objects.create(
            document=doc,
            corpus=corpus2,
            path="/test/doc.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )

        # Unlock the document
        set_doc_lock_state(locked=False, doc_id=doc.id)

        # Should have triggered process_corpus_action for BOTH corpuses
        self.assertEqual(mock_task.call_count, 2)

        # Verify both corpus IDs were called
        called_corpus_ids = {
            call.kwargs["corpus_id"] for call in mock_task.call_args_list
        }
        self.assertEqual(called_corpus_ids, {self.corpus.id, corpus2.id})

    @patch("opencontractserver.tasks.corpus_tasks.process_corpus_action.delay")
    def test_set_doc_lock_state_ignores_deleted_paths(self, mock_task):
        """
        Test that set_doc_lock_state ignores DocumentPath records that are
        soft-deleted (is_deleted=True) or not current (is_current=False).
        """
        from opencontractserver.tasks.doc_tasks import set_doc_lock_state

        # Create a second corpus
        corpus2 = Corpus.objects.create(title="Second Corpus", creator=self.user)

        # Create a locked document
        doc = Document.objects.create(
            title="Test Doc",
            creator=self.user,
            backend_lock=True,
        )

        # Create an active DocumentPath in corpus1
        DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            path="/test/doc.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )

        # Create a DELETED DocumentPath in corpus2 (should be ignored)
        DocumentPath.objects.create(
            document=doc,
            corpus=corpus2,
            path="/test/doc.pdf",
            version_number=1,
            is_current=True,
            is_deleted=True,  # Soft deleted
            creator=self.user,
        )

        # Unlock the document
        set_doc_lock_state(locked=False, doc_id=doc.id)

        # Should have triggered process_corpus_action for ONLY corpus1
        mock_task.assert_called_once_with(
            corpus_id=self.corpus.id,
            document_ids=[doc.id],
            user_id=self.corpus.creator.id,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
        )

    def test_process_corpus_action_with_task_based_analyzer(self):
        CorpusAction.objects.create(
            corpus=self.corpus,
            analyzer=self.task_based_analyzer,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            creator=self.user,
        )

        process_corpus_action.si(
            self.corpus.id, [self.document.id], self.user.id
        ).apply().get()

        self.assertEqual(Analysis.objects.all().count(), 1)

    def test_process_corpus_action_with_analyzer(self):
        CorpusAction.objects.create(
            corpus=self.corpus,
            analyzer=self.analyzer,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            creator=self.user,
        )

        process_corpus_action.si(
            self.corpus.id, [self.document.id], self.user.id
        ).apply()

        analyses = Analysis.objects.all()
        self.assertEqual(1, analyses.count())
        analyzed_corpus = analyses[0].analyzed_corpus
        assert analyzed_corpus is not None
        self.assertEqual(analyzed_corpus.id, self.corpus.id)
        self.assertEqual(analyses[0].analyzer.id, self.analyzer.id)

    def test_multiple_corpus_actions(self):

        CorpusAction.objects.create(
            corpus=self.corpus,
            fieldset=self.fieldset,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            creator=self.user,
        )
        CorpusAction.objects.create(
            corpus=self.corpus,
            analyzer=self.analyzer,
            trigger=CorpusActionTrigger.ADD_DOCUMENT,
            creator=self.user,
        )

        process_corpus_action.si(
            self.corpus.id, [self.document.id], self.user.id
        ).apply()

        analyses = Analysis.objects.all()
        self.assertEqual(1, analyses.count())
        analyzed_corpus = analyses[0].analyzed_corpus
        assert analyzed_corpus is not None
        self.assertEqual(analyzed_corpus.id, self.corpus.id)
        self.assertEqual(analyses[0].analyzer.id, self.analyzer.id)

        extracts = Extract.objects.all()
        self.assertEqual(1, extracts.count())
        extract_corpus = extracts[0].corpus
        assert extract_corpus is not None
        self.assertEqual(extract_corpus.id, self.corpus.id)
        self.assertEqual(extracts[0].fieldset.id, self.fieldset.id)
