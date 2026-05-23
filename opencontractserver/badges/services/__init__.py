"""Badges service package.

Re-exports ``BadgeService`` so callers can
``from opencontractserver.badges.services import BadgeService`` without
depending on the internal module layout.

Migrated from the retired ``badges/query_optimizer.py`` as Phase 4 of the
service-layer centralization roadmap — see
docs/refactor_plans/2026-05-19-service-layer-centralization-design.md.
"""

from opencontractserver.badges.services.badge_service import BadgeService

__all__ = ["BadgeService"]
