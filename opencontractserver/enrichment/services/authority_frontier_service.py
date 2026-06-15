"""Manage the durable authority discovery queue (AuthorityFrontier).

Follows the repo-wide ``opencontractserver/<app>/services/`` convention:
user-context callers reach enrichment data through these services, never via
inline Tier-0 ORM fusions.
"""

from __future__ import annotations

from django.utils import timezone

from opencontractserver.annotations.models import AuthorityFrontier
from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.services.corpus_reference_service import (
    CorpusReferenceService,
)
from opencontractserver.shared.services.base import BaseService


class AuthorityFrontierService(BaseService):
    """Manage the durable authority discovery queue."""

    @classmethod
    def seed_from_wanted_authorities(cls, user, corpus_id: int | None = None) -> dict:
        """Upsert one AuthorityFrontier row per wanted section-root key.

        Reuses the exact aggregation users already see in the Wanted Authorities
        panel — so the queue can never diverge from the GraphQL surface.
        Idempotent: re-running refreshes mention_count / distinct_corpus_count /
        candidate_sources and leaves discovery_state untouched for in-flight rows.
        """
        wanted = CorpusReferenceService.wanted_authorities(user, corpus_id=corpus_id)
        created = updated = 0
        for auth in wanted:
            authority = auth["authority"]
            juris, atype = C.classify_prefix(authority)
            for key_entry in auth["top_keys"]:
                root = key_entry["canonical_key"]
                row, was_created = AuthorityFrontier.objects.get_or_create(
                    canonical_key=root,
                    defaults={
                        "authority": authority,
                        "jurisdiction": juris,
                        "authority_type": atype,
                    },
                )
                row.mention_count = key_entry["mention_count"]
                row.distinct_corpus_count = key_entry["corpus_count"]
                # jurisdiction/authority_type may have been unknown at create
                row.jurisdiction = row.jurisdiction or juris
                row.authority_type = row.authority_type or atype
                row.save(
                    update_fields=[
                        "mention_count",
                        "distinct_corpus_count",
                        "jurisdiction",
                        "authority_type",
                        "modified",
                    ]
                )
                created += int(was_created)
                updated += int(not was_created)
        return {"frontier_created": created, "frontier_updated": updated}

    @classmethod
    def dequeue_queued(
        cls,
        *,
        limit: int = 10,
        max_depth: int | None = None,
        min_demand: int = 0,
    ) -> list[AuthorityFrontier]:
        """Highest-demand queued rows regardless of assigned provider.

        Unlike ``dequeue_for_provider`` (which requires a stamped provider),
        this serves the crawl driver: it picks ``discovery_state="queued"`` rows
        ranked by ``-mention_count``, optionally bounded by depth and a minimum
        demand floor.  Provider selection happens later in the discovery service.
        """
        qs = AuthorityFrontier.objects.filter(discovery_state="queued")
        if max_depth is not None:
            qs = qs.filter(depth__lte=max_depth)
        if min_demand:
            qs = qs.filter(mention_count__gte=min_demand)
        return list(qs.order_by("-mention_count")[:limit])

    @classmethod
    def seed_child_keys(
        cls, parent: AuthorityFrontier, canonical_keys: list[str]
    ) -> dict:
        """Seed depth+1 frontier rows for an ingested authority's outbound cites.

        Each key is rolled to its section root via ``candidate_keys(key)[-1]``
        and upserted at ``parent.depth + 1``.  Idempotent: a key that already
        has a row at ANY depth/state is skipped — re-crawling never creates
        duplicates and never resets an in-flight row.
        """
        from opencontractserver.enrichment.authorities import candidate_keys

        created = skipped = 0
        child_depth = parent.depth + 1
        for raw in canonical_keys:
            root = candidate_keys(raw)[-1]
            authority = root.split(":", 1)[0]
            juris, atype = C.classify_prefix(authority)
            _, was_created = AuthorityFrontier.objects.get_or_create(
                canonical_key=root,
                defaults={
                    "authority": authority,
                    "jurisdiction": juris,
                    "authority_type": atype,
                    "depth": child_depth,
                    "mention_count": 1,
                    "discovery_state": "queued",
                },
            )
            created += int(was_created)
            skipped += int(not was_created)
        return {"child_created": created, "child_skipped": skipped}

    @classmethod
    def dequeue_for_provider(
        cls, provider: str, limit: int = 10
    ) -> list[AuthorityFrontier]:
        """Return up to ``limit`` queued rows assigned to ``provider``."""
        return list(
            AuthorityFrontier.objects.filter(
                provider=provider, discovery_state="queued"
            ).order_by("-mention_count")[:limit]
        )

    @classmethod
    def mark(
        cls,
        row: AuthorityFrontier,
        state: str,
        *,
        document_id: int | None = None,
        error: str | None = None,
        candidate_record: dict | None = None,
    ) -> None:
        """Transition ``row`` to ``state``, optionally recording a document or error.

        Args:
            row: The ``AuthorityFrontier`` instance to update.
            state: New ``discovery_state`` value.
            document_id: If provided, set ``ingested_document_id`` to this value.
            error: If provided, set ``last_error`` to this message.
            candidate_record: If provided, APPEND to ``candidate_sources`` (append-only
                audit trail — earlier attempts are never overwritten).
        """
        row.discovery_state = state
        row.last_attempt = timezone.now()
        if document_id is not None:
            row.ingested_document_id = document_id
        if error is not None:
            row.last_error = error
        update_fields = [
            "discovery_state",
            "last_attempt",
            "ingested_document",
            "last_error",
            "modified",
        ]
        if candidate_record is not None:
            # Append-only audit trail; never overwrite prior attempts.
            row.candidate_sources = list(row.candidate_sources or []) + [
                candidate_record
            ]
            update_fields.append("candidate_sources")
        row.save(update_fields=update_fields)
