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
from config.graphql._util import coerce_enum, coerce_str, strip_unset
from config.graphql import enums




@strawberry.type(name="SystemStatsType", description='Install-wide aggregate metrics, materialised periodically.\n\nFields mirror :class:`opencontractserver.users.models.SystemStats`. All\ncounts are global, not permission-scoped.')
class SystemStatsType:
    user_count: Optional[int] = strawberry.field(name="userCount", description='Active users.', default=None)
    document_count: Optional[int] = strawberry.field(name="documentCount", description='Documents with an active path.', default=None)
    corpus_count: Optional[int] = strawberry.field(name="corpusCount", description='Corpuses.', default=None)
    annotation_count: Optional[int] = strawberry.field(name="annotationCount", description='Non-structural annotations.', default=None)
    conversation_count: Optional[int] = strawberry.field(name="conversationCount", description='Non-deleted conversations.', default=None)
    message_count: Optional[int] = strawberry.field(name="messageCount", description='Non-deleted chat messages.', default=None)
    computed_at: Optional[datetime.datetime] = strawberry.field(name="computedAt", description='When the snapshot was last recomputed; null until first run.', default=None)


register_type("SystemStatsType", SystemStatsType, model=None)


def _resolve_Query_system_stats(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/stats_queries.py:52

    Port of StatsQueryMixin.resolve_system_stats
    """
    raise NotImplementedError("_resolve_Query_system_stats not yet ported — see manifest")


def q_system_stats(info: strawberry.Info) -> Optional["SystemStatsType"]:
    kwargs = strip_unset({})
    return _resolve_Query_system_stats(None, info, **kwargs)



QUERY_FIELDS = {
    "system_stats": strawberry.field(resolver=q_system_stats, name="systemStats", description="Materialised install-wide aggregate counts (refreshed periodically). Global, not permission-scoped — use a scoped connection's totalCount for per-user figures. NOTE: these aggregates are readable WITHOUT authentication (landing/dashboard use case); they expose total user/document/corpus/conversation/annotation counts to anonymous callers."),
}
