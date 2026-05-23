"""Conversation service — permission-aware conversation visibility queries.

``ConversationService`` provides classmethod helpers with request-level
caching to efficiently check conversation visibility and retrieve threads
for corpus/document contexts.

It implements the bifurcated permission model:
- CHAT type: Restrictive (creator + explicit permissions + public)
- THREAD type: Context-based (inherits visibility from corpus/document)

Migrated from ``conversations/query_optimizer.py`` as Phase 4 of the
service-layer centralization roadmap. The previous instance-based
``ConversationQueryOptimizer`` / ``get_request_optimizer(request)`` style
is retired in favour of the standard ``BaseService`` convention: every
public method is a classmethod taking an optional ``request`` kwarg,
threaded into the request-scoped cache. See
docs/refactor_plans/2026-05-19-service-layer-centralization-design.md.
"""

from typing import Any, Optional

from django.contrib.auth.models import AnonymousUser
from django.db.models import QuerySet

from opencontractserver.shared.services import BaseService


class ConversationService(BaseService):
    """Permission-aware conversation visibility queries.

    Caching is request-scoped: pass ``request`` (``info.context`` in GraphQL
    resolvers) so repeated visibility checks within one request share the
    visible-conversation-id set. When ``request`` is ``None`` (Celery /
    internal callers) each call recomputes — there is no cross-request state.
    """

    # Request attribute prefix for the cached visible-conversation-id set.
    _VISIBLE_CONVERSATION_IDS_CACHE_KEY = "_conversation_visible_ids"

    @staticmethod
    def _normalize_user(user: Optional[Any]) -> Any:
        """Return ``user`` unchanged, or an ``AnonymousUser`` when ``None``."""
        return user if user is not None else AnonymousUser()

    @staticmethod
    def _is_superuser(user: Any) -> bool:
        """Check if the user is a superuser."""
        return bool(getattr(user, "is_superuser", False))

    @classmethod
    def _get_visible_conversation_ids(
        cls, user: Any, *, request: Optional[Any] = None
    ) -> set:
        """
        Get the set of conversation IDs visible to ``user``.

        For superusers this returns an empty set — callers must check
        ``_is_superuser`` first and bypass set-membership entirely.

        When ``request`` is provided the set is cached on the request,
        keyed by user, so repeated visibility checks share the subquery.

        Returns:
            Set of conversation IDs the user can see, or empty set for superusers.
        """
        from opencontractserver.conversations.models import Conversation

        if cls._is_superuser(user):
            # Superusers see all - callers short-circuit before reaching here.
            return set()

        cache_key = (
            f"{cls._VISIBLE_CONVERSATION_IDS_CACHE_KEY}_{getattr(user, 'id', None)}"
        )
        if request is not None and hasattr(request, cache_key):
            return getattr(request, cache_key)

        visible_ids = set(
            Conversation.objects.visible_to_user(user).values_list("id", flat=True)
        )
        if request is not None:
            setattr(request, cache_key, visible_ids)
        return visible_ids

    @classmethod
    def check_conversation_visibility(
        cls, user: Optional[Any], conversation_id: int, *, request: Optional[Any] = None
    ) -> bool:
        """
        Check if user can see a specific conversation (IDOR-safe).

        This method is safe to use in mutation resolvers where you need
        to verify access without revealing whether the object exists.

        Args:
            user: The user to check visibility for. None is treated as anonymous.
            conversation_id: The ID of the conversation to check.
            request: Optional request object for request-level caching.

        Returns:
            True if user can see the conversation, False otherwise.
            Returns False for both non-existent and inaccessible conversations.
        """
        from opencontractserver.conversations.models import Conversation

        user = cls._normalize_user(user)
        if cls._is_superuser(user):
            # Superusers see all - just check existence
            return Conversation.objects.filter(id=conversation_id).exists()
        return conversation_id in cls._get_visible_conversation_ids(
            user, request=request
        )

    @classmethod
    def get_threads_for_corpus(
        cls, user: Optional[Any], corpus_id: int, *, request: Optional[Any] = None
    ) -> QuerySet:
        """
        Get all visible THREAD conversations for a corpus.

        Args:
            user: The user to filter visibility for. None is treated as anonymous.
            corpus_id: The corpus ID to get threads for.
            request: Accepted for service-layer API consistency; the visibility
                subquery here is not request-cached.

        Returns:
            QuerySet of Conversation objects (THREAD type only) visible
            to the user and linked to the specified corpus.
        """
        from opencontractserver.conversations.models import (
            Conversation,
            ConversationTypeChoices,
        )

        user = cls._normalize_user(user)
        return (
            Conversation.objects.visible_to_user(user)
            .filter(
                conversation_type=ConversationTypeChoices.THREAD,
                chat_with_corpus_id=corpus_id,
            )
            .order_by("-is_pinned", "-created")
        )

    @classmethod
    def get_threads_for_document(
        cls, user: Optional[Any], document_id: int, *, request: Optional[Any] = None
    ) -> QuerySet:
        """
        Get all visible THREAD conversations for a document.

        Args:
            user: The user to filter visibility for. None is treated as anonymous.
            document_id: The document ID to get threads for.
            request: Accepted for service-layer API consistency; the visibility
                subquery here is not request-cached.

        Returns:
            QuerySet of Conversation objects (THREAD type only) visible
            to the user and linked to the specified document.
        """
        from opencontractserver.conversations.models import (
            Conversation,
            ConversationTypeChoices,
        )

        user = cls._normalize_user(user)
        return (
            Conversation.objects.visible_to_user(user)
            .filter(
                conversation_type=ConversationTypeChoices.THREAD,
                chat_with_document_id=document_id,
            )
            .order_by("-is_pinned", "-created")
        )

    @classmethod
    def get_chats_for_user(
        cls, user: Optional[Any], *, request: Optional[Any] = None
    ) -> QuerySet:
        """
        Get all CHAT conversations created by or shared with the user.

        Args:
            user: The user to filter visibility for. None is treated as anonymous.
            request: Accepted for service-layer API consistency; the visibility
                subquery here is not request-cached.

        Returns:
            QuerySet of Conversation objects (CHAT type only) visible
            to the user.
        """
        from opencontractserver.conversations.models import (
            Conversation,
            ConversationTypeChoices,
        )

        user = cls._normalize_user(user)
        return (
            Conversation.objects.visible_to_user(user)
            .filter(conversation_type=ConversationTypeChoices.CHAT)
            .order_by("-created")
        )

    @classmethod
    def get_corpus_conversation_counts(
        cls, user: Optional[Any], corpus_id: int, *, request: Optional[Any] = None
    ) -> tuple[int, int]:
        """
        Get thread and chat counts for a corpus in a single visibility check.

        This is more efficient than calling get_threads_for_corpus() and
        get_chats_for_user() separately, as it only executes the visibility
        subqueries once.

        Args:
            user: The user to filter visibility for. None is treated as anonymous.
            corpus_id: The corpus ID to get counts for.
            request: Accepted for service-layer API consistency.

        Returns:
            Tuple of (thread_count, chat_count) for visible conversations.
        """
        from opencontractserver.conversations.models import (
            Conversation,
            ConversationTypeChoices,
        )

        user = cls._normalize_user(user)

        # Share the visibility QuerySet so the corpus-visibility subquery is
        # only constructed once; the two .count() calls below each issue their
        # own COUNT(*) round-trip but reuse that subquery.
        visible_corpus_conversations = Conversation.objects.visible_to_user(
            user
        ).filter(chat_with_corpus_id=corpus_id)

        thread_count = visible_corpus_conversations.filter(
            conversation_type=ConversationTypeChoices.THREAD
        ).count()
        chat_count = visible_corpus_conversations.filter(
            conversation_type=ConversationTypeChoices.CHAT
        ).count()

        return thread_count, chat_count
