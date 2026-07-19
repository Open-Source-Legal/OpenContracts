"""Generated strawberry GraphQL module (graphene migration).

Shape-generated from the graphene schema; stub functions marked PORT(...)
carry the ported business logic. See config/graphql_new/manifest.json.
"""

# mypy: disable-error-code="name-defined, valid-type, arg-type"
#   Code-generation artifacts of the strawberry schema bindings that
#   mypy's static pass cannot resolve, NOT real typing defects:
#     name-defined / valid-type — ``Annotated["XType", strawberry.lazy(...)]``
#       forward-reference strings + the runtime-generated ``*Connection``
#       types (``make_connection_types``).
#     arg-type — resolvers construct result types with ``to_global_id()``
#       (``str``) for ``strawberry.ID`` fields and return Django MODEL
#       instances where the field annotation names the strawberry type
#       (the graphene-django resolver contract). Both are correct at
#       runtime. Hand-written config/graphql/core/* stays fully checked.
# flake8: noqa: E501, F821 — generated strawberry schema module.
# E501: long GraphQL field/argument ``description=`` strings and the
# single-line generated resolver signatures (black cannot split string
# literals). F821: ``Annotated["XType", strawberry.lazy(...)]`` /
# ``cast("QuerySet", ...)`` forward-reference STRINGS that pyflakes
# resolves as names — the whole point of strawberry.lazy is to avoid the
# import (which would then be F401). Both are code-generation artifacts,
# not defects; hand-written modules (config/graphql/core/*, security.py,
# testing.py, filters.py, …) stay fully linted.

from __future__ import annotations

import logging
from typing import Annotated

import strawberry
from graphql_relay import from_global_id

from config.graphql._util import strip_unset
from config.graphql.core.auth import PermissionDenied
from config.graphql.core.relay import (
    register_type,
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

# NOTE on decorators: the graphene mutations were decorated with
# ``@login_required`` and/or ``@graphql_ratelimit(...)`` on
# ``mutate(root, info, …)``. Mutate stubs here take ``payload_cls`` as their
# first positional argument, which does not match those decorators'
# ``(root, info, ...)`` calling convention — so ``login_required`` is inlined
# (see user_mutations.py) and ``graphql_ratelimit`` is applied to an inner
# function named ``mutate`` so the rate-limit cache group (defaults to the
# decorated function's ``__name__``) stays "mutate", exactly as in the
# graphene layer.


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


@strawberry.type(
    name="VoteMessageMutation",
    description="Create or update a vote on a message.\nUsers can upvote or downvote messages. Changing vote type updates the existing vote.\nUsers cannot vote on their own messages.",
)
class VoteMessageMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[MessageType, strawberry.lazy("config.graphql.conversation_types")]
    ) = strawberry.field(name="obj", default=None)


register_type("VoteMessageMutation", VoteMessageMutation, model=None)


@strawberry.type(
    name="RemoveVoteMutation", description="Remove user's vote from a message."
)
class RemoveVoteMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[MessageType, strawberry.lazy("config.graphql.conversation_types")]
    ) = strawberry.field(name="obj", default=None)


register_type("RemoveVoteMutation", RemoveVoteMutation, model=None)


@strawberry.type(
    name="VoteConversationMutation",
    description="Create or update a vote on a conversation/thread.\nUsers can upvote or downvote threads. Changing vote type updates the existing vote.\nUsers cannot vote on their own threads.\n\nPermission: Users can vote on any conversation/thread they can see (visibility-based).",
)
class VoteConversationMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[
            ConversationType, strawberry.lazy("config.graphql.conversation_types")
        ]
    ) = strawberry.field(name="obj", default=None)


register_type("VoteConversationMutation", VoteConversationMutation, model=None)


@strawberry.type(
    name="RemoveConversationVoteMutation",
    description="Remove user's vote from a conversation/thread.\n\nPermission: Users can remove their vote from any conversation they can see.",
)
class RemoveConversationVoteMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[
            ConversationType, strawberry.lazy("config.graphql.conversation_types")
        ]
    ) = strawberry.field(name="obj", default=None)


register_type(
    "RemoveConversationVoteMutation", RemoveConversationVoteMutation, model=None
)


@strawberry.type(
    name="VoteCorpusMutation",
    description='Create or update a vote on a corpus.\n\nAuthenticated users vote with their account; the service blocks self-vote\n(creators cannot upvote their own corpuses, matching the Message /\nConversation contract). Anonymous viewers vote via their Django session\nkey — one vote per session per corpus. Anonymous voting on a non-public\ncorpus is rejected by the same IDOR-safe "not found or no permission"\nresponse as a malformed corpus id.',
)
class VoteCorpusMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[CorpusType, strawberry.lazy("config.graphql.corpus_types")]
    ) = strawberry.field(name="obj", default=None)


