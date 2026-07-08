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

import datetime

import strawberry

from config.graphql._util import strip_unset
from config.graphql.core.relay import (
    register_type,
)
from opencontractserver.users.models import SystemStats


@strawberry.type(
    name="SystemStatsType",
    description="Install-wide aggregate metrics, materialised periodically.\n\nFields mirror :class:`opencontractserver.users.models.SystemStats`. All\ncounts are global, not permission-scoped.",
)
class SystemStatsType:
    user_count: int | None = strawberry.field(
        name="userCount", description="Active users.", default=None
    )
    document_count: int | None = strawberry.field(
        name="documentCount", description="Documents with an active path.", default=None
    )
    corpus_count: int | None = strawberry.field(
        name="corpusCount", description="Corpuses.", default=None
    )
    annotation_count: int | None = strawberry.field(
        name="annotationCount", description="Non-structural annotations.", default=None
    )
    conversation_count: int | None = strawberry.field(
        name="conversationCount", description="Non-deleted conversations.", default=None
    )
    message_count: int | None = strawberry.field(
        name="messageCount", description="Non-deleted chat messages.", default=None
    )
    computed_at: datetime.datetime | None = strawberry.field(
        name="computedAt",
        description="When the snapshot was last recomputed; null until first run.",
        default=None,
    )


register_type("SystemStatsType", SystemStatsType, model=None)


def _resolve_Query_system_stats(root, info, **kwargs):
    """PORT: /home/user/oc-graphene-ref/config/graphql/stats_queries.py:52

    Port of StatsQueryMixin.resolve_system_stats
    """
    # Singleton accessor — no permission scoping (global public
    # aggregates). Returns zeros until the first scheduled refresh runs.
    return SystemStats.get()


def q_system_stats(info: strawberry.Info) -> SystemStatsType | None:
    kwargs = strip_unset({})
    return _resolve_Query_system_stats(None, info, **kwargs)


QUERY_FIELDS = {
    "system_stats": strawberry.field(
        resolver=q_system_stats,
        name="systemStats",
        description="Materialised install-wide aggregate counts (refreshed periodically). Global, not permission-scoped — use a scoped connection's totalCount for per-user figures. NOTE: these aggregates are readable WITHOUT authentication (landing/dashboard use case); they expose total user/document/corpus/conversation/annotation counts to anonymous callers.",
    ),
}
