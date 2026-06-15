"""Unit tests for AuthorityGateService — no database required."""

from __future__ import annotations

from unittest import TestCase

from opencontractserver.enrichment.authorities import AuthoritySection
from opencontractserver.enrichment.services.authority_gate_service import (
    GATE_BLOCKED_LICENSE,
    GATE_OK,
    GATE_PENDING_APPROVAL,
    GATE_UNLOCATED,
    AuthorityGateService,
)


def _section(
    key: str = "usc-15:78j",
    heading: str = "Manipulative and deceptive devices",
    text: str = "It shall be unlawful...",
    source_url: str | None = "https://uscode.house.gov/download/t15.zip",
) -> AuthoritySection:
    return AuthoritySection(key=key, heading=heading, text=text, source_url=source_url)


class GateLicenseBlockTests(TestCase):
    """Check 1: non-public-domain license is blocked immediately."""

    def test_licensed_provider_blocked(self):
        decision = AuthorityGateService.evaluate(
            canonical_key="usc-15:78j",
            sections=[_section()],
            provider_license="licensed",
        )
        self.assertEqual(decision.verdict, GATE_BLOCKED_LICENSE)
        self.assertEqual(decision.verify, "skipped")
        self.assertIsNone(decision.source_domain)

    def test_proprietary_provider_blocked(self):
        decision = AuthorityGateService.evaluate(
            canonical_key="usc-15:78j",
            sections=[_section()],
            provider_license="proprietary",
        )
        self.assertEqual(decision.verdict, GATE_BLOCKED_LICENSE)


class GateEmptySectionsTests(TestCase):
    """Check 2: empty sections list → UNLOCATED."""

    def test_empty_sections_unlocated(self):
        decision = AuthorityGateService.evaluate(
            canonical_key="usc-15:78j",
            sections=[],
            provider_license="public-domain",
        )
        self.assertEqual(decision.verdict, GATE_UNLOCATED)
        self.assertEqual(decision.verify, "skipped")
        self.assertIsNone(decision.source_domain)


class GateDomainAllowlistTests(TestCase):
    """Check 3: source_url with off-allowlist host → BLOCKED_LICENSE."""

    def test_off_allowlist_host_blocked(self):
        decision = AuthorityGateService.evaluate(
            canonical_key="usc-15:78j",
            sections=[_section(source_url="https://evil.com/statute.html")],
            provider_license="public-domain",
        )
        self.assertEqual(decision.verdict, GATE_BLOCKED_LICENSE)
        self.assertEqual(decision.verify, "skipped")
        self.assertEqual(decision.source_domain, "evil.com")

    def test_none_source_url_skips_allowlist_check(self):
        """If source_url is None, skip the allowlist check and proceed to verify."""
        # With a matching key, this should get to GATE_OK.
        decision = AuthorityGateService.evaluate(
            canonical_key="usc-15:78j",
            sections=[_section(source_url=None)],
            provider_license="public-domain",
        )
        self.assertEqual(decision.verdict, GATE_OK)


class GateVerifyMismatchTests(TestCase):
    """Check 4: key/heading mismatch → UNLOCATED with verify="mismatch"."""

    def test_key_mismatch_unlocated(self):
        """usc-15:78j requested but usc-15:99z returned with no '78j' in heading."""
        decision = AuthorityGateService.evaluate(
            canonical_key="usc-15:78j",
            sections=[_section(key="usc-15:99z", heading="Something unrelated")],
            provider_license="public-domain",
        )
        self.assertEqual(decision.verdict, GATE_UNLOCATED)
        self.assertEqual(decision.verify, "mismatch")

    def test_heading_fallback_matches(self):
        """Section heading contains the section_id part → verify match."""
        decision = AuthorityGateService.evaluate(
            canonical_key="usc-15:78j",
            sections=[_section(key="usc-15:99z", heading="See also 78j provisions")],
            provider_license="public-domain",
        )
        self.assertEqual(decision.verdict, GATE_OK)
        self.assertEqual(decision.verify, "match")


class GateVerifyMatchTests(TestCase):
    """Check 5: matching key → GATE_OK."""

    def test_exact_key_match_ok(self):
        decision = AuthorityGateService.evaluate(
            canonical_key="usc-15:78j",
            sections=[_section(key="usc-15:78j")],
            provider_license="public-domain",
        )
        self.assertEqual(decision.verdict, GATE_OK)
        self.assertEqual(decision.verify, "match")
        self.assertEqual(decision.reason, "verified")


class GatePendingApprovalTests(TestCase):
    """Check 6: require_approval_for_agentic=True on otherwise-OK → PENDING_APPROVAL."""

    def test_pending_approval_when_agentic(self):
        decision = AuthorityGateService.evaluate(
            canonical_key="usc-15:78j",
            sections=[_section(key="usc-15:78j")],
            provider_license="public-domain",
            require_approval_for_agentic=True,
        )
        self.assertEqual(decision.verdict, GATE_PENDING_APPROVAL)
        self.assertEqual(decision.verify, "match")


class GateHeadingFalsePositiveTests(TestCase):
    """Check that heading fallback uses word-boundary matching, not substring.

    Regression for the case where section_id "1" would falsely match headings
    containing "15", "1722", or other numbers that contain "1" as a substring.
    """

    def test_heading_substring_does_not_match(self):
        """Section id '1' must NOT match heading 'Title 15 — Commerce'.

        'Title 15 — Commerce' contains '1' and '15' as substrings, but the
        section id '1' does not appear as a whole token.
        """
        # requested key: usc-15:1, section key: usc-15:99 (no exact match)
        decision = AuthorityGateService.evaluate(
            canonical_key="usc-15:1",
            sections=[_section(key="usc-15:99", heading="Title 15 — Commerce")],
            provider_license="public-domain",
        )
        self.assertEqual(decision.verdict, GATE_UNLOCATED)
        self.assertEqual(decision.verify, "mismatch")

    def test_heading_whole_token_matches(self):
        """Section id '1' DOES match heading 'Section 1 of Title 15' (whole token)."""
        decision = AuthorityGateService.evaluate(
            canonical_key="usc-15:1",
            sections=[_section(key="usc-15:99", heading="Section 1 of Title 15")],
            provider_license="public-domain",
        )
        self.assertEqual(decision.verdict, GATE_OK)
        self.assertEqual(decision.verify, "match")

    def test_heading_section_id_at_start(self):
        """Section id '78j' at the very start of heading is matched."""
        decision = AuthorityGateService.evaluate(
            canonical_key="usc-15:78j",
            sections=[_section(key="usc-15:99z", heading="78j. Manipulative devices")],
            provider_license="public-domain",
        )
        self.assertEqual(decision.verdict, GATE_OK)
        self.assertEqual(decision.verify, "match")

    def test_section_id_embedded_in_longer_token_not_matched(self):
        """Section id '15' must NOT match heading 'Title 150' (different token)."""
        decision = AuthorityGateService.evaluate(
            canonical_key="usc-1:15",
            sections=[_section(key="usc-1:99", heading="Title 150 provisions")],
            provider_license="public-domain",
        )
        self.assertEqual(decision.verdict, GATE_UNLOCATED)
        self.assertEqual(decision.verify, "mismatch")
