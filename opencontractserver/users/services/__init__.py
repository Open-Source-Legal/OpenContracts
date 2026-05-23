"""Users service package.

Re-exports ``UserService`` so callers can
``from opencontractserver.users.services import UserService`` without
depending on the internal module layout.

Migrated from the retired ``users/query_optimizer.py`` as Phase 4 of the
service-layer centralization roadmap — see
docs/refactor_plans/2026-05-19-service-layer-centralization-design.md.
"""

from opencontractserver.users.services.user_service import RequestingUser, UserService

__all__ = ["RequestingUser", "UserService"]
