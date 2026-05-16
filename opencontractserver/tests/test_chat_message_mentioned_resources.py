"""GraphQL resolver tests for ``MessageType.mentioned_resources`` — agent branch.

These tests focus on the new ``agent`` mention type wired up in Task 3 of the
rich-mention agent delegation feature. They exercise the GraphQL resolver
(``chatMessage`` -> ``mentionedResources``) end-to-end so we can be confident
that ``resolve_mentions_for_user`` correctly resolves agent URLs and honors
visibility rules.

Note: The Django/Graphene type ``MessageType`` is what the plan calls
``ChatMessageType`` — it's the only GraphQL type that wraps the
``ChatMessage`` model. There is no separate type.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from graphene.test import Client as GrapheneClient
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.agents.models import AgentConfiguration
from opencontractserver.conversations.models import ChatMessage, Conversation
from opencontractserver.corpuses.models import Corpus
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


CHAT_MESSAGE_MENTIONS_QUERY = """
    query GetMessage($id: ID!) {
        chatMessage(id: $id) {
            id
            content
            mentionedResources {
                type
                slug
                title
                url
            }
        }
    }
"""


class ChatMessageAgentMentionResolverTests(TestCase):
    """Tests for resolving ``type="agent"`` mentions on chat messages."""

    def setUp(self):
        self.user1 = User.objects.create_user(
            username="alice",
            password="test",
            email="alice@example.com",
            slug="alice",
        )
        self.user2 = User.objects.create_user(
            username="bob",
            password="test",
            email="bob@example.com",
            slug="bob",
        )

        # A globally visible, active, public agent.
        self.global_agent = AgentConfiguration.objects.create(
            name="Research Bot",
            slug="research-bot",
            description="Reads stuff",
            scope="GLOBAL",
            system_instructions="You are a helpful research bot.",
            is_active=True,
            is_public=True,
            creator=self.user1,
        )

        # A globally registered but **inactive** agent — should be omitted.
        self.inactive_agent = AgentConfiguration.objects.create(
            name="Inactive Bot",
            slug="inactive-bot",
            description="Disabled",
            scope="GLOBAL",
            system_instructions="N/A",
            is_active=False,
            is_public=True,
            creator=self.user1,
        )

        # Two corpora: one user1 can see, one private to user2.
        self.public_corpus = Corpus.objects.create(
            title="Open Corpus",
            description="Open to user1",
            creator=self.user1,
            slug="open-corpus",
            is_public=False,
        )
        set_permissions_for_obj_to_user(
            self.user1,
            self.public_corpus,
            [PermissionTypes.READ, PermissionTypes.UPDATE],
        )

        self.private_corpus = Corpus.objects.create(
            title="Locked Corpus",
            description="user2 only",
            creator=self.user2,
            slug="locked-corpus",
            is_public=False,
        )
        set_permissions_for_obj_to_user(
            self.user2,
            self.private_corpus,
            [PermissionTypes.READ, PermissionTypes.UPDATE],
        )

        # Corpus-scoped agent inside the corpus user1 can see.
        self.corpus_agent = AgentConfiguration.objects.create(
            name="Corpus Expert",
            slug="corpus-expert",
            description="Expert in the open corpus",
            scope="CORPUS",
            corpus=self.public_corpus,
            system_instructions="You are an expert.",
            is_active=True,
            is_public=True,
            creator=self.user1,
        )

        # Corpus-scoped agent inside the corpus user1 CANNOT see.
        self.locked_corpus_agent = AgentConfiguration.objects.create(
            name="Locked Expert",
            slug="locked-expert",
            description="Hidden agent",
            scope="CORPUS",
            corpus=self.private_corpus,
            system_instructions="Secret.",
            is_active=True,
            is_public=True,
            creator=self.user2,
        )

        self.conversation = Conversation.objects.create(
            title="Test Thread",
            creator=self.user1,
            conversation_type="THREAD",
        )

        self.client = GrapheneClient(schema)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _execute(self, message: ChatMessage, user):
        """Execute the chatMessage mentions query for ``user``."""
        # graphene.test.Client exposes ``execute`` at runtime but the typing
        # stubs do not declare it; matches the pattern in test_mentions.py.
        return self.client.execute(  # type: ignore[attr-defined]
            CHAT_MESSAGE_MENTIONS_QUERY,
            variables={"id": to_global_id("MessageType", message.id)},
            context_value=type("Request", (), {"user": user})(),
        )

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def test_global_agent_mention_resolves(self):
        """Markdown link to /agents/{slug} should resolve into a single agent mention."""
        message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="HUMAN",
            creator=self.user1,
            content="Ping [@research-bot](/agents/research-bot) please.",
        )

        result = self._execute(message, self.user1)

        self.assertIsNone(result.get("errors"))
        mentions = result["data"]["chatMessage"]["mentionedResources"]
        self.assertEqual(len(mentions), 1)
        self.assertEqual(mentions[0]["type"], "agent")
        self.assertEqual(mentions[0]["slug"], "research-bot")
        self.assertEqual(mentions[0]["title"], "Research Bot")
        self.assertEqual(mentions[0]["url"], "/agents/research-bot")

    def test_inactive_agent_mention_is_omitted(self):
        """Active=False agents are not visible_to_user and must be dropped."""
        message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="HUMAN",
            creator=self.user1,
            content="Ping [@inactive-bot](/agents/inactive-bot)",
        )

        result = self._execute(message, self.user1)

        self.assertIsNone(result.get("errors"))
        mentions = result["data"]["chatMessage"]["mentionedResources"]
        self.assertEqual(mentions, [])

    def test_corpus_scoped_agent_resolves_with_visible_corpus(self):
        """Corpus-scoped agent whose corpus is visible should resolve."""
        message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="HUMAN",
            creator=self.user1,
            content=(
                "Ask "
                "[@corpus-expert](/c/alice/open-corpus/agents/corpus-expert) "
                "please."
            ),
        )

        result = self._execute(message, self.user1)

        self.assertIsNone(result.get("errors"))
        mentions = result["data"]["chatMessage"]["mentionedResources"]
        self.assertEqual(len(mentions), 1)
        self.assertEqual(mentions[0]["type"], "agent")
        self.assertEqual(mentions[0]["slug"], "corpus-expert")
        self.assertEqual(mentions[0]["title"], "Corpus Expert")
        # URL preserved from original markdown link.
        self.assertEqual(
            mentions[0]["url"],
            "/c/alice/open-corpus/agents/corpus-expert",
        )

    def test_corpus_scoped_agent_with_inaccessible_corpus_is_omitted(self):
        """If the corpus isn't visible to the user, the agent must be hidden."""
        message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="HUMAN",
            creator=self.user1,
            content=(
                "Ping " "[@locked-expert](/c/bob/locked-corpus/agents/locked-expert)"
            ),
        )

        result = self._execute(message, self.user1)

        self.assertIsNone(result.get("errors"))
        mentions = result["data"]["chatMessage"]["mentionedResources"]
        self.assertEqual(mentions, [])

    def test_corpus_scoped_agent_mention_with_mismatched_corpus_slug_is_omitted(self):
        """If the URL points to a corpus that doesn't host this agent, drop it."""
        message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="HUMAN",
            creator=self.user1,
            # research-bot is a GLOBAL agent — putting it under a
            # corpus-scoped URL must NOT resolve.
            content=(
                "Ping " "[@research-bot](/c/alice/open-corpus/agents/research-bot)"
            ),
        )

        result = self._execute(message, self.user1)

        self.assertIsNone(result.get("errors"))
        mentions = result["data"]["chatMessage"]["mentionedResources"]
        self.assertEqual(mentions, [])

    def test_unknown_agent_slug_is_silently_omitted(self):
        """Mention of an agent that doesn't exist must not leak existence."""
        message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="HUMAN",
            creator=self.user1,
            content="Ping [@ghost-bot](/agents/ghost-bot)",
        )

        result = self._execute(message, self.user1)

        self.assertIsNone(result.get("errors"))
        mentions = result["data"]["chatMessage"]["mentionedResources"]
        self.assertEqual(mentions, [])
