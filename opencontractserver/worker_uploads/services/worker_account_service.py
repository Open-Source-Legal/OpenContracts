"""``WorkerAccount`` service — superuser-gated worker-account lifecycle.

Worker accounts are service identities used by external document-processing
workers. Their creation / deactivation / reactivation flows are
**superuser-only**, and the listing surface exposes a different shape for
non-superusers (active accounts only, sensitive ``token_count`` zeroed).

Phase 5 of the service-layer centralization roadmap — see
``docs/refactor_plans/2026-05-19-service-layer-centralization-design.md``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from opencontractserver.shared.services.base import BaseService
from opencontractserver.shared.services.conventions import ServiceResult

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from opencontractserver.worker_uploads.models import WorkerAccount

logger = logging.getLogger(__name__)


class WorkerAccountService(BaseService):
    """Worker-account lifecycle (superuser-gated)."""

    @classmethod
    def list_visible_accounts(
        cls,
        user: Any,
        *,
        name_contains: str | None = None,
        is_active: bool | None = None,
        request: Any = None,
    ) -> QuerySet:
        """Return worker accounts visible to ``user``, annotated for the resolver.

        Intentionally accessible to all authenticated users so that corpus
        creators can populate the worker-account dropdown when creating
        access tokens. Non-superusers see only active accounts; the
        ``is_active`` filter is honoured only for superusers (matching the
        pre-relocation resolver behaviour).

        The queryset is annotated with ``_token_count`` so callers can
        cheaply build the projection type without an extra round-trip.
        Non-superuser callers should zero ``token_count`` themselves (the
        resolver does so).
        """
        from django.db.models import Count

        from opencontractserver.worker_uploads.models import WorkerAccount

        qs = WorkerAccount.objects.select_related("creator").order_by("-created")

        is_superuser = bool(getattr(user, "is_superuser", False))
        if not is_superuser:
            qs = qs.filter(is_active=True)
        else:
            if is_active is not None:
                qs = qs.filter(is_active=is_active)

        qs = qs.annotate(_token_count=Count("access_tokens"))

        if name_contains:
            qs = qs.filter(name__icontains=name_contains)

        return qs

    _SUPERUSER_ONLY_MSG = "Superuser privileges required."

    @classmethod
    def create_worker_account(
        cls,
        user: Any,
        *,
        name: str,
        description: str = "",
        request: Any = None,
    ) -> ServiceResult[WorkerAccount]:
        """Create a new worker account. **Superuser-only.**

        The superuser gate is enforced in-service (defence-in-depth) so
        internal callers (management commands, Celery tasks, future REST
        endpoints) cannot bypass it by skipping the ``user_passes_test``
        decorator on the GraphQL mutation. ``WorkerAccount.create_with_user``
        raises :class:`ValueError` on a duplicate name; the service surfaces
        that as a ``ServiceResult.failure`` so the caller can map it to a
        ``GraphQLError`` without unwrapping the exception twice.
        """
        from opencontractserver.worker_uploads.models import WorkerAccount

        if not getattr(user, "is_superuser", False):
            return ServiceResult.failure(cls._SUPERUSER_ONLY_MSG)

        try:
            account = WorkerAccount.create_with_user(
                name=name,
                description=description,
                creator=user,
            )
        except ValueError as exc:
            return ServiceResult.failure(str(exc))

        cls.log_action("Created", account, user)
        return ServiceResult.success(account)

    @classmethod
    def set_active(
        cls,
        user: Any,
        worker_account_id: Any,
        *,
        active: bool,
        request: Any = None,
    ) -> ServiceResult[WorkerAccount]:
        """Activate or deactivate a worker account by id. **Superuser-only.**

        The superuser gate is enforced in-service (defence-in-depth) — see
        :meth:`create_worker_account` for the rationale. Deactivating an
        account implicitly revokes all of its tokens (the
        :meth:`CorpusAccessToken.is_valid` check fails when the parent
        account is inactive). Returns a failure with a stable
        "Worker account not found." message when the id does not exist —
        matching the pre-relocation ``GraphQLError`` text.
        """
        from opencontractserver.worker_uploads.models import WorkerAccount

        if not getattr(user, "is_superuser", False):
            return ServiceResult.failure(cls._SUPERUSER_ONLY_MSG)

        try:
            account = WorkerAccount.objects.get(id=worker_account_id)
        except WorkerAccount.DoesNotExist:
            return ServiceResult.failure("Worker account not found.")

        account.is_active = active
        account.save(update_fields=["is_active"])
        cls.log_action("Activated" if active else "Deactivated", account, user)
        return ServiceResult.success(account)
