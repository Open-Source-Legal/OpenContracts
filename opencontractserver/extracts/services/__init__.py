"""Extracts-app service package.

Re-exports the public services so callers import a stable path::

    from opencontractserver.extracts.services import ExtractService, MetadataService

Phase 3 of the service-layer centralization roadmap — see
``docs/refactor_plans/2026-05-19-service-layer-centralization-design.md``.
"""

from opencontractserver.extracts.services.extract_service import ExtractService
from opencontractserver.extracts.services.metadata import MetadataService

__all__ = ["ExtractService", "MetadataService"]
