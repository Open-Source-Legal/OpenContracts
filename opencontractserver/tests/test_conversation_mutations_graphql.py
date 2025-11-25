"""
Tests for GraphQL conversation/thread mutations.

Tests the GraphQL mutations for creating and managing threads and messages:
- CreateThreadMutation
- CreateThreadMessageMutation
- ReplyToMessageMutation
- DeleteConversationMutation
- DeleteMessageMutation
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from graphene.test import Client

from config.graphql.schema import schema
from opencontractserver.conversations.models import ChatMessage, Conversation
from opencontractserver.corpuses.models import Corpus
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class ConversationMutationsTestCase(TestCase):
    """Test GraphQL mutations for conversations and threads."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="conversation_testuser",
            email="conversation_test@example.com",
            password="testpass123",
        )
        self.other_user = User.objects.create_user(
            username="conversation_otheruser",
            email="conversation_other@example.com",
            password="testpass123",
        )

        # Create a corpus
        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            description="Test corpus for threads",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, self.corpus, [PermissionTypes.CRUD, PermissionTypes.READ]
        )

        # Create GraphQL client
        self.client = Client(schema)

    def _execute_with_user(self, query, user, variables=None):
        """Execute a GraphQL query with a specific user context."""

        # Mock request object with user
        class MockRequest:
            def __init__(self, user):
                self.user = user
                self.META = {}

        context_value = MockRequest(user)
        return self.client.execute(
            query, variables=variables, context_value=context_value
        )

    def test_create_thread_mutation(self):
        """Test creating a new thread."""
        mutation = """
            mutation CreateThread($corpusId: String!, $title: String!, $initialMessage: String!) {
                createThread(corpusId: $corpusId, title: $title, initialMessage: $initialMessage) {
                    ok
                    message
                    obj {
                        id
                        title
                        conversationType
                    }
                }
            }
        """

        # Get corpus global ID
        from graphql_relay import to_global_id

        corpus_id = to_global_id("CorpusType", self.corpus.id)

        variables = {
            "corpusId": corpus_id,
            "title": "Test Thread",
            "initialMessage": "This is the first message",
        }

        result = self._execute_with_user(mutation, self.user, variables)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["createThread"]
        self.assertTrue(data["ok"])
        self.assertEqual(data["message"], "Thread created successfully")
        self.assertIsNotNone(data["obj"])
        self.assertEqual(data["obj"]["title"], "Test Thread")
        self.assertEqual(data["obj"]["conversationType"], "THREAD")

        # Verify conversation was created in database
        conversation = Conversation.objects.get(title="Test Thread")
        self.assertEqual(conversation.conversation_type, "thread")
        self.assertEqual(conversation.creator, self.user)
        self.assertEqual(conversation.chat_with_corpus, self.corpus)

        # Verify initial message was created
        messages = ChatMessage.objects.filter(conversation=conversation)
        self.assertEqual(messages.count(), 1)
        self.assertEqual(messages.first().content, "This is the first message")

    def test_create_thread_without_permission(self):
        """Test creating a thread without corpus permission."""
        mutation = """
            mutation CreateThread($corpusId: String!, $title: String!, $initialMessage: String!) {
                createThread(corpusId: $corpusId, title: $title, initialMessage: $initialMessage) {
                    ok
                    message
                    obj {
                        id
                    }
                }
            }
        """

        from graphql_relay import to_global_id

        corpus_id = to_global_id("CorpusType", self.corpus.id)

        variables = {
            "corpusId": corpus_id,
            "title": "Unauthorized Thread",
            "initialMessage": "Should fail",
        }

        result = self._execute_with_user(mutation, self.other_user, variables)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["createThread"]
        self.assertFalse(data["ok"])
        self.assertIn("permission", data["message"].lower())

    def test_create_thread_message_mutation(self):
        """Test posting a message to a thread."""
        # Create a thread first
        conversation = Conversation.objects.create(
            title="Test Thread",
            conversation_type="thread",
            chat_with_corpus=self.corpus,
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, conversation, [PermissionTypes.CRUD, PermissionTypes.READ]
        )

        mutation = """
            mutation CreateThreadMessage($conversationId: String!, $content: String!) {
                createThreadMessage(conversationId: $conversationId, content: $content) {
                    ok
                    message
                    obj {
                        id
                        content
                        msgType
                    }
                }
            }
        """

        from graphql_relay import to_global_id

        conversation_id = to_global_id("ConversationType", conversation.id)

        variables = {
            "conversationId": conversation_id,
            "content": "This is a new message",
        }

        result = self._execute_with_user(mutation, self.user, variables)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["createThreadMessage"]
        self.assertTrue(data["ok"])
        self.assertEqual(data["message"], "Message posted successfully")
        self.assertEqual(data["obj"]["content"], "This is a new message")
        self.assertEqual(data["obj"]["msgType"], "HUMAN")

        # Verify message was created in database
        message = ChatMessage.objects.get(content="This is a new message")
        self.assertEqual(message.conversation, conversation)
        self.assertEqual(message.creator, self.user)

    def test_create_message_in_locked_thread(self):
        """Test posting a message to a locked thread (should fail)."""
        conversation = Conversation.objects.create(
            title="Locked Thread",
            conversation_type="thread",
            chat_with_corpus=self.corpus,
            creator=self.user,
            is_locked=True,
        )
        set_permissions_for_obj_to_user(
            self.user, conversation, [PermissionTypes.CRUD, PermissionTypes.READ]
        )

        mutation = """
            mutation CreateThreadMessage($conversationId: String!, $content: String!) {
                createThreadMessage(conversationId: $conversationId, content: $content) {
                    ok
                    message
                }
            }
        """

        from graphql_relay import to_global_id

        conversation_id = to_global_id("ConversationType", conversation.id)

        variables = {
            "conversationId": conversation_id,
            "content": "Should fail",
        }

        result = self._execute_with_user(mutation, self.user, variables)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["createThreadMessage"]
        self.assertFalse(data["ok"])
        self.assertIn("locked", data["message"].lower())

    def test_reply_to_message_mutation(self):
        """Test creating a nested reply to a message."""
        # Create conversation and parent message
        conversation = Conversation.objects.create(
            title="Test Thread",
            conversation_type="thread",
            chat_with_corpus=self.corpus,
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, conversation, [PermissionTypes.CRUD, PermissionTypes.READ]
        )

        parent_message = ChatMessage.objects.create(
            conversation=conversation,
            msg_type="HUMAN",
            content="Parent message",
            creator=self.user,
        )

        mutation = """
            mutation ReplyToMessage($parentMessageId: String!, $content: String!) {
                replyToMessage(parentMessageId: $parentMessageId, content: $content) {
                    ok
                    message
                    obj {
                        id
                        content
                        parentMessage {
                            id
                            content
                        }
                    }
                }
            }
        """

        from graphql_relay import to_global_id

        parent_id = to_global_id("MessageType", parent_message.id)

        variables = {
            "parentMessageId": parent_id,
            "content": "This is a reply",
        }

        result = self._execute_with_user(mutation, self.user, variables)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["replyToMessage"]
        self.assertTrue(data["ok"])
        self.assertEqual(data["message"], "Reply posted successfully")
        self.assertEqual(data["obj"]["content"], "This is a reply")
        self.assertEqual(data["obj"]["parentMessage"]["content"], "Parent message")

        # Verify reply was created in database
        reply = ChatMessage.objects.get(content="This is a reply")
        self.assertEqual(reply.parent_message, parent_message)
        self.assertEqual(reply.conversation, conversation)

    def test_delete_conversation_mutation(self):
        """Test soft deleting a conversation."""
        conversation = Conversation.objects.create(
            title="Thread to Delete",
            conversation_type="thread",
            chat_with_corpus=self.corpus,
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, conversation, [PermissionTypes.CRUD, PermissionTypes.DELETE]
        )

        mutation = """
            mutation DeleteConversation($conversationId: String!) {
                deleteConversation(conversationId: $conversationId) {
                    ok
                    message
                }
            }
        """

        from graphql_relay import to_global_id

        conversation_id = to_global_id("ConversationType", conversation.id)

        variables = {"conversationId": conversation_id}

        result = self._execute_with_user(mutation, self.user, variables)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["deleteConversation"]
        self.assertTrue(data["ok"])
        self.assertEqual(data["message"], "Conversation deleted successfully")

        # Verify conversation was soft deleted
        conversation.refresh_from_db()
        self.assertIsNotNone(conversation.deleted_at)

    def test_delete_message_mutation(self):
        """Test soft deleting a message."""
        conversation = Conversation.objects.create(
            title="Test Thread",
            conversation_type="thread",
            chat_with_corpus=self.corpus,
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, conversation, [PermissionTypes.CRUD, PermissionTypes.READ]
        )

        message = ChatMessage.objects.create(
            conversation=conversation,
            msg_type="HUMAN",
            content="Message to delete",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, message, [PermissionTypes.CRUD, PermissionTypes.DELETE]
        )

        mutation = """
            mutation DeleteMessage($messageId: String!) {
                deleteMessage(messageId: $messageId) {
                    ok
                    message
                }
            }
        """

        from graphql_relay import to_global_id

        message_id = to_global_id("MessageType", message.id)

        variables = {"messageId": message_id}

        result = self._execute_with_user(mutation, self.user, variables)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["deleteMessage"]
        self.assertTrue(data["ok"])
        self.assertEqual(data["message"], "Message deleted successfully")

        # Verify message was soft deleted
        message.refresh_from_db()
        self.assertIsNotNone(message.deleted_at)

    def test_nested_replies(self):
        """Test creating multiple levels of nested replies."""
        # Create conversation
        conversation = Conversation.objects.create(
            title="Nested Thread",
            conversation_type="thread",
            chat_with_corpus=self.corpus,
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, conversation, [PermissionTypes.CRUD, PermissionTypes.READ]
        )

        # Create parent message
        parent = ChatMessage.objects.create(
            conversation=conversation,
            msg_type="HUMAN",
            content="Level 0",
            creator=self.user,
        )

        # Create first level reply
        reply1 = ChatMessage.objects.create(
            conversation=conversation,
            parent_message=parent,
            msg_type="HUMAN",
            content="Level 1",
            creator=self.user,
        )

        # Create second level reply
        reply2 = ChatMessage.objects.create(
            conversation=conversation,
            parent_message=reply1,
            msg_type="HUMAN",
            content="Level 2",
            creator=self.user,
        )

        # Verify relationships
        self.assertEqual(reply1.parent_message, parent)
        self.assertEqual(reply2.parent_message, reply1)
        self.assertEqual(parent.replies.count(), 1)
        self.assertEqual(reply1.replies.count(), 1)
        self.assertEqual(reply2.replies.count(), 0)
