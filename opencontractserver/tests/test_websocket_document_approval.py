from __future__ import annotations

"""Websocket consumer – approval-gate integration test.

This test focuses solely on the new pause / approval / resume workflow.
It patches the agent factory so no LLM calls are made while exercising the
consumer end-to-end through Channels' ``WebsocketCommunicator``.
"""

import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from channels.testing import WebsocketCommunicator
from django.test.utils import override_settings

from config.websocket.middleware import WS_AUTH_SUBPROTOCOL
from opencontractserver.llms.agents.core_agents import (
    ApprovalNeededEvent,
    ContentEvent,
    FinalEvent,
)
from opencontractserver.tests.base import WebsocketFixtureBaseTestCase

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# Dummy agent that replicates pause → resume behaviour without real LLM.
# ---------------------------------------------------------------------------


class _DummyPauseAgent:
    """Mimics CoreAgent but hard-codes the approval flow."""

    _USER_ID = 123
    _LLM_ID = 456

    async def stream(
        self, message: str, **kwargs
    ) -> AsyncGenerator[Any]:  # noqa: D401 – generator sig
        # Immediately pause and request approval
        yield ApprovalNeededEvent(
            pending_tool_call={
                "name": "restricted_tool",
                "arguments": {},
                "tool_call_id": "tc-1",
            },
            user_message_id=self._USER_ID,
            llm_message_id=self._LLM_ID,
            metadata={"state": "awaiting_approval"},
        )

    def resume_with_approval(
        self, llm_message_id: int, approved: bool, **kwargs
    ):  # noqa: D401
        async def _gen():
            text = "Approved" if approved else "Rejected"
            yield ContentEvent(
                content=text,
                accumulated_content=text,
                user_message_id=self._USER_ID,
                llm_message_id=self._LLM_ID,
            )
            yield FinalEvent(
                accumulated_content=text,
                user_message_id=self._USER_ID,
                llm_message_id=self._LLM_ID,
                sources=[],
            )

        return _gen()

    # The consumer calls get_conversation_id() for logging; provide stub.
    def get_conversation_id(self):  # noqa: D401 – stub
        return None


@pytest.mark.serial
class WebsocketApprovalGateTestCase(WebsocketFixtureBaseTestCase):
    """End-to-end test of the approval gate through the websocket consumer.

    Marked as serial because websocket tests use async event loops that
    can conflict with pytest-xdist workers.
    """

    @pytest.mark.asyncio
    async def test_pause_and_approve_via_websocket(self):  # noqa: D401 – async test
        # ------------------------------------------------------------------
        # Monkey-patch the high-level factory so the consumer gets our dummy.
        # ------------------------------------------------------------------
        from opencontractserver.llms import agents as _agents_module

        async def _fake_for_document(*args, **kwargs):  # noqa: D401 – stub
            return _DummyPauseAgent()

        with override_settings(
            LLMS_DEFAULT_AGENT_FRAMEWORK="pydantic_ai",
        ), pytest.MonkeyPatch().context() as mp:
            mp.setattr(_agents_module, "for_document", _fake_for_document, raising=True)

            # Build websocket path using unified agent-chat endpoint
            ws_path = (
                f"ws/agent-chat/?document_id={self.doc.id}"
                f"&corpus_id={self.corpus.id}"
            )

            communicator = WebsocketCommunicator(
                self.application,
                ws_path,
                subprotocols=[WS_AUTH_SUBPROTOCOL, self.token],
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            # Drain initial AUTH_OK frame from auth handshake mixin
            raw = await communicator.receive_from(timeout=5)
            self.assertEqual(json.loads(raw)["type"], "AUTH_OK")

            # ---------------- send first query ----------------
            await communicator.send_to(json.dumps({"query": "run sensitive"}))

            # consume until we receive the pause-frame
            approval_payload = None
            while True:
                first_msg = await communicator.receive_from(timeout=10)
                pl = json.loads(first_msg)
                if pl["type"] == "ASYNC_APPROVAL_NEEDED":
                    approval_payload = pl
                    break
            llm_msg_id = approval_payload["data"]["message_id"]

            # ---------------- send approval decision -----------
            await communicator.send_to(
                json.dumps(
                    {
                        "approval_decision": True,
                        "llm_message_id": llm_msg_id,
                    }
                )
            )

            # Capture events until FINISH
            finished = False
            while not finished:
                ws_msg = await communicator.receive_from(timeout=10)
                ws_payload = json.loads(ws_msg)
                if ws_payload["type"] == "ASYNC_FINISH":
                    finished = True
                    self.assertIn("Approved", ws_payload["content"])

            await communicator.disconnect()

            # Note: dummy agent does not persist messages; DB check omitted.
