"""Real socket approval dispatch binds messages to the active conversation."""

from unittest.mock import patch

from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase
from pydantic_ai.models.test import TestModel

from config.asgi import application
from config.jwt_auth.shortcuts import get_token
from config.websocket import middleware
from opencontractserver.agents.models import AgentConfiguration
from opencontractserver.conversations.models import ChatMessage, Conversation
from opencontractserver.corpuses.models import Corpus
from opencontractserver.llms import agents
from opencontractserver.llms.agents.core_agents import (
    AgentConfig,
    CoreConversationManager,
    FinalEvent,
    MessageState,
)
from opencontractserver.llms.agents.pydantic_ai_agents import PydanticAICoreAgent
from opencontractserver.llms.agents.pydantic_ai_factory import make_pydantic_ai_agent
from opencontractserver.llms.tools.pydantic_ai_tools import (
    PydanticAIDependencies,
    PydanticAIToolFactory,
)
from opencontractserver.shared.services import BaseService
from opencontractserver.users.models import User


async def finish(*args, **kwargs):
    yield FinalEvent(content="Done", accumulated_content="Done", metadata={})


async def terminal_frames(socket):
    frames = []
    while True:
        frame = await socket.receive_json_from(timeout=5)
        frames.append(frame)
        if frame["type"] in ("ASYNC_FINISH", "SYNC_CONTENT", "AUTH_FAILED"):
            return frames


class ApprovalMessageBindingTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="approval-binding-user")
        other = User.objects.create_user(username="approval-binding-other")
        self.corpus = Corpus.objects.create(creator=self.user, title="Approval corpus")
        self.own = Conversation.objects.create(
            creator=self.user, chat_with_corpus=self.corpus, conversation_type="chat"
        )
        self.foreign = Conversation.objects.create(
            creator=other, conversation_type="chat"
        )
        self.other_owned = Conversation.objects.create(
            creator=self.user, conversation_type="chat"
        )
        self.selected = AgentConfiguration.objects.create(
            creator=self.user,
            name="Approval binding agent",
            scope="GLOBAL",
            is_active=True,
        )
        self.token = get_token(self.user)
        self.effects: list[str] = []

        async def witness(value: str) -> str:
            """Record approved execution without provider or target I/O."""
            self.effects.append(value)
            return value

        config = AgentConfig(
            user_id=self.user.pk,
            model_name="openai:gpt-4o",
            system_prompt="Approval binding",
        )
        self.agent = PydanticAICoreAgent(
            config,
            CoreConversationManager(self.own, self.user.pk, config),
            make_pydantic_ai_agent(
                model=TestModel(call_tools=[]),
                tools=[
                    PydanticAIToolFactory.from_function(witness, requires_approval=True)
                ],
            ),
            PydanticAIDependencies(user_id=self.user.pk, corpus_id=self.corpus.pk),
        )

    def message(self, conversation):
        return ChatMessage.objects.create(
            creator_id=conversation.creator_id,
            conversation=conversation,
            msg_type="LLM",
            content="Private pending content",
            state=MessageState.AWAITING_APPROVAL,
            data={
                "state": MessageState.AWAITING_APPROVAL,
                "pending_tool_call": {
                    "name": "witness",
                    "arguments": {"value": "Private pending argument"},
                    "tool_call_id": "approval-call",
                },
            },
        )

    async def decision(self, message, approved):
        socket = WebsocketCommunicator(
            application,
            f"/ws/agent-chat/?corpus_id={self.corpus.pk}&conversation_id={self.own.pk}&agent_id={self.selected.pk}",
            subprotocols=[middleware.WS_AUTH_SUBPROTOCOL, self.token],
        )
        with patch.object(agents, "for_corpus", return_value=self.agent), patch.object(
            self.agent, "stream", new=finish
        ), patch.object(self.agent, "_stream_core", new=finish):
            try:
                accepted, _ = await socket.connect()
                self.assertTrue(accepted)
                self.assertEqual((await socket.receive_json_from())["type"], "AUTH_OK")
                await socket.send_json_to({"query": "Initialize"})
                self.assertEqual(
                    (await terminal_frames(socket))[-1]["type"], "ASYNC_FINISH"
                )
                await socket.send_json_to(
                    {"approval_decision": approved, "llm_message_id": message.pk}
                )
                return await terminal_frames(socket)
            finally:
                await socket.disconnect()

    def test_approval_and_rejection_cannot_select_another_conversations_message(self):
        for conversation in (self.own, self.foreign, self.other_owned):
            for approved in (False, True):
                with self.subTest(conversation=conversation.pk, approved=approved):
                    self.effects.clear()
                    message = self.message(conversation)
                    before = message.data.copy()
                    self.assertEqual(
                        BaseService.filter_visible(ChatMessage, self.user)
                        .filter(pk=message.pk)
                        .exists(),
                        conversation.creator_id == self.user.pk,
                    )
                    frames = async_to_sync(self.decision)(message, approved)
                    message.refresh_from_db()
                    if conversation != self.own:
                        self.assertEqual(
                            frames,
                            [
                                {
                                    "type": "SYNC_CONTENT",
                                    "content": "",
                                    "data": {
                                        "error": f"Failed to resume after approval: ChatMessage {message.pk} not found"
                                    },
                                }
                            ],
                        )
                        self.assertEqual(message.data, before)
                        self.assertEqual(message.state, MessageState.AWAITING_APPROVAL)
                        self.assertEqual(self.effects, [])
                    else:
                        self.assertEqual(
                            message.data["state"],
                            (
                                MessageState.COMPLETED
                                if approved
                                else MessageState.CANCELLED
                            ),
                        )
                        self.assertEqual(
                            self.effects,
                            ["Private pending argument"] if approved else [],
                        )
                        result = next(
                            frame
                            for frame in frames
                            if frame["type"] == "ASYNC_APPROVAL_RESULT"
                        )
                        self.assertEqual(
                            result["data"]["pending_tool_call"],
                            before["pending_tool_call"],
                        )
                        self.assertEqual(frames[-1]["type"], "ASYNC_FINISH")

    def test_agent_without_a_conversation_cannot_resume_a_persisted_message(self):
        message = self.message(self.own)
        self.agent.conversation_manager.conversation = None

        async def attempt():
            return [
                event
                async for event in self.agent.resume_with_approval(message.pk, True)
            ]

        with self.assertRaisesMessage(
            ValueError, f"ChatMessage {message.pk} not found"
        ):
            async_to_sync(attempt)()
        message.refresh_from_db()
        self.assertEqual(message.data["state"], MessageState.AWAITING_APPROVAL)
        self.assertEqual(self.effects, [])
