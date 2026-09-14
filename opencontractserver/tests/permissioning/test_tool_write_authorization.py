"""Tool confirmation cannot replace current actor/resource WRITE permission."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.core.files.base import ContentFile
from django.test import TransactionTestCase
from django.utils import timezone
from pydantic_ai.models.test import TestModel

from opencontractserver.conversations.models import ChatMessage
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.llms import agents
from opencontractserver.llms.agents.core_agents import FinalEvent, MessageState
from opencontractserver.llms.agents.pydantic_ai_agents import _get_function_tools
from opencontractserver.llms.tools.pydantic_ai_tools import (
    PydanticAIDependencies,
    _check_user_permissions,
)
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.users.models import User
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user


async def finish(*args, **kwargs):
    yield FinalEvent(content="Done", accumulated_content="Done", metadata={})


async def collect(agent, message_id):
    return [event async for event in agent.resume_with_approval(message_id, True)]


class ToolWriteAuthorizationTests(TransactionTestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="tool-write-owner")
        self.reader = User.objects.create_user(username="tool-write-reader")
        self.corpus = Corpus.objects.create(
            creator=self.owner, title="Write corpus", is_public=True
        )
        self.document = Document.objects.create(
            creator=self.owner,
            title="Write document",
            description="Original",
            is_public=True,
            file_type="text/plain",
            processing_started=timezone.now(),
        )
        self.document.txt_extract_file.save("write.txt", ContentFile(b"Public text"))

    def agent(self, user, kind="document"):
        with patch(
            "opencontractserver.llms.agents.pydantic_ai_agents.abuild_agent_model",
            return_value=TestModel(call_tools=[]),
        ):
            if kind == "corpus":
                return async_to_sync(agents.for_corpus)(
                    corpus=self.corpus,
                    user_id=user.pk,
                    persist=True,
                    model="openai:gpt-4o",
                    embedder="tool.write.no_embedding",
                )
            return async_to_sync(agents.for_document)(
                document=self.document,
                corpus=self.corpus,
                user_id=user.pk,
                persist=True,
                model="openai:gpt-4o",
                embedder="tool.write.no_embedding",
            )

    def pending(self, agent):
        message_id = async_to_sync(agent.create_placeholder_message)()
        ChatMessage.objects.filter(pk=message_id).update(
            state=MessageState.AWAITING_APPROVAL,
            data={
                "state": MessageState.AWAITING_APPROVAL,
                "pending_tool_call": {
                    "name": "update_document_description",
                    "arguments": {"new_description": "Approved edit"},
                    "tool_call_id": "write-call",
                },
            },
        )
        return message_id

    def test_anonymous_and_context_free_writes_are_denied(self):
        for deps in (
            None,
            PydanticAIDependencies(user_id=self.owner.pk),
            PydanticAIDependencies(document_id=self.document.pk),
        ):
            with self.subTest(deps=deps):
                ctx: Any = SimpleNamespace(deps=deps)
                with self.assertRaisesRegex(PermissionError, "actor and resource"):
                    async_to_sync(_check_user_permissions)(ctx, require_write=True)

    def test_all_context_built_writers_enforce_write_before_the_body(self):
        for kind, names in (
            (
                "document",
                (
                    "update_document_description",
                    "update_document_summary",
                    "add_document_note",
                    "update_document_note",
                    "duplicate_annotations",
                    "add_exact_string_annotations",
                ),
            ),
            ("corpus", ("update_corpus_description",)),
        ):
            agent = self.agent(self.reader, kind)
            registry = _get_function_tools(agent.pydantic_ai_agent)
            for name in names:
                with self.subTest(kind=kind, tool=name):
                    tool = registry[name].function
                    self.assertTrue(tool.core_tool.requires_write_permission)
                    for approved in (False, True):
                        ctx = SimpleNamespace(
                            deps=agent.agent_deps.model_copy(
                                update={"skip_approval_gate": approved}
                            )
                        )
                        with self.subTest(approved=approved):
                            with self.assertRaisesRegex(PermissionError, "WRITE"):
                                async_to_sync(tool)(ctx)

    def test_real_approval_rechecks_write_and_account_activity(self):
        for outcome in ("owner", "reader", "write-revoked", "actor-disabled"):
            with self.subTest(outcome=outcome):
                self.reader.is_active = True
                self.reader.save(update_fields=["is_active"])
                self.document.description = "Original"
                self.document.save(update_fields=["description"])
                set_permissions_for_obj_to_user(
                    self.reader,
                    self.document,
                    [] if outcome == "reader" else [PermissionTypes.CRUD],
                )
                agent = self.agent(self.owner if outcome == "owner" else self.reader)
                message_id = self.pending(agent)
                if outcome == "write-revoked":
                    set_permissions_for_obj_to_user(self.reader, self.document, [])
                elif outcome == "actor-disabled":
                    User.objects.filter(pk=self.reader.pk).update(is_active=False)
                with patch.object(agent, "_stream_core", new=finish):
                    if outcome == "owner":
                        events = async_to_sync(collect)(agent, message_id)
                        self.assertIsInstance(events[-1], FinalEvent)
                    else:
                        with self.assertRaises(PermissionError):
                            async_to_sync(collect)(agent, message_id)
                self.document.refresh_from_db()
                self.assertEqual(
                    self.document.description,
                    "Approved edit" if outcome == "owner" else "Original",
                )
                self.assertEqual(
                    ChatMessage.objects.get(pk=message_id).state,
                    (
                        MessageState.COMPLETED
                        if outcome == "owner"
                        else MessageState.AWAITING_APPROVAL
                    ),
                )
                self.assertFalse(agent.agent_deps.skip_approval_gate)
                self.assertFalse(agent.config._approval_bypass_allowed)
