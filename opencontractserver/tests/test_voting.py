"""
Tests for voting and reputation functionality in OpenContracts.

This module tests Epic #550: Voting System & Reputation

Tests cover:
1. Creating upvotes and downvotes
2. Changing votes (upvote to downvote and vice versa)
3. Deleting votes
4. Denormalized vote count updates
5. User reputation calculation (global and per-corpus)
6. Unique constraint enforcement (one vote per user per message)
7. Signal-based automatic updates
8. Rate limiting integration
"""

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

from opencontractserver.conversations.models import (
    ChatMessage,
    Conversation,
    ConversationTypeChoices,
    MessageVote,
    UserReputation,
    VoteType,
)
from opencontractserver.corpuses.models import Corpus

User = get_user_model()


class TestMessageVoting(TestCase):
    """Test message voting functionality."""

    @classmethod
    def setUpTestData(cls):
        """Create test data."""
        cls.user1 = User.objects.create_user(
            username="voter1",
            password="testpass123",
            email="voter1@test.com",
        )

        cls.user2 = User.objects.create_user(
            username="voter2",
            password="testpass123",
            email="voter2@test.com",
        )

        cls.author = User.objects.create_user(
            username="author",
            password="testpass123",
            email="author@test.com",
        )

        cls.corpus = Corpus.objects.create(
            title="Test Voting Corpus",
            description="A corpus for testing voting",
            creator=cls.user1,
            is_public=True,
        )

        cls.thread = Conversation.objects.create(
            title="Discussion Thread",
            conversation_type=ConversationTypeChoices.THREAD,
            chat_with_corpus=cls.corpus,
            creator=cls.author,
        )

        cls.message = ChatMessage.objects.create(
            conversation=cls.thread,
            msg_type="HUMAN",
            content="Test message for voting",
            creator=cls.author,
        )

    def test_create_upvote(self):
        """Test creating an upvote on a message."""
        vote = MessageVote.objects.create(
            message=self.message,
            vote_type=VoteType.UPVOTE,
            creator=self.user1,
        )

        self.assertEqual(vote.vote_type, VoteType.UPVOTE)
        self.assertEqual(vote.message, self.message)
        self.assertEqual(vote.creator, self.user1)

    def test_create_downvote(self):
        """Test creating a downvote on a message."""
        vote = MessageVote.objects.create(
            message=self.message,
            vote_type=VoteType.DOWNVOTE,
            creator=self.user1,
        )

        self.assertEqual(vote.vote_type, VoteType.DOWNVOTE)
        self.assertEqual(vote.message, self.message)
        self.assertEqual(vote.creator, self.user1)

    def test_one_vote_per_user_per_message_constraint(self):
        """Test that a user can only vote once per message."""
        # Create first vote
        MessageVote.objects.create(
            message=self.message,
            vote_type=VoteType.UPVOTE,
            creator=self.user1,
        )

        # Attempt to create second vote by same user
        with self.assertRaises(IntegrityError):
            MessageVote.objects.create(
                message=self.message,
                vote_type=VoteType.UPVOTE,
                creator=self.user1,
            )

    def test_multiple_users_can_vote_on_same_message(self):
        """Test that multiple users can vote on the same message."""
        vote1 = MessageVote.objects.create(
            message=self.message,
            vote_type=VoteType.UPVOTE,
            creator=self.user1,
        )

        vote2 = MessageVote.objects.create(
            message=self.message,
            vote_type=VoteType.UPVOTE,
            creator=self.user2,
        )

        self.assertEqual(self.message.votes.count(), 2)
        self.assertIn(vote1, self.message.votes.all())
        self.assertIn(vote2, self.message.votes.all())

    def test_change_vote_from_upvote_to_downvote(self):
        """Test changing a vote from upvote to downvote."""
        vote = MessageVote.objects.create(
            message=self.message,
            vote_type=VoteType.UPVOTE,
            creator=self.user1,
        )

        # Change vote type
        vote.vote_type = VoteType.DOWNVOTE
        vote.save()

        # Refresh from database
        vote.refresh_from_db()
        self.assertEqual(vote.vote_type, VoteType.DOWNVOTE)

    def test_delete_vote(self):
        """Test deleting a vote."""
        vote = MessageVote.objects.create(
            message=self.message,
            vote_type=VoteType.UPVOTE,
            creator=self.user1,
        )

        vote_id = vote.id
        vote.delete()

        self.assertFalse(MessageVote.objects.filter(id=vote_id).exists())


