"""
Tests for UnifiedAgentConsumer per-turn delegation tool injection (Task 7).

These tests verify the consumer's pre-dispatch augmentation:
- mention extraction → visibility/scope filter → delegation tool list
- per-turn conductor rebuild with ``extra_tools``
- relay-driven sub-agent frame attribution (agent_id, parent_message_id,
  requesting_agent)
- pinned sub-agent ChatMessage persistence
- sub-agent approval bubbling via tuple-keyed pending_approvals
"""

from __future__ import annotations

import asyncio
import json
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.parse import quote

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.test.utils import override_settings
from graphql_relay import to_global_id

from config.websocket.middleware import WS_AUTH_SUBPROTOCOL
from opencontractserver.agents.models import AgentConfiguration
from opencontractserver.conversations.models import (
    ChatMessage,
    Conversation,
    MessageStateChoices,
    MessageTypeChoices,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.llms.agents.core_agents import (
    ContentEvent,
    FinalEvent,
)
from opencontractserver.tests.base import WebsocketFixtureBaseTestCase

logger = logging.getLogger(__name__)


class _StubAgent:
    """Stub agent with deterministic stream events and a recorded conversation id."""

    def __init__(self, gen_factory, conversation_id=None):
        self._gen_factory = gen_factory
        self._conversation_id = conversation_id
        self.conversation_manager = SimpleNamespace(context_exhausted=False)

    def stream(self, user_query: str):
        return self._gen_factory()

    def resume_with_approval(self, llm_msg_id, approved, stream=True):
        async def _empty():
            if False:  # pragma: no cover
                yield None

        return _empty()

    def get_conversation_id(self):
        return self._conversation_id


async def _consume_until_finish(communicator, timeout: float = 10) -> list[dict]:
    """Drain frames from a communicator up to (and including) ASYNC_FINISH."""
    msgs: list[dict] = []
    while True:
        payload = json.loads(await communicator.receive_from(timeout=timeout))
        msgs.append(payload)
        if payload.get("type") == "ASYNC_FINISH":
            break
    return msgs


async def _drain_auth_ok(communicator) -> None:
    raw = await communicator.receive_from(timeout=5)
    # AUTH_OK is the initial handshake frame from AuthHandshakeMixin.
    json.loads(raw)


@override_settings(USE_AUTH0=False)
@pytest.mark.django_db(transaction=True)
class UnifiedAgentConsumerDelegationTestCase(WebsocketFixtureBaseTestCase):
    """Integration tests for the consumer's per-turn delegation tool injection."""

    def _build_simple_stream_factory(self, message_id: int = 7):
        """Build a stream-event generator factory yielding Content + Final."""

        async def _gen():
            yield ContentEvent(
                content="ok",
                llm_message_id=message_id,
                user_message_id=message_id,
                metadata={},
            )
            yield FinalEvent(
                content="",
                accumulated_content="ok",
                sources=[],
                llm_message_id=message_id,
                user_message_id=message_id,
                metadata={"timeline": []},
            )

        return _gen

    async def _connect(self) -> WebsocketCommunicator:
        """Open a corpus-bound chat as the authenticated user."""
        corpus_gid = to_global_id("CorpusType", self.corpus.id)
        ws_path = f"ws/agent-chat/?corpus_id={quote(corpus_gid)}"
        communicator = WebsocketCommunicator(
            self.application,
            ws_path,
            subprotocols=[WS_AUTH_SUBPROTOCOL, self.token],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await _drain_auth_ok(communicator)
        return communicator

    # ---- A. silent fallback: target invisible ----
    async def test_silent_fallback_when_target_invisible_to_user(self) -> None:
        """A corpus-scoped agent bound to an invisible corpus is silently dropped.

        Per AgentConfigurationQuerySet.visible_to_user, all active GLOBAL
        agents are visible to all authenticated users (they're public by
        definition).  Invisibility is therefore tested via the CORPUS-scoped
        branch: an agent bound to a private corpus the current user cannot
        access is silently dropped.
        """
        from django.contrib.auth import get_user_model

        OtherUser = get_user_model()
        other = await database_sync_to_async(OtherUser.objects.create_user)(
            username="agent_owner_invisible",
            password="pw123456!",
            email="ainvisible@example.com",
        )
        # Private corpus owned by `other`, which `self.user` cannot see.
        private_corpus = await database_sync_to_async(Corpus.objects.create)(
            title="Other private",
            creator=other,
            is_public=False,
        )
        await database_sync_to_async(AgentConfiguration.objects.create)(
            name="Hidden",
            slug="hidden-bot",
            description="Bound to inaccessible corpus",
            scope="CORPUS",
            corpus=private_corpus,
            is_active=True,
            is_public=False,
            creator=other,
            system_instructions="hidden",
        )

        communicator = await self._connect()

        captured_kwargs: dict = {}

        async def _fake_factory(*args, **kwargs):
            captured_kwargs.update(kwargs)
            return _StubAgent(self._build_simple_stream_factory())

        with patch(
            "config.websocket.consumers.unified_agent_conversation.agents.for_corpus",
            side_effect=_fake_factory,
        ):
            await communicator.send_to(
                json.dumps({"query": "Hello [Hidden](/agents/hidden-bot) please"})
            )
            await _consume_until_finish(communicator)

        await communicator.disconnect()

        # No delegation tools should have been threaded in.
        tools = captured_kwargs.get("tools")
        if tools is not None:
            tool_names = [
                getattr(t, "name", None)
                or getattr(t, "__name__", None)
                or getattr(getattr(t, "metadata", None), "name", None)
                for t in tools
            ]
            self.assertFalse(
                any(name and "delegate_to_" in str(name) for name in tool_names),
                f"Expected no delegate_to_* tools but found: {tool_names}",
            )

    # ---- B. silent fallback: scope mismatch ----
    async def test_silent_fallback_when_scope_mismatched(self) -> None:
        """Corpus-scoped agent owned by another corpus is dropped silently."""
        from opencontractserver.types.enums import PermissionTypes
        from opencontractserver.utils.permissioning import (
            set_permissions_for_obj_to_user,
        )

        other_corpus = await database_sync_to_async(Corpus.objects.create)(
            title="Other",
            creator=self.user,
        )
        # Grant the user permissions on the other corpus too so visibility
        # passes; we want to test SCOPE filtering, not permission.
        await database_sync_to_async(set_permissions_for_obj_to_user)(
            self.user, other_corpus, [PermissionTypes.ALL]
        )
        await database_sync_to_async(AgentConfiguration.objects.create)(
            name="Other Corp Bot",
            slug="other-corp-bot",
            description="bound to other corpus",
            scope="CORPUS",
            corpus=other_corpus,
            is_active=True,
            is_public=False,
            creator=self.user,
            system_instructions="other",
        )

        communicator = await self._connect()

        captured_kwargs: dict = {}

        async def _fake_factory(*args, **kwargs):
            captured_kwargs.update(kwargs)
            return _StubAgent(self._build_simple_stream_factory())

        with patch(
            "config.websocket.consumers.unified_agent_conversation.agents.for_corpus",
            side_effect=_fake_factory,
        ):
            await communicator.send_to(
                json.dumps({"query": "Hi [OCB](/agents/other-corp-bot) thanks"})
            )
            await _consume_until_finish(communicator)

        await communicator.disconnect()

        tools = captured_kwargs.get("tools")
        if tools is not None:
            tool_names = [
                getattr(getattr(t, "metadata", None), "name", None) for t in tools
            ]
            self.assertNotIn("delegate_to_other_corp_bot", tool_names)

    # ---- C. anonymous user can mention public global ----
    async def test_anonymous_can_mention_public_global_agent(self) -> None:
        """Anonymous user mentioning a public GLOBAL agent gets the tool wired in."""
        await database_sync_to_async(AgentConfiguration.objects.create)(
            name="Public Bot",
            slug="public-bot",
            description="Public",
            scope="GLOBAL",
            is_active=True,
            is_public=True,
            creator=self.user,
            system_instructions="public",
        )

        # Make corpus public so anonymous can connect.
        self.corpus.is_public = True
        await database_sync_to_async(self.corpus.save)(update_fields=["is_public"])

        corpus_gid = to_global_id("CorpusType", self.corpus.id)
        ws_path = f"ws/agent-chat/?corpus_id={quote(corpus_gid)}"
        communicator = WebsocketCommunicator(self.application, ws_path)
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        # Anonymous path has no AUTH_OK frame (or it does; we drain either way).
        # Only suppress the timeout from a missing frame; bubble up anything else
        # so accidental regressions in the handshake flow don't get masked.
        try:
            await _drain_auth_ok(communicator)
        except asyncio.TimeoutError:
            pass

        captured_kwargs: dict = {}

        async def _fake_factory(*args, **kwargs):
            captured_kwargs.update(kwargs)
            return _StubAgent(self._build_simple_stream_factory())

        with patch(
            "config.websocket.consumers.unified_agent_conversation.agents.for_corpus",
            side_effect=_fake_factory,
        ):
            await communicator.send_to(
                json.dumps({"query": "Try [P](/agents/public-bot) please"})
            )
            await _consume_until_finish(communicator)

        await communicator.disconnect()

        tools = captured_kwargs.get("tools") or []
        tool_names = [
            getattr(getattr(t, "metadata", None), "name", None) for t in tools
        ]
        self.assertIn("delegate_to_public_bot", tool_names)

    # ---- D. single unpinned delegation: tools wired, no extra ASYNC_START ----
    async def test_unpinned_delegation_wires_tool_only(self) -> None:
        """A mention without pinning attaches the delegation tool to the conductor.

        We assert the tool list contains exactly one delegate_to_* entry for
        the mentioned agent.  Sub-agent behavior is verified in body tests
        (test_delegation_tools.py); here we only assert the consumer's
        plumbing.
        """
        await database_sync_to_async(AgentConfiguration.objects.create)(
            name="Helper",
            slug="helper",
            description="Helper agent",
            scope="GLOBAL",
            is_active=True,
            is_public=True,
            creator=self.user,
            system_instructions="help",
        )

        communicator = await self._connect()

        captured_kwargs: dict = {}

        async def _fake_factory(*args, **kwargs):
            captured_kwargs.update(kwargs)
            return _StubAgent(self._build_simple_stream_factory())

        with patch(
            "config.websocket.consumers.unified_agent_conversation.agents.for_corpus",
            side_effect=_fake_factory,
        ):
            await communicator.send_to(
                json.dumps({"query": "Use [H](/agents/helper) please"})
            )
            await _consume_until_finish(communicator)

        await communicator.disconnect()

        tools = captured_kwargs.get("tools") or []
        tool_names = [
            getattr(getattr(t, "metadata", None), "name", None) for t in tools
        ]
        delegation_tool_names = [n for n in tool_names if n and "delegate_to_" in n]
        self.assertEqual(delegation_tool_names, ["delegate_to_helper"])

    # ---- E. pinned sub-agent → ChatMessage created + ASYNC_FINISH frame ----
    async def test_pinned_delegation_persists_chat_message(self) -> None:
        """The relay's on_finish creates an LLM ChatMessage row tagged with the sub-agent.

        We test the consumer's relay closure directly (it has no LLM
        dependency) by instantiating the consumer, stubbing its
        ``_send_safe``, and driving the relay's ``on_finish`` for ``pin=True``.
        """
        from config.websocket.consumers.unified_agent_conversation import (
            UnifiedAgentConsumer,
        )

        agent = await database_sync_to_async(AgentConfiguration.objects.create)(
            name="Pinnable",
            slug="pinnable",
            description="Pinnable agent",
            scope="GLOBAL",
            is_active=True,
            is_public=True,
            creator=self.user,
            system_instructions="pin me",
        )

        conversation = await database_sync_to_async(Conversation.objects.create)(
            title="t",
            creator=self.user,
            chat_with_corpus=self.corpus,
        )
        # Create a real parent ChatMessage so the FK constraint on
        # parent_message_id (NOT NULL when set) is satisfied.
        parent_msg = await database_sync_to_async(ChatMessage.objects.create)(
            conversation=conversation,
            msg_type=MessageTypeChoices.LLM,
            content="conductor turn",
            creator=self.user,
            state=MessageStateChoices.COMPLETED,
        )

        consumer = UnifiedAgentConsumer()
        consumer.session_id = "t"
        consumer._is_connected = True
        consumer.conversation_id = conversation.id
        consumer.user_id = self.user.id
        consumer.corpus = self.corpus
        consumer.document = None
        consumer.scope = {"user": self.user}

        sent: list[dict] = []

        async def fake_send_safe(msg_type, content="", data=None):
            sent.append({"msg_type": msg_type, "content": content, "data": data or {}})
            return True

        consumer._send_safe = fake_send_safe  # type: ignore[method-assign]

        box: dict = {"value": parent_msg.id}
        relay = consumer._build_stream_relay_factory(parent_message_id_box=box)(
            agent, True
        )

        # Exercise a representative pinned-bubble lifecycle:
        await relay.on_token("Sub-agent says hi")
        pinned_id = await relay.on_finish("Sub-agent says hi")

        self.assertIsNotNone(pinned_id)
        persisted = await ChatMessage.objects.aget(id=pinned_id)
        self.assertEqual(persisted.msg_type, MessageTypeChoices.LLM)
        self.assertEqual(persisted.agent_configuration_id, agent.id)
        self.assertEqual(persisted.parent_message_id, parent_msg.id)
        self.assertEqual(persisted.content, "Sub-agent says hi")
        self.assertEqual(persisted.state, MessageStateChoices.COMPLETED)
        data = persisted.data or {}
        self.assertTrue(data.get("pinned"))
        self.assertEqual(data.get("delegated_from"), parent_msg.id)
        self.assertEqual(data.get("agent_slug"), "pinnable")

        # The ASYNC_CONTENT for the token must carry agent_id/parent_message_id.
        token_frames = [s for s in sent if s["msg_type"] == "ASYNC_CONTENT"]
        self.assertEqual(len(token_frames), 1)
        self.assertEqual(token_frames[0]["data"]["agent_id"], agent.id)
        self.assertEqual(token_frames[0]["data"]["parent_message_id"], parent_msg.id)

        # The ASYNC_FINISH must reference the persisted pinned message id.
        finish_frames = [s for s in sent if s["msg_type"] == "ASYNC_FINISH"]
        self.assertEqual(len(finish_frames), 1)
        self.assertEqual(finish_frames[0]["data"]["pinned_message_id"], pinned_id)
        self.assertEqual(finish_frames[0]["data"]["agent_id"], agent.id)
        self.assertEqual(finish_frames[0]["data"]["parent_message_id"], parent_msg.id)

    # ---- F. multiple mentions → multiple delegation tools ----
    async def test_multiple_mentions_attach_multiple_tools(self) -> None:
        """Two agents mentioned → conductor gets two delegate_to_* tools."""
        await database_sync_to_async(AgentConfiguration.objects.create)(
            name="A1",
            slug="a-one",
            description="agent one",
            scope="GLOBAL",
            is_active=True,
            is_public=True,
            creator=self.user,
            system_instructions="a1",
        )
        await database_sync_to_async(AgentConfiguration.objects.create)(
            name="A2",
            slug="a-two",
            description="agent two",
            scope="GLOBAL",
            is_active=True,
            is_public=True,
            creator=self.user,
            system_instructions="a2",
        )

        communicator = await self._connect()

        captured_kwargs: dict = {}

        async def _fake_factory(*args, **kwargs):
            captured_kwargs.update(kwargs)
            return _StubAgent(self._build_simple_stream_factory())

        with patch(
            "config.websocket.consumers.unified_agent_conversation.agents.for_corpus",
            side_effect=_fake_factory,
        ):
            await communicator.send_to(
                json.dumps(
                    {
                        "query": (
                            "Ping [a1](/agents/a-one) and [a2](/agents/a-two) " "please"
                        )
                    }
                )
            )
            await _consume_until_finish(communicator)

        await communicator.disconnect()

        tools = captured_kwargs.get("tools") or []
        tool_names = [
            getattr(getattr(t, "metadata", None), "name", None) for t in tools
        ]
        delegate_names = sorted(n for n in tool_names if n and "delegate_to_" in n)
        self.assertEqual(delegate_names, ["delegate_to_a_one", "delegate_to_a_two"])

    # ---- F.1 dedup: collision in delegate_to_<snake_slug> tool names ----
    async def test_snake_case_slug_collision_dedupes_to_single_tool(self) -> None:
        """Two agents whose slugs differ only in `-` vs `_` collide after
        snake-case normalization (``a-one`` / ``a_one`` → ``delegate_to_a_one``).

        ``AgentConfiguration.save()`` normalizes to `-`, so the normal write
        path cannot produce this collision — but admin / fixture / management
        commands that bypass ``save()`` (e.g. ``QuerySet.update(slug=...)``)
        can land a literal `_` slug. The consumer must dedup defensively so
        the conductor never receives two ``CoreTool`` instances with the same
        name (pydantic-ai's tool registry would silently shadow one).
        """
        a1 = await database_sync_to_async(AgentConfiguration.objects.create)(
            name="A One",
            slug="a-one",
            description="dash slug",
            scope="GLOBAL",
            is_active=True,
            is_public=True,
            creator=self.user,
            system_instructions="a1",
        )
        a2 = await database_sync_to_async(AgentConfiguration.objects.create)(
            name="A Underscore",
            # Distinct slug at creation time so unique=True passes; the
            # ``filter(...).update(slug=...)`` below bypasses ``save()`` to
            # land the literal underscore slug we actually need for the test.
            slug="a-two",
            description="underscore slug",
            scope="GLOBAL",
            is_active=True,
            is_public=True,
            creator=self.user,
            system_instructions="a2",
        )
        await database_sync_to_async(
            AgentConfiguration.objects.filter(pk=a2.pk).update
        )(slug="a_one")
        # Sanity: both rows are present, both visible, but they snake-case
        # to the same tool name.
        self.assertNotEqual(a1.slug, "a_one")
        self.assertEqual(
            await database_sync_to_async(
                AgentConfiguration.objects.filter(slug="a_one").count
            )(),
            1,
        )

        communicator = await self._connect()

        captured_kwargs: dict = {}

        async def _fake_factory(*args, **kwargs):
            captured_kwargs.update(kwargs)
            return _StubAgent(self._build_simple_stream_factory())

        with patch(
            "config.websocket.consumers.unified_agent_conversation.agents.for_corpus",
            side_effect=_fake_factory,
        ):
            await communicator.send_to(
                json.dumps(
                    {
                        "query": (
                            "Ping [a1](/agents/a-one) and [a2](/agents/a_one) please"
                        )
                    }
                )
            )
            await _consume_until_finish(communicator)

        await communicator.disconnect()

        tools = captured_kwargs.get("tools") or []
        delegate_names = [
            getattr(getattr(t, "metadata", None), "name", None) or ""
            for t in tools
            if "delegate_to_"
            in (getattr(getattr(t, "metadata", None), "name", None) or "")
        ]
        # Exactly one ``delegate_to_a_one`` survives — the duplicate must
        # have been dropped (with a warning) rather than silently shadowing.
        self.assertEqual(delegate_names, ["delegate_to_a_one"])

    # ---- G. sub-agent approval bubbles requesting_agent through ASYNC_APPROVAL_NEEDED ----
    async def test_sub_agent_approval_bubbles_with_requesting_agent(self) -> None:
        """Sub-agent's ApprovalNeededEvent flows through relay.on_approval.

        The relay must:
          - register a future keyed by (parent_message_id, agent.id)
          - emit ASYNC_APPROVAL_NEEDED with data.requesting_agent
          - resolve the future when _handle_approval_decision routes the user reply
        """
        # We test the consumer's relay + approval-future contract directly
        # (without going through a real WebSocket roundtrip, which would
        # require driving a real conductor + sub-agent stream).  This is the
        # tightest integration test for the new approval-future-key shape.
        from config.websocket.consumers.unified_agent_conversation import (
            UnifiedAgentConsumer,
        )

        agent = await database_sync_to_async(AgentConfiguration.objects.create)(
            name="Approver",
            slug="approver",
            description="needs approvals",
            scope="GLOBAL",
            is_active=True,
            is_public=True,
            creator=self.user,
            system_instructions="approve",
        )

        consumer = UnifiedAgentConsumer()
        consumer.session_id = "t"
        consumer._is_connected = True
        consumer.conversation_id = None
        consumer.user_id = None
        consumer.corpus = None
        consumer.document = None
        # scope.user is read in some paths; stub it.
        consumer.scope = {"user": self.user}

        sent: list[dict] = []

        async def fake_send_safe(msg_type, content="", data=None):
            sent.append({"msg_type": msg_type, "content": content, "data": data or {}})
            return True

        consumer._send_safe = fake_send_safe  # type: ignore[method-assign]

        # Build the relay factory and instantiate a relay for the agent (pin=False).
        box: dict = {"value": 1234}
        relay_factory = consumer._build_stream_relay_factory(
            parent_message_id_box=box,
        )
        relay = relay_factory(agent, False)

        # Drive on_approval and feed the decision via _handle_approval_decision.
        approval_payload = {
            "name": "needs_approval",
            "arguments": {"x": 1},
        }

        async def _resolve_via_consumer():
            # Wait for the relay to register the future, then send the user reply.
            for _ in range(50):
                if (1234, agent.id) in consumer._pending_approvals:
                    break
                await asyncio.sleep(0.01)
            else:
                raise RuntimeError("relay never registered the approval future")
            await consumer._handle_approval_decision(
                {"approval_decision": True, "llm_message_id": 1234}
            )

        # Run the approval await + the consumer's decision dispatch concurrently.
        decision, _ = await asyncio.gather(
            relay.on_approval(approval_payload),
            _resolve_via_consumer(),
        )

        self.assertEqual(decision.get("approved"), True)
        self.assertEqual(decision.get("llm_message_id"), 1234)

        # ASYNC_APPROVAL_NEEDED must have carried the requesting_agent chip.
        needed = [s for s in sent if s["msg_type"] == "ASYNC_APPROVAL_NEEDED"]
        self.assertEqual(len(needed), 1)
        chip = needed[0]["data"].get("requesting_agent")
        self.assertIsNotNone(chip)
        # Internal pk is intentionally not in the wire chip; consumers
        # attribute by slug.
        self.assertNotIn("id", chip)
        self.assertEqual(chip["slug"], "approver")
        self.assertEqual(chip["name"], "Approver")
        self.assertEqual(needed[0]["data"]["message_id"], 1234)

        # ASYNC_APPROVAL_RESULT must have been emitted with the result and
        # the same requesting_agent_id.
        result_frames = [s for s in sent if s["msg_type"] == "ASYNC_APPROVAL_RESULT"]
        self.assertEqual(len(result_frames), 1)
        self.assertEqual(result_frames[0]["data"]["decision"], "approved")
        self.assertEqual(result_frames[0]["data"]["requesting_agent_id"], agent.id)

    # ---- approval-future key tuple back-compat: conductor path uses (id, None) ----
    async def test_conductor_approval_routes_to_agent_when_no_subagent_future(
        self,
    ) -> None:
        """When no sub-agent future is registered, the conductor's resume path runs."""
        from config.websocket.consumers.unified_agent_conversation import (
            UnifiedAgentConsumer,
        )

        consumer = UnifiedAgentConsumer()
        consumer.session_id = "t"
        consumer._is_connected = True
        consumer.user_id = None
        consumer.corpus = None
        consumer.document = None

        # No sub-agent futures registered.  The consumer should fall through
        # and call self.agent.resume_with_approval.  Note: the consumer
        # iterates the result of resume_with_approval with ``async for`` —
        # so this must be a generator function (not a coroutine that
        # *returns* a generator).
        resume_calls: list[tuple[int, bool]] = []

        def _resume(msg_id, approved, stream=True):
            resume_calls.append((msg_id, approved))

            async def _empty():
                if False:  # pragma: no cover
                    yield None

            return _empty()

        stub_agent = MagicMock()
        stub_agent.resume_with_approval = _resume
        consumer.agent = stub_agent

        sent: list[dict] = []

        async def fake_send_safe(msg_type, content="", data=None):
            sent.append({"msg_type": msg_type, "content": content, "data": data or {}})
            return True

        consumer._send_safe = fake_send_safe  # type: ignore[method-assign]

        await consumer._handle_approval_decision(
            {"approval_decision": True, "llm_message_id": 5555}
        )

        self.assertEqual(resume_calls, [(5555, True)])

    # ---- H. disconnect during sub-agent approval cancels pending futures ----
    async def test_disconnect_cancels_pending_approval_futures(self) -> None:
        """A socket close while a sub-agent is awaiting approval must
        cancel its pending future so the delegation tool body unwinds
        instead of leaking the asyncio task forever.
        """
        from config.websocket.consumers.unified_agent_conversation import (
            UnifiedAgentConsumer,
        )

        agent = await database_sync_to_async(AgentConfiguration.objects.create)(
            name="Hanger",
            slug="hanger",
            description="never returns",
            scope="GLOBAL",
            is_active=True,
            is_public=True,
            creator=self.user,
            system_instructions="hang",
        )

        consumer = UnifiedAgentConsumer()
        consumer.session_id = "t"
        consumer._is_connected = True
        consumer.conversation_id = None
        consumer.user_id = None
        consumer.corpus = None
        consumer.document = None
        consumer.scope = {"user": self.user}

        # Stub out send_safe + cleanup_auth_handshake so disconnect() runs
        # in isolation.
        async def fake_send_safe(msg_type, content="", data=None):
            return True

        async def fake_cleanup():
            return None

        consumer._send_safe = fake_send_safe  # type: ignore[method-assign]
        consumer.cleanup_auth_handshake = fake_cleanup  # type: ignore[method-assign]

        box: dict = {"value": 9999}
        relay = consumer._build_stream_relay_factory(parent_message_id_box=box)(
            agent, False
        )

        # Kick off the approval await — it should register a future and block.
        approval_task = asyncio.create_task(
            relay.on_approval({"name": "t", "arguments": {}})
        )

        # Wait until the future is registered.
        for _ in range(50):
            if (9999, agent.id) in consumer._pending_approvals:
                break
            await asyncio.sleep(0.01)
        else:
            approval_task.cancel()
            raise RuntimeError("relay never registered the approval future")

        self.assertIn((9999, agent.id), consumer._pending_approvals)
        pending_future = consumer._pending_approvals[(9999, agent.id)]
        self.assertFalse(pending_future.done())

        # Now disconnect — it must cancel the pending future.
        await consumer.disconnect(close_code=1000)

        # Yield so the cancellation propagates through on_approval's finally
        # block (which pops the entry).
        with self.assertRaises(asyncio.CancelledError):
            await approval_task

        self.assertTrue(pending_future.cancelled())
        # The on_approval finally block removes the entry from the map.
        self.assertNotIn((9999, agent.id), consumer._pending_approvals)

    # ---- I. conductor approval routes correctly AFTER a sub-agent approval resolves ----
    async def test_conductor_approval_after_subagent_approval_resolves(self) -> None:
        """After a sub-agent approval drains, the conductor's OWN approval
        under a different ``llm_message_id`` must route through
        ``self.agent.resume_with_approval`` (i.e. the routing in
        ``_handle_approval_decision`` cleanly disambiguates because the
        sub-agent future is already popped).
        """
        from config.websocket.consumers.unified_agent_conversation import (
            UnifiedAgentConsumer,
        )

        agent = await database_sync_to_async(AgentConfiguration.objects.create)(
            name="Sub",
            slug="sub",
            description="sub-agent",
            scope="GLOBAL",
            is_active=True,
            is_public=True,
            creator=self.user,
            system_instructions="sub",
        )

        consumer = UnifiedAgentConsumer()
        consumer.session_id = "t"
        consumer._is_connected = True
        consumer.conversation_id = None
        consumer.user_id = None
        consumer.corpus = None
        consumer.document = None
        consumer.scope = {"user": self.user}

        sent: list[dict] = []

        async def fake_send_safe(msg_type, content="", data=None):
            sent.append({"msg_type": msg_type, "content": content, "data": data or {}})
            return True

        consumer._send_safe = fake_send_safe  # type: ignore[method-assign]

        # ---- Step 1: drive a sub-agent approval to completion. ----
        box: dict = {"value": 100}
        relay_factory = consumer._build_stream_relay_factory(
            parent_message_id_box=box,
        )
        relay = relay_factory(agent, False)

        async def _resolve_sub():
            for _ in range(50):
                if (100, agent.id) in consumer._pending_approvals:
                    break
                await asyncio.sleep(0.01)
            else:
                raise RuntimeError("sub-agent future never registered")
            await consumer._handle_approval_decision(
                {"approval_decision": True, "llm_message_id": 100}
            )

        sub_decision, _ = await asyncio.gather(
            relay.on_approval({"name": "subtool", "arguments": {}}),
            _resolve_sub(),
        )
        self.assertTrue(sub_decision.get("approved"))
        # The sub-agent future must have been drained.
        self.assertNotIn((100, agent.id), consumer._pending_approvals)

        # ---- Step 2: simulate the conductor's OWN approval (different msg id). ----
        resume_calls: list[tuple[int, bool]] = []

        def _resume(msg_id, approved, stream=True):
            resume_calls.append((msg_id, approved))

            async def _empty():
                if False:  # pragma: no cover
                    yield None

            return _empty()

        stub_agent = MagicMock()
        stub_agent.resume_with_approval = _resume
        consumer.agent = stub_agent

        await consumer._handle_approval_decision(
            {"approval_decision": False, "llm_message_id": 200}
        )

        # The conductor path ran — no sub-agent future under id=200, so
        # we fell through to ``self.agent.resume_with_approval``.
        self.assertEqual(resume_calls, [(200, False)])

    # ---- J. multiple pinned delegations create distinct ChatMessage rows ----
    async def test_multiple_pinned_delegations_create_distinct_rows(self) -> None:
        """Two pinned delegations in one turn must persist two distinct
        ChatMessage rows with distinct ``agent_configuration`` FKs.
        """
        from config.websocket.consumers.unified_agent_conversation import (
            UnifiedAgentConsumer,
        )

        agent_a = await database_sync_to_async(AgentConfiguration.objects.create)(
            name="Pin-A",
            slug="pin-a",
            description="A",
            scope="GLOBAL",
            is_active=True,
            is_public=True,
            creator=self.user,
            system_instructions="a",
        )
        agent_b = await database_sync_to_async(AgentConfiguration.objects.create)(
            name="Pin-B",
            slug="pin-b",
            description="B",
            scope="GLOBAL",
            is_active=True,
            is_public=True,
            creator=self.user,
            system_instructions="b",
        )

        conversation = await database_sync_to_async(Conversation.objects.create)(
            title="t-multi",
            creator=self.user,
            chat_with_corpus=self.corpus,
        )
        parent_msg = await database_sync_to_async(ChatMessage.objects.create)(
            conversation=conversation,
            msg_type=MessageTypeChoices.LLM,
            content="conductor turn",
            creator=self.user,
            state=MessageStateChoices.COMPLETED,
        )

        consumer = UnifiedAgentConsumer()
        consumer.session_id = "t"
        consumer._is_connected = True
        consumer.conversation_id = conversation.id
        consumer.user_id = self.user.id
        consumer.corpus = self.corpus
        consumer.document = None
        consumer.scope = {"user": self.user}

        async def fake_send_safe(msg_type, content="", data=None):
            return True

        consumer._send_safe = fake_send_safe  # type: ignore[method-assign]

        box: dict = {"value": parent_msg.id}
        factory = consumer._build_stream_relay_factory(parent_message_id_box=box)
        relay_a = factory(agent_a, True)
        relay_b = factory(agent_b, True)

        id_a = await relay_a.on_finish("hello from A")
        id_b = await relay_b.on_finish("hello from B")

        self.assertIsNotNone(id_a)
        self.assertIsNotNone(id_b)
        self.assertNotEqual(id_a, id_b)

        row_a = await ChatMessage.objects.aget(id=id_a)
        row_b = await ChatMessage.objects.aget(id=id_b)
        self.assertEqual(row_a.agent_configuration_id, agent_a.id)
        self.assertEqual(row_b.agent_configuration_id, agent_b.id)
        self.assertEqual(row_a.parent_message_id, parent_msg.id)
        self.assertEqual(row_b.parent_message_id, parent_msg.id)
        self.assertEqual(row_a.content, "hello from A")
        self.assertEqual(row_b.content, "hello from B")

    # ---- K. stale delegation tools must NOT leak into a mention-less turn ----
    async def test_no_stale_delegation_tools_after_mentioned_turn(self) -> None:
        """Turn 1 mentions an agent → conductor is built with delegate_to_<slug>.
        Turn 2 omits the mention → conductor MUST be rebuilt without any
        delegate_to_* tools attached.  Otherwise the LLM still sees the
        delegation tool definition in its context and could silently invoke
        it on a turn the user did not intend.
        """
        await database_sync_to_async(AgentConfiguration.objects.create)(
            name="Researcher",
            slug="researcher",
            description="r",
            scope="GLOBAL",
            is_active=True,
            is_public=True,
            creator=self.user,
            system_instructions="r",
        )

        communicator = await self._connect()

        # Capture every factory call so we can inspect turn 1 vs turn 2 tools.
        captured_calls: list[dict] = []

        async def _fake_factory(*args, **kwargs):
            captured_calls.append(kwargs)
            return _StubAgent(self._build_simple_stream_factory())

        with patch(
            "config.websocket.consumers.unified_agent_conversation.agents.for_corpus",
            side_effect=_fake_factory,
        ):
            # Turn 1 — with mention
            await communicator.send_to(
                json.dumps({"query": "Try [R](/agents/researcher) please"})
            )
            await _consume_until_finish(communicator)

            # Turn 2 — NO mention
            await communicator.send_to(
                json.dumps({"query": "Just a follow-up question with no mention"})
            )
            await _consume_until_finish(communicator)

        await communicator.disconnect()

        # At least two factory calls — one per turn.  The first must include a
        # delegate_to_* tool; the second must not.
        self.assertGreaterEqual(len(captured_calls), 2)

        def _delegate_names(kwargs: dict) -> list[str]:
            tools = kwargs.get("tools") or []
            return [
                getattr(getattr(t, "metadata", None), "name", None) or ""
                for t in tools
                if "delegate_to_"
                in (getattr(getattr(t, "metadata", None), "name", None) or "")
            ]

        turn1_delegate_names = _delegate_names(captured_calls[0])
        turn2_delegate_names = _delegate_names(captured_calls[-1])

        self.assertIn("delegate_to_researcher", turn1_delegate_names)
        self.assertEqual(
            turn2_delegate_names,
            [],
            f"Turn-2 conductor still has stale delegation tools: "
            f"{turn2_delegate_names}",
        )
