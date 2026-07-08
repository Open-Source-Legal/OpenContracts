"""Generated strawberry GraphQL module (graphene migration).

Shape-generated from the graphene schema; stub functions marked PORT(...)
carry the ported business logic. See config/graphql_new/manifest.json.
"""
from __future__ import annotations

import datetime
import decimal
import uuid
from typing import Annotated, Any, Optional

import strawberry

from config.graphql.core import permissions as core_permissions
from config.graphql.core.filtering import filterset_factory, setup_filterset
from config.graphql.core.mutations import drf_deletion, drf_mutation
from config.graphql.core.relay import (
    Node,
    get_node_from_global_id,
    make_connection_types,
    register_type,
    resolve_django_connection,
    resolve_django_list,
)
from config.graphql.core.scalars import BigInt, GenericScalar, JSONString
from config.graphql_new._util import coerce_enum, coerce_str, strip_unset
from config.graphql_new import enums




@strawberry.type(name="VoteMessageMutation", description='Create or update a vote on a message.\nUsers can upvote or downvote messages. Changing vote type updates the existing vote.\nUsers cannot vote on their own messages.')
class VoteMessageMutation:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["MessageType", strawberry.lazy("config.graphql_new.conversation_types")]] = strawberry.field(name="obj")


register_type("VoteMessageMutation", VoteMessageMutation, model=None)


@strawberry.type(name="RemoveVoteMutation", description="Remove user's vote from a message.")
class RemoveVoteMutation:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["MessageType", strawberry.lazy("config.graphql_new.conversation_types")]] = strawberry.field(name="obj")


register_type("RemoveVoteMutation", RemoveVoteMutation, model=None)


@strawberry.type(name="VoteConversationMutation", description='Create or update a vote on a conversation/thread.\nUsers can upvote or downvote threads. Changing vote type updates the existing vote.\nUsers cannot vote on their own threads.\n\nPermission: Users can vote on any conversation/thread they can see (visibility-based).')
class VoteConversationMutation:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["ConversationType", strawberry.lazy("config.graphql_new.conversation_types")]] = strawberry.field(name="obj")


register_type("VoteConversationMutation", VoteConversationMutation, model=None)


@strawberry.type(name="RemoveConversationVoteMutation", description="Remove user's vote from a conversation/thread.\n\nPermission: Users can remove their vote from any conversation they can see.")
class RemoveConversationVoteMutation:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["ConversationType", strawberry.lazy("config.graphql_new.conversation_types")]] = strawberry.field(name="obj")


register_type("RemoveConversationVoteMutation", RemoveConversationVoteMutation, model=None)


@strawberry.type(name="VoteCorpusMutation", description='Create or update a vote on a corpus.\n\nAuthenticated users vote with their account; the service blocks self-vote\n(creators cannot upvote their own corpuses, matching the Message /\nConversation contract). Anonymous viewers vote via their Django session\nkey — one vote per session per corpus. Anonymous voting on a non-public\ncorpus is rejected by the same IDOR-safe "not found or no permission"\nresponse as a malformed corpus id.')
class VoteCorpusMutation:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["CorpusType", strawberry.lazy("config.graphql_new.corpus_types")]] = strawberry.field(name="obj")


register_type("VoteCorpusMutation", VoteCorpusMutation, model=None)


@strawberry.type(name="RemoveCorpusVoteMutation", description="Remove the caller's vote on a corpus.\n\nSymmetric with :class:`VoteCorpusMutation` — works for both\nauthenticated users (creator-keyed) and anonymous viewers\n(session-keyed). Idempotent: removing a non-existent vote is a\nsuccessful no-op rather than an error.")
class RemoveCorpusVoteMutation:
    ok: Optional[bool] = strawberry.field(name="ok")
    @strawberry.field(name="message")
    def message(self, info: strawberry.Info) -> Optional[str]:
        return coerce_str(getattr(self, "message", None))
    obj: Optional[Annotated["CorpusType", strawberry.lazy("config.graphql_new.corpus_types")]] = strawberry.field(name="obj")


register_type("RemoveCorpusVoteMutation", RemoveCorpusVoteMutation, model=None)


def _mutate_VoteMessageMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:131

    Port of VoteMessageMutation.mutate
    """
    raise NotImplementedError("_mutate_VoteMessageMutation not yet ported — see manifest")


def m_vote_message(info: strawberry.Info, message_id: Annotated[str, strawberry.argument(name="messageId", description='ID of the message to vote on')] = strawberry.UNSET, vote_type: Annotated[str, strawberry.argument(name="voteType", description="Vote type: 'upvote' or 'downvote'")] = strawberry.UNSET) -> Optional["VoteMessageMutation"]:
    kwargs = strip_unset({"message_id": message_id, "vote_type": vote_type})
    return _mutate_VoteMessageMutation(VoteMessageMutation, None, info, **kwargs)


def _mutate_RemoveVoteMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:218

    Port of RemoveVoteMutation.mutate
    """
    raise NotImplementedError("_mutate_RemoveVoteMutation not yet ported — see manifest")


