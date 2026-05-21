import json
import logging

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.test import TestCase

from opencontractserver.analyzer.models import Analysis, Analyzer, GremlinEngine
from opencontractserver.corpuses.models import Corpus, CorpusAction
from opencontractserver.documents.models import Document
from opencontractserver.tests.fixtures import SAMPLE_GREMLIN_ENGINE_MANIFEST_PATH
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.analysis import create_and_setup_analysis

logger = logging.getLogger(__name__)

User = get_user_model()


class TestAnalysisUtils(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="12345")
        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)

        self.gremlin_manifest = json.loads(
            SAMPLE_GREMLIN_ENGINE_MANIFEST_PATH.open("r").read()
        )
        self.gremlin_url = "http://localhost:8000"
        self.gremlin = GremlinEngine.objects.create(
            url=self.gremlin_url, creator=self.user
        )
        self.analyzer_gremlin = Analyzer.objects.create(
            id="Web-Based Analyzer",
            description="Test Gremlin Analyzer",
            host_gremlin=self.gremlin,
            creator=self.user,
            manifest={},
        )
        self.analyzer_task = Analyzer.objects.create(
            id="Task-Based Analyzer",
            description="Test Task Analyzer",
            task_name="test_task",
            creator=self.user,
            manifest={},
        )

        self.doc_ids = []
        for a in range(0, 3):
            doc = Document(
                title="Test Document", description="Test Description", creator=self.user
            )
            doc.save()
            self.doc_ids.append(doc.id)

    def test_create_and_setup_analysis_gremlin(self):
        analysis = create_and_setup_analysis(
            self.analyzer_gremlin, self.user.id, corpus_id=self.corpus.id
        )
        self.assertIsInstance(analysis, Analysis)
        self.assertEqual(analysis.analyzer, self.analyzer_gremlin)
        self.assertEqual(analysis.analyzed_corpus_id, self.corpus.id)
        self.assertEqual(analysis.creator_id, self.user.id)
        self.assertIsNone(analysis.corpus_action)

    def test_create_and_setup_analysis_task(self):
        analysis = create_and_setup_analysis(
            self.analyzer_task, self.user.id, corpus_id=self.corpus.id
        )
        self.assertIsInstance(analysis, Analysis)
        self.assertEqual(analysis.analyzer, self.analyzer_task)
        self.assertEqual(analysis.analyzed_corpus_id, self.corpus.id)
        self.assertEqual(analysis.creator_id, self.user.id)
        self.assertIsNone(analysis.corpus_action)

    def test_create_and_setup_analysis_with_corpus_action(self):
        corpus_action = CorpusAction.objects.create(
            name="Test Action",
            corpus=self.corpus,
            analyzer=self.analyzer_task,
            trigger="add_document",
            creator=self.user,
        )
        analysis = create_and_setup_analysis(
            self.analyzer_task,
            self.user.id,
            corpus_id=self.corpus.id,
            corpus_action=corpus_action,
        )
        self.assertIsInstance(analysis, Analysis)
        self.assertEqual(analysis.analyzer, self.analyzer_task)
        self.assertEqual(analysis.analyzed_corpus_id, self.corpus.id)
        self.assertEqual(analysis.creator_id, self.user.id)
        self.assertEqual(analysis.corpus_action, corpus_action)

    def test_create_and_setup_analysis_with_doc_ids(self):
        doc_ids = self.doc_ids  # Mock document IDs
        analysis = create_and_setup_analysis(
            self.analyzer_gremlin,
            self.user.id,
            corpus_id=self.corpus.id,
            doc_ids=doc_ids,
        )
        self.assertIsInstance(analysis, Analysis)
        self.assertCountEqual(
            list(analysis.analyzed_documents.values_list("id", flat=True)), doc_ids
        )

    def test_create_and_setup_analysis_grants_creator_crud(self):
        """Pins the framework contract: every Analysis created through the
        canonical chokepoint must have guardian CRUD for its creator.

        Breaks if a refactor accidentally drops the
        ``set_permissions_for_obj_to_user`` call — the agent-tool
        ``start_analysis``, the GraphQL mutation, and every CorpusAction
        delegation rely on this invariant.
        """
        analysis = create_and_setup_analysis(
            self.analyzer_task, self.user.id, corpus_id=self.corpus.id
        )
        for permission in (
            PermissionTypes.READ,
            PermissionTypes.UPDATE,
            PermissionTypes.DELETE,
        ):
            self.assertTrue(
                analysis.user_can(self.user, permission),
                f"creator should have {permission.name} on Analysis "
                f"created via the framework helper",
            )

    def test_create_and_setup_analysis_invalid_analyzer(self):
        with self.assertRaises(ValidationError):
            with transaction.atomic():
                invalid_analyzer = Analyzer(
                    description="Invalid Analyzer", creator=self.user, manifest={}
                )
                invalid_analyzer.full_clean()
                create_and_setup_analysis(
                    invalid_analyzer, self.user.id, corpus_id=self.corpus.id
                )
