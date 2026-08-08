"""Orchestrates authority discovery: registry -> provider -> bootstrap -> relink.

``AuthorityDiscoveryService`` is the single entry point for the automated
discovery pipeline.  Given an ``AuthorityFrontier`` row it:

1. Finds a registered provider that ``can_handle`` the row's key.
2. Calls the provider's ``locate`` + ``fetch`` to retrieve authority records.
3. Applies per-record rights/domain verification, then delegates to
   ``bootstrap_authority_corpus`` for idempotent materialisation.
4. Triggers a cross-corpus relink that upgrades act-section EXTERNAL
   references (e.g. ``exchange-act:10(b)``) to RESOLVED once the USC
   document lands — the equivalence relink seam.
5. Marks the frontier row ``ingested`` (or ``failed`` / ``unsupported``).
"""

from __future__ import annotations

import hashlib
import json
import logging
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Mapping, Sequence
from typing import Any, TypedDict
from urllib.parse import urlsplit, urlunsplit

import httpx
import requests
from django.db.models import Q
from django.utils import timezone

from opencontractserver.annotations.models import AuthorityFrontier
from opencontractserver.enrichment import constants as C
from opencontractserver.shared.services.base import BaseService

logger = logging.getLogger(__name__)


class _AuditRecord(TypedDict):
    """Schema of one append-only ``candidate_sources`` audit entry.

    Declaring the shape here (rather than building a bare dict in three places)
    means a field rename/addition is caught at type-check time instead of
    drifting silently across the fetch-failure, gate-decision, and
    bootstrap-failure paths.
    """

    provider: str | None
    license: str
    source_domain: str | None
    verify: str
    outcome: str
    error: str | None
    attempted_at: str
    rights_status: str | None
    discovery_mode: str | None
    approval_fingerprint: str | None


