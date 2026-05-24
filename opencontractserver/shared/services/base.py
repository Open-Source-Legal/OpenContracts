"""``BaseService`` — shared machinery for the OpenContracts service layer.

Every concrete service (``opencontractserver/*/services/*.py``) inherits
``BaseService``. It centralises the cross-cutting behaviour so per-model
services stay small and contain only model-specific fetch/mutate logic:

- IDOR-safe single-object lookup (``get_or_none``)
- permission-filtered queryset access (``filter_visible``)
- a uniform permission gate for write operations (``require_permission``)
- structured action logging (``log_action``)

Services are classmethod/staticmethod based — there is no per-call service
instance. Subclasses call ``cls.get_or_none(...)`` etc. directly.

Part of the Phase 1 service-layer foundation — see
docs/refactor_plans/2026-05-19-service-layer-centralization-design.md.
"""

from __future__ import annotations

import logging
from typing import Any

from opencontractserver.shared.services.conventions import get_for_user_or_none

logger = logging.getLogger(__name__)


class BaseService:
    """Base class for all service-layer services."""

    @staticmethod
    def get_or_none(
        model: Any,
        pk: Any,
        user: Any,
        permission: Any = None,
        *,
        request: Any = None,
    ) -> Any | None:
        """IDOR-safe single-object lookup.

        Thin delegate to ``conventions.get_for_user_or_none`` — see that
        function for the full contract. ``permission`` defaults to
        ``PermissionTypes.READ`` when omitted.
        """
        return get_for_user_or_none(model, pk, user, permission, request=request)

    @staticmethod
    def filter_visible(
        model: Any,
        user: Any,
        *,
        request: Any = None,
        **kwargs: Any,
    ) -> Any:
        """Return ``model`` rows visible to ``user`` (permission-filtered).

        Delegates to the model's ``visible_to_user`` manager method, which
        encodes the per-model READ visibility rules.

        ``request`` is accepted for API consistency with ``get_or_none`` /
        ``require_permission`` (every public service method takes an optional
        ``request`` so the request-scoped permission cache can be threaded).
        It is not yet forwarded — the ``visible_to_user`` manager API does not
        currently accept it — and will be threaded in once that API supports
        it.

        Extra ``**kwargs`` are passed straight through to the manager's
        ``visible_to_user`` call. This supports per-model performance knobs
        (e.g. ``Document.objects.visible_to_user(user, lightweight=True)``)
        without leaking the Tier-0 attribute name into ``config/graphql/``.
        """
        return model.objects.visible_to_user(user, **kwargs)

    @staticmethod
    def user_has(
        instance: Any,
        user: Any,
        permission: Any,
        *,
        request: Any = None,
    ) -> bool:
        """Return ``True`` iff ``user`` holds ``permission`` on ``instance``.

        Companion to ``require_permission`` — same delegation to the model
        manager's ``user_can``, but returns a plain ``bool`` for resolvers
        that need a yes/no without producing an error string. Use this when
        the answer feeds a UI-state field (e.g. ``can_edit_summary``,
        ``can_create_labels``) rather than gating a mutation.

        Resolvers and tools MUST NOT call ``Model.objects.user_can`` /
        ``obj.user_can`` directly — that is Tier-0 and forbidden in
        ``config/graphql/`` (see
        ``opencontractserver/tests/architecture/test_graphql_service_layer.py``).
        """
        manager = type(instance).objects
        return manager.user_can(user, instance, permission, request=request)

    @staticmethod
    def require_permission(
        instance: Any,
        user: Any,
        permission: Any,
        *,
        request: Any = None,
        error_message: str | None = None,
    ) -> str:
        """Return ``""`` when ``user`` holds ``permission`` on ``instance``.

        Otherwise return a human-readable denial string. Services use the
        return value directly as the ``error`` field of a
        ``ServiceResult``::

            error = cls.require_permission(corpus, user, PermissionTypes.UPDATE)
            if error:
                return ServiceResult.failure(error)

        ``error_message`` overrides the default denial string; it is
        ignored when the check passes.

        The model's manager MUST implement ``user_can`` (see
        ``conventions.get_for_user_or_none`` for the same contract).
        """
        manager = type(instance).objects
        if manager.user_can(user, instance, permission, request=request):
            return ""
        if error_message is not None:
            return error_message
        # ``permission`` is typically a PermissionTypes enum, but fall back to
        # its string form so a plain-string permission cannot raise here.
        action = getattr(permission, "value", permission)
        return f"Permission denied: cannot {action} this {type(instance).__name__}"

    @staticmethod
    def log_action(action: str, instance: Any, user: Any, **extra: Any) -> None:
        """Emit a structured who-did-what-to-which-object log line.

        Args:
            action: Verb describing the operation (e.g. ``"Created"``).
            instance: The affected model instance.
            user: The acting user.
            **extra: Additional ``key=value`` context appended to the line.
        """
        suffix = (
            " " + " ".join(f"{key}={value!r}" for key, value in extra.items())
            if extra
            else ""
        )
        logger.info(
            "%s %s(id=%s) by user=%s%s",
            action,
            type(instance).__name__,
            getattr(instance, "pk", None),
            getattr(user, "id", user),
            suffix,
        )