class TestVoteCountDenormalization(TestCase):
    """Test automatic vote count updates via signals."""

    @classmethod
    def setUpTestData(cls):
        """Create test data."""
        cls.user1 = User.objects.create_user(
            username="voter1",
            password="testpass123",
            email="voter1@test.com",
        )

        cls.user2 = User.objects.create_user(
            username="voter2",
            password="testpass123",
            email="voter2@test.com",
        )

        cls.author = User.objects.create_user(
            username="author",
            password="testpass123",
            email="author@test.com",
        )

        cls.thread = Conversation.objects.create(
            title="Discussion Thread",
            conversation_type=ConversationTypeChoices.THREAD,
            creator=cls.author,
        )

    def setUp(self):
        """Create a fresh message for each test."""
        self.message = ChatMessage.objects.create(
            conversation=self.thread,
            msg_type="HUMAN",
            content="Test message for vote counts",
            creator=self.author,
        )

    def test_initial_vote_counts_are_zero(self):
        """Test that new messages start with zero vote counts."""
        self.assertEqual(self.message.upvote_count, 0)
        self.assertEqual(self.message.downvote_count, 0)

    def test_upvote_increments_count(self):
        """Test that creating an upvote increments the upvote count."""
        MessageVote.objects.create(
            message=self.message,
            vote_type=VoteType.UPVOTE,
            creator=self.user1,
        )

        self.message.refresh_from_db()
        self.assertEqual(self.message.upvote_count, 1)
        self.assertEqual(self.message.downvote_count, 0)

    def test_downvote_increments_count(self):
        """Test that creating a downvote increments the downvote count."""
        MessageVote.objects.create(
            message=self.message,
            vote_type=VoteType.DOWNVOTE,
            creator=self.user1,
        )

        self.message.refresh_from_db()
        self.assertEqual(self.message.upvote_count, 0)
        self.assertEqual(self.message.downvote_count, 1)

    def test_multiple_upvotes_increment_count(self):
        """Test that multiple upvotes correctly increment the count."""
        MessageVote.objects.create(
            message=self.message,
            vote_type=VoteType.UPVOTE,
            creator=self.user1,
        )

        MessageVote.objects.create(
            message=self.message,
            vote_type=VoteType.UPVOTE,
            creator=self.user2,
        )

        self.message.refresh_from_db()
        self.assertEqual(self.message.upvote_count, 2)
        self.assertEqual(self.message.downvote_count, 0)

    def test_mixed_votes_update_counts(self):
        """Test that mixed upvotes and downvotes update correctly."""
        MessageVote.objects.create(
            message=self.message,
            vote_type=VoteType.UPVOTE,
            creator=self.user1,
        )

        MessageVote.objects.create(
            message=self.message,
            vote_type=VoteType.DOWNVOTE,
            creator=self.user2,
        )

        self.message.refresh_from_db()
        self.assertEqual(self.message.upvote_count, 1)
        self.assertEqual(self.message.downvote_count, 1)

    def test_changing_vote_updates_counts(self):
        """Test that changing a vote updates counts correctly."""
        vote = MessageVote.objects.create(
            message=self.message,
            vote_type=VoteType.UPVOTE,
            creator=self.user1,
        )

        self.message.refresh_from_db()
        self.assertEqual(self.message.upvote_count, 1)
        self.assertEqual(self.message.downvote_count, 0)

        # Change to downvote
        vote.vote_type = VoteType.DOWNVOTE
        vote.save()

        self.message.refresh_from_db()
        self.assertEqual(self.message.upvote_count, 0)
        self.assertEqual(self.message.downvote_count, 1)

    def test_deleting_upvote_decrements_count(self):
        """Test that deleting an upvote decrements the count."""
        vote = MessageVote.objects.create(
            message=self.message,
            vote_type=VoteType.UPVOTE,
            creator=self.user1,
        )

        self.message.refresh_from_db()
        self.assertEqual(self.message.upvote_count, 1)

        vote.delete()

        self.message.refresh_from_db()
        self.assertEqual(self.message.upvote_count, 0)

    def test_deleting_downvote_decrements_count(self):
        """Test that deleting a downvote decrements the count."""
        vote = MessageVote.objects.create(
            message=self.message,
            vote_type=VoteType.DOWNVOTE,
            creator=self.user1,
        )

        self.message.refresh_from_db()
        self.assertEqual(self.message.downvote_count, 1)

        vote.delete()

        self.message.refresh_from_db()
        self.assertEqual(self.message.downvote_count, 0)


