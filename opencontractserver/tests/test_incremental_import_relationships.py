"""Incremental imports must resolve both sides of a cross-document edge."""

import io
import json
import uuid
import zipfile

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase
from django.utils import timezone

from opencontractserver.annotations.models import (
    RELATIONSHIP_LABEL,
    TOKEN_LABEL,
    Annotation,
    AnnotationLabel,
    LabelSet,
    Relationship,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import (
    DocumentPath,
    PendingCorpusImport,
    PendingDocumentAnnotations,
)
from opencontractserver.tasks.doc_tasks import (
    finalize_corpus_import_relationships,
    remap_pending_annotations,
)
from opencontractserver.tasks.import_tasks_v2 import _import_document_with_annotations
from opencontractserver.tests.test_import_v2_reingest_remap import _PAWLS_V1
from opencontractserver.utils.importing import import_annotations


class IncrementalRelationshipImportTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="pack-importer")
        labelset = LabelSet.objects.create(title="Pack labels", creator=self.user)
        self.label = AnnotationLabel.objects.create(
            text="CLAUSE", label_type=TOKEN_LABEL, creator=self.user
        )
        self.rel_label = AnnotationLabel.objects.create(
            text="references", label_type=RELATIONSHIP_LABEL, creator=self.user
        )
        labelset.annotation_labels.add(self.label, self.rel_label)
        self.corpus = Corpus.objects.create(
            title="Target pack", creator=self.user, label_set=labelset
        )
        self.labels = {"clause-label": self.label}
        self.a, self.ann_a = self._seed("a.txt", "Tenant pays rent.", "pays rent")
        self.b, self.ann_b = self._seed(
            "b.txt", "Landlord insures property.", "insures property"
        )

    def _annotation(self, export_id, content, phrase):
        start = content.index(phrase)
        return {
            "id": export_id,
            "annotationLabel": "clause-label",
            "rawText": phrase,
            "page": 0,
            "annotation_json": {
                "start": start,
                "end": start + len(phrase),
                "text": phrase,
            },
        }

    def _seed(self, filename, content, phrase, source=None):
        doc, _, _ = self.corpus.import_content(
            content=source if source is not None else content.encode(),
            user=self.user,
            filename=filename,
            path=f"/{filename}",
            title=filename,
            file_type="text/plain",
            processing_started=timezone.now(),
        )
        doc.txt_extract_file.save("text.txt", ContentFile(content.encode()))
        ids = import_annotations(
            user_id=self.user.pk,
            doc_obj=doc,
            corpus_obj=self.corpus,
            annotations_data=[self._annotation("old-id", content, phrase)],
            label_lookup=self.labels,
            dispatch_embeddings=False,
        )
        return doc, Annotation.objects.get(pk=ids["old-id"])

    def _refresh(
        self,
        doc,
        content,
        phrase,
        export_id,
        run_id,
        *,
        reingest=True,
        source=None,
        annotation=None,
    ):
        data = {
            "title": doc.title,
            "content": content,
            "file_type": doc.file_type,
            "pawls_file_content": [],
            "labelled_text": [
                annotation or self._annotation(export_id, content, phrase)
            ],
        }
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr(
                doc.title, source if source is not None else content.encode()
            )
        buffer.seek(0)
        with zipfile.ZipFile(buffer) as archive:
            imported, ids = _import_document_with_annotations(
                doc_filename=doc.title,
                doc_data=data,
                import_zip=archive,
                user_obj=self.user,
                corpus_obj=self.corpus,
                label_lookup=self.labels,
                doc_label_lookup={},
                reingest_and_remap=reingest,
                import_run_id=run_id,
                identity_target_path=DocumentPath.objects.get(
                    document=doc, corpus=self.corpus, is_current=True
                ),
            )
        self.assertIsNotNone(imported)
        return imported, ids

    def _finalize(self, run_id, source_id, target_id):
        coordination = PendingCorpusImport.objects.create(
            import_run_id=run_id,
            corpus=self.corpus,
            creator=self.user,
            expected_doc_count=2,
            status=PendingCorpusImport.Status.FINALIZING,
            relationships_payload=[
                {
                    "relationshipLabel": "references",
                    "source_annotation_ids": [source_id],
                    "target_annotation_ids": [target_id],
                }
            ],
        )
        finalize_corpus_import_relationships(str(run_id))
        coordination.refresh_from_db()
        self.assertEqual(coordination.status, PendingCorpusImport.Status.DONE)

    def test_changed_document_keeps_relationship_to_unchanged_document(self):
        run_id = uuid.uuid4()
        changed_text = "Tenant pays rent monthly."
        changed, _ = self._refresh(self.a, changed_text, "pays rent", "new-a", run_id)
        unchanged, _ = self._refresh(
            self.b, "Landlord insures property.", "insures property", "new-b", run_id
        )
        self.assertNotEqual(changed.pk, self.a.pk)
        self.assertEqual(unchanged.pk, self.b.pk)

        # Supply the deterministic parser output, then exercise real remapping
        # and fan-in. The unchanged document must not need a parser invocation.
        changed.txt_extract_file.save("text.txt", ContentFile(changed_text.encode()))
        remap_pending_annotations(doc_id=changed.pk)
        unchanged_row = PendingDocumentAnnotations.objects.get(
            ingestion_run_id=run_id, document=unchanged
        )
        self.assertEqual(unchanged_row.status, PendingDocumentAnnotations.Status.DONE)
        self.assertEqual(unchanged_row.id_map, {"new-b": self.ann_b.pk})

        self._finalize(run_id, "new-a", "new-b")

        relationship = Relationship.objects.get(corpus=self.corpus)
        self.assertEqual(relationship.source_annotations.get().document_id, changed.pk)
        self.assertEqual(list(relationship.target_annotations.all()), [self.ann_b])
        self.assertEqual(Annotation.objects.filter(document=self.b).count(), 1)

    def test_unchanged_baked_import_maps_renumbered_ids_without_duplicates(self):
        for export_id in ("reexport-1", "reexport-2"):
            with self.subTest(export_id=export_id):
                imported, ids = self._refresh(
                    self.b,
                    "Landlord insures property.",
                    "insures property",
                    export_id,
                    None,
                    reingest=False,
                )
                self.assertEqual(imported.pk, self.b.pk)
                self.assertEqual(ids, {export_id: self.ann_b.pk})
        self.assertEqual(Annotation.objects.filter(document=self.b).count(), 1)

    def test_unchanged_sourceless_fallback_records_recovered_ids(self):
        doc, annotation = self._seed(
            "notes.txt", "Notes apply.", "Notes", source=b"\x00"
        )
        run_id = uuid.uuid4()
        imported, ids = self._refresh(
            doc, "Notes apply.", "Notes", "renumbered-note", run_id, source=b"\x00"
        )
        self.assertEqual(imported.pk, doc.pk)
        self.assertEqual(ids, {"renumbered-note": annotation.pk})
        row = PendingDocumentAnnotations.objects.get(ingestion_run_id=run_id)
        self.assertEqual(row.status, PendingDocumentAnnotations.Status.DONE)
        self.assertEqual(row.id_map, {"renumbered-note": annotation.pk})
        self.assertEqual(Annotation.objects.filter(document=doc).count(), 1)

    def test_sidecar_omitted_by_export_does_not_hide_an_existing_endpoint(self):
        self.ann_b.data = {"country_code": "US"}
        self.ann_b.save(update_fields=["data"])
        run_id = uuid.uuid4()
        self._refresh(self.a, "Tenant pays rent.", "pays rent", "new-a", run_id)
        self._refresh(
            self.b, "Landlord insures property.", "insures property", "new-b", run_id
        )

        self._finalize(run_id, "new-a", "new-b")

        relationship = Relationship.objects.get(corpus=self.corpus)
        self.assertEqual(list(relationship.target_annotations.all()), [self.ann_b])
        self.ann_b.refresh_from_db()
        self.assertEqual(self.ann_b.data, {"country_code": "US"})

    def test_explicitly_different_sidecar_is_not_treated_as_the_same_annotation(self):
        self.ann_b.data = {"country_code": "US"}
        self.ann_b.save(update_fields=["data"])
        incoming = self._annotation(
            "new-b", "Landlord insures property.", "insures property"
        )
        incoming["data"] = {"country_code": "CA"}

        with self.assertLogs("opencontractserver.utils.importing", level="WARNING"):
            _, ids = self._refresh(
                self.b,
                "Landlord insures property.",
                "insures property",
                "new-b",
                None,
                reingest=False,
                annotation=incoming,
            )

        self.assertEqual(ids, {})
        self.ann_b.refresh_from_db()
        self.assertEqual(self.ann_b.data, {"country_code": "US"})

    def test_ambiguous_existing_annotations_are_reported_without_guessing(self):
        import_annotations(
            user_id=self.user.pk,
            doc_obj=self.b,
            corpus_obj=self.corpus,
            annotations_data=[
                self._annotation(
                    "duplicate", "Landlord insures property.", "insures property"
                )
            ],
            label_lookup=self.labels,
            dispatch_embeddings=False,
        )
        with self.assertLogs(
            "opencontractserver.utils.importing", level="WARNING"
        ) as logs:
            _, ids = self._refresh(
                self.b,
                "Landlord insures property.",
                "insures property",
                "new-b",
                None,
                reingest=False,
            )
        self.assertEqual(ids, {})
        self.assertIn("2 matching annotations", " ".join(logs.output))
        self.assertEqual(Annotation.objects.filter(document=self.b).count(), 2)

    def _remapped_pdf(self):
        source = b"%PDF-1.4 retained source"
        doc, seed_annotation = self._seed(
            "rule.pdf", "CHAPTER 1", "CHAPTER 1", source=source
        )
        seed_annotation.delete()
        doc.file_type = "application/pdf"
        doc.pawls_parse_file.save(
            "pawls.json", ContentFile(json.dumps(_PAWLS_V1).encode())
        )
        incoming = {
            "id": "renumbered-pdf",
            "annotationLabel": "clause-label",
            "rawText": "CHAPTER 1",
            "page": 0,
            "content_modalities": ["IMAGE"],
            "annotation_json": {
                "v": 2,
                "p": {"0": {"b": [8.0, 8.0, 110.0, 24.0], "t": "98-99"}},
            },
        }
        PendingDocumentAnnotations.objects.create(
            document=doc,
            corpus=self.corpus,
            creator=self.user,
            payload={"annotations": [{**incoming, "annotationLabel": "CLAUSE"}]},
        )
        remap_pending_annotations(doc_id=doc.pk)
        stored = Annotation.objects.get(document=doc)
        self.assertNotEqual(stored.json, incoming["annotation_json"])
        return doc, stored, incoming, source

    def test_unchanged_pdf_reanchors_export_locations_against_stored_tokens(self):
        doc, stored, incoming, source = self._remapped_pdf()
        run_id = uuid.uuid4()

        imported, _ = self._refresh(
            doc,
            "CHAPTER 1",
            "CHAPTER 1",
            incoming["id"],
            run_id,
            source=source,
            annotation=incoming,
        )

        self.assertEqual(imported.pk, doc.pk)
        row = PendingDocumentAnnotations.objects.get(ingestion_run_id=run_id)
        self.assertEqual(row.id_map, {incoming["id"]: stored.pk})
        self.assertEqual(Annotation.objects.filter(document=doc).count(), 1)

    def test_baked_refresh_of_previously_remapped_pdf_preserves_endpoint(self):
        doc, stored, incoming, source = self._remapped_pdf()

        imported, ids = self._refresh(
            doc,
            "CHAPTER 1",
            "CHAPTER 1",
            incoming["id"],
            None,
            source=source,
            annotation=incoming,
            reingest=False,
        )

        self.assertEqual(imported.pk, doc.pk)
        self.assertEqual(ids, {incoming["id"]: stored.pk})
        self.assertEqual(Annotation.objects.filter(document=doc).count(), 1)

    def test_missing_stored_text_still_allows_an_exact_baked_match(self):
        self.b.txt_extract_file.name = "missing-import-test-text.txt"
        self.b.save(update_fields=["txt_extract_file"])

        with self.assertLogs(
            "opencontractserver.utils.importing", level="WARNING"
        ) as logs:
            _, ids = self._refresh(
                self.b,
                "Landlord insures property.",
                "insures property",
                "new-b",
                None,
                reingest=False,
            )

        self.assertEqual(ids, {"new-b": self.ann_b.pk})
        self.assertIn("Cannot read stored annotation layers", " ".join(logs.output))

    def test_missing_endpoint_is_logged_and_never_bound_to_another_document(self):
        self.ann_b.document = self.a
        self.ann_b.save(update_fields=["document"])
        run_id = uuid.uuid4()
        self._refresh(self.a, "Tenant pays rent.", "pays rent", "new-a", run_id)
        with self.assertLogs("opencontractserver.utils.importing", level="WARNING"):
            self._refresh(
                self.b,
                "Landlord insures property.",
                "insures property",
                "new-b",
                run_id,
            )
        with self.assertLogs(
            "opencontractserver.tasks.import_tasks_v2", level="WARNING"
        ) as logs:
            self._finalize(run_id, "new-a", "new-b")
        self.assertIn("lost 0 source and 1 target", " ".join(logs.output))
        self.assertFalse(Relationship.objects.filter(corpus=self.corpus).exists())
