"""
Coverage-focused tests for the strawberry-ported conversation/thread
mutations in ``config/graphql/conversation_mutations.py``.

``test_conversation_mutations_graphql.py`` already covers the happy paths,
the empty/locked/deleted validation branches on ``updateMessage``, and the
"no permission at all" IDOR-safe responses. This module targets the
remaining branches:

- Unauthenticated access (each of the six mutations)
- IDOR-safe not-found responses where the target row exists but is not
  visible to the caller
- "Visible via one path but not another" gaps that are real permission-
  boundary bugs if broken: a message individually shared without thread
  access (``replyToMessage``), and a message/conversation visible via
  corpus/thread context but without the specific CRUD/DELETE grant
- The resilience contract around ``@mentions``: parsing/linking failures
  must not fail the surrounding mutation (mirrors the existing
  ``test_update_message_reparses_mentions`` mocking pattern for the
  agent-trigger branches; extends it to the sibling mutations and to the
  mention-*failure* branches, which no existing test exercises)
- Malformed-message-id handling in ``updateMessage``: an id that decodes
  to a non-numeric pk raises ``ValueError`` from the ORM, uncaught by the
  narrow ``ChatMessage.DoesNotExist`` handler, falling through to the
  outer generic ``except Exception``

Several sibling ``except Exception:`` blocks that wrap only
``from_global_id(...)[1]`` are intentionally NOT targeted here: the
installed ``graphql_relay.utils.base64.unbase64`` swallows
``binascii.Error``/``UnicodeDecodeError``/``UnicodeEncodeError`` internally
and returns ``""`` rather than raising, and ``ResolvedGlobalId`` is a
2-tuple that can't ``IndexError`` on ``[1]``. Confirmed empirically (see
PR discussion) — these branches are unreachable through the GraphQL
client with the current dependency pin, not just untested. The typed
``except Conversation.DoesNotExist:`` / ``except ChatMessage.DoesNotExist:``
handlers that sit directly above a generic catch-all are unreachable for
the same reason: ``get_for_user_or_none`` already swallows
``DoesNotExist`` and returns ``None`` before a typed exception could ever
propagate out of the ``try`` block.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from graphql_relay import to_global_id

from config.graphql.schema import schema
from config.graphql.testing import Client
from opencontractserver.agents.models import AgentConfiguration
from opencontractserver.conversations.models import ChatMessage, Conversation
from opencontractserver.corpuses.models import Corpus
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()

# A syntactically well-formed global id whose decoded raw pk is
# non-numeric. ``from_global_id`` never raises on this, but the downstream
# ``ChatMessage.objects...get(pk=...)`` int-cast does, exercising the
# generic ``except Exception`` fallback without mocking anything.
_MALFORMED_PK = "not-an-int"

_AGENT_MENTION_CONTENT = "Hey [@test-agent](/agents/test-agent), take a look"


class _MockRequest:
    """Mirrors ConversationMutationsTestCase._execute_with_user's context."""

    def __init__(self, user):
        self.user = user
        self.META = {}


def _execute(query, user, variables=None):
    client = Client(schema)
    return client.execute(query, variables=variables, context_value=_MockRequest(user))


CREATE_THREAD_MUTATION = """
    mutation CreateThread($corpusId: String, $title: String!, $initialMessage: String!) {
        createThread(corpusId: $corpusId, title: $title, initialMessage: $initialMessage) {
            ok
            message
            obj {
                id
            }
        }
    }
"""

CREATE_THREAD_MESSAGE_MUTATION = """
    mutation CreateThreadMessage($conversationId: String!, $content: String!) {
        createThreadMessage(conversationId: $conversationId, content: $content) {
            ok
            message
            obj {
                id
            }
        }
    }
"""

REPLY_TO_MESSAGE_MUTATION = """
    mutation ReplyToMessage($parentMessageId: String!, $content: String!) {
        replyToMessage(parentMessageId: $parentMessageId, content: $content) {
            ok
            message
            obj {
                id
            }
        }
    }
"""

