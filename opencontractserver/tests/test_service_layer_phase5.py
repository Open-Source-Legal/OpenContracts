"""Structural tests for the Phase 5 service-layer migration.

Phase 5 of the service-layer centralization roadmap fills the coverage gaps
left by Phases 1–4: the five models that still hand-rolled permission
composition inline (``agents``, ``analyzer`` lifecycle, ``notifications``,
``feedback``, ``worker_uploads``) now have per-app ``services/`` packages.

These tests pin the *structure* of that migration — every new service is
importable from its package, inherits ``BaseService``, and public methods
thread ``request`` as a keyword-only argument so the Phase-4 convention is
applied uniformly. The behavioural coverage lives in the per-app GraphQL /
model tests those flows already had — they exercise the same surface, now
wired through the services.

See ``docs/refactor_plans/2026-05-23-service-layer-phase5-gap-models-plan.md``.
"""

from __future__ import annotations

import inspect

from django.test import SimpleTestCase

from opencontractserver.shared.services import BaseService


class TestPhase5ServicePackages(SimpleTestCase):
    """SCENARIO: every gap-model service is importable + inherits BaseService.

    BUSINESS RULE: the per-app ``services/`` package is the stable public
    import path. Each service inherits ``BaseService`` so the shared
    machinery (request threading, ``log_action``, IDOR-safe lookup helpers)
    is uniformly available.
    """

    def test_agents_services_importable_and_inherit_base_service(self):
        from opencontractserver.agents.services import (
            AgentActionResultService,
            AgentConfigurationService,
        )

        self.assertTrue(issubclass(AgentConfigurationService, BaseService))
        self.assertTrue(issubclass(AgentActionResultService, BaseService))

    def test_analyzer_lifecycle_service_importable_and_inherits_base_service(self):
        from opencontractserver.analyzer.services import AnalysisLifecycleService

        self.assertTrue(issubclass(AnalysisLifecycleService, BaseService))

    def test_notifications_service_importable_and_inherits_base_service(self):
        from opencontractserver.notifications.services import NotificationService

        self.assertTrue(issubclass(NotificationService, BaseService))

    def test_feedback_service_importable_and_inherits_base_service(self):
        from opencontractserver.feedback.services import UserFeedbackService

        self.assertTrue(issubclass(UserFeedbackService, BaseService))

    def test_worker_uploads_services_importable_and_inherit_base_service(self):
        from opencontractserver.worker_uploads.services import (
            CorpusAccessTokenService,
            WorkerAccountService,
            WorkerDocumentUploadService,
        )

        for service in (
            WorkerAccountService,
            CorpusAccessTokenService,
            WorkerDocumentUploadService,
        ):
            self.assertTrue(issubclass(service, BaseService))


class TestPhase5RequestThreadingConvention(SimpleTestCase):
    """SCENARIO: every Phase-5 public service method threads ``request`` keyword-only.

    BUSINESS RULE: Phase 4 standardised request threading onto the
    ``BaseService`` convention — ``request`` is an optional keyword-only
    parameter. Phase 5 services adopt the same convention so a caller does
    not have to remember which service uses which style.
    """

    def test_phase5_service_methods_accept_request_keyword_only(self):
        from opencontractserver.agents.services import (
            AgentActionResultService,
            AgentConfigurationService,
        )
        from opencontractserver.analyzer.services import AnalysisLifecycleService
        from opencontractserver.feedback.services import UserFeedbackService
        from opencontractserver.notifications.services import NotificationService
        from opencontractserver.worker_uploads.services import (
            CorpusAccessTokenService,
            WorkerAccountService,
            WorkerDocumentUploadService,
        )

        request_threaded_methods = [
            (AgentConfigurationService, "list_visible_agents"),
            (AgentConfigurationService, "get_agent_by_id"),
            (AgentConfigurationService, "create_agent"),
            (AgentConfigurationService, "update_agent"),
            (AgentConfigurationService, "delete_agent"),
            (AgentActionResultService, "list_visible_results"),
            (AnalysisLifecycleService, "make_public"),
            (AnalysisLifecycleService, "start_document_analysis"),
            (AnalysisLifecycleService, "delete_analysis"),
            (NotificationService, "list_for_user"),
            (NotificationService, "get_for_user"),
            (NotificationService, "unread_count"),
            (NotificationService, "mark_read"),
            (NotificationService, "mark_unread"),
            (NotificationService, "mark_all_read"),
            (NotificationService, "delete_for_user"),
            (UserFeedbackService, "approve_annotation"),
            (UserFeedbackService, "reject_annotation"),
            (WorkerAccountService, "list_visible_accounts"),
            (WorkerAccountService, "create_worker_account"),
            (WorkerAccountService, "set_active"),
            (CorpusAccessTokenService, "list_for_corpus"),
            (CorpusAccessTokenService, "create_token"),
            (CorpusAccessTokenService, "revoke_token"),
            (WorkerDocumentUploadService, "list_for_corpus"),
        ]

        for service, method_name in request_threaded_methods:
            signature = inspect.signature(getattr(service, method_name))
            with self.subTest(service=service.__name__, method=method_name):
                self.assertIn(
                    "request",
                    signature.parameters,
                    f"{service.__name__}.{method_name} must accept request",
                )
                parameter = signature.parameters["request"]
                self.assertEqual(
                    parameter.kind,
                    inspect.Parameter.KEYWORD_ONLY,
                    f"{service.__name__}.{method_name} request must be keyword-only",
                )
                self.assertIsNone(
                    parameter.default,
                    f"{service.__name__}.{method_name} request must default to None",
                )