register_type("VoteCorpusMutation", VoteCorpusMutation, model=None)


@strawberry.type(
    name="RemoveCorpusVoteMutation",
    description="Remove the caller's vote on a corpus.\n\nSymmetric with :class:`VoteCorpusMutation` — works for both\nauthenticated users (creator-keyed) and anonymous viewers\n(session-keyed). Idempotent: removing a non-existent vote is a\nsuccessful no-op rather than an error.",
)
class RemoveCorpusVoteMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[CorpusType, strawberry.lazy("config.graphql.corpus_types")]
    ) = strawberry.field(name="obj", default=None)


register_type("RemoveCorpusVoteMutation", RemoveCorpusVoteMutation, model=None)


def _mutate_VoteMessageMutation(payload_cls, root, info, message_id, vote_type):
    """PORT: /home/user/oc-graphene-ref/config/graphql/voting_mutations.py:131

    Port of VoteMessageMutation.mutate
    """
    # @login_required — inlined (see module NOTE above).
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    @graphql_ratelimit(rate="60/m")
    def mutate(root, info, message_id, vote_type):
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

    return mutate(root, info, message_id, vote_type)


def m_vote_message(
    info: strawberry.Info,
    message_id: Annotated[
        str,
        strawberry.argument(
            name="messageId", description="ID of the message to vote on"
        ),
    ] = strawberry.UNSET,
    vote_type: Annotated[
        str,
        strawberry.argument(
            name="voteType", description="Vote type: 'upvote' or 'downvote'"
        ),
    ] = strawberry.UNSET,
) -> VoteMessageMutation | None:
    kwargs = strip_unset({"message_id": message_id, "vote_type": vote_type})
    return _mutate_VoteMessageMutation(VoteMessageMutation, None, info, **kwargs)


def _mutate_RemoveVoteMutation(payload_cls, root, info, message_id):
    """PORT: /home/user/oc-graphene-ref/config/graphql/voting_mutations.py:218

    Port of RemoveVoteMutation.mutate
    """
    # @login_required — inlined (see module NOTE above).
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    @graphql_ratelimit(rate="60/m")
    def mutate(root, info, message_id):
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

    return mutate(root, info, message_id)


def m_remove_vote(
    info: strawberry.Info,
    message_id: Annotated[
        str,
        strawberry.argument(
            name="messageId", description="ID of the message to remove vote from"
        ),
    ] = strawberry.UNSET,
) -> RemoveVoteMutation | None:
    kwargs = strip_unset({"message_id": message_id})
    return _mutate_RemoveVoteMutation(RemoveVoteMutation, None, info, **kwargs)


