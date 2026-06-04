"""GraphQL query mixin exposing the materialised :class:`SystemStats` snapshot.

Headline surfaces (dashboards, landing tiles) read these pre-computed,
install-wide counts in a single indexed PK lookup instead of triggering
full-table ``COUNT``s on every page load (issue #1908). The snapshot is
refreshed on a schedule by
``opencontractserver.tasks.stats_tasks.refresh_system_stats``.

These counts are GLOBAL (not permission-scoped), so the field is readable by
anonymous visitors — there is nothing user-specific to leak. For a per-user
"what can I see" total, use the relevant scoped connection's ``totalCount``.
"""

import graphene

from opencontractserver.users.models import SystemStats


class SystemStatsType(graphene.ObjectType):
    """Install-wide aggregate metrics, materialised periodically.

    Fields mirror :class:`opencontractserver.users.models.SystemStats`. All
    counts are global, not permission-scoped.
    """

    user_count = graphene.Int(description="Active users.")
    document_count = graphene.Int(description="Documents with an active path.")
    corpus_count = graphene.Int(description="Corpuses.")
    annotation_count = graphene.Int(description="Non-structural annotations.")
    conversation_count = graphene.Int(description="Non-deleted conversations.")
    message_count = graphene.Int(description="Non-deleted chat messages.")
    computed_at = graphene.DateTime(
        description="When the snapshot was last recomputed; null until first run."
    )


class StatsQueryMixin:
    """Query field for the materialised system statistics snapshot."""

    system_stats = graphene.Field(
        SystemStatsType,
        description=(
            "Materialised install-wide aggregate counts (refreshed "
            "periodically). Global, not permission-scoped — use a scoped "
            "connection's totalCount for per-user figures. NOTE: these "
            "aggregates are readable WITHOUT authentication (landing/dashboard "
            "use case); they expose total user/document/corpus/conversation/"
            "annotation counts to anonymous callers."
        ),
    )

    def resolve_system_stats(self, info, **kwargs) -> SystemStats:
        # Singleton accessor — no permission scoping (global public
        # aggregates). Returns zeros until the first scheduled refresh runs.
        return SystemStats.get()
