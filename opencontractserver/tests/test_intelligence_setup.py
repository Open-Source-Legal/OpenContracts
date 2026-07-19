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
from opencontractserver.corpuses.services.data_story import PROFILE_ACTION_NAME
from opencontractserver.documents.models import Document
from opencontractserver.enrichment import constants as enrichment_constants
from opencontractserver.shared.services.conventions import ServiceResult
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()

_START_ANALYSIS = (
    "opencontractserver.analyzer.services.analysis_lifecycle_service."
    "AnalysisLifecycleService.start_document_analysis"
)

# Superuser the template seeder requires to own AgentConfigurations (mirrors
# the migration-time admin in test_corpus_action_template).
_SEED_ADMIN_USERNAME = "migration_admin"


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
        username=_SEED_ADMIN_USERNAME,
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
        # No duplicate action rows, no duplicate executions. Setup installs the
        # reference-enrichment action, one action per LLM template, and the
        # structured Collection Profile add_document action.
        self.assertEqual(
            CorpusAction.objects.filter(corpus=self.corpus).count(),
            1 + len(INTELLIGENCE_SETUP_TEMPLATE_NAMES) + 1,
        )
        # The structured-profile action is itself idempotent: re-running setup
        # reuses the single accumulating action rather than cloning it.
        self.assertEqual(
            CorpusAction.objects.filter(
                corpus=self.corpus, name=PROFILE_ACTION_NAME
            ).count(),
            1,
        )
        self.assertEqual(
            CorpusActionExecution.objects.filter(
                corpus_action__corpus=self.corpus
            ).count(),
            3 * len(INTELLIGENCE_SETUP_TEMPLATE_NAMES),
        )

    @patch(_START_ANALYSIS, side_effect=_ok_analysis)
    def test_setup_requires_crud_permission(self, mock_start):
        """Setup gates at CRUD — the tier AddTemplateToCorpus and
        CreateCorpusAction require for installing the very same rows. An
        UPDATE-only collaborator must be refused, not offered a weaker path."""
        # Invisible corpus: same not-found envelope (anti-enumeration).
        result = CorpusIntelligenceSetupService.setup(self.stranger, self.corpus.pk)
        self.assertFalse(result.ok)
        self.assertEqual(
            result.error, CorpusIntelligenceSetupService._NOT_FOUND_MESSAGE
        )

        # Visible with UPDATE but not CRUD: still refused.
        set_permissions_for_obj_to_user(
            self.stranger,
            self.corpus,
            [PermissionTypes.READ, PermissionTypes.UPDATE],
        )
        result = CorpusIntelligenceSetupService.setup(self.stranger, self.corpus.pk)
        self.assertFalse(result.ok)
        self.assertEqual(
            result.error, CorpusIntelligenceSetupService._NOT_FOUND_MESSAGE
        )
        self.assertFalse(CorpusAction.objects.filter(corpus=self.corpus).exists())
        mock_start.assert_not_called()

    @patch(_START_ANALYSIS, side_effect=_ok_analysis)
    def test_status_reports_can_setup(self, mock_start):
        """``can_setup`` mirrors the mutation's permission gate so the CTA
        never renders for viewers whose click is guaranteed to fail."""
        owner_status = CorpusIntelligenceSetupService.status(self.user, self.corpus.pk)
        self.assertTrue(owner_status.ok)
        assert owner_status.value is not None
        self.assertTrue(owner_status.value.can_setup)

        reader = User.objects.create_user(username="reader", password="x")
        set_permissions_for_obj_to_user(reader, self.corpus, [PermissionTypes.READ])
        reader_status = CorpusIntelligenceSetupService.status(reader, self.corpus.pk)
        self.assertTrue(reader_status.ok)
        assert reader_status.value is not None
        self.assertFalse(reader_status.value.can_setup)

        # UPDATE-without-CRUD matches the setup gate too.
        editor = User.objects.create_user(username="editor", password="x")
        set_permissions_for_obj_to_user(
            editor, self.corpus, [PermissionTypes.READ, PermissionTypes.UPDATE]
        )
        editor_status = CorpusIntelligenceSetupService.status(editor, self.corpus.pk)
        self.assertTrue(editor_status.ok)
        assert editor_status.value is not None
        self.assertFalse(editor_status.value.can_setup)

    @patch(_START_ANALYSIS, side_effect=_ok_analysis)
    def test_status_fully_set_up_without_analyzer(self, mock_start):
        """Without the enrichment analyzer registered the reference half can
        never install — status must not demand it forever (zombie CTA)."""
        from opencontractserver.analyzer.models import Analyzer

        Analyzer.objects.filter(
            task_name=enrichment_constants.ENRICHMENT_ANALYZER_TASK
        ).delete()

        before = CorpusIntelligenceSetupService.status(self.user, self.corpus.pk)
        assert before.value is not None
        self.assertFalse(before.value.reference_available)
        self.assertFalse(before.value.is_fully_set_up)  # templates still missing

        CorpusIntelligenceSetupService.setup(self.user, self.corpus.pk)

        after = CorpusIntelligenceSetupService.status(self.user, self.corpus.pk)
        assert after.value is not None
        self.assertFalse(after.value.reference_available)
        self.assertFalse(after.value.reference_action_installed)
        self.assertTrue(after.value.is_fully_set_up)

    @patch(_START_ANALYSIS, side_effect=_ok_analysis)
    def test_status_ignores_unavailable_template(self, mock_start):
        """A template deactivated deployment-wide cannot be installed — it must
        not keep the corpus 'not fully set up' (and the CTA visible) forever."""
        target = INTELLIGENCE_SETUP_TEMPLATE_NAMES[0]
        CorpusActionTemplate.objects.filter(name=target).update(is_active=False)

        CorpusIntelligenceSetupService.setup(self.user, self.corpus.pk)

        status = CorpusIntelligenceSetupService.status(self.user, self.corpus.pk)
        assert status.value is not None
        self.assertNotIn(target, status.value.missing_template_names)
        self.assertTrue(status.value.is_fully_set_up)

    @patch(_START_ANALYSIS, side_effect=_ok_analysis)
    def test_setup_queues_partial_batch_over_cap(self, mock_start):
        """Over the per-call cap, setup queues up to the cap instead of nothing
        and reports how many documents remain for a later run."""
        with patch(
            "opencontractserver.corpuses.services.corpus_actions.BATCH_RUN_MAX_DOCS",
            2,
        ):
            result = CorpusIntelligenceSetupService.setup(self.user, self.corpus.pk)
        self.assertTrue(result.ok, result.error)
        summary = result.value
        assert summary is not None
        for outcome in summary.templates:
            self.assertEqual(outcome.queued_count, 2, outcome.template_name)
            self.assertEqual(outcome.remaining_count, 1, outcome.template_name)
            self.assertEqual(outcome.error, "", outcome.template_name)
        self.assertEqual(
            CorpusActionExecution.objects.filter(
                corpus_action__corpus=self.corpus
            ).count(),
            2 * len(INTELLIGENCE_SETUP_TEMPLATE_NAMES),
        )

    @patch(_START_ANALYSIS, side_effect=_ok_analysis)
    def test_status_before_and_after(self, mock_start):
        before = CorpusIntelligenceSetupService.status(self.user, self.corpus.pk)
        self.assertTrue(before.ok)
        before_status = before.value
        assert before_status is not None
        self.assertFalse(before_status.reference_action_installed)
        self.assertEqual(
            before_status.missing_template_names,
            list(INTELLIGENCE_SETUP_TEMPLATE_NAMES),
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

    @patch(_START_ANALYSIS, side_effect=_ok_analysis)
    def test_setup_skips_deterministic_half_without_analyzer(self, mock_start):
        """No enrichment analyzer registered → LLM half still installs."""
        from opencontractserver.analyzer.models import Analyzer

        Analyzer.objects.filter(
            task_name=enrichment_constants.ENRICHMENT_ANALYZER_TASK
        ).delete()

        result = CorpusIntelligenceSetupService.setup(self.user, self.corpus.pk)
        self.assertTrue(result.ok, result.error)
        summary = result.value
        assert summary is not None

        self.assertFalse(summary.reference_available)
        self.assertFalse(summary.reference_action_installed_now)
        self.assertFalse(summary.reference_analysis_started)
        mock_start.assert_not_called()
        # No reference action row, but the templates still installed.
        self.assertFalse(
            CorpusAction.objects.filter(
                corpus=self.corpus,
                analyzer__task_name=enrichment_constants.ENRICHMENT_ANALYZER_TASK,
            ).exists()
        )
        self.assertTrue(all(o.installed_now for o in summary.templates))

    @patch(_START_ANALYSIS, side_effect=_ok_analysis)
    def test_setup_skips_second_analysis_when_one_in_flight(self, mock_start):
        """A QUEUED/RUNNING enrichment analysis suppresses a duplicate start."""
        from opencontractserver.analyzer.models import Analysis, Analyzer
        from opencontractserver.types.enums import JobStatus

        analyzer = Analyzer.objects.get(
            task_name=enrichment_constants.ENRICHMENT_ANALYZER_TASK
        )
        Analysis.objects.create(
            analyzer=analyzer,
            analyzed_corpus=self.corpus,
            creator=self.user,
            status=JobStatus.RUNNING.value,
        )

        result = CorpusIntelligenceSetupService.setup(self.user, self.corpus.pk)
        self.assertTrue(result.ok, result.error)
        summary = result.value
        assert summary is not None

        # Action installed and no *second* analysis started (the running one
        # is not duplicated)...
        self.assertTrue(summary.reference_action_installed_now)
        mock_start.assert_not_called()
        # ...but the summary still reports the weave as started: the reference
        # web IS being built by the in-flight analysis, so the toast must not
        # misleadingly omit the "reference web weaving" note.
        self.assertTrue(summary.reference_analysis_started)

    @patch(_START_ANALYSIS, side_effect=lambda *a, **k: ServiceResult.failure("boom"))
    def test_setup_records_failed_analysis_start(self, mock_start):
        """A failed analysis start is logged, not fatal — setup still succeeds."""
        result = CorpusIntelligenceSetupService.setup(self.user, self.corpus.pk)
        self.assertTrue(result.ok, result.error)
        summary = result.value
        assert summary is not None
        self.assertTrue(summary.reference_action_installed_now)
        self.assertFalse(summary.reference_analysis_started)
        mock_start.assert_called_once()

    @patch(_START_ANALYSIS, side_effect=_ok_analysis)
    def test_setup_records_error_for_inactive_template(self, mock_start):
        """An inactive bundle template is recorded as an error, not raised."""
        target = INTELLIGENCE_SETUP_TEMPLATE_NAMES[0]
        CorpusActionTemplate.objects.filter(name=target).update(is_active=False)

        result = CorpusIntelligenceSetupService.setup(self.user, self.corpus.pk)
        self.assertTrue(result.ok, result.error)
        summary = result.value
        assert summary is not None

        by_name = {o.template_name: o for o in summary.templates}
        self.assertEqual(by_name[target].error, "Template not found or inactive.")
        self.assertFalse(by_name[target].installed_now)
        # The other templates still install — partial success.
        for name, outcome in by_name.items():
            if name != target:
                self.assertTrue(outcome.installed_now, name)

    @patch(_START_ANALYSIS, side_effect=_ok_analysis)
    def test_setup_contains_clone_failure_per_template(self, mock_start):
        """A non-IntegrityError clone failure stays contained to its template."""
        with patch.object(
            CorpusActionTemplate,
            "clone_to_corpus",
            side_effect=ValueError("kaboom"),
        ):
            setup_result = CorpusIntelligenceSetupService.setup(
                self.user, self.corpus.pk
            )

        # The whole call still succeeds (graceful partial success), and the
        # deterministic reference half is unaffected.
        self.assertTrue(setup_result.ok, setup_result.error)
        summary = setup_result.value
        assert summary is not None
        self.assertTrue(summary.reference_action_installed_now)
        for outcome in summary.templates:
            self.assertFalse(outcome.installed_now, outcome.template_name)
            self.assertTrue(
                outcome.error.startswith("Failed to install template:"),
                outcome.error,
            )
        # No partial action rows were left installed.
        self.assertFalse(
            CorpusAction.objects.filter(
                corpus=self.corpus,
                source_template__name__in=INTELLIGENCE_SETUP_TEMPLATE_NAMES,
            ).exists()
        )

    # ------------------------------------------------------------------
    # Structured-profile setup branches (the data-story backfill)
    # ------------------------------------------------------------------
    def test_structured_profile_skips_empty_corpus(self):
        """A corpus with no documents installs the accumulating extract but
        adds no docs and never schedules a backfill (the ``if not docs``
        early return)."""
        from opencontractserver.extracts.models import Extract

        empty = Corpus.objects.create(title="Empty Profile Corpus", creator=self.user)
        CorpusIntelligenceSetupService._setup_structured_profile(self.user, empty)

        extract = Extract.objects.filter(corpus=empty).first()
        self.assertIsNotNone(extract)
        assert extract is not None
        self.assertEqual(extract.documents.count(), 0)
        self.assertIsNone(extract.started)

    def test_structured_profile_skips_backfill_when_cells_exist(self):
        """Once the accumulating extract already has cells, re-running setup
        returns before fetching documents (the datacell-exists guard) so a
        prior run's profile is never recomputed."""
        from opencontractserver.corpuses.services.data_story import (
            DEFAULT_PROFILE_FIELDSET_NAME,
        )
        from opencontractserver.extracts.models import Column, Datacell, Extract

        # First run builds the extract and backfills the corpus's 3 documents.
        CorpusIntelligenceSetupService._setup_structured_profile(self.user, self.corpus)
        extract = Extract.objects.get(
            corpus=self.corpus,
            fieldset__name=DEFAULT_PROFILE_FIELDSET_NAME,
            corpus_action__isnull=False,
        )
        self.assertEqual(extract.documents.count(), 3)
        column = Column.objects.filter(fieldset=extract.fieldset).first()
        document = extract.documents.first()
        assert column is not None and document is not None
        Datacell.objects.create(
            extract=extract,
            column=column,
            document=document,
            data_definition="profile",
            creator=self.user,
        )

        # Second run: the datacell-exists guard returns before the document
        # fetch, so ``get_corpus_documents`` is never reached.
        with patch(
            "opencontractserver.corpuses.services.corpus_documents."
            "CorpusDocumentService.get_corpus_documents"
        ) as mock_get_docs:
            CorpusIntelligenceSetupService._setup_structured_profile(
                self.user, self.corpus
            )
        mock_get_docs.assert_not_called()

    def test_structured_profile_swallows_setup_exception(self):
        """A failure inside structured-profile setup is logged, never raised —
        the data story is an enhancement, not a precondition for the bundle."""
        from opencontractserver.extracts.models import Extract

        with patch(
            "opencontractserver.corpuses.services.data_story."
            "get_or_create_default_profile_fieldset",
            side_effect=RuntimeError("boom"),
        ):
            # Must not raise.
            CorpusIntelligenceSetupService._setup_structured_profile(
                self.user, self.corpus
            )
        # The exception fires before any row is written.
        self.assertFalse(Extract.objects.filter(corpus=self.corpus).exists())


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
        result = schema.execute_sync(
            query, variable_values=variables, context_value=request
        )
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
                    remainingCount
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
                referenceAvailable
                referenceActionInstalled
                installedTemplateNames
                missingTemplateNames
                isFullySetUp
                canSetup
              }
            }
            """,
            {"id": gid},
            self.user,
        )
        status = data["corpusIntelligenceSetupStatus"]
        self.assertTrue(status["referenceAvailable"])
        self.assertTrue(status["referenceActionInstalled"])
        self.assertEqual(status["missingTemplateNames"], [])
        self.assertTrue(status["isFullySetUp"])
        self.assertTrue(status["canSetup"])

    @patch(_START_ANALYSIS, side_effect=_ok_analysis)
    def test_setup_mutation_idor_for_stranger(self, mock_start):
        """A user without corpus access gets the indistinguishable failure.

        The mutation must return ``ok=False`` with the IDOR-safe message (same
        text whether the corpus is missing or merely off-limits) and install
        nothing — never leaking the corpus's existence and never running the
        CRUD-gated writes as a stranger.
        """
        stranger = User.objects.create_user(username="gql-stranger", password="x")
        gid = to_global_id("CorpusType", self.corpus.pk)

        data = self._execute(
            """
            mutation Setup($id: ID!) {
              setupCorpusIntelligence(corpusId: $id) {
                ok
                message
                summary {
                  referenceActionInstalledNow
                }
              }
            }
            """,
            {"id": gid},
            stranger,
        )
        payload = data["setupCorpusIntelligence"]
        self.assertFalse(payload["ok"])
        self.assertEqual(
            payload["message"],
            "Corpus not found or you don't have permission.",
        )
        self.assertIsNone(payload["summary"])
        # No reference action was installed on the corpus by the stranger's call.
        self.assertFalse(
            CorpusAction.objects.filter(corpus=self.corpus).exists(),
            "stranger's rejected setup must not install any CorpusAction",
        )
