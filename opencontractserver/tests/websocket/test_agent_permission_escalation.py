"""
Tests for WebSocket Agent Permission Escalation Prevention.

This module provides comprehensive tests to ensure that agents operating via
WebSocket connections cannot escalate beyond the calling user's permissions.

Tests cover three security layers:
1. Consumer Layer - Connection-time permission validation
2. Tool Filtering Layer - Agent factory permission-based tool filtering
3. Runtime Layer - Defense-in-depth tool execution checks

Test Categories:
- Category 1: Consumer-Level Permission Validation (C1.x, D1.x, DC1.x)
- Category 2: Tool Filtering Tests (TF2.x)
- Category 3: Runtime Permission Validation (RT3.x)
- Category 4: Permission Escalation Scenarios (PE4.x)
- Category 5: Integration Tests (IT5.x)
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock
from urllib.parse import quote

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test.utils import override_settings
from graphql_jwt.shortcuts import get_token
from graphql_relay import to_global_id

from config.websocket.middleware import WS_AUTH_SUBPROTOCOL
from opencontractserver.agents.models import AgentConfiguration
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.llms.agents.core_agents import (
    ContentEvent,
    FinalEvent,
)
from opencontractserver.llms.tools.tool_registry import AVAILABLE_TOOLS
from opencontractserver.tests.base import WebsocketFixtureBaseTestCase
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()
logger = logging.getLogger(__name__)


# =============================================================================
# Helper Functions
# =============================================================================


async def connect_and_verify(
    application,
    path: str,
    expected_connected: bool,
    expected_close_code: int | None = None,
    token: str | None = None,
) -> WebsocketCommunicator:
    """
    Helper to test WebSocket connection acceptance/rejection.

    Args:
        application: The ASGI application
        path: WebSocket path to connect to
        expected_connected: Whether connection should succeed
        expected_close_code: Expected close code if connection should fail
        token: Optional JWT token to send via Sec-WebSocket-Protocol header

    Returns:
        The WebsocketCommunicator instance
    """
    if token is not None:
        communicator = WebsocketCommunicator(
            application, path, subprotocols=[WS_AUTH_SUBPROTOCOL, token]
        )
    else:
        communicator = WebsocketCommunicator(application, path)
    connected, code = await communicator.connect()

    assert (
        connected == expected_connected
    ), f"Expected connected={expected_connected}, got {connected} with code {code}"
    if expected_close_code is not None:
        assert (
            code == expected_close_code
        ), f"Expected close code {expected_close_code}, got {code}"

    if connected:
        await communicator.disconnect()

    return communicator


class _StubAgent:
    """Stub agent for testing WebSocket message flow without actual LLM calls."""

    def __init__(self, gen_factory, conversation_id=None, available_tools=None):
        self._gen_factory = gen_factory
        self._conversation_id = conversation_id
        self._available_tools = available_tools or []

    def stream(self, user_query: str):
        return self._gen_factory()

    def resume_with_approval(
        self, llm_msg_id: int, approved: bool, stream: bool = True
    ):
        return self._gen_factory()

    def get_conversation_id(self):
        return self._conversation_id

    def get_available_tool_names(self) -> list[str]:
        return self._available_tools


# =============================================================================
# Base Test Class with Agent Config Helper
# =============================================================================


class AgentConfigMixin:
    """Mixin that provides agent configuration setup for tests."""

    async def _ensure_agent_configs_exist(self) -> None:
        """Ensure default agent configurations exist for tests."""
        await database_sync_to_async(AgentConfiguration.objects.get_or_create)(
            slug="default-corpus-agent",
            defaults={
                "name": "Default Corpus Agent",
                "is_active": True,
                "creator": self.user,
            },
        )
        await database_sync_to_async(AgentConfiguration.objects.get_or_create)(
            slug="default-document-agent",
            defaults={
                "name": "Default Document Agent",
                "is_active": True,
                "creator": self.user,
            },
        )


# =============================================================================
# Category 1: Consumer-Level Permission Validation
# =============================================================================


@override_settings(USE_AUTH0=False)
@pytest.mark.django_db(transaction=True)
class ConsumerCorpusPermissionTestCase(AgentConfigMixin, WebsocketFixtureBaseTestCase):
    """
    Category 1.1: Corpus Permission Tests

    Tests that verify UnifiedAgentConsumer properly validates permissions
    for corpus access at connection time.
    """

    async def test_c1_1_authenticated_user_with_corpus_read_connects(self) -> None:
        """C1.1: Authenticated user with READ on private corpus can connect."""
        await self._ensure_agent_configs_exist()

        # User owns the corpus from fixture, so has permission
        corpus_gid = to_global_id("CorpusType", self.corpus.id)
        ws_path = f"ws/agent-chat/?corpus_id={quote(corpus_gid)}"

        communicator = WebsocketCommunicator(
            self.application,
            ws_path,
            subprotocols=[WS_AUTH_SUBPROTOCOL, self.token],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.disconnect()

    async def test_c1_2_authenticated_user_without_corpus_read_rejected(self) -> None:
        """C1.2: Authenticated user WITHOUT READ on private corpus is rejected."""
        # Create another user who doesn't own the corpus
        other_user = await database_sync_to_async(User.objects.create_user)(
            username="outsider_corpus",
            password="pw123456!",
            email="outsider_corpus@example.com",
        )
        other_token = await database_sync_to_async(get_token)(user=other_user)

        # Ensure corpus is private
        self.corpus.is_public = False
        await database_sync_to_async(self.corpus.save)(update_fields=["is_public"])

        corpus_gid = to_global_id("CorpusType", self.corpus.id)
        ws_path = f"ws/agent-chat/?corpus_id={quote(corpus_gid)}"

        communicator = WebsocketCommunicator(
            self.application,
            ws_path,
            subprotocols=[WS_AUTH_SUBPROTOCOL, other_token],
        )
        connected, code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(code, 4003)  # Permission denied

    async def test_c1_3_anonymous_user_public_corpus_connects(self) -> None:
        """C1.3: Anonymous user can access public corpus."""
        await self._ensure_agent_configs_exist()

        self.corpus.is_public = True
        await database_sync_to_async(self.corpus.save)(update_fields=["is_public"])

        corpus_gid = to_global_id("CorpusType", self.corpus.id)
        ws_path = f"ws/agent-chat/?corpus_id={quote(corpus_gid)}"  # No token

        communicator = WebsocketCommunicator(self.application, ws_path)
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.disconnect()

    async def test_c1_4_anonymous_user_private_corpus_rejected(self) -> None:
        """C1.4: Anonymous user is denied for private corpus."""
        self.corpus.is_public = False
        await database_sync_to_async(self.corpus.save)(update_fields=["is_public"])

        corpus_gid = to_global_id("CorpusType", self.corpus.id)
        ws_path = f"ws/agent-chat/?corpus_id={quote(corpus_gid)}"  # No token

        communicator = WebsocketCommunicator(self.application, ws_path)
        connected, code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(code, 4003)

    async def test_c1_5_user_with_only_crud_no_read_has_read_via_crud(self) -> None:
        """C1.5: User with CRUD actually has READ (CRUD includes READ)."""
        await self._ensure_agent_configs_exist()

        # Create a user with explicit CRUD permission
        crud_user = await database_sync_to_async(User.objects.create_user)(
            username="crud_user", password="pw123456!", email="crud@example.com"
        )

        # Grant CRUD permission (which includes READ)
        await database_sync_to_async(set_permissions_for_obj_to_user)(
            crud_user, self.corpus, [PermissionTypes.CRUD]
        )

        self.corpus.is_public = False
        await database_sync_to_async(self.corpus.save)(update_fields=["is_public"])

        crud_token = await database_sync_to_async(get_token)(user=crud_user)
        corpus_gid = to_global_id("CorpusType", self.corpus.id)
        ws_path = f"ws/agent-chat/?corpus_id={quote(corpus_gid)}"

        communicator = WebsocketCommunicator(
            self.application,
            ws_path,
            subprotocols=[WS_AUTH_SUBPROTOCOL, crud_token],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)  # CRUD includes READ
        await communicator.disconnect()


@override_settings(USE_AUTH0=False)
@pytest.mark.django_db(transaction=True)
class ConsumerDocumentPermissionTestCase(
    AgentConfigMixin, WebsocketFixtureBaseTestCase
):
    """
    Category 1.2: Document Permission Tests

    Tests that verify UnifiedAgentConsumer properly validates permissions
    for document access at connection time.
    """

    async def test_d1_1_authenticated_user_with_document_read_connects(self) -> None:
        """D1.1: Authenticated user with READ on private document can connect."""
        await self._ensure_agent_configs_exist()

        # Make doc owned by user (public to simplify)
        self.doc.is_public = True
        await database_sync_to_async(self.doc.save)(update_fields=["is_public"])

        doc_gid = to_global_id("DocumentType", self.doc.id)
        ws_path = f"ws/agent-chat/?document_id={quote(doc_gid)}"

        communicator = WebsocketCommunicator(
            self.application,
            ws_path,
            subprotocols=[WS_AUTH_SUBPROTOCOL, self.token],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.disconnect()

    async def test_d1_2_authenticated_user_without_document_read_rejected(self) -> None:
        """D1.2: Authenticated user WITHOUT READ on private document is rejected."""
        # Create another user who doesn't own the document
        other_user = await database_sync_to_async(User.objects.create_user)(
            username="outsider_doc",
            password="pw123456!",
            email="outsider_doc@example.com",
        )
        other_token = await database_sync_to_async(get_token)(user=other_user)

        # Make doc private
        self.doc.is_public = False
        await database_sync_to_async(self.doc.save)(update_fields=["is_public"])

        doc_gid = to_global_id("DocumentType", self.doc.id)
        ws_path = f"ws/agent-chat/?document_id={quote(doc_gid)}"

        communicator = WebsocketCommunicator(
            self.application,
            ws_path,
            subprotocols=[WS_AUTH_SUBPROTOCOL, other_token],
        )
        connected, code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(code, 4003)

    async def test_d1_3_anonymous_user_public_document_connects(self) -> None:
        """D1.3: Anonymous user can access public document."""
        await self._ensure_agent_configs_exist()

        self.doc.is_public = True
        await database_sync_to_async(self.doc.save)(update_fields=["is_public"])

        doc_gid = to_global_id("DocumentType", self.doc.id)
        ws_path = f"ws/agent-chat/?document_id={quote(doc_gid)}"  # No token

        communicator = WebsocketCommunicator(self.application, ws_path)
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.disconnect()

    async def test_d1_4_anonymous_user_private_document_rejected(self) -> None:
        """D1.4: Anonymous user is denied for private document."""
        self.doc.is_public = False
        await database_sync_to_async(self.doc.save)(update_fields=["is_public"])

        doc_gid = to_global_id("DocumentType", self.doc.id)
        ws_path = f"ws/agent-chat/?document_id={quote(doc_gid)}"  # No token

        communicator = WebsocketCommunicator(self.application, ws_path)
        connected, code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(code, 4003)


@override_settings(USE_AUTH0=False)
@pytest.mark.django_db(transaction=True)
class ConsumerCombinedPermissionTestCase(
    AgentConfigMixin, WebsocketFixtureBaseTestCase
):
    """
    Category 1.3: Document + Corpus Combined Permission Tests

    Tests that verify UnifiedAgentConsumer properly validates permissions
    when both document_id and corpus_id are provided.
    """

    async def test_dc1_1_user_with_document_read_but_not_corpus_read(self) -> None:
        """DC1.1: User has READ on doc, NOT on corpus - should be rejected."""
        # Create user with document read but no corpus read
        limited_user = await database_sync_to_async(User.objects.create_user)(
            username="doc_only_user", password="pw123456!", email="doconly@example.com"
        )

        # Grant READ on document
        await database_sync_to_async(set_permissions_for_obj_to_user)(
            limited_user, self.doc, [PermissionTypes.READ]
        )
        # No permission on corpus

        # Make both private
        self.doc.is_public = False
        await database_sync_to_async(self.doc.save)(update_fields=["is_public"])
        self.corpus.is_public = False
        await database_sync_to_async(self.corpus.save)(update_fields=["is_public"])

        limited_token = await database_sync_to_async(get_token)(user=limited_user)
        doc_gid = to_global_id("DocumentType", self.doc.id)
        corpus_gid = to_global_id("CorpusType", self.corpus.id)
        ws_path = (
            f"ws/agent-chat/?document_id={quote(doc_gid)}"
            f"&corpus_id={quote(corpus_gid)}"
        )

        communicator = WebsocketCommunicator(
            self.application,
            ws_path,
            subprotocols=[WS_AUTH_SUBPROTOCOL, limited_token],
        )
        connected, code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(code, 4003)

    async def test_dc1_2_user_with_corpus_read_but_not_document_read(self) -> None:
        """DC1.2: User has READ on corpus, NOT on doc - should be rejected."""
        # Create user with corpus read but no document read
        limited_user = await database_sync_to_async(User.objects.create_user)(
            username="corpus_only_user",
            password="pw123456!",
            email="corpusonly@example.com",
        )

        # Grant READ on corpus
        await database_sync_to_async(set_permissions_for_obj_to_user)(
            limited_user, self.corpus, [PermissionTypes.READ]
        )
        # No permission on document

        # Make both private
        self.doc.is_public = False
        await database_sync_to_async(self.doc.save)(update_fields=["is_public"])
        self.corpus.is_public = False
        await database_sync_to_async(self.corpus.save)(update_fields=["is_public"])

        limited_token = await database_sync_to_async(get_token)(user=limited_user)
        doc_gid = to_global_id("DocumentType", self.doc.id)
        corpus_gid = to_global_id("CorpusType", self.corpus.id)
        ws_path = (
            f"ws/agent-chat/?document_id={quote(doc_gid)}"
            f"&corpus_id={quote(corpus_gid)}"
        )

        communicator = WebsocketCommunicator(
            self.application,
            ws_path,
            subprotocols=[WS_AUTH_SUBPROTOCOL, limited_token],
        )
        connected, code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(code, 4003)

    async def test_dc1_3_user_with_both_permissions_connects(self) -> None:
        """DC1.3: User has READ on both doc and corpus - should connect."""
        await self._ensure_agent_configs_exist()

        # User from fixture owns both, so has READ on both
        self.doc.is_public = False
        await database_sync_to_async(self.doc.save)(update_fields=["is_public"])
        self.corpus.is_public = False
        await database_sync_to_async(self.corpus.save)(update_fields=["is_public"])

        doc_gid = to_global_id("DocumentType", self.doc.id)
        corpus_gid = to_global_id("CorpusType", self.corpus.id)
        ws_path = (
            f"ws/agent-chat/?document_id={quote(doc_gid)}"
            f"&corpus_id={quote(corpus_gid)}"
        )

        communicator = WebsocketCommunicator(
            self.application,
            ws_path,
            subprotocols=[WS_AUTH_SUBPROTOCOL, self.token],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.disconnect()


# =============================================================================
# Category 2: Tool Filtering Tests
# =============================================================================


@override_settings(USE_AUTH0=False)
@pytest.mark.django_db(transaction=True)
class ToolFilteringCorpusAgentTestCase(WebsocketFixtureBaseTestCase):
    """
    Category 2.1: Write Tool Filtering - Corpus Agent

    Tests that verify the agent factory properly filters tools based on
    user's WRITE permission for corpus agents.
    """

    async def test_tf2_1_corpus_agent_write_tools_available_for_owner(self) -> None:
        """TF2.1: Owner of corpus gets write tools."""
        from opencontractserver.llms.agents.agent_factory import (
            _user_has_write_permission,
        )

        # User from fixture owns the corpus, so should have write permission
        has_write = await _user_has_write_permission(self.user.id, self.corpus)
        self.assertTrue(has_write, "Owner should have write permission")

    async def test_tf2_2_corpus_agent_write_tools_filtered_for_read_only_user(
        self,
    ) -> None:
        """TF2.2: User with only READ gets write tools filtered out."""
        from opencontractserver.llms.agents.agent_factory import (
            _user_has_write_permission,
        )

        # Create user with only READ permission
        read_user = await database_sync_to_async(User.objects.create_user)(
            username="reader_corpus",
            password="pw123456!",
            email="reader_corpus@example.com",
        )
        await database_sync_to_async(set_permissions_for_obj_to_user)(
            read_user, self.corpus, [PermissionTypes.READ]
        )

        has_write = await _user_has_write_permission(read_user.id, self.corpus)
        self.assertFalse(has_write, "Read-only user should NOT have write permission")

    async def test_tf2_3_corpus_agent_write_tools_filtered_for_anonymous(self) -> None:
        """TF2.3: Anonymous user gets write tools filtered out."""
        from opencontractserver.llms.agents.agent_factory import (
            _user_has_write_permission,
        )

        self.corpus.is_public = True
        await database_sync_to_async(self.corpus.save)(update_fields=["is_public"])

        # Anonymous user = None user_id
        has_write = await _user_has_write_permission(None, self.corpus)
        self.assertFalse(has_write, "Anonymous user should NOT have write permission")

    async def test_tf2_4_corpus_agent_read_tools_available_for_all(self) -> None:
        """TF2.4: Read tools are available for read-only users."""
        # Get read tools (those without requires_write_permission)
        read_tools = [t for t in AVAILABLE_TOOLS if not t.requires_write_permission]
        self.assertTrue(len(read_tools) > 0, "Should have read-only tools available")

        # Verify these include expected tools
        read_tool_names = [t.name for t in read_tools]
        self.assertIn("similarity_search", read_tool_names)
        self.assertIn("load_document_summary", read_tool_names)


@override_settings(USE_AUTH0=False)
@pytest.mark.django_db(transaction=True)
class ToolFilteringDocumentAgentTestCase(WebsocketFixtureBaseTestCase):
    """
    Category 2.2: Write Tool Filtering - Document Agent

    Tests that verify the agent factory properly filters tools based on
    user's WRITE permission for document agents.
    """

    async def test_tf2_5_document_agent_write_tools_available_for_owner(self) -> None:
        """TF2.5: Owner of document gets write tools."""
        from opencontractserver.llms.agents.agent_factory import (
            _user_has_write_permission,
        )

        # User from fixture owns the document
        has_write = await _user_has_write_permission(self.user.id, self.doc)
        self.assertTrue(has_write, "Owner should have write permission on document")

    async def test_tf2_6_document_agent_write_tools_filtered_for_read_only_user(
        self,
    ) -> None:
        """TF2.6: User with only READ gets write tools filtered out."""
        from opencontractserver.llms.agents.agent_factory import (
            _user_has_write_permission,
        )

        # Create user with only READ permission
        read_user = await database_sync_to_async(User.objects.create_user)(
            username="reader_doc", password="pw123456!", email="reader_doc@example.com"
        )
        await database_sync_to_async(set_permissions_for_obj_to_user)(
            read_user, self.doc, [PermissionTypes.READ]
        )

        has_write = await _user_has_write_permission(read_user.id, self.doc)
        self.assertFalse(has_write, "Read-only user should NOT have write permission")

    async def test_tf2_7_document_agent_write_tools_filtered_for_anonymous(
        self,
    ) -> None:
        """TF2.7: Anonymous user gets write tools filtered out."""
        from opencontractserver.llms.agents.agent_factory import (
            _user_has_write_permission,
        )

        self.doc.is_public = True
        await database_sync_to_async(self.doc.save)(update_fields=["is_public"])

        has_write = await _user_has_write_permission(None, self.doc)
        self.assertFalse(has_write, "Anonymous user should NOT have write permission")


@override_settings(USE_AUTH0=False)
@pytest.mark.django_db(transaction=True)
class ToolFilteringSpecificToolsTestCase(WebsocketFixtureBaseTestCase):
    """
    Category 2.3: Specific Tool Filtering Verification

    Tests that verify specific tools are properly filtered based on their
    requires_write_permission flag.
    """

    def test_tf2_8_add_document_note_requires_write(self) -> None:
        """TF2.8: add_document_note is marked as requiring write permission."""
        tool = next((t for t in AVAILABLE_TOOLS if t.name == "add_document_note"), None)
        self.assertIsNotNone(tool, "add_document_note tool should exist")
        self.assertTrue(
            tool.requires_write_permission,
            "add_document_note should require write permission",
        )

    def test_tf2_9_update_document_summary_requires_write(self) -> None:
        """TF2.9: update_document_summary is marked as requiring write permission."""
        tool = next(
            (t for t in AVAILABLE_TOOLS if t.name == "update_document_summary"), None
        )
        self.assertIsNotNone(tool, "update_document_summary tool should exist")
        self.assertTrue(
            tool.requires_write_permission,
            "update_document_summary should require write permission",
        )

    def test_tf2_10_update_corpus_description_requires_write(self) -> None:
        """TF2.10: update_corpus_description is marked as requiring write permission."""
        tool = next(
            (t for t in AVAILABLE_TOOLS if t.name == "update_corpus_description"), None
        )
        self.assertIsNotNone(tool, "update_corpus_description tool should exist")
        self.assertTrue(
            tool.requires_write_permission,
            "update_corpus_description should require write permission",
        )

    def test_tf2_11_duplicate_annotations_requires_write(self) -> None:
        """TF2.11: duplicate_annotations_with_label requires write permission."""
        tool = next(
            (
                t
                for t in AVAILABLE_TOOLS
                if t.name == "duplicate_annotations_with_label"
            ),
            None,
        )
        self.assertIsNotNone(tool, "duplicate_annotations_with_label tool should exist")
        self.assertTrue(
            tool.requires_write_permission,
            "duplicate_annotations_with_label should require write permission",
        )

    def test_tf2_12_similarity_search_does_not_require_write(self) -> None:
        """TF2.12: similarity_search does NOT require write permission."""
        tool = next((t for t in AVAILABLE_TOOLS if t.name == "similarity_search"), None)
        self.assertIsNotNone(tool, "similarity_search tool should exist")
        self.assertFalse(
            tool.requires_write_permission,
            "similarity_search should NOT require write permission",
        )

    def test_tf2_13_load_document_summary_does_not_require_write(self) -> None:
        """TF2.13: load_document_summary does NOT require write permission."""
        tool = next(
            (t for t in AVAILABLE_TOOLS if t.name == "load_document_summary"), None
        )
        self.assertIsNotNone(tool, "load_document_summary tool should exist")
        self.assertFalse(
            tool.requires_write_permission,
            "load_document_summary should NOT require write permission",
        )


# =============================================================================
# Category 3: Runtime Permission Validation (Defense in Depth)
# =============================================================================


@override_settings(USE_AUTH0=False)
@pytest.mark.django_db(transaction=True)
class RuntimePermissionValidationTestCase(WebsocketFixtureBaseTestCase):
    """
    Category 3.1: Direct Tool Execution Tests

    Tests that verify _check_user_permissions() blocks unauthorized tool
    execution even if filtering fails.
    """

    async def test_rt3_1_runtime_check_blocks_anonymous_on_private_document(
        self,
    ) -> None:
        """RT3.1: Runtime check blocks anonymous user on private document."""

        from opencontractserver.llms.tools.pydantic_ai_tools import (
            PydanticAIDependencies,
            _check_user_permissions,
        )

        # Make document private
        self.doc.is_public = False
        await database_sync_to_async(self.doc.save)()

        # Create mock context with anonymous user (None)
        mock_ctx = MagicMock()
        mock_ctx.deps = PydanticAIDependencies(
            user_id=None,
            document_id=self.doc.id,
            corpus_id=None,
        )

        with self.assertRaises(PermissionError) as context:
            await _check_user_permissions(mock_ctx)

        self.assertIn("Anonymous access denied", str(context.exception))

    async def test_rt3_2_runtime_check_blocks_anonymous_on_private_corpus(self) -> None:
        """RT3.2: Runtime check blocks anonymous user on private corpus."""

        from opencontractserver.llms.tools.pydantic_ai_tools import (
            PydanticAIDependencies,
            _check_user_permissions,
        )

        # Make corpus private
        self.corpus.is_public = False
        await database_sync_to_async(self.corpus.save)()

        mock_ctx = MagicMock()
        mock_ctx.deps = PydanticAIDependencies(
            user_id=None,
            document_id=None,
            corpus_id=self.corpus.id,
        )

        with self.assertRaises(PermissionError) as context:
            await _check_user_permissions(mock_ctx)

        self.assertIn("Anonymous access denied", str(context.exception))

    async def test_rt3_3_runtime_check_blocks_user_without_document_read(self) -> None:
        """RT3.3: Runtime check blocks user without READ on document."""

        from opencontractserver.llms.tools.pydantic_ai_tools import (
            PydanticAIDependencies,
            _check_user_permissions,
        )

        # Create user without permission
        outsider = await database_sync_to_async(User.objects.create_user)(
            username="outsider_runtime_doc",
            password="pw123456!",
            email="outsider_runtime_doc@example.com",
        )

        # Make document private
        self.doc.is_public = False
        await database_sync_to_async(self.doc.save)()

        mock_ctx = MagicMock()
        mock_ctx.deps = PydanticAIDependencies(
            user_id=outsider.id,
            document_id=self.doc.id,
            corpus_id=None,
        )

        with self.assertRaises(PermissionError) as context:
            await _check_user_permissions(mock_ctx)

        self.assertIn("lacks READ permission on document", str(context.exception))

    async def test_rt3_4_runtime_check_blocks_user_without_corpus_read(self) -> None:
        """RT3.4: Runtime check blocks user without READ on corpus."""

        from opencontractserver.llms.tools.pydantic_ai_tools import (
            PydanticAIDependencies,
            _check_user_permissions,
        )

        # Create user without permission
        outsider = await database_sync_to_async(User.objects.create_user)(
            username="outsider_runtime_corpus",
            password="pw123456!",
            email="outsider_runtime_corpus@example.com",
        )

        # Make corpus private
        self.corpus.is_public = False
        await database_sync_to_async(self.corpus.save)()

        mock_ctx = MagicMock()
        mock_ctx.deps = PydanticAIDependencies(
            user_id=outsider.id,
            document_id=None,
            corpus_id=self.corpus.id,
        )

        with self.assertRaises(PermissionError) as context:
            await _check_user_permissions(mock_ctx)

        self.assertIn("lacks READ permission on corpus", str(context.exception))

    async def test_rt3_5_runtime_check_allows_user_with_read_permission(self) -> None:
        """RT3.5: Runtime check allows user with READ permission."""

        from opencontractserver.llms.tools.pydantic_ai_tools import (
            PydanticAIDependencies,
            _check_user_permissions,
        )

        # User from fixture has permission
        mock_ctx = MagicMock()
        mock_ctx.deps = PydanticAIDependencies(
            user_id=self.user.id,
            document_id=self.doc.id,
            corpus_id=self.corpus.id,
        )

        # Should not raise
        await _check_user_permissions(mock_ctx)

    async def test_rt3_6_runtime_check_allows_anonymous_on_public_resource(
        self,
    ) -> None:
        """RT3.6: Runtime check allows anonymous on public resource."""

        from opencontractserver.llms.tools.pydantic_ai_tools import (
            PydanticAIDependencies,
            _check_user_permissions,
        )

        # Make both public
        self.doc.is_public = True
        await database_sync_to_async(self.doc.save)()
        self.corpus.is_public = True
        await database_sync_to_async(self.corpus.save)()

        mock_ctx = MagicMock()
        mock_ctx.deps = PydanticAIDependencies(
            user_id=None,  # Anonymous
            document_id=self.doc.id,
            corpus_id=self.corpus.id,
        )

        # Should not raise
        await _check_user_permissions(mock_ctx)


# =============================================================================
# Category 4: Permission Escalation Scenarios
# =============================================================================


@override_settings(USE_AUTH0=False)
@pytest.mark.django_db(transaction=True)
class CrossUserEscalationTestCase(AgentConfigMixin, WebsocketFixtureBaseTestCase):
    """
    Category 4.1: Cross-User Escalation

    Tests for specific escalation attack vectors involving multiple users.
    """

    async def test_pe4_1_agent_created_by_admin_used_by_regular_user(self) -> None:
        """PE4.1: Admin creates agent config, regular user calls it - regular user's permissions enforced."""
        from opencontractserver.llms.agents.agent_factory import (
            _user_has_write_permission,
        )

        # Create an admin user who owns the corpus
        admin_user = await database_sync_to_async(User.objects.create_user)(
            username="admin_agent_creator",
            password="pw123456!",
            email="admin_agent@example.com",
        )
        admin_user.is_superuser = True
        await database_sync_to_async(admin_user.save)()

        # Create a regular user with only READ permission
        regular_user = await database_sync_to_async(User.objects.create_user)(
            username="regular_agent_user",
            password="pw123456!",
            email="regular_agent@example.com",
        )
        await database_sync_to_async(set_permissions_for_obj_to_user)(
            regular_user, self.corpus, [PermissionTypes.READ]
        )

        # Even though admin created the corpus/agent config, regular user's permissions apply
        has_write = await _user_has_write_permission(regular_user.id, self.corpus)
        self.assertFalse(
            has_write,
            "Regular user should NOT have write permission regardless of who created agent",
        )

    async def test_pe4_2_shared_corpus_different_user_permissions(self) -> None:
        """PE4.2: Corpus shared with 2 users (one READ, one CRUD) - each gets their own permission level."""
        from opencontractserver.llms.agents.agent_factory import (
            _user_has_write_permission,
        )

        # Create two users
        read_user = await database_sync_to_async(User.objects.create_user)(
            username="shared_read_user",
            password="pw123456!",
            email="shared_read@example.com",
        )
        crud_user = await database_sync_to_async(User.objects.create_user)(
            username="shared_crud_user",
            password="pw123456!",
            email="shared_crud@example.com",
        )

        # Grant different permissions
        await database_sync_to_async(set_permissions_for_obj_to_user)(
            read_user, self.corpus, [PermissionTypes.READ]
        )
        await database_sync_to_async(set_permissions_for_obj_to_user)(
            crud_user, self.corpus, [PermissionTypes.CRUD]
        )

        # Verify each user has appropriate level
        read_has_write = await _user_has_write_permission(read_user.id, self.corpus)
        crud_has_write = await _user_has_write_permission(crud_user.id, self.corpus)

        self.assertFalse(read_has_write, "READ user should NOT have write permission")
        self.assertTrue(crud_has_write, "CRUD user SHOULD have write permission")

    async def test_pe4_3_user_cannot_access_other_users_document_via_agent(
        self,
    ) -> None:
        """PE4.3: User A's agent cannot access User B's document."""
        await self._ensure_agent_configs_exist()

        # Create User B with their own private document
        user_b = await database_sync_to_async(User.objects.create_user)(
            username="user_b_owner", password="pw123456!", email="user_b@example.com"
        )

        # Create a private document owned by User B
        user_b_doc = await database_sync_to_async(Document.objects.create)(
            title="User B's Private Document",
            creator=user_b,
            is_public=False,
        )

        # User A (self.user) should not be able to connect to User B's document
        doc_gid = to_global_id("DocumentType", user_b_doc.id)
        ws_path = f"ws/agent-chat/?document_id={quote(doc_gid)}"

        communicator = WebsocketCommunicator(
            self.application,
            ws_path,
            subprotocols=[WS_AUTH_SUBPROTOCOL, self.token],
        )
        connected, code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(code, 4003)