class AuthorityDiscoveryService(BaseService):
    """Registry-driven authority ingestion orchestrator."""

    @classmethod
    def _provider_for(cls, canonical_key: str) -> tuple[str | None, Any, str | None]:
        """Return ``(name, provider, fetch_key)`` for *canonical_key*.

        ``fetch_key`` is the key the chosen provider should ``locate``/``fetch``:
        the original key when a provider handles it directly, or a
        provider-supported ``AuthorityKeyEquivalence`` counterpart when the
        original is a *domain* key that no provider handles directly.

        Providers only ``can_handle`` statutory/regulatory canonical keys
        (``usc-*``, ``cfr-*``, ``fedreg``), but filings cite *popular-name*
        domain keys (e.g. ``exchange-act:10``, ``securities-act:2``). Those have
        curated equivalences to positive-law USC keys (``usc-15:78j``); rather
        than mark them ``unsupported``, we fetch the equivalent statutory key —
        and the post-ingest equivalence relink (below) upgrades the original
        domain-key EXTERNAL references. Direction-agnostic.

        Sorts the registry by ascending ``priority`` ClassVar so lower numbers
        are preferred. License enforcement is delegated to ``AuthorityGateService``
        — this method intentionally does NOT filter by license. Returns
        ``(None, None, None)`` when nothing matches even after the equivalence hop.
        """
        from opencontractserver.annotations.models import AuthorityKeyEquivalence
        from opencontractserver.pipeline.registry import (
            get_all_authority_source_providers_cached,
        )

        defns = sorted(
            get_all_authority_source_providers_cached(),
            key=lambda d: getattr(d.component_class, "priority", 100),
        )

        # Instantiate each enabled provider ONCE per call and reuse the instances
        # across every candidate key below. ``can_handle`` is pure given the key,
        # so re-instantiating a provider for each candidate (the prior behaviour)
        # was wasted work that grew with the candidate-key fan-out.
        providers = [
            (defn.name, defn.component_class())
            for defn in defns
            if defn.component_class is not None
            and getattr(defn.component_class, "enabled", True)
        ]

        def _match(key: str):
            for name, provider in providers:
                if provider.can_handle(key):
                    return name, provider
            return None

        from opencontractserver.enrichment.data import mappings as _mappings

        # Candidate fetch-keys, in precedence order — the first one a provider
        # can_handle wins:
        #   1. the original key (direct provider support);
        #   2. AuthorityKeyEquivalence counterparts (exchange-act:10 -> usc-15:78j);
        #   3. prefix rewrite rules over the original (irc:N -> usc-26:N);
        #   4. rewrite rules over the equivalence counterparts.
        # Per-key equivalences therefore always beat a mechanical rule, and the
        # two stages compose (an equivalence INTO a rewriteable key resolves) —
        # symmetric with ``find_authority_target``. The equivalence query is
        # ``order_by``-ed so the counterpart chosen for a one-to-many key is
        # deterministic (no Meta.ordering on AuthorityKeyEquivalence).
        equiv_alts: list[str] = [
            (to_key if from_key == canonical_key else from_key)
            for from_key, to_key in AuthorityKeyEquivalence.objects.filter(
                Q(from_key=canonical_key) | Q(to_key=canonical_key)
            )
            .order_by("to_key", "from_key")
            .values_list("from_key", "to_key")
        ]

        candidates: list[tuple[str, str]] = [(canonical_key, "direct")]
        candidates += [(alt, "equivalence") for alt in equiv_alts]
        candidates += [
            (rw, "rewrite rule") for rw in _mappings.apply_rewrite_rules(canonical_key)
        ]
        for alt in equiv_alts:
            candidates += [
                (rw, "equivalence+rewrite rule")
                for rw in _mappings.apply_rewrite_rules(alt)
            ]

        seen: set[str] = set()
        for key, how in candidates:
            if key in seen:
                continue
            seen.add(key)
            matched = _match(key)
            if matched is not None:
                if key != canonical_key:
                    logger.info(
                        "AuthorityDiscoveryService: bridged %s -> %s via %s",
                        canonical_key,
                        key,
                        how,
                    )
                return matched[0], matched[1], key

        return None, None, None

    @staticmethod
    def _audit_record(
        *,
        provider_name: str | None,
        provider_license: str,
        outcome: str,
        source_domain: str | None = None,
        verify: str = "skipped",
        error: str | None = None,
        rights_status: str | None = None,
        discovery_mode: str | None = None,
        approval_fingerprint: str | None = None,
    ) -> _AuditRecord:
        """Build a frontier ``candidate_record`` audit entry.

        Centralises the schema shared by the fetch-failure, gate-decision, and
        bootstrap-failure paths in :meth:`discover_and_bootstrap` so a new field
        is added in exactly one place instead of three. The ``_AuditRecord``
        TypedDict makes that schema explicit and type-checked.
        """
        return _AuditRecord(
            provider=provider_name,
            license=provider_license,
            source_domain=source_domain,
            verify=verify,
            outcome=outcome,
            error=error,
            attempted_at=timezone.now().isoformat(),
            rights_status=rights_status,
            discovery_mode=discovery_mode,
            approval_fingerprint=approval_fingerprint,
        )

    @staticmethod
    def _normalized_source_url(value: str | None) -> str | None:
        """Normalize URL casing/fragment without erasing source distinctions."""

        if not isinstance(value, str) or not value.strip():
            return None
        parsed = urlsplit(value.strip())
        return urlunsplit(
            (
                parsed.scheme.casefold(),
                parsed.netloc.casefold(),
                parsed.path,
                parsed.query,
                "",  # fragments are client-side and never part of fetched bytes
            )
        )

    @classmethod
    def _response_approval_fingerprint(
        cls,
        *,
        provider_name: str | None,
        fetch_key: str,
        request: Any,
        sections: Sequence[Any],
    ) -> str:
        """Bind approval to provider, fetch source, evidence, and exact bytes.

        Records are individually serialized then sorted by their canonical JSON
        representation, making the fingerprint invariant to provider response
        order while remaining sensitive to changed bytes, URL, identity
        evidence, rights disposition, or redirect provenance.
        """

        from opencontractserver.enrichment.authority_sources import (
            AuthoritySourceRecord,
        )

        serialized_records: list[dict[str, object]] = []
        for section in sections:
            if isinstance(section, AuthoritySourceRecord):
                serialized_records.append(
                    {
                        "canonical_key": section.canonical_key,
                        "source_url": cls._normalized_source_url(section.source_url),
                        "final_source_host": str(
                            section.metadata.get("final_source_host") or ""
                        )
                        .strip()
                        .rstrip(".")
                        .casefold(),
                        "content_hash": section.content_hash,
                        "rights_status": str(section.rights_status),
                        "source_identifier": section.source_identifier,
                        "title": section.title,
                        "publisher_evidence": sorted(
                            (
                                evidence.as_dict()
                                for evidence in section.publisher_evidence
                            ),
                            key=lambda item: json.dumps(
                                item,
                                sort_keys=True,
                                separators=(",", ":"),
                            ),
                        ),
                    }
                )
            else:
                text = str(section.text)
                serialized_records.append(
                    {
                        "canonical_key": section.key,
                        "source_url": cls._normalized_source_url(section.source_url),
                        "final_source_host": (
                            urlsplit(section.source_url or "").hostname or ""
                        )
                        .rstrip(".")
                        .casefold(),
                        "content_hash": hashlib.sha256(
                            text.encode("utf-8")
                        ).hexdigest(),
                        "rights_status": None,
                        # Legacy verification evidence is the heading fallback.
                        "heading": section.heading,
                    }
                )
        serialized_records.sort(
            key=lambda item: json.dumps(
                item,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            )
        )
        payload = {
            "schema": "authority-response-approval-v1",
            "provider": provider_name,
            "fetch_key": fetch_key,
            "request_url": cls._normalized_source_url(getattr(request, "url", None)),
            "request_params": getattr(request, "params", {}),
            "records": serialized_records,
        }
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _listing_candidate_for(
        frontier_row: AuthorityFrontier,
        *,
        fetch_key: str,
    ):
        """Rehydrate the durable listing candidate for provider ``locate``.

        Fetching an equivalent/rewrite key must not receive an unrelated source
        URL discovered for the original key.  Directly handled listing keys,
        however, need the exact URL/title/extra that discovery persisted because
        many publisher attachment URLs cannot be derived from their canonical
        identity.
        """

        if fetch_key != frontier_row.canonical_key:
            return None
        from opencontractserver.pipeline.base.base_authority_discovery_provider import (
            DiscoveryCandidate,
        )

        for record in reversed(list(frontier_row.candidate_sources or [])):
            if not isinstance(record, Mapping):
                continue
            url = record.get("url")
            provider_name = record.get("discovery_provider")
            if not isinstance(url, str) or not url or not provider_name:
                continue
            title = record.get("title")
            extra = record.get("extra")
            return DiscoveryCandidate(
                canonical_key=frontier_row.canonical_key,
                url=url,
                title=title if isinstance(title, str) else None,
                extra=dict(extra) if isinstance(extra, Mapping) else {},
            )
        return None

    @staticmethod
    def _has_durable_approval(
        frontier_row: AuthorityFrontier,
        *,
        provider_name: str | None,
        approval_fingerprint: str,
    ) -> bool:
        """Return whether this exact provider response has an approval."""

        for record in reversed(list(frontier_row.candidate_sources or [])):
            if not isinstance(record, Mapping):
                continue
            if (
                record.get("outcome") == "approved"
                and record.get("approval_scope") == "authority-ingestion"
                and record.get("provider") == provider_name
                and record.get("approval_fingerprint") == approval_fingerprint
            ):
                return True
        return False

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
            ``"unsupported"``, or ``"failed"``). On the ``"ingested"`` path the
            dict also carries ``"equivalence_relink"`` (the relink result, or
            ``{"queued": True, "task_id": ...}`` when ``relink_async=True``) and
            ``"relinked_count"`` (the number of law references upgraded, or
            ``None`` when the relink was queued asynchronously and hasn't run).
        """
        from opencontractserver.annotations.models import AuthorityKeyEquivalence
        from opencontractserver.enrichment.authorities import bootstrap_authority_corpus
        from opencontractserver.enrichment.services.authority_frontier_service import (
            AuthorityFrontierService,
        )
        from opencontractserver.enrichment.services.enrichment_service import (
            EnrichmentService,
        )

        canonical_key = frontier_row.canonical_key
        # ``fetch_key`` may differ from the frontier's domain key when a
        # popular-name citation (exchange-act:10) is bridged to its statutory
        # equivalent (usc-15:78j) for fetching; the frontier row keeps its own
        # ``canonical_key`` identity and the relink seam reconciles citations.
        name, provider, fetch_key = cls._provider_for(canonical_key)

        if provider is None:
            AuthorityFrontierService.mark(frontier_row, C.DISCOVERY_STATE_UNSUPPORTED)
            return {
                "status": C.DISCOVERY_STATE_UNSUPPORTED,
                "canonical_key": canonical_key,
            }

        # ``_provider_for`` only returns a non-None provider alongside a non-None
        # ``fetch_key`` (the matched candidate key); the ``(None, None, None)``
        # miss is handled by the guard above. Assert it so the type narrows to
        # ``str`` for ``locate``/``evaluate`` below (and the invariant is loud if
        # a future edit decouples the two return slots).
        assert fetch_key is not None

        # Record which provider was selected and mark in-flight.
        frontier_row.provider = name
        frontier_row.save(update_fields=["provider", "modified"])
        AuthorityFrontierService.mark(frontier_row, C.DISCOVERY_STATE_IN_PROGRESS)

        # --- fetch -----------------------------------------------------------
        listing_candidate = cls._listing_candidate_for(
            frontier_row, fetch_key=fetch_key
        )
        discovery_mode = (
            listing_candidate.extra.get("discovery_mode")
            if listing_candidate is not None
            else None
        )
        if not isinstance(discovery_mode, str):
            discovery_mode = None

        try:
            request = provider.locate(
                fetch_key,
                discovery_candidate=listing_candidate,
            )
            sections = provider.fetch(request)
        except (
            requests.RequestException,
            httpx.HTTPError,
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
            candidate_record = cls._audit_record(
                provider_name=name,
                provider_license=provider.license,
                outcome=C.DISCOVERY_STATE_FAILED,
                error=str(exc),
                discovery_mode=discovery_mode,
            )
            AuthorityFrontierService.mark(
                frontier_row,
                C.DISCOVERY_STATE_FAILED,
                error=str(exc),
                candidate_record=candidate_record,
            )
            return {
                "status": C.DISCOVERY_STATE_FAILED,
                "error": str(exc),
                "canonical_key": canonical_key,
            }

        # --- gate (verify + license + domain) --------------------------------
        # Deferred import (like the bootstrap/frontier/enrichment imports at the
        # top of this method): enrichment/services/__init__ eagerly imports this
        # module, and the gate transitively pulls enrichment.authorities, which
        # re-enters the enrichment.services package — a module-level import here
        # would form an import cycle during app/registry loading.
        from opencontractserver.enrichment.authority_sources import (
            AuthoritySourceRecord,
        )
        from opencontractserver.enrichment.services.authority_gate_service import (
            GATE_OK,
            AuthorityGateService,
            GateDecision,
        )

        # Verify against the key we actually fetched (``fetch_key``) — for a
        # bridged domain key the located text is the statutory section
        # (usc-15:78j), not the popular-name key.
        #
        # Rights are a disposition of each fetched record, not of the provider
        # class.  A single fetch must have one unambiguous disposition: otherwise
        # an approved record could accidentally authorize a LINK_ONLY sibling in
        # the same provider response.  Feeding the sentinel through the normal
        # gate produces a durable blocked-license decision without duplicating
        # the gate's state transition here.
        rich_records = [
            section
            for section in sections
            if isinstance(section, AuthoritySourceRecord)
        ]
        if rich_records and len(rich_records) != len(sections):
            rights_status: str | None = "MIXED_LEGACY_AND_RICH"
        elif rich_records:
            dispositions = {record.rights_status for record in rich_records}
            rights_status = (
                next(iter(dispositions))
                if len(dispositions) == 1
                else "MIXED_RECORD_RIGHTS"
            )
        else:
            rights_status = None
        # The row is already "in_progress" here, so — exactly like the fetch
        # above and the bootstrap below — this stretch needs its own fault
        # handler or an unexpected exception strands it there forever
        # (dequeue_queued only returns "queued" rows, so a stranded row is
        # invisible to every later crawl until an admin resets it by hand) and
        # aborts the whole crawl batch on its way out.  The gate calls a
        # provider-supplied ``verify_publisher_evidence`` override, which is
        # precisely where an unlisted exception type comes from.
        #
        # Deliberately NOT merged with the bootstrap handler below: that one
        # builds its audit record from ``decision``, which is not yet bound
        # here, so sharing it would raise UnboundLocalError inside the handler
        # and re-strand the row.
        try:
            approval_fingerprint = cls._response_approval_fingerprint(
                provider_name=name,
                fetch_key=fetch_key,
                request=request,
                sections=sections,
            )
            rights_approved = cls._has_durable_approval(
                frontier_row,
                provider_name=name,
                approval_fingerprint=approval_fingerprint,
            )
            decision: GateDecision = AuthorityGateService.evaluate(
                canonical_key=fetch_key,
                sections=sections,
                provider_license=provider.license,
                require_approval_for_agentic=getattr(
                    provider, "requires_approval", False
                ),
                rights_status=rights_status,
                rights_approved=rights_approved,
                publisher_evidence_verifier=provider.verify_publisher_evidence,
            )
            candidate_record = cls._audit_record(
                provider_name=name,
                provider_license=provider.license,
                source_domain=decision.source_domain,
                verify=decision.verify,
                outcome=(
                    decision.verdict
                    if decision.verdict != GATE_OK
                    else C.DISCOVERY_STATE_INGESTED
                ),
                error=None if decision.verdict == GATE_OK else decision.reason,
                rights_status=rights_status,
                discovery_mode=discovery_mode,
                approval_fingerprint=approval_fingerprint,
            )
        except Exception as exc:
            logger.exception(
                "AuthorityDiscoveryService: gate evaluation failed for %s",
                canonical_key,
            )
            AuthorityFrontierService.mark(
                frontier_row,
                C.DISCOVERY_STATE_FAILED,
                error=str(exc),
                # Only names bound before the guarded block appear here.
                candidate_record=cls._audit_record(
                    provider_name=name,
                    provider_license=provider.license,
                    outcome=C.DISCOVERY_STATE_FAILED,
                    error=str(exc),
                    rights_status=rights_status,
                    discovery_mode=discovery_mode,
                ),
            )
            return {
                "status": C.DISCOVERY_STATE_FAILED,
                "error": str(exc),
                "canonical_key": canonical_key,
            }
        if decision.verdict != GATE_OK:
            AuthorityFrontierService.mark(
                frontier_row,
                decision.verdict,
                error=decision.reason,
                candidate_record=candidate_record,
            )
            return {
                "status": decision.verdict,
                "reason": decision.reason,
                "canonical_key": canonical_key,
            }

        # --- bootstrap + relink ---------------------------------------------
        # Everything from bootstrap through the ingested-mark runs under one
        # fault handler: a failure here (DB/migration issue, signal handler,
        # relink error) must not strand the row in "in_progress" — it is marked
        # "failed" just like a provider fetch failure above.
        try:
            # Pass relink=False here; we do a wider relink below that includes
            # the equivalence from_keys so act-section refs also upgrade.
            # Rich records own their target corpus.  Grouping by the declared
            # slug keeps a provider free to return related records for more than
            # one pack corpus while preserving the legacy title-keyed behaviour
            # for AuthoritySection providers.  Passing corpus_slug is essential:
            # otherwise a provider title shared across runs can create a second,
            # title-keyed corpus beside the pack-managed corpus.
            section_groups: dict[str | None, list] = {}
            for section in sections:
                corpus_slug = (
                    section.corpus_slug
                    if isinstance(section, AuthoritySourceRecord)
                    else None
                )
                section_groups.setdefault(corpus_slug, []).append(section)

            bootstrap_results: list[dict] = []
            document_id_by_key: dict[str, int] = {}
            for corpus_slug, group in section_groups.items():
                group_result = bootstrap_authority_corpus(
                    creator_id=creator_id,
                    corpus_title=provider.title,
                    sections=group,
                    aliases=list(provider.supported_prefixes),
                    corpus_slug=corpus_slug,
                    make_public=make_public,
                    relink=False,
                    relationship_origin=name,
                )
                bootstrap_results.append(group_result)
                for section, document_id in zip(
                    group, group_result.get("document_ids", []), strict=False
                ):
                    document_id_by_key[section.key] = document_id

            if len(bootstrap_results) == 1:
                result = bootstrap_results[0]
            else:
                numeric_summary_fields = (
                    "documents_created",
                    "documents_updated",
                    "documents_skipped",
                    "documents_restamped",
                    "documents_metadata_updated",
                )
                result = {
                    field: sum(
                        int(group_result.get(field, 0))
                        for group_result in bootstrap_results
                    )
                    for field in numeric_summary_fields
                }
                result.update(
                    {
                        "corpus_ids": [
                            group_result["corpus_id"]
                            for group_result in bootstrap_results
                        ],
                        "document_ids": [
                            document_id
                            for group_result in bootstrap_results
                            for document_id in group_result.get("document_ids", [])
                        ],
                        "bootstrap_results": bootstrap_results,
                    }
                )

            # Bootstrap returns document ids in section order; use that exact
            # result instead of a global first-key query that can select another
            # creator's/current corpus document for the same canonical key.
            ingested_document_id = document_id_by_key.get(fetch_key)
            if ingested_document_id is None and sections:
                ingested_document_id = document_id_by_key.get(sections[0].key)

            # --- equivalence-aware relink seam -------------------------------
            # Filings cite act-section keys (e.g. exchange-act:10) while we
            # bootstrap under USC keys (usc-15:78j). Pull every equivalence
            # touching an ingested key and collect the OTHER side (the
            # popular-name key filings actually cite) so relink upgrades those
            # EXTERNAL refs via find_authority_target's equivalence hop.
            # Direction-agnostic: we don't assume which column holds the
            # ingested key.
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
                # The relink runs in a Celery task that hasn't executed yet, so
                # the count is unknown — use None (not 0) so callers can tell
                # "pending" apart from "ran and linked nothing". The queued task
                # id lives in result["equivalence_relink"].
                relinked_count = None
            else:
                relink_result = EnrichmentService().relink_corpora_for_keys(relink_keys)
                relinked_count = relink_result.get("law_references_linked", 0)

            result["equivalence_relink"] = relink_result

            # --- mark ingested -----------------------------------------------
            # mark() clears any stale last_error from a prior failed attempt on
            # this SUCCESS transition (see C.DISCOVERY_SUCCESS_STATES).
            AuthorityFrontierService.mark(
                frontier_row,
                C.DISCOVERY_STATE_INGESTED,
                document_id=ingested_document_id,
                candidate_record=candidate_record,
            )
        except Exception as exc:
            # The gate already passed, so a failure here is bootstrap/relink — it
            # must not strand the row in "in_progress". Record a failure audit
            # entry (the gate's candidate_record reflected an expected ingest).
            logger.exception(
                "AuthorityDiscoveryService: bootstrap/relink failed for %s",
                canonical_key,
            )
            AuthorityFrontierService.mark(
                frontier_row,
                C.DISCOVERY_STATE_FAILED,
                error=str(exc),
                candidate_record=cls._audit_record(
                    provider_name=name,
                    provider_license=provider.license,
                    source_domain=decision.source_domain,
                    verify=decision.verify,
                    outcome=C.DISCOVERY_STATE_FAILED,
                    error=str(exc),
                    rights_status=rights_status,
                    discovery_mode=discovery_mode,
                    approval_fingerprint=approval_fingerprint,
                ),
            )
            return {
                "status": C.DISCOVERY_STATE_FAILED,
                "error": str(exc),
                "canonical_key": canonical_key,
            }

        return {
            "status": C.DISCOVERY_STATE_INGESTED,
            **result,
            "relinked_count": relinked_count,
            "canonical_key": canonical_key,
        }
