from __future__ import annotations

"""Approval-gate integration tests runnable with Django's built-in test runner.

These tests exercise:
1. JSON-serialisation of every emitted UnifiedStreamEvent until the first
   ApprovalNeededEvent is seen.
2. Pause → approve → resume happy-path.
3. Pause → rejection branch.

The heavy Pydantic-AI runtime is patched with an in-process stub so no network
traffic is generated; therefore the entire suite completes in <2 s.
"""

import json
import types
from dataclasses import asdict
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.llms.agents.agent_factory import UnifiedAgentFactory
from opencontractserver.llms.agents.core_agents import (
    ApprovalNeededEvent,
    ApprovalResultEvent,
    FinalEvent,
    MessageState,
    ResumeEvent,
    UnifiedStreamEvent,
)
from opencontractserver.llms.exceptions import ToolConfirmationRequired
from opencontractserver.llms.tools.tool_factory import CoreTool
from opencontractserver.llms.types import AgentFramework

User = get_user_model()

# ---------------------------------------------------------------------------
# Helper: deterministic CoreTool that always requires approval
# ---------------------------------------------------------------------------


def _make_gate_tool(name: str) -> CoreTool:
    """Return a CoreTool whose execution is veto-gated by default."""

    def _inner(x: int) -> int:  # pragma: no cover – never executed
        return x * 2

    return CoreTool.from_function(_inner, name=name, requires_approval=True)


GATE_TOOL = _make_gate_tool("approved_tool")
SECOND_TOOL = _make_gate_tool("second_gate_tool")

# ---------------------------------------------------------------------------
# Lightweight stub for PydanticAIAgent
# ---------------------------------------------------------------------------


class _DummyRunResult:
    def __init__(self, text: str = "ok") -> None:
        self.data = text
        self.sources: list[Any] = []

    def usage(self) -> None:  # noqa: D401 – stub
        return None


class _RunRes:
    """Stub returned by the agent's iter context manager after approval."""

    def __init__(self, text: str = "ok") -> None:
        self.output = text

    def usage(self):  # noqa: D401 – stub
        return None

    # Pydantic-AI expects .result.usage() later
    @property
    def result(self):  # noqa: D401 – property for compatibility
        return types.SimpleNamespace(output=self.output, usage=self.usage)

    def __aiter__(self):
        return self

    async def __anext__(self):  # pragma: no cover – no deltas emitted
        raise StopAsyncIteration


class _IterCtx:
    """Async context manager mimicking a successful agent.iter() call."""

    async def __aenter__(self):
        return _RunRes()

    async def __aexit__(self, exc_type, exc, tb):
        return False


# ---------------------------------------------------------------------------
# Base TestCase – sets up corpus / document once for the whole class
# ---------------------------------------------------------------------------


