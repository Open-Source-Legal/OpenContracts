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
    def filter_visible(model: Any, user: Any) -> Any:
        """Return ``model`` rows visible to ``user`` (permission-filtered).

        Delegates to the model's ``visible_to_user`` manager method, which
        encodes the per-model READ visibility rules.
        """
        return model.objects.visible_to_user(user)
