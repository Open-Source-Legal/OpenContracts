"""Rights, discovery-candidate handoff, and rich-record corpus routing."""

from __future__ import annotations

from typing import ClassVar
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.annotations.models import AuthorityFrontier
from opencontractserver.documents.models import Document
from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.authority_sources import (
    AuthorityPublisherEvidence,
    AuthoritySourceRecord,
    AuthorityWeight,
    InstrumentType,
    PublisherEvidenceSource,
    RightsStatus,
    SourceStatus,
)
from opencontractserver.enrichment.services.authority_discovery_service import (
    AuthorityDiscoveryService,
)
from opencontractserver.enrichment.services.authority_frontier_service import (
    AuthorityFrontierService,
)
from opencontractserver.pipeline.base.base_authority_discovery_provider import (
    DiscoveryCandidate,
)
from opencontractserver.pipeline.base.base_authority_source_provider import (
    AuthorityRequest,
    BaseAuthoritySourceProvider,
)

User = get_user_model()


class _RuntimeRichProvider(BaseAuthoritySourceProvider):
    title: str = "Runtime Rich Provider"
    supported_prefixes: ClassVar[tuple[str, ...]] = ("ex-docket",)
    license: ClassVar[str] = "mixed-review-required"

    def __init__(self, records: list[AuthoritySourceRecord]) -> None:
        self.records = records
        self.received_candidate: DiscoveryCandidate | None = None
        super().__init__()

    def _locate_impl(self, canonical_key: str, **all_kwargs) -> AuthorityRequest:
        self.received_candidate = all_kwargs.get("discovery_candidate")
        return AuthorityRequest(
            canonical_key=canonical_key,
            url=(
                self.received_candidate.url
                if self.received_candidate is not None
                else self.records[0].source_url
            ),
        )

    def _fetch_impl(
        self, request: AuthorityRequest, **all_kwargs
    ) -> list[AuthoritySourceRecord]:
        del request, all_kwargs
        return self.records

    def verify_publisher_evidence(
        self, canonical_key: str, record: AuthoritySourceRecord
    ) -> bool:
        return any(
            evidence.source == PublisherEvidenceSource.LISTING_METADATA
            and evidence.value == canonical_key
            for evidence in record.publisher_evidence
        )


def _record(
    *,
    canonical_key: str = "ex-docket:58211:item:4",
    rights_status: RightsStatus = RightsStatus.REVIEW_REQUIRED,
    corpus_slug: str = "example-utility-proceedings",
    source_url: str = "https://uscode.house.gov/authority-discovery-test.txt",
    content: bytes = b"Authority record test content",
) -> AuthoritySourceRecord:
    return AuthoritySourceRecord(
        canonical_key=canonical_key,
        title="Example Docket 58211 Item 4",
        source_url=source_url,
        source_identifier=canonical_key.rsplit(":", 1)[-1],
        publisher="Example Utility Commission",
        jurisdiction="us-tx",
        authority_type="admin-rule",
        instrument_type=InstrumentType.TESTIMONY,
        issued_date=None,
        effective_from=None,
        effective_until=None,
        status=SourceStatus.FILED,
        authority_weight=AuthorityWeight.EVIDENTIARY,
        parent_key="ex-docket:58211",
        version_label=None,
        content=content,
        mime_type="text/plain",
        corpus_slug=corpus_slug,
        rights_status=rights_status,
        extracted_text=content.decode("utf-8"),
        publisher_evidence=(
            AuthorityPublisherEvidence(
                source=PublisherEvidenceSource.LISTING_METADATA,
                value=canonical_key,
                locator=source_url,
            ),
        ),
    )