class TestPhase5NotificationServiceSimpleOwnership(SimpleTestCase):
    """SCENARIO: ``NotificationService`` uses simple ownership, not ``user_can``.

    BUSINESS RULE: ``Notification`` does not implement ``user_can`` /
    ``visible_to_user`` (the design-doc §3 exception — simple ownership
    model, no ``AnnotatePermissionsForReadMixin``). The service must
    therefore NOT call ``BaseService.get_or_none`` / ``filter_visible`` /
    ``require_permission`` (all of which delegate to those manager methods).
    Instead it must expose its own ownership-filtered lookup.

    This test asserts the public IDOR-safe lookup exists; the behavioural
    coverage (returning ``None`` for both not-found and another-user-owned
    rows) lives in ``test_notification_graphql.py``.
    """

    def test_notification_service_exposes_simple_ownership_lookup(self):
        from opencontractserver.notifications.services import NotificationService

        # The simple-ownership lookup must be named ``get_for_user`` (the
        # service's IDOR-safe entry point) and must NOT be inherited
        # ``get_or_none`` from ``BaseService`` (which would fail for
        # ``Notification`` since the manager has no ``user_can``).
        self.assertTrue(hasattr(NotificationService, "get_for_user"))
        # ``BaseService.get_or_none`` exists but the service must not call
        # it for Notification — confirm the method is implemented locally
        # on NotificationService (not just inherited).
        self.assertIn("get_for_user", NotificationService.__dict__)


class TestPhase5RetiredInlinePatternsHaveServiceCallers(SimpleTestCase):
    """SCENARIO: migrated GraphQL files import the new services.

    BUSINESS RULE: Phase 5 migrates the gap-model call sites onto the new
    services. This test pins those imports so a future refactor cannot
    silently regress the GraphQL surface back onto inline composition
    without breaking this test.
    """

    def test_migrated_graphql_files_import_phase5_services(self):
        # Each migrated GraphQL module must reference at least one of the
        # Phase-5 services in its source (either as a top-level import or as
        # a lazy in-function import — the latter is used in modules with
        # circular-import constraints). A bare ``assertIsNotNone(module)``
        # would still pass after a regression to inline composition; scanning
        # the source for the service import line catches that silent revert.
        import inspect

        from config.graphql import (
            action_queries,
            agent_mutations,
            analysis_mutations,
            annotation_mutations,
            conversation_types,
            notification_mutations,
            search_queries,
            social_queries,
            worker_mutations,
            worker_queries,
        )

        module_to_expected_services = {
            action_queries: ["AgentActionResultService"],
            agent_mutations: ["AgentConfigurationService"],
            analysis_mutations: ["AnalysisLifecycleService"],
            annotation_mutations: ["UserFeedbackService"],
            conversation_types: ["AgentConfigurationService"],
            notification_mutations: ["NotificationService"],
            search_queries: ["AgentConfigurationService"],
            social_queries: [
                "AgentConfigurationService",
                "NotificationService",
            ],
            worker_mutations: [
                "CorpusAccessTokenService",
                "WorkerAccountService",
            ],
            worker_queries: [
                "CorpusAccessTokenService",
                "WorkerAccountService",
                "WorkerDocumentUploadService",
            ],
        }
        for module, expected_services in module_to_expected_services.items():
            source = inspect.getsource(module)
            for service_name in expected_services:
                with self.subTest(module=module.__name__, service=service_name):
                    self.assertIn(
                        service_name,
                        source,
                        f"{module.__name__} must reference {service_name} so "
                        "the service-layer migration cannot silently regress "
                        "to inline composition.",
                    )
