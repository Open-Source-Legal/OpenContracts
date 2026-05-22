"""Annotation-app service package.

Re-exports the public services so callers import a stable path::

    from opencontractserver.annotations.services import AnnotationService

Phase 3 of the service-layer centralization roadmap — see
``docs/refactor_plans/2026-05-19-service-layer-centralization-design.md``.
"""

from opencontractserver.annotations.services.annotation_service import (
    AnnotationService,
)
from opencontractserver.annotations.services.relationship_service import (
    RelationshipService,
)

__all__ = ["AnnotationService", "RelationshipService"]
