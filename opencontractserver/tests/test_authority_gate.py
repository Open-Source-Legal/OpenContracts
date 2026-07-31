"""Unit tests for AuthorityGateService — no database required."""

from __future__ import annotations

from unittest import TestCase

from opencontractserver.enrichment.authorities import AuthoritySection
from opencontractserver.enrichment.authority_sources import (
    AuthorityPublisherEvidence,
    AuthoritySourceRecord,
    AuthorityWeight,
    InstrumentType,
    PublisherEvidenceSource,
    RightsStatus,
    SourceStatus,
)
from opencontractserver.enrichment.services.authority_gate_service import (
    GATE_BLOCKED_DOMAIN,
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


def _rich_record(
    *,
    key: str = "tx-util:37.056",
    source_url: str = "https://uscode.house.gov/test.txt",
    evidence: tuple[AuthorityPublisherEvidence, ...] = (),
) -> AuthoritySourceRecord:
    return AuthoritySourceRecord(
        canonical_key=key,
        title="Texas Utilities Code § 37.056",
        source_url=source_url,
        source_identifier="UT-37.056",
        publisher="Texas Legislature",
        jurisdiction="us-tx",
        authority_type="statute",
        instrument_type=InstrumentType.STATUTE,
        issued_date=None,
        effective_from=None,
        effective_until=None,
        status=SourceStatus.CURRENT,
        authority_weight=AuthorityWeight.CONTROLLING,
        parent_key=None,
        version_label=None,
        content=b"Sec. 37.056. Publisher text.",
        mime_type="text/plain",
        corpus_slug="texas-electric-statutes",
        rights_status=RightsStatus.PUBLIC_DOMAIN,
        extracted_text="Sec. 37.056. Publisher text.",
        publisher_evidence=evidence,
    )


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
    """Check 3: source_url with off-allowlist host → BLOCKED_DOMAIN."""

    def test_off_allowlist_host_blocked(self):
        decision = AuthorityGateService.evaluate(
            canonical_key="usc-15:78j",
            sections=[_section(source_url="https://evil.com/statute.html")],
            provider_license="public-domain",
        )
        # A bad domain is a security block, distinct from a license block.
        self.assertEqual(decision.verdict, GATE_BLOCKED_DOMAIN)
        self.assertEqual(decision.verify, "skipped")
        self.assertEqual(decision.source_domain, "evil.com")

    def test_blocked_domain_distinct_from_blocked_license(self):
        """The two block verdicts must not be the same string (operator filtering)."""
        self.assertNotEqual(GATE_BLOCKED_DOMAIN, GATE_BLOCKED_LICENSE)

    def test_none_source_url_is_unlocated(self):
        """A section with no source_url must NOT bypass the domain gate.

        Previously a missing source_url skipped check 3 and (with a matching key)
        reached GATE_OK on license alone. It now resolves to GATE_UNLOCATED: a
        result we cannot attribute to an allowlisted domain is not ingestible.
        """
        decision = AuthorityGateService.evaluate(
            canonical_key="usc-15:78j",
            sections=[_section(source_url=None)],
            provider_license="public-domain",
        )
        self.assertEqual(decision.verdict, GATE_UNLOCATED)
        self.assertIsNone(decision.source_domain)

    def test_every_returned_section_domain_is_checked(self):
        decision = AuthorityGateService.evaluate(
            canonical_key="usc-15:78j",
            sections=[
                _section(),
                _section(
                    key="usc-15:78k",
                    heading="Related section",
                    source_url="https://evil.com/related",
                ),
            ],
            provider_license="public-domain",
        )
        self.assertEqual(decision.verdict, GATE_BLOCKED_DOMAIN)
        self.assertIn("evil.com", decision.reason)


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


class GateRichPublisherEvidenceTests(TestCase):
    def test_echoed_rich_record_key_cannot_verify_itself(self):
        record = _rich_record()
        decision = AuthorityGateService.evaluate(
            canonical_key=record.canonical_key,
            sections=[record],
            provider_license="public-domain",
            rights_status=RightsStatus.PUBLIC_DOMAIN,
            # Even an unsafe callback cannot rescue missing raw evidence.
            publisher_evidence_verifier=lambda key, value: key == value.canonical_key,
        )
        self.assertEqual(decision.verdict, GATE_UNLOCATED)
        self.assertEqual(decision.verify, "mismatch")

    def test_rich_record_requires_provider_positive_evidence_verifier(self):
        evidence = AuthorityPublisherEvidence(
            source=PublisherEvidenceSource.PARSED_CONTENT,
            value="Sec. 37.056",
        )
        record = _rich_record(evidence=(evidence,))
        without_verifier = AuthorityGateService.evaluate(
            canonical_key=record.canonical_key,
            sections=[record],
            provider_license="public-domain",
            rights_status=RightsStatus.PUBLIC_DOMAIN,
        )
        self.assertEqual(without_verifier.verdict, GATE_UNLOCATED)

        verified = AuthorityGateService.evaluate(
            canonical_key=record.canonical_key,
            sections=[record],
            provider_license="public-domain",
            rights_status=RightsStatus.PUBLIC_DOMAIN,
            publisher_evidence_verifier=lambda key, value: (
                key == "tx-util:37.056"
                and value.publisher_evidence[0].value == "Sec. 37.056"
            ),
        )
        self.assertEqual(verified.verdict, GATE_OK)

    def test_every_rich_sibling_needs_positive_evidence(self):
        first = _rich_record(
            evidence=(
                AuthorityPublisherEvidence(
                    source=PublisherEvidenceSource.PARSED_CONTENT,
                    value="Sec. 37.056",
                ),
            )
        )
        second = _rich_record(
            key="tx-util:37.057",
            evidence=(
                AuthorityPublisherEvidence(
                    source=PublisherEvidenceSource.PARSED_CONTENT,
                    value="unrelated",
                ),
            ),
        )

        def verifier(key, record):
            return record.publisher_evidence[0].value == (
                f"Sec. {key.split(':', 1)[1]}"
            )

        decision = AuthorityGateService.evaluate(
            canonical_key=first.canonical_key,
            sections=[first, second],
            provider_license="public-domain",
            rights_status=RightsStatus.PUBLIC_DOMAIN,
            publisher_evidence_verifier=verifier,
        )
        self.assertEqual(decision.verdict, GATE_UNLOCATED)


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


class GateNoColonKeyTests(TestCase):
    """Edge case: a canonical_key with no ':' uses the whole key as the section id.

    ``section_id = canonical_key.split(":", 1)[-1]`` yields the full key when
    there is no colon, so the heading fallback then searches for the whole key
    as a word-boundary token. Production keys always carry a prefix colon, but
    the verify path must still behave sanely if one does not.
    """

    def test_no_colon_key_exact_match_ok(self):
        """A colon-less key still verifies via an exact section-key match."""
        decision = AuthorityGateService.evaluate(
            canonical_key="fedreg",
            sections=[_section(key="fedreg")],
            provider_license="public-domain",
        )
        self.assertEqual(decision.verdict, GATE_OK)
        self.assertEqual(decision.verify, "match")

    def test_no_colon_key_heading_fallback_matches(self):
        """With no exact key match, the whole colon-less key is the heading token."""
        decision = AuthorityGateService.evaluate(
            canonical_key="fedreg",
            sections=[_section(key="other", heading="See fedreg notice")],
            provider_license="public-domain",
        )
        self.assertEqual(decision.verdict, GATE_OK)
        self.assertEqual(decision.verify, "match")

    def test_no_colon_key_absent_everywhere_is_mismatch(self):
        """A colon-less key absent from both key and heading → UNLOCATED."""
        decision = AuthorityGateService.evaluate(
            canonical_key="fedreg",
            sections=[_section(key="other", heading="Unrelated heading")],
            provider_license="public-domain",
        )
        self.assertEqual(decision.verdict, GATE_UNLOCATED)
        self.assertEqual(decision.verify, "mismatch")

    def test_no_colon_key_substring_does_not_falsely_match(self):
        """Word-boundary matching still holds for a colon-less key.

        'fedreg' must NOT match a heading that only contains it as a substring
        of a longer token (e.g. 'fedregister').
        """
        decision = AuthorityGateService.evaluate(
            canonical_key="fedreg",
            sections=[_section(key="other", heading="fedregister daily edition")],
            provider_license="public-domain",
        )
        self.assertEqual(decision.verdict, GATE_UNLOCATED)
        self.assertEqual(decision.verify, "mismatch")
