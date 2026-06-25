"""
Tests for bifurcated conversation permissions.

This module tests the permission model for Conversation and ChatMessage:
- CHAT type: Restrictive (creator + explicit permissions + public)
- THREAD type: Context-based (inherits visibility from corpus/document)

Key test scenarios:
1. CHAT: creator visibility, no context inheritance
2. THREAD: context inheritance from corpus/document
3. AND logic when both corpus AND document are set on THREAD
4. Anonymous users: only public
5. Superusers: computed like a normal user (no blanket bypass)
6. Parallel permission schemes: Same context with both CHAT and THREAD
"""

from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser, Group
from django.test import TestCase
from guardian.shortcuts import assign_perm

from opencontractserver.conversations.models import (
    ChatMessage,
    Conversation,
    ConversationTypeChoices,
    MessageTypeChoices,
)
from opencontractserver.conversations.services import ConversationService
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.users.models import User


class TestConversationBifurcatedPermissions(TestCase):
    """
    Test the bifurcated permission model for Conversation visibility.
    """

    superuser: User
    alice: User
    bob: User
    charlie: User

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Create users
        cls.superuser = User.objects.create_superuser(
            username="superuser",
            email="super@test.com",
            password="testpass123",
        )
        cls.alice = User.objects.create_user(
            username="alice",
            email="alice@test.com",
            password="testpass123",
        )
        cls.bob = User.objects.create_user(
            username="bob",
            email="bob@test.com",
            password="testpass123",
        )
        cls.charlie = User.objects.create_user(
            username="charlie",
            email="charlie@test.com",
            password="testpass123",
        )

    def setUp(self):
        """Create fresh test data for each test."""
        # Create corpus owned by Alice
        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            creator=self.alice,
            is_public=False,
        )
        # Give Bob READ permission on corpus
        assign_perm("read_corpus", self.bob, self.corpus)

        # Create document owned by Alice in the corpus
        self.document = Document.objects.create(
            title="Test Document",
            creator=self.alice,
            is_public=False,
        )
        # Give Bob READ permission on document
        assign_perm("read_document", self.bob, self.document)

    def tearDown(self):
        """Clean up conversations and documents after each test."""
        ChatMessage.all_objects.all().delete()
        Conversation.all_objects.all().delete()
        Document.objects.all().delete()
        Corpus.objects.all().delete()

    # =========================================================================
    # CHAT Type Tests - Restrictive Permission Model
    # =========================================================================

    def test_chat_creator_can_see_own_chat(self):
        """Creator can see their own CHAT conversation."""
        chat = Conversation.objects.create(
            title="Alice's Chat",
            chat_with_corpus=self.corpus,
            creator=self.alice,
            conversation_type=ConversationTypeChoices.CHAT,
        )

        visible = Conversation.objects.visible_to_user(self.alice)
        self.assertIn(chat, visible)

    def test_chat_no_context_inheritance(self):
        """
        CHAT type does NOT inherit visibility from corpus/document.
        Even corpus readers cannot see others' CHATs.
        """
        # Alice creates a CHAT on the corpus
        chat = Conversation.objects.create(
            title="Alice's Private Chat",
            chat_with_corpus=self.corpus,
            creator=self.alice,
            conversation_type=ConversationTypeChoices.CHAT,
        )

        # Bob has READ on corpus but should NOT see Alice's CHAT
        visible_to_bob = Conversation.objects.visible_to_user(self.bob)
        self.assertNotIn(chat, visible_to_bob)

        # Charlie (no permissions) should also not see it
        visible_to_charlie = Conversation.objects.visible_to_user(self.charlie)
        self.assertNotIn(chat, visible_to_charlie)

    def test_chat_explicit_permission_grants_access(self):
        """
        Explicit guardian permission grants access to CHAT.
        """
        chat = Conversation.objects.create(
            title="Shared Chat",
            chat_with_corpus=self.corpus,
            creator=self.alice,
            conversation_type=ConversationTypeChoices.CHAT,
        )

        # Initially Charlie cannot see it
        self.assertNotIn(chat, Conversation.objects.visible_to_user(self.charlie))

        # Grant explicit permission
        assign_perm("read_conversation", self.charlie, chat)

        # Now Charlie can see it
        self.assertIn(chat, Conversation.objects.visible_to_user(self.charlie))

    def test_chat_public_visible_to_all(self):
        """Public CHAT conversations are visible to all authenticated users."""
        chat = Conversation.objects.create(
            title="Public Chat",
            chat_with_corpus=self.corpus,
            creator=self.alice,
            conversation_type=ConversationTypeChoices.CHAT,
            is_public=True,
        )

        # Everyone can see public chats
        self.assertIn(chat, Conversation.objects.visible_to_user(self.alice))
        self.assertIn(chat, Conversation.objects.visible_to_user(self.bob))
        self.assertIn(chat, Conversation.objects.visible_to_user(self.charlie))

    # =========================================================================
    # THREAD Type Tests - Context-Based Permission Model
    # =========================================================================

    def test_thread_creator_can_see_own_thread(self):
        """Creator can see their own THREAD conversation."""
        thread = Conversation.objects.create(
            title="Alice's Thread",
            chat_with_corpus=self.corpus,
            creator=self.alice,
            conversation_type=ConversationTypeChoices.THREAD,
        )

        visible = Conversation.objects.visible_to_user(self.alice)
        self.assertIn(thread, visible)

    def test_thread_inherits_corpus_visibility(self):
        """
        THREAD type inherits visibility from corpus.
        Users with READ on corpus can see threads linked to it.
        """
        thread = Conversation.objects.create(
            title="Corpus Discussion",
            chat_with_corpus=self.corpus,
            creator=self.alice,
            conversation_type=ConversationTypeChoices.THREAD,
        )

        # Bob has READ on corpus - should see the thread
        visible_to_bob = Conversation.objects.visible_to_user(self.bob)
        self.assertIn(thread, visible_to_bob)

        # Charlie has no corpus permission - should NOT see it
        visible_to_charlie = Conversation.objects.visible_to_user(self.charlie)
        self.assertNotIn(thread, visible_to_charlie)

    def test_thread_inherits_document_visibility(self):
        """
        THREAD type inherits visibility from document.
        Users with READ on document can see threads linked to it.
        """
        thread = Conversation.objects.create(
            title="Document Discussion",
            chat_with_document=self.document,
            creator=self.alice,
            conversation_type=ConversationTypeChoices.THREAD,
        )

        # Bob has READ on document - should see the thread
        visible_to_bob = Conversation.objects.visible_to_user(self.bob)
        self.assertIn(thread, visible_to_bob)

        # Charlie has no document permission - should NOT see it
        visible_to_charlie = Conversation.objects.visible_to_user(self.charlie)
        self.assertNotIn(thread, visible_to_charlie)

    def test_thread_both_context_and_logic(self):
        """
        When THREAD has BOTH corpus AND document set,
        user must have READ on BOTH to see via context inheritance.
        """
        thread = Conversation.objects.create(
            title="Doc-in-Corpus Discussion",
            chat_with_corpus=self.corpus,
            chat_with_document=self.document,
            creator=self.alice,
            conversation_type=ConversationTypeChoices.THREAD,
        )

        # Bob has READ on BOTH corpus and document - should see it
        visible_to_bob = Conversation.objects.visible_to_user(self.bob)
        self.assertIn(thread, visible_to_bob)

        # Create a user with only corpus permission
        corpus_only_user = User.objects.create_user(
            username="corpus_only",
            email="corpus@test.com",
            password="testpass123",
        )
        assign_perm("read_corpus", corpus_only_user, self.corpus)
        # Only corpus permission - should NOT see (AND logic)
        visible_to_corpus_only = Conversation.objects.visible_to_user(corpus_only_user)
        self.assertNotIn(thread, visible_to_corpus_only)

        # Create a user with only document permission
        doc_only_user = User.objects.create_user(
            username="doc_only",
            email="doc@test.com",
            password="testpass123",
        )
        assign_perm("read_document", doc_only_user, self.document)
        # Only document permission - should NOT see (AND logic)
        visible_to_doc_only = Conversation.objects.visible_to_user(doc_only_user)
        self.assertNotIn(thread, visible_to_doc_only)

        # Clean up
        corpus_only_user.delete()
        doc_only_user.delete()

    def test_thread_explicit_permission_bypasses_context(self):
        """
        Explicit guardian permission grants access to THREAD
        even without context permissions.
        """
        thread = Conversation.objects.create(
            title="Restricted Thread",
            chat_with_corpus=self.corpus,
            creator=self.alice,
            conversation_type=ConversationTypeChoices.THREAD,
        )

        # Charlie has no context permissions
        self.assertNotIn(thread, Conversation.objects.visible_to_user(self.charlie))

        # Grant explicit permission
        assign_perm("read_conversation", self.charlie, thread)

        # Now Charlie can see it
        self.assertIn(thread, Conversation.objects.visible_to_user(self.charlie))

    # =========================================================================
    # Parallel Permission Schemes Test
    # =========================================================================

    def test_parallel_chat_and_thread_different_visibility(self):
        """
        Same corpus, same user creates both CHAT and THREAD.
        Corpus reader can see THREAD but NOT CHAT.
        """
        # Alice creates a CHAT on the corpus
        chat = Conversation.objects.create(
            title="Alice's Agent Chat",
            chat_with_corpus=self.corpus,
            creator=self.alice,
            conversation_type=ConversationTypeChoices.CHAT,
        )

        # Alice creates a THREAD on the same corpus
        thread = Conversation.objects.create(
            title="Alice's Discussion",
            chat_with_corpus=self.corpus,
            creator=self.alice,
            conversation_type=ConversationTypeChoices.THREAD,
        )

        # Both exist simultaneously
        all_conversations = Conversation.objects.all()
        self.assertEqual(all_conversations.count(), 2)

        # Alice (creator) sees BOTH
        visible_to_alice = Conversation.objects.visible_to_user(self.alice)
        self.assertIn(chat, visible_to_alice)
        self.assertIn(thread, visible_to_alice)

        # Bob (corpus reader) sees THREAD only - NOT CHAT
        visible_to_bob = Conversation.objects.visible_to_user(self.bob)
        self.assertIn(thread, visible_to_bob)
        self.assertNotIn(chat, visible_to_bob)

        # Charlie (no permissions) sees neither
        visible_to_charlie = Conversation.objects.visible_to_user(self.charlie)
        self.assertNotIn(chat, visible_to_charlie)
        self.assertNotIn(thread, visible_to_charlie)

    # =========================================================================
    # Superuser and Anonymous Tests
    # =========================================================================

    def test_superuser_computed_like_normal_user(self):
        """A no-grant superuser is computed exactly like any authenticated user
        (scoped admin access, 2026-05) — no blanket "sees everything" bypass.

        - A private CHAT created by a stranger (Alice) is NOT visible.
        - A private THREAD on a private corpus the superuser cannot read is
          NOT visible.
        - Once the superuser is granted READ on the corpus, it inherits
          THREAD visibility via context, exactly like a normal corpus reader.
        - A conversation the superuser creates itself is visible via creator.
        """
        stranger_chat = Conversation.objects.create(
            title="Private Chat",
            chat_with_corpus=self.corpus,
            creator=self.alice,
            conversation_type=ConversationTypeChoices.CHAT,
        )
        stranger_thread = Conversation.objects.create(
            title="Private Thread",
            chat_with_corpus=self.corpus,
            creator=self.bob,
            conversation_type=ConversationTypeChoices.THREAD,
        )

        # No grants → the superuser sees neither stranger conversation.
        visible = Conversation.objects.visible_to_user(self.superuser)
        self.assertNotIn(stranger_chat, visible)
        self.assertNotIn(stranger_thread, visible)

        # Positive case 1: the superuser's OWN conversation is visible (creator).
        own_chat = Conversation.objects.create(
            title="Superuser's Own Chat",
            chat_with_corpus=self.corpus,
            creator=self.superuser,
            conversation_type=ConversationTypeChoices.CHAT,
        )
        self.assertIn(own_chat, Conversation.objects.visible_to_user(self.superuser))

        # Positive case 2: grant the superuser READ on the corpus → it now
        # inherits visibility of the THREAD via context, like a normal reader.
        assign_perm("read_corpus", self.superuser, self.corpus)
        visible_after_grant = Conversation.objects.visible_to_user(self.superuser)
        self.assertIn(stranger_thread, visible_after_grant)
        # The CHAT is still restrictive (no context inheritance) — still hidden.
        self.assertNotIn(stranger_chat, visible_after_grant)

    def test_anonymous_user_sees_only_public(self):
        """Anonymous users can only see public conversations."""
        private_chat = Conversation.objects.create(
            title="Private Chat",
            chat_with_corpus=self.corpus,
            creator=self.alice,
            conversation_type=ConversationTypeChoices.CHAT,
            is_public=False,
        )
        public_thread = Conversation.objects.create(
            title="Public Thread",
            chat_with_corpus=self.corpus,
            creator=self.alice,
            conversation_type=ConversationTypeChoices.THREAD,
            is_public=True,
        )

        visible = Conversation.objects.visible_to_user(AnonymousUser())
        self.assertNotIn(private_chat, visible)
        self.assertIn(public_thread, visible)

    def test_anonymous_user_with_none(self):
        """Passing None as user is treated as anonymous."""
        public_thread = Conversation.objects.create(
            title="Public Thread",
            chat_with_corpus=self.corpus,
            creator=self.alice,
            conversation_type=ConversationTypeChoices.THREAD,
            is_public=True,
        )
        private_chat = Conversation.objects.create(
            title="Private Chat",
            creator=self.alice,
            conversation_type=ConversationTypeChoices.CHAT,
        )

        visible = Conversation.objects.visible_to_user(None)
        self.assertIn(public_thread, visible)
        self.assertNotIn(private_chat, visible)

    def test_anonymous_user_sees_threads_on_public_corpus(self):
        """
        Anonymous users can see THREAD conversations on public corpuses
        even if the conversation itself is not marked as public.
        This tests context inheritance for anonymous users.
        """
        # Create a public corpus
        public_corpus = Corpus.objects.create(
            title="Public Corpus",
            creator=self.alice,
            is_public=True,
        )

        # Thread on public corpus (conversation NOT marked public)
        thread_on_public = Conversation.objects.create(
            title="Thread on Public Corpus",
            chat_with_corpus=public_corpus,
            creator=self.alice,
            conversation_type=ConversationTypeChoices.THREAD,
            is_public=False,  # NOT public, but corpus IS public
        )

        # CHAT on public corpus (should NOT be visible - CHATs are restrictive)
        chat_on_public = Conversation.objects.create(
            title="Chat on Public Corpus",
            chat_with_corpus=public_corpus,
            creator=self.alice,
            conversation_type=ConversationTypeChoices.CHAT,
            is_public=False,
        )

        # Thread on private corpus (should NOT be visible)
        thread_on_private = Conversation.objects.create(
            title="Thread on Private Corpus",
            chat_with_corpus=self.corpus,  # self.corpus is private
            creator=self.alice,
            conversation_type=ConversationTypeChoices.THREAD,
            is_public=False,
        )

        visible = Conversation.objects.visible_to_user(AnonymousUser())

        # Anonymous CAN see thread on public corpus (context inheritance)
        self.assertIn(thread_on_public, visible)

        # Anonymous CANNOT see chat on public corpus (CHAT is restrictive)
        self.assertNotIn(chat_on_public, visible)

        # Anonymous CANNOT see thread on private corpus
        self.assertNotIn(thread_on_private, visible)

        # Cleanup
        public_corpus.delete()