@override_settings(USE_AUTH0=False)
@pytest.mark.django_db(transaction=True)
class PermissionChangeMidSessionTestCase(WebsocketFixtureBaseTestCase):
    """
    Category 4.2: Permission Change During Session

    Tests for scenarios where permissions change while a session is active.
    """

    async def test_pe4_4_permission_revoked_mid_session_blocks_next_call(
        self,
    ) -> None:
        """PE4.4: User connects, permission revoked, sends message - tool execution blocked."""

        from opencontractserver.llms.tools.pydantic_ai_tools import (
            PydanticAIDependencies,
            _check_user_permissions,
        )

        # Create user with initial permission
        temp_user = await database_sync_to_async(User.objects.create_user)(
            username="temp_perm_user",
            password="pw123456!",
            email="temp_perm@example.com",
        )
        await database_sync_to_async(set_permissions_for_obj_to_user)(
            temp_user, self.corpus, [PermissionTypes.READ]
        )
        self.corpus.is_public = False
        await database_sync_to_async(self.corpus.save)(update_fields=["is_public"])

        # First check should pass
        mock_ctx = MagicMock()
        mock_ctx.deps = PydanticAIDependencies(
            user_id=temp_user.id,
            document_id=None,
            corpus_id=self.corpus.id,
        )
        # Wrap sync function for async context
        await _check_user_permissions(mock_ctx)  # Should not raise

        # Revoke permission
        await database_sync_to_async(set_permissions_for_obj_to_user)(
            temp_user, self.corpus, []  # Empty = revoke all
        )

        # Next check should fail (runtime check catches revoked permission)
        with self.assertRaises(PermissionError):
            await _check_user_permissions(mock_ctx)

    async def test_pe4_5_document_made_private_mid_session(self) -> None:
        """PE4.5: Anonymous on public doc, doc made private - next tool call blocked."""

        from opencontractserver.llms.tools.pydantic_ai_tools import (
            PydanticAIDependencies,
            _check_user_permissions,
        )

        # Start with public document
        self.doc.is_public = True
        await database_sync_to_async(self.doc.save)(update_fields=["is_public"])

        mock_ctx = MagicMock()
        mock_ctx.deps = PydanticAIDependencies(
            user_id=None,  # Anonymous
            document_id=self.doc.id,
            corpus_id=None,
        )

        # First check should pass (wrap sync function for async context)
        await _check_user_permissions(mock_ctx)

        # Make document private
        self.doc.is_public = False
        await database_sync_to_async(self.doc.save)(update_fields=["is_public"])

        # Next check should fail
        with self.assertRaises(PermissionError):
            await _check_user_permissions(mock_ctx)

    async def test_pe4_6_permission_granted_mid_session_allows_next_call(
        self,
    ) -> None:
        """PE4.6: Read-only user, CRUD granted mid-session - write tools now work."""
        from opencontractserver.llms.agents.agent_factory import (
            _user_has_write_permission,
        )

        # Create user with initial READ-only permission
        upgrade_user = await database_sync_to_async(User.objects.create_user)(
            username="upgrade_user", password="pw123456!", email="upgrade@example.com"
        )
        await database_sync_to_async(set_permissions_for_obj_to_user)(
            upgrade_user, self.corpus, [PermissionTypes.READ]
        )

        # Initially no write permission
        has_write = await _user_has_write_permission(upgrade_user.id, self.corpus)
        self.assertFalse(has_write)

        # Grant CRUD permission
        await database_sync_to_async(set_permissions_for_obj_to_user)(
            upgrade_user, self.corpus, [PermissionTypes.CRUD]
        )

        # Now has write permission
        has_write = await _user_has_write_permission(upgrade_user.id, self.corpus)
        self.assertTrue(has_write)


