"""``CorpusGroup`` service — group CRUD + call-time corpus resolution.

``CorpusGroupService`` is the canonical entry point for every user-context
surface that touches corpus groups (GraphQL resolvers/mutations and the
``search_across_corpora`` agent tool). Reads return permission-filtered
querysets / ``None``; writes return :class:`ServiceResult` envelopes.

The load-bearing method is :meth:`get_group_corpora_visible_to_user`: it
resolves a group's ``corpora`` M2M at *call time* and intersects it with
``Corpus.objects.visible_to_user`` so membership changes are visible on the
very next query and a group member the caller cannot READ is never searched
(issue #2056).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.db import IntegrityError, transaction
from django.db.models import Q

from opencontractserver.shared.services.base import BaseService
from opencontractserver.shared.services.conventions import ServiceResult
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from opencontractserver.corpuses.models import Corpus, CorpusGroup

logger = logging.getLogger(__name__)

# Unified IDOR-safe message: callers cannot distinguish "does not exist"
# from "exists but forbidden".
GROUP_NOT_FOUND_MESSAGE = "Corpus group not found"


class CorpusGroupService(BaseService):
    """Corpus-group CRUD and call-time member-corpus resolution."""

    @classmethod
    def list_visible_groups(cls, user: Any, *, request: Any = None) -> QuerySet:
        """Return corpus groups visible to ``user`` with the standard prefetch shape."""
        from opencontractserver.corpuses.models import CorpusGroup

        return CorpusGroup.objects.visible_to_user(user).select_related(
            "creator", "default_agent"
        )

    @classmethod
    def get_group_by_id(
        cls, user: Any, group_pk: Any, *, request: Any = None
    ) -> CorpusGroup | None:
        """IDOR-safe single-group lookup by primary key."""
        from opencontractserver.corpuses.models import CorpusGroup

        return cls.get_or_none(CorpusGroup, group_pk, user, request=request)

    @classmethod
    def get_group_by_ref(
        cls, user: Any, group_ref: int | str, *, request: Any = None
    ) -> CorpusGroup | None:
        """IDOR-safe group lookup by primary key or slug.

        Accepts an int / all-digit string (matched against pk OR slug, pk
        winning on the vanishingly-rare all-digit slug collision) or a slug
        string. Returns ``None`` uniformly for not-found and not-visible.
        """
        from opencontractserver.corpuses.models import CorpusGroup

        visible = CorpusGroup.objects.visible_to_user(user)
        ref_str = str(group_ref).strip()
        if not ref_str:
            return None
        if ref_str.isdigit():
            return (
                visible.filter(Q(pk=int(ref_str)) | Q(slug=ref_str))
                .order_by("pk")
                .first()
            )
        return visible.filter(slug=ref_str).first()

    @classmethod
    def get_group_corpora_visible_to_user(
        cls, user: Any, group: CorpusGroup, *, request: Any = None
    ) -> QuerySet[Corpus]:
        """Resolve the group's corpora the user can READ, at call time.

        This is the ``MIN(corpus_permission, group_membership)`` gate for
        cross-corpus retrieval: the M2M is re-read on every call (never a
        config-time snapshot) and intersected with per-user corpus
        visibility, so a private corpus inside a shared group stays hidden
        from users who lack corpus-level READ.
        """
        from opencontractserver.corpuses.models import Corpus

        return Corpus.objects.visible_to_user(user).filter(corpus_groups=group)

    # ------------------------------------------------------------------ #
    # Writes                                                             #
    # ------------------------------------------------------------------ #

    @classmethod
    def _resolve_member_corpora(
        cls, user: Any, corpus_pks: list[Any], *, request: Any = None
    ) -> ServiceResult[list[Corpus]]:
        """Resolve ``corpus_pks`` to corpora the user can READ.

        Fails with a uniform message listing the pks that are missing OR
        forbidden (indistinguishable by design) so a caller cannot probe
        for the existence of corpora they cannot see.
        """
        from opencontractserver.corpuses.models import Corpus

        if not corpus_pks:
            return ServiceResult.success([])

        # A non-numeric pk (e.g. a well-formed global id that decoded to a
        # garbage string) can never match a Corpus row — coerce up front so
        # the queryset never raises a raw int-coercion ValueError; the bad
        # value falls through to the uniform "not found" set below instead.
        numeric_pks: list[int] = []
        for pk in corpus_pks:
            try:
                numeric_pks.append(int(pk))
            except (TypeError, ValueError):
                continue

        corpora = (
            list(Corpus.objects.visible_to_user(user).filter(pk__in=numeric_pks))
            if numeric_pks
            else []
        )
        missing = {str(pk) for pk in corpus_pks} - {str(c.pk) for c in corpora}
        if missing:
            return ServiceResult.failure(
                f"Corpora not found: {', '.join(sorted(missing))}"
            )
        return ServiceResult.success(corpora)

    @classmethod
    def _resolve_default_agent(
        cls, user: Any, default_agent_pk: Any, *, request: Any = None
    ) -> ServiceResult[Any]:
        """Resolve a default-agent pk to an agent visible to ``user``."""
        from opencontractserver.agents.models import AgentConfiguration

        agent = cls.get_or_none(
            AgentConfiguration, default_agent_pk, user, request=request
        )
        if agent is None:
            return ServiceResult.failure("Agent configuration not found")
        return ServiceResult.success(agent)

    @classmethod
    def create_group(
        cls,
        user: Any,
        *,
        title: str,
        description: str = "",
        slug: str | None = None,
        corpus_pks: list[Any] | None = None,
        default_agent_pk: Any = None,
        is_public: bool = False,
        request: Any = None,
    ) -> ServiceResult[CorpusGroup]:
        """Create a corpus group owned by ``user``.

        Every corpus in ``corpus_pks`` must be READ-visible to the caller;
        ``default_agent_pk`` (when given) must resolve to a visible
        ``AgentConfiguration``. Grants the creator CRUD object permissions.
        """
        from opencontractserver.corpuses.models import CorpusGroup

        if not user or not getattr(user, "is_authenticated", False):
            return ServiceResult.failure(
                "You must be logged in to create a corpus group."
            )
        if not title or not title.strip():
            return ServiceResult.failure("Title is required.")

        corpora_result = cls._resolve_member_corpora(
            user, corpus_pks or [], request=request
        )
        if not corpora_result.ok:
            return ServiceResult.failure(corpora_result.error)

        default_agent = None
        if default_agent_pk is not None:
            agent_result = cls._resolve_default_agent(
                user, default_agent_pk, request=request
            )
            if not agent_result.ok:
                return agent_result
            default_agent = agent_result.value

        # Outer ``atomic()`` makes the row + M2M + permission writes
        # all-or-nothing; the inner savepoint scopes the slug-collision
        # IntegrityError so catching it doesn't poison a caller's enclosing
        # transaction (e.g. TestCase blocks / atomic GraphQL requests).
        with transaction.atomic():
            try:
                with transaction.atomic():
                    group = CorpusGroup.objects.create(
                        title=title.strip(),
                        # empty slug triggers auto-generation in ``save()``
                        slug=slug or "",
                        description=description or "",
                        default_agent=default_agent,
                        creator=user,
                        is_public=is_public,
                    )
            except IntegrityError:
                # The unique ``slug`` column is the model's only unique
                # constraint, so an IntegrityError here means the caller's
                # explicit slug collided (auto-generated slugs are
                # de-duplicated in ``save()``). Surface a friendly message
                # instead of a raw DB constraint error.
                return ServiceResult.failure(
                    "A corpus group with this slug already exists."
                )
            if corpora_result.value:
                group.corpora.set(corpora_result.value)

            set_permissions_for_obj_to_user(
                user, group, [PermissionTypes.CRUD], is_new=True, request=request
            )
        cls.log_action("Created", group, user)
        return ServiceResult.success(group)

    @classmethod
    def update_group(
        cls,
        user: Any,
        group: CorpusGroup,
        *,
        title: str | None = None,
        slug: str | None = None,
        description: str | None = None,
        corpus_pks: list[Any] | None = None,
        default_agent_pk: Any = None,
        clear_default_agent: bool = False,
        is_public: bool | None = None,
        request: Any = None,
    ) -> ServiceResult[CorpusGroup]:
        """Update a corpus group after CRUD-permission verification.

        ``corpus_pks`` (when given) replaces the caller-*visible* slice of
        the membership: every submitted corpus must be READ-visible to the
        caller, and members the caller cannot READ are preserved untouched
        (see the asymmetry comment at the ``corpora.set`` call below).
        ``default_agent_pk=None`` means "no change";
        ``clear_default_agent=True`` explicitly unbinds the agent (mirrors
        the ``clear_preferred_llm`` convention in
        ``AgentConfigurationService.update_agent``).
        """
        error = cls.require_permission(
            group,
            user,
            PermissionTypes.CRUD,
            request=request,
            error_message=GROUP_NOT_FOUND_MESSAGE,
        )
        if error:
            return ServiceResult.failure(error)

        corpora_result: ServiceResult[list[Corpus]] | None = None
        if corpus_pks is not None:
            corpora_result = cls._resolve_member_corpora(
                user, corpus_pks, request=request
            )
            if not corpora_result.ok:
                return ServiceResult.failure(corpora_result.error)

        if clear_default_agent:
            group.default_agent = None
        elif default_agent_pk is not None:
            agent_result = cls._resolve_default_agent(
                user, default_agent_pk, request=request
            )
            if not agent_result.ok:
                return agent_result
            group.default_agent = agent_result.value

        if title is not None:
            group.title = title
        if slug is not None:
            group.slug = slug
        if description is not None:
            group.description = description
        if is_public is not None:
            group.is_public = is_public

        # Outer ``atomic()`` keeps the field update + membership replace
        # all-or-nothing; inner savepoint scopes the slug-collision catch
        # (see the matching structure in ``create_group``).
        with transaction.atomic():
            try:
                with transaction.atomic():
                    group.save()
            except IntegrityError:
                # The unique slug is the model's only unique constraint.
                return ServiceResult.failure(
                    "A corpus group with this slug already exists."
                )
            if corpora_result is not None:
                # Membership replacement is deliberately ASYMMETRIC: it
                # replaces only the slice of the membership the caller can
                # READ, and preserves the rest.
                #
                # Why: ``CorpusGroupType.corpora`` is per-viewer filtered by
                # ``get_group_corpora_visible_to_user`` (the MIN(group READ,
                # corpus READ) gate), so an edit form can only ever seed the
                # members the caller can currently READ. If a member later
                # becomes invisible to them — e.g. its owner flips it private
                # — a wholesale ``set(submitted)`` would silently destroy that
                # membership on any unrelated edit (a title-only save). The
                # caller cannot see the member, no field exposes the true
                # membership count, and the M2M row is unrecoverable: silent,
                # undetectable data loss caused purely by a visibility filter.
                #
                # The converse guarantee is untouched: ``_resolve_member_corpora``
                # still requires every SUBMITTED corpus to be READ-visible, so a
                # caller cannot smuggle an unreadable corpus IN. Net rule — you
                # may add or remove only what you can see. Removing a visible
                # member therefore still works normally.
                visible_member_pks = list(
                    cls.get_group_corpora_visible_to_user(
                        user, group, request=request
                    ).values_list("pk", flat=True)
                )
                # Exactly the members the caller cannot see, hence must not be
                # able to destroy. Disjoint from the submitted set by
                # construction (submitted is enforced-readable).
                preserved = list(group.corpora.exclude(pk__in=visible_member_pks))
                group.corpora.set(preserved + (corpora_result.value or []))
        cls.log_action("Updated", group, user)
        return ServiceResult.success(group)

    @classmethod
    def delete_group(
        cls, user: Any, group: CorpusGroup, *, request: Any = None
    ) -> ServiceResult[None]:
        """Delete a corpus group after CRUD-permission verification."""
        error = cls.require_permission(
            group,
            user,
            PermissionTypes.CRUD,
            request=request,
            error_message=GROUP_NOT_FOUND_MESSAGE,
        )
        if error:
            return ServiceResult.failure(error)

        group.delete()
        cls.log_action("Deleted", group, user)
        return ServiceResult.success(None)
