"""Behavioural tests for the Phase 5 service-layer migration.

The structural ``test_service_layer_phase5`` tests pin the *shape* of each
service (importability, base-class, request threading). This file pins the
*behaviour* of each service for internal callers — paths that the GraphQL
mutation suite cannot exercise because the GraphQL decorator gates them out
first. In particular:

- The defence-in-depth in-service superuser guards on
  :meth:`AnalysisLifecycleService.make_public`,
  :meth:`WorkerAccountService.create_worker_account` and
  :meth:`WorkerAccountService.set_active`.
- The anonymous-caller short-circuit on
  :meth:`NotificationService.mark_all_read`.
- The IDOR-safe error paths in the agent / worker-upload services that
  the GraphQL mutations short-circuit before they reach.

See ``docs/refactor_plans/2026-05-23-service-layer-phase5-gap-models-plan.md``.
"""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase

from opencontractserver.agents.models import AgentActionResult, AgentConfiguration
from opencontractserver.agents.services import (
    AgentActionResultService,
    AgentConfigurationService,
)
from opencontractserver.analyzer.models import Analysis, Analyzer
from opencontractserver.analyzer.services import AnalysisLifecycleService
from opencontractserver.annotations.models import Annotation, AnnotationLabel
from opencontractserver.corpuses.models import Corpus, CorpusAction
from opencontractserver.documents.models import Document
from opencontractserver.feedback.models import UserFeedback
from opencontractserver.feedback.services import UserFeedbackService
from opencontractserver.notifications.models import (
    Notification,
    NotificationTypeChoices,
)
from opencontractserver.notifications.services import NotificationService
from opencontractserver.types.enums import LabelType, PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user
from opencontractserver.worker_uploads.models import (
    CorpusAccessToken,
    WorkerAccount,
    WorkerDocumentUpload,
)
from opencontractserver.worker_uploads.services import (
    CorpusAccessTokenService,
    WorkerAccountService,
    WorkerDocumentUploadService,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# AgentConfigurationService — internal paths
# ---------------------------------------------------------------------------


class TestAgentConfigurationServiceBehavioral(TestCase):
    """Exercise the internal paths of ``AgentConfigurationService``.

    The GraphQL mutation does its own corpus gate before calling the
    service, so the service's defence-in-depth branches (bad scope, missing
    corpus, non-superuser GLOBAL) are unreachable from GraphQL. These tests
    pin them at the service level so an internal caller — a Celery task or
    a management command — gets the same safety.
    """

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username="phase5_super",
            email="super@phase5.test",
            password="x",
        )
        cls.regular = User.objects.create_user(
            username="phase5_regular",
            email="reg@phase5.test",
            password="x",
        )
        cls.corpus = Corpus.objects.create(
            title="Phase5 Agent Corpus",
            creator=cls.superuser,
        )
        set_permissions_for_obj_to_user(
            cls.superuser, cls.corpus, [PermissionTypes.CRUD]
        )

    def test_create_agent_rejects_unknown_scope(self):
        result = AgentConfigurationService.create_agent(
            self.superuser,
            name="bad",
            description="d",
            system_instructions="s",
            scope="GROUP",
        )
        self.assertFalse(result.ok)
        self.assertIn("GLOBAL or CORPUS", result.error)

    def test_create_agent_corpus_scope_requires_corpus(self):
        result = AgentConfigurationService.create_agent(
            self.superuser,
            name="no-corpus",
            description="d",
            system_instructions="s",
            scope="CORPUS",
            corpus=None,
        )
        self.assertFalse(result.ok)
        self.assertIn("corpus_id is required", result.error)

    def test_create_agent_corpus_scope_requires_crud_on_corpus(self):
        # Regular user has no CRUD on the corpus → service should refuse
        # even though the GraphQL mutation already pre-gates this. The
        # in-service defence-in-depth keeps internal callers safe too.
        result = AgentConfigurationService.create_agent(
            self.regular,
            name="defence",
            description="d",
            system_instructions="s",
            scope="CORPUS",
            corpus=self.corpus,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "Corpus not found")

    def test_create_agent_global_scope_rejects_corpus_id(self):
        result = AgentConfigurationService.create_agent(
            self.superuser,
            name="bad-global",
            description="d",
            system_instructions="s",
            scope="GLOBAL",
            corpus=self.corpus,
        )
        self.assertFalse(result.ok)
        self.assertIn("must not be provided", result.error)

    def test_create_agent_global_scope_requires_superuser(self):
        result = AgentConfigurationService.create_agent(
            self.regular,
            name="not-super",
            description="d",
            system_instructions="s",
            scope="GLOBAL",
        )
        self.assertFalse(result.ok)
        self.assertIn("superuser", result.error)

    def test_create_agent_global_scope_succeeds_for_superuser(self):
        result = AgentConfigurationService.create_agent(
            self.superuser,
            name="GlobalAgent",
            description="d",
            system_instructions="s",
            scope="GLOBAL",
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.value.scope, "GLOBAL")
        self.assertEqual(result.value.creator, self.superuser)
        # ``set_permissions_for_obj_to_user`` ran with ``is_new=True`` so
        # the creator gets CRUD on the new agent.
        self.assertTrue(result.value.user_can(self.superuser, PermissionTypes.CRUD))

    def test_create_agent_corpus_scope_succeeds_for_creator(self):
        result = AgentConfigurationService.create_agent(
            self.superuser,
            name="CorpusAgent",
            description="d",
            system_instructions="s",
            scope="CORPUS",
            corpus=self.corpus,
            available_tools=["search"],
            permission_required_tools=["delete"],
            badge_config={"icon": "bot"},
            avatar_url="https://example.test/a.png",
            slug="corpus-agent",
        )
        self.assertTrue(result.ok)
        agent = result.value
        self.assertEqual(agent.scope, "CORPUS")
        self.assertEqual(agent.corpus_id, self.corpus.id)
        self.assertEqual(agent.available_tools, ["search"])
        self.assertEqual(agent.permission_required_tools, ["delete"])
        self.assertEqual(agent.badge_config, {"icon": "bot"})
        self.assertEqual(agent.slug, "corpus-agent")

    def test_update_agent_denied_for_non_owner(self):
        agent = AgentConfiguration.objects.create(
            name="protected",
            description="d",
            system_instructions="s",
            scope="GLOBAL",
            creator=self.superuser,
        )
        set_permissions_for_obj_to_user(
            self.superuser, agent, [PermissionTypes.CRUD], is_new=True
        )

        result = AgentConfigurationService.update_agent(
            self.regular, agent, name="hacked"
        )
        self.assertFalse(result.ok)
        # IDOR-safe failure message: same as "not found".
        self.assertEqual(result.error, "Agent configuration not found")

    def test_update_agent_applies_all_optional_fields(self):
        agent = AgentConfiguration.objects.create(
            name="orig",
            description="o",
            system_instructions="o",
            scope="GLOBAL",
            creator=self.superuser,
        )
        set_permissions_for_obj_to_user(
            self.superuser, agent, [PermissionTypes.CRUD], is_new=True
        )
        result = AgentConfigurationService.update_agent(
            self.superuser,
            agent,
            name="new",
            slug="new-slug",
            description="new-desc",
            system_instructions="new-instr",
            available_tools=["t1"],
            permission_required_tools=["t2"],
            badge_config={"x": 1},
            avatar_url="https://example.test/u.png",
            is_active=False,
            is_public=False,
        )
        self.assertTrue(result.ok)
        agent.refresh_from_db()
        self.assertEqual(agent.name, "new")
        self.assertEqual(agent.slug, "new-slug")
        self.assertEqual(agent.description, "new-desc")
        self.assertEqual(agent.system_instructions, "new-instr")
        self.assertEqual(agent.available_tools, ["t1"])
        self.assertEqual(agent.permission_required_tools, ["t2"])
        self.assertEqual(agent.badge_config, {"x": 1})
        self.assertFalse(agent.is_active)
        self.assertFalse(agent.is_public)

    def test_delete_agent_denied_for_non_owner(self):
        agent = AgentConfiguration.objects.create(
            name="del-protected",
            description="d",
            system_instructions="s",
            scope="GLOBAL",
            creator=self.superuser,
        )
        set_permissions_for_obj_to_user(
            self.superuser, agent, [PermissionTypes.CRUD], is_new=True
        )
        result = AgentConfigurationService.delete_agent(self.regular, agent)
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "Agent configuration not found")
        # Row still exists.
        self.assertTrue(AgentConfiguration.objects.filter(pk=agent.pk).exists())

    def test_delete_agent_succeeds_and_drops_row(self):
        agent = AgentConfiguration.objects.create(
            name="to-delete",
            description="d",
            system_instructions="s",
            scope="GLOBAL",
            creator=self.superuser,
        )
        set_permissions_for_obj_to_user(
            self.superuser, agent, [PermissionTypes.CRUD], is_new=True
        )
        result = AgentConfigurationService.delete_agent(self.superuser, agent)
        self.assertTrue(result.ok)
        self.assertFalse(AgentConfiguration.objects.filter(pk=agent.pk).exists())

    def test_search_mentionable_agents_anonymous_empty(self):
        qs = AgentConfigurationService.search_mentionable_agents(AnonymousUser())
        self.assertEqual(qs.count(), 0)

    def test_search_mentionable_agents_filters_by_corpus_and_text(self):
        AgentConfiguration.objects.create(
            name="GlobalSearchHit",
            description="findme",
            system_instructions="s",
            scope=AgentConfiguration.SCOPE_GLOBAL,
            creator=self.superuser,
            is_active=True,
            is_public=True,
        )
        AgentConfiguration.objects.create(
            name="CorpusSearchHit",
            description="findme",
            system_instructions="s",
            scope=AgentConfiguration.SCOPE_CORPUS,
            corpus=self.corpus,
            creator=self.superuser,
            is_active=True,
            is_public=True,
        )
        AgentConfiguration.objects.create(
            name="OtherCorpusAgent",
            description="findme",
            system_instructions="s",
            scope=AgentConfiguration.SCOPE_CORPUS,
            corpus=Corpus.objects.create(
                title="other",
                creator=self.superuser,
                is_public=True,
            ),
            creator=self.superuser,
            is_active=True,
            is_public=True,
        )

        qs = AgentConfigurationService.search_mentionable_agents(
            self.superuser,
            corpus_id=self.corpus.id,
            text_search="findme",
        )
        names = sorted(qs.values_list("name", flat=True))
        self.assertEqual(names, ["CorpusSearchHit", "GlobalSearchHit"])

    def test_get_active_agents_by_slugs_empty_list(self):
        qs = AgentConfigurationService.get_active_agents_by_slugs(
            self.superuser, slugs=[]
        )
        self.assertEqual(qs.count(), 0)

    def test_get_active_agents_by_slugs_returns_matches(self):
        a = AgentConfiguration.objects.create(
            name="slug-agent",
            slug="slug-agent",
            description="d",
            system_instructions="s",
            scope="GLOBAL",
            creator=self.superuser,
            is_active=True,
            is_public=True,
        )
        AgentConfiguration.objects.create(
            name="inactive-agent",
            slug="inactive-agent",
            description="d",
            system_instructions="s",
            scope="GLOBAL",
            creator=self.superuser,
            is_active=False,
            is_public=True,
        )
        slugs = ["slug-agent", "inactive-agent", "nope"]
        qs = AgentConfigurationService.get_active_agents_by_slugs(
            self.superuser, slugs=slugs
        )
        self.assertEqual(list(qs.values_list("pk", flat=True)), [a.pk])

    def test_list_visible_agents_select_relateds_creator_and_corpus(self):
        agent = AgentConfiguration.objects.create(
            name="visible",
            description="d",
            system_instructions="s",
            scope="GLOBAL",
            creator=self.superuser,
            is_public=True,
        )
        qs = AgentConfigurationService.list_visible_agents(self.superuser)
        self.assertIn(agent, list(qs))

    def test_get_agent_by_id_visible_returns_agent(self):
        agent = AgentConfiguration.objects.create(
            name="byid",
            description="d",
            system_instructions="s",
            scope="GLOBAL",
            creator=self.superuser,
            is_public=True,
        )
        result = AgentConfigurationService.get_agent_by_id(self.superuser, agent.pk)
        self.assertEqual(result, agent)

    def test_get_agent_by_id_missing_returns_none(self):
        self.assertIsNone(
            AgentConfigurationService.get_agent_by_id(self.superuser, 99_999_999)
        )


