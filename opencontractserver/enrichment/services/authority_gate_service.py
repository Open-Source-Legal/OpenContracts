"""Verify+license gate: evaluates fetched authority text BEFORE bootstrap.

Runs AFTER provider.fetch() and BEFORE bootstrap_authority_corpus. Never silently
drops a result — every non-OK verdict is returned for the caller to record on the
frontier via AuthorityFrontierService.mark(candidate_record=...).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlparse

from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.authorities import AuthoritySection
from opencontractserver.enrichment.authority_sources import AuthoritySourceRecord
from opencontractserver.utils.safe_http import host_on_allowlist

PublisherEvidenceVerifier = Callable[[str, AuthoritySourceRecord], bool]

# Gate verdicts map 1:1 onto the discovery_state strings (except GATE_OK, the
# internal "proceed to ingest" sentinel that is never a stored state). Aliasing
# the shared constants — rather than re-declaring the literals — makes that
# mapping structural, so the gate and the frontier state vocabulary cannot drift.
GATE_OK = "ok"
GATE_BLOCKED_LICENSE = C.DISCOVERY_STATE_BLOCKED_LICENSE
GATE_BLOCKED_DOMAIN = C.DISCOVERY_STATE_BLOCKED_DOMAIN
GATE_UNLOCATED = C.DISCOVERY_STATE_UNLOCATED
GATE_PENDING_APPROVAL = C.DISCOVERY_STATE_PENDING_APPROVAL


@dataclass(frozen=True)
class GateDecision:
    verdict: str  # one of the GATE_* constants
    reason: str  # human-readable, recorded on candidate_sources
    verify: str  # "match" | "mismatch" | "skipped"
    source_domain: str | None  # host of the first section's source_url


class AuthorityGateService:
    """Verify fetched text against the requested key + enforce license/domain.

    All checks are ordered from cheapest to most specific:
    1. Provider license must be "public-domain" (else GATE_BLOCKED_LICENSE).
    2. Provider must have returned at least one section (else GATE_UNLOCATED).
    3. Source URL must be present (else GATE_UNLOCATED) and its host on the
       public-domain allowlist (else GATE_BLOCKED_DOMAIN).
    4. At least one section key or heading must match the canonical_key.
    5. If require_approval_for_agentic, park at pending_approval.

    Unlike the other authority services this does NOT extend ``BaseService``:
    ``evaluate`` is a pure, stateless classmethod with no user context and no
    ORM access, so the Tier-0 visibility/permission helpers BaseService provides
    have nothing to operate on here.
    """

    @classmethod
    def evaluate(
        cls,
        *,
        canonical_key: str,
        sections: Sequence[AuthoritySection | AuthoritySourceRecord],
        provider_license: str,
        require_approval_for_agentic: bool = False,
        rights_status: str | None = None,
        rights_approved: bool = False,
        publisher_evidence_verifier: PublisherEvidenceVerifier | None = None,
    ) -> GateDecision:
        """Evaluate whether fetched sections may be ingested.

        Args:
            canonical_key: The requested authority key (e.g. "usc-15:78j").
            sections: List of AuthoritySection objects returned by the provider.
                The domain gate checks ``sections[0].source_url``.
            provider_license: The provider's declared license ClassVar.
            require_approval_for_agentic: When True, gate returns
                PENDING_APPROVAL for an otherwise-valid result.
            rights_status: Optional per-record disposition emitted by a rich
                authority provider. When omitted, the legacy provider-class
                license rule applies unchanged.
            rights_approved: Durable authority-admin approval for a
                ``REVIEW_REQUIRED``/``LICENSED`` record or agentic result.
            publisher_evidence_verifier: Provider-specific, positive verifier
                that derives a rich record's key from publisher-owned evidence.
                Rich records fail closed when this is absent or returns false.

        Returns:
            A frozen GateDecision with verdict, reason, verify, source_domain.

        Notes:
            - License blocks (check 1) and source-domain blocks (check 3) are
              distinct verdicts: ``GATE_BLOCKED_LICENSE`` vs
              ``GATE_BLOCKED_DOMAIN``. They mean operationally different things
              (fix the provider's license metadata vs. an allowlist/security
              review), so operators can filter on state alone without parsing
              ``reason``.
            - A missing source URL (``sections[0].source_url`` None/"") is
              treated as ``GATE_UNLOCATED`` when sections are present: a result
              we cannot attribute to an allowlisted domain must NOT bypass the
              domain gate on its license alone. See
              ``test_none_source_url_is_unlocated``.
        """
        # 1) Rights/license gate ------------------------------------------------
        requires_rights_approval = False
        if rights_status is None:
            rights_allowed = provider_license == "public-domain"
        else:
            normalized_rights = str(rights_status).strip().upper().replace("-", "_")
            if normalized_rights == "LINK_ONLY":
                return GateDecision(
                    GATE_BLOCKED_LICENSE,
                    "record is explicitly link-only and cannot be ingested",
                    "skipped",
                    None,
                )
            if normalized_rights not in {
                "PUBLIC_DOMAIN",
                "LICENSED",
                "REVIEW_REQUIRED",
            }:
                return GateDecision(
                    GATE_BLOCKED_LICENSE,
                    f"unknown record rights_status {rights_status!r}",
                    "skipped",
                    None,
                )
            requires_rights_approval = normalized_rights in {
                "LICENSED",
                "REVIEW_REQUIRED",
            }
            rights_allowed = normalized_rights == "PUBLIC_DOMAIN" or rights_approved
        if not rights_allowed and not requires_rights_approval:
            return GateDecision(
                GATE_BLOCKED_LICENSE,
                f"provider license {provider_license!r} not public-domain",
                "skipped",
                None,
            )

        # 2) Located? -----------------------------------------------------------
        if not sections:
            return GateDecision(
                GATE_UNLOCATED,
                "provider returned no sections",
                "skipped",
                None,
            )

        first = sections[0]
        domain = urlparse(first.source_url or "").hostname or None

        # 3) Source-domain allowlist --------------------------------------------
        # Every returned section is attributed independently.  Checking only
        # sections[0] would allow an off-allowlist sibling record to ride behind
        # one valid first result.
        for section in sections:
            section_domain = urlparse(section.source_url or "").hostname or None
            if section_domain is None:
                return GateDecision(
                    GATE_UNLOCATED,
                    f"section {section.key!r} has no source URL to verify against "
                    "the public-domain allowlist",
                    "skipped",
                    domain,
                )
            # ``allowlist`` is omitted so this resolves to the effective
            # baseline ∪ installed-packs host set, matching safe_fetch.  Rich
            # pack providers additionally enforce their narrower source_hosts
            # boundary in BaseAuthoritySourceProvider.
            if not host_on_allowlist(section_domain):
                return GateDecision(
                    GATE_BLOCKED_DOMAIN,
                    f"source domain {section_domain!r} for section "
                    f"{section.key!r} not on public-domain allowlist",
                    "skipped",
                    domain,
                )

        # 4) Verify from independent publisher evidence -----------------------
        rich_records = [
            section
            for section in sections
            if isinstance(section, AuthoritySourceRecord)
        ]
        if rich_records:
            verified = cls._verify_rich_publisher_evidence(
                canonical_key,
                sections,
                rich_records,
                publisher_evidence_verifier,
            )
        else:
            verified = cls._verify_key_match(canonical_key, sections)
        if not verified:
            return GateDecision(
                GATE_UNLOCATED,
                "fetched section publisher evidence does not independently "
                f"verify requested {canonical_key!r}; returned key(s) "
                f"{[s.key for s in sections]}",
                "mismatch",
                domain,
            )

        # 5) Rights or agentic provenance may need a durable human approval ----
        if requires_rights_approval and not rights_approved:
            return GateDecision(
                GATE_PENDING_APPROVAL,
                f"record rights_status {rights_status!r} requires human approval",
                "match",
                domain,
            )
        if require_approval_for_agentic and not rights_approved:
            return GateDecision(
                GATE_PENDING_APPROVAL,
                "agentic locator result requires human approval",
                "match",
                domain,
            )

        return GateDecision(GATE_OK, "verified", "match", domain)

    @staticmethod
    def _verify_rich_publisher_evidence(
        canonical_key: str,
        sections: Sequence[AuthoritySection | AuthoritySourceRecord],
        rich_records: Sequence[AuthoritySourceRecord],
        verifier: PublisherEvidenceVerifier | None,
    ) -> bool:
        """Require positive provider verification for every rich response record."""

        # Mixed legacy/rich response shapes are ambiguous and already become a
        # blocked rights disposition in the orchestrator.  Fail verification
        # here too so this pure gate is safe when called directly.
        if len(rich_records) != len(sections) or verifier is None:
            return False
        if any(not record.publisher_evidence for record in rich_records):
            return False
        try:
            # No sibling record is allowed to carry an unverified echoed key.
            if not all(
                verifier(record.canonical_key, record) for record in rich_records
            ):
                return False
            # Separately prove that one publisher signal derives the key that
            # was actually requested, rather than trusting record.key equality.
            return any(verifier(canonical_key, record) for record in rich_records)
        except (KeyError, TypeError, ValueError):
            return False

    @staticmethod
    def _verify_key_match(
        canonical_key: str,
        sections: Sequence[AuthoritySection | AuthoritySourceRecord],
    ) -> bool:
        """Return True if the fetched sections are consistent with the requested key.

        Two signals accepted:
        - Exact key match: any section.key == canonical_key.
        - Heading containment: the section identifier (part after ':' in
          canonical_key) appears in a section heading. This is the fallback for
          providers whose key normalisation differs from the source's own numbering.
        """
        if any(s.key == canonical_key for s in sections):
            return True
        # Fallback: section id (part after ':') surfaces as a whole token in a
        # heading.  Word-boundary match prevents false positives where the
        # section_id is a substring of a longer token (e.g. "1" inside "15").
        section_id = canonical_key.split(":", 1)[-1]
        if not section_id:
            return False
        pattern = re.compile(
            r"(?<![A-Za-z0-9])" + re.escape(section_id) + r"(?![A-Za-z0-9])"
        )
        return any(bool(pattern.search(s.heading)) for s in sections if s.heading)