class AuthorityDiscoveryRuntimeTests(TestCase):
    provider_name: ClassVar[str] = "_RuntimeRichProvider"

    def setUp(self):
        self.user = User.objects.create_user(username="authority-runtime", password="p")

    def _frontier(self, *, approved: bool = False) -> AuthorityFrontier:
        candidate_sources: list[dict] = [
            {
                "discovery_provider": "ExampleDocketDiscoveryProvider",
                "url": "https://uscode.house.gov/authority-discovery-test.txt",
                "title": "Discovered docket attachment",
                "extra": {
                    "document_id": "attachment-4",
                    "discovery_mode": "link-only",
                },
            }
        ]
        if approved:
            approval_fingerprint = (
                AuthorityDiscoveryService._response_approval_fingerprint(
                    provider_name=self.provider_name,
                    fetch_key="ex-docket:58211:item:4",
                    request=AuthorityRequest(
                        canonical_key="ex-docket:58211:item:4",
                        url="https://uscode.house.gov/authority-discovery-test.txt",
                    ),
                    sections=[_record()],
                )
            )
            candidate_sources.append(
                {
                    "provider": self.provider_name,
                    "outcome": "approved",
                    "approval_scope": "authority-ingestion",
                    "approval_fingerprint": approval_fingerprint,
                    "approved_by": self.user.pk,
                    "approved_at": "2026-07-25T12:00:00+00:00",
                }
            )
        return AuthorityFrontier.objects.create(
            canonical_key="ex-docket:58211:item:4",
            authority="ex-docket",
            authority_type="admin-rule",
            discovery_state=C.DISCOVERY_STATE_QUEUED,
            candidate_sources=candidate_sources,
        )

    def test_review_required_record_parks_for_durable_approval(self):
        frontier = self._frontier()
        provider = _RuntimeRichProvider([_record()])
        with (
            patch.object(
                AuthorityDiscoveryService,
                "_provider_for",
                return_value=(
                    self.provider_name,
                    provider,
                    frontier.canonical_key,
                ),
            ),
            patch(
                "opencontractserver.enrichment.authorities.bootstrap_authority_corpus"
            ) as bootstrap,
        ):
            result = AuthorityDiscoveryService.discover_and_bootstrap(
                creator_id=self.user.pk,
                frontier_row=frontier,
                relink_async=False,
            )
        self.assertEqual(result["status"], C.DISCOVERY_STATE_PENDING_APPROVAL)
        bootstrap.assert_not_called()
        frontier.refresh_from_db()
        self.assertEqual(frontier.discovery_state, C.DISCOVERY_STATE_PENDING_APPROVAL)
        self.assertEqual(
            frontier.candidate_sources[-1]["rights_status"],
            RightsStatus.REVIEW_REQUIRED,
        )
        self.assertEqual(frontier.candidate_sources[-1]["discovery_mode"], "link-only")

    def test_approved_record_uses_discovered_url_declared_slug_and_exact_doc_id(self):
        frontier = self._frontier(approved=True)
        provider = _RuntimeRichProvider([_record()])
        document = Document.objects.create(
            title="Existing bootstrap result", creator=self.user
        )
        bootstrap_result = {
            "corpus_id": 91,
            "corpus_created": False,
            "documents_created": 1,
            "documents_updated": 0,
            "documents_skipped": 0,
            "documents_restamped": 0,
            "documents_metadata_updated": 0,
            "document_ids": [document.pk],
        }
        with (
            patch.object(
                AuthorityDiscoveryService,
                "_provider_for",
                return_value=(
                    self.provider_name,
                    provider,
                    frontier.canonical_key,
                ),
            ),
            patch(
                "opencontractserver.enrichment.authorities.bootstrap_authority_corpus",
                return_value=bootstrap_result,
            ) as bootstrap,
            patch(
                "opencontractserver.enrichment.services.enrichment_service."
                "EnrichmentService.relink_corpora_for_keys",
                return_value={"law_references_linked": 0},
            ),
        ):
            result = AuthorityDiscoveryService.discover_and_bootstrap(
                creator_id=self.user.pk,
                frontier_row=frontier,
                relink_async=False,
            )
        self.assertEqual(result["status"], C.DISCOVERY_STATE_INGESTED)
        received_candidate = provider.received_candidate
        self.assertIsNotNone(received_candidate)
        assert received_candidate is not None
        self.assertEqual(received_candidate.extra["document_id"], "attachment-4")
        self.assertEqual(
            bootstrap.call_args.kwargs["corpus_slug"],
            "example-utility-proceedings",
        )
        frontier.refresh_from_db()
        self.assertEqual(frontier.ingested_document_id, document.pk)

    def test_mixed_record_rights_are_rejected_even_with_approval(self):
        frontier = self._frontier(approved=True)
        provider = _RuntimeRichProvider(
            [
                _record(rights_status=RightsStatus.PUBLIC_DOMAIN),
                _record(
                    canonical_key="ex-docket:58211:item:4:attachment:2",
                    rights_status=RightsStatus.REVIEW_REQUIRED,
                ),
            ]
        )
        with (
            patch.object(
                AuthorityDiscoveryService,
                "_provider_for",
                return_value=(
                    self.provider_name,
                    provider,
                    frontier.canonical_key,
                ),
            ),
            patch(
                "opencontractserver.enrichment.authorities.bootstrap_authority_corpus"
            ) as bootstrap,
        ):
            result = AuthorityDiscoveryService.discover_and_bootstrap(
                creator_id=self.user.pk,
                frontier_row=frontier,
                relink_async=False,
            )
        self.assertEqual(result["status"], C.DISCOVERY_STATE_BLOCKED_LICENSE)
        self.assertIn("MIXED_RECORD_RIGHTS", result["reason"])
        bootstrap.assert_not_called()

    def test_link_only_record_stays_blocked_after_generic_approval(self):
        frontier = self._frontier(approved=True)
        provider = _RuntimeRichProvider([_record(rights_status=RightsStatus.LINK_ONLY)])
        with (
            patch.object(
                AuthorityDiscoveryService,
                "_provider_for",
                return_value=(
                    self.provider_name,
                    provider,
                    frontier.canonical_key,
                ),
            ),
            patch(
                "opencontractserver.enrichment.authorities.bootstrap_authority_corpus"
            ) as bootstrap,
        ):
            result = AuthorityDiscoveryService.discover_and_bootstrap(
                creator_id=self.user.pk,
                frontier_row=frontier,
                relink_async=False,
            )
        self.assertEqual(result["status"], C.DISCOVERY_STATE_BLOCKED_LICENSE)
        self.assertIn("link-only", result["reason"])
        bootstrap.assert_not_called()

    def test_changed_response_bytes_require_new_approval(self):
        frontier = self._frontier(approved=True)
        provider = _RuntimeRichProvider(
            [_record(content=b"Changed authority record bytes")]
        )
        with (
            patch.object(
                AuthorityDiscoveryService,
                "_provider_for",
                return_value=(self.provider_name, provider, frontier.canonical_key),
            ),
            patch(
                "opencontractserver.enrichment.authorities.bootstrap_authority_corpus"
            ) as bootstrap,
        ):
            result = AuthorityDiscoveryService.discover_and_bootstrap(
                creator_id=self.user.pk,
                frontier_row=frontier,
            )
        self.assertEqual(result["status"], C.DISCOVERY_STATE_PENDING_APPROVAL)
        bootstrap.assert_not_called()

    def test_changed_response_url_requires_new_approval(self):
        frontier = self._frontier(approved=True)
        provider = _RuntimeRichProvider(
            [
                _record(
                    source_url=(
                        "https://uscode.house.gov/authority-discovery-reseeded-test.txt"
                    )
                )
            ]
        )
        with (
            patch.object(
                AuthorityDiscoveryService,
                "_provider_for",
                return_value=(self.provider_name, provider, frontier.canonical_key),
            ),
            patch(
                "opencontractserver.enrichment.authorities.bootstrap_authority_corpus"
            ) as bootstrap,
        ):
            result = AuthorityDiscoveryService.discover_and_bootstrap(
                creator_id=self.user.pk,
                frontier_row=frontier,
            )
        self.assertEqual(result["status"], C.DISCOVERY_STATE_PENDING_APPROVAL)
        bootstrap.assert_not_called()

    def test_approval_fingerprint_is_response_order_invariant(self):
        request = AuthorityRequest(
            canonical_key="ex-docket:58211:item:4",
            url="https://uscode.house.gov/authority-discovery-test.txt",
        )
        first = _record()
        second = _record(
            canonical_key="ex-docket:58211:item:4:attachment:2",
        )
        left = AuthorityDiscoveryService._response_approval_fingerprint(
            provider_name=self.provider_name,
            fetch_key=request.canonical_key,
            request=request,
            sections=[first, second],
        )
        right = AuthorityDiscoveryService._response_approval_fingerprint(
            provider_name=self.provider_name,
            fetch_key=request.canonical_key,
            request=request,
            sections=[second, first],
        )
        self.assertEqual(left, right)

    def test_approve_writes_scoped_durable_audit_record(self):
        admin = User.objects.create_superuser(
            username="grid-admin", password="p", email="admin@example.com"
        )
        frontier = AuthorityFrontier.objects.create(
            canonical_key="ex-docket:58211:item:9",
            authority="ex-docket",
            provider=self.provider_name,
            discovery_state=C.DISCOVERY_STATE_PENDING_APPROVAL,
            candidate_sources=[
                {
                    "provider": self.provider_name,
                    "outcome": C.DISCOVERY_STATE_PENDING_APPROVAL,
                    "approval_fingerprint": "a" * 64,
                }
            ],
        )
        with patch.object(AuthorityFrontierService, "log_action"):
            outcome = AuthorityFrontierService.approve(admin, pk=frontier.pk)
        self.assertTrue(outcome.ok)
        frontier.refresh_from_db()
        self.assertEqual(frontier.discovery_state, C.DISCOVERY_STATE_QUEUED)
        approval = frontier.candidate_sources[-1]
        self.assertEqual(approval["provider"], self.provider_name)
        self.assertEqual(approval["outcome"], "approved")
        self.assertEqual(approval["approval_scope"], "authority-ingestion")
        self.assertEqual(approval["approval_fingerprint"], "a" * 64)
        self.assertEqual(approval["approved_by"], admin.pk)
        self.assertTrue(approval["approved_at"])
