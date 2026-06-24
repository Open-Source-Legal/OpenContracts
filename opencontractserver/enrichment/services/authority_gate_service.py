"""Verify+license gate: evaluates fetched authority text BEFORE bootstrap.

Runs AFTER provider.fetch() and BEFORE bootstrap_authority_corpus. Never silently
drops a result — every non-OK verdict is returned for the caller to record on the
frontier via AuthorityFrontierService.mark(candidate_record=...).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from opencontractserver.constants.safe_http import PUBLIC_DOMAIN_SOURCE_HOSTS
from opencontractserver.enrichment.authorities import AuthoritySection
from opencontractserver.utils.safe_http import host_on_allowlist

# Gate verdicts map 1:1 onto the discovery_state strings.
GATE_OK = "ok"
GATE_BLOCKED_LICENSE = "blocked_license"
GATE_BLOCKED_DOMAIN = "blocked_domain"
GATE_UNLOCATED = "unlocated"
GATE_PENDING_APPROVAL = "pending_approval"


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
        sections: list[AuthoritySection],
        provider_license: str,
        require_approval_for_agentic: bool = False,
    ) -> GateDecision:
        """Evaluate whether fetched sections may be ingested.

        Args:
            canonical_key: The requested authority key (e.g. "usc-15:78j").
            sections: List of AuthoritySection objects returned by the provider.
                The domain gate checks ``sections[0].source_url``.
            provider_license: The provider's declared license ClassVar.
            require_approval_for_agentic: When True, gate returns
                PENDING_APPROVAL for an otherwise-valid result.

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
        # 1) License gate -------------------------------------------------------
        if provider_license != "public-domain":
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
        # A missing/un-parseable source URL means we cannot attribute the result
        # to an allowlisted domain. Rather than trust it on its license alone
        # (an unexpected bypass of the domain gate), treat it as UNLOCATED.
        if domain is None:
            return GateDecision(
                GATE_UNLOCATED,
                "no source URL to verify against the public-domain allowlist",
                "skipped",
                None,
            )
        # An off-allowlist domain is a security block, distinct from a license
        # block — operators filter the two states differently.
        if not host_on_allowlist(domain, allowlist=PUBLIC_DOMAIN_SOURCE_HOSTS):
            return GateDecision(
                GATE_BLOCKED_DOMAIN,
                f"source domain {domain!r} not on public-domain allowlist",
                "skipped",
                domain,
            )

        # 4) Verify: fetched key/heading must match the requested key ----------
        if not cls._verify_key_match(canonical_key, sections):
            return GateDecision(
                GATE_UNLOCATED,
                f"fetched section key(s) {[s.key for s in sections]} "
                f"do not match requested {canonical_key!r}",
                "mismatch",
                domain,
            )

        # 5) Agentic provenance needs a human ----------------------------------
        if require_approval_for_agentic:
            return GateDecision(
                GATE_PENDING_APPROVAL,
                "agentic locator result requires human approval",
                "match",
                domain,
            )

        return GateDecision(GATE_OK, "verified", "match", domain)

    @staticmethod
    def _verify_key_match(canonical_key: str, sections: list[AuthoritySection]) -> bool:
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