class TestChatMessageInheritedPermissions(TestCase):
    """
    Test that ChatMessage visibility inherits from Conversation visibility.
    """

    alice: User
    bob: User
    charlie: User

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.alice = User.objects.create_user(
            username="msg_alice",
            email="msg_alice@test.com",
            password="testpass123",
        )
        cls.bob = User.objects.create_user(
            username="msg_bob",
            email="msg_bob@test.com",
            password="testpass123",
        )
        cls.charlie = User.objects.create_user(
            username="msg_charlie",
            email="msg_charlie@test.com",
            password="testpass123",
        )

    def setUp(self):
        """Create fresh test data for each test."""
        self.corpus = Corpus.objects.create(
            title="Message Test Corpus",
            creator=self.alice,
            is_public=False,
        )
        assign_perm("read_corpus", self.bob, self.corpus)

    def tearDown(self):
        """Clean up after each test."""
        ChatMessage.all_objects.all().delete()
        Conversation.all_objects.all().delete()
        Corpus.objects.all().delete()

    def test_message_inherits_chat_visibility(self):
        """
        Messages in CHAT conversations inherit restrictive visibility.
        Only creator can see messages in their CHAT.
        """
        chat = Conversation.objects.create(
            title="Alice's Chat",
            chat_with_corpus=self.corpus,
            creator=self.alice,
            conversation_type=ConversationTypeChoices.CHAT,
        )
        message = ChatMessage.objects.create(
            conversation=chat,
            creator=self.alice,
            msg_type=MessageTypeChoices.HUMAN,
            content="Hello from chat",
        )

        # Alice sees her message
        visible_to_alice = ChatMessage.objects.visible_to_user(self.alice)
        self.assertIn(message, visible_to_alice)

        # Bob (corpus reader) does NOT see it
        visible_to_bob = ChatMessage.objects.visible_to_user(self.bob)
        self.assertNotIn(message, visible_to_bob)

    def test_message_inherits_thread_visibility(self):
        """
        Messages in THREAD conversations inherit context-based visibility.
        Corpus readers can see messages in threads linked to their corpus.
        """
        thread = Conversation.objects.create(
            title="Corpus Discussion",
            chat_with_corpus=self.corpus,
            creator=self.alice,
            conversation_type=ConversationTypeChoices.THREAD,
        )
        message = ChatMessage.objects.create(
            conversation=thread,
            creator=self.alice,
            msg_type=MessageTypeChoices.HUMAN,
            content="Hello from thread",
        )

        # Alice sees her message
        visible_to_alice = ChatMessage.objects.visible_to_user(self.alice)
        self.assertIn(message, visible_to_alice)

        # Bob (corpus reader) CAN see it via context inheritance
        visible_to_bob = ChatMessage.objects.visible_to_user(self.bob)
        self.assertIn(message, visible_to_bob)

        # Charlie (no permissions) cannot see it
        visible_to_charlie = ChatMessage.objects.visible_to_user(self.charlie)
        self.assertNotIn(message, visible_to_charlie)

    def test_moderator_can_see_all_messages(self):
        """
        Corpus owner (moderator) can see all messages even in others' CHATs.
        """
        # Bob creates a CHAT on Alice's corpus
        chat = Conversation.objects.create(
            title="Bob's Chat",
            chat_with_corpus=self.corpus,
            creator=self.bob,
            conversation_type=ConversationTypeChoices.CHAT,
        )
        message = ChatMessage.objects.create(
            conversation=chat,
            creator=self.bob,
            msg_type=MessageTypeChoices.HUMAN,
            content="Bob's message",
        )

        # Alice (corpus owner) can see Bob's message as moderator
        visible_to_alice = ChatMessage.objects.visible_to_user(self.alice)
        self.assertIn(message, visible_to_alice)

    def test_anonymous_message_visibility_follows_conversation_bifurcation(self):
        """Regression for issue #1986 item 2.

        Anonymous ChatMessage visibility must mirror anonymous *conversation*
        visibility (the CHAT/THREAD bifurcation): public THREADs — and threads
        on public corpuses via context inheritance — are visible, but a public
        CHAT's messages are NOT, because the conversation itself stays hidden
        from anonymous users. The old anonymous branch filtered
        ``conversation__is_public=True`` alone, which both leaked a public
        CHAT's messages and missed context-inherited thread messages.
        """
        public_corpus = Corpus.objects.create(
            title="Public Corpus",
            creator=self.alice,
            is_public=True,
        )

        # Public THREAD -> message visible to anonymous.
        public_thread = Conversation.objects.create(
            title="Public Thread",
            creator=self.alice,
            conversation_type=ConversationTypeChoices.THREAD,
            is_public=True,
        )
        public_thread_msg = ChatMessage.objects.create(
            conversation=public_thread,
            creator=self.alice,
            msg_type=MessageTypeChoices.HUMAN,
            content="visible to anon",
        )

        # Public CHAT -> message must stay hidden (the item-2 leak): the
        # conversation itself is anonymous-hidden, so its messages must be too.
        public_chat = Conversation.objects.create(
            title="Public Chat",
            creator=self.alice,
            conversation_type=ConversationTypeChoices.CHAT,
            is_public=True,
        )
        public_chat_msg = ChatMessage.objects.create(
            conversation=public_chat,
            creator=self.alice,
            msg_type=MessageTypeChoices.HUMAN,
            content="must stay hidden from anon",
        )

        # THREAD on a public corpus (conversation NOT public) -> message
        # visible via context inheritance, matching conversation visibility.
        ctx_thread = Conversation.objects.create(
            title="Thread on Public Corpus",
            chat_with_corpus=public_corpus,
            creator=self.alice,
            conversation_type=ConversationTypeChoices.THREAD,
            is_public=False,
        )
        ctx_thread_msg = ChatMessage.objects.create(
            conversation=ctx_thread,
            creator=self.alice,
            msg_type=MessageTypeChoices.HUMAN,
            content="visible via context inheritance",
        )

        # Private THREAD (on the private setUp corpus) -> message hidden.
        private_thread = Conversation.objects.create(
            title="Private Thread",
            chat_with_corpus=self.corpus,
            creator=self.alice,
            conversation_type=ConversationTypeChoices.THREAD,
            is_public=False,
        )
        private_thread_msg = ChatMessage.objects.create(
            conversation=private_thread,
            creator=self.alice,
            msg_type=MessageTypeChoices.HUMAN,
            content="hidden from anon",
        )

        visible = ChatMessage.objects.visible_to_user(AnonymousUser())

        self.assertIn(public_thread_msg, visible)
        self.assertNotIn(public_chat_msg, visible)  # the item-2 fix
        self.assertIn(ctx_thread_msg, visible)
        self.assertNotIn(private_thread_msg, visible)

        public_corpus.delete()


