"""``AgentActionResult`` service — visibility queries for agent action results.

Migrates the inline filtering composition from
``config/graphql/action_queries.py`` (``resolve_agent_action_results``) onto a
classmethod-based service that threads ``request`` for Tier-2 permission
caching.

Phase 5 of the service-layer centralization roadmap — see
``docs/refactor_plans/2026-05-19-service-layer-centralization-design.md``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from opencontractserver.shared.services.base import BaseService

if TYPE_CHECKING:
    from django.db.models import QuerySet


class AgentActionResultService(BaseService):
    """Visibility-aware ``AgentActionResult`` queries.

    Visibility derives from corpus permissions: a user can see results for
    corpus actions whose corpus is visible to them. This service is the
    canonical entry point for the resolver — it composes the per-corpus
    defense-in-depth check and threads ``request`` for the permission cache.
    """

    @classmethod
    def list_visible_results(
        cls,
        user: Any,
        *,
        corpus_action_id: int | None = None,
        document_id: int | None = None,
        status: str | None = None,
        request: Any = None,
    ) -> QuerySet:
        """Return agent action results visible to ``user``, optionally filtered.

        Supports filtering by ``corpus_action_id`` (with a defence-in-depth
        check that ``user`` can see the parent corpus action),
        ``document_id``, and ``status``.

        Returns a queryset ordered by ``-created``. If a ``corpus_action_id``
        is supplied but the caller lacks visibility, an empty queryset is
        returned (not an error) to match the pre-relocation resolver
        behaviour.
        """
        from opencontractserver.agents.models import AgentActionResult
        from opencontractserver.corpuses.models import CorpusAction

        qs = AgentActionResult.objects.visible_to_user(user)

        if corpus_action_id is not None:
            # Defence-in-depth: verify the user can see the parent corpus
            # action before exposing its child results.
            if (
                not CorpusAction.objects.visible_to_user(user)
                .filter(pk=corpus_action_id)
                .exists()
            ):
                return qs.none()
            qs = qs.filter(corpus_action_id=corpus_action_id)

        if document_id is not None:
            qs = qs.filter(document_id=document_id)

        if status:
            qs = qs.filter(status=status)

        return qs.order_by("-created")