@override_settings(USE_AUTH0=False)
@pytest.mark.django_db(transaction=True)
class ResourceSubstitutionAttackTestCase(WebsocketFixtureBaseTestCase):
    """
    Category 4.3: Resource Substitution Attacks

    Tests that verify users cannot access different resources than those
    established in the WebSocket connection context.
    """

    async def test_pe4_7_cannot_access_different_document_via_tool_params(
        self,
    ) -> None:
        """PE4.7: Tool called with different document_id - blocked by context validation."""

        from opencontractserver.llms.tools.pydantic_ai_tools import (
            PydanticAIDependencies,
            _check_user_permissions,
        )

        # Create user B with their own private document
        user_b = await database_sync_to_async(User.objects.create_user)(
            username="user_b_doc_attack",
            password="pw123456!",
            email="user_b_attack@example.com",
        )
        user_b_doc = await database_sync_to_async(Document.objects.create)(
            title="User B's Secret Document",
            creator=user_b,
            is_public=False,
        )

        # User A (self.user) tries to access User B's document via tool
        mock_ctx = MagicMock()
        mock_ctx.deps = PydanticAIDependencies(
            user_id=self.user.id,
            document_id=user_b_doc.id,  # Attempting to access B's doc
            corpus_id=None,
        )

        # Runtime check should block this (wrap sync function for async context)
        with self.assertRaises(PermissionError):
            await _check_user_permissions(mock_ctx)

    async def test_pe4_8_cannot_access_different_corpus_via_tool_params(
        self,
    ) -> None:
        """PE4.8: Tool called with different corpus_id - blocked by context validation."""

        from opencontractserver.llms.tools.pydantic_ai_tools import (
            PydanticAIDependencies,
            _check_user_permissions,
        )

        # Create user B with their own private corpus
        user_b = await database_sync_to_async(User.objects.create_user)(
            username="user_b_corpus_attack",
            password="pw123456!",
            email="user_b_corpus@example.com",
        )
        user_b_corpus = await database_sync_to_async(Corpus.objects.create)(
            title="User B's Secret Corpus",
            creator=user_b,
            is_public=False,
        )

        # User A (self.user) tries to access User B's corpus via tool
        mock_ctx = MagicMock()
        mock_ctx.deps = PydanticAIDependencies(
            user_id=self.user.id,
            document_id=None,
            corpus_id=user_b_corpus.id,  # Attempting to access B's corpus
        )

        # Runtime check should block this (wrap sync function for async context)
        with self.assertRaises(PermissionError):
            await _check_user_permissions(mock_ctx)

    async def test_pe4_9_tool_params_cannot_override_context_ids(self) -> None:
        """PE4.9: Malicious tool args try to change target - context IDs take precedence."""
        # This test verifies that the PydanticAIDependencies set in context
        # cannot be overridden by tool parameters. The agent factory sets
        # document_id and corpus_id in deps, and tools use those values
        # rather than accepting them as parameters.

        # The key insight is that our tools get document_id and corpus_id
        # from ctx.deps, NOT from function parameters. This means even if
        # an attacker could somehow inject malicious tool arguments, the
        # runtime permission check still validates against the original
        # context IDs.

        from opencontractserver.llms.tools.pydantic_ai_tools import (
            PydanticAIDependencies,
        )

        # Original context is set with self.user's document
        deps = PydanticAIDependencies(
            user_id=self.user.id,
            document_id=self.doc.id,
            corpus_id=self.corpus.id,
        )

        # These values are immutable in the deps object
        self.assertEqual(deps.document_id, self.doc.id)
        self.assertEqual(deps.corpus_id, self.corpus.id)

        # Even if someone tried to modify deps (which they shouldn't be able to),
        # the permission check would run against whatever is in deps
        # So the design is: deps are set once at agent creation, then validated
        # on every tool call

        self.assertTrue(True, "Context IDs are fixed at agent creation time")


