"""Documents service package.

Re-exports the public document service classes so callers can
``from opencontractserver.documents.services import DocumentRelationshipService``
without depending on the internal module layout.

Each service inherits ``opencontractserver.shared.services.BaseService`` and
exposes permission-filtered ``get_*`` methods. Migrated from the retired
``documents/query_optimizer.py`` as Phase 4 of the service-layer
centralization roadmap — see
docs/refactor_plans/2026-05-19-service-layer-centralization-design.md.
"""

from opencontractserver.documents.services.actions import DocumentActionsService
from opencontractserver.documents.services.relationships import (
    DocumentRelationshipService,
)
from opencontractserver.documents.services.versions import DocumentVersionService

__all__ = [
    "DocumentActionsService",
    "DocumentRelationshipService",
    "DocumentVersionService",
]
