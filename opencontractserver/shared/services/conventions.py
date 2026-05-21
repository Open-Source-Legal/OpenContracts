"""Shared return-type conventions and IDOR-safe lookup for the service layer.

Every service in ``opencontractserver/*/services/`` returns results through
``ServiceResult`` (write operations) or permission-filtered querysets /
``None`` (read operations). This module is the single home for those
conventions so the service layer presents one uniform surface to GraphQL
resolvers, MCP tools, REST views, and Celery tasks.

Part of the Phase 1 service-layer foundation — see
docs/refactor_plans/2026-05-19-service-layer-centralization-design.md.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class ServiceResult(Generic[T]):
    """Uniform envelope returned by service-layer write operations.

    ``ok`` is derived: a result is successful exactly when ``error`` is
    empty. Construct via the ``success`` / ``failure`` classmethods rather
    than the bare constructor so intent is explicit at the call site.

    Tuple-unpacking is supported (``value, error = result``) so callers
    written against the legacy ``(obj, error)`` / ``(ok, error)``
    convention keep working while the service layer is migrated.
    """

    value: T | None = None
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error

    @classmethod
    def success(cls, value: T) -> ServiceResult[T]:
        return cls(value=value, error="")

    @classmethod
    def failure(cls, error: str) -> ServiceResult[Any]:
        # Returns ``ServiceResult[Any]`` rather than ``ServiceResult[T]``:
        # a failure carries no value, so the type parameter is genuinely
        # unbound at the call site.
        if not error:
            raise ValueError("ServiceResult.failure requires a non-empty error message")
        return cls(value=None, error=error)

    def __post_init__(self) -> None:
        # Guard the bare constructor against contradictory states. A failure
        # carries no value; a success carries no error. Callers should use
        # success() / failure(), but the frozen dataclass still exposes the
        # default constructor, so pin the invariant here.
        if self.value is not None and self.error:
            raise ValueError(
                "ServiceResult cannot carry both a value and an error; "
                "use ServiceResult.success() or ServiceResult.failure()"
            )

    def __iter__(self) -> Iterator[Any]:
        """Yield ``(value, error)`` for backward-compatible tuple unpacking."""
        yield self.value
        yield self.error


def get_for_user_or_none(
    model: Any,
    pk: Any,
    user: Any,
    permission: Any = None,
    *,
    request: Any = None,
) -> Any | None:
    """IDOR-safe single-object lookup.

    Returns the instance only when it exists AND ``user`` holds
    ``permission`` on it. Returns ``None`` for every other case —
    not-found, permission-denied, or a malformed ``pk`` — so callers
    cannot distinguish "does not exist" from "exists but forbidden"
    (the IDOR-prevention contract from CLAUDE.md).

    The model's manager MUST implement ``user_can`` — i.e. it extends
    ``BaseVisibilityManager`` / ``UserCanMixin`` or is built from
    ``PermissionedTreeQuerySet``. Models with a plain manager (e.g.
    ``Notification``, which uses a simple ownership model) are not
    supported here; gate those with their own ownership filter.

    Args:
        model: The Django model class to look up.
        pk: Primary key of the desired row.
        user: Requesting user (``User``, ``AnonymousUser``, id, or None).
        permission: Required ``PermissionTypes`` — defaults to ``READ``.
        request: Optional request object, threaded into ``user_can`` so
            the request-scoped permission cache is shared.

    Returns:
        The instance, or ``None``.
    """
    from opencontractserver.types.enums import PermissionTypes

    if permission is None:
        permission = PermissionTypes.READ

    try:
        if permission == PermissionTypes.READ:
            # Fast path for the high-frequency READ case: ``visible_to_user``
            # encodes exactly the READ visibility rule (the
            # ``visible_to_user ⟺ user_can(READ)`` invariant is pinned by
            # test_authorization_invariants), so a single filtered query
            # replaces the fetch-then-check round-trip below.
            return model.objects.visible_to_user(user).filter(pk=pk).first()
        instance = model.objects.get(pk=pk)
    except model.DoesNotExist:
        return None
    except (ValueError, TypeError, OverflowError):
        # Malformed pk — a GraphQL global id passed instead of a raw PK
        # (ValueError/TypeError), or a value too large for the PK column
        # (OverflowError). Treat as not-found rather than raising.
        return None

    if model.objects.user_can(user, instance, permission, request=request):
        return instance
    return None
