"""Feedback service-layer package.

Re-exports the public service so callers import a stable path::

    from opencontractserver.feedback.services import UserFeedbackService

Phase 5 of the service-layer centralization roadmap — see
``docs/refactor_plans/2026-05-19-service-layer-centralization-design.md``.
"""

from opencontractserver.feedback.services.user_feedback_service import (
    UserFeedbackService,
)

__all__ = ["UserFeedbackService"]
