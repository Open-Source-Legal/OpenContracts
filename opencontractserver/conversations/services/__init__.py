"""Conversations service package.

Re-exports ``ConversationService`` so callers can
``from opencontractserver.conversations.services import ConversationService``
without depending on the internal module layout.

Migrated from the retired ``conversations/query_optimizer.py`` as Phase 4
of the service-layer centralization roadmap — see
docs/refactor_plans/2026-05-19-service-layer-centralization-design.md.
"""

from opencontractserver.conversations.services.conversation_service import (
    ConversationService,
)

__all__ = ["ConversationService"]
