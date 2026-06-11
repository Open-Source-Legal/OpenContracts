"""Tests for the one-click collection-intelligence setup.

Covers ``CorpusIntelligenceSetupService`` (install + idempotence + permission
gating + status) and the ``setupCorpusIntelligence`` /
``corpusIntelligenceSetupStatus`` GraphQL surface.

The LLM batch runs are queued via ``transaction.on_commit`` — under
``TestCase`` those callbacks never fire, so no agent run is attempted; the
queued ``CorpusActionExecution`` rows are the observable contract. The
deterministic half's analysis start is patched (it has its own test
coverage in the analyzer suite).
"""

from typing import Any
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from graphql_relay import to_global_id

from opencontractserver.constants.corpus_actions import (
    INTELLIGENCE_SETUP_TEMPLATE_NAMES,
    REFERENCE_ENRICHMENT_ACTION_NAME,
)
from opencontractserver.corpuses.models import (
    Corpus,
    CorpusAction,
    CorpusActionExecution,
    CorpusActionTemplate,
)
from opencontractserver.corpuses.services import CorpusIntelligenceSetupService
from opencontractserver.documents.models import Document
from opencontractserver.enrichment import constants as enrichment_constants
from opencontractserver.shared.services.conventions import ServiceResult

User = get_user_model()

_START_ANALYSIS = (
    "opencontractserver.analyzer.services.analysis_lifecycle_service."
    "AnalysisLifecycleService.start_document_analysis"
)


def _ok_analysis(*args, **kwargs):
    return ServiceResult.success(object())


def _seed_bundle_dependencies(creator_id: int) -> None:
    """Seed the templates + enrichment analyzer the bundle composes.

    Mirrors what the data migrations (`agents/0010`, analyzer auto-sync)
    provide in a live deployment — the test DB starts empty, so each test
    class seeds explicitly (same pattern as ``test_corpus_action_template``).
    """
    from django.apps import apps

    from opencontractserver.corpuses.template_seeds import (
        create_default_action_templates,
    )
    from opencontractserver.enrichment.services import EnrichmentService

    # The seeder skips silently unless a superuser exists to own the
    # AgentConfigurations (mirrors test_corpus_action_template).
    User.objects.get_or_create(
        username="migration_admin",
        defaults={"is_superuser": True, "is_staff": True, "password": "x"},
    )
    create_default_action_templates(apps, None)
    EnrichmentService.get_or_create_analyzer(creator_id)


class IntelligenceSetupServiceTestCase(TestCase):
    user: Any
    stranger: Any
    corpus: Corpus

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="owner", password="x")
        cls.stranger = User.objects.create_user(username="stranger", password="x")
        _seed_bundle_dependencies(cls.user.id)
        cls.corpus = Corpus.objects.create(title="Setup Corpus", creator=cls.user)
        for i in range(3):
            doc = Document.objects.create(
                title=f"Doc {i}", creator=cls.user, description=""
            )
            doc._skip_signals = True
            cls.corpus.add_document(document=doc, user=cls.user)

    def test_bundle_template_names_are_seeded(self):
        """The constants must keep matching the seeded template names."""
        for name in INTELLIGENCE_SETUP_TEMPLATE_NAMES:
            self.assertTrue(
                CorpusActionTemplate.objects.filter(name=name, is_active=True).exists(),
                f"Bundle template {name!r} is not seeded/active",
            )

    @patch(_START_ANALYSIS, side_effect=_ok_analysis)
    def test_setup_installs_bundle(self, mock_start):
        result = CorpusIntelligenceSetupService.setup(self.user, self.corpus.pk)
        self.assertTrue(result.ok, result.error)
        summary = result.value
        assert summary is not None

        # Deterministic half: action row + immediate weave.
        ref_actions = CorpusAction.objects.filter(
            corpus=self.corpus,
            analyzer__task_name=enrichment_constants.ENRICHMENT_ANALYZER_TASK,
        )
        self.assertEqual(ref_actions.count(), 1)
        self.assertEqual(ref_actions.get().name, REFERENCE_ENRICHMENT_ACTION_NAME)
        self.assertTrue(summary.reference_available)
        self.assertTrue(summary.reference_action_installed_now)
        self.assertTrue(summary.reference_analysis_started)
        mock_start.assert_called_once()

        # LLM half: one cloned action per template, every doc queued.
        self.assertEqual(len(summary.templates), len(INTELLIGENCE_SETUP_TEMPLATE_NAMES))
        for outcome in summary.templates:
            self.assertTrue(outcome.installed_now, outcome.template_name)
            self.assertEqual(outcome.queued_count, 3, outcome.template_name)
            self.assertEqual(outcome.error, "")
        self.assertEqual(
            CorpusAction.objects.filter(
                corpus=self.corpus,
                source_template__name__in=INTELLIGENCE_SETUP_TEMPLATE_NAMES,
            ).count(),
            len(INTELLIGENCE_SETUP_TEMPLATE_NAMES),
        )
        self.assertEqual(
            CorpusActionExecution.objects.filter(
                corpus_action__corpus=self.corpus
            ).count(),
            3 * len(INTELLIGENCE_SETUP_TEMPLATE_NAMES),
        )
        self.assertEqual(summary.total_active_documents, 3)

    @patch(_START_ANALYSIS, side_effect=_ok_analysis)
    def test_setup_is_idempotent(self, mock_start):
        first = CorpusIntelligenceSetupService.setup(self.user, self.corpus.pk)
        self.assertTrue(first.ok, first.error)
        second = CorpusIntelligenceSetupService.setup(self.user, self.corpus.pk)
        self.assertTrue(second.ok, second.error)
        summary = second.value
        assert summary is not None

        self.assertFalse(summary.reference_action_installed_now)
        self.assertTrue(summary.reference_action_already_installed)
        for outcome in summary.templates:
            self.assertFalse(outcome.installed_now, outcome.template_name)
            self.assertTrue(outcome.already_installed, outcome.template_name)
            self.assertEqual(outcome.queued_count, 0, outcome.template_name)
            self.assertEqual(outcome.skipped_already_run_count, 3)
        # No duplicate action rows, no duplicate executions.
        self.assertEqual(
            CorpusAction.objects.filter(corpus=self.corpus).count(),
            1 + len(INTELLIGENCE_SETUP_TEMPLATE_NAMES),
        )
        self.assertEqual(
            CorpusActionExecution.objects.filter(
                corpus_action__corpus=self.corpus
            ).count(),
            3 * len(INTELLIGENCE_SETUP_TEMPLATE_NAMES),
        )

    @patch(_START_ANALYSIS, side_effect=_ok_analysis)
    def test_setup_requires_update_permission(self, mock_start):
        result = CorpusIntelligenceSetupService.setup(self.stranger, self.corpus.pk)
        self.assertFalse(result.ok)
        self.assertEqual(
            result.error, CorpusIntelligenceSetupService._NOT_FOUND_MESSAGE
        )
        self.assertFalse(CorpusAction.objects.filter(corpus=self.corpus).exists())
        mock_start.assert_not_called()

    @patch(_START_ANALYSIS, side_effect=_ok_analysis)
    def test_status_before_and_after(self, mock_start):
        before = CorpusIntelligenceSetupService.status(self.user, self.corpus.pk)
        self.assertTrue(before.ok)
        before_status = before.value
        assert before_status is not None
        self.assertFalse(before_status.reference_action_installed)
        self.assertEqual(
            before_status.missing_template_names, INTELLIGENCE_SETUP_TEMPLATE_NAMES
        )
        self.assertFalse(before_status.is_fully_set_up)

        CorpusIntelligenceSetupService.setup(self.user, self.corpus.pk)

        after = CorpusIntelligenceSetupService.status(self.user, self.corpus.pk)
        self.assertTrue(after.ok)
        after_status = after.value
        assert after_status is not None
        self.assertTrue(after_status.reference_action_installed)
        self.assertEqual(after_status.missing_template_names, [])
        self.assertTrue(after_status.is_fully_set_up)

    def test_status_invisible_corpus(self):
        result = CorpusIntelligenceSetupService.status(self.stranger, self.corpus.pk)
        self.assertFalse(result.ok)


