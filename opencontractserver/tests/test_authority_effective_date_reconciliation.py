"""Regression tests for authority effective-date metadata reconciliation."""

from __future__ import annotations

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from opencontractserver.documents.models import Document
from opencontractserver.enrichment.authorities import AuthorityCorpusBootstrapper
from opencontractserver.enrichment.authority_sources import (
    AuthorityPublisherEvidence,
    AuthoritySourceRecord,
    AuthorityWeight,
    InstrumentType,
    PublisherEvidenceSource,
    RightsStatus,
    SourceStatus,
)
from opencontractserver.extracts.models import Datacell

User = get_user_model()


class AuthorityEffectiveDateReconciliationTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="authority-reconcile-owner",
            is_usage_capped=False,
        )
        self.bootstrapper = AuthorityCorpusBootstrapper()

    def _record(
        self,
        key: str,
        *,
        current_version: bool | None,
        effective_from: str | None = None,
    ) -> AuthoritySourceRecord:
        return AuthoritySourceRecord(
            canonical_key=key,
            title=f"Authority {key}",
            source_url=f"https://example.test/authority/{key.replace(':', '-')}",
            source_identifier=key.replace(":", "-"),
            publisher="Test Authority",
            jurisdiction="us-test",
            authority_type="admin-rule",
            instrument_type=InstrumentType.REGULATION,
            issued_date="2026-01-01",
            effective_from=effective_from,
            effective_until=None,
            status=SourceStatus.CURRENT,
            authority_weight=AuthorityWeight.CONTROLLING,
            parent_key=None,
            version_label="test",
            content=f"Text for {key}".encode(),
            mime_type="text/plain",
            corpus_slug="effective-date-reconciliation",
            current_version=current_version,
            rights_status=RightsStatus.REVIEW_REQUIRED,
            publisher_evidence=(
                AuthorityPublisherEvidence(
                    source=PublisherEvidenceSource.TITLE,
                    value="Test Authority",
                ),
            ),
        )

    def _bootstrap(self, *records: AuthoritySourceRecord):
        result = self.bootstrapper.bootstrap(
            creator_id=self.user.id,
            corpus_title="Effective Date Reconciliation",
            corpus_slug="effective-date-reconciliation",
            sections=records,
        )
        from opencontractserver.corpuses.models import Corpus

        return Corpus.objects.get(pk=result["corpus_id"])

    @staticmethod
    def _remove_derived_review_state(document: Document) -> None:
        metadata = dict(document.custom_meta or {})
        metadata.pop("effective_date_review_status", None)
        fields = metadata.get("authority_provider_fields", [])
        if isinstance(fields, list):
            metadata["authority_provider_fields"] = [
                field for field in fields if field != "effective_date_review_status"
            ]
        document.custom_meta = metadata
        document.save(update_fields=["custom_meta", "modified"])
        Datacell.objects.filter(
            document=document,
            column__name="effective_date_review_status",
            extract__isnull=True,
        ).delete()

    def test_backfills_only_missing_current_authority_review_states(self) -> None:
        corpus = self._bootstrap(
            self._record("test-rule:needs-review", current_version=None),
            self._record(
                "test-rule:has-effective-date",
                current_version=True,
                effective_from="2026-07-11",
            ),
            self._record("test-rule:historical", current_version=False),
            self._record("test-rule:curator-locked", current_version=True),
        )
        needs_review = Document.objects.get(
            custom_meta__canonical_key="test-rule:needs-review"
        )
        curator_locked = Document.objects.get(
            custom_meta__canonical_key="test-rule:curator-locked"
        )
        self._remove_derived_review_state(needs_review)
        self._remove_derived_review_state(curator_locked)
        curator_metadata = dict(curator_locked.custom_meta or {})
        curator_metadata["authority_curator_fields"] = ["effective_date_review_status"]
        curator_locked.custom_meta = curator_metadata
        curator_locked.save(update_fields=["custom_meta", "modified"])

        dry_summary = self.bootstrapper.reconcile_effective_date_review_states(
            corpus=corpus,
            user=self.user,
            dry_run=True,
        )
        self.assertEqual(dry_summary["authority_documents"], 4)
        self.assertEqual(dry_summary["would_update"], 1)
        self.assertEqual(dry_summary["updated"], 0)
        self.assertEqual(dry_summary["skipped_effective_date"], 1)
        self.assertEqual(dry_summary["skipped_historical"], 1)
        self.assertEqual(dry_summary["curator_preserved"], 1)
        needs_review.refresh_from_db()
        self.assertNotIn("effective_date_review_status", needs_review.custom_meta)

        applied_summary = self.bootstrapper.reconcile_effective_date_review_states(
            corpus=corpus,
            user=self.user,
        )
        self.assertEqual(applied_summary["would_update"], 1)
        self.assertEqual(applied_summary["updated"], 1)
        needs_review.refresh_from_db()
        self.assertEqual(
            needs_review.custom_meta["effective_date_review_status"],
            "UNKNOWN_NEEDS_REVIEW",
        )
        self.assertTrue(
            Datacell.objects.filter(
                document=needs_review,
                column__name="effective_date_review_status",
                data={"value": "UNKNOWN_NEEDS_REVIEW"},
                extract__isnull=True,
            ).exists()
        )

        idempotent_summary = self.bootstrapper.reconcile_effective_date_review_states(
            corpus=corpus,
            user=self.user,
        )
        self.assertEqual(idempotent_summary["would_update"], 0)
        self.assertEqual(idempotent_summary["updated"], 0)
        self.assertEqual(idempotent_summary["already_stated"], 1)

    def test_command_defaults_to_dry_run_then_applies(self) -> None:
        corpus = self._bootstrap(
            self._record("test-rule:command-needs-review", current_version=True)
        )
        document = Document.objects.get(
            custom_meta__canonical_key="test-rule:command-needs-review"
        )
        self._remove_derived_review_state(document)

        dry_output = StringIO()
        call_command(
            "reconcile_authority_effective_date_states",
            "--creator",
            self.user.username,
            "--corpus-slug",
            corpus.slug,
            stdout=dry_output,
        )
        document.refresh_from_db()
        self.assertNotIn("effective_date_review_status", document.custom_meta)
        self.assertIn("DRY RUN", dry_output.getvalue())
        self.assertIn("would_update=1", dry_output.getvalue())

        apply_output = StringIO()
        call_command(
            "reconcile_authority_effective_date_states",
            "--apply",
            "--creator",
            self.user.username,
            "--corpus-slug",
            corpus.slug,
            stdout=apply_output,
        )
        document.refresh_from_db()
        self.assertEqual(
            document.custom_meta["effective_date_review_status"],
            "UNKNOWN_NEEDS_REVIEW",
        )
        self.assertIn("APPLIED", apply_output.getvalue())