class TestConversationGroupGrants(TestCase):
    """Group-level guardian READ grants must unlock conversations and messages.

    Regression for issue #1986 item 3: ``ConversationQuerySet`` /
    ``ChatMessageQuerySet`` consulted only USER object-permission tables.
    Because ``user_can(READ)`` routes through ``visible_to_user`` for these
    models, a group-only READ grant was both invisible in lists AND denied by
    ``user_can(READ)`` — even though non-READ writes (``_default_user_can``)
    honour the same group grant. The fix joins the group tables so filter and
    check agree (the same gap PR #1985 closed for annotations / relationships /
    extracts).
    """

    owner: User
    member: User
    outsider: User
    group: Group

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.owner = User.objects.create_user(
            username="grant_owner", email="grant_owner@test.com", password="pw"
        )
        cls.member = User.objects.create_user(
            username="grant_member", email="grant_member@test.com", password="pw"
        )
        cls.outsider = User.objects.create_user(
            username="grant_outsider", email="grant_outsider@test.com", password="pw"
        )
        cls.group = Group.objects.create(name="conversation-readers")
        cls.member.groups.add(cls.group)

    def tearDown(self):
        ChatMessage.all_objects.all().delete()
        Conversation.all_objects.all().delete()

    def test_group_read_grant_makes_conversation_visible_and_passes_user_can(self):
        chat = Conversation.objects.create(
            title="Owner's Chat",
            creator=self.owner,
            conversation_type=ConversationTypeChoices.CHAT,
        )

        # Before the grant: invisible in lists AND user_can(READ) denies.
        self.assertNotIn(chat, Conversation.objects.visible_to_user(self.member))
        self.assertFalse(
            Conversation.objects.user_can(self.member, chat, PermissionTypes.READ)
        )

        assign_perm("read_conversation", self.group, chat)

        # After the group grant: visible AND user_can(READ) grants (parity).
        self.assertIn(chat, Conversation.objects.visible_to_user(self.member))
        self.assertTrue(
            Conversation.objects.user_can(self.member, chat, PermissionTypes.READ)
        )

        # A user NOT in the group still cannot see it.
        self.assertNotIn(chat, Conversation.objects.visible_to_user(self.outsider))

    def test_group_read_grant_makes_message_visible(self):
        # A CHAT the member cannot otherwise see (not creator, not public).
        chat = Conversation.objects.create(
            title="Owner's Chat",
            creator=self.owner,
            conversation_type=ConversationTypeChoices.CHAT,
        )
        message = ChatMessage.objects.create(
            conversation=chat,
            creator=self.owner,
            msg_type=MessageTypeChoices.HUMAN,
            content="group-shared message",
        )

        # No grant -> message invisible (conversation is hidden too).
        self.assertNotIn(message, ChatMessage.objects.visible_to_user(self.member))

        # Direct message-level group grant unlocks it via the message branch.
        assign_perm("read_chatmessage", self.group, message)

        self.assertIn(message, ChatMessage.objects.visible_to_user(self.member))
        # Parity: user_can(READ) on the message agrees with the list filter.
        self.assertTrue(
            ChatMessage.objects.user_can(self.member, message, PermissionTypes.READ)
        )
        # Outsider (not in the group) still cannot see it.
        self.assertNotIn(message, ChatMessage.objects.visible_to_user(self.outsider))

    def test_conversation_group_grant_makes_messages_visible(self):
        """The common path (issue #1986 item 3): a group grant on the
        *conversation* surfaces its *messages* via the ``conversation_visible``
        inheritance branch — distinct from a direct message-level grant. Pins
        the integration between the conversation group-grant fix and message
        visibility so removing the ``conversation_visible`` branch can't
        silently regress it."""
        chat = Conversation.objects.create(
            title="Owner's Chat",
            creator=self.owner,
            conversation_type=ConversationTypeChoices.CHAT,
        )
        message = ChatMessage.objects.create(
            conversation=chat,
            creator=self.owner,
            msg_type=MessageTypeChoices.HUMAN,
            content="via-conversation-grant",
        )

        # No grant -> the member sees neither the conversation nor its messages.
        self.assertNotIn(message, ChatMessage.objects.visible_to_user(self.member))

        # Conversation-level group grant (NOT a message-level grant) -> the
        # message surfaces through conversation visibility inheritance.
        assign_perm("read_conversation", self.group, chat)

        self.assertIn(message, ChatMessage.objects.visible_to_user(self.member))
        # Outsider (not in the group) still cannot see it.
        self.assertNotIn(message, ChatMessage.objects.visible_to_user(self.outsider))

    def test_missing_conversation_group_table_falls_back_gracefully(self):
        """Defensive branch (issue #1986 item 3): if the conversation
        group-permission model can't be resolved, the `except LookupError`
        must degrade to user-level grants only — no crash, group grant simply
        ignored, and already-resolved USER-level grants preserved (the two
        lookups live in separate try blocks precisely for this). Mirrors the
        `BaseVisibilityManager` group-table fallback."""
        import django.apps

        # Only a GROUP grant -> must vanish when the group table is unreadable.
        group_only_chat = Conversation.objects.create(
            title="Group-Only Chat",
            creator=self.owner,
            conversation_type=ConversationTypeChoices.CHAT,
        )
        assign_perm("read_conversation", self.group, group_only_chat)

        # A USER-level grant -> must SURVIVE the missing group table.
        user_granted_chat = Conversation.objects.create(
            title="User-Granted Chat",
            creator=self.owner,
            conversation_type=ConversationTypeChoices.CHAT,
        )
        assign_perm("read_conversation", self.member, user_granted_chat)

        real_get_model = django.apps.apps.get_model

        def fake_get_model(app_label, model_name=None, *args, **kwargs):
            name = model_name if model_name is not None else app_label
            # Surgically fail ONLY the conversation group-permission lookup so
            # the user-level lookup (and Corpus/Document visibility) stay real.
            if isinstance(name, str) and name == "conversationgroupobjectpermission":
                raise LookupError("simulated missing group permission table")
            return real_get_model(app_label, model_name, *args, **kwargs)

        with patch.object(django.apps.apps, "get_model", side_effect=fake_get_model):
            visible = list(Conversation.objects.visible_to_user(self.member))

        # No crash; the un-consultable group grant is ignored...
        self.assertNotIn(group_only_chat, visible)
        # ...but the separately-resolved user-level grant is NOT discarded.
        self.assertIn(user_granted_chat, visible)
        # Owner still sees their own (no patch active here).
        self.assertIn(group_only_chat, Conversation.objects.visible_to_user(self.owner))

    def test_missing_message_group_table_falls_back_gracefully(self):
        """Defensive branch (issue #1986 item 3): the message-level
        `except LookupError` for the chat-message group-permission model must
        degrade gracefully — group grant ignored, no crash, and already-resolved
        USER-level message grants preserved (separate try blocks). Mirrors the
        conversation counterpart's positive/negative assertions."""
        import django.apps

        chat = Conversation.objects.create(
            title="Owner's Chat",
            creator=self.owner,
            conversation_type=ConversationTypeChoices.CHAT,
        )
        # Only a GROUP grant on the message -> must vanish when the group table
        # is unreadable (the parent CHAT is hidden from the member too).
        group_only_message = ChatMessage.objects.create(
            conversation=chat,
            creator=self.owner,
            msg_type=MessageTypeChoices.HUMAN,
            content="group-shared message",
        )
        assign_perm("read_chatmessage", self.group, group_only_message)

        # A USER-level message grant -> must SURVIVE the missing group table.
        user_granted_message = ChatMessage.objects.create(
            conversation=chat,
            creator=self.owner,
            msg_type=MessageTypeChoices.HUMAN,
            content="user-shared message",
        )
        assign_perm("read_chatmessage", self.member, user_granted_message)

        real_get_model = django.apps.apps.get_model

        def fake_get_model(app_label, model_name=None, *args, **kwargs):
            name = model_name if model_name is not None else app_label
            if isinstance(name, str) and name == "chatmessagegroupobjectpermission":
                raise LookupError("simulated missing group permission table")
            return real_get_model(app_label, model_name, *args, **kwargs)

        with patch.object(django.apps.apps, "get_model", side_effect=fake_get_model):
            visible = list(ChatMessage.objects.visible_to_user(self.member))

        # Group-only message vanishes (table unreadable, parent CHAT hidden)...
        self.assertNotIn(group_only_message, visible)
        # ...but the separately-resolved user-level message grant is preserved.
        self.assertIn(user_granted_message, visible)


