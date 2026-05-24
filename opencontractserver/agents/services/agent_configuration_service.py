"""``AgentConfiguration`` service — agent CRUD + visibility queries.

``AgentConfigurationService`` owns the agent-configuration surface that used
to live inline in ``config/graphql/agent_mutations.py`` and the agent
resolvers in ``config/graphql/social_queries.py``. Reads return
permission-filtered querysets; writes return :class:`ServiceResult` envelopes.

Phase 5 of the service-layer centralization roadmap — see
``docs/refactor_plans/2026-05-19-service-layer-centralization-design.md``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from opencontractserver.shared.services.base import BaseService
from opencontractserver.shared.services.conventions import ServiceResult
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from opencontractserver.agents.models import AgentConfiguration
    from opencontractserver.corpuses.models import Corpus

logger = logging.getLogger(__name__)


class AgentConfigurationService(BaseService):
    """Agent-configuration CRUD and visibility queries.

    Read access is encoded on the Tier-0 manager
    (``AgentConfiguration.objects.visible_to_user``); this service is the
    canonical entry point for resolvers, threading ``request`` into the
    permission cache and adding the standard ``select_related`` shape.
    """

    @classmethod
    def list_visible_agents(
        cls,
        user: Any,
        *,
        request: Any = None,
    ) -> QuerySet:
        """Return agents visible to ``user`` with the standard prefetch shape.

        ``request`` is accepted for service-layer API consistency; the
        ``visible_to_user`` manager does not yet thread it.
        """
        from opencontractserver.agents.models import AgentConfiguration

        return AgentConfiguration.objects.visible_to_user(user).select_related(
            "creator", "corpus"
        )

    @classmethod
    def search_mentionable_agents(
        cls,
        user: Any,
        *,
        text_search: str | None = None,
        corpus_id: int | None = None,
        request: Any = None,
    ) -> QuerySet:
        """Return active agents the user may @-mention, narrowed by filters.

        Anonymous users get an empty queryset (anonymous callers cannot
        mention agents). When ``corpus_id`` is provided, results are
        restricted to GLOBAL agents plus that corpus's agents; ``text_search``
        does an icontains match on name / description / slug.
        """
        from django.db.models import Q

        from opencontractserver.agents.models import AgentConfiguration

        if not user or not getattr(user, "is_authenticated", False):
            return AgentConfiguration.objects.none()

        qs = AgentConfiguration.objects.visible_to_user(user).filter(is_active=True)

        if corpus_id is not None:
            qs = qs.filter(
                Q(scope=AgentConfiguration.SCOPE_GLOBAL)
                | Q(scope=AgentConfiguration.SCOPE_CORPUS, corpus_id=corpus_id)
            )

        if text_search:
            qs = qs.filter(
                Q(name__icontains=text_search)
                | Q(description__icontains=text_search)
                | Q(slug__icontains=text_search)
            )

        return qs

    @classmethod
    def get_active_agents_by_slugs(
        cls,
        user: Any,
        slugs: list[str],
        *,
        request: Any = None,
    ) -> QuerySet:
        """Return the active agents (visible to ``user``) whose slug is in ``slugs``.

        Used by the mention-resolution batch lookup in
        ``config/graphql/conversation_types.py``. Threads ``select_related("corpus")``
        for the resolver's per-row corpus access.
        """
        from opencontractserver.agents.models import AgentConfiguration

        if not slugs:
            return AgentConfiguration.objects.none()

        return (
            AgentConfiguration.objects.visible_to_user(user)
            .filter(slug__in=slugs, is_active=True)
            .select_related("corpus")
        )

    @classmethod
    def get_agent_by_id(
        cls,
        user: Any,
        agent_pk: Any,
        *,
        request: Any = None,
    ) -> AgentConfiguration | None:
        """IDOR-safe single-agent lookup.

        Returns the agent only when it is visible to ``user``; returns
        ``None`` for both not-found and not-permitted so callers cannot
        distinguish the two branches.
        """
        from opencontractserver.agents.models import AgentConfiguration

        return cls.get_or_none(AgentConfiguration, agent_pk, user, request=request)

    @classmethod
    def create_agent(
        cls,
        user: Any,
        *,
        name: str,
        description: str,
        system_instructions: str,
        scope: str,
        slug: str | None = None,
        available_tools: list[str] | None = None,
        permission_required_tools: list[str] | None = None,
        badge_config: dict[str, Any] | None = None,
        avatar_url: str | None = None,
        corpus: Corpus | None = None,
        is_public: bool = True,
        request: Any = None,
    ) -> ServiceResult[AgentConfiguration]:
        """Create a new agent configuration.

        Authorisation:
        - ``CORPUS`` scope: requires ``corpus`` and CRUD permission on it.
        - ``GLOBAL`` scope: superuser only.

        The corpus's READ/CRUD pre-checks are the caller's responsibility
        when the corpus is fetched via global-id decoding; this method
        enforces the corpus CRUD gate redundantly so an internal caller is
        also safe. Returns a ``ServiceResult`` whose value is the created
        agent on success.
        """
        from opencontractserver.agents.models import AgentConfiguration

        if scope not in ("GLOBAL", "CORPUS"):
            return ServiceResult.failure("Scope must be GLOBAL or CORPUS.")

        if scope == "CORPUS":
            if corpus is None:
                return ServiceResult.failure(
                    "corpus_id is required for CORPUS scope agents."
                )
            # Defence in depth: re-check CRUD on the corpus.
            if not corpus.user_can(user, PermissionTypes.CRUD, request=request):
                return ServiceResult.failure("Corpus not found")
        else:  # GLOBAL
            # Superuser gate first — surfacing the canonical "must be
            # superuser" message before any shape complaint so a non-superuser
            # passing both ``scope=GLOBAL`` and ``corpus_id`` learns they
            # can't create GLOBAL agents at all (rather than being told the
            # corpus argument is invalid for a scope they can't use anyway).
            if not getattr(user, "is_superuser", False):
                return ServiceResult.failure(
                    "You must be a superuser to create global agents."
                )
            if corpus is not None:
                return ServiceResult.failure(
                    "corpus_id must not be provided for GLOBAL scope agents."
                )

        agent = AgentConfiguration.objects.create(
            name=name,
            slug=slug or "",  # empty triggers auto-generation in ``save()``
            description=description,
            system_instructions=system_instructions,
            available_tools=available_tools or [],
            permission_required_tools=permission_required_tools or [],
            badge_config=badge_config or {},
            avatar_url=avatar_url,
            scope=scope,
            corpus=corpus,
            creator=user,
            is_public=is_public,
            is_active=True,
        )

        set_permissions_for_obj_to_user(
            user, agent, [PermissionTypes.CRUD], is_new=True, request=request
        )
        cls.log_action("Created", agent, user)
        return ServiceResult.success(agent)

    @classmethod
    def update_agent(
        cls,
        user: Any,
        agent: AgentConfiguration,
        *,
        name: str | None = None,
        slug: str | None = None,
        description: str | None = None,
        system_instructions: str | None = None,
        available_tools: list[str] | None = None,
        permission_required_tools: list[str] | None = None,
        badge_config: dict[str, Any] | None = None,
        avatar_url: str | None = None,
        is_active: bool | None = None,
        is_public: bool | None = None,
        request: Any = None,
    ) -> ServiceResult[AgentConfiguration]:
        """Update an agent configuration after CRUD-permission verification.

        Returns the unified IDOR-safe failure message when the caller lacks
        permission so the GraphQL response cannot distinguish "not found"
        from "exists but forbidden". Callers MUST have already gated READ
        (the wrapper does so via :func:`get_agent_by_id`).
        """
        error = cls.require_permission(
            agent,
            user,
            PermissionTypes.CRUD,
            request=request,
            error_message="Agent configuration not found",
        )
        if error:
            return ServiceResult.failure(error)

        if name is not None:
            agent.name = name
        if slug is not None:
            agent.slug = slug
        if description is not None:
            agent.description = description
        if system_instructions is not None:
            agent.system_instructions = system_instructions
        if available_tools is not None:
            agent.available_tools = available_tools
        if permission_required_tools is not None:
            agent.permission_required_tools = permission_required_tools
        if badge_config is not None:
            agent.badge_config = badge_config
        if avatar_url is not None:
            agent.avatar_url = avatar_url
        if is_active is not None:
            agent.is_active = is_active
        if is_public is not None:
            agent.is_public = is_public

        agent.save()
        cls.log_action("Updated", agent, user)
        return ServiceResult.success(agent)

    @classmethod
    def delete_agent(
        cls,
        user: Any,
        agent: AgentConfiguration,
        *,
        request: Any = None,
    ) -> ServiceResult[None]:
        """Delete an agent configuration after CRUD-permission verification.

        Callers MUST have already gated READ. Returns the unified IDOR-safe
        failure message on permission denial so the GraphQL response cannot
        distinguish "not found" from "exists but forbidden".
        """
        error = cls.require_permission(
            agent,
            user,
            PermissionTypes.CRUD,
            request=request,
            error_message="Agent configuration not found",
        )
        if error:
            return ServiceResult.failure(error)

        agent.delete()
        cls.log_action("Deleted", agent, user)
        return ServiceResult.success(None)
