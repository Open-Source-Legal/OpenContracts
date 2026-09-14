"""Registered moderation tools must act as the account bound by their factory."""

import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from asgiref.sync import async_to_sync
from django.test import TransactionTestCase

from opencontractserver.conversations.models import (
    ChatMessage,
    Conversation,
    ConversationTypeChoices,
    MessageTypeChoices,
    ModerationAction,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.llms.agents import agent_factory as factory
from opencontractserver.llms.api import _resolve_tools
from opencontractserver.llms.tools.pydantic_ai_tools import PydanticAIDependencies
from opencontractserver.users.models import User

NAMES = ("lock_thread", "unlock_thread", "pin_thread", "unpin_thread", "delete_message")


class ModeratorContextBindingTests(TransactionTestCase):
    def setUp(self):
        self.actor = User.objects.create_user(username="moderator-binding-actor")
        self.owner = User.objects.create_user(username="moderator-binding-owner")
        self.origin = Corpus.objects.create(creator=self.actor, title="Origin corpus")
        self.target = Corpus.objects.create(creator=self.owner, title="Target corpus")

    def tools(self, actor, corpus):
        specs = _resolve_tools(list(NAMES))
        with patch(
            "opencontractserver.llms.agents.pydantic_ai_agents."
            "PydanticAICorpusAgent.create",
            new_callable=AsyncMock,
        ) as construct, patch.object(
            factory, "get_default_llm_spec", return_value=""
        ), patch.object(
            factory, "_inject_temporal_grounding", new_callable=AsyncMock
        ):
            async_to_sync(factory.UnifiedAgentFactory.create_corpus_agent)(
                corpus,
                user_id=actor.pk,
                tools=[*specs],
                skip_approval_gate=True,
            )
        context = SimpleNamespace(
            deps=PydanticAIDependencies(
                user_id=actor.pk, corpus_id=corpus.pk, skip_approval_gate=True
            )
        )
        return context, {tool.__name__: tool for tool in construct.call_args.args[2]}

    def resource(self, name):
        thread = Conversation.objects.create(
            creator=self.owner,
            chat_with_corpus=self.target,
            conversation_type=ConversationTypeChoices.THREAD,
            title="Moderation target",
            is_locked=name == "unlock_thread",
            is_pinned=name == "unpin_thread",
        )
        if name == "delete_message":
            message = ChatMessage.objects.create(
                creator=self.owner,
                conversation=thread,
                msg_type=MessageTypeChoices.HUMAN,
                content="Moderation target message",
            )
            return message, {"message_id": message.pk}
        return thread, {"thread_id": thread.pk}

    def test_another_users_id_cannot_authorize_moderation(self):
        context, tools = self.tools(self.actor, self.origin)
        for name in NAMES:
            with self.subTest(tool=name):
                resource, kwargs = self.resource(name)
                before = (
                    type(resource).all_objects.filter(pk=resource.pk).values().get()
                )
                count = ModerationAction.objects.count()
                with self.assertRaises(PermissionError):
                    async_to_sync(tools[name])(
                        context,
                        **kwargs,
                        reason="Untrusted actor substitution",
                        moderator_id=self.owner.pk,
                    )
                self.assertEqual(ModerationAction.objects.count(), count)
                self.assertEqual(
                    type(resource).all_objects.filter(pk=resource.pk).values().get(),
                    before,
                )

    def test_bound_moderator_succeeds_without_an_actor_argument(self):
        context, tools = self.tools(self.owner, self.target)
        for name in NAMES:
            for supplied in ({}, {"moderator_id": self.actor.pk}):
                with self.subTest(tool=name, supplied=supplied):
                    tool = tools[name]
                    self.assertNotIn("moderator_id", inspect.signature(tool).parameters)
                    resource, kwargs = self.resource(name)
                    result = async_to_sync(tool)(
                        context, **kwargs, **supplied, reason="Bound moderator"
                    )
                    self.assertTrue(result["success"])
                    action = ModerationAction.objects.latest("pk")
                    self.assertEqual(action.moderator_id, self.owner.pk)
                    self.assertEqual(action.creator_id, self.owner.pk)
                    resource.refresh_from_db()
                    if name == "delete_message":
                        self.assertIsNotNone(resource.deleted_at)
                    else:
                        self.assertEqual(resource.is_locked, name == "lock_thread")
                        self.assertEqual(resource.is_pinned, name == "pin_thread")