class TestConversationService(TestCase):
    """
    Test the ConversationService helper class.

    ``ConversationService`` is classmethod-based: every public method takes
    the acting ``user`` plus an optional ``request`` for request-scoped
    caching (the standard ``BaseService`` convention). It replaced the
    retired instance-based ``ConversationQueryOptimizer`` /
    ``get_request_optimizer`` style in Phase 4 of the service-layer
    centralization roadmap.
    """

    alice: User
    bob: User
    superuser: User

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.alice = User.objects.create_user(
            username="svc_alice",
            email="svc_alice@test.com",
            password="testpass123",
        )
        cls.bob = User.objects.create_user(
            username="svc_bob",
            email="svc_bob@test.com",
            password="testpass123",
        )
        cls.superuser = User.objects.create_superuser(
            username="svc_super",
            email="svc_super@test.com",
            password="testpass123",
        )

    def setUp(self):
        """Create test data."""
        self.corpus = Corpus.objects.create(
            title="Service Test Corpus",
            creator=self.alice,
            is_public=False,
        )
        assign_perm("read_corpus", self.bob, self.corpus)

        self.document = Document.objects.create(
            title="Service Test Document",
            description="",
            pdf_file="path/to/x.pdf",
            creator=self.alice,
            is_public=False,
        )
        assign_perm("read_document", self.bob, self.document)

    def tearDown(self):
        """Clean up."""
        ChatMessage.all_objects.all().delete()
        Conversation.all_objects.all().delete()
        Document.objects.all().delete()
        Corpus.objects.all().delete()

    def test_check_conversation_visibility(self):
        """Test IDOR-safe visibility check."""
        thread = Conversation.objects.create(
            title="Test Thread",
            chat_with_corpus=self.corpus,
            creator=self.alice,
            conversation_type=ConversationTypeChoices.THREAD,
        )

        # Bob can see it (inherits READ from the shared corpus)
        self.assertTrue(
            ConversationService.check_conversation_visibility(self.bob, thread.id)
        )

        # Non-existent ID returns False (IDOR-safe)
        self.assertFalse(
            ConversationService.check_conversation_visibility(self.bob, 99999)
        )

    def test_check_conversation_visibility_superuser(self):
        """Visibility is computed for a superuser exactly like a normal user
        (scoped admin access, 2026-05) — no blanket bypass.

        - A private THREAD on a corpus the superuser cannot read → False.
        - Once granted corpus READ (THREAD context inheritance) → True.
        - Non-existent IDs always fail (IDOR-safe).
        """
        thread = Conversation.objects.create(
            title="Super Thread",
            chat_with_corpus=self.corpus,
            creator=self.alice,
            conversation_type=ConversationTypeChoices.THREAD,
        )
        # No grant on the private corpus → the THREAD is not visible.
        self.assertFalse(
            ConversationService.check_conversation_visibility(self.superuser, thread.id)
        )

        # Grant corpus READ → the THREAD becomes visible via context inheritance.
        assign_perm("read_corpus", self.superuser, self.corpus)
        self.assertTrue(
            ConversationService.check_conversation_visibility(self.superuser, thread.id)
        )

        # Non-existent ID returns False (IDOR-safe), regardless of superuser.
        self.assertFalse(
            ConversationService.check_conversation_visibility(self.superuser, 99999)
        )

    def test_get_threads_for_corpus(self):
        """Test getting visible threads for a corpus (THREAD type only)."""
        thread1 = Conversation.objects.create(
            title="Thread 1",
            chat_with_corpus=self.corpus,
            creator=self.alice,
            conversation_type=ConversationTypeChoices.THREAD,
        )
        # Create a CHAT (should not be included)
        Conversation.objects.create(
            title="Chat",
            chat_with_corpus=self.corpus,
            creator=self.alice,
            conversation_type=ConversationTypeChoices.CHAT,
        )

        threads = ConversationService.get_threads_for_corpus(self.bob, self.corpus.id)

        self.assertEqual(threads.count(), 1)
        self.assertIn(thread1, threads)

    def test_get_threads_for_document(self):
        """Test getting visible threads for a document (THREAD type only)."""
        thread = Conversation.objects.create(
            title="Doc Thread",
            chat_with_document=self.document,
            creator=self.alice,
            conversation_type=ConversationTypeChoices.THREAD,
        )

        threads = ConversationService.get_threads_for_document(
            self.bob, self.document.id
        )

        self.assertEqual(threads.count(), 1)
        self.assertIn(thread, threads)

    def test_get_chats_for_user(self):
        """get_chats_for_user returns the user's own CHAT conversations."""
        own_chat = Conversation.objects.create(
            title="Bob's Chat",
            creator=self.bob,
            conversation_type=ConversationTypeChoices.CHAT,
        )
        # A THREAD must not appear in the CHAT list.
        Conversation.objects.create(
            title="Bob's Thread",
            chat_with_corpus=self.corpus,
            creator=self.bob,
            conversation_type=ConversationTypeChoices.THREAD,
        )

        chats = ConversationService.get_chats_for_user(self.bob)

        self.assertEqual(chats.count(), 1)
        self.assertIn(own_chat, chats)

    def test_get_corpus_conversation_counts(self):
        """get_corpus_conversation_counts returns (thread_count, chat_count)."""
        for idx in range(2):
            Conversation.objects.create(
                title=f"Count Thread {idx}",
                chat_with_corpus=self.corpus,
                creator=self.alice,
                conversation_type=ConversationTypeChoices.THREAD,
            )
        # Bob's own CHAT linked to the corpus (visible to its creator).
        Conversation.objects.create(
            title="Count Chat",
            chat_with_corpus=self.corpus,
            creator=self.bob,
            conversation_type=ConversationTypeChoices.CHAT,
        )

        thread_count, chat_count = ConversationService.get_corpus_conversation_counts(
            self.bob, self.corpus.id
        )
        self.assertEqual(thread_count, 2)
        self.assertEqual(chat_count, 1)

    def test_request_level_caching(self):
        """check_conversation_visibility caches the visible-id set on the request."""
        thread = Conversation.objects.create(
            title="Cached Thread",
            chat_with_corpus=self.corpus,
            creator=self.alice,
            conversation_type=ConversationTypeChoices.THREAD,
        )
        request = SimpleNamespace()

        # First call computes and caches the visible-id set on the request.
        self.assertTrue(
            ConversationService.check_conversation_visibility(
                self.bob, thread.id, request=request
            )
        )

        # Delete the conversation; a fresh visibility query would miss it.
        Conversation.objects.filter(id=thread.id).delete()

        # Second call with the same request reuses the cached set.
        self.assertTrue(
            ConversationService.check_conversation_visibility(
                self.bob, thread.id, request=request
            )
        )

    def test_no_request_recomputes_each_call(self):
        """Without a request, each visibility check recomputes (no stale cache)."""
        thread = Conversation.objects.create(
            title="Uncached Thread",
            chat_with_corpus=self.corpus,
            creator=self.alice,
            conversation_type=ConversationTypeChoices.THREAD,
        )
        self.assertTrue(
            ConversationService.check_conversation_visibility(self.bob, thread.id)
        )

        Conversation.objects.filter(id=thread.id).delete()

        # No request was threaded, so the second call recomputes and misses.
        self.assertFalse(
            ConversationService.check_conversation_visibility(self.bob, thread.id)
        )