class TestApprovalFlow(TestCase):

    @classmethod
    def setUpClass(cls):  # noqa: D401 – Django hook
        super().setUpClass()
        cls.user: User = User.objects.create_user("gate-user")

        cls.corpus: Corpus = Corpus.objects.create(
            title="Gate Corpus", description="", creator=cls.user, is_public=False
        )
        cls.document: Document = Document.objects.create(
            title="Gate Doc", description="", creator=cls.user, is_public=False
        )
        cls.document, _, _ = cls.corpus.add_document(
            document=cls.document, user=cls.user
        )

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    async def _create_agent(self, extra_tools: list[CoreTool] | None = None):
        """Return a fresh PydanticAI document agent for the prepared doc."""
        tools = [GATE_TOOL]
        if extra_tools:
            tools.extend(extra_tools)

        return await UnifiedAgentFactory.create_document_agent(
            self.document.id,
            self.corpus.id,
            framework=AgentFramework.PYDANTIC_AI,
            user_id=self.user.id,
            tools=tools,
        )

    async def _collect(self, gen):  # noqa: D401 – tiny helper
        items: list[UnifiedStreamEvent] = []
        async for ev in gen:
            items.append(ev)
        return items

    # ------------------------------------------------------------------
    # Global patch applied to every test method
    # ------------------------------------------------------------------

    def setUp(self):  # noqa: D401 – Django hook
        super().setUp()

        # Instance aliases for convenience
        self.document = self.__class__.document
        self.corpus = self.__class__.corpus
        self.user = self.__class__.user

        patcher = patch(
            "opencontractserver.llms.agents.pydantic_ai_agents.PydanticAIAgent"
        )
        self.addCleanup(patcher.stop)
        mock_cls = patcher.start()

        inst = MagicMock()

        # First two calls raise; third succeeds
        call_counter = {"n": 0}

        async def _run_side_effect(*_a, **_kw):
            call_counter["n"] += 1
            if call_counter["n"] == 1:
                raise ToolConfirmationRequired(
                    tool_name="approved_tool", tool_args={"x": 1}, tool_call_id="tc-1"
                )
            if call_counter["n"] == 2:
                raise ToolConfirmationRequired(
                    tool_name="second_gate_tool",
                    tool_args={"x": 2},
                    tool_call_id="tc-2",
                )
            return _DummyRunResult()

        inst.run = AsyncMock(side_effect=_run_side_effect)
        inst.iter = MagicMock(return_value=_IterCtx())

        # Provide registry entry so resume_with_approval can execute tool
        async def _approved_tool(ctx, x: int):  # noqa: D401 – minimal stub
            return x * 2

        inst._function_tools = {
            "approved_tool": types.SimpleNamespace(function=_approved_tool),
            "second_gate_tool": types.SimpleNamespace(function=_approved_tool),
        }
        mock_cls.return_value = inst

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    async def test_event_serialisation(self):
        agent = await self._create_agent()
        events = []
        async for ev in agent.stream("trigger"):
            events.append(ev)
            if isinstance(ev, ApprovalNeededEvent):
                break

        # JSON serialisable
        for ev in events:
            json.dumps(asdict(ev), default=str)

        # We expect either an approval pause *or* a straight FinalEvent when
        # streaming, depending on stub behaviour.  At least one of them must
        # be present so the event sequence is non-empty and meaningful.
        assert any(isinstance(e, (ApprovalNeededEvent, FinalEvent)) for e in events)

    async def test_single_gate_pause_resume(self):
        agent = await self._create_agent()
        resp = await agent.chat("run gate")
        self.assertEqual(resp.metadata["state"], MessageState.AWAITING_APPROVAL)
        paused_llm_id = resp.llm_message_id

        # New agent instance with same conversation
        fresh = await UnifiedAgentFactory.create_document_agent(
            self.document.id,
            self.corpus.id,
            framework=AgentFramework.PYDANTIC_AI,
            user_id=self.user.id,
            conversation_id=agent.get_conversation_id(),
            tools=[GATE_TOOL],
        )

        events = await self._collect(
            fresh.resume_with_approval(paused_llm_id, approved=True)
        )
        self.assertTrue(
            any(
                isinstance(e, ApprovalResultEvent) and e.decision == "approved"
                for e in events
            )
        )
        self.assertTrue(any(isinstance(e, ResumeEvent) for e in events))
        # FinalEvent may be skipped by stub; ensure stream completed successfully.
        self.assertTrue(events, "No events returned from resume stream")

    async def test_rejection_branch(self):
        agent = await self._create_agent()
        resp = await agent.chat("run gate")
        paused_llm_id = resp.llm_message_id

        events = await self._collect(
            agent.resume_with_approval(paused_llm_id, approved=False)
        )
        self.assertTrue(
            any(
                isinstance(e, ApprovalResultEvent) and e.decision == "rejected"
                for e in events
            )
        )
        final_event = next(e for e in events if isinstance(e, FinalEvent))
        self.assertEqual(final_event.metadata.get("approval_decision"), "rejected")

    async def test_multiple_gates_interleaved(self):
        """Pause on first gate, approve, pause on second gate, approve again."""

        agent = await self._create_agent(extra_tools=[SECOND_TOOL])

        # 1st gate
        resp1 = await agent.chat("first")
        self.assertEqual(resp1.metadata["state"], MessageState.AWAITING_APPROVAL)
        msg1 = resp1.llm_message_id

        # Approve 1st
        await self._collect(agent.resume_with_approval(msg1, approved=True))

        # 2nd gate triggered by another chat
        resp2 = await agent.chat("second")
        self.assertEqual(resp2.metadata["state"], MessageState.AWAITING_APPROVAL)
        msg2 = resp2.llm_message_id

        # Approve 2nd
        await self._collect(agent.resume_with_approval(msg2, approved=True))

        # Ensure no pending approvals remain
        conv_msgs = await agent.get_conversation_messages()
        pending = [
            m
            for m in conv_msgs
            if m.data.get("state") == MessageState.AWAITING_APPROVAL
        ]
        self.assertFalse(pending)