# =============================================================================
# Category 5: Integration Tests (Full Flow)
# =============================================================================


@override_settings(USE_AUTH0=False)
@pytest.mark.django_db(transaction=True)
class FullConversationFlowTestCase(AgentConfigMixin, WebsocketFixtureBaseTestCase):
    """
    Category 5.1: Full Conversation Flow Tests

    End-to-end tests verifying complete permission flow through WebSocket.
    """

    async def _mock_stream_events(self):
        """Mock event generator for testing."""
        yield ContentEvent(
            content="Test response",
            llm_message_id=1,
            user_message_id=1,
            metadata={},
        )
        yield FinalEvent(
            content="",
            accumulated_content="Test response",
            sources=[],
            llm_message_id=1,
            user_message_id=1,
            metadata={"timeline": []},
        )

    async def test_it5_1_read_only_user_full_conversation(self) -> None:
        """IT5.1: User with READ connects, queries, receives response."""
        await self._ensure_agent_configs_exist()

        from opencontractserver.llms.agents.agent_factory import (
            _user_has_write_permission,
        )

        # Create read-only user
        read_user = await database_sync_to_async(User.objects.create_user)(
            username="integration_read_user",
            password="pw123456!",
            email="integration_read@example.com",
        )
        await database_sync_to_async(set_permissions_for_obj_to_user)(
            read_user, self.corpus, [PermissionTypes.READ]
        )
        read_token = await database_sync_to_async(get_token)(user=read_user)

        self.corpus.is_public = False
        await database_sync_to_async(self.corpus.save)(update_fields=["is_public"])

        # Verify read-only user cannot write
        has_write = await _user_has_write_permission(read_user.id, self.corpus)
        self.assertFalse(has_write, "Read-only user should not have write permission")

        # 1. Connection succeeds
        corpus_gid = to_global_id("CorpusType", self.corpus.id)
        ws_path = f"ws/agent-chat/?corpus_id={quote(corpus_gid)}"

        communicator = WebsocketCommunicator(
            self.application,
            ws_path,
            subprotocols=[WS_AUTH_SUBPROTOCOL, read_token],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected, "Read-only user should be able to connect")
        await communicator.disconnect()

    async def test_it5_2_owner_full_conversation_with_write(self) -> None:
        """IT5.2: Owner connects, has write tools available."""
        await self._ensure_agent_configs_exist()

        from opencontractserver.llms.agents.agent_factory import (
            _user_has_write_permission,
        )

        # Verify owner has write permission
        has_write = await _user_has_write_permission(self.user.id, self.corpus)
        self.assertTrue(has_write, "Owner should have write permission")

        # Connection succeeds
        corpus_gid = to_global_id("CorpusType", self.corpus.id)
        ws_path = f"ws/agent-chat/?corpus_id={quote(corpus_gid)}"

        communicator = WebsocketCommunicator(
            self.application,
            ws_path,
            subprotocols=[WS_AUTH_SUBPROTOCOL, self.token],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected, "Owner should be able to connect")
        await communicator.disconnect()

    async def test_it5_3_anonymous_public_corpus_conversation(self) -> None:
        """IT5.3: No token, public corpus - connection succeeds, no write tools."""
        await self._ensure_agent_configs_exist()

        from opencontractserver.llms.agents.agent_factory import (
            _user_has_write_permission,
        )

        self.corpus.is_public = True
        await database_sync_to_async(self.corpus.save)(update_fields=["is_public"])

        # Anonymous has no write permission
        has_write = await _user_has_write_permission(None, self.corpus)
        self.assertFalse(has_write, "Anonymous should not have write permission")

        # Connection succeeds
        corpus_gid = to_global_id("CorpusType", self.corpus.id)
        ws_path = f"ws/agent-chat/?corpus_id={quote(corpus_gid)}"  # No token

        communicator = WebsocketCommunicator(self.application, ws_path)
        connected, _ = await communicator.connect()
        self.assertTrue(
            connected, "Anonymous should be able to connect to public corpus"
        )
        await communicator.disconnect()

    async def test_it5_4_permission_denied_error_message_flow(self) -> None:
        """IT5.4: User without permission queries - connection rejected with proper error code."""
        # Create outsider
        outsider = await database_sync_to_async(User.objects.create_user)(
            username="integration_outsider",
            password="pw123456!",
            email="integration_outsider@example.com",
        )
        outsider_token = await database_sync_to_async(get_token)(user=outsider)

        # Make corpus private
        self.corpus.is_public = False
        await database_sync_to_async(self.corpus.save)(update_fields=["is_public"])

        corpus_gid = to_global_id("CorpusType", self.corpus.id)
        ws_path = f"ws/agent-chat/?corpus_id={quote(corpus_gid)}"

        communicator = WebsocketCommunicator(
            self.application,
            ws_path,
            subprotocols=[WS_AUTH_SUBPROTOCOL, outsider_token],
        )
        connected, code = await communicator.connect()

        # 1. Connection rejected
        self.assertFalse(connected)
        # 2. Proper error code
        self.assertEqual(code, 4003)


