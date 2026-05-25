"""
GraphQL mutations for voting system.

This module provides mutations for upvoting/downvoting messages, conversations,
and corpuses:
- VoteMessageMutation: Create or update vote on a message
- RemoveVoteMutation: Remove user's vote from a message
- VoteConversationMutation: Create or update vote on a conversation/thread
- RemoveConversationVoteMutation: Remove user's vote from a conversation/thread
- VoteCorpusMutation: Create or update vote on a corpus (anonymous-friendly)
- RemoveCorpusVoteMutation: Remove caller's vote from a corpus

Permission model:
- Message / Conversation votes: visibility-based, login required.
- Corpus votes: visibility-based for both authenticated and anonymous
  viewers — anonymous voters can only see (and therefore only vote on)
  public corpuses, with one vote per Django session per corpus.
"""

import logging

import graphene
from graphql_jwt.decorators import login_required
from graphql_relay import from_global_id

from config.graphql.graphene_types import (
    ConversationType,
    CorpusType,
    MessageType,
)
from config.graphql.ratelimits import graphql_ratelimit
from opencontractserver.conversations.models import (
    ChatMessage,
    Conversation,
    ConversationVote,
    MessageVote,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.corpuses.services import CorpusVoteService
from opencontractserver.shared.services.base import BaseService
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.auth import is_authenticated_user
from opencontractserver.utils.permissioning import (
    set_permissions_for_obj_to_user,
)

logger = logging.getLogger(__name__)


def _client_ip(info) -> str | None:
    """Best-effort extraction of the caller's IP for the audit hash.

    Honours ``X-Forwarded-For`` (first hop) so deployments behind a
    reverse proxy still get a useful value, then falls back to
    ``REMOTE_ADDR``. Returns ``None`` when no IP can be determined so
    the service stores ``ip_hash=None`` rather than hashing an empty
    string.

    SECURITY NOTE: ``X-Forwarded-For`` is trusted unconditionally — the
    value is only used to compute a salted SHA-256 audit hash on
    :class:`CorpusVote` and never participates in unique constraints,
    rate-limiting, or vote dedup. If the ``ip_hash`` column is ever
    repurposed for abuse decisions, tighten this to honour
    ``settings.SECURE_PROXY_SSL_HEADER`` / a trusted-proxies list.
    """
    request = getattr(info, "context", None)
    if request is None:
        return None
    meta = getattr(request, "META", {}) or {}
    forwarded = meta.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        # X-Forwarded-For may be a CSV: client, proxy1, proxy2 — first
        # value is the real client per the convention.
        return forwarded.split(",")[0].strip() or None
    return meta.get("REMOTE_ADDR") or None


def _ensure_session_key(info) -> str | None:
    """Ensure the Django session exists and return its key, if possible.

    Anonymous corpus voting needs a stable identifier to dedupe against.
    Django creates a session row lazily on the first write; we trigger
    that write by marking the session ``modified`` so the request
    response carries the ``Set-Cookie`` header and subsequent votes from
    the same browser land on the same key.

    Returns the session key on success, or ``None`` if no session
    middleware is available on this request (e.g. a stripped-down test
    client). Callers handle the ``None`` case via the service's
    "anonymous voting requires a session" error.
    """
    request = getattr(info, "context", None)
    if request is None:
        return None
    session = getattr(request, "session", None)
    if session is None:
        return None
    if not session.session_key:
        # Force persistence without polluting the session store with a
        # never-cleaned-up sentinel key.  ``session.modified = True`` is
        # the documented Django idiom for "I haven't written anything
        # meaningful but please create the row + set the cookie anyway".
        session.modified = True
        try:
            session.save()
        except Exception:  # pragma: no cover - defensive
            logger.exception("Failed to persist session for anonymous vote")
            return None
    return session.session_key


class VoteMessageMutation(graphene.Mutation):
    """
    Create or update a vote on a message.
    Users can upvote or downvote messages. Changing vote type updates the existing vote.
    Users cannot vote on their own messages.
    """

    class Arguments:
        message_id = graphene.String(
            required=True, description="ID of the message to vote on"
        )
        vote_type = graphene.String(
            required=True, description="Vote type: 'upvote' or 'downvote'"
        )

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(MessageType)

    @login_required
    @graphql_ratelimit(rate="60/m")
    def mutate(root, info, message_id, vote_type) -> "VoteMessageMutation":
        ok = False
        obj = None
        message_text = ""

        try:
            user = info.context.user

            # Validate vote_type
            vote_type_lower = vote_type.lower()
            if vote_type_lower not in ["upvote", "downvote"]:
                return VoteMessageMutation(
                    ok=False,
                    message="Invalid vote_type. Must be 'upvote' or 'downvote'",
                    obj=None,
                )

            # IDOR-safe fetch via the service layer.
            message_pk = from_global_id(message_id)[1]
            chat_message = BaseService.get_or_none(
                ChatMessage, message_pk, user, request=info.context
            )
            if chat_message is None:
                return VoteMessageMutation(
                    ok=False, message="Message not found", obj=None
                )

            # Prevent users from voting on their own messages
            if chat_message.creator == user:
                return VoteMessageMutation(
                    ok=False, message="You cannot vote on your own messages", obj=None
                )

            # Check if vote already exists
            existing_vote = MessageVote.objects.filter(
                message=chat_message, creator=user
            ).first()

            if existing_vote:
                # Update existing vote if vote type changed
                if existing_vote.vote_type != vote_type_lower:
                    existing_vote.vote_type = vote_type_lower
                    existing_vote.save(update_fields=["vote_type"])
                    message_text = f"Vote updated to {vote_type_lower}"
                else:
                    message_text = f"Vote already set to {vote_type_lower}"
            else:
                # Create new vote
                existing_vote = MessageVote.objects.create(
                    message=chat_message, vote_type=vote_type_lower, creator=user
                )
                # Set permissions for the creator
                set_permissions_for_obj_to_user(
                    user,
                    existing_vote,
                    [PermissionTypes.CRUD],
                    is_new=True,
                    request=info.context,
                )
                message_text = f"Vote ({vote_type_lower}) added successfully"

            ok = True
            obj = chat_message

        except Exception as e:
            logger.error(f"Error voting on message: {e}", exc_info=True)
            message_text = f"Failed to vote on message: {str(e)}"

        return VoteMessageMutation(ok=ok, message=message_text, obj=obj)


class RemoveVoteMutation(graphene.Mutation):
    """
    Remove user's vote from a message.
    """

    class Arguments:
        message_id = graphene.String(
            required=True, description="ID of the message to remove vote from"
        )

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(MessageType)

    @login_required
    @graphql_ratelimit(rate="60/m")
    def mutate(root, info, message_id) -> "RemoveVoteMutation":
        ok = False
        obj = None
        message_text = ""

        try:
            user = info.context.user

            # IDOR-safe fetch via the service layer.
            message_pk = from_global_id(message_id)[1]
            chat_message = BaseService.get_or_none(
                ChatMessage, message_pk, user, request=info.context
            )
            if chat_message is None:
                return RemoveVoteMutation(
                    ok=False, message="Message not found", obj=None
                )

            # Check if vote exists
            existing_vote = MessageVote.objects.filter(
                message=chat_message, creator=user
            ).first()

            if existing_vote:
                existing_vote.delete()
                message_text = "Vote removed successfully"
            else:
                message_text = "No vote found to remove"

            ok = True
            obj = chat_message

        except Exception as e:
            logger.error(f"Error removing vote: {e}", exc_info=True)
            message_text = f"Failed to remove vote: {str(e)}"

        return RemoveVoteMutation(ok=ok, message=message_text, obj=obj)


class VoteConversationMutation(graphene.Mutation):
    """
    Create or update a vote on a conversation/thread.
    Users can upvote or downvote threads. Changing vote type updates the existing vote.
    Users cannot vote on their own threads.

    Permission: Users can vote on any conversation/thread they can see (visibility-based).
    """

    class Arguments:
        conversation_id = graphene.String(
            required=True, description="ID of the conversation/thread to vote on"
        )
        vote_type = graphene.String(
            required=True, description="Vote type: 'upvote' or 'downvote'"
        )

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(ConversationType)

    @login_required
    @graphql_ratelimit(rate="60/m")
    def mutate(root, info, conversation_id, vote_type) -> "VoteConversationMutation":
        ok = False
        obj = None
        message_text = ""

        try:
            user = info.context.user

            # Validate vote_type
            vote_type_lower = vote_type.lower()
            if vote_type_lower not in ["upvote", "downvote"]:
                return VoteConversationMutation(
                    ok=False,
                    message="Invalid vote_type. Must be 'upvote' or 'downvote'",
                    obj=None,
                )

            # IDOR-safe fetch via the service layer.
            conversation_pk = from_global_id(conversation_id)[1]
            conversation = BaseService.get_or_none(
                Conversation, conversation_pk, user, request=info.context
            )
            if conversation is None:
                return VoteConversationMutation(
                    ok=False,
                    message="Conversation not found or you do not have permission to access it",
                    obj=None,
                )

            # Prevent users from voting on their own threads
            if conversation.creator == user:
                return VoteConversationMutation(
                    ok=False,
                    message="You cannot vote on your own threads",
                    obj=None,
                )

            # Check if vote already exists
            existing_vote = ConversationVote.objects.filter(
                conversation=conversation, creator=user
            ).first()

            if existing_vote:
                # Update existing vote if vote type changed
                if existing_vote.vote_type != vote_type_lower:
                    existing_vote.vote_type = vote_type_lower
                    existing_vote.save(update_fields=["vote_type"])
                    message_text = f"Vote updated to {vote_type_lower}"
                else:
                    message_text = f"Vote already set to {vote_type_lower}"
            else:
                # Create new vote
                existing_vote = ConversationVote.objects.create(
                    conversation=conversation, vote_type=vote_type_lower, creator=user
                )
                # Set permissions for the creator
                set_permissions_for_obj_to_user(
                    user,
                    existing_vote,
                    [PermissionTypes.CRUD],
                    is_new=True,
                    request=info.context,
                )
                message_text = f"Vote ({vote_type_lower}) added successfully"

            ok = True
            obj = conversation

        except Exception as e:
            logger.error(f"Error voting on conversation: {e}", exc_info=True)
            message_text = f"Failed to vote on conversation: {str(e)}"

        return VoteConversationMutation(ok=ok, message=message_text, obj=obj)


class RemoveConversationVoteMutation(graphene.Mutation):
    """
    Remove user's vote from a conversation/thread.

    Permission: Users can remove their vote from any conversation they can see.
    """

    class Arguments:
        conversation_id = graphene.String(
            required=True,
            description="ID of the conversation/thread to remove vote from",
        )

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(ConversationType)

    @login_required
    @graphql_ratelimit(rate="60/m")
    def mutate(root, info, conversation_id) -> "RemoveConversationVoteMutation":
        ok = False
        obj = None
        message_text = ""

        try:
            user = info.context.user

            # IDOR-safe fetch via the service layer.
            conversation_pk = from_global_id(conversation_id)[1]
            conversation = BaseService.get_or_none(
                Conversation, conversation_pk, user, request=info.context
            )
            if conversation is None:
                return RemoveConversationVoteMutation(
                    ok=False,
                    message="Conversation not found or you do not have permission to access it",
                    obj=None,
                )

            # Check if vote exists
            existing_vote = ConversationVote.objects.filter(
                conversation=conversation, creator=user
            ).first()

            if existing_vote:
                existing_vote.delete()
                message_text = "Vote removed successfully"
            else:
                message_text = "No vote found to remove"

            ok = True
            obj = conversation

        except Exception as e:
            logger.error(f"Error removing conversation vote: {e}", exc_info=True)
            message_text = f"Failed to remove vote: {str(e)}"

        return RemoveConversationVoteMutation(ok=ok, message=message_text, obj=obj)


# --------------------------------------------------------------------------- #
# Corpus voting — anonymous-friendly                                          #
# --------------------------------------------------------------------------- #
#
# Unlike the message/conversation mutations these are deliberately NOT
# decorated with ``@login_required``: anonymous browsers should be able to
# upvote/downvote public corpuses on the public discovery surface.  The
# service layer (``CorpusVoteService``) handles the auth/anon branch logic
# and the READ-permission check; this layer only translates GraphQL
# arguments and renders the response.


class VoteCorpusMutation(graphene.Mutation):
    """Create or update a vote on a corpus.

    Authenticated users vote with their account; the service blocks self-vote
    (creators cannot upvote their own corpuses, matching the Message /
    Conversation contract). Anonymous viewers vote via their Django session
    key — one vote per session per corpus. Anonymous voting on a non-public
    corpus is rejected by the same IDOR-safe "not found or no permission"
    response as a malformed corpus id.
    """

    class Arguments:
        corpus_id = graphene.String(
            required=True, description="Relay global ID of the corpus to vote on"
        )
        vote_type = graphene.String(
            required=True, description="Vote type: 'upvote' or 'downvote'"
        )

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(CorpusType)

    # Rate-limited but NOT @login_required: anonymous voting is the whole
    # point of this mutation. The ratelimit_dynamic key falls back to IP for
    # anonymous callers via the existing graphql_ratelimit middleware.
    @graphql_ratelimit(rate="60/m")
    def mutate(root, info, corpus_id, vote_type) -> "VoteCorpusMutation":
        try:
            user = info.context.user
        except AttributeError:
            user = None

        try:
            corpus_pk = from_global_id(corpus_id)[1]
        except Exception:
            return VoteCorpusMutation(
                ok=False,
                message="Corpus not found or you do not have permission to vote on it",
                obj=None,
            )

        is_authenticated = is_authenticated_user(user)
        session_key = None if is_authenticated else _ensure_session_key(info)

        result = CorpusVoteService.cast_vote(
            user,
            corpus_pk,
            vote_type,
            session_key=session_key,
            ip_address=_client_ip(info),
            request=info.context,
        )
        if not result.ok:
            return VoteCorpusMutation(ok=False, message=result.error, obj=None)
        if result.value is None:
            # Defensive: success without a value would be a service bug; surface
            # it as a generic failure rather than crashing on .corpus_id below.
            logger.error("CorpusVoteService.cast_vote returned ok=True without value")
            return VoteCorpusMutation(
                ok=False,
                message="Vote recorded but corpus could not be refreshed",
                obj=None,
            )

        # Refresh the corpus row through the service so the response carries
        # the post-signal denormalized counts (signal runs in the same
        # transaction as the vote insert/update). Routing through the
        # service keeps us inside the CLAUDE.md rule 7 contract.
        corpus = BaseService.get_or_none(
            Corpus, result.value.corpus_id, user, request=info.context
        )
        return VoteCorpusMutation(ok=True, message="Vote recorded", obj=corpus)


class RemoveCorpusVoteMutation(graphene.Mutation):
    """Remove the caller's vote on a corpus.

    Symmetric with :class:`VoteCorpusMutation` — works for both
    authenticated users (creator-keyed) and anonymous viewers
    (session-keyed). Idempotent: removing a non-existent vote is a
    successful no-op rather than an error.
    """

    class Arguments:
        corpus_id = graphene.String(
            required=True,
            description="Relay global ID of the corpus to remove the vote from",
        )

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(CorpusType)

    @graphql_ratelimit(rate="60/m")
    def mutate(root, info, corpus_id) -> "RemoveCorpusVoteMutation":
        try:
            user = info.context.user
        except AttributeError:
            user = None

        try:
            corpus_pk = from_global_id(corpus_id)[1]
        except Exception:
            return RemoveCorpusVoteMutation(
                ok=False,
                message="Corpus not found or you do not have permission to vote on it",
                obj=None,
            )

        # On removal we don't want to spuriously create a session for a
        # caller who never voted in the first place — read whatever's on
        # the request without writing.
        session_key = None
        is_authenticated = is_authenticated_user(user)
        if not is_authenticated:
            session = getattr(info.context, "session", None)
            session_key = getattr(session, "session_key", None) if session else None

        result = CorpusVoteService.remove_vote(
            user,
            corpus_pk,
            session_key=session_key,
            request=info.context,
        )
        if not result.ok:
            return RemoveCorpusVoteMutation(ok=False, message=result.error, obj=None)

        # Route through the service layer (CLAUDE.md rule 7) so we don't
        # hand-roll an ORM call here. The service already gated READ, so
        # ``get_or_none`` returns ``None`` only in pathological cases where
        # something else revoked access between the two calls.
        corpus = BaseService.get_or_none(Corpus, corpus_pk, user, request=info.context)
        message = "Vote removed" if result.value else "No vote to remove"
        return RemoveCorpusVoteMutation(ok=True, message=message, obj=corpus)