def _mutate_VoteConversationMutation(
    payload_cls, root, info, conversation_id, vote_type
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/voting_mutations.py:280

    Port of VoteConversationMutation.mutate
    """
    # @login_required — inlined (see module NOTE above).
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    @graphql_ratelimit(rate="60/m")
    def mutate(root, info, conversation_id, vote_type):
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

    return mutate(root, info, conversation_id, vote_type)


def m_vote_conversation(
    info: strawberry.Info,
    conversation_id: Annotated[
        str,
        strawberry.argument(
            name="conversationId",
            description="ID of the conversation/thread to vote on",
        ),
    ] = strawberry.UNSET,
    vote_type: Annotated[
        str,
        strawberry.argument(
            name="voteType", description="Vote type: 'upvote' or 'downvote'"
        ),
    ] = strawberry.UNSET,
) -> VoteConversationMutation | None:
    kwargs = strip_unset({"conversation_id": conversation_id, "vote_type": vote_type})
    return _mutate_VoteConversationMutation(
        VoteConversationMutation, None, info, **kwargs
    )


def _mutate_RemoveConversationVoteMutation(payload_cls, root, info, conversation_id):
    """PORT: /home/user/oc-graphene-ref/config/graphql/voting_mutations.py:374

    Port of RemoveConversationVoteMutation.mutate
    """
    # @login_required — inlined (see module NOTE above).
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    @graphql_ratelimit(rate="60/m")
    def mutate(root, info, conversation_id):
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

    return mutate(root, info, conversation_id)


def m_remove_conversation_vote(
    info: strawberry.Info,
    conversation_id: Annotated[
        str,
        strawberry.argument(
            name="conversationId",
            description="ID of the conversation/thread to remove vote from",
        ),
    ] = strawberry.UNSET,
) -> RemoveConversationVoteMutation | None:
    kwargs = strip_unset({"conversation_id": conversation_id})
    return _mutate_RemoveConversationVoteMutation(
        RemoveConversationVoteMutation, None, info, **kwargs
    )


def _mutate_VoteCorpusMutation(payload_cls, root, info, corpus_id, vote_type):
    """PORT: /home/user/oc-graphene-ref/config/graphql/voting_mutations.py:455

    Port of VoteCorpusMutation.mutate
    """

    # Rate-limited but NOT @login_required: anonymous voting is the whole
    # point of this mutation. The ratelimit_dynamic key falls back to IP for
    # anonymous callers via the existing graphql_ratelimit middleware.
    @graphql_ratelimit(rate="60/m")
    def mutate(root, info, corpus_id, vote_type):
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

    return mutate(root, info, corpus_id, vote_type)


def m_vote_corpus(
    info: strawberry.Info,
    corpus_id: Annotated[
        str,
        strawberry.argument(
            name="corpusId", description="Relay global ID of the corpus to vote on"
        ),
    ] = strawberry.UNSET,
    vote_type: Annotated[
        str,
        strawberry.argument(
            name="voteType", description="Vote type: 'upvote' or 'downvote'"
        ),
    ] = strawberry.UNSET,
) -> VoteCorpusMutation | None:
    kwargs = strip_unset({"corpus_id": corpus_id, "vote_type": vote_type})
    return _mutate_VoteCorpusMutation(VoteCorpusMutation, None, info, **kwargs)


def _mutate_RemoveCorpusVoteMutation(payload_cls, root, info, corpus_id):
    """PORT: /home/user/oc-graphene-ref/config/graphql/voting_mutations.py:523

    Port of RemoveCorpusVoteMutation.mutate
    """

    # NOT @login_required — symmetric with VoteCorpusMutation (anonymous
    # session-keyed voters must be able to remove their vote).
    @graphql_ratelimit(rate="60/m")
    def mutate(root, info, corpus_id):
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

    return mutate(root, info, corpus_id)


def m_remove_corpus_vote(
    info: strawberry.Info,
    corpus_id: Annotated[
        str,
        strawberry.argument(
            name="corpusId",
            description="Relay global ID of the corpus to remove the vote from",
        ),
    ] = strawberry.UNSET,
) -> RemoveCorpusVoteMutation | None:
    kwargs = strip_unset({"corpus_id": corpus_id})
    return _mutate_RemoveCorpusVoteMutation(
        RemoveCorpusVoteMutation, None, info, **kwargs
    )


MUTATION_FIELDS = {
    "vote_message": strawberry.field(
        resolver=m_vote_message,
        name="voteMessage",
        description="Create or update a vote on a message.\nUsers can upvote or downvote messages. Changing vote type updates the existing vote.\nUsers cannot vote on their own messages.",
    ),
    "remove_vote": strawberry.field(
        resolver=m_remove_vote,
        name="removeVote",
        description="Remove user's vote from a message.",
    ),
    "vote_conversation": strawberry.field(
        resolver=m_vote_conversation,
        name="voteConversation",
        description="Create or update a vote on a conversation/thread.\nUsers can upvote or downvote threads. Changing vote type updates the existing vote.\nUsers cannot vote on their own threads.\n\nPermission: Users can vote on any conversation/thread they can see (visibility-based).",
    ),
    "remove_conversation_vote": strawberry.field(
        resolver=m_remove_conversation_vote,
        name="removeConversationVote",
        description="Remove user's vote from a conversation/thread.\n\nPermission: Users can remove their vote from any conversation they can see.",
    ),
    "vote_corpus": strawberry.field(
        resolver=m_vote_corpus,
        name="voteCorpus",
        description='Create or update a vote on a corpus.\n\nAuthenticated users vote with their account; the service blocks self-vote\n(creators cannot upvote their own corpuses, matching the Message /\nConversation contract). Anonymous viewers vote via their Django session\nkey — one vote per session per corpus. Anonymous voting on a non-public\ncorpus is rejected by the same IDOR-safe "not found or no permission"\nresponse as a malformed corpus id.',
    ),
    "remove_corpus_vote": strawberry.field(
        resolver=m_remove_corpus_vote,
        name="removeCorpusVote",
        description="Remove the caller's vote on a corpus.\n\nSymmetric with :class:`VoteCorpusMutation` — works for both\nauthenticated users (creator-keyed) and anonymous viewers\n(session-keyed). Idempotent: removing a non-existent vote is a\nsuccessful no-op rather than an error.",
    ),
}
