"""Service layer for corpus reference enrichment.

Follows the repo-wide ``opencontractserver/<app>/services/`` convention:
user-context callers (GraphQL resolvers, agent tools, Celery adapters) reach
enrichment data through these services, never via inline Tier-0 ORM fusions.
"""

from opencontractserver.enrichment.services.corpus_reference_service import (
    CorpusReferenceService,
)
from opencontractserver.enrichment.services.enrichment_service import EnrichmentService

__all__ = ["CorpusReferenceService", "EnrichmentService"]