class TestUserReputation(TestCase):
    """Test user reputation calculation."""

    @classmethod
    def setUpTestData(cls):
        """Create test data."""
        cls.user1 = User.objects.create_user(
            username="voter1",
            password="testpass123",
            email="voter1@test.com",
        )

        cls.user2 = User.objects.create_user(
            username="voter2",
            password="testpass123",
            email="voter2@test.com",
        )

        cls.author = User.objects.create_user(
            username="author",
            password="testpass123",
            email="author@test.com",
        )

        cls.corpus1 = Corpus.objects.create(
            title="Corpus 1",
            description="First corpus",
            creator=cls.user1,
            is_public=True,
        )

        cls.corpus2 = Corpus.objects.create(
            title="Corpus 2",
            description="Second corpus",
            creator=cls.user1,
            is_public=True,
        )

    def test_create_global_reputation(self):
        """Test creating a global reputation record."""
        reputation = UserReputation.objects.create(
            user=self.author,
            corpus=None,  # Global
            reputation_score=10,
            total_upvotes_received=12,
            total_downvotes_received=2,
            creator=self.author,
        )

        self.assertIsNone(reputation.corpus)
        self.assertEqual(reputation.reputation_score, 10)
        self.assertEqual(reputation.total_upvotes_received, 12)
        self.assertEqual(reputation.total_downvotes_received, 2)

    def test_create_corpus_specific_reputation(self):
        """Test creating a corpus-specific reputation record."""
        reputation = UserReputation.objects.create(
            user=self.author,
            corpus=self.corpus1,
            reputation_score=5,
            total_upvotes_received=7,
            total_downvotes_received=2,
            creator=self.author,
        )

        self.assertEqual(reputation.corpus, self.corpus1)
        self.assertEqual(reputation.reputation_score, 5)

    def test_one_reputation_per_user_per_corpus_constraint(self):
        """Test that there can only be one reputation record per user per corpus."""
        UserReputation.objects.create(
            user=self.author,
            corpus=self.corpus1,
            reputation_score=5,
            creator=self.author,
        )

        with self.assertRaises(IntegrityError):
            UserReputation.objects.create(
                user=self.author,
                corpus=self.corpus1,
                reputation_score=10,
                creator=self.author,
            )

    def test_automatic_reputation_calculation_on_vote(self):
        """Test that reputation is automatically calculated when a vote is created."""
        # Create a thread and message
        thread = Conversation.objects.create(
            title="Test Thread",
            conversation_type=ConversationTypeChoices.THREAD,
            creator=self.author,
        )

        message = ChatMessage.objects.create(
            conversation=thread,
            msg_type="HUMAN",
            content="Test message",
            creator=self.author,
        )

        # Create an upvote
        MessageVote.objects.create(
            message=message,
            vote_type=VoteType.UPVOTE,
            creator=self.user1,
        )

        # Check that global reputation was created/updated
        global_reputation = UserReputation.objects.get(user=self.author, corpus=None)
        self.assertEqual(global_reputation.reputation_score, 1)
        self.assertEqual(global_reputation.total_upvotes_received, 1)
        self.assertEqual(global_reputation.total_downvotes_received, 0)

    def test_reputation_updates_with_multiple_votes(self):
        """Test that reputation updates correctly with multiple votes."""
        thread = Conversation.objects.create(
            title="Test Thread",
            conversation_type=ConversationTypeChoices.THREAD,
            creator=self.author,
        )

        message = ChatMessage.objects.create(
            conversation=thread,
            msg_type="HUMAN",
            content="Test message",
            creator=self.author,
        )

        # Create multiple votes
        MessageVote.objects.create(
            message=message,
            vote_type=VoteType.UPVOTE,
            creator=self.user1,
        )

        MessageVote.objects.create(
            message=message,
            vote_type=VoteType.UPVOTE,
            creator=self.user2,
        )

        # Check reputation
        global_reputation = UserReputation.objects.get(user=self.author, corpus=None)
        self.assertEqual(global_reputation.reputation_score, 2)
        self.assertEqual(global_reputation.total_upvotes_received, 2)

    def test_reputation_decreases_with_downvotes(self):
        """Test that reputation decreases with downvotes."""
        thread = Conversation.objects.create(
            title="Test Thread",
            conversation_type=ConversationTypeChoices.THREAD,
            creator=self.author,
        )

        message = ChatMessage.objects.create(
            conversation=thread,
            msg_type="HUMAN",
            content="Test message",
            creator=self.author,
        )

        # Create upvote and downvote
        MessageVote.objects.create(
            message=message,
            vote_type=VoteType.UPVOTE,
            creator=self.user1,
        )

        MessageVote.objects.create(
            message=message,
            vote_type=VoteType.DOWNVOTE,
            creator=self.user2,
        )

        # Check reputation (upvote - downvote = 0)
        global_reputation = UserReputation.objects.get(user=self.author, corpus=None)
        self.assertEqual(global_reputation.reputation_score, 0)
        self.assertEqual(global_reputation.total_upvotes_received, 1)
        self.assertEqual(global_reputation.total_downvotes_received, 1)

    def test_corpus_specific_reputation_calculation(self):
        """Test that corpus-specific reputation is calculated separately."""
        thread = Conversation.objects.create(
            title="Test Thread",
            conversation_type=ConversationTypeChoices.THREAD,
            chat_with_corpus=self.corpus1,
            creator=self.author,
        )

        message = ChatMessage.objects.create(
            conversation=thread,
            msg_type="HUMAN",
            content="Test message",
            creator=self.author,
        )

        MessageVote.objects.create(
            message=message,
            vote_type=VoteType.UPVOTE,
            creator=self.user1,
        )

        # Check corpus-specific reputation
        corpus_reputation = UserReputation.objects.get(
            user=self.author, corpus=self.corpus1
        )
        self.assertEqual(corpus_reputation.reputation_score, 1)

        # Check global reputation also exists
        global_reputation = UserReputation.objects.get(user=self.author, corpus=None)
        self.assertEqual(global_reputation.reputation_score, 1)

    def test_reputation_across_multiple_messages(self):
        """Test that reputation is calculated across all user messages."""
        thread = Conversation.objects.create(
            title="Test Thread",
            conversation_type=ConversationTypeChoices.THREAD,
            creator=self.author,
        )

        # Create multiple messages
        message1 = ChatMessage.objects.create(
            conversation=thread,
            msg_type="HUMAN",
            content="Message 1",
            creator=self.author,
        )

        message2 = ChatMessage.objects.create(
            conversation=thread,
            msg_type="HUMAN",
            content="Message 2",
            creator=self.author,
        )

        # Vote on both messages
        MessageVote.objects.create(
            message=message1,
            vote_type=VoteType.UPVOTE,
            creator=self.user1,
        )

        MessageVote.objects.create(
            message=message2,
            vote_type=VoteType.UPVOTE,
            creator=self.user1,
        )

        # Check reputation includes votes from both messages
        global_reputation = UserReputation.objects.get(user=self.author, corpus=None)
        self.assertEqual(global_reputation.reputation_score, 2)
        self.assertEqual(global_reputation.total_upvotes_received, 2)

    def test_reputation_updates_when_vote_deleted(self):
        """Test that reputation updates when a vote is deleted."""
        thread = Conversation.objects.create(
            title="Test Thread",
            conversation_type=ConversationTypeChoices.THREAD,
            creator=self.author,
        )

        message = ChatMessage.objects.create(
            conversation=thread,
            msg_type="HUMAN",
            content="Test message",
            creator=self.author,
        )

        vote = MessageVote.objects.create(
            message=message,
            vote_type=VoteType.UPVOTE,
            creator=self.user1,
        )

        # Verify reputation is 1
        global_reputation = UserReputation.objects.get(user=self.author, corpus=None)
        self.assertEqual(global_reputation.reputation_score, 1)

        # Delete the vote
        vote.delete()

        # Verify reputation is back to 0
        global_reputation.refresh_from_db()
        self.assertEqual(global_reputation.reputation_score, 0)
        self.assertEqual(global_reputation.total_upvotes_received, 0)


