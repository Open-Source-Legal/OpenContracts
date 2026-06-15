"""Orchestrates authority discovery: registry -> provider -> bootstrap -> relink.

``AuthorityDiscoveryService`` is the single entry point for the automated
discovery pipeline.  Given an ``AuthorityFrontier`` row it:

1. Finds a public-domain provider that ``can_handle`` the row's key.
2. Calls the provider's ``locate`` + ``fetch`` to retrieve section text.
3. Delegates to ``bootstrap_authority_corpus`` for idempotent materialisation.
4. Triggers a cross-corpus relink that upgrades act-section EXTERNAL
   references (e.g. ``exchange-act:10(b)``) to RESOLVED once the USC
   document lands — the equivalence relink seam.
5. Marks the frontier row ``ingested`` (or ``failed`` / ``unsupported``).
"""

from __future__ import annotations

import logging

from django.db.models import Q

from opencontractserver.annotations.models import AuthorityFrontier
from opencontractserver.shared.services.base import BaseService

logger = logging.getLogger(__name__)


class AuthorityDiscoveryService(BaseService):
    """Registry-driven authority ingestion orchestrator."""

    @classmethod
    def _provider_for(cls, canonical_key: str):
        """Return the first public-domain provider that can handle *canonical_key*.

        Iterates the registry and instantiates each provider to call
        ``can_handle``.  Returns a ``(name, provider_instance)`` tuple on
        success, or ``(None, None)`` when no provider matches.
        """
        from opencontractserver.pipeline.registry import (
            get_all_authority_source_providers_cached,
        )

        for defn in get_all_authority_source_providers_cached():
            if defn.component_class is None:
                continue
            provider = defn.component_class()
            if (
                provider.can_handle(canonical_key)
                and provider.license == "public-domain"
            ):
                return defn.name, provider
        return None, None

    @classmethod
    def discover_and_bootstrap(
        cls,
        *,
        creator_id: int,
        frontier_row: AuthorityFrontier,
        make_public: bool = True,
        relink_async: bool = False,
    ) -> dict:
        """Ingest the authority described by *frontier_row*.

        Selects a provider, fetches section text, bootstraps the authority
        corpus, triggers a cross-namespace relink (so act-section citations
        that map to ingested USC keys upgrade from EXTERNAL to RESOLVED),
        and updates *frontier_row*'s discovery state.

        Args:
            creator_id: PK of the user who owns the resulting corpus.
            frontier_row: The ``AuthorityFrontier`` row being processed.
            make_public: Publish the resulting corpus (default True) so all
                users benefit from the authority resolution.
            relink_async: Queue the relink as a Celery task instead of
                running it inline (use for large authority sets).

        Returns:
            A dict with at least a ``"status"`` key (``"ingested"``,
            ``"unsupported"``, or ``"failed"``).
        """
        import xml.etree.ElementTree as ET
        import zipfile

        import requests

        from opencontractserver.annotations.models import AuthorityKeyEquivalence
        from opencontractserver.enrichment.authorities import bootstrap_authority_corpus
        from opencontractserver.enrichment.services.authority_frontier_service import (
            AuthorityFrontierService,
        )
        from opencontractserver.enrichment.services.enrichment_service import (
            EnrichmentService,
        )

        canonical_key = frontier_row.canonical_key
        name, provider = cls._provider_for(canonical_key)

        if provider is None:
            AuthorityFrontierService.mark(frontier_row, "unsupported")
            return {"status": "unsupported", "canonical_key": canonical_key}

        # Record which provider was selected and mark in-flight.
        frontier_row.provider = name
        frontier_row.save(update_fields=["provider", "modified"])
        AuthorityFrontierService.mark(frontier_row, "in_progress")

        # --- fetch -----------------------------------------------------------
        try:
            request = provider.locate(canonical_key)
            sections = provider.fetch(request)
        except (
            requests.RequestException,
            OSError,
            ValueError,
            KeyError,
            ET.ParseError,
            zipfile.BadZipFile,
        ) as exc:
            logger.exception(
                "AuthorityDiscoveryService: provider %s failed for %s",
                name,
                canonical_key,
            )
            AuthorityFrontierService.mark(frontier_row, "failed", error=str(exc))
            return {
                "status": "failed",
                "error": str(exc),
                "canonical_key": canonical_key,
            }

        # --- guard: empty fetch is a failure, not a silent no-op ------------
        if not sections:
            logger.warning(
                "AuthorityDiscoveryService: provider %s returned no sections for %s",
                name,
                canonical_key,
            )
            AuthorityFrontierService.mark(
                frontier_row, "failed", error="provider returned no sections"
            )
            return {
                "status": "failed",
                "error": "provider returned no sections",
                "canonical_key": canonical_key,
            }

        # --- bootstrap -------------------------------------------------------
        # Pass relink=False here; we do a wider relink below that includes the
        # equivalence from_keys so act-section refs also upgrade.
        result = bootstrap_authority_corpus(
            creator_id=creator_id,
            corpus_title=provider.title,
            sections=sections,
            aliases=list(provider.supported_prefixes),
            make_public=make_public,
            relink=False,
        )

        # --- locate the ingested document to record on the frontier row ------
        from opencontractserver.documents.models import Document

        ingested_doc = (
            Document.objects.filter(
                custom_meta__canonical_key=sections[0].key,
                path_records__is_current=True,
                path_records__is_deleted=False,
            )
            .order_by("id")
            .first()
        )

        # --- equivalence-aware relink seam -----------------------------------
        # Filings cite act-section keys (e.g. exchange-act:10) while we
        # bootstrap under USC keys (usc-15:78j). Pull every equivalence
        # touching an ingested key and collect the OTHER side (the
        # popular-name key filings actually cite) so relink upgrades those
        # EXTERNAL refs via find_authority_target's equivalence hop.
        # Direction-agnostic: we don't assume which column holds the ingested
        # key.
        section_keys = [s.key for s in sections]
        equiv_pairs = AuthorityKeyEquivalence.objects.filter(
            Q(from_key__in=section_keys) | Q(to_key__in=section_keys)
        ).values_list("from_key", "to_key")
        other_keys = {(f if t in section_keys else t) for f, t in equiv_pairs}
        relink_keys = sorted({*section_keys, *other_keys})

        if relink_async:
            from opencontractserver.tasks.corpus_tasks import (
                relink_corpora_for_keys_task,
            )

            async_result = relink_corpora_for_keys_task.delay(relink_keys)
            relink_result: dict = {"queued": True, "task_id": async_result.id}
            relinked_count = 0
        else:
            relink_result = EnrichmentService().relink_corpora_for_keys(relink_keys)
            relinked_count = relink_result.get("law_references_linked", 0)

        result["equivalence_relink"] = relink_result

        # --- mark ingested ---------------------------------------------------
        AuthorityFrontierService.mark(
            frontier_row,
            "ingested",
            document_id=ingested_doc.id if ingested_doc else None,
        )

        return {
            "status": "ingested",
            **result,
            "relinked_count": relinked_count,
            "canonical_key": canonical_key,
        }
