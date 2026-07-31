"""Canonical-identity invariants for sideloading authority corpus exports."""

from __future__ import annotations

import io
import zipfile

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from opencontractserver.annotations.models import (
    AuthorityNamespace,
    AuthorityRelationship,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import (
    Document,
    DocumentPath,
    PendingDocumentAnnotations,
)
from opencontractserver.extracts.models import Datacell
from opencontractserver.tasks.import_tasks_v2 import (
    _canonical_identity_target_path,
    _import_document_with_annotations,
    _reconcile_imported_authority_metadata,
)
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class AuthorityTargetedImportTests(TestCase):
    canonical_key = "example-rule:1"
    seed_path = "/documents/[LEGAL_REVIEW_REQUIRED]_Example_Rule"
    member_name = "Publisher_Clean_Title"
    incoming_bytes = b"publisher source version two"

    def _seed(self, suffix: str) -> tuple[Corpus, Document, DocumentPath]:
        user = User.objects.create_user(
            username=f"targeted-import-{suffix}", password="test"
        )
        corpus = Corpus.objects.create(
            title=f"Target Authority {suffix}",
            creator=user,
        )
        set_permissions_for_obj_to_user(user, corpus, [PermissionTypes.ALL])
        document, status, path = corpus.import_content(
            content=b"pack seed version one",
            user=user,
            path=self.seed_path,
            file_type="text/plain",
            title="[LEGAL REVIEW REQUIRED] Example Rule",
            custom_meta={
                "canonical_key": self.canonical_key,
                "current_version": True,
                "status": "CURRENT",
                "curator_note": "preserve me",
            },
            processing_started=timezone.now(),
        )
        self.assertEqual(status, "created")
        return corpus, document, path

    def _doc_data(self) -> dict:
        return {
            "title": "Publisher Clean Title",
            "description": "Fetched outside OpenContracts and sideloaded.",
            "content": self.incoming_bytes.decode("utf-8"),
            "pawls_file_content": [],
            "page_count": 0,
            "file_type": "text/plain",
            "custom_meta": {
                "canonical_key": self.canonical_key,
                "current_version": True,
                "status": "EFFECTIVE",
                "publisher": "Example Publisher",
            },
            "doc_labels": [],
            "labelled_text": [],
        }

    def _archive(self) -> tuple[io.BytesIO, zipfile.ZipFile]:
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr(self.member_name, self.incoming_bytes)
        payload.seek(0)
        return payload, zipfile.ZipFile(payload)

    def _exercise_targeted_path(self, *, reingest_and_remap: bool) -> None:
        corpus, prior_document, _prior_path = self._seed(
            "reingest" if reingest_and_remap else "baked"
        )
        user = corpus.creator
        doc_data = self._doc_data()
        payload, archive = self._archive()
        self.addCleanup(archive.close)
        self.addCleanup(payload.close)

        identity_path = _canonical_identity_target_path(
            corpus=corpus,
            doc_data=doc_data,
            targeted_import=True,
        )
        self.assertIsNotNone(identity_path)
        self.assertEqual(identity_path.path, self.seed_path)

        imported, _id_map = _import_document_with_annotations(
            doc_filename=self.member_name,
            doc_data=doc_data,
            import_zip=archive,
            user_obj=user,
            corpus_obj=corpus,
            label_lookup={},
            doc_label_lookup={},
            reingest_and_remap=reingest_and_remap,
            identity_target_path=identity_path,
        )
        self.assertIsNotNone(imported)
        imported = Document.objects.get(pk=imported.pk)

        current_path = DocumentPath.objects.get(
            corpus=corpus,
            is_current=True,
            is_deleted=False,
        )
        self.assertEqual(current_path.path, self.seed_path)
        self.assertEqual(current_path.version_number, 2)
        self.assertEqual(current_path.document_id, imported.pk)
        self.assertEqual(
            DocumentPath.objects.filter(
                corpus=corpus,
                path=f"/documents/{self.member_name}",
            ).count(),
            0,
        )
        self.assertEqual(
            Document.objects.filter(version_tree_id=imported.version_tree_id).count(),
            2,
        )
        self.assertEqual(imported.title, "Publisher Clean Title")
        self.assertEqual(imported.custom_meta["status"], "EFFECTIVE")
        self.assertEqual(imported.custom_meta["curator_note"], "preserve me")
        self.assertTrue(imported.custom_meta["current_version"])

        prior_document.refresh_from_db()
        self.assertFalse(prior_document.custom_meta["current_version"])

        # An identical sideload converges on the current version instead of
        # fabricating a sibling path or another content version.
        document_count = Document.objects.filter(
            version_tree_id=imported.version_tree_id
        ).count()
        path_count = DocumentPath.objects.filter(corpus=corpus).count()
        rerun_target = _canonical_identity_target_path(
            corpus=corpus,
            doc_data=doc_data,
            targeted_import=True,
        )
        rerun_document, _rerun_map = _import_document_with_annotations(
            doc_filename=self.member_name,
            doc_data=doc_data,
            import_zip=archive,
            user_obj=user,
            corpus_obj=corpus,
            label_lookup={},
            doc_label_lookup={},
            reingest_and_remap=reingest_and_remap,
            identity_target_path=rerun_target,
        )
        self.assertEqual(rerun_document.pk, imported.pk)
        self.assertEqual(
            Document.objects.filter(version_tree_id=imported.version_tree_id).count(),
            document_count,
        )
        self.assertEqual(
            DocumentPath.objects.filter(corpus=corpus).count(),
            path_count,
        )
        self.assertEqual(
            DocumentPath.objects.filter(
                corpus=corpus,
                is_current=True,
                is_deleted=False,
                path=self.seed_path,
            ).count(),
            1,
        )

        if reingest_and_remap:
            # The first content update is parser-bound; the identical rerun has
            # no parser dispatch and therefore records no standalone pending
            # row when this low-level helper is called without a run id.
            self.assertEqual(
                PendingDocumentAnnotations.objects.filter(document=imported).count(),
                0,
            )

    def test_baked_targeted_import_uses_canonical_identity_and_converges(self):
        self._exercise_targeted_path(reingest_and_remap=False)

    def test_reingest_targeted_import_uses_canonical_identity_and_converges(self):
        self._exercise_targeted_path(reingest_and_remap=True)


class AuthorityArchiveReconciliationTests(TestCase):
    """Archive metadata can mutate global authority state only when trusted."""

    def _document(
        self,
        *,
        user,
        corpus: Corpus,
        prefix: str,
        relationships: list[dict],
    ) -> Document:
        document = Document.objects.create(
            title="Imported authority",
            creator=user,
            file_type="text/plain",
            custom_meta={
                "canonical_key": f"{prefix}:1",
                "pack_origin": "trusted_pack",
                "status": "CURRENT",
                "current_version": True,
                "relationships": relationships,
            },
            processing_started=timezone.now(),
        )
        DocumentPath.objects.create(
            document=document,
            corpus=corpus,
            path="/documents/imported-authority",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=user,
        )
        return document

    def _bind_namespace(self, *, corpus: Corpus, prefix: str, user) -> None:
        AuthorityNamespace.objects.create(
            prefix=prefix,
            display_name=f"{prefix} authority",
            authority_type="regulation",
            source="manual",
            is_global=False,
            authority_corpus=corpus,
            created_by=user,
        )

    def test_corpus_with_no_bound_prefix_silently_skips_reconciliation(self):
        """Pin the silent skip, because it is invisible in a real deployment.

        The namespace gate is deliberate: an arbitrary corpus import must not be
        able to write global authority relationships just by putting a
        ``canonical_key`` in custom metadata. The cost is that a *trusted* pack
        which forgets to declare ``authority_prefixes`` for one of its corpora
        imports every document successfully, keeps every provider-authored edge
        in ``custom_meta["relationships"]``, and creates no
        ``AuthorityRelationship`` row at all — with no error, no warning, and no
        failing import.

        That is not hypothetical: it stranded 154 of 396 declared edges on the
        reference GridDossier deployment. The static guard against it is
        ``test_grid_dossier_authority_pack_data.py::
        test_every_declared_prefix_is_bound_to_exactly_one_pack_corpus``; this
        test exists so the skip itself stays a deliberate, documented property
        rather than a surprise.
        """
        admin = User.objects.create_superuser(
            username="archive-unbound-admin",
            email="archive-unbound@example.com",
            password="test",
        )
        corpus = Corpus.objects.create(title="Unbound target", creator=admin)
        prefix = "archive-unbound"
        # Deliberately NOT calling ``_bind_namespace``.
        document = self._document(
            user=admin,
            corpus=corpus,
            prefix=prefix,
            relationships=[
                {
                    "target_key": "archive-unbound-target:1",
                    "relationship_type": "FILED_IN",
                    "verified": False,
                    "metadata": {},
                }
            ],
        )

        _reconcile_imported_authority_metadata(
            corpus=corpus,
            documents=[document],
            user_obj=admin,
        )

        self.assertFalse(
            AuthorityRelationship.objects.filter(source_key=f"{prefix}:1").exists(),
            "An unbound prefix must not reach the global authority graph",
        )
        # The edge is not lost, only unpromoted — which is why the failure is
        # invisible without an explicit check.
        self.assertEqual(
            document.custom_meta["relationships"][0]["target_key"],
            "archive-unbound-target:1",
        )

    def test_non_admin_cannot_reconcile_typed_metadata_or_global_edges(self):
        user = User.objects.create_user(username="archive-non-admin", password="test")
        corpus = Corpus.objects.create(title="Untrusted target", creator=user)
        prefix = "archive-non-admin"
        self._bind_namespace(corpus=corpus, prefix=prefix, user=user)
        document = self._document(
            user=user,
            corpus=corpus,
            prefix=prefix,
            relationships=[
                {
                    "target_key": "archive-target:1",
                    "relationship_type": "CITES",
                    "verified": True,
                    "metadata": {},
                }
            ],
        )

        _reconcile_imported_authority_metadata(
            corpus=corpus,
            documents=[document],
            user_obj=user,
        )

        self.assertFalse(
            AuthorityRelationship.objects.filter(source_key=f"{prefix}:1").exists()
        )
        self.assertFalse(Datacell.objects.filter(document=document).exists())

    def test_admin_and_exact_namespace_gate_preserve_curated_ownership(self):
        admin = User.objects.create_superuser(
            username="archive-admin",
            email="archive-admin@example.com",
            password="test",
        )
        corpus = Corpus.objects.create(title="Trusted target", creator=admin)
        prefix = "archive-admin-test"
        source_key = f"{prefix}:1"
        self._bind_namespace(corpus=corpus, prefix=prefix, user=admin)
        baseline = AuthorityRelationship.objects.create(
            source_key=source_key,
            relationship_type="IMPLEMENTS",
            target_key="archive-baseline:1",
            source="baseline",
            origin="trusted_pack",
            verified=True,
            metadata={"owner": "baseline"},
        )
        manual = AuthorityRelationship.objects.create(
            source_key=source_key,
            relationship_type="CITES",
            target_key="archive-manual:1",
            source="manual",
            origin="curator",
            verified=True,
            metadata={"owner": "curator"},
        )
        document = self._document(
            user=admin,
            corpus=corpus,
            prefix=prefix,
            relationships=[
                {
                    "target_key": "archive-baseline:1",
                    "relationship_type": "IMPLEMENTS",
                    "verified": False,
                    "metadata": {"owner": "provider"},
                },
                {
                    "target_key": "archive-manual:1",
                    "relationship_type": "CITES",
                    "verified": False,
                    "metadata": {"owner": "provider"},
                },
                {
                    "target_key": "archive-provider:1",
                    "relationship_type": "AMENDS",
                    "verified": True,
                    "metadata": {"evidence": "publisher"},
                },
            ],
        )

        _reconcile_imported_authority_metadata(
            corpus=corpus,
            documents=[document, document],
            user_obj=admin,
        )

        baseline.refresh_from_db()
        manual.refresh_from_db()
        self.assertEqual(baseline.source, "baseline")
        self.assertTrue(baseline.verified)
        self.assertEqual(baseline.metadata, {"owner": "baseline"})
        self.assertEqual(manual.source, "manual")
        self.assertTrue(manual.verified)
        self.assertEqual(manual.metadata, {"owner": "curator"})
        provider = AuthorityRelationship.objects.get(
            source_key=source_key,
            relationship_type="AMENDS",
            target_key="archive-provider:1",
        )
        self.assertEqual(provider.source, "provider")
        self.assertEqual(provider.origin, "trusted_pack")
        self.assertTrue(provider.verified)
        self.assertEqual(
            Datacell.objects.get(
                document=document,
                column__name="canonical_key",
            ).data,
            {"value": source_key},
        )
