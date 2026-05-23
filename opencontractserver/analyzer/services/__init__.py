"""Analyzer-app service package.

Re-exports the public services so callers import a stable path::

    from opencontractserver.analyzer.services import AnalysisService

Phase 3 of the service-layer centralization roadmap — see
``docs/refactor_plans/2026-05-19-service-layer-centralization-design.md``.
"""

from opencontractserver.analyzer.services.analysis_service import AnalysisService

__all__ = ["AnalysisService"]
