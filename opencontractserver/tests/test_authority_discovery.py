"""Tests for Phase 3 authority discovery orchestration.

Covers:
- find_authority_target cross-namespace equivalence hop
- AuthorityDiscoveryService.discover_and_bootstrap via patched provider
- End-to-end EXTERNAL -> RESOLVED payoff via equivalence-aware relink
- Unsupported key handling
"""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase

from opencontractserver.annotations.models import (
    SPAN_LABEL,
    Annotation,
    AuthorityFrontier,
    AuthorityKeyEquivalence,
    CorpusReference,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.authorities import (
    AuthoritySection,
    bootstrap_authority_corpus,
    find_authority_target,
)
from opencontractserver.enrichment.services import AuthorityDiscoveryService

User = get_user_model()

# ---------------------------------------------------------------------------
# Minimal USLM XML fixtures (no network required)
# ---------------------------------------------------------------------------

# Used in tests 2 and 4 (usc-15:2 / unsupported)
USC_SECTION_FIXTURE = b"""<?xml version="1.0" encoding="UTF-8"?>
<uscDoc xmlns="http://xml.house.gov/schemas/uslm/1.0" identifier="/us/usc/t15">
  <main>
    <title identifier="/us/usc/t15">
      <num value="15">Title 15-</num>
      <heading>COMMERCE AND TRADE</heading>
      <section identifier="/us/usc/t15/s2">
        <num value="2">2.</num>
        <heading>Monopolizing trade a felony; penalty</heading>
        <content>
          <p class="indent0">Every person who shall monopolize, or attempt to
          monopolize trade shall be guilty.</p>
        </content>
      </section>
    </title>
  </main>
</uscDoc>"""

# Used in test 3 (exchange-act:10(b) -> usc-15:78j)
USC_78J_FIXTURE = b"""<?xml version="1.0" encoding="UTF-8"?>
<uscDoc xmlns="http://xml.house.gov/schemas/uslm/1.0" identifier="/us/usc/t15">
  <main>
    <title identifier="/us/usc/t15">
      <num value="15">Title 15-</num>
      <heading>COMMERCE AND TRADE</heading>
      <section identifier="/us/usc/t15/s78j">
        <num value="78j">78j.</num>
        <heading>Manipulative and deceptive devices</heading>
        <content>
          <p class="indent0">It shall be unlawful for any person to use any
          manipulative or deceptive device.</p>
        </content>
      </section>
    </title>
  </main>
</uscDoc>"""


def _create_user(username: str):
    return User.objects.create_user(username=username, password="p")


def _ensure_exchange_act_10_equiv():
    """Ensure the exchange-act:10 <-> usc-15:78j equivalence exists.

    The 0087 migration seeds these when --create-db is used.  When the DB
    is reused the rows already exist.  This helper is a safety net so tests
    pass in either case.
    """
    AuthorityKeyEquivalence.objects.get_or_create(
        from_key="exchange-act:10",
        to_key="usc-15:78j",
        defaults={"source": "manual", "confidence": 1.0},
    )


class FindAuthorityTargetEquivalenceHopTests(TransactionTestCase):
    """Test 1: find_authority_target resolves act-section -> USC via equiv table."""

    def test_cross_namespace_hop(self):
        """exchange-act:10(b) resolves to the usc-15:78j document."""
        user = _create_user("equiv-hop-user")
        _ensure_exchange_act_10_equiv()

        section = AuthoritySection(
            key="usc-15:78j",
            heading="Manipulative and deceptive devices",
            text="It shall be unlawful...",
        )
        result = bootstrap_authority_corpus(
            creator_id=user.id,
            corpus_title="USC Title 15",
            sections=[section],
            make_public=True,
            relink=False,
        )
        corpus = Corpus.objects.get(pk=result["corpus_id"])
        doc = Document.objects.get(custom_meta__canonical_key="usc-15:78j")

        # bootstrap_authority_corpus creates DocumentPath rows; verify one
        # is_current so find_authority_target can find it.
        self.assertTrue(
            DocumentPath.objects.filter(
                document=doc, corpus=corpus, is_current=True, is_deleted=False
            ).exists(),
            "bootstrap must create a current DocumentPath for the authority document",
        )

        # Act-section subsection key should hop to the USC doc.
        found = find_authority_target("exchange-act:10(b)", user)
        self.assertIsNotNone(found, "should resolve exchange-act:10(b) via equiv hop")
        assert found is not None  # narrow type for mypy
        self.assertEqual(found.pk, doc.pk)

    def test_direct_usc_key_still_works(self):
        """Direct usc-15:78j key resolves without needing the equiv hop."""
        user = _create_user("direct-usc-user")

        section = AuthoritySection(
            key="usc-15:78j",
            heading="Manipulative and deceptive devices",
            text="It shall be unlawful...",
        )
        bootstrap_authority_corpus(
            creator_id=user.id,
            corpus_title="USC Title 15",
            sections=[section],
            make_public=True,
            relink=False,
        )
        doc = Document.objects.get(custom_meta__canonical_key="usc-15:78j")
        found = find_authority_target("usc-15:78j", user)
        self.assertIsNotNone(found)
        assert found is not None  # narrow type for mypy
        self.assertEqual(found.pk, doc.pk)


class AuthorityDiscoveryServiceIngestTests(TransactionTestCase):
    """Test 2: orchestrator ingests a frontier row via a patched provider."""

    def test_ingest_via_provider(self):
        """discover_and_bootstrap fetches XML, creates document, marks ingested."""
        user = _create_user("ingest-user")

        frontier_row = AuthorityFrontier.objects.create(
            canonical_key="usc-15:2",
            authority="usc-15",
            jurisdiction=C.JURISDICTION_US_FEDERAL,
            authority_type=C.AUTHORITY_TYPE_STATUTE,
            discovery_state="queued",
        )

        with patch(
            "opencontractserver.pipeline.authority_source_providers"
            ".us_code_provider.USCodeAuthoritySourceProvider._load_title_xml",
            return_value=USC_SECTION_FIXTURE,
        ):
            result = AuthorityDiscoveryService.discover_and_bootstrap(
                creator_id=user.id,
                frontier_row=frontier_row,
                make_public=True,
                relink_async=False,
            )

        self.assertEqual(result["status"], "ingested", result)

        # The authority document must exist with the correct canonical key.
        self.assertTrue(
            Document.objects.filter(custom_meta__canonical_key="usc-15:2").exists(),
            "authority document for usc-15:2 must be created",
        )

        # Frontier row must be marked ingested.
        frontier_row.refresh_from_db()
        self.assertEqual(frontier_row.discovery_state, "ingested")

    def test_ingest_sets_provider_field(self):
        """The frontier row's provider field is populated before ingestion."""
        user = _create_user("ingest-provider-user")

        frontier_row = AuthorityFrontier.objects.create(
            canonical_key="usc-15:2",
            authority="usc-15",
            discovery_state="queued",
        )

        with patch(
            "opencontractserver.pipeline.authority_source_providers"
            ".us_code_provider.USCodeAuthoritySourceProvider._load_title_xml",
            return_value=USC_SECTION_FIXTURE,
        ):
            AuthorityDiscoveryService.discover_and_bootstrap(
                creator_id=user.id,
                frontier_row=frontier_row,
                make_public=True,
                relink_async=False,
            )

        frontier_row.refresh_from_db()
        # Provider field must be set to the provider's name (class name).
        self.assertIsNotNone(frontier_row.provider)
        self.assertNotEqual(frontier_row.provider, "")


class EndToEndResolvePayoffTests(TransactionTestCase):
    """Test 3: act-section EXTERNAL ref upgrades to RESOLVED after bootstrap."""

    def test_exchange_act_ref_resolves(self):
        """exchange-act:10(b) CorpusReference becomes RESOLVED after usc-15:78j ingest."""
        _ensure_exchange_act_10_equiv()

        # --- filing corpus with an EXTERNAL reference to exchange-act:10(b) ---
        filing_user = _create_user("filing-user")
        corpus = Corpus.objects.create(title="Filing Corpus", creator=filing_user)
        doc = Document.objects.create(title="Filing Doc", creator=filing_user)
        DocumentPath.objects.create(
            document=doc,
            corpus=corpus,
            path="/filing/doc.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=filing_user,
        )
        label = corpus.ensure_label_and_labelset(
            label_text=C.LABEL_REF_LAW, creator_id=filing_user.id, label_type=SPAN_LABEL
        )
        ann = Annotation.objects.create(
            raw_text="exchange-act:10(b)",
            page=1,
            json={"start": 0, "end": len("exchange-act:10(b)")},
            annotation_label=label,
            document=doc,
            corpus=corpus,
            creator=filing_user,
            annotation_type=SPAN_LABEL,
        )
        ref = CorpusReference.objects.create(
            corpus=corpus,
            reference_type=C.REF_LAW,
            source_annotation=ann,
            canonical_key="exchange-act:10(b)",
            resolution_status=C.STATUS_EXTERNAL,
            jurisdiction=C.JURISDICTION_US_FEDERAL,
            authority_type=C.AUTHORITY_TYPE_STATUTE,
            creator=filing_user,
        )

        # --- authority user + frontier row ---
        auth_user = _create_user("auth-user")
        frontier_row = AuthorityFrontier.objects.create(
            canonical_key="usc-15:78j",
            authority="usc-15",
            jurisdiction=C.JURISDICTION_US_FEDERAL,
            authority_type=C.AUTHORITY_TYPE_STATUTE,
            discovery_state="queued",
        )

        with patch(
            "opencontractserver.pipeline.authority_source_providers"
            ".us_code_provider.USCodeAuthoritySourceProvider._load_title_xml",
            return_value=USC_78J_FIXTURE,
        ):
            result = AuthorityDiscoveryService.discover_and_bootstrap(
                creator_id=auth_user.id,
                frontier_row=frontier_row,
                make_public=True,
                relink_async=False,
            )

        self.assertEqual(result["status"], "ingested", result)

        # The CorpusReference must now be RESOLVED.
        ref.refresh_from_db()
        self.assertEqual(
            ref.resolution_status,
            C.STATUS_RESOLVED,
            "exchange-act:10(b) CorpusReference must upgrade to RESOLVED",
        )
        self.assertIsNotNone(
            ref.target_document,
            "target_document must be set on the resolved CorpusReference",
        )

        # target_document must be the usc-15:78j authority document.
        assert ref.target_document is not None  # narrow type for mypy
        target_key = ref.target_document.custom_meta.get("canonical_key")
        self.assertEqual(target_key, "usc-15:78j")


class UnsupportedKeyTests(TransactionTestCase):
    """Test 4: discovery marks unsupported for keys with no matching provider."""

    def test_unsupported_key(self):
        """A key with no provider is marked unsupported."""
        user = _create_user("unsupported-user")

        frontier_row = AuthorityFrontier.objects.create(
            canonical_key="mystery-zz:1",
            authority="mystery-zz",
            discovery_state="queued",
        )

        result = AuthorityDiscoveryService.discover_and_bootstrap(
            creator_id=user.id,
            frontier_row=frontier_row,
            make_public=True,
            relink_async=False,
        )

        self.assertEqual(result["status"], "unsupported")
        frontier_row.refresh_from_db()
        self.assertEqual(frontier_row.discovery_state, "unsupported")


class ProviderForEquivalenceBridgeTests(TransactionTestCase):
    """`_provider_for` bridges a popular-name domain key (which no provider
    handles directly) to its provider-supported statutory equivalent — the
    namespace-gap fix. Without an equivalence the key stays unsupported."""

    def test_domain_key_bridges_to_supported_equivalent(self):
        """exchange-act:10 → usc-15:78j (handled by the US Code provider)."""
        _ensure_exchange_act_10_equiv()
        name, provider, fetch_key = AuthorityDiscoveryService._provider_for(
            "exchange-act:10"
        )
        self.assertIsNotNone(provider, "domain key should bridge to a provider")
        self.assertIsNotNone(name)
        self.assertEqual(fetch_key, "usc-15:78j")
        self.assertTrue(provider.can_handle(fetch_key))

    def test_direct_statutory_key_is_unchanged(self):
        """A directly-supported key fetches under itself (no bridge)."""
        name, provider, fetch_key = AuthorityDiscoveryService._provider_for(
            "usc-15:78j"
        )
        self.assertIsNotNone(provider)
        self.assertEqual(fetch_key, "usc-15:78j")

    def test_domain_key_without_equivalence_is_unsupported(self):
        """No provider and no equivalence → (None, None, None)."""
        name, provider, fetch_key = AuthorityDiscoveryService._provider_for(
            "mystery-zz:1"
        )
        self.assertIsNone(provider)
        self.assertIsNone(name)
        self.assertIsNone(fetch_key)


class FindAuthorityTargetMissingKeyTests(TransactionTestCase):
    """find_authority_target returns None for unknown keys with no equiv or doc."""

    def test_missing_key_returns_none(self):
        """A key with no document and no equivalence row must return None."""
        user = _create_user("missing-key-user")
        result = find_authority_target("unknown-act:999", user)
        self.assertIsNone(
            result, "find_authority_target must return None for an unknown key"
        )


class EquivalenceRelinkInResultTests(TransactionTestCase):
    """discover_and_bootstrap result includes equivalence_relink info."""

    def test_result_contains_equivalence_relink(self):
        """After successful ingest, result dict includes 'equivalence_relink' key."""
        _ensure_exchange_act_10_equiv()
        user = _create_user("relink-result-user")

        frontier_row = AuthorityFrontier.objects.create(
            canonical_key="usc-15:78j",
            authority="usc-15",
            jurisdiction=C.JURISDICTION_US_FEDERAL,
            authority_type=C.AUTHORITY_TYPE_STATUTE,
            discovery_state="queued",
        )

        with patch(
            "opencontractserver.pipeline.authority_source_providers"
            ".us_code_provider.USCodeAuthoritySourceProvider._load_title_xml",
            return_value=USC_78J_FIXTURE,
        ):
            result = AuthorityDiscoveryService.discover_and_bootstrap(
                creator_id=user.id,
                frontier_row=frontier_row,
                make_public=True,
                relink_async=False,
            )

        self.assertEqual(result["status"], "ingested", result)
        self.assertIn(
            "equivalence_relink",
            result,
            "result dict must contain 'equivalence_relink' key after ingest",
        )


class EmptyFetchMarksUnlocatedTests(TransactionTestCase):
    """discover_and_bootstrap marks frontier 'unlocated' when provider returns no sections.

    Behaviour changed in Phase 4: empty sections now flow through the gate and
    return status='unlocated' (GATE_UNLOCATED) rather than status='failed'.
    'unlocated' is a more precise audit state than 'failed' — it distinguishes
    "we found the provider but the section wasn't there" from a network/parse error.
    """

    def test_empty_fetch_marks_unlocated(self):
        """When provider._load_title_xml returns XML with no matching section, status=unlocated."""
        user = _create_user("empty-fetch-user")

        frontier_row = AuthorityFrontier.objects.create(
            canonical_key="usc-15:9999",
            authority="usc-15",
            jurisdiction=C.JURISDICTION_US_FEDERAL,
            authority_type=C.AUTHORITY_TYPE_STATUTE,
            discovery_state="queued",
        )

        # USC_SECTION_FIXTURE only has section /us/usc/t15/s2 — not s9999.
        with patch(
            "opencontractserver.pipeline.authority_source_providers"
            ".us_code_provider.USCodeAuthoritySourceProvider._load_title_xml",
            return_value=USC_SECTION_FIXTURE,
        ):
            result = AuthorityDiscoveryService.discover_and_bootstrap(
                creator_id=user.id,
                frontier_row=frontier_row,
                make_public=True,
                relink_async=False,
            )

        # Phase 4: gate returns unlocated (not failed) for empty sections.
        self.assertEqual(result["status"], "unlocated", result)
        self.assertIn("reason", result)

        frontier_row.refresh_from_db()
        self.assertEqual(frontier_row.discovery_state, "unlocated")

        # No authority document should have been created for the missing section.
        self.assertFalse(
            Document.objects.filter(custom_meta__canonical_key="usc-15:9999").exists(),
            "no authority document should be created when provider returns no sections",
        )


class GateFailureDoesNotStrandTheFrontierRowTests(TransactionTestCase):
    """An unexpected exception in the gate section must not wedge the row.

    ``discover_and_bootstrap`` marks the row ``in_progress`` before fetching.
    The fetch and the bootstrap each have a fault handler; the stretch between
    them (approval fingerprint → gate → audit record) did not. Since
    ``dequeue_queued`` only ever returns ``queued`` rows, a row left
    ``in_progress`` is invisible to every later crawl until an admin resets it
    by hand — and the exception also aborts the whole crawl batch on its way
    out of ``crawl_authorities_service``.
    """

    def test_gate_exception_marks_failed_not_in_progress(self):
        user = _create_user("gate-fault-user")

        frontier_row = AuthorityFrontier.objects.create(
            canonical_key="usc-15:2",
            authority="usc-15",
            jurisdiction=C.JURISDICTION_US_FEDERAL,
            authority_type=C.AUTHORITY_TYPE_STATUTE,
            discovery_state="queued",
        )

        with patch(
            "opencontractserver.pipeline.authority_source_providers"
            ".us_code_provider.USCodeAuthoritySourceProvider._load_title_xml",
            return_value=USC_SECTION_FIXTURE,
        ), patch(
            "opencontractserver.enrichment.services.authority_gate_service"
            ".AuthorityGateService.evaluate",
            side_effect=RuntimeError("gate exploded"),
        ):
            result = AuthorityDiscoveryService.discover_and_bootstrap(
                creator_id=user.id,
                frontier_row=frontier_row,
                make_public=True,
                relink_async=False,
            )

        self.assertEqual(result["status"], C.DISCOVERY_STATE_FAILED, result)
        self.assertIn("gate exploded", result["error"])

        frontier_row.refresh_from_db()
        self.assertEqual(
            frontier_row.discovery_state,
            C.DISCOVERY_STATE_FAILED,
            "a gate fault must leave a terminal state, never in_progress",
        )
        # The failure is auditable: the handler builds its record from names
        # bound BEFORE the guarded block (merging it with the bootstrap handler
        # would raise UnboundLocalError on `decision` and re-strand the row).
        self.assertTrue(frontier_row.candidate_sources)
        last_record = frontier_row.candidate_sources[-1]
        self.assertEqual(last_record["outcome"], C.DISCOVERY_STATE_FAILED)
        self.assertIn("gate exploded", last_record["error"])

        self.assertFalse(
            Document.objects.filter(custom_meta__canonical_key="usc-15:2").exists(),
            "nothing may be ingested when the gate never returned a verdict",
        )


class IngestedDocumentPopulatedTests(TransactionTestCase):
    """After successful ingest, frontier row's ingested_document is set."""

    def test_ingested_document_populated(self):
        """frontier_row.ingested_document is set to the created authority Document."""
        user = _create_user("ingested-doc-user")

        frontier_row = AuthorityFrontier.objects.create(
            canonical_key="usc-15:2",
            authority="usc-15",
            jurisdiction=C.JURISDICTION_US_FEDERAL,
            authority_type=C.AUTHORITY_TYPE_STATUTE,
            discovery_state="queued",
        )

        with patch(
            "opencontractserver.pipeline.authority_source_providers"
            ".us_code_provider.USCodeAuthoritySourceProvider._load_title_xml",
            return_value=USC_SECTION_FIXTURE,
        ):
            result = AuthorityDiscoveryService.discover_and_bootstrap(
                creator_id=user.id,
                frontier_row=frontier_row,
                make_public=True,
                relink_async=False,
            )

        self.assertEqual(result["status"], "ingested", result)

        frontier_row.refresh_from_db()
        # ingested_document must be set.
        self.assertIsNotNone(
            frontier_row.ingested_document,
            "frontier_row.ingested_document must be set after successful ingest",
        )
        # It must point to the authority document with the correct canonical key.
        assert frontier_row.ingested_document is not None  # narrow for mypy
        key = frontier_row.ingested_document.custom_meta.get("canonical_key")
        self.assertEqual(key, "usc-15:2")


# ---------------------------------------------------------------------------
# Phase 4 gate integration tests
# ---------------------------------------------------------------------------

USC_15_2_SECTIONS = [
    AuthoritySection(
        key="usc-15:2",
        heading="Monopolizing trade a felony; penalty",
        text="Every person who shall monopolize...",
        source_url="https://uscode.house.gov/download/t15.zip",
    )
]

USC_78J_SECTIONS = [
    AuthoritySection(
        key="usc-15:78j",
        heading="Manipulative and deceptive devices",
        text="It shall be unlawful...",
        source_url="https://uscode.house.gov/download/t15.zip",
    )
]

MISMATCHED_SECTIONS = [
    AuthoritySection(
        key="usc-15:99z",
        heading="Some unrelated section",
        text="Text with no relation.",
        source_url="https://uscode.house.gov/download/t15.zip",
    )
]


class GateLicenseBlockedIntegrationTests(TransactionTestCase):
    """Gate blocks discovery when provider license is not public-domain."""

    def test_license_blocked_records_state(self):
        """Provider with non-public-domain license → frontier gets blocked_license."""
        user = _create_user("gate-license-user")

        frontier_row = AuthorityFrontier.objects.create(
            canonical_key="usc-15:2",
            authority="usc-15",
            jurisdiction=C.JURISDICTION_US_FEDERAL,
            authority_type=C.AUTHORITY_TYPE_STATUTE,
            discovery_state="queued",
        )

        # Patch provider to return a non-public-domain license and valid sections.
        with patch(
            "opencontractserver.pipeline.authority_source_providers"
            ".us_code_provider.USCodeAuthoritySourceProvider._load_title_xml",
            return_value=USC_SECTION_FIXTURE,
        ), patch(
            "opencontractserver.pipeline.authority_source_providers"
            ".us_code_provider.USCodeAuthoritySourceProvider.license",
            new="licensed",
        ):
            result = AuthorityDiscoveryService.discover_and_bootstrap(
                creator_id=user.id,
                frontier_row=frontier_row,
                make_public=True,
                relink_async=False,
            )

        self.assertEqual(result["status"], "blocked_license", result)

        frontier_row.refresh_from_db()
        self.assertEqual(frontier_row.discovery_state, "blocked_license")
        self.assertGreater(len(frontier_row.candidate_sources), 0)
        self.assertEqual(
            frontier_row.candidate_sources[-1]["outcome"], "blocked_license"
        )


class GateCitationMismatchIntegrationTests(TransactionTestCase):
    """Gate blocks when fetched section key doesn't match requested key."""

    def test_mismatch_records_unlocated(self):
        """Provider returns sections with wrong key → frontier gets unlocated with mismatch."""
        user = _create_user("gate-mismatch-user")

        frontier_row = AuthorityFrontier.objects.create(
            canonical_key="usc-15:78j",
            authority="usc-15",
            jurisdiction=C.JURISDICTION_US_FEDERAL,
            authority_type=C.AUTHORITY_TYPE_STATUTE,
            discovery_state="queued",
        )

        # Patch fetch() to return a section with a wrong key (not 78j), bypassing
        # the empty-sections path so we exercise the key-mismatch branch.
        with patch(
            "opencontractserver.pipeline.authority_source_providers"
            ".us_code_provider.USCodeAuthoritySourceProvider.fetch",
            return_value=MISMATCHED_SECTIONS,
        ):
            result = AuthorityDiscoveryService.discover_and_bootstrap(
                creator_id=user.id,
                frontier_row=frontier_row,
                make_public=True,
                relink_async=False,
            )

        self.assertEqual(result["status"], "unlocated", result)

        frontier_row.refresh_from_db()
        self.assertEqual(frontier_row.discovery_state, "unlocated")
        self.assertGreater(len(frontier_row.candidate_sources), 0)
        self.assertEqual(frontier_row.candidate_sources[-1]["verify"], "mismatch")


class GateHappyPathIntegrationTests(TransactionTestCase):
    """Gate passes for valid public-domain sections with matching key."""

    def test_happy_path_gate_passes_and_records(self):
        """Provider returns matching section → frontier ingested with verify=match."""
        user = _create_user("gate-happy-user")

        frontier_row = AuthorityFrontier.objects.create(
            canonical_key="usc-15:2",
            authority="usc-15",
            jurisdiction=C.JURISDICTION_US_FEDERAL,
            authority_type=C.AUTHORITY_TYPE_STATUTE,
            discovery_state="queued",
        )

        # USC_SECTION_FIXTURE has section usc-15:2.
        with patch(
            "opencontractserver.pipeline.authority_source_providers"
            ".us_code_provider.USCodeAuthoritySourceProvider._load_title_xml",
            return_value=USC_SECTION_FIXTURE,
        ):
            result = AuthorityDiscoveryService.discover_and_bootstrap(
                creator_id=user.id,
                frontier_row=frontier_row,
                make_public=True,
                relink_async=False,
            )

        self.assertEqual(result["status"], "ingested", result)

        frontier_row.refresh_from_db()
        self.assertEqual(frontier_row.discovery_state, "ingested")
        self.assertGreater(len(frontier_row.candidate_sources), 0)
        last = frontier_row.candidate_sources[-1]
        self.assertEqual(last["outcome"], "ingested")
        self.assertEqual(last["verify"], "match")


# ---------------------------------------------------------------------------
# Phase 4 hardening tests
# ---------------------------------------------------------------------------


class FetchFailureAuditTests(TransactionTestCase):
    """Fetch errors are recorded in candidate_sources with outcome='failed'."""

    def test_httpx_error_records_audit_trail(self):
        """When provider.fetch raises an httpx error, frontier state=failed and
        candidate_sources[-1]['outcome']=='failed'."""
        import httpx

        user = _create_user("fetch-fail-audit-user")

        frontier_row = AuthorityFrontier.objects.create(
            canonical_key="usc-15:2",
            authority="usc-15",
            jurisdiction=C.JURISDICTION_US_FEDERAL,
            authority_type=C.AUTHORITY_TYPE_STATUTE,
            discovery_state="queued",
        )

        with patch(
            "opencontractserver.pipeline.authority_source_providers"
            ".us_code_provider.USCodeAuthoritySourceProvider._load_title_xml",
            side_effect=httpx.ConnectError("connection refused"),
        ):
            result = AuthorityDiscoveryService.discover_and_bootstrap(
                creator_id=user.id,
                frontier_row=frontier_row,
                make_public=True,
                relink_async=False,
            )

        self.assertEqual(result["status"], "failed", result)

        frontier_row.refresh_from_db()
        self.assertEqual(frontier_row.discovery_state, "failed")
        self.assertGreater(
            len(frontier_row.candidate_sources or []),
            0,
            "candidate_sources must record the failed attempt",
        )
        last = frontier_row.candidate_sources[-1]
        self.assertEqual(last["outcome"], "failed")
        self.assertIn("error", last)
        self.assertTrue(last["error"])


class DisabledAgenticUnsupportedTests(TransactionTestCase):
    """When agentic provider is disabled (default) and no deterministic provider
    can handle a key, discovery returns 'unsupported'."""

    def test_disabled_agentic_does_not_handle_unknown_key(self):
        """act:obscure-thing:1 is not handled by USC/CFR/FR providers, and the
        agentic provider is disabled by default — so result is unsupported."""
        user = _create_user("disabled-agentic-user")

        frontier_row = AuthorityFrontier.objects.create(
            canonical_key="act:obscure-thing:1",
            authority="act",
            jurisdiction=C.JURISDICTION_US_FEDERAL,
            authority_type=C.AUTHORITY_TYPE_STATUTE,
            discovery_state="queued",
        )

        result = AuthorityDiscoveryService.discover_and_bootstrap(
            creator_id=user.id,
            frontier_row=frontier_row,
            make_public=True,
            relink_async=False,
        )

        self.assertEqual(result["status"], "unsupported", result)

        frontier_row.refresh_from_db()
        self.assertEqual(frontier_row.discovery_state, "unsupported")


class IngestedCandidateRecordAuditTests(TransactionTestCase):
    """After successful ingest, candidate_sources[-1]['outcome'] == 'ingested'."""

    def test_ingested_outcome_in_candidate_sources(self):
        """Happy-path ingest sets candidate_sources[-1]['outcome']=='ingested'."""
        user = _create_user("ingested-audit-user")

        frontier_row = AuthorityFrontier.objects.create(
            canonical_key="usc-15:2",
            authority="usc-15",
            jurisdiction=C.JURISDICTION_US_FEDERAL,
            authority_type=C.AUTHORITY_TYPE_STATUTE,
            discovery_state="queued",
        )

        with patch(
            "opencontractserver.pipeline.authority_source_providers"
            ".us_code_provider.USCodeAuthoritySourceProvider._load_title_xml",
            return_value=USC_SECTION_FIXTURE,
        ):
            result = AuthorityDiscoveryService.discover_and_bootstrap(
                creator_id=user.id,
                frontier_row=frontier_row,
                make_public=True,
                relink_async=False,
            )

        self.assertEqual(result["status"], "ingested", result)

        frontier_row.refresh_from_db()
        self.assertGreater(
            len(frontier_row.candidate_sources or []),
            0,
            "candidate_sources must be populated after ingest",
        )
        last = frontier_row.candidate_sources[-1]
        self.assertEqual(last["outcome"], "ingested")
        self.assertIn("attempted_at", last)
        self.assertIsNotNone(last.get("license"))
