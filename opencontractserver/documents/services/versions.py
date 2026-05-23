"""Document version service — version-tree metadata queries.

Documents in the same ``version_tree_id`` represent successive content
versions of the same logical document (Rule C1). The
``DocumentType.versionCount`` GraphQL field surfaces the size of that
tree to the UI, so any list view that selects it would otherwise issue
one ``COUNT(*)`` per row — the classic N+1 storm.

``DocumentVersionService`` batches that work into a single aggregated
query per request, scoped to documents the user is allowed to read so
the badge cannot be used to enumerate hidden versions.

Migrated from ``documents/query_optimizer.py`` as Phase 4 of the
service-layer centralization roadmap — see
docs/refactor_plans/2026-05-19-service-layer-centralization-design.md.
"""

from typing import Any, Optional
from uuid import UUID

from django.db.models import Count

from opencontractserver.shared.services import BaseService


class DocumentVersionService(BaseService):
    """Permission-aware queries for document version metadata."""

    _VERSION_COUNTS_CACHE_KEY = "_doc_version_counts_by_tree"

    @classmethod
    def get_version_counts_by_tree(
        cls,
        user,
        *,
        request: Optional[Any] = None,
    ) -> dict[UUID, int]:
        """
        Return a mapping ``{version_tree_id: count}`` of visible documents per
        version tree, computed in a single aggregated SQL query.

        Replaces the per-document ``.count()`` pattern in
        ``resolve_version_count`` (config/graphql/document_types.py), which
        produced N+1 query storms when ``versionCount`` was selected on a
        paginated documents connection.

        The aggregation is scoped to ``Document.objects.visible_to_user(user)``
        so the badge cannot leak the existence of versions the user is not
        allowed to see.

        Args:
            user: The requesting user.
            request: Optional request object for request-level caching. When
                provided, the result is cached on the request keyed by user
                so repeated resolvers in the same request share the work.

        Returns:
            A plain ``dict`` keyed by ``version_tree_id`` (UUID) with visible
            document counts as values. Trees with no visible documents are
            absent from the dict; resolvers should fall back to a sensible
            default (typically 1, since the resolver is only called on a
            document the user can already see).
        """
        from opencontractserver.documents.models import Document

        cache_obj_key = f"{cls._VERSION_COUNTS_CACHE_KEY}_{getattr(user, 'id', None)}"
        if request is not None and hasattr(request, cache_obj_key):
            return getattr(request, cache_obj_key)

        rows = (
            Document.objects.visible_to_user(user)
            .values("version_tree_id")
            .annotate(c=Count("id"))
        )
        result: dict[UUID, int] = {r["version_tree_id"]: r["c"] for r in rows}

        if request is not None:
            setattr(request, cache_obj_key, result)
        return result