class TestEdgeCases(TestCase):
    """
    Test edge cases and boundary conditions.
    """

    alice: User

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.alice = User.objects.create_user(
            username="edge_alice",
            email="edge_alice@test.com",
            password="testpass123",
        )

    def tearDown(self):
        """Clean up."""
        ChatMessage.all_objects.all().delete()
        Conversation.all_objects.all().delete()
        Corpus.objects.all().delete()
        Document.objects.all().delete()

    def test_thread_with_no_context(self):
        """
        THREAD with no corpus or document relies on base conditions only.
        """
        thread = Conversation.objects.create(
            title="Orphan Thread",
            creator=self.alice,
            conversation_type=ConversationTypeChoices.THREAD,
        )

        # Creator can see it
        visible = Conversation.objects.visible_to_user(self.alice)
        self.assertIn(thread, visible)

    def test_distinct_results(self):
        """
        Ensure visible_to_user() returns distinct results without duplicates.
        """
        corpus = Corpus.objects.create(
            title="Test Corpus",
            creator=self.alice,
            is_public=True,
        )
        thread = Conversation.objects.create(
            title="Test Thread",
            chat_with_corpus=corpus,
            creator=self.alice,
            conversation_type=ConversationTypeChoices.THREAD,
            is_public=True,
        )

        # Multiple conditions could match (creator + public + context)
        visible = Conversation.objects.visible_to_user(self.alice)

        # Should have exactly one result, not duplicates
        self.assertEqual(visible.filter(id=thread.id).count(), 1)

    def test_soft_deleted_conversations_not_visible(self):
        """
        Soft-deleted conversations should not be visible.
        """
        from django.utils import timezone

        thread = Conversation.objects.create(
            title="Deleted Thread",
            creator=self.alice,
            conversation_type=ConversationTypeChoices.THREAD,
            deleted_at=timezone.now(),
        )

        # Should not be visible via normal manager
        visible = Conversation.objects.visible_to_user(self.alice)
        self.assertNotIn(thread, visible)

        # But should be accessible via all_objects
        self.assertIn(thread, Conversation.all_objects.all())
