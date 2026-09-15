"""Readiness checks stored artifacts; repair reuses inference without parsing."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier, Event
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import close_old_connections
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from opencontractserver.annotations.models import (
    Annotation,
    Embedding,
    StructuralAnnotationSet,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.corpuses.services.corpus_service import CorpusService
from opencontractserver.documents.models import (
    Document,
    DocumentPath,
    EmbeddingRepair,
    PendingDocumentAnnotations,
    PipelineSettings,
)
from opencontractserver.documents.readiness import (
    ReadinessUnavailable,
    assess_document,
    assess_documents,
    effective_embedder,
    request_repair,
)
from opencontractserver.pipeline.embedders.test_embedder import TestEmbedder
from opencontractserver.tasks.readiness_tasks import repair_document_embeddings
from opencontractserver.utils.embedding_identity import (
    embedding_configuration,
    valid_embeddings,
)
from opencontractserver.worker_uploads.models import (
    CorpusAccessToken,
    WorkerAccount,
    WorkerDocumentUpload,
)

EMBEDDER = "opencontractserver.pipeline.embedders.test_embedder.TestEmbedder"
DISPATCH = "opencontractserver.tasks.readiness_tasks.repair_document_embeddings.delay"


class ReadinessFixtures(SimpleTestCase):
    def setUp(self):
        super().setUp()
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        setting = override_settings(MEDIA_ROOT=media.name)
        setting.enable()
        self.addCleanup(setting.disable)
        self.user = get_user_model().objects.create_user(username="readiness-owner")
        pipeline = PipelineSettings.get_instance(use_cache=False)
        pipeline.default_embedder = EMBEDDER
        pipeline.enabled_components = []
        pipeline.save()
        self.corpus = Corpus.objects.create(
            title="Imported documents", creator=self.user
        )
        self.doc = Document.objects.create(
            title="Agreement",
            creator=self.user,
            processing_status="completed",
            processing_started=timezone.now(),
            processing_finished=timezone.now(),
            txt_extract_file=ContentFile(
                b"The contract takes effect today.", name="text.txt"
            ),
        )
        DocumentPath.objects.create(
            document=self.doc,
            corpus=self.corpus,
            creator=self.user,
            path="/agreement",
            version_number=1,
        )
        self.doc.refresh_from_db()
        self.annotation = Annotation.objects.create(
            document=self.doc,
            corpus=self.corpus,
            creator=self.user,
            raw_text="Effective date",
        )

    def embed(self, obj, *, dimension=384, configuration=None, value=0.1):
        if configuration is None:
            configuration = effective_embedder(self.corpus)[2]
        return obj.add_embedding(
            EMBEDDER, [value] * dimension, configuration=configuration
        )

    def repair(self, doc=None):
        doc = doc or self.doc
        request_repair(doc, self.corpus, user=self.user)
        repair_document_embeddings(EmbeddingRepair.objects.get(document=doc).pk)
        return assess_document(doc, self.corpus)


class ReadinessTests(ReadinessFixtures, TestCase):
    def test_nonserializable_settings_allow_unverified_embeddings(self):
        from opencontractserver.tasks.embeddings_task import (
            calculate_embedding_for_doc_text,
            calculate_embeddings_for_annotation_batch,
        )

        client = APIClient()
        client.force_authenticate(self.user)
        with patch.object(
            TestEmbedder,
            "get_component_settings",
            return_value={"model_path": Path("/models/custom")},
        ):
            calculate_embedding_for_doc_text(self.doc.pk, embedder_path=EMBEDDER)
            batch = calculate_embeddings_for_annotation_batch(
                [self.annotation.pk], embedder_path=EMBEDDER
            )
            response = client.get(f"/api/readiness/documents/{self.doc.pk}/")
        self.assertEqual(batch["succeeded"], 1)
        self.assertEqual(Embedding.objects.filter(configuration="").count(), 2)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["state"], "unavailable")
        self.assertEqual(
            response.data["reasons"], ["embedder_configuration_unavailable"]
        )

    def test_active_repair_still_requires_authorization(self):
        request_repair(self.doc, self.corpus, user=self.user)
        stranger = get_user_model().objects.create_user(username="repair-stranger")
        with self.assertRaises(PermissionError):
            request_repair(self.doc, self.corpus, user=stranger)

    def test_deleted_document_is_unavailable_during_status_and_repair(self):
        client = APIClient()
        client.force_authenticate(self.user)

        def delete_during_observation(document):
            DocumentPath.objects.filter(document=document).delete()
            Document.objects.filter(pk=document.pk).delete()
            return True

        with patch(
            "opencontractserver.documents.readiness.document_has_text",
            side_effect=delete_during_observation,
        ):
            response = client.get(f"/api/readiness/documents/{self.doc.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["state"], "unavailable")
        self.assertIn("document_deleted", response.data["reasons"])
        result = request_repair(self.doc, self.corpus, user=self.user)
        self.assertEqual(result["reasons"], ["document_deleted"])
        self.assertFalse(EmbeddingRepair.objects.exists())

    def test_settings_save_invalidates_cached_embedder_before_repair(self):
        self.embed(self.doc)
        self.embed(self.annotation)
        Annotation.objects.create(
            document=self.doc,
            corpus=self.corpus,
            creator=self.user,
            raw_text="Second clause",
        )
        # Warm the cache used by the embedding tasks, then edit settings through
        # the normal write path while that cached snapshot is still live.
        pipeline = PipelineSettings.get_instance()
        pipeline.component_settings = {EMBEDDER: {"model": "new-model"}}
        pipeline.save()
        with patch(
            "opencontractserver.tasks.embeddings_task.embedding_configuration",
            wraps=embedding_configuration,
        ) as fingerprint:
            result = self.repair()
        self.assertEqual(result["state"], "ready")
        self.assertEqual(result["repair"]["succeeded"], 3)
        # One fingerprint for the document and one for the annotation batch.
        self.assertEqual(fingerprint.call_count, 2)

    def test_unverified_update_invalidates_siblings_and_preserves_creator(self):
        original = self.embed(self.doc)
        updater = get_user_model().objects.create_user(username="embedding-updater")
        updated = Embedding.objects.store_embedding(
            creator=updater,
            document_id=self.doc.pk,
            embedder_path=EMBEDDER,
            dimension=768,
            vector=[0.2] * 768,
        )
        self.assertEqual(updated.pk, original.pk)
        self.assertEqual(updated.creator_id, self.user.pk)
        self.assertEqual(updated.configuration, "")
        # Legacy multi-dimension storage remains supported, but no dimension
        # with an unverified fingerprint can establish readiness.
        self.assertIsNotNone(updated.vector_384)
        self.assertIsNotNone(updated.vector_768)
        result = assess_document(self.doc, self.corpus)
        self.assertEqual(result["coverage"]["documents"]["valid"], 0)
        self.assertEqual(result["state"], "outstanding")

    def test_copy_preserves_failed_terminal_processing_state(self):
        self.doc.processing_status = "failed"
        self.doc.processing_error = "Parser failed"
        self.doc.save(update_fields=["processing_status", "processing_error"])
        copy, _, _ = self.corpus.add_document(document=self.doc, user=self.user)
        for field in (
            "processing_started",
            "processing_finished",
            "processing_status",
            "processing_error",
        ):
            self.assertEqual(getattr(copy, field), getattr(self.doc, field))
        self.assertEqual(assess_document(copy, self.corpus)["state"], "failed")

    def test_deferred_annotations_gate_readiness_even_with_complete_vectors(self):
        self.embed(self.doc)
        self.embed(self.annotation)
        pending = PendingDocumentAnnotations.objects.create(
            document=self.doc, corpus=self.corpus, creator=self.user
        )
        for status, state in (
            ("pending", "outstanding"),
            ("failed", "failed"),
            ("done", "ready"),
        ):
            with self.subTest(status=status):
                pending.status = status
                pending.save(update_fields=["status"])
                result = assess_document(self.doc, self.corpus)
                self.assertEqual(result["state"], state)
                self.assertEqual(
                    "annotations_outstanding" in result["reasons"], status != "done"
                )
                request_repair(self.doc, self.corpus, user=self.user)
                self.assertFalse(EmbeddingRepair.objects.exists())

    def test_unavailable_corpus_configuration_is_resolved_once(self):
        other = Document.objects.create(creator=self.user)
        with patch(
            "opencontractserver.documents.readiness.effective_embedder",
            side_effect=ReadinessUnavailable("embedder_unavailable"),
        ) as resolve:
            results = assess_documents([self.doc, other], self.corpus)
        resolve.assert_called_once_with(self.corpus)
        self.assertEqual(
            [result["document_id"] for result in results], [self.doc.pk, other.pk]
        )
        for result in results:
            self.assertEqual(result["state"], "unavailable")
            self.assertEqual(result["reasons"], ["embedder_unavailable"])

    def test_document_repair_reports_dispatch_failure_and_can_be_retried(self):
        client = APIClient()
        client.force_authenticate(self.user)
        url = f"/api/readiness/documents/{self.doc.pk}/"
        with patch(DISPATCH, side_effect=OSError), self.captureOnCommitCallbacks(
            execute=True
        ):
            self.assertEqual(client.post(url).status_code, 202)
        failed = client.get(url).data
        self.assertEqual(failed["state"], "failed")
        self.assertEqual(failed["repair"]["errors"], ["dispatch_failed"])
        with patch(DISPATCH) as dispatch, self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(client.post(url).data["repair"]["status"], "queued")
        dispatch.assert_called_once()

    def test_worker_repair_rechecks_revoked_token_and_observes_missing_result(self):
        account = WorkerAccount.create_with_user(
            name="repair-worker", creator=self.user
        )
        token, key = CorpusAccessToken.create_token(
            worker_account=account, corpus=self.corpus
        )
        receipt = WorkerDocumentUpload.objects.create(
            corpus=self.corpus, corpus_access_token=token
        )
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"WorkerKey {key}")
        url = f"/api/readiness/worker/{receipt.pk}/"
        self.assertEqual(
            client.get(url).data["reasons"], ["result_document_unavailable"]
        )
        self.assertEqual(client.post(url).status_code, 400)
        receipt.result_document = self.doc
        receipt.save(update_fields=["result_document"])
        with patch(DISPATCH), self.captureOnCommitCallbacks(execute=True):
            queued = client.post(url)
        self.assertEqual(queued.status_code, 202)
        self.assertEqual(
            client.get("/api/readiness/worker/").data["documents"][0]["document_id"],
            self.doc.pk,
        )
        token.is_active = False
        token.save(update_fields=["is_active"])
        with patch.object(TestEmbedder, "embed_texts_batch") as inference:
            repair_document_embeddings(queued.data["repair"]["id"])
        inference.assert_not_called()
        self.assertEqual(
            EmbeddingRepair.objects.get(document=self.doc).status, "failed"
        )
        self.assertFalse(Embedding.objects.exists())

    def test_completed_parse_and_unlocked_document_still_need_both_embedding_stages(
        self,
    ):
        result = assess_document(self.doc, self.corpus)
        self.assertEqual(result["state"], "outstanding", result)
        self.assertEqual(
            result["coverage"],
            {
                "documents": {"eligible": 1, "valid": 0},
                "annotations": {"eligible": 1, "valid": 0},
            },
        )
        self.embed(self.doc)
        self.assertEqual(assess_document(self.doc, self.corpus)["state"], "outstanding")
        self.embed(self.annotation)
        result = assess_document(self.doc, self.corpus)
        self.assertEqual(result["state"], "ready")
        self.assertEqual(result["optional_artifacts"], {"thumbnail": False})

    def test_wrong_dimension_unknown_model_and_zero_vectors_are_not_coverage(self):
        self.embed(self.doc)
        for dimension, configuration, value in (
            (768, None, 0.1),
            (384, "old-model", 0.1),
            (384, None, 0.0),
        ):
            with self.subTest(
                dimension=dimension, configuration=configuration, value=value
            ):
                Embedding.objects.filter(annotation=self.annotation).delete()
                self.embed(
                    self.annotation,
                    dimension=dimension,
                    configuration=configuration,
                    value=value,
                )
                result = assess_document(self.doc, self.corpus)
                self.assertEqual(result["coverage"]["annotations"]["valid"], 0)
                self.assertEqual(result["state"], "outstanding")

    def test_wrong_dimension_cannot_relabel_an_older_models_vector(self):
        self.embed(self.doc)
        self.embed(self.annotation, configuration="old-model")
        self.embed(self.annotation, dimension=768)
        result = assess_document(self.doc, self.corpus)
        self.assertEqual(result["state"], "outstanding")
        self.assertEqual(result["coverage"]["annotations"]["valid"], 0)

    def test_empty_annotations_are_excluded_and_shared_structural_annotations_are_counted_once(
        self,
    ):
        shared = StructuralAnnotationSet.objects.create(
            content_hash="shared", creator=self.user
        )
        self.doc.structural_annotation_set = shared
        self.doc.save(update_fields=["structural_annotation_set"])
        copy = Document.objects.create(
            creator=self.user,
            title="Copy",
            structural_annotation_set=shared,
            txt_extract_file=self.doc.txt_extract_file,
            processing_status="completed",
        )
        DocumentPath.objects.create(
            document=copy,
            corpus=self.corpus,
            creator=self.user,
            path="/copy",
            version_number=1,
        )
        structural = Annotation.objects.create(
            creator=self.user,
            structural=True,
            structural_set=shared,
            raw_text="Shared clause",
        )
        for raw_text in ("", " \t\n\f"):
            Annotation.objects.create(
                document=self.doc,
                corpus=self.corpus,
                creator=self.user,
                raw_text=raw_text,
            )
        self.embed(self.doc)
        self.embed(self.annotation)
        self.assertEqual(
            assess_document(self.doc, self.corpus)["coverage"]["annotations"],
            {"eligible": 2, "valid": 1},
        )
        self.embed(structural)
        self.assertEqual(assess_document(self.doc, self.corpus)["state"], "ready")
        self.assertEqual(
            assess_document(copy, self.corpus)["coverage"]["annotations"],
            {"eligible": 1, "valid": 1},
        )

    def test_model_revision_change_invalidates_prior_readiness_and_generation(self):
        self.embed(self.doc)
        self.embed(self.annotation)
        before = assess_document(self.doc, self.corpus)
        with override_settings(EMBEDDING_MODEL_REVISIONS={EMBEDDER: "model-v2"}):
            after = assess_document(self.doc, self.corpus)
        self.assertEqual(before["state"], "ready")
        self.assertEqual(after["state"], "outstanding")
        self.assertNotEqual(before["generation"], after["generation"])
        self.assertEqual(after["coverage"]["documents"]["valid"], 0)

    def test_failed_parsing_remains_failed_even_with_complete_vectors(self):
        self.embed(self.doc)
        self.embed(self.annotation)
        self.doc.processing_status = "failed"
        self.doc.processing_error = "Parser timed out\nwhile loading page 2"
        self.doc.save(update_fields=["processing_status", "processing_error"])
        result = assess_document(self.doc, self.corpus)
        self.assertEqual(result["state"], "failed")
        self.assertEqual(
            result["processing_error"], "Parser timed out while loading page 2"
        )
        request_repair(self.doc, self.corpus, user=self.user)
        self.assertFalse(EmbeddingRepair.objects.exists())

    def test_missing_text_or_disabled_embedder_is_unavailable(self):
        with patch.object(
            self.doc.txt_extract_file.storage, "open", side_effect=FileNotFoundError
        ):
            result = assess_document(self.doc, self.corpus)
            self.assertEqual(result["state"], "unavailable")
            self.assertEqual(result["reasons"], ["text_artifact_missing"])
        pipeline = PipelineSettings.get_instance(use_cache=False)
        pipeline.enabled_components = ["another.embedder"]
        pipeline.save()
        result = assess_document(self.doc, self.corpus)
        self.assertEqual(result["state"], "unavailable")
        self.assertEqual(result["reasons"], ["embedder_unavailable"])

    def test_empty_document_text_does_not_require_a_document_vector(self):
        self.doc.txt_extract_file.save("empty.txt", ContentFile(b" \t\n"))
        self.embed(self.annotation)
        result = assess_document(self.doc, self.corpus)
        self.assertEqual(result["state"], "ready")
        self.assertEqual(result["coverage"]["documents"], {"eligible": 0, "valid": 0})

    def test_partial_batch_failure_is_visible_and_retry_preserves_valid_vectors_and_files(
        self,
    ):
        good = self.embed(self.doc)
        sibling = Annotation.objects.create(
            document=self.doc,
            corpus=self.corpus,
            creator=self.user,
            raw_text="Second clause",
        )
        files = (self.doc.txt_extract_file.name, self.doc.pawls_parse_file.name)
        with patch.object(
            TestEmbedder, "embed_texts_batch", return_value=[[0.2] * 384, None]
        ):
            failed = self.repair()
        self.assertEqual(failed["state"], "failed")
        self.assertEqual(
            (
                failed["repair"]["attempted"],
                failed["repair"]["succeeded"],
                failed["repair"]["failed"],
            ),
            (2, 1, 1),
        )
        first_vector = Embedding.objects.get(annotation=self.annotation)
        with patch.object(
            TestEmbedder, "embed_texts_batch", return_value=[[0.3] * 384]
        ) as inference:
            ready = self.repair()
        self.assertEqual(ready["state"], "ready")
        inference.assert_called_once()
        self.assertEqual(inference.call_args.args[0], [sibling.raw_text])
        good.refresh_from_db()
        first_vector.refresh_from_db()
        assert first_vector.vector_384 is not None
        self.assertAlmostEqual(float(good.vector_384[0]), 0.1)
        self.assertAlmostEqual(float(first_vector.vector_384[0]), 0.2)
        self.doc.refresh_from_db()
        self.assertEqual(
            (self.doc.txt_extract_file.name, self.doc.pawls_parse_file.name), files
        )

    def test_repair_batch_is_bounded_and_repeated_queued_requests_dispatch_once(self):
        for index in range(4):
            Annotation.objects.create(
                document=self.doc,
                corpus=self.corpus,
                creator=self.user,
                raw_text=f"Clause {index}",
            )
        with patch(DISPATCH) as dispatch, self.captureOnCommitCallbacks(execute=True):
            first = request_repair(self.doc, self.corpus, user=self.user)
            second = request_repair(self.doc, self.corpus, user=self.user)
        self.assertEqual(first["repair"]["id"], second["repair"]["id"])
        dispatch.assert_called_once()
        with patch("opencontractserver.tasks.readiness_tasks.REPAIR_BATCH_SIZE", 3):
            repair_document_embeddings(first["repair"]["id"])
        job = EmbeddingRepair.objects.get(document=self.doc)
        self.assertEqual((job.attempted, job.succeeded), (3, 3))
        self.assertEqual(assess_document(self.doc, self.corpus)["state"], "outstanding")

    def test_configuration_change_before_task_execution_does_not_embed(self):
        request_repair(self.doc, self.corpus, user=self.user)
        with override_settings(
            EMBEDDING_MODEL_REVISIONS={EMBEDDER: "changed"}
        ), patch.object(TestEmbedder, "embed_texts_batch") as inference:
            repair_document_embeddings(
                EmbeddingRepair.objects.get(document=self.doc).pk
            )
        inference.assert_not_called()
        self.assertEqual(
            EmbeddingRepair.objects.get(document=self.doc).status, "failed"
        )
        self.assertFalse(Embedding.objects.exists())

    def test_deactivated_requester_cannot_execute_a_queued_repair(self):
        request_repair(self.doc, self.corpus, user=self.user)
        get_user_model().objects.filter(pk=self.user.pk).update(is_active=False)
        with patch.object(TestEmbedder, "embed_texts_batch") as inference:
            repair_document_embeddings(
                EmbeddingRepair.objects.get(document=self.doc).pk
            )
        inference.assert_not_called()
        self.assertEqual(
            EmbeddingRepair.objects.get(document=self.doc).status, "failed"
        )
        self.assertFalse(Embedding.objects.exists())

    def test_remote_vectors_require_the_configured_model_revision(self):
        from opencontractserver.worker_uploads.tasks import _store_embeddings

        payload = {
            "embedder_path": EMBEDDER,
            "model_identity": "old-model",
            "document_embedding": [0.1] * 384,
            "annotation_embeddings": {"clause": [0.2] * 384},
        }
        with override_settings(EMBEDDING_MODEL_REVISIONS={EMBEDDER: "model-v2"}):
            _store_embeddings(
                payload, self.doc, {"clause": self.annotation.pk}, self.user
            )
            self.assertEqual(
                assess_document(self.doc, self.corpus)["state"], "outstanding"
            )
            Embedding.objects.all().delete()
            payload["model_identity"] = "model-v2"
            _store_embeddings(
                payload, self.doc, {"clause": self.annotation.pk}, self.user
            )
            self.assertEqual(assess_document(self.doc, self.corpus)["state"], "ready")

    def test_remote_reupload_at_a_new_dimension_clears_the_stale_sibling_vector(
        self,
    ):
        from opencontractserver.worker_uploads.tasks import _store_embeddings

        payload = {
            "embedder_path": EMBEDDER,
            "model_identity": "model-v2",
            "document_embedding": [0.1] * 384,
            "annotation_embeddings": {},
        }
        with override_settings(EMBEDDING_MODEL_REVISIONS={EMBEDDER: "model-v2"}):
            _store_embeddings(payload, self.doc, {}, self.user)
            # The service behind the same path now emits 768-wide vectors.
            payload["document_embedding"] = [0.2] * 768
            with patch.object(TestEmbedder, "vector_size", 768):
                _store_embeddings(payload, self.doc, {}, self.user)
                configuration = effective_embedder(self.corpus)[2]
        embedding = Embedding.objects.get(document=self.doc, embedder_path=EMBEDDER)
        self.assertIsNone(embedding.vector_384)
        assert embedding.vector_768 is not None
        self.assertEqual(len(embedding.vector_768), 768)
        self.assertEqual(embedding.configuration, configuration)

    def test_migration_repairs_historical_completed_worker_copies_only(self):
        import importlib

        from django.apps import apps

        reconcile = importlib.import_module(
            "opencontractserver.documents.migrations.0045_worker_copy_processing_status"
        ).reconcile_completed_uploads
        account = WorkerAccount.create_with_user(
            name="legacy-worker", creator=self.user
        )
        token, _ = CorpusAccessToken.create_token(
            worker_account=account, corpus=self.corpus
        )
        copies = []
        for status in ("pending", "failed"):
            copy = Document.objects.create(
                creator=self.user, source_document=self.doc, processing_status=status
            )
            WorkerDocumentUpload.objects.create(
                corpus=self.corpus,
                corpus_access_token=token,
                result_document=copy,
                status="COMPLETED",
                processing_finished=self.doc.processing_finished,
            )
            copies.append(copy)
        reconcile(apps, None)
        for copy in copies:
            copy.refresh_from_db()
        self.assertEqual(copies[0].processing_status, "completed")
        self.assertEqual(copies[0].processing_finished, self.doc.processing_finished)
        self.assertEqual(copies[1].processing_status, "failed")

    def test_status_requires_document_read_and_repair_requires_update(self):
        client = APIClient()
        url = f"/api/readiness/documents/{self.doc.pk}/"
        self.assertIn(client.get(url).status_code, (401, 403))
        stranger = get_user_model().objects.create_user(username="readiness-stranger")
        client.force_authenticate(stranger)
        self.assertEqual(client.get(url).status_code, 404)
        self.doc.is_public = True
        self.doc.save(update_fields=["is_public"])
        self.corpus.is_public = True
        self.corpus.save(update_fields=["is_public"])
        self.assertEqual(client.get(url).status_code, 200)
        self.assertEqual(client.post(url).status_code, 404)
        self.assertFalse(EmbeddingRepair.objects.exists())

    def test_worker_receipt_scope_and_corpus_page_limit_are_enforced(self):
        account = WorkerAccount.create_with_user(
            name="readiness-worker", creator=self.user
        )
        token, key = CorpusAccessToken.create_token(
            worker_account=account, corpus=self.corpus
        )
        other_token, _ = CorpusAccessToken.create_token(
            worker_account=account, corpus=self.corpus
        )
        receipt = WorkerDocumentUpload.objects.create(
            corpus=self.corpus,
            corpus_access_token=token,
            result_document=self.doc,
            status="COMPLETED",
        )
        other = WorkerDocumentUpload.objects.create(
            corpus=self.corpus,
            corpus_access_token=other_token,
            result_document=self.doc,
            status="COMPLETED",
        )
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"WorkerKey {key}")
        result = client.get(f"/api/readiness/worker/{receipt.pk}/")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["state"], "outstanding")
        self.assertEqual(
            client.get(f"/api/readiness/worker/{other.pk}/").status_code, 404
        )
        self.assertEqual(
            client.get("/api/readiness/worker/?limit=101").status_code, 400
        )

    def test_document_status_picks_the_newest_corpus_and_accepts_an_explicit_one(
        self,
    ):
        later = Corpus.objects.create(title="Later corpus", creator=self.user)
        DocumentPath.objects.create(
            document=self.doc,
            corpus=later,
            creator=self.user,
            path="/agreement",
            version_number=1,
        )
        client = APIClient()
        client.force_authenticate(self.user)
        url = f"/api/readiness/documents/{self.doc.pk}/"
        # Without a hint the newest current path wins, on every call.
        for _ in range(2):
            self.assertEqual(client.get(url).data["corpus_id"], later.pk)
        explicit = client.get(url, {"corpus": self.corpus.pk})
        self.assertEqual(explicit.data["corpus_id"], self.corpus.pk)
        unrelated = Corpus.objects.create(title="Unrelated", creator=self.user)
        self.assertEqual(client.get(url, {"corpus": unrelated.pk}).status_code, 404)
        self.assertEqual(client.get(url, {"corpus": "agreement"}).status_code, 400)
        # A reader of only the older corpus needs the hint to observe it.
        reader = get_user_model().objects.create_user(username="readiness-reader")
        for obj in (self.doc, self.corpus):
            obj.is_public = True
            obj.save(update_fields=["is_public"])
        client.force_authenticate(reader)
        self.assertEqual(client.get(url).status_code, 404)
        self.assertEqual(client.get(url, {"corpus": self.corpus.pk}).status_code, 200)

    def test_dimension_scoped_coverage_query_stays_scoped_to_assessed_annotations(
        self,
    ):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        path, dimension, configuration = effective_embedder(self.corpus)
        with CaptureQueriesContext(connection) as queries:
            missing = CorpusService.count_annotations_missing_embeddings(
                self.corpus, path, dimension=dimension, configuration=configuration
            )
        self.assertEqual(missing, 1)
        validity = [
            q["sql"] for q in queries.captured_queries if "vector_norm" in q["sql"]
        ]
        self.assertEqual(len(validity), 1)
        # The vector_norm scan must be restricted to the assessed annotations
        # rather than sweeping every Embedding row in the installation.
        self.assertIn('"annotation_id" IN (SELECT', validity[0])

    def test_embedder_missing_required_settings_is_reported_unavailable(self):
        from opencontractserver.pipeline.base.settings_schema import (
            ConfigurationError,
        )

        client = APIClient()
        client.force_authenticate(self.user)
        with patch.object(
            TestEmbedder,
            "__init__",
            side_effect=ConfigurationError(EMBEDDER, ["base_url"]),
        ):
            result = assess_document(self.doc, self.corpus)
            response = client.get(f"/api/readiness/documents/{self.doc.pk}/")
        self.assertEqual(result["state"], "unavailable")
        self.assertEqual(result["reasons"], ["embedder_configuration_unavailable"])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["state"], "unavailable")

    def test_repair_selection_scopes_vector_validity_to_document_annotations(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as queries:
            result = self.repair()
        self.assertEqual(result["state"], "ready")
        selection = [
            q["sql"]
            for q in queries.captured_queries
            if q["sql"].startswith('SELECT DISTINCT "annotations_annotation"."id"')
            and "vector_norm" in q["sql"]
        ]
        self.assertEqual(len(selection), 1)
        self.assertIn('"annotation_id" IN (SELECT', selection[0])

    def test_corpus_page_isolates_a_failing_document_and_resolves_once(self):
        from opencontractserver.documents import readiness

        copy = Document.objects.create(
            title="Copy",
            creator=self.user,
            processing_status="completed",
            txt_extract_file=self.doc.txt_extract_file,
        )
        DocumentPath.objects.create(
            document=copy,
            corpus=self.corpus,
            creator=self.user,
            path="/copy",
            version_number=1,
        )
        real = readiness.document_has_text

        def explode(document):
            if document.pk == copy.pk:
                raise RuntimeError("boom")
            return real(document)

        client = APIClient()
        client.force_authenticate(self.user)
        with patch.object(
            readiness, "document_has_text", side_effect=explode
        ), patch.object(
            readiness, "effective_embedder", wraps=effective_embedder
        ) as resolve:
            response = client.get(f"/api/readiness/corpuses/{self.corpus.pk}/")
        self.assertEqual(response.status_code, 200)
        observed = {d["document_id"]: d for d in response.data["documents"]}
        self.assertEqual(observed[self.doc.pk]["state"], "outstanding")
        self.assertEqual(observed[copy.pk]["state"], "unavailable")
        self.assertEqual(observed[copy.pk]["reasons"], ["assessment_failed"])
        self.assertEqual(resolve.call_count, 1)

    def test_bulk_add_embeddings_records_the_configuration(self):
        configuration = effective_embedder(self.corpus)[2]
        self.annotation.add_embeddings(
            EMBEDDER, [[0.1] * 384], configuration=configuration
        )
        self.assertEqual(
            Embedding.objects.get(annotation=self.annotation).configuration,
            configuration,
        )

    def test_validity_filter_requires_a_configuration_fingerprint(self):
        for configuration in (None, ""):
            with self.subTest(configuration=configuration), self.assertRaises(
                ValueError
            ):
                valid_embeddings(EMBEDDER, 384, configuration)


class ConcurrentRepairTests(ReadinessFixtures, TransactionTestCase):
    def test_repeat_post_returns_progress_while_inference_holds_document_lock(self):
        started, release = Event(), Event()

        def embed(*args, **kwargs):
            started.set()
            if not release.wait(timeout=10):
                raise TimeoutError("Test did not release embedding inference")
            return [0.1] * 384

        def run_repair(job_id):
            close_old_connections()
            try:
                repair_document_embeddings(job_id)
            finally:
                close_old_connections()

        def post():
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(self.user)
                return client.post(f"/api/readiness/documents/{self.doc.pk}/")
            finally:
                close_old_connections()

        with patch(DISPATCH) as dispatch:
            initial = request_repair(self.doc, self.corpus, user=self.user)
            with patch.object(
                TestEmbedder, "_embed_text_impl", side_effect=embed
            ), ThreadPoolExecutor(max_workers=2) as pool:
                worker = pool.submit(run_repair, initial["repair"]["id"])
                try:
                    self.assertTrue(started.wait(timeout=10))
                    response = pool.submit(post).result(timeout=5)
                    self.assertEqual(response.status_code, 202)
                    self.assertEqual(response.data["repair"]["status"], "running")
                    self.assertEqual(
                        response.data["repair"]["id"], initial["repair"]["id"]
                    )
                finally:
                    release.set()
                worker.result(timeout=10)
        dispatch.assert_called_once()
        self.assertEqual(assess_document(self.doc, self.corpus)["state"], "ready")

    def test_concurrent_requests_claim_one_batch(self):
        barrier = Barrier(2)

        def request():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return request_repair(self.doc, self.corpus, user=self.user)["repair"][
                    "id"
                ]
            finally:
                close_old_connections()

        with patch(DISPATCH) as dispatch, ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(request) for _ in range(2)]
            ids = [future.result(timeout=30) for future in futures]
        self.assertEqual(ids[0], ids[1])
        self.assertEqual(EmbeddingRepair.objects.count(), 1)
        dispatch.assert_called_once()