def m_remove_vote(info: strawberry.Info, message_id: Annotated[str, strawberry.argument(name="messageId", description='ID of the message to remove vote from')] = strawberry.UNSET) -> Optional["RemoveVoteMutation"]:
    kwargs = strip_unset({"message_id": message_id})
    return _mutate_RemoveVoteMutation(RemoveVoteMutation, None, info, **kwargs)


def _mutate_VoteConversationMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:280

    Port of VoteConversationMutation.mutate
    """
    raise NotImplementedError("_mutate_VoteConversationMutation not yet ported — see manifest")


def m_vote_conversation(info: strawberry.Info, conversation_id: Annotated[str, strawberry.argument(name="conversationId", description='ID of the conversation/thread to vote on')] = strawberry.UNSET, vote_type: Annotated[str, strawberry.argument(name="voteType", description="Vote type: 'upvote' or 'downvote'")] = strawberry.UNSET) -> Optional["VoteConversationMutation"]:
    kwargs = strip_unset({"conversation_id": conversation_id, "vote_type": vote_type})
    return _mutate_VoteConversationMutation(VoteConversationMutation, None, info, **kwargs)


def _mutate_RemoveConversationVoteMutation(payload_cls, root, info, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:374

    Port of RemoveConversationVoteMutation.mutate
    """
    raise NotImplementedError("_mutate_RemoveConversationVoteMutation not yet ported — see manifest")


def m_remove_conversation_vote(info: strawberry.Info, conversation_id: Annotated[str, strawberry.argument(name="conversationId", description='ID of the conversation/thread to remove vote from')] = strawberry.UNSET) -> Optional["RemoveConversationVoteMutation"]:
    kwargs = strip_unset({"conversation_id": conversation_id})
    return _mutate_RemoveConversationVoteMutation(RemoveConversationVoteMutation, None, info, **kwargs)


def _mutate_VoteCorpusMutation(payload_cls, root, info, **kwargs):
    """PORT: config/ratelimit/decorators.py:455

    Port of VoteCorpusMutation.mutate
    """
    raise NotImplementedError("_mutate_VoteCorpusMutation not yet ported — see manifest")


def m_vote_corpus(info: strawberry.Info, corpus_id: Annotated[str, strawberry.argument(name="corpusId", description='Relay global ID of the corpus to vote on')] = strawberry.UNSET, vote_type: Annotated[str, strawberry.argument(name="voteType", description="Vote type: 'upvote' or 'downvote'")] = strawberry.UNSET) -> Optional["VoteCorpusMutation"]:
    kwargs = strip_unset({"corpus_id": corpus_id, "vote_type": vote_type})
    return _mutate_VoteCorpusMutation(VoteCorpusMutation, None, info, **kwargs)


def _mutate_RemoveCorpusVoteMutation(payload_cls, root, info, **kwargs):
    """PORT: config/ratelimit/decorators.py:523

    Port of RemoveCorpusVoteMutation.mutate
    """
    raise NotImplementedError("_mutate_RemoveCorpusVoteMutation not yet ported — see manifest")


def m_remove_corpus_vote(info: strawberry.Info, corpus_id: Annotated[str, strawberry.argument(name="corpusId", description='Relay global ID of the corpus to remove the vote from')] = strawberry.UNSET) -> Optional["RemoveCorpusVoteMutation"]:
    kwargs = strip_unset({"corpus_id": corpus_id})
    return _mutate_RemoveCorpusVoteMutation(RemoveCorpusVoteMutation, None, info, **kwargs)



MUTATION_FIELDS = {
    "vote_message": strawberry.field(resolver=m_vote_message, name="voteMessage", description='Create or update a vote on a message.\nUsers can upvote or downvote messages. Changing vote type updates the existing vote.\nUsers cannot vote on their own messages.'),
    "remove_vote": strawberry.field(resolver=m_remove_vote, name="removeVote", description="Remove user's vote from a message."),
    "vote_conversation": strawberry.field(resolver=m_vote_conversation, name="voteConversation", description='Create or update a vote on a conversation/thread.\nUsers can upvote or downvote threads. Changing vote type updates the existing vote.\nUsers cannot vote on their own threads.\n\nPermission: Users can vote on any conversation/thread they can see (visibility-based).'),
    "remove_conversation_vote": strawberry.field(resolver=m_remove_conversation_vote, name="removeConversationVote", description="Remove user's vote from a conversation/thread.\n\nPermission: Users can remove their vote from any conversation they can see."),
    "vote_corpus": strawberry.field(resolver=m_vote_corpus, name="voteCorpus", description='Create or update a vote on a corpus.\n\nAuthenticated users vote with their account; the service blocks self-vote\n(creators cannot upvote their own corpuses, matching the Message /\nConversation contract). Anonymous viewers vote via their Django session\nkey — one vote per session per corpus. Anonymous voting on a non-public\ncorpus is rejected by the same IDOR-safe "not found or no permission"\nresponse as a malformed corpus id.'),
    "remove_corpus_vote": strawberry.field(resolver=m_remove_corpus_vote, name="removeCorpusVote", description="Remove the caller's vote on a corpus.\n\nSymmetric with :class:`VoteCorpusMutation` — works for both\nauthenticated users (creator-keyed) and anonymous viewers\n(session-keyed). Idempotent: removing a non-existent vote is a\nsuccessful no-op rather than an error."),
}
