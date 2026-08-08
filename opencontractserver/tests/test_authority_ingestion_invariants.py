"""Focused invariants for the shared authority-ingestion persistence path."""

from __future__ import annotations

from datetime import datetime, timezone

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from opencontractserver.annotations.models import AuthorityRelationship
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.documents.versioning import delete_document, import_document
from opencontractserver.enrichment.authorities import bootstrap_authority_corpus
from opencontractserver.enrichment.authority_sources import (
    AuthoritySourceRecord,
    AuthorityWeight,
    InstrumentType,
    RightsStatus,
    SourceRelationship,
    SourceStatus,
)
from opencontractserver.enrichment.services.authority_relationship_service import (
    AuthorityRelationshipService,
)
from opencontractserver.extracts.models import Datacell

User = get_user_model()


class AuthorityImportVersioningInvariantTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="authority-versioning", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Authority Corpus",
            creator=self.user,
            is_public=True,
        )

    def _import(self, **overrides):
        kwargs = {
            "corpus": self.corpus,
            "path": "/documents/authority.txt",
            "content": b"stable source bytes",
            "user": self.user,
            "file_type": "text/plain",
            "title": "Authority",
            "description": "Initial description",
            "custom_meta": {"canonical_key": "test-law:1", "status": "CURRENT"},
            "is_public": True,
            "external_id": "source-1",
            "ingestion_metadata": {"retrieved_at": "2026-07-25T00:00:00Z"},
        }
        kwargs.update(overrides)
        return import_document(**kwargs)

    def test_unchanged_bytes_are_a_true_noop_when_dedupe_is_enabled(self):
        document, _, path = self._import()

        same_document, status, same_path = self._import(
            skip_if_unchanged=True,
            record_metadata_event=True,
        )

        self.assertEqual(status, "unchanged")
        self.assertEqual(same_document.pk, document.pk)
        self.assertEqual(same_path.pk, path.pk)
        self.assertEqual(Document.objects.count(), 1)
        self.assertEqual(DocumentPath.objects.count(), 1)
        self.assertEqual(same_path.version_number, 1)

    def test_metadata_change_creates_same_version_path_event(self):
        document, _, old_path = self._import()

        same_document, status, metadata_path = self._import(
            title="Authority (official title)",
            custom_meta={
                "canonical_key": "test-law:1",
                "status": "EFFECTIVE",
            },
            ingestion_metadata={"retrieved_at": "2026-07-26T00:00:00Z"},
            skip_if_unchanged=True,
            record_metadata_event=True,
        )

        self.assertEqual(status, "metadata_updated")
        self.assertEqual(same_document.pk, document.pk)
        self.assertEqual(Document.objects.count(), 1)
        self.assertEqual(DocumentPath.objects.count(), 2)
        self.assertEqual(metadata_path.parent_id, old_path.pk)
        self.assertEqual(metadata_path.version_number, old_path.version_number)
        self.assertTrue(metadata_path.is_current)
        old_path.refresh_from_db()
        self.assertFalse(old_path.is_current)
        same_document.refresh_from_db()
        self.assertEqual(same_document.title, "Authority (official title)")
        self.assertEqual(same_document.custom_meta["status"], "EFFECTIVE")
        self.assertEqual(
            metadata_path.ingestion_metadata["retrieved_at"],
            "2026-07-26T00:00:00Z",
        )

    def test_metadata_change_can_update_in_place_without_an_audit_event(self):
        document, _, path = self._import()

        same_document, status, same_path = self._import(
            description="Corrected description",
            ingestion_metadata={"retrieved_at": "2026-07-27T00:00:00Z"},
            skip_if_unchanged=True,
            record_metadata_event=False,
        )

        self.assertEqual(status, "metadata_updated")
        self.assertEqual(same_document.pk, document.pk)
        self.assertEqual(same_path.pk, path.pk)
        self.assertEqual(Document.objects.count(), 1)
        self.assertEqual(DocumentPath.objects.count(), 1)
        same_document.refresh_from_db()
        same_path.refresh_from_db()
        self.assertEqual(same_document.description, "Corrected description")
        self.assertEqual(
            same_path.ingestion_metadata["retrieved_at"],
            "2026-07-27T00:00:00Z",
        )

    def test_dedupe_does_not_downgrade_public_visibility(self):
        document, _, _ = self._import()
        self.assertTrue(document.is_public)

        same_document, status, _ = self._import(
            description="Metadata-only correction",
            is_public=False,
            skip_if_unchanged=True,
            record_metadata_event=True,
        )

        self.assertEqual(status, "metadata_updated")
        same_document.refresh_from_db()
        self.assertTrue(same_document.is_public)

    def test_opt_in_dedupe_does_not_change_default_upload_versioning(self):
        first_document, _, first_path = self._import()

        second_document, status, second_path = self._import()

        self.assertEqual(status, "updated")
        self.assertNotEqual(second_document.pk, first_document.pk)
        self.assertEqual(second_document.parent_id, first_document.pk)
        self.assertEqual(second_path.parent_id, first_path.pk)
        self.assertEqual(second_path.version_number, 2)


class AuthoritySourceRecordVersioningInvariantTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="authority-source-record-versioning",
            password="test",
        )

    @staticmethod
    def _record(*, content: bytes, retrieved_at: datetime) -> AuthoritySourceRecord:
        return AuthoritySourceRecord(
            canonical_key="test-rule:1",
            title="Test Rule 1",
            source_url="https://example.gov/test-rule-1",
            source_identifier="test-rule-1",
            publisher="Example Authority",
            jurisdiction="us-test",
            authority_type="regulation",
            instrument_type=InstrumentType.REGULATION,
            issued_date=None,
            effective_from=None,
            effective_until=None,
            status=SourceStatus.CURRENT,
            authority_weight=AuthorityWeight.CONTROLLING,
            parent_key=None,
            version_label=None,
            content=content,
            mime_type="text/plain",
            corpus_slug="authority-source-versioning",
            retrieved_at=retrieved_at,
            current_version=True,
            rights_status=RightsStatus.PUBLIC_DOMAIN,
            extracted_text=content.decode("utf-8"),
        )

    def test_current_version_metadata_moves_with_changed_source_bytes(self):
        first = bootstrap_authority_corpus(
            creator_id=self.user.pk,
            corpus_title="Authority Source Versioning",
            corpus_slug="authority-source-versioning",
            sections=[
                self._record(
                    content=b"source version one",
                    retrieved_at=datetime(2026, 7, 24, tzinfo=timezone.utc),
                )
            ],
            relationship_origin="test-provider",
            relink=False,
        )
        first_document = Document.objects.get(pk=first["document_ids"][0])

        second = bootstrap_authority_corpus(
            creator_id=self.user.pk,
            corpus_title="Authority Source Versioning",
            corpus_slug="authority-source-versioning",
            sections=[
                self._record(
                    content=b"source version two",
                    retrieved_at=datetime(2026, 7, 25, tzinfo=timezone.utc),
                )
            ],
            relationship_origin="test-provider",
            relink=False,
        )
        second_document = Document.objects.get(pk=second["document_ids"][0])

        self.assertEqual(second["documents_updated"], 1)
        self.assertNotEqual(first_document.pk, second_document.pk)
        self.assertEqual(
            first_document.version_tree_id,
            second_document.version_tree_id,
        )
        first_document.refresh_from_db()
        second_document.refresh_from_db()
        self.assertFalse(first_document.is_current)
        self.assertTrue(second_document.is_current)
        self.assertIs(first_document.custom_meta["current_version"], False)
        self.assertIs(second_document.custom_meta["current_version"], True)

        typed_values = {
            datacell.document_id: datacell.data["value"]
            for datacell in Datacell.objects.filter(
                document_id__in=[first_document.pk, second_document.pk],
                column__name="current_version",
                extract=None,
            )
        }
        self.assertEqual(
            typed_values,
            {
                first_document.pk: False,
                second_document.pk: True,
            },
        )

        repeated = bootstrap_authority_corpus(
            creator_id=self.user.pk,
            corpus_title="Authority Source Versioning",
            corpus_slug="authority-source-versioning",
            sections=[
                self._record(
                    content=b"source version two",
                    retrieved_at=datetime(2026, 7, 25, tzinfo=timezone.utc),
                )
            ],
            relationship_origin="test-provider",
            relink=False,
        )
        self.assertEqual(repeated["documents_skipped"], 1)
        self.assertEqual(
            Document.objects.filter(
                version_tree_id=second_document.version_tree_id
            ).count(),
            2,
        )


class AuthorityRelationshipInvariantTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="authority-relationships", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Relationship Corpus",
            creator=self.user,
        )
        self.source_document, _, self.source_path = self._import_authority(
            key="source-law:1",
            path="/documents/source.txt",
            content=b"source version one",
        )
        self.target_document, _, self.target_path = self._import_authority(
            key="target-law:2",
            path="/documents/target.txt",
            content=b"target version one",
        )

    def _import_authority(self, *, key: str, path: str, content: bytes):
        return import_document(
            corpus=self.corpus,
            path=path,
            content=content,
            user=self.user,
            file_type="text/plain",
            title=key,
            custom_meta={"canonical_key": key},
        )

    @staticmethod
    def _declaration(
        *,
        verified: bool = False,
        metadata: dict[str, object] | None = None,
    ) -> SourceRelationship:
        return SourceRelationship(
            target_key="target-law:2",
            relationship_type="IMPLEMENTS",
            verified=verified,
            metadata=metadata or {},
        )

    def test_upsert_is_idempotent_and_document_independent(self):
        first = AuthorityRelationshipService.upsert_for_source(
            source_key="source-law:1",
            relationships=[self._declaration(metadata={"basis": "official"})],
            origin="test-pack",
            baseline=True,
        )
        second = AuthorityRelationshipService.upsert_for_source(
            source_key="source-law:1",
            relationships=[self._declaration(metadata={"basis": "official"})],
            origin="test-pack",
            baseline=True,
        )

        self.assertEqual(first["created"], 1)
        self.assertEqual(second["unchanged"], 1)
        self.assertEqual(AuthorityRelationship.objects.count(), 1)
        row = AuthorityRelationship.objects.get()
        self.assertEqual(row.source_key, "source-law:1")
        self.assertEqual(row.target_key, "target-law:2")

    def test_same_origin_writer_can_revoke_managed_verification(self):
        AuthorityRelationshipService.upsert_for_source(
            source_key="source-law:1",
            relationships=[self._declaration(verified=True)],
            origin="provider-a",
        )

        AuthorityRelationshipService.upsert_for_source(
            source_key="source-law:1",
            relationships=[self._declaration(verified=False)],
            origin="provider-a",
        )

        self.assertFalse(AuthorityRelationship.objects.get().verified)

    def test_managed_ownership_prevents_baseline_and_foreign_takeover(self):
        AuthorityRelationshipService.upsert_for_source(
            source_key="source-law:1",
            relationships=[self._declaration(verified=True)],
            origin="pack-a",
            baseline=True,
        )

        same_origin_provider = AuthorityRelationshipService.upsert_for_source(
            source_key="source-law:1",
            relationships=[self._declaration(verified=False)],
            origin="pack-a",
        )
        foreign_provider = AuthorityRelationshipService.upsert_for_source(
            source_key="source-law:1",
            relationships=[self._declaration(verified=False)],
            origin="provider-b",
        )

        baseline_row = AuthorityRelationship.objects.get(
            source_key="source-law:1",
            target_key="target-law:2",
        )
        self.assertEqual(same_origin_provider["preserved_baseline"], 1)
        self.assertEqual(foreign_provider["skipped_foreign"], 1)
        self.assertEqual(baseline_row.source, "baseline")
        self.assertEqual(baseline_row.origin, "pack-a")
        self.assertTrue(baseline_row.verified)

        provider_edge = SourceRelationship(
            target_key="target-law:3",
            relationship_type="IMPLEMENTS",
            verified=True,
        )
        AuthorityRelationshipService.upsert_for_source(
            source_key="source-law:1",
            relationships=[provider_edge],
            origin="provider-a",
        )
        foreign_takeover = AuthorityRelationshipService.upsert_for_source(
            source_key="source-law:1",
            relationships=[
                SourceRelationship(
                    target_key="target-law:3",
                    relationship_type="IMPLEMENTS",
                    verified=False,
                )
            ],
            origin="provider-b",
        )

        provider_row = AuthorityRelationship.objects.get(
            source_key="source-law:1",
            target_key="target-law:3",
        )
        self.assertEqual(foreign_takeover["skipped_foreign"], 1)
        self.assertEqual(provider_row.origin, "provider-a")
        self.assertTrue(provider_row.verified)

    def test_provider_replace_deletes_only_its_stale_source_slice(self):
        owned_stale = AuthorityRelationship.objects.create(
            source_key="source-law:1",
            relationship_type="CITES",
            target_key="stale-law:1",
            source="provider",
            origin="provider-a",
        )
        owned_current = AuthorityRelationship.objects.create(
            source_key="source-law:1",
            relationship_type="IMPLEMENTS",
            target_key="target-law:2",
            source="provider",
            origin="provider-a",
        )
        foreign = AuthorityRelationship.objects.create(
            source_key="source-law:1",
            relationship_type="CITES",
            target_key="foreign-law:1",
            source="provider",
            origin="provider-b",
        )
        baseline = AuthorityRelationship.objects.create(
            source_key="source-law:1",
            relationship_type="CITES",
            target_key="baseline-law:1",
            source="baseline",
            origin="pack-a",
        )
        manual = AuthorityRelationship.objects.create(
            source_key="source-law:1",
            relationship_type="CITES",
            target_key="manual-law:1",
            source="manual",
            origin="curator",
        )

        first = AuthorityRelationshipService.upsert_for_source(
            source_key="source-law:1",
            relationships=[self._declaration()],
            origin="provider-a",
            replace=True,
        )

        self.assertEqual(first["unchanged"], 1)
        self.assertEqual(first["deleted"], 1)
        self.assertFalse(
            AuthorityRelationship.objects.filter(pk=owned_stale.pk).exists()
        )
        self.assertTrue(
            AuthorityRelationship.objects.filter(pk=owned_current.pk).exists()
        )
        self.assertEqual(
            AuthorityRelationship.objects.filter(
                pk__in=[foreign.pk, baseline.pk, manual.pk]
            ).count(),
            3,
        )

        empty = AuthorityRelationshipService.upsert_for_source(
            source_key="source-law:1",
            relationships=[],
            origin="provider-a",
            replace=True,
        )

        self.assertEqual(empty["deleted"], 1)
        self.assertFalse(
            AuthorityRelationship.objects.filter(pk=owned_current.pk).exists()
        )
        self.assertEqual(
            AuthorityRelationship.objects.filter(
                pk__in=[foreign.pk, baseline.pk, manual.pk]
            ).count(),
            3,
        )

    def test_manual_relationship_fields_are_preserved(self):
        manual = AuthorityRelationship.objects.create(
            source_key="source-law:1",
            relationship_type="IMPLEMENTS",
            target_key="target-law:2",
            source="manual",
            origin="curator",
            verified=True,
            metadata={"note": "curated"},
        )

        result = AuthorityRelationshipService.upsert_for_source(
            source_key="source-law:1",
            relationships=[
                self._declaration(
                    verified=False,
                    metadata={"note": "provider", "new": "provider-value"},
                )
            ],
            origin="provider-a",
        )

        self.assertEqual(result["preserved_manual"], 1)
        manual.refresh_from_db()
        self.assertEqual(manual.source, "manual")
        self.assertEqual(manual.origin, "curator")
        self.assertTrue(manual.verified)
        self.assertEqual(manual.metadata, {"note": "curated"})

    def test_curator_metadata_overrides_survive_provider_refresh(self):
        AuthorityRelationship.objects.create(
            source_key="source-law:1",
            relationship_type="IMPLEMENTS",
            target_key="target-law:2",
            source="provider",
            origin="provider-a",
            metadata={
                "note": "curated",
                "curator_overrides": {"note": "curated"},
            },
        )

        AuthorityRelationshipService.upsert_for_source(
            source_key="source-law:1",
            relationships=[
                self._declaration(
                    metadata={"note": "provider", "new": "provider-value"}
                )
            ],
            origin="provider-a",
        )

        row = AuthorityRelationship.objects.get()
        self.assertEqual(row.metadata["note"], "curated")
        self.assertEqual(row.metadata["new"], "provider-value")
        self.assertEqual(row.metadata["curator_overrides"], {"note": "curated"})

    def test_pack_relationship_reload_removes_only_its_stale_baseline_edges(self):
        AuthorityRelationship.objects.create(
            source_key="source-law:1",
            relationship_type="CITES",
            target_key="stale-law:1",
            source="baseline",
            origin="test-pack",
        )
        foreign = AuthorityRelationship.objects.create(
            source_key="source-law:1",
            relationship_type="CITES",
            target_key="foreign-law:1",
            source="baseline",
            origin="other-pack",
        )
        manual = AuthorityRelationship.objects.create(
            source_key="source-law:1",
            relationship_type="CITES",
            target_key="manual-law:1",
            source="manual",
            origin="curator",
        )

        result = AuthorityRelationshipService.load_declarations(
            [
                {
                    "source_key": "source-law:1",
                    "relationship_type": "IMPLEMENTS",
                    "target_key": "target-law:2",
                    "verified": False,
                    "metadata": {},
                }
            ],
            origin="test-pack",
        )

        self.assertEqual(result["created"], 1)
        self.assertEqual(result["deleted"], 1)
        self.assertFalse(
            AuthorityRelationship.objects.filter(
                source_key="source-law:1",
                relationship_type="CITES",
                target_key="stale-law:1",
            ).exists()
        )
        self.assertEqual(
            AuthorityRelationship.objects.filter(
                pk__in=[foreign.pk, manual.pk]
            ).count(),
            2,
        )

    def test_empty_pack_baseline_removes_only_rows_owned_by_that_pack(self):
        owned = [
            AuthorityRelationship.objects.create(
                source_key="source-law:1",
                relationship_type="CITES",
                target_key=f"owned-law:{index}",
                source="baseline",
                origin="test-pack",
            )
            for index in (1, 2)
        ]
        manual = AuthorityRelationship.objects.create(
            source_key="source-law:1",
            relationship_type="CITES",
            target_key="manual-law:1",
            source="manual",
            origin="curator",
        )
        provider = AuthorityRelationship.objects.create(
            source_key="source-law:1",
            relationship_type="CITES",
            target_key="provider-law:1",
            source="provider",
            origin="test-pack",
        )
        foreign = AuthorityRelationship.objects.create(
            source_key="source-law:1",
            relationship_type="CITES",
            target_key="foreign-law:1",
            source="baseline",
            origin="other-pack",
        )

        result = AuthorityRelationshipService.load_declarations(
            [],
            origin="test-pack",
        )

        self.assertEqual(result["deleted"], 2)
        self.assertFalse(
            AuthorityRelationship.objects.filter(
                pk__in=[row.pk for row in owned]
            ).exists()
        )
        self.assertEqual(
            AuthorityRelationship.objects.filter(
                pk__in=[manual.pk, provider.pk, foreign.pk]
            ).count(),
            3,
        )

    def test_declaration_loader_rejects_truthy_non_boolean_verification(self):
        with self.assertRaisesMessage(
            ValueError, "verified must be true or false; got 'false'"
        ):
            AuthorityRelationshipService.load_declarations(
                [
                    {
                        "source_key": "source-law:1",
                        "relationship_type": "IMPLEMENTS",
                        "target_key": "target-law:2",
                        "verified": "false",
                        "metadata": {},
                    }
                ],
                origin="test-pack",
            )

        self.assertFalse(AuthorityRelationship.objects.exists())

    def test_relationship_identity_survives_document_version_and_deletion(self):
        AuthorityRelationshipService.upsert_for_source(
            source_key="source-law:1",
            relationships=[self._declaration()],
            origin="provider-a",
        )

        self._import_authority(
            key="target-law:2",
            path=self.target_path.path,
            content=b"target version two",
        )
        delete_document(
            corpus=self.corpus,
            path=self.target_path.path,
            user=self.user,
        )
        row = AuthorityRelationship.objects.get()
        self.assertEqual(row.source_key, "source-law:1")
        self.assertEqual(row.target_key, "target-law:2")

    def test_database_constraints_reject_duplicate_and_self_edges(self):
        AuthorityRelationship.objects.create(
            source_key="source-law:1",
            relationship_type="CITES",
            target_key="target-law:2",
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            AuthorityRelationship.objects.create(
                source_key="source-law:1",
                relationship_type="CITES",
                target_key="target-law:2",
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            AuthorityRelationship.objects.create(
                source_key="source-law:1",
                relationship_type="CITES",
                target_key="source-law:1",
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            AuthorityRelationship.objects.create(
                source_key="source-law:1",
                relationship_type="MADE_UP",
                target_key="target-law:3",
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            AuthorityRelationship.objects.create(
                source_key="source-law:1",
                relationship_type="CITES",
                target_key="target-law:4",
                source="unowned",
            )