# ---------------------------------------------------------------------------
# AgentActionResultService — internal paths
# ---------------------------------------------------------------------------


class TestAgentActionResultServiceBehavioral(TestCase):
    """Exercise filtering and the corpus-action defence-in-depth branch."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser(
            username="phase5_aar_super",
            email="aar@phase5.test",
            password="x",
        )
        cls.corpus = Corpus.objects.create(
            title="aar-corpus",
            creator=cls.user,
            is_public=True,
        )
        cls.document = Document.objects.create(
            title="aar-doc",
            creator=cls.user,
            file_type="application/pdf",
        )
        cls.action = CorpusAction.objects.create(
            name="ActionWithInstr",
            corpus=cls.corpus,
            creator=cls.user,
            trigger="add_document",
            task_instructions="run me",
        )
        cls.result_completed = AgentActionResult.objects.create(
            corpus_action=cls.action,
            document=cls.document,
            status=AgentActionResult.Status.COMPLETED,
            creator=cls.user,
        )
        # A second document for status-filter variety
        other_doc = Document.objects.create(
            title="aar-other-doc",
            creator=cls.user,
            file_type="application/pdf",
        )
        cls.result_failed = AgentActionResult.objects.create(
            corpus_action=cls.action,
            document=other_doc,
            status=AgentActionResult.Status.FAILED,
            creator=cls.user,
        )
        cls.other_doc_id = other_doc.id

    def test_list_visible_results_no_filters(self):
        qs = AgentActionResultService.list_visible_results(self.user)
        ids = set(qs.values_list("pk", flat=True))
        self.assertEqual(ids, {self.result_completed.pk, self.result_failed.pk})

    def test_list_visible_results_filters_by_corpus_action(self):
        qs = AgentActionResultService.list_visible_results(
            self.user, corpus_action_id=self.action.id
        )
        ids = set(qs.values_list("pk", flat=True))
        self.assertEqual(ids, {self.result_completed.pk, self.result_failed.pk})

    def test_list_visible_results_invisible_corpus_action_returns_empty(self):
        # Use a user that cannot see any CorpusAction
        outsider = User.objects.create_user(
            username="aar_outsider", password="x", email="out@aar.test"
        )
        qs = AgentActionResultService.list_visible_results(
            outsider, corpus_action_id=self.action.id
        )
        self.assertEqual(qs.count(), 0)

    def test_list_visible_results_filters_by_document(self):
        qs = AgentActionResultService.list_visible_results(
            self.user, document_id=self.other_doc_id
        )
        ids = set(qs.values_list("pk", flat=True))
        self.assertEqual(ids, {self.result_failed.pk})

    def test_list_visible_results_filters_by_status(self):
        qs = AgentActionResultService.list_visible_results(
            self.user, status=AgentActionResult.Status.COMPLETED
        )
        ids = set(qs.values_list("pk", flat=True))
        self.assertEqual(ids, {self.result_completed.pk})


# ---------------------------------------------------------------------------
# AnalysisLifecycleService — make_public guard, start, delete
# ---------------------------------------------------------------------------


class TestAnalysisLifecycleServiceBehavioral(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username="phase5_analysis_super",
            email="als@phase5.test",
            password="x",
        )
        cls.regular = User.objects.create_user(
            username="phase5_analysis_reg",
            email="alr@phase5.test",
            password="x",
        )
        cls.corpus = Corpus.objects.create(
            title="als-corpus",
            creator=cls.superuser,
            is_public=True,
        )
        cls.document = Document.objects.create(
            title="als-doc",
            creator=cls.superuser,
            file_type="application/pdf",
            is_public=True,
        )
        cls.analyzer = Analyzer.objects.create(
            id="phase5.als.fake",
            description="fake",
            creator=cls.superuser,
            task_name="phase5.als.fake_task",
        )
        cls.analysis = Analysis.objects.create(
            analyzer=cls.analyzer,
            analyzed_corpus=cls.corpus,
            creator=cls.superuser,
        )
        set_permissions_for_obj_to_user(
            cls.superuser, cls.analysis, [PermissionTypes.ALL]
        )

    def test_make_public_rejects_non_superuser(self):
        result = AnalysisLifecycleService.make_public(self.regular, self.analysis.id)
        self.assertFalse(result.ok)
        self.assertIn("superuser", result.error.lower())

    @patch("opencontractserver.tasks.permissioning_tasks.make_analysis_public_task.si")
    def test_make_public_dispatches_task_for_superuser(self, mock_si):
        mock_si.return_value.apply_async.return_value = None
        result = AnalysisLifecycleService.make_public(self.superuser, self.analysis.id)
        self.assertTrue(result.ok)
        mock_si.assert_called_once_with(analysis_id=self.analysis.id)

    def test_start_document_analysis_requires_target_pk(self):
        result = AnalysisLifecycleService.start_document_analysis(
            self.superuser,
            analyzer_pk=self.analyzer.id,
            document_pk=None,
            corpus_pk=None,
        )
        self.assertFalse(result.ok)
        self.assertIn("must be provided", result.error)

    def test_start_document_analysis_rejects_invisible_document(self):
        result = AnalysisLifecycleService.start_document_analysis(
            self.regular,
            analyzer_pk=self.analyzer.id,
            document_pk=99_999_999,
        )
        self.assertFalse(result.ok)
        self.assertIn("Resource not found", result.error)

    def test_start_document_analysis_rejects_invisible_corpus(self):
        private_corpus = Corpus.objects.create(
            title="private",
            creator=self.superuser,
            is_public=False,
        )
        result = AnalysisLifecycleService.start_document_analysis(
            self.regular,
            analyzer_pk=self.analyzer.id,
            corpus_pk=private_corpus.id,
        )
        self.assertFalse(result.ok)
        self.assertIn("Resource not found", result.error)

    def test_start_document_analysis_rejects_unknown_analyzer(self):
        result = AnalysisLifecycleService.start_document_analysis(
            self.superuser,
            analyzer_pk="no.such.analyzer.id",
            document_pk=self.document.id,
        )
        self.assertFalse(result.ok)
        self.assertIn("Resource not found", result.error)

    @patch("opencontractserver.tasks.corpus_tasks.process_analyzer")
    def test_start_document_analysis_success(self, mock_process):
        new_analysis = Analysis.objects.create(
            analyzer=self.analyzer,
            analyzed_corpus=self.corpus,
            creator=self.superuser,
        )
        mock_process.return_value = new_analysis
        result = AnalysisLifecycleService.start_document_analysis(
            self.superuser,
            analyzer_pk=self.analyzer.id,
            document_pk=self.document.id,
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.value, new_analysis)
        mock_process.assert_called_once()

    @patch("opencontractserver.tasks.corpus_tasks.process_analyzer")
    def test_start_document_analysis_none_from_process_is_failure(self, mock_process):
        # Pin the explicit-failure semantics: when ``process_analyzer`` returns
        # ``None`` (e.g. internal failure / resource exhaustion), the service
        # surfaces a failure rather than ``ok=True, value=None`` so callers
        # can't silently treat it as a successful no-op.
        mock_process.return_value = None
        result = AnalysisLifecycleService.start_document_analysis(
            self.superuser,
            analyzer_pk=self.analyzer.id,
            document_pk=self.document.id,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "Analyzer could not be started.")
        self.assertIsNone(result.value)

    def test_delete_analysis_not_found_for_invisible(self):
        result = AnalysisLifecycleService.delete_analysis(
            self.regular, self.analysis.id
        )
        self.assertFalse(result.ok)
        self.assertIn("not found", result.error.lower())

    def test_delete_analysis_locked_by_another_user(self):
        # Give regular READ on the analysis so the lookup succeeds, then
        # lock it as the superuser to verify the lock-holder check.
        set_permissions_for_obj_to_user(
            self.regular, self.analysis, [PermissionTypes.READ]
        )
        self.analysis.user_lock = self.superuser
        self.analysis.save(update_fields=["user_lock"])
        result = AnalysisLifecycleService.delete_analysis(
            self.regular, self.analysis.id
        )
        self.assertFalse(result.ok)
        self.assertIn("locked by another user", result.error)

    @patch(
        "opencontractserver.tasks.delete_analysis_and_annotations_task.si",
    )
    def test_delete_analysis_dispatches_for_owner(self, mock_si):
        mock_si.return_value.apply_async.return_value = None
        result = AnalysisLifecycleService.delete_analysis(
            self.superuser, self.analysis.id
        )
        self.assertTrue(result.ok)
        mock_si.assert_called_once_with(analysis_pk=self.analysis.id)

    @patch(
        "opencontractserver.tasks.delete_analysis_and_annotations_task.si",
    )
    def test_delete_analysis_threads_request_into_initial_lookup(self, mock_si):
        """Initial visibility lookup must thread ``request`` into the Tier-2 cache.

        Regression for PR #1770 follow-up: the lookup half of the two-step
        check used the bare ``get_for_user_or_none`` helper which has no
        ``request=`` kwarg, silently bypassing the request-scoped cache.
        It now routes through ``cls.get_or_none`` (``BaseService``) so the
        ``request`` is forwarded — the subsequent ``user_can`` call reuses
        the cached entry instead of issuing a duplicate permission query.
        """
        from types import SimpleNamespace

        # ``BaseService.get_or_none`` imports ``get_for_user_or_none`` at
        # module load time, so the patch target is the ``base`` module's
        # local reference, not the ``conventions`` source — patching the
        # source would leave ``BaseService`` calling the unwrapped function.
        from opencontractserver.shared.services import base as base_module

        mock_si.return_value.apply_async.return_value = None
        request = SimpleNamespace()

        with patch.object(
            base_module,
            "get_for_user_or_none",
            wraps=base_module.get_for_user_or_none,
        ) as wrapped_lookup:
            result = AnalysisLifecycleService.delete_analysis(
                self.superuser, self.analysis.id, request=request
            )

        self.assertTrue(result.ok)
        wrapped_lookup.assert_called_once()
        # ``request`` must be threaded through — otherwise the Tier-2
        # permission cache is silently bypassed for the lookup half.
        self.assertIs(wrapped_lookup.call_args.kwargs.get("request"), request)


# ---------------------------------------------------------------------------
# NotificationService — mark_all_read anonymous guard + other reads
# ---------------------------------------------------------------------------


class TestNotificationServiceBehavioral(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="phase5_notif_user",
            email="notif@phase5.test",
            password="x",
        )
        cls.other = User.objects.create_user(
            username="phase5_notif_other",
            email="notif_other@phase5.test",
            password="x",
        )
        # Clean auto-created notifications from signal handlers.
        Notification.objects.filter(recipient=cls.user).delete()
        Notification.objects.filter(recipient=cls.other).delete()
        cls.n1 = Notification.objects.create(
            recipient=cls.user,
            notification_type=NotificationTypeChoices.REPLY,
            is_read=False,
        )
        cls.n2 = Notification.objects.create(
            recipient=cls.user,
            notification_type=NotificationTypeChoices.MENTION,
            is_read=False,
        )

    def test_mark_all_read_anonymous_short_circuits_to_zero(self):
        result = NotificationService.mark_all_read(AnonymousUser())
        self.assertTrue(result.ok)
        self.assertEqual(result.value, 0)

    def test_mark_all_read_none_user_short_circuits_to_zero(self):
        result = NotificationService.mark_all_read(None)
        self.assertTrue(result.ok)
        self.assertEqual(result.value, 0)

    def test_mark_all_read_returns_updated_count(self):
        result = NotificationService.mark_all_read(self.user)
        self.assertTrue(result.ok)
        self.assertEqual(result.value, 2)
        self.assertTrue(
            all(n.is_read for n in Notification.objects.filter(recipient=self.user))
        )

    def test_list_for_user_anonymous_returns_empty(self):
        qs = NotificationService.list_for_user(AnonymousUser())
        self.assertEqual(qs.count(), 0)

    def test_get_for_user_anonymous_returns_none(self):
        self.assertIsNone(NotificationService.get_for_user(AnonymousUser(), self.n1.pk))

    def test_get_for_user_missing_returns_none(self):
        self.assertIsNone(NotificationService.get_for_user(self.user, 99_999_999))

    def test_get_for_user_other_owner_returns_none(self):
        # IDOR: the other user must not see ``self.user``'s notifications.
        self.assertIsNone(NotificationService.get_for_user(self.other, self.n1.pk))

    def test_unread_count_anonymous_zero(self):
        self.assertEqual(NotificationService.unread_count(AnonymousUser()), 0)

    def test_unread_count_user(self):
        # ``setUpTestData`` left two unread for ``self.user``.
        self.assertEqual(NotificationService.unread_count(self.user), 2)

    def test_mark_read_returns_failure_for_missing(self):
        result = NotificationService.mark_read(self.user, 99_999_999)
        self.assertFalse(result.ok)
        self.assertIn("not found", result.error.lower())

    def test_mark_read_success_flips_is_read(self):
        result = NotificationService.mark_read(self.user, self.n1.pk)
        self.assertTrue(result.ok)
        self.n1.refresh_from_db()
        self.assertTrue(self.n1.is_read)

    def test_mark_unread_returns_failure_for_other_owner(self):
        result = NotificationService.mark_unread(self.other, self.n1.pk)
        self.assertFalse(result.ok)
        self.assertIn("not found", result.error.lower())

    def test_mark_unread_success_flips_is_read(self):
        # Force-mark first so mark_unread has work to do.
        self.n1.is_read = True
        self.n1.save(update_fields=["is_read"])
        result = NotificationService.mark_unread(self.user, self.n1.pk)
        self.assertTrue(result.ok)
        self.n1.refresh_from_db()
        self.assertFalse(self.n1.is_read)

    def test_list_for_user_returns_notifications(self):
        qs = NotificationService.list_for_user(self.user)
        ids = set(qs.values_list("pk", flat=True))
        self.assertEqual(ids, {self.n1.pk, self.n2.pk})

    def test_delete_for_user_drops_row(self):
        result = NotificationService.delete_for_user(self.user, self.n2.pk)
        self.assertTrue(result.ok)
        self.assertFalse(Notification.objects.filter(pk=self.n2.pk).exists())

    def test_delete_for_user_failure_for_missing(self):
        result = NotificationService.delete_for_user(self.user, 99_999_999)
        self.assertFalse(result.ok)


# ---------------------------------------------------------------------------
# WorkerAccountService — superuser-guard branches
# ---------------------------------------------------------------------------


class TestWorkerAccountServiceBehavioral(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username="phase5_wa_super",
            email="wa@phase5.test",
            password="x",
        )
        cls.regular = User.objects.create_user(
            username="phase5_wa_reg",
            email="war@phase5.test",
            password="x",
        )

    def test_create_worker_account_requires_superuser(self):
        result = WorkerAccountService.create_worker_account(
            self.regular, name="should-fail"
        )
        self.assertFalse(result.ok)
        self.assertIn("Superuser", result.error)
        self.assertFalse(WorkerAccount.objects.filter(name="should-fail").exists())

    def test_create_worker_account_succeeds_for_superuser(self):
        result = WorkerAccountService.create_worker_account(
            self.superuser, name="phase5-worker", description="hello"
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.value.name, "phase5-worker")
        self.assertEqual(result.value.description, "hello")

    def test_create_worker_account_duplicate_name_failure(self):
        WorkerAccountService.create_worker_account(self.superuser, name="dup-name")
        result = WorkerAccountService.create_worker_account(
            self.superuser, name="dup-name"
        )
        self.assertFalse(result.ok)

    def test_set_active_requires_superuser(self):
        account = WorkerAccount.create_with_user(
            name="set-active-reg", creator=self.superuser
        )
        result = WorkerAccountService.set_active(self.regular, account.id, active=False)
        self.assertFalse(result.ok)
        self.assertIn("Superuser", result.error)
        account.refresh_from_db()
        self.assertTrue(account.is_active)

    def test_set_active_missing_account(self):
        result = WorkerAccountService.set_active(
            self.superuser, 99_999_999, active=False
        )
        self.assertFalse(result.ok)
        self.assertIn("not found", result.error.lower())

    def test_set_active_toggles_state(self):
        account = WorkerAccount.create_with_user(
            name="toggle-worker", creator=self.superuser
        )
        result = WorkerAccountService.set_active(
            self.superuser, account.id, active=False
        )
        self.assertTrue(result.ok)
        account.refresh_from_db()
        self.assertFalse(account.is_active)

    def test_list_visible_accounts_non_superuser_excludes_inactive(self):
        active = WorkerAccount.create_with_user(
            name="visible-active", creator=self.superuser
        )
        inactive = WorkerAccount.create_with_user(
            name="visible-inactive", creator=self.superuser
        )
        inactive.is_active = False
        inactive.save(update_fields=["is_active"])

        qs = WorkerAccountService.list_visible_accounts(self.regular)
        ids = set(qs.values_list("id", flat=True))
        self.assertIn(active.id, ids)
        self.assertNotIn(inactive.id, ids)

    def test_list_visible_accounts_superuser_with_is_active_filter(self):
        WorkerAccount.create_with_user(name="active-su", creator=self.superuser)
        inactive = WorkerAccount.create_with_user(
            name="inactive-su", creator=self.superuser
        )
        inactive.is_active = False
        inactive.save(update_fields=["is_active"])

        qs = WorkerAccountService.list_visible_accounts(self.superuser, is_active=False)
        ids = set(qs.values_list("id", flat=True))
        self.assertIn(inactive.id, ids)
        self.assertNotIn(WorkerAccount.objects.get(name="active-su").id, ids)

    def test_list_visible_accounts_name_contains_filter(self):
        WorkerAccount.create_with_user(name="alpha-account", creator=self.superuser)
        WorkerAccount.create_with_user(name="beta-account", creator=self.superuser)
        qs = WorkerAccountService.list_visible_accounts(
            self.superuser, name_contains="alpha"
        )
        names = list(qs.values_list("name", flat=True))
        self.assertEqual(names, ["alpha-account"])


# ---------------------------------------------------------------------------
# CorpusAccessTokenService — list / create / revoke
# ---------------------------------------------------------------------------


class TestCorpusAccessTokenServiceBehavioral(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username="phase5_cat_super",
            email="cat@phase5.test",
            password="x",
        )
        cls.regular = User.objects.create_user(
            username="phase5_cat_reg",
            email="catr@phase5.test",
            password="x",
        )
        cls.corpus = Corpus.objects.create(title="cat-corpus", creator=cls.superuser)
        cls.account = WorkerAccount.create_with_user(
            name="cat-worker", creator=cls.superuser
        )

    def test_list_for_corpus_not_found_for_non_owner(self):
        result = CorpusAccessTokenService.list_for_corpus(self.regular, self.corpus.id)
        self.assertFalse(result.ok)
        self.assertIn("Not found", result.error)

    def test_list_for_corpus_owner_with_is_active_filter(self):
        token_active, _ = CorpusAccessToken.create_token(
            worker_account=self.account, corpus=self.corpus
        )
        token_inactive, _ = CorpusAccessToken.create_token(
            worker_account=self.account, corpus=self.corpus
        )
        token_inactive.is_active = False
        token_inactive.save(update_fields=["is_active"])

        result = CorpusAccessTokenService.list_for_corpus(
            self.superuser, self.corpus.id, is_active=True
        )
        self.assertTrue(result.ok)
        ids = set(result.value.values_list("id", flat=True))
        self.assertIn(token_active.id, ids)
        self.assertNotIn(token_inactive.id, ids)

    def test_create_token_corpus_not_found(self):
        # IDOR-safe: a nonexistent corpus and a corpus the caller doesn't own
        # both surface the same "Not found or permission denied." response so
        # the caller cannot distinguish missing-pk from forbidden-pk.
        result = CorpusAccessTokenService.create_token(
            self.superuser,
            worker_account_id=self.account.id,
            corpus_id=99_999_999,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "Not found or permission denied.")

    def test_create_token_permission_denied(self):
        result = CorpusAccessTokenService.create_token(
            self.regular,
            worker_account_id=self.account.id,
            corpus_id=self.corpus.id,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "Not found or permission denied.")

    def test_create_token_worker_account_not_found(self):
        result = CorpusAccessTokenService.create_token(
            self.superuser,
            worker_account_id=99_999_999,
            corpus_id=self.corpus.id,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "Worker account not found.")

    def test_create_token_success(self):
        result = CorpusAccessTokenService.create_token(
            self.superuser,
            worker_account_id=self.account.id,
            corpus_id=self.corpus.id,
            rate_limit_per_minute=42,
        )
        self.assertTrue(result.ok)
        token, plaintext = result.value
        self.assertEqual(token.corpus_id, self.corpus.id)
        self.assertEqual(token.rate_limit_per_minute, 42)
        self.assertEqual(len(plaintext), 64)

    def test_revoke_token_not_found(self):
        result = CorpusAccessTokenService.revoke_token(self.superuser, 99_999_999)
        self.assertFalse(result.ok)
        self.assertIn("Not found", result.error)

    def test_revoke_token_marks_inactive(self):
        token, _ = CorpusAccessToken.create_token(
            worker_account=self.account, corpus=self.corpus
        )
        result = CorpusAccessTokenService.revoke_token(self.superuser, token.id)
        self.assertTrue(result.ok)
        token.refresh_from_db()
        self.assertFalse(token.is_active)


# ---------------------------------------------------------------------------
# WorkerDocumentUploadService — list / pagination
# ---------------------------------------------------------------------------


class TestWorkerDocumentUploadServiceBehavioral(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username="phase5_wdu_super",
            email="wdu@phase5.test",
            password="x",
        )
        cls.regular = User.objects.create_user(
            username="phase5_wdu_reg",
            email="wdur@phase5.test",
            password="x",
        )
        cls.corpus = Corpus.objects.create(title="wdu-corpus", creator=cls.superuser)
        cls.account = WorkerAccount.create_with_user(
            name="wdu-worker", creator=cls.superuser
        )
        cls.token, _ = CorpusAccessToken.create_token(
            worker_account=cls.account, corpus=cls.corpus
        )
        cls.u_pending = WorkerDocumentUpload.objects.create(
            corpus_access_token=cls.token,
            corpus=cls.corpus,
            metadata={"title": "p"},
            status="PENDING",
        )
        cls.u_completed = WorkerDocumentUpload.objects.create(
            corpus_access_token=cls.token,
            corpus=cls.corpus,
            metadata={"title": "c"},
            status="COMPLETED",
        )

    def test_list_for_corpus_not_found_for_non_owner(self):
        result = WorkerDocumentUploadService.list_for_corpus(
            self.regular, self.corpus.id
        )
        self.assertFalse(result.ok)
        self.assertIn("Not found", result.error)

    def test_list_for_corpus_status_filter(self):
        result = WorkerDocumentUploadService.list_for_corpus(
            self.superuser, self.corpus.id, status="pending"
        )
        self.assertTrue(result.ok)
        page, total, limit, offset = result.value
        ids = [u.id for u in page]
        self.assertEqual(ids, [self.u_pending.id])
        self.assertEqual(total, 1)
        self.assertEqual(offset, 0)
        self.assertGreater(limit, 0)

    def test_list_for_corpus_limit_offset(self):
        result = WorkerDocumentUploadService.list_for_corpus(
            self.superuser,
            self.corpus.id,
            limit=1,
            offset=0,
        )
        self.assertTrue(result.ok)
        page, total, limit, offset = result.value
        self.assertEqual(len(list(page)), 1)
        self.assertEqual(total, 2)
        self.assertEqual(limit, 1)
        self.assertEqual(offset, 0)

    def test_list_for_corpus_unbounded_uses_default_limit(self):
        result = WorkerDocumentUploadService.list_for_corpus(
            self.superuser, self.corpus.id
        )
        self.assertTrue(result.ok)
        _, total, limit, offset = result.value
        self.assertEqual(total, 2)
        # WORKER_UPLOADS_QUERY_LIMIT cap applied.
        self.assertGreater(limit, 0)


# ---------------------------------------------------------------------------
# UserFeedbackService — internal behaviour
# ---------------------------------------------------------------------------


class TestUserFeedbackServiceBehavioral(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="phase5_fb_user", email="fb@phase5.test", password="x"
        )
        cls.other = User.objects.create_user(
            username="phase5_fb_other", email="fbo@phase5.test", password="x"
        )
        cls.corpus = Corpus.objects.create(
            title="fb-corpus",
            creator=cls.user,
            is_public=True,
            allow_comments=True,
        )
        cls.document = Document.objects.create(
            title="fb-doc",
            creator=cls.user,
            file_type="application/pdf",
            is_public=True,
        )
        cls.label = AnnotationLabel.objects.create(
            text="fb-label",
            creator=cls.user,
            label_type=LabelType.TOKEN_LABEL,
        )
        cls.annotation = Annotation.objects.create(
            page=1,
            raw_text="phase5 fb",
            annotation_label=cls.label,
            document=cls.document,
            corpus=cls.corpus,
            creator=cls.user,
            is_public=True,
        )

    def test_approve_annotation_missing_annotation_idor_safe(self):
        result = UserFeedbackService.approve_annotation(
            self.user, annotation_pk=99_999_999
        )
        self.assertFalse(result.ok)
        self.assertIn("permission", result.error.lower())

    def test_approve_annotation_creates_feedback_row(self):
        result = UserFeedbackService.approve_annotation(
            self.user, self.annotation.pk, comment="ok"
        )
        self.assertTrue(result.ok)
        fb = UserFeedback.objects.get(commented_annotation=self.annotation)
        self.assertTrue(fb.approved)
        self.assertFalse(fb.rejected)
        self.assertEqual(fb.comment, "ok")

    def test_reject_annotation_updates_existing_row(self):
        # First approve, then reject the same annotation → service should
        # toggle approved=False/rejected=True on the existing row.
        UserFeedbackService.approve_annotation(
            self.user, self.annotation.pk, comment="first"
        )
        result = UserFeedbackService.reject_annotation(
            self.user, self.annotation.pk, comment="now bad"
        )
        self.assertTrue(result.ok)
        fb = UserFeedback.objects.get(commented_annotation=self.annotation)
        self.assertFalse(fb.approved)
        self.assertTrue(fb.rejected)
        self.assertEqual(fb.comment, "now bad")

    def test_reject_annotation_preserves_comment_when_none_passed(self):
        UserFeedbackService.approve_annotation(
            self.user, self.annotation.pk, comment="keep me"
        )
        result = UserFeedbackService.reject_annotation(self.user, self.annotation.pk)
        self.assertTrue(result.ok)
        fb = UserFeedback.objects.get(commented_annotation=self.annotation)
        self.assertEqual(fb.comment, "keep me")
