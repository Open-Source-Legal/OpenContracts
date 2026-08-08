"""Manage the durable authority discovery queue (AuthorityFrontier).

Follows the repo-wide ``opencontractserver/<app>/services/`` convention:
user-context callers reach enrichment data through these services, never via
inline Tier-0 ORM fusions.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from opencontractserver.annotations.models import AuthorityFrontier
from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.services.authority_permissions import (
    DENIED,
    is_authority_admin,
)
from opencontractserver.enrichment.services.corpus_reference_service import (
    CorpusReferenceService,
)
from opencontractserver.shared.services.base import BaseService

if TYPE_CHECKING:
    from opencontractserver.pipeline.base.base_authority_discovery_provider import (
        DiscoveryCandidate,
    )


@dataclass
class FrontierActionResult:
    """Outcome of an admin frontier row-action: ``ok`` + error/obj/count."""

    ok: bool
    error: str = ""
    obj: AuthorityFrontier | None = None
    count: int = 0


class AuthorityFrontierService(BaseService):
    """Manage the durable authority discovery queue."""

    @classmethod
    def discovery_identities_for_provider(cls, discovery_provider: str) -> set[str]:
        """Return candidate identities durably enumerated by one provider.

        ``candidate_sources`` is the existing append-only frontier provenance
        rail, so it also serves as the deterministic discovery cursor: capped
        reruns exclude exact observations and continue through stable listing
        order without introducing another queue/model.  A changed URL, title,
        or provider-owned listing metadata value for the same canonical key has
        a different identity and remains reachable.
        """

        from opencontractserver.pipeline.base.base_authority_discovery_provider import (
            DiscoveryCandidate,
            discovery_candidate_identity,
        )

        identities: set[str] = set()
        for canonical_key, candidate_sources in AuthorityFrontier.objects.values_list(
            "canonical_key", "candidate_sources"
        ):
            for record in candidate_sources or []:
                if (
                    not isinstance(record, Mapping)
                    or record.get("discovery_provider") != discovery_provider
                ):
                    continue
                url = record.get("url")
                if not isinstance(url, str) or not url:
                    continue
                extra = record.get("extra")
                identities.add(
                    discovery_candidate_identity(
                        DiscoveryCandidate(
                            canonical_key=canonical_key,
                            url=url,
                            title=(
                                record.get("title")
                                if isinstance(record.get("title"), str)
                                else None
                            ),
                            extra=(dict(extra) if isinstance(extra, Mapping) else {}),
                        ),
                        discovery_provider=discovery_provider,
                    )
                )
                # Keep accepting a previously stored identity during rolling
                # upgrades, while the reconstruction above upgrades legacy v1
                # observations to the current title/extra-bound identity.
                stored_identity = record.get("discovery_id")
                if isinstance(stored_identity, str) and len(stored_identity) == 64:
                    identities.add(stored_identity)
        return identities

    @classmethod
    def seed_from_wanted_authorities(cls, user, corpus_id: int | None = None) -> dict:
        """Upsert one AuthorityFrontier row per wanted section-root key.

        Reuses the same aggregation users see in the Wanted Authorities panel,
        but with ``finalized_only=True``: the crawl ingests authorities, an
        irreversible action, so it must seed only from FINALIZED references —
        never from the partial output of a still-running enrichment pass. The
        panel itself shows in-flight rows (so the queue is a finalized subset of
        the display, by design). Idempotent: re-running refreshes mention_count /
        distinct_corpus_count / candidate_sources and leaves discovery_state
        untouched for in-flight rows.
        """
        wanted = CorpusReferenceService.wanted_authorities(
            user, corpus_id=corpus_id, finalized_only=True
        )
        created = updated = 0
        queued_keys: set[str] = set()
        for auth in wanted:
            authority = auth["authority"]
            juris, atype = C.classify_prefix(authority)
            for key_entry in auth["top_keys"]:
                root = key_entry["canonical_key"]
                queued_keys.add(root)
                # Atomic create-or-refresh under a row lock. Collapsing the old
                # get_or_create + unconditional save into one ``select_for_update``
                # critical section closes a TOCTOU race: two concurrent seed
                # passes could previously both pass get_or_create and then have
                # one silently clobber the other's count update, and a fresh row
                # was briefly visible at mention_count=0 (the default) between the
                # insert and its follow-up save. The lock serialises the second
                # writer behind the first and seeds the real counts atomically.
                with transaction.atomic():
                    locked = AuthorityFrontier.objects.select_for_update()
                    row, was_created = locked.get_or_create(
                        canonical_key=root,
                        defaults={
                            "authority": authority,
                            "jurisdiction": juris,
                            "authority_type": atype,
                            "mention_count": key_entry["mention_count"],
                            "distinct_corpus_count": key_entry["corpus_count"],
                        },
                    )
                    if not was_created:
                        row.mention_count = key_entry["mention_count"]
                        row.distinct_corpus_count = key_entry["corpus_count"]
                        # jurisdiction/authority_type use "prefer existing
                        # non-null": a row first seeded before its prefix was
                        # classifiable is filled in later, but a known value is
                        # never overwritten (so this is NOT update_or_create with
                        # the pair in defaults, which would clobber on every run).
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
        return {
            "frontier_created": created,
            "frontier_updated": updated,
            # The sole consumer (CrawlAuthoritiesService.crawl) only needs
            # containment, not ordering, so return the keys unsorted.
            "queued_keys": list(queued_keys),
        }

    @classmethod
    def admin_state_counts(
        cls,
        user,
        *,
        jurisdiction: str | None = None,
        authority_type: str | None = None,
        provider: str | None = None,
        authority: str | None = None,
        search: str | None = None,
    ) -> dict:
        """Per-``discovery_state`` row counts for the global authority-sources
        monitor's summary chips (**superuser-only**).

        Honours the non-state facets (jurisdiction / authority_type / provider /
        authority / search) but NOT a state filter, so the chips always show the
        full state breakdown for the current facet selection. Returns
        ``{"total_count": int, "by_state": [{"state", "count"}, ...]}`` and is
        empty for non-superusers (the frontier is a system-managed global queue
        with no per-object permissions).
        """
        if not is_authority_admin(user):
            return {"total_count": 0, "by_state": []}

        qs = AuthorityFrontier.objects.all()
        if jurisdiction:
            qs = qs.filter(jurisdiction=jurisdiction)
        if authority_type:
            qs = qs.filter(authority_type=authority_type)
        if provider:
            qs = qs.filter(provider=provider)
        if authority:
            qs = qs.filter(authority=authority)
        if search:
            qs = qs.filter(
                Q(canonical_key__icontains=search) | Q(authority__icontains=search)
            )

        by_state = [
            {"state": r["discovery_state"], "count": r["count"]}
            for r in qs.values("discovery_state")
            .annotate(count=Count("id"))
            .order_by("-count")
        ]
        return {
            "total_count": sum(r["count"] for r in by_state),
            "by_state": by_state,
        }

    @classmethod
    def dequeue_queued(
        cls,
        *,
        limit: int = 10,
        max_depth: int | None = None,
        min_demand: int = 0,
        canonical_keys: set[str] | list[str] | tuple[str, ...] | None = None,
    ) -> list[AuthorityFrontier]:
        """Atomically CLAIM the highest-demand queued rows for the crawl driver.

        Unlike ``dequeue_for_provider`` (which requires a stamped provider),
        this serves the crawl driver: it picks ``discovery_state="queued"`` rows
        ranked by ``-mention_count``, optionally bounded by depth and a minimum
        demand floor.  Provider selection happens later in the discovery service.

        The returned rows are transitioned to ``in_progress`` inside a single
        ``SELECT ... FOR UPDATE SKIP LOCKED`` transaction, so the dequeue is an
        atomic *claim* rather than a plain read: two ``crawl_authorities`` tasks
        running concurrently (e.g. two manual triggers on the same corpus) can
        never return — and therefore never ``discover_and_bootstrap`` — the same
        frontier row twice (issue #2027). ``skip_locked`` lets a second worker
        pick the next available rows instead of blocking on the first worker's
        lock. Rows excluded by ``max_depth`` / ``min_demand`` are never claimed,
        so the crawl's ``frontier_drained`` residual census still sees them as
        ``queued``.

        ``canonical_keys`` scopes the claim to a single crawl run's frontier —
        this is the primary corpus-isolation gate: ``None`` disables scoping
        (claims from the global frontier), while an empty collection
        short-circuits to ``[]`` immediately rather than falling through to an
        unscoped (and therefore cross-corpus) claim.
        """
        qs = AuthorityFrontier.objects.filter(discovery_state=C.DISCOVERY_STATE_QUEUED)
        if canonical_keys is not None:
            if not canonical_keys:
                return []
            qs = qs.filter(canonical_key__in=canonical_keys)
        if max_depth is not None:
            qs = qs.filter(depth__lte=max_depth)
        if min_demand:
            qs = qs.filter(mention_count__gte=min_demand)
        with transaction.atomic():
            rows = list(
                qs.select_for_update(skip_locked=True).order_by("-mention_count")[
                    :limit
                ]
            )
            if rows:
                now = timezone.now()
                for row in rows:
                    row.discovery_state = "in_progress"
                    row.last_attempt = now
                    # bulk_update bypasses auto_now — stamp ``modified`` so the
                    # claim matches the single-row ``mark()`` writer.
                    row.modified = now
                AuthorityFrontier.objects.bulk_update(
                    rows, ["discovery_state", "last_attempt", "modified"]
                )
        return rows

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
        queued_keys: set[str] = set()
        child_depth = parent.depth + 1
        for raw in canonical_keys:
            root = candidate_keys(raw)[-1]
            queued_keys.add(root)
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
                    "discovery_state": C.DISCOVERY_STATE_QUEUED,
                },
            )
            created += int(was_created)
            skipped += int(not was_created)
        return {
            "child_created": created,
            "child_skipped": skipped,
            # Consumer (crawl) only needs containment; skip the sort.
            "queued_keys": list(queued_keys),
        }

    @classmethod
    def seed_from_discovery(
        cls,
        candidates: list[DiscoveryCandidate],
        *,
        discovery_provider: str,
    ) -> dict:
        """Upsert AuthorityFrontier rows from a discovery provider's candidates.

        Phase 2 (issue #2054): a ``BaseAuthorityDiscoveryProvider`` lists
        documents nobody has cited yet (candidate = canonical_key + url +
        minimal metadata); this is the ONE place that turns those candidates
        into durable frontier rows.

        Freshly created rows are seeded at ``depth=0`` (a discovery-sourced
        candidate is a fresh root, not a hop from an existing frontier row),
        ``mention_count=1`` (parity with ``seed_child_keys``'s floor demand for a
        freshly-seen key), and carry the candidate's url/title/extra in the
        append-only ``candidate_sources`` audit trail.  A key may already exist
        because a filing cited it before its publisher listing was crawled.  In
        that case a new/different listing candidate is appended under a row lock
        without changing state, provider, demand counts, errors, or the ingested
        document; an exact rediscovery is a no-op.  Persisting ``extra`` is
        essential: the fetch provider later receives this exact
        candidate context, so listing-only document URLs and attachment identity
        survive the discovery -> frontier -> locate hand-off.

        Does NOT stamp ``AuthorityFrontier.provider``: that field names a
        registered ``BaseAuthoritySourceProvider`` (the citation-keyed FETCH
        rail), which a discovery provider is not — the row is left
        ``provider=None`` so the existing ``discover_and_bootstrap``
        orchestration picks a source provider via its normal ``_provider_for``
        routing, exactly like ``seed_child_keys`` / ``seed_from_wanted_authorities``.
        """
        created = appended = skipped = 0
        queued_keys: set[str] = set()
        from opencontractserver.pipeline.base.base_authority_discovery_provider import (
            DiscoveryCandidate,
            discovery_candidate_identity,
        )

        for candidate in candidates:
            key = candidate.canonical_key
            queued_keys.add(key)
            authority = key.split(":", 1)[0]
            juris, atype = C.classify_prefix(authority)
            candidate_source: dict[str, object] = {
                "discovery_provider": discovery_provider,
                "discovery_id": discovery_candidate_identity(
                    candidate,
                    discovery_provider=discovery_provider,
                ),
                "url": candidate.url,
                "title": candidate.title,
            }
            # Preserve the historical sparse shape for candidates that carry no
            # provider-specific metadata, while round-tripping every non-empty
            # mapping for listing-backed source providers.
            if candidate.extra:
                candidate_source["extra"] = dict(candidate.extra)

            with transaction.atomic():
                locked = AuthorityFrontier.objects.select_for_update()
                row, was_created = locked.get_or_create(
                    canonical_key=key,
                    defaults={
                        "authority": authority,
                        "jurisdiction": juris,
                        "authority_type": atype,
                        "mention_count": 1,
                        "candidate_sources": [candidate_source],
                    },
                )
                was_appended = False
                if not was_created:
                    prior_sources = list(row.candidate_sources or [])
                    prior_identities: set[str] = set()
                    for prior in prior_sources:
                        if not isinstance(prior, Mapping):
                            continue
                        if prior.get(
                            "discovery_provider"
                        ) != discovery_provider or not isinstance(
                            prior.get("url"), str
                        ):
                            continue
                        extra = prior.get("extra")
                        prior_identities.add(
                            discovery_candidate_identity(
                                DiscoveryCandidate(
                                    canonical_key=key,
                                    url=str(prior["url"]),
                                    title=(
                                        prior.get("title")
                                        if isinstance(prior.get("title"), str)
                                        else None
                                    ),
                                    extra=(
                                        dict(extra)
                                        if isinstance(extra, Mapping)
                                        else {}
                                    ),
                                ),
                                discovery_provider=discovery_provider,
                            )
                        )
                        prior_identity = prior.get("discovery_id")
                        if (
                            isinstance(prior_identity, str)
                            and len(prior_identity) == 64
                        ):
                            prior_identities.add(prior_identity)
                    if candidate_source["discovery_id"] not in prior_identities:
                        row.candidate_sources = [*prior_sources, candidate_source]
                        row.save(update_fields=["candidate_sources", "modified"])
                        was_appended = True
            created += int(was_created)
            appended += int(was_appended)
            skipped += int(not was_created and not was_appended)
        return {
            "discovery_created": created,
            "discovery_appended": appended,
            "discovery_skipped": skipped,
            # Consumer (discover_authority_candidates command) only needs
            # containment; skip the sort (mirrors seed_child_keys).
            "queued_keys": list(queued_keys),
        }

    @classmethod
    def dequeue_for_provider(
        cls, provider: str, limit: int = 10
    ) -> list[AuthorityFrontier]:
        """Return up to ``limit`` queued rows already STAMPED with ``provider``.

        This is NOT the primary dispatch entrypoint — the crawl driver uses
        ``dequeue_queued`` (provider-agnostic) and provider selection happens
        mid-flight inside ``AuthorityDiscoveryService.discover_and_bootstrap``.
        Freshly seeded rows carry ``provider=None`` until then, so this method
        returns ZERO rows for them by design. Its real use is crash recovery:
        re-draining rows whose ``provider`` was recorded before a Celery task
        died, so a named provider can resume exactly where it left off.
        """
        return list(
            AuthorityFrontier.objects.filter(
                provider=provider, discovery_state=C.DISCOVERY_STATE_QUEUED
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
        candidate_record: Mapping[str, object] | None = None,
        clear_document: bool = False,
        clear_error: bool = False,
        clear_provider: bool = False,
        set_provider: str | None = None,
    ) -> None:
        """Transition ``row`` to ``state``, optionally recording or CLEARING fields.

        This is the ONE frontier transition primitive — every state change (the
        discovery/crawl pipeline AND the admin row-action verbs) funnels through
        it. The ``clear_*`` flags exist so an admin requeue can move an already-
        ingested row back to ``queued`` while clearing ``ingested_document``: the
        ``frontier_queued_no_ingested_doc`` CheckConstraint forbids a queued row
        that still carries a document, so a requeue MUST clear it here rather than
        leave a constraint-violating row.

        Transitioning into a terminal SUCCESS state (``C.DISCOVERY_SUCCESS_STATES``
        — i.e. ``ingested``) also clears ``last_error`` implicitly, so a row that
        succeeds on retry does not retain the error string from its earlier failed
        attempt (the audit trail in ``candidate_sources`` keeps that history).

        Args:
            row: The ``AuthorityFrontier`` instance to update.
            state: New ``discovery_state`` value.
            document_id: If provided, set ``ingested_document_id`` to this value.
            error: If provided, set ``last_error`` to this message.
            candidate_record: If provided, APPEND to ``candidate_sources`` (append-only
                audit trail — earlier attempts are never overwritten).
            clear_document: If True, NULL ``ingested_document`` (mutually exclusive
                with ``document_id``).
            clear_error: If True, NULL ``last_error`` (mutually exclusive with
                ``error``). Redundant for SUCCESS states, which clear it anyway.
            clear_provider: If True, NULL ``provider``.
        """
        if document_id is not None and clear_document:
            raise ValueError("mark(): document_id and clear_document are exclusive.")
        if error is not None and clear_error:
            raise ValueError("mark(): error and clear_error are exclusive.")
        if set_provider is not None and clear_provider:
            raise ValueError("mark(): set_provider and clear_provider are exclusive.")
        if error is not None and state in C.DISCOVERY_SUCCESS_STATES:
            # A terminal SUCCESS row must carry no error (the invariant the
            # last_error auto-clear below establishes); refuse the contradiction
            # loudly rather than persist an "ingested but errored" row.
            raise ValueError(
                "mark(): cannot set error on a terminal success transition "
                f"({state!r}); omit error= (success states clear last_error)."
            )

        row.discovery_state = state
        row.last_attempt = timezone.now()
        # Only touch ingested_document / last_error when the caller actually
        # supplies them, so e.g. marking a previously-ingested row "failed"
        # (document_id=None) neither rewrites nor clears its existing document.
        update_fields = ["discovery_state", "last_attempt", "modified"]
        if document_id is not None:
            row.ingested_document_id = document_id
            update_fields.append("ingested_document")
        elif clear_document:
            row.ingested_document_id = None
            update_fields.append("ingested_document")
        if error is not None:
            row.last_error = error
            update_fields.append("last_error")
        elif clear_error or state in C.DISCOVERY_SUCCESS_STATES:
            # A row that reaches a terminal SUCCESS state (ingested) carries no
            # error: clear any stale last_error from an earlier failed attempt so
            # a row that transitions failed -> ingested is not misread as broken
            # by health checks. Callers need not remember clear_error=True on the
            # happy path; an explicit error= (guarded exclusive with clear_error
            # above) still wins for non-success states.
            row.last_error = None
            update_fields.append("last_error")
        if set_provider is not None:
            row.provider = set_provider
            update_fields.append("provider")
        elif clear_provider:
            row.provider = None
            update_fields.append("provider")
        if candidate_record is not None:
            # Append-only audit trail; never overwrite prior attempts.
            row.candidate_sources = list(row.candidate_sources or []) + [
                candidate_record
            ]
            update_fields.append("candidate_sources")
        row.save(update_fields=update_fields)

    # ----- admin row-action verbs (superuser-gated wrappers over mark()) ---- #

    @classmethod
    def _get_admin_row(cls, user, pk) -> AuthorityFrontier | None:
        """Fetch a frontier row for an authority-admin (else None — opaque)."""
        if not is_authority_admin(user):
            return None
        return AuthorityFrontier.objects.filter(pk=pk).first()

    @staticmethod
    def _reject_if_in_progress(row) -> FrontierActionResult | None:
        """Refuse a state-flip verb on a row a crawl worker is actively ingesting.

        Flipping an ``in_progress`` row back to ``queued`` would let the crawl
        driver re-dequeue it mid-pass (it would be processed twice). Discovery is
        idempotent so the blast radius is small, but the admin verbs should still
        not race the worker — wait for the row to settle. ``approve`` already has
        its own (``pending_approval``-only) state guard, so this is for the
        re-queueing verbs requeue / reset / reroute.
        """
        if row.discovery_state == C.DISCOVERY_STATE_IN_PROGRESS:
            return FrontierActionResult(
                False,
                "Row is in_progress (a crawl worker is ingesting it); wait for it "
                "to settle before requeue/reset/reroute.",
            )
        return None

    @classmethod
    def requeue(cls, user, *, pk) -> FrontierActionResult:
        """Re-queue a row (un-stick ``deferred_cap`` / ``failed`` / a stale state).

        Clears ``ingested_document`` + ``last_error`` and marks ``queued`` so the
        crawl driver's ``dequeue_queued`` (which matches only ``queued``) can pick
        it up again — the fix for ``deferred_cap`` rows that otherwise stick.
        """
        row = cls._get_admin_row(user, pk)
        if row is None:
            return FrontierActionResult(False, DENIED)
        blocked = cls._reject_if_in_progress(row)
        if blocked is not None:
            return blocked
        cls.mark(row, C.DISCOVERY_STATE_QUEUED, clear_document=True, clear_error=True)
        cls.log_action("Requeued", row, user)
        return FrontierActionResult(True, obj=row)

    @classmethod
    def reset(cls, user, *, pk) -> FrontierActionResult:
        """Hard reset: clear document + provider + error and re-queue."""
        row = cls._get_admin_row(user, pk)
        if row is None:
            return FrontierActionResult(False, DENIED)
        blocked = cls._reject_if_in_progress(row)
        if blocked is not None:
            return blocked
        cls.mark(
            row,
            C.DISCOVERY_STATE_QUEUED,
            clear_document=True,
            clear_error=True,
            clear_provider=True,
        )
        cls.log_action("Reset", row, user)
        return FrontierActionResult(True, obj=row)

    @classmethod
    def reroute(cls, user, *, pk, provider: str) -> FrontierActionResult:
        """Re-assign the provider (validated against the registry) and re-queue."""
        row = cls._get_admin_row(user, pk)
        if row is None:
            return FrontierActionResult(False, DENIED)
        blocked = cls._reject_if_in_progress(row)
        if blocked is not None:
            return blocked
        provider = (provider or "").strip()
        if provider not in cls.registered_provider_names():
            return FrontierActionResult(False, f"Unknown provider '{provider}'.")
        # Persist the new provider through mark() (the single writer) and re-queue,
        # clearing the prior ingested doc so the new provider re-fetches cleanly.
        cls.mark(
            row,
            C.DISCOVERY_STATE_QUEUED,
            set_provider=provider,
            clear_document=True,
            clear_error=True,
        )
        cls.log_action("Rerouted", row, user, provider=provider)
        return FrontierActionResult(True, obj=row)

    @classmethod
    def approve(cls, user, *, pk) -> FrontierActionResult:
        """Durably approve a ``pending_approval`` candidate and re-queue it.

        Approval is copied from the latest pending-attempt fingerprint, binding
        it to that provider response's source, evidence, rights, and exact bytes.
        A changed/reseeded response therefore parks for a new approval.  Both
        attempt and approval remain in the append-only candidate_sources trail.
        """
        row = cls._get_admin_row(user, pk)
        if row is None:
            return FrontierActionResult(False, DENIED)
        if row.discovery_state != C.DISCOVERY_STATE_PENDING_APPROVAL:
            return FrontierActionResult(
                False, "Only pending-approval rows can be approved."
            )
        pending_attempt = next(
            (
                record
                for record in reversed(list(row.candidate_sources or []))
                if isinstance(record, Mapping)
                and record.get("outcome") == C.DISCOVERY_STATE_PENDING_APPROVAL
                and record.get("provider") == row.provider
            ),
            None,
        )
        approval_fingerprint = (
            pending_attempt.get("approval_fingerprint")
            if pending_attempt is not None
            else None
        )
        if not isinstance(approval_fingerprint, str) or len(approval_fingerprint) != 64:
            return FrontierActionResult(
                False,
                "Pending attempt has no response approval fingerprint; re-run "
                "discovery before approving.",
            )
        approved_at = timezone.now().isoformat()
        cls.mark(
            row,
            C.DISCOVERY_STATE_QUEUED,
            clear_error=True,
            candidate_record={
                "provider": row.provider,
                "outcome": "approved",
                "approval_scope": "authority-ingestion",
                "approval_fingerprint": approval_fingerprint,
                "approved_by": user.pk,
                "approved_at": approved_at,
            },
        )
        cls.log_action("Approved", row, user)
        return FrontierActionResult(True, obj=row)

    @classmethod
    def delete_rows(cls, user, *, pks: list[int]) -> FrontierActionResult:
        """Delete frontier rows (superuser-gated bulk action)."""
        if not is_authority_admin(user):
            return FrontierActionResult(False, DENIED)
        deleted, _ = AuthorityFrontier.objects.filter(pk__in=pks).delete()
        return FrontierActionResult(True, count=deleted)

    @staticmethod
    def registered_provider_names() -> set[str]:
        """Class names of the registered authority source providers."""
        from opencontractserver.pipeline.registry import (
            get_all_authority_source_providers_cached,
        )

        return {defn.name for defn in get_all_authority_source_providers_cached()}