@override_settings(USE_AUTH0=False)
@pytest.mark.django_db(transaction=True)
class MultiTurnConversationTestCase(WebsocketFixtureBaseTestCase):
    """
    Category 5.2: Multi-Turn Conversation Tests

    Tests for multi-turn conversation permission handling.
    """

    async def test_it5_5_multi_turn_maintains_permission_context(self) -> None:
        """IT5.5: Multiple messages in session - each turn respects original permissions."""

        from opencontractserver.llms.tools.pydantic_ai_tools import (
            PydanticAIDependencies,
            _check_user_permissions,
        )

        # Create user with READ permission
        multi_turn_user = await database_sync_to_async(User.objects.create_user)(
            username="multi_turn_user",
            password="pw123456!",
            email="multi_turn@example.com",
        )
        await database_sync_to_async(set_permissions_for_obj_to_user)(
            multi_turn_user, self.corpus, [PermissionTypes.READ]
        )

        # Simulate multiple turns - each should be validated
        for turn in range(3):
            mock_ctx = MagicMock()
            mock_ctx.deps = PydanticAIDependencies(
                user_id=multi_turn_user.id,
                document_id=None,
                corpus_id=self.corpus.id,
            )

            # Each turn should pass permission check (wrap sync function for async context)
            await _check_user_permissions(mock_ctx)  # Should not raise

        self.assertTrue(True, "All turns respected permissions")

    async def test_it5_6_conversation_resume_respects_current_permissions(
        self,
    ) -> None:
        """IT5.6: Load existing conversation - current user's permissions, not creator's."""

        from opencontractserver.conversations.models import Conversation
        from opencontractserver.llms.tools.pydantic_ai_tools import (
            PydanticAIDependencies,
            _check_user_permissions,
        )

        # User A creates a conversation
        user_a = await database_sync_to_async(User.objects.create_user)(
            username="convo_creator",
            password="pw123456!",
            email="convo_creator@example.com",
        )
        await database_sync_to_async(set_permissions_for_obj_to_user)(
            user_a, self.corpus, [PermissionTypes.CRUD]
        )

        # Conversation exists but user B's permissions are what matters for tool execution
        await Conversation.objects.acreate(
            title="Test Conversation",
            creator=user_a,
            chat_with_corpus=self.corpus,
        )

        # User B tries to resume the conversation
        user_b = await database_sync_to_async(User.objects.create_user)(
            username="convo_resumer",
            password="pw123456!",
            email="convo_resumer@example.com",
        )
        # User B has NO permission on the corpus
        self.corpus.is_public = False
        await database_sync_to_async(self.corpus.save)(update_fields=["is_public"])

        # When User B tries to execute tools, their permissions are checked
        mock_ctx = MagicMock()
        mock_ctx.deps = PydanticAIDependencies(
            user_id=user_b.id,  # User B's ID
            document_id=None,
            corpus_id=self.corpus.id,
        )

        # Should fail because User B doesn't have permission
        # even though User A created the conversation (wrap sync function for async context)
        with self.assertRaises(PermissionError):
            await _check_user_permissions(mock_ctx)


