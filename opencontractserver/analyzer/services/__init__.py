"""Analyzer-app service package.

Re-exports the public services so callers import a stable path::

    from opencontractserver.analyzer.services import (
        AnalysisService,
        AnalysisLifecycleService,
    )

``AnalysisService`` (Phase 3) owns the read-side visibility queries;
``AnalysisLifecycleService`` (Phase 5) owns the lifecycle write surface —
``start_document_analysis``, ``make_public``, ``delete_analysis``. Both
inherit ``shared.services.BaseService``. See
``docs/refactor_plans/2026-05-19-service-layer-centralization-design.md``.
"""

from opencontractserver.analyzer.services.analysis_lifecycle_service import (
    AnalysisLifecycleService,
)
from opencontractserver.analyzer.services.analysis_service import AnalysisService

__all__ = ["AnalysisLifecycleService", "AnalysisService"]