class IntelligenceSetupGraphQLTestCase(TestCase):
    """Schema-level smoke tests via graphql_sync execution."""

    user: Any
    corpus: Corpus

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="gql-owner", password="x")
        _seed_bundle_dependencies(cls.user.id)
        cls.corpus = Corpus.objects.create(title="GQL Setup Corpus", creator=cls.user)
        doc = Document.objects.create(title="Doc", creator=cls.user, description="")
        doc._skip_signals = True
        cls.corpus.add_document(document=doc, user=cls.user)

    def _execute(self, query: str, variables: dict, user) -> dict:
        from django.test import RequestFactory

        from config.graphql.schema import schema

        request = RequestFactory().post("/graphql/")
        request.user = user
        result = schema.execute(query, variable_values=variables, context_value=request)
        self.assertIsNone(result.errors, result.errors)
        return result.data

    @patch(_START_ANALYSIS, side_effect=_ok_analysis)
    def test_mutation_and_status_query(self, mock_start):
        gid = to_global_id("CorpusType", self.corpus.pk)

        data = self._execute(
            """
            mutation Setup($id: ID!) {
              setupCorpusIntelligence(corpusId: $id) {
                ok
                message
                summary {
                  referenceAvailable
                  referenceActionInstalledNow
                  referenceAnalysisStarted
                  totalActiveDocuments
                  templates {
                    templateName
                    installedNow
                    queuedCount
                    error
                  }
                }
              }
            }
            """,
            {"id": gid},
            self.user,
        )
        payload = data["setupCorpusIntelligence"]
        self.assertTrue(payload["ok"], payload["message"])
        self.assertTrue(payload["summary"]["referenceActionInstalledNow"])
        self.assertEqual(payload["summary"]["totalActiveDocuments"], 1)
        self.assertEqual(
            {t["templateName"] for t in payload["summary"]["templates"]},
            set(INTELLIGENCE_SETUP_TEMPLATE_NAMES),
        )
        for t in payload["summary"]["templates"]:
            self.assertTrue(t["installedNow"])
            self.assertEqual(t["queuedCount"], 1)

        data = self._execute(
            """
            query Status($id: ID!) {
              corpusIntelligenceSetupStatus(corpusId: $id) {
                referenceActionInstalled
                installedTemplateNames
                missingTemplateNames
                isFullySetUp
              }
            }
            """,
            {"id": gid},
            self.user,
        )
        status = data["corpusIntelligenceSetupStatus"]
        self.assertTrue(status["referenceActionInstalled"])
        self.assertEqual(status["missingTemplateNames"], [])
        self.assertTrue(status["isFullySetUp"])
