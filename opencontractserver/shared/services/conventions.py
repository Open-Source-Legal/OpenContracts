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
    def success(cls, value: T) -> "ServiceResult[T]":
        return cls(value=value, error="")

    @classmethod
    def failure(cls, error: str) -> "ServiceResult[T]":
        if not error:
            raise ValueError(
                "ServiceResult.failure requires a non-empty error message"
            )
        return cls(value=None, error=error)

    def __iter__(self) -> Iterator[Any]:
        """Yield ``(value, error)`` for backward-compatible tuple unpacking."""
        yield self.value
        yield self.error