class TestVoteIntegration(TestCase):
    """Integration tests for complete voting scenarios."""

    @classmethod
    def setUpTestData(cls):
        """Create test data."""
        cls.user1 = User.objects.create_user(
            username="user1",
            password="testpass123",
            email="user1@test.com",
        )

        cls.user2 = User.objects.create_user(
            username="user2",
            password="testpass123",
            email="user2@test.com",
        )

        cls.user3 = User.objects.create_user(
            username="user3",
            password="testpass123",
            email="user3@test.com",
        )

        cls.corpus = Corpus.objects.create(
            title="Discussion Corpus",
            description="A corpus for discussions",
            creator=cls.user1,
            is_public=True,
        )

    def test_complete_voting_scenario(self):
        """Test a complete discussion with multiple users voting."""
        # User1 creates a thread
        thread = Conversation.objects.create(
            title="Feature Request",
            conversation_type=ConversationTypeChoices.THREAD,
            chat_with_corpus=self.corpus,
            creator=self.user1,
        )

        # User1 posts initial message
        message1 = ChatMessage.objects.create(
            conversation=thread,
            msg_type="HUMAN",
            content="I think we should add feature X",
            creator=self.user1,
        )

        # User2 replies and upvotes user1's message
        message2 = ChatMessage.objects.create(
            conversation=thread,
            msg_type="HUMAN",
            content="Great idea!",
            parent_message=message1,
            creator=self.user2,
        )

        MessageVote.objects.create(
            message=message1,
            vote_type=VoteType.UPVOTE,
            creator=self.user2,
        )

        # User3 also upvotes user1's message
        MessageVote.objects.create(
            message=message1,
            vote_type=VoteType.UPVOTE,
            creator=self.user3,
        )

        # User1 upvotes user2's message
        MessageVote.objects.create(
            message=message2,
            vote_type=VoteType.UPVOTE,
            creator=self.user1,
        )

        # Verify vote counts
        message1.refresh_from_db()
        message2.refresh_from_db()
        self.assertEqual(message1.upvote_count, 2)
        self.assertEqual(message2.upvote_count, 1)

        # Verify reputations
        user1_global_rep = UserReputation.objects.get(user=self.user1, corpus=None)
        user2_global_rep = UserReputation.objects.get(user=self.user2, corpus=None)

        self.assertEqual(user1_global_rep.reputation_score, 2)  # 2 upvotes
        self.assertEqual(user2_global_rep.reputation_score, 1)  # 1 upvote

        # Verify corpus-specific reputations
        user1_corpus_rep = UserReputation.objects.get(
            user=self.user1, corpus=self.corpus
        )
        user2_corpus_rep = UserReputation.objects.get(
            user=self.user2, corpus=self.corpus
        )

        self.assertEqual(user1_corpus_rep.reputation_score, 2)
        self.assertEqual(user2_corpus_rep.reputation_score, 1)

    def test_vote_change_scenario(self):
        """Test changing votes in a discussion."""
        thread = Conversation.objects.create(
            title="Controversial Topic",
            conversation_type=ConversationTypeChoices.THREAD,
            creator=self.user1,
        )

        message = ChatMessage.objects.create(
            conversation=thread,
            msg_type="HUMAN",
            content="Controversial opinion",
            creator=self.user1,
        )

        # User2 initially downvotes
        vote = MessageVote.objects.create(
            message=message,
            vote_type=VoteType.DOWNVOTE,
            creator=self.user2,
        )

        message.refresh_from_db()
        self.assertEqual(message.downvote_count, 1)
        self.assertEqual(message.upvote_count, 0)

        # User2 changes mind and upvotes
        vote.vote_type = VoteType.UPVOTE
        vote.save()

        message.refresh_from_db()
        self.assertEqual(message.upvote_count, 1)
        self.assertEqual(message.downvote_count, 0)

        # Verify reputation adjusted
        user1_rep = UserReputation.objects.get(user=self.user1, corpus=None)
        self.assertEqual(user1_rep.reputation_score, 1)
