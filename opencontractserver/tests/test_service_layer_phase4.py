"""Structural tests for the Phase 4 service-layer migration.

Phase 4 of the service-layer centralization roadmap migrated the four
remaining query optimizers (``documents``, ``conversations``, ``users``,
``badges``) into per-app ``services/`` packages and retired the standalone
``query_optimizer.py`` modules. See
docs/refactor_plans/2026-05-19-service-layer-centralization-design.md.

These tests pin the *structure* of that migration — every migrated service
is importable from its package, inherits ``BaseService``, and the retired
optimizer modules no longer exist. The behavioural coverage (visibility,
permission filtering, request-level caching) lives in the per-app test
modules those optimizers always had — now exercising the service classes:
``test_document_actions_permissions``, ``test_document_relationship_*``,
``test_document_version_count_optimizer``, ``test_conversation_permissions``,
``test_user_visibility``, ``test_badge_visibility``.
"""

from __future__ import annotations

import importlib

from django.test import SimpleTestCase

from opencontractserver.shared.services import BaseService


class TestPhase4ServicePackages(SimpleTestCase):
    """SCENARIO: the migrated optimizers are now ``BaseService`` subclasses.

    BUSINESS RULE: every per-app service is reachable from its ``services/``
    package root and inherits the shared ``BaseService`` machinery, so the
    package — not an internal module path — is the stable public import.
    """

    def test_documents_services_importable_and_inherit_base_service(self):
        from opencontractserver.documents.services import (
            DocumentActionsService,
            DocumentRelationshipService,
            DocumentVersionService,
        )

        for service in (
            DocumentActionsService,
            DocumentRelationshipService,
            DocumentVersionService,
        ):
            self.assertTrue(issubclass(service, BaseService))

    def test_conversations_service_importable_and_inherits_base_service(self):
        from opencontractserver.conversations.services import ConversationService

        self.assertTrue(issubclass(ConversationService, BaseService))

    def test_users_service_importable_and_inherits_base_service(self):
        from opencontractserver.users.services import UserService

        self.assertTrue(issubclass(UserService, BaseService))

    def test_badges_service_importable_and_inherits_base_service(self):
        from opencontractserver.badges.services import BadgeService

        self.assertTrue(issubclass(BadgeService, BaseService))

    def test_package_root_reexports_match_module_definitions(self):
        """The package ``__init__`` re-export IS the module's class object."""
        from opencontractserver.documents.services import DocumentRelationshipService
        from opencontractserver.documents.services.relationships import (
            DocumentRelationshipService as RelationshipServiceFromModule,
        )

        self.assertIs(DocumentRelationshipService, RelationshipServiceFromModule)

    def test_users_package_reexports_requesting_user_alias(self):
        """The ``RequestingUser`` type alias is re-exported alongside the service."""
        from opencontractserver.users.services import RequestingUser

        self.assertIsNotNone(RequestingUser)


class TestPhase4RetiredOptimizerModules(SimpleTestCase):
    """SCENARIO: the standalone ``query_optimizer.py`` modules are retired.

    BUSINESS RULE: Phase 4 fully replaces the optimizer modules — leaving a
    dead module behind would violate the no-dead-code rule and let callers
    keep importing the retired path.
    """

    def test_retired_query_optimizer_modules_no_longer_importable(self):
        for module_path in (
            "opencontractserver.documents.query_optimizer",
            "opencontractserver.conversations.query_optimizer",
            "opencontractserver.users.query_optimizer",
            "opencontractserver.badges.query_optimizer",
        ):
            with self.assertRaises(
                ModuleNotFoundError, msg=f"{module_path} should be retired"
            ):
                importlib.import_module(module_path)


class TestPhase4RequestThreadingConvention(SimpleTestCase):
    """SCENARIO: every public service method threads ``request`` keyword-only.

    BUSINESS RULE: Phase 4 standardises request threading onto the
    ``BaseService`` convention — ``request`` is an optional keyword-only
    parameter, retiring the legacy ``context=`` and instance-based
    ``get_request_optimizer(request)`` styles.
    """

    def test_service_methods_accept_request_keyword_only(self):
        import inspect

        from opencontractserver.badges.services import BadgeService
        from opencontractserver.conversations.services import ConversationService
        from opencontractserver.documents.services import (
            DocumentActionsService,
            DocumentRelationshipService,
            DocumentVersionService,
        )
        from opencontractserver.users.services import UserService

        # (service, method name) pairs whose public surface threads ``request``.
        request_threaded_methods = [
            (DocumentActionsService, "get_document_actions"),
            (DocumentActionsService, "get_corpus_actions_for_corpus"),
            (DocumentActionsService, "get_extracts_for_document"),
            (DocumentActionsService, "get_analysis_rows_for_document"),
            (DocumentRelationshipService, "get_relationship_counts_by_document"),
            (DocumentRelationshipService, "get_visible_relationships"),
            (DocumentRelationshipService, "get_relationships_for_document"),
            (DocumentRelationshipService, "get_relationship_by_id"),
            (DocumentRelationshipService, "user_has_permission"),
            (DocumentVersionService, "get_version_counts_by_tree"),
            (ConversationService, "check_conversation_visibility"),
            (ConversationService, "get_threads_for_corpus"),
            (ConversationService, "get_threads_for_document"),
            (ConversationService, "get_chats_for_user"),
            (ConversationService, "get_corpus_conversation_counts"),
            (UserService, "get_visible_users"),
            (UserService, "check_user_visibility"),
            (UserService, "get_users_for_mention"),
            (BadgeService, "get_visible_user_badges"),
            (BadgeService, "check_user_badge_visibility"),
            (BadgeService, "get_badges_for_user"),
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
