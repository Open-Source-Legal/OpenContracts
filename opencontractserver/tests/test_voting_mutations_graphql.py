"""
Tests for GraphQL voting mutations.

Tests the GraphQL mutations for voting on messages:
- VoteMessageMutation
- RemoveVoteMutation
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from graphene.test import Client

from config.graphql.schema import schema
from opencontractserver.conversations.models import (
    ChatMessage,
    Conversation,
    MessageVote,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class VotingMutationsTestCase(TestCase):
    """Test GraphQL mutations for voting on messages."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
        )
        self.other_user = User.objects.create_user(
            username="otheruser",
            email="other@example.com",
            password="testpass123",
        )

        # Create a corpus
        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            description="Test corpus for voting",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, self.corpus, [PermissionTypes.CRUD, PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.other_user, self.corpus, [PermissionTypes.READ]
        )

        # Create a conversation
        self.conversation = Conversation.objects.create(
            title="Test Thread",
            conversation_type="thread",
            chat_with_corpus=self.corpus,
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, self.conversation, [PermissionTypes.CRUD, PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.other_user, self.conversation, [PermissionTypes.READ]
        )

        # Create a message by user (other_user will vote on it)
        self.message = ChatMessage.objects.create(
            conversation=self.conversation,
            msg_type="HUMAN",
            content="Test message",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(self.user, self.message, [PermissionTypes.CRUD])

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

    def test_vote_message_upvote(self):
        """Test upvoting a message."""
        mutation = """
            mutation VoteMessage($messageId: String!, $voteType: String!) {
                voteMessage(messageId: $messageId, voteType: $voteType) {
                    ok
                    message
                    obj {
                        id
                        upvoteCount
                        downvoteCount
                    }
                }
            }
        """

        from graphql_relay import to_global_id

        message_id = to_global_id("MessageType", self.message.id)

        variables = {"messageId": message_id, "voteType": "upvote"}

        result = self._execute_with_user(mutation, self.other_user, variables)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["voteMessage"]
        self.assertTrue(data["ok"])
        self.assertIn("added successfully", data["message"])

        # Verify vote was created in database
        vote = MessageVote.objects.get(message=self.message, creator=self.other_user)
        self.assertEqual(vote.vote_type, "upvote")

        # Verify vote count was updated
        self.message.refresh_from_db()
        self.assertEqual(self.message.upvote_count, 1)
        self.assertEqual(self.message.downvote_count, 0)

    def test_vote_message_downvote(self):
        """Test downvoting a message."""
        mutation = """
            mutation VoteMessage($messageId: String!, $voteType: String!) {
                voteMessage(messageId: $messageId, voteType: $voteType) {
                    ok
                    message
                    obj {
                        id
                        upvoteCount
                        downvoteCount
                    }
                }
            }
        """

        from graphql_relay import to_global_id

        message_id = to_global_id("MessageType", self.message.id)

        variables = {"messageId": message_id, "voteType": "downvote"}

        result = self._execute_with_user(mutation, self.other_user, variables)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["voteMessage"]
        self.assertTrue(data["ok"])

        # Verify vote was created in database
        vote = MessageVote.objects.get(message=self.message, creator=self.other_user)
        self.assertEqual(vote.vote_type, "downvote")

        # Verify vote count was updated
        self.message.refresh_from_db()
        self.assertEqual(self.message.upvote_count, 0)
        self.assertEqual(self.message.downvote_count, 1)

    def test_vote_message_change_vote(self):
        """Test changing vote from upvote to downvote."""
        # First create an upvote
        MessageVote.objects.create(
            message=self.message, vote_type="upvote", creator=self.other_user
        )
        self.message.upvote_count = 1
        self.message.save()

        mutation = """
            mutation VoteMessage($messageId: String!, $voteType: String!) {
                voteMessage(messageId: $messageId, voteType: $voteType) {
                    ok
                    message
                }
            }
        """

        from graphql_relay import to_global_id

        message_id = to_global_id("MessageType", self.message.id)

        variables = {"messageId": message_id, "voteType": "downvote"}

        result = self._execute_with_user(mutation, self.other_user, variables)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["voteMessage"]
        self.assertTrue(data["ok"])
        self.assertIn("updated", data["message"])

        # Verify vote was updated
        vote = MessageVote.objects.get(message=self.message, creator=self.other_user)
        self.assertEqual(vote.vote_type, "downvote")

    def test_vote_own_message_fails(self):
        """Test that users cannot vote on their own messages."""
        mutation = """
            mutation VoteMessage($messageId: String!, $voteType: String!) {
                voteMessage(messageId: $messageId, voteType: $voteType) {
                    ok
                    message
                }
            }
        """

        from graphql_relay import to_global_id

        message_id = to_global_id("MessageType", self.message.id)

        variables = {"messageId": message_id, "voteType": "upvote"}

        # User tries to vote on their own message
        result = self._execute_with_user(mutation, self.user, variables)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["voteMessage"]
        self.assertFalse(data["ok"])
        self.assertIn("cannot vote on your own", data["message"].lower())

        # Verify no vote was created
        self.assertFalse(
            MessageVote.objects.filter(message=self.message, creator=self.user).exists()
        )

    def test_vote_invalid_vote_type(self):
        """Test voting with invalid vote type."""
        mutation = """
            mutation VoteMessage($messageId: String!, $voteType: String!) {
                voteMessage(messageId: $messageId, voteType: $voteType) {
                    ok
                    message
                }
            }
        """

        from graphql_relay import to_global_id

        message_id = to_global_id("MessageType", self.message.id)

        variables = {"messageId": message_id, "voteType": "invalid"}

        result = self._execute_with_user(mutation, self.other_user, variables)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["voteMessage"]
        self.assertFalse(data["ok"])
        self.assertIn("invalid", data["message"].lower())

    def test_vote_without_permission(self):
        """Test voting on a message without conversation access."""
        # Create a third user without permissions
        unauthorized_user = User.objects.create_user(
            username="unauthorized", email="unauth@example.com", password="pass123"
        )

        mutation = """
            mutation VoteMessage($messageId: String!, $voteType: String!) {
                voteMessage(messageId: $messageId, voteType: $voteType) {
                    ok
                    message
                }
            }
        """

        from graphql_relay import to_global_id

        message_id = to_global_id("MessageType", self.message.id)

        variables = {"messageId": message_id, "voteType": "upvote"}

        result = self._execute_with_user(mutation, unauthorized_user, variables)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["voteMessage"]
        self.assertFalse(data["ok"])
        self.assertIn("permission", data["message"].lower())

    def test_remove_vote(self):
        """Test removing a vote from a message."""
        # Create a vote first
        MessageVote.objects.create(
            message=self.message, vote_type="upvote", creator=self.other_user
        )
        self.message.upvote_count = 1
        self.message.save()

        mutation = """
            mutation RemoveVote($messageId: String!) {
                removeVote(messageId: $messageId) {
                    ok
                    message
                    obj {
                        id
                        upvoteCount
                        downvoteCount
                    }
                }
            }
        """

        from graphql_relay import to_global_id

        message_id = to_global_id("MessageType", self.message.id)

        variables = {"messageId": message_id}

        result = self._execute_with_user(mutation, self.other_user, variables)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["removeVote"]
        self.assertTrue(data["ok"])
        self.assertIn("removed successfully", data["message"])

        # Verify vote was deleted
        self.assertFalse(
            MessageVote.objects.filter(
                message=self.message, creator=self.other_user
            ).exists()
        )

    def test_remove_nonexistent_vote(self):
        """Test removing a vote that doesn't exist."""
        mutation = """
            mutation RemoveVote($messageId: String!) {
                removeVote(messageId: $messageId) {
                    ok
                    message
                }
            }
        """

        from graphql_relay import to_global_id

        message_id = to_global_id("MessageType", self.message.id)

        variables = {"messageId": message_id}

        result = self._execute_with_user(mutation, self.other_user, variables)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["removeVote"]
        self.assertTrue(data["ok"])
        self.assertIn("no vote found", data["message"].lower())

    def test_vote_message_not_found(self):
        """Test voting on a non-existent message."""
        mutation = """
            mutation VoteMessage($messageId: String!, $voteType: String!) {
                voteMessage(messageId: $messageId, voteType: $voteType) {
                    ok
                    message
                }
            }
        """

        from graphql_relay import to_global_id

        # Use a non-existent message ID
        message_id = to_global_id("MessageType", 99999)

        variables = {"messageId": message_id, "voteType": "upvote"}

        result = self._execute_with_user(mutation, self.other_user, variables)

        self.assertIsNone(result.get("errors"))
        data = result["data"]["voteMessage"]
        self.assertFalse(data["ok"])
        self.assertIn("not found", data["message"].lower())

    def test_multiple_users_voting(self):
        """Test multiple users voting on the same message."""
        # Create another user
        user3 = User.objects.create_user(
            username="user3", email="user3@example.com", password="pass123"
        )
        set_permissions_for_obj_to_user(user3, self.corpus, [PermissionTypes.READ])
        set_permissions_for_obj_to_user(
            user3, self.conversation, [PermissionTypes.READ]
        )

        # User 2 upvotes
        MessageVote.objects.create(
            message=self.message, vote_type="upvote", creator=self.other_user
        )

        # User 3 downvotes
        MessageVote.objects.create(
            message=self.message, vote_type="downvote", creator=user3
        )

        # Verify both votes exist
        votes = MessageVote.objects.filter(message=self.message)
        self.assertEqual(votes.count(), 2)
        self.assertEqual(votes.filter(vote_type="upvote").count(), 1)
        self.assertEqual(votes.filter(vote_type="downvote").count(), 1)