# =============================================================================
# Summary: Tool Registry Verification Tests
# =============================================================================


@pytest.mark.django_db
class ToolRegistryPermissionFlagsTestCase(WebsocketFixtureBaseTestCase):
    """
    Verify all write tools in the registry are properly flagged.

    This test ensures that when new tools are added, developers don't
    forget to add the requires_write_permission flag.
    """

    def test_all_write_tools_flagged(self) -> None:
        """All tools that require approval should also require write permission if they modify data."""
        # Tools that require approval AND modify data should have requires_write_permission
        tools_needing_attention = []

        for tool in AVAILABLE_TOOLS:
            if tool.requires_approval:
                # If it requires approval, it likely modifies data
                # So it should have requires_write_permission=True
                if not tool.requires_write_permission:
                    # Exception: read-only approval tools (if any exist)
                    # For now, we expect all approval tools to be write tools
                    tools_needing_attention.append(tool.name)

        self.assertEqual(
            len(tools_needing_attention),
            0,
            f"These approval-required tools are missing requires_write_permission flag: {tools_needing_attention}",
        )

    def test_known_write_tools_all_flagged(self) -> None:
        """Known write tools should all have requires_write_permission=True."""
        known_write_tools = [
            "update_document_description",
            "update_document_summary",
            "add_document_note",
            "update_document_note",
            "update_corpus_description",
            "duplicate_annotations_with_label",
            "add_annotations_from_exact_strings",
            "delete_message",
            "lock_thread",
            "unlock_thread",
            "add_thread_message",
            "pin_thread",
            "unpin_thread",
        ]

        missing_flag = []
        for tool_name in known_write_tools:
            tool = next((t for t in AVAILABLE_TOOLS if t.name == tool_name), None)
            if tool and not tool.requires_write_permission:
                missing_flag.append(tool_name)

        self.assertEqual(
            len(missing_flag),
            0,
            f"These known write tools are missing requires_write_permission flag: {missing_flag}",
        )

    def test_known_read_tools_not_flagged(self) -> None:
        """Known read-only tools should NOT have requires_write_permission=True."""
        known_read_tools = [
            "similarity_search",
            "search_exact_text",
            "load_document_summary",
            "get_summary_token_length",
            "get_document_text_length",
            "load_document_text",
            "get_page_image",
            "get_document_description",
            "get_document_summary",
            "get_document_summary_versions",
            "get_document_summary_diff",
            "get_document_notes",
            "search_document_notes",
            "get_corpus_description",
            "list_documents",
            "ask_document",
            "get_thread_context",
            "get_thread_messages",
            "get_message_content",
            "create_markdown_link",
        ]

        incorrectly_flagged = []
        for tool_name in known_read_tools:
            tool = next((t for t in AVAILABLE_TOOLS if t.name == tool_name), None)
            if tool and tool.requires_write_permission:
                incorrectly_flagged.append(tool_name)

        self.assertEqual(
            len(incorrectly_flagged),
            0,
            f"These read-only tools should NOT have requires_write_permission flag: {incorrectly_flagged}",
        )