UPDATE_MESSAGE_MUTATION = """
    mutation UpdateMessage($messageId: ID!, $content: String!) {
        updateMessage(messageId: $messageId, content: $content) {
            ok
            message
            obj {
                id
                content
            }
        }
    }
"""

DELETE_CONVERSATION_MUTATION = """
    mutation DeleteConversation($conversationId: String!) {
        deleteConversation(conversationId: $conversationId) {
            ok
            message
        }
    }
"""

DELETE_MESSAGE_MUTATION = """
    mutation DeleteMessage($messageId: ID!) {
        deleteMessage(messageId: $messageId) {
            ok
            message
        }
    }
"""


def _make_global_agent(creator) -> AgentConfiguration:
    return AgentConfiguration.objects.create(
        name="Coverage Test Agent",
        slug="test-agent",
        scope="GLOBAL",
        description="Agent used to exercise the @mention trigger path",
        is_active=True,
        is_public=True,
        creator=creator,
    )


class CreateThreadCoverageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="ct_cov_user", password="pw")
        self.corpus = Corpus.objects.create(title="Coverage Corpus", creator=self.user)
        set_permissions_for_obj_to_user(
            self.user, self.corpus, [PermissionTypes.CRUD, PermissionTypes.READ]
        )

    def test_unauthenticated_raises(self):
        result = _execute(
            CREATE_THREAD_MUTATION,
            AnonymousUser(),
            {
                "corpusId": to_global_id("CorpusType", self.corpus.id),
                "title": "Anon Thread",
                "initialMessage": "hi",
            },
        )
        self.assertIsNotNone(result.get("errors"))

    def test_mention_parse_failure_does_not_fail_mutation(self):
        with patch(
            "config.graphql.conversation_mutations.parse_mentions_from_content",
            side_effect=ValueError("boom"),
        ):
            result = _execute(
                CREATE_THREAD_MUTATION,
                self.user,
                {
                    "corpusId": to_global_id("CorpusType", self.corpus.id),
                    "title": "Resilient Thread",
                    "initialMessage": "content that would normally be parsed",
                },
            )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["createThread"]
        self.assertTrue(data["ok"])
        self.assertEqual(data["message"], "Thread created successfully")

    def test_agent_mention_triggers_response(self):
        _make_global_agent(self.user)
        with patch(
            "config.graphql.conversation_mutations.trigger_agent_responses_for_message"
        ) as mock_task:
            result = _execute(
                CREATE_THREAD_MUTATION,
                self.user,
                {
                    "corpusId": to_global_id("CorpusType", self.corpus.id),
                    "title": "Agent Thread",
                    "initialMessage": _AGENT_MENTION_CONTENT,
                },
            )
            self.assertIsNone(result.get("errors"))
            data = result["data"]["createThread"]
            self.assertTrue(data["ok"])
            mock_task.delay.assert_called_once()

        conversation = Conversation.objects.get(title="Agent Thread")
        first_message = ChatMessage.objects.get(conversation=conversation)
        self.assertEqual(first_message.mentioned_agents.count(), 1)

    def test_unexpected_error_returns_generic_failure(self):
        with patch(
            "config.graphql.conversation_mutations.set_permissions_for_obj_to_user",
            side_effect=RuntimeError("boom"),
        ):
            result = _execute(
                CREATE_THREAD_MUTATION,
                self.user,
                {
                    "corpusId": to_global_id("CorpusType", self.corpus.id),
                    "title": "Doomed Thread",
                    "initialMessage": "hi",
                },
            )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["createThread"]
        self.assertFalse(data["ok"])
        self.assertEqual(data["message"], "Failed to create thread")


class CreateThreadMessageCoverageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="ctm_cov_user", password="pw")
        self.corpus = Corpus.objects.create(title="Coverage Corpus", creator=self.user)
        self.conversation = Conversation.objects.create(
            title="Coverage Thread",
            conversation_type="thread",
            chat_with_corpus=self.corpus,
            creator=self.user,
        )

    def test_unauthenticated_raises(self):
        result = _execute(
            CREATE_THREAD_MESSAGE_MUTATION,
            AnonymousUser(),
            {
                "conversationId": to_global_id(
                    "ConversationType", self.conversation.id
                ),
                "content": "hi",
            },
        )
        self.assertIsNotNone(result.get("errors"))

    def test_conversation_not_visible_returns_generic_denial(self):
        outsider = User.objects.create_user(username="ctm_cov_outsider", password="pw")
        result = _execute(
            CREATE_THREAD_MESSAGE_MUTATION,
            outsider,
            {
                "conversationId": to_global_id(
                    "ConversationType", self.conversation.id
                ),
                "content": "should fail",
            },
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["createThreadMessage"]
        self.assertFalse(data["ok"])
        self.assertEqual(data["message"], "Cannot post in this thread")

    def test_mention_parse_failure_does_not_fail_mutation(self):
        with patch(
            "config.graphql.conversation_mutations.parse_mentions_from_content",
            side_effect=ValueError("boom"),
        ):
            result = _execute(
                CREATE_THREAD_MESSAGE_MUTATION,
                self.user,
                {
                    "conversationId": to_global_id(
                        "ConversationType", self.conversation.id
                    ),
                    "content": "content that would normally be parsed",
                },
            )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["createThreadMessage"]
        self.assertTrue(data["ok"])
        self.assertEqual(data["message"], "Message posted successfully")

    def test_agent_mention_triggers_response(self):
        _make_global_agent(self.user)
        with patch(
            "config.graphql.conversation_mutations.trigger_agent_responses_for_message"
        ) as mock_task:
            result = _execute(
                CREATE_THREAD_MESSAGE_MUTATION,
                self.user,
                {
                    "conversationId": to_global_id(
                        "ConversationType", self.conversation.id
                    ),
                    "content": _AGENT_MENTION_CONTENT,
                },
            )
            self.assertIsNone(result.get("errors"))
            self.assertTrue(result["data"]["createThreadMessage"]["ok"])
            mock_task.delay.assert_called_once()

    def test_unexpected_error_returns_generic_failure(self):
        with patch(
            "config.graphql.conversation_mutations.set_permissions_for_obj_to_user",
            side_effect=RuntimeError("boom"),
        ):
            result = _execute(
                CREATE_THREAD_MESSAGE_MUTATION,
                self.user,
                {
                    "conversationId": to_global_id(
                        "ConversationType", self.conversation.id
                    ),
                    "content": "hi",
                },
            )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["createThreadMessage"]
        self.assertFalse(data["ok"])
        self.assertEqual(data["message"], "Failed to create message")


class ReplyToMessageCoverageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="reply_cov_user", password="pw")
        self.corpus = Corpus.objects.create(title="Coverage Corpus", creator=self.user)
        self.conversation = Conversation.objects.create(
            title="Coverage Thread",
            conversation_type="thread",
            chat_with_corpus=self.corpus,
            creator=self.user,
        )
        self.parent_message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="HUMAN",
            content="Parent message",
            creator=self.user,
        )

    def test_unauthenticated_raises(self):
        result = _execute(
            REPLY_TO_MESSAGE_MUTATION,
            AnonymousUser(),
            {
                "parentMessageId": to_global_id("MessageType", self.parent_message.id),
                "content": "hi",
            },
        )
        self.assertIsNotNone(result.get("errors"))

    def test_parent_message_not_visible_returns_generic_denial(self):
        outsider = User.objects.create_user(
            username="reply_cov_outsider", password="pw"
        )
        result = _execute(
            REPLY_TO_MESSAGE_MUTATION,
            outsider,
            {
                "parentMessageId": to_global_id("MessageType", self.parent_message.id),
                "content": "should fail",
            },
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["replyToMessage"]
        self.assertFalse(data["ok"])
        self.assertEqual(
            data["message"], "You do not have permission to reply to this message"
        )

    def test_message_shared_without_thread_access_still_denies_reply(self):
        """A user granted explicit READ on the parent message (but nothing
        on the corpus/conversation) can *see* the message via
        ``ChatMessageQuerySet.visible_to_user``'s explicit-grant branch,
        but ``replyToMessage`` gates on conversation READ, not message
        READ — the reply must still be denied (IDOR: don't leak thread
        content through a narrower per-message share)."""
        shared_with = User.objects.create_user(
            username="reply_cov_shared", password="pw"
        )
        set_permissions_for_obj_to_user(
            shared_with, self.parent_message, [PermissionTypes.READ]
        )
        result = _execute(
            REPLY_TO_MESSAGE_MUTATION,
            shared_with,
            {
                "parentMessageId": to_global_id("MessageType", self.parent_message.id),
                "content": "should still fail",
            },
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["replyToMessage"]
        self.assertFalse(data["ok"])
        self.assertEqual(data["message"], "Cannot reply in this thread")

    def test_locked_thread_denies_reply(self):
        self.conversation.is_locked = True
        self.conversation.save(update_fields=["is_locked"])
        result = _execute(
            REPLY_TO_MESSAGE_MUTATION,
            self.user,
            {
                "parentMessageId": to_global_id("MessageType", self.parent_message.id),
                "content": "should fail: locked",
            },
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["replyToMessage"]
        self.assertFalse(data["ok"])
        self.assertEqual(data["message"], "This thread is locked")

    def test_mention_parse_failure_does_not_fail_mutation(self):
        with patch(
            "config.graphql.conversation_mutations.parse_mentions_from_content",
            side_effect=ValueError("boom"),
        ):
            result = _execute(
                REPLY_TO_MESSAGE_MUTATION,
                self.user,
                {
                    "parentMessageId": to_global_id(
                        "MessageType", self.parent_message.id
                    ),
                    "content": "content that would normally be parsed",
                },
            )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["replyToMessage"]
        self.assertTrue(data["ok"])
        self.assertEqual(data["message"], "Reply posted successfully")

    def test_agent_mention_triggers_response(self):
        _make_global_agent(self.user)
        with patch(
            "config.graphql.conversation_mutations.trigger_agent_responses_for_message"
        ) as mock_task:
            result = _execute(
                REPLY_TO_MESSAGE_MUTATION,
                self.user,
                {
                    "parentMessageId": to_global_id(
                        "MessageType", self.parent_message.id
                    ),
                    "content": _AGENT_MENTION_CONTENT,
                },
            )
            self.assertIsNone(result.get("errors"))
            self.assertTrue(result["data"]["replyToMessage"]["ok"])
            mock_task.delay.assert_called_once()

    def test_unexpected_error_returns_generic_failure(self):
        with patch(
            "config.graphql.conversation_mutations.set_permissions_for_obj_to_user",
            side_effect=RuntimeError("boom"),
        ):
            result = _execute(
                REPLY_TO_MESSAGE_MUTATION,
                self.user,
                {
                    "parentMessageId": to_global_id(
                        "MessageType", self.parent_message.id
                    ),
                    "content": "hi",
                },
            )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["replyToMessage"]
        self.assertFalse(data["ok"])
        self.assertEqual(data["message"], "Failed to create reply")


class UpdateMessageCoverageTests(TestCase):
    def setUp(self):
        self.corpus_owner = User.objects.create_user(
            username="um_cov_owner", password="pw"
        )
        self.corpus = Corpus.objects.create(
            title="Coverage Corpus", creator=self.corpus_owner, is_public=False
        )
        self.conversation = Conversation.objects.create(
            title="Coverage Thread",
            conversation_type="thread",
            chat_with_corpus=self.corpus,
            creator=self.corpus_owner,
        )
        self.message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="HUMAN",
            content="Original content",
            creator=self.corpus_owner,
        )

    def test_unauthenticated_raises(self):
        result = _execute(
            UPDATE_MESSAGE_MUTATION,
            AnonymousUser(),
            {
                "messageId": to_global_id("MessageType", self.message.id),
                "content": "hi",
            },
        )
        self.assertIsNotNone(result.get("errors"))

    def test_visible_via_thread_context_but_no_crud_grant_denies_edit(self):
        """A collaborator with corpus READ can *see* the message (via
        ``ChatMessageQuerySet.visible_to_user``'s conversation-visible
        branch) but was never granted message-level CRUD and is not a
        moderator — editing must still be denied."""
        viewer = User.objects.create_user(username="um_cov_viewer", password="pw")
        set_permissions_for_obj_to_user(viewer, self.corpus, [PermissionTypes.READ])
        result = _execute(
            UPDATE_MESSAGE_MUTATION,
            viewer,
            {
                "messageId": to_global_id("MessageType", self.message.id),
                "content": "Hijacked content",
            },
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["updateMessage"]
        self.assertFalse(data["ok"])
        self.assertEqual(
            data["message"], "You do not have permission to edit this message"
        )
        self.message.refresh_from_db()
        self.assertEqual(self.message.content, "Original content")

    def test_mention_parse_failure_still_succeeds_with_caveat(self):
        set_permissions_for_obj_to_user(
            self.corpus_owner, self.message, [PermissionTypes.CRUD]
        )
        with patch(
            "config.graphql.conversation_mutations.parse_mentions_from_content",
            side_effect=ValueError("boom"),
        ):
            result = _execute(
                UPDATE_MESSAGE_MUTATION,
                self.corpus_owner,
                {
                    "messageId": to_global_id("MessageType", self.message.id),
                    "content": "Updated content that would normally be parsed",
                },
            )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["updateMessage"]
        self.assertTrue(data["ok"])
        self.assertIn("may not have been recognized", data["message"])
        self.message.refresh_from_db()
        self.assertEqual(
            self.message.content, "Updated content that would normally be parsed"
        )

    def test_mention_link_failure_still_succeeds_with_caveat(self):
        set_permissions_for_obj_to_user(
            self.corpus_owner, self.message, [PermissionTypes.CRUD]
        )
        with patch(
            "config.graphql.conversation_mutations.link_message_to_resources",
            side_effect=ValueError("boom"),
        ):
            result = _execute(
                UPDATE_MESSAGE_MUTATION,
                self.corpus_owner,
                {
                    "messageId": to_global_id("MessageType", self.message.id),
                    "content": _AGENT_MENTION_CONTENT,
                },
            )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["updateMessage"]
        self.assertTrue(data["ok"])
        self.assertIn("may not have been recognized", data["message"])

    def test_malformed_message_id_returns_generic_failure(self):
        set_permissions_for_obj_to_user(
            self.corpus_owner, self.message, [PermissionTypes.CRUD]
        )
        result = _execute(
            UPDATE_MESSAGE_MUTATION,
            self.corpus_owner,
            {
                "messageId": to_global_id("MessageType", _MALFORMED_PK),
                "content": "New content",
            },
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["updateMessage"]
        self.assertFalse(data["ok"])
        self.assertEqual(data["message"], "Failed to update message")


class DeleteConversationCoverageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="dc_cov_user", password="pw")
        self.corpus = Corpus.objects.create(title="Coverage Corpus", creator=self.user)
        self.conversation = Conversation.objects.create(
            title="Coverage Thread",
            conversation_type="thread",
            chat_with_corpus=self.corpus,
            creator=self.user,
        )

    def test_unauthenticated_raises(self):
        result = _execute(
            DELETE_CONVERSATION_MUTATION,
            AnonymousUser(),
            {"conversationId": to_global_id("ConversationType", self.conversation.id)},
        )
        self.assertIsNotNone(result.get("errors"))

    def test_conversation_not_visible_returns_generic_denial(self):
        outsider = User.objects.create_user(username="dc_cov_outsider", password="pw")
        result = _execute(
            DELETE_CONVERSATION_MUTATION,
            outsider,
            {"conversationId": to_global_id("ConversationType", self.conversation.id)},
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["deleteConversation"]
        self.assertFalse(data["ok"])
        self.assertEqual(
            data["message"], "You do not have permission to delete this conversation"
        )

    def test_visible_but_no_delete_grant_denies_deletion(self):
        """A collaborator granted explicit conversation READ (not DELETE,
        and not corpus/document ownership so ``can_moderate`` is False)
        can see the thread but cannot delete it."""
        viewer = User.objects.create_user(username="dc_cov_viewer", password="pw")
        set_permissions_for_obj_to_user(
            viewer, self.conversation, [PermissionTypes.READ]
        )
        result = _execute(
            DELETE_CONVERSATION_MUTATION,
            viewer,
            {"conversationId": to_global_id("ConversationType", self.conversation.id)},
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["deleteConversation"]
        self.assertFalse(data["ok"])
        self.assertEqual(
            data["message"], "You do not have permission to delete this conversation"
        )
        self.conversation.refresh_from_db()
        self.assertIsNone(self.conversation.deleted_at)

    def test_unexpected_error_returns_generic_failure(self):
        with patch(
            "config.graphql.conversation_mutations.BaseService.user_has",
            side_effect=RuntimeError("boom"),
        ):
            result = _execute(
                DELETE_CONVERSATION_MUTATION,
                self.user,
                {
                    "conversationId": to_global_id(
                        "ConversationType", self.conversation.id
                    )
                },
            )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["deleteConversation"]
        self.assertFalse(data["ok"])
        self.assertEqual(data["message"], "Failed to delete conversation")


class DeleteMessageCoverageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="dm_cov_user", password="pw")
        self.corpus = Corpus.objects.create(title="Coverage Corpus", creator=self.user)
        self.conversation = Conversation.objects.create(
            title="Coverage Thread",
            conversation_type="thread",
            chat_with_corpus=self.corpus,
            creator=self.user,
        )
        self.message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="HUMAN",
            content="Coverage message",
            creator=self.user,
        )

    def test_unauthenticated_raises(self):
        result = _execute(
            DELETE_MESSAGE_MUTATION,
            AnonymousUser(),
            {"messageId": to_global_id("MessageType", self.message.id)},
        )
        self.assertIsNotNone(result.get("errors"))

    def test_message_not_visible_returns_generic_denial(self):
        outsider = User.objects.create_user(username="dm_cov_outsider", password="pw")
        result = _execute(
            DELETE_MESSAGE_MUTATION,
            outsider,
            {"messageId": to_global_id("MessageType", self.message.id)},
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["deleteMessage"]
        self.assertFalse(data["ok"])
        self.assertEqual(
            data["message"], "You do not have permission to delete this message"
        )

    def test_visible_but_no_delete_grant_denies_deletion(self):
        viewer = User.objects.create_user(username="dm_cov_viewer", password="pw")
        set_permissions_for_obj_to_user(viewer, self.message, [PermissionTypes.READ])
        result = _execute(
            DELETE_MESSAGE_MUTATION,
            viewer,
            {"messageId": to_global_id("MessageType", self.message.id)},
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["deleteMessage"]
        self.assertFalse(data["ok"])
        self.assertEqual(
            data["message"], "You do not have permission to delete this message"
        )
        self.message.refresh_from_db()
        self.assertIsNone(self.message.deleted_at)

    def test_unexpected_error_returns_generic_failure(self):
        with patch(
            "config.graphql.conversation_mutations.BaseService.user_has",
            side_effect=RuntimeError("boom"),
        ):
            result = _execute(
                DELETE_MESSAGE_MUTATION,
                self.user,
                {"messageId": to_global_id("MessageType", self.message.id)},
            )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["deleteMessage"]
        self.assertFalse(data["ok"])
        self.assertEqual(data["message"], "Failed to delete message")
