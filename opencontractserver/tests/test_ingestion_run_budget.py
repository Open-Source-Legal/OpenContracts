"""Budget admission at real database and provider-call boundaries."""

import inspect
import json
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import (
    IntegrityError,
    OperationalError,
    close_old_connections,
    connection,
    transaction,
)
from django.test import SimpleTestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from opencontractserver.annotations.models import (
    Annotation,
    AnnotationLabel,
    Embedding,
    LabelSet,
    Relationship,
    StructuralAnnotationSet,
)
from opencontractserver.constants.embeddings import OPENAI_EMBEDDER_PATH as OPENAI
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import (
    Document,
    DocumentProcessingStatus,
    PipelineSettings,
)
from opencontractserver.pipeline.embedders.openai_embedder import OpenAIEmbedder
from opencontractserver.tests.test_worker_uploads import (
    _make_fake_pdf,
    _make_metadata,
    _structural_metadata,
)
from opencontractserver.worker_uploads.models import (
    CorpusAccessToken,
    UploadStatus,
    WorkerAccount,
)
from opencontractserver.worker_uploads.run_models import (
    IngestionOperation,
    IngestionReservation,
    IngestionRun,
)
from opencontractserver.worker_uploads.run_policy import RunPolicyError
from opencontractserver.worker_uploads.run_services import (
    control_run,
    create_run,
    execute_reservation,
    lock_target,
    route_embedding,
    run_report,
)
from opencontractserver.worker_uploads.tasks import _process_single_upload
from opencontractserver.worker_uploads.upload_recovery import stage_upload

PREPARATION = {
    "fingerprint": "a" * 64,
    "parser_name": "TextParser",
    "parser_version": "1.0",
    "embedder_path": "",
    "embedding_dimension": 0,
    "embedding_model_fingerprint": "b" * 64,
}
PRICING = {
    "version": "test-rate-v1",
    "openai_usd_per_million_tokens": {"text-embedding-3-small": "1"},
}


@override_settings(INGESTION_RUN_PRICING=PRICING)
class IngestionRunBudgetTests(TransactionTestCase):
    def setUp(self):
        self.nudge = patch(
            "opencontractserver.worker_uploads.run_services._nudge"
        ).start()
        self.addCleanup(patch.stopall)
        self.user = get_user_model().objects.create_superuser(
            "budget-owner", "budget@example.com", "pw"
        )
        self.account = WorkerAccount.create_with_user(
            name="budget-worker", creator=self.user
        )
        self.corpus = Corpus.objects.create(
            title="Budget corpus",
            creator=self.user,
            preferred_embedder=OPENAI,
            label_set=LabelSet.objects.create(title="Labels", creator=self.user),
        )
        self.token, self.key = CorpusAccessToken.create_token(
            worker_account=self.account, corpus=self.corpus
        )
        self.pipeline = PipelineSettings.get_instance(use_cache=False)
        self.pipeline.default_embedder = OPENAI
        self.pipeline.component_settings = {
            OPENAI: {
                "openai_api_key": "secret-provider-credential",
                "openai_embedding_model": "text-embedding-3-small",
                "openai_embedding_dimensions": 384,
            }
        }
        self.pipeline.save()
        self.addCleanup(PipelineSettings.clear_cache)
        self.api_client = APIClient()
        self.api_client.credentials(HTTP_AUTHORIZATION=f"WorkerKey {self.key}")

    def new_run(self, ceiling="0.000004", **kwargs):
        return create_run(
            self.token,
            ceiling_usd=ceiling,
            preparations=[PREPARATION],
            embedding_mode="server",
            **kwargs,
        )

    def document(self, run, text="abcd"):
        return Document.objects.create(
            title="Budget document",
            creator=self.user,
            ingestion_run=run,
            file_type="text/plain",
            processing_started=timezone.now(),
            txt_extract_file=ContentFile(text.encode(), name="body.txt"),
        )

    def reserve(self, run, text="abcd"):
        doc = self.document(run, text)
        self.assertTrue(route_embedding(doc))
        return doc, IngestionReservation.objects.get(operation__target_id=doc.pk)

    def assert_totals(self, run, *, accounted, reserved):
        run.refresh_from_db()
        self.assertEqual(run.accounted_usd, Decimal(accounted))
        self.assertEqual(run.reserved_usd, Decimal(reserved))
        self.assertLessEqual(run.accounted_usd + run.reserved_usd, run.ceiling_usd)

    def test_run_endpoints_only_return_public_policy_codes(self):
        sensitive = "provider credential=secret at /private/provider.py:42"
        payload = {"ceiling_usd": "0", "preparations": [PREPARATION]}
        for message, code, status in (
            (sensitive, "run_policy_error", 400),
            ("invalid_money", "invalid_money", 400),
            ("run_identity_conflict", "run_identity_conflict", 409),
        ):
            with self.subTest(message=message), patch(
                "opencontractserver.worker_uploads.run_views.create_run",
                side_effect=RunPolicyError(message),
            ):
                response = self.api_client.post(
                    "/api/worker-uploads/runs/", payload, format="json"
                )
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.json(), {"error": code})

        run = self.new_run()
        for message, code in (
            (sensitive, "run_policy_error"),
            ("run_cancelled", "run_cancelled"),
        ):
            with self.subTest(message=message), patch(
                "opencontractserver.worker_uploads.run_views.control_run",
                side_effect=RunPolicyError(message),
            ):
                response = self.api_client.post(
                    f"/api/worker-uploads/runs/{run.pk}/",
                    {"action": "resume"},
                    format="json",
                )
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.json(), {"error": code})

    def test_policy_exception_details_do_not_reach_persisted_reports(self):
        sensitive = "provider credential=secret at /private/provider.py:42"
        for phase in ("admission", "execution", "publication", "provider"):
            with self.subTest(phase=phase):
                run = self.new_run()
                if phase == "admission":
                    with patch(
                        "opencontractserver.worker_uploads.run_services.validate_execution",
                        side_effect=RunPolicyError(sensitive),
                    ):
                        self.assertTrue(route_embedding(self.document(run)))
                else:
                    _, reservation = self.reserve(run)
                    targets = {
                        "execution": "opencontractserver.worker_uploads.run_services.validate_execution",
                        "publication": "opencontractserver.documents.models.Document.add_embedding",
                        "provider": (
                            "opencontractserver.pipeline.embedders.openai_embedder."
                            "OpenAIEmbedder.embed_text_accounted"
                        ),
                    }
                    with patch.object(
                        OpenAIEmbedder,
                        "embed_text_accounted",
                        return_value=([0.25] * 384, 2),
                    ), patch(targets[phase], side_effect=RunPolicyError(sensitive)):
                        execute_reservation(reservation.pk)

                # Exercise all three report responses, including an idempotent
                # create replay of a run which already has a persisted failure.
                url = f"/api/worker-uploads/runs/{run.pk}/"
                responses = [
                    self.api_client.get(url),
                    self.api_client.post(url, {"action": "pause"}, format="json"),
                    self.api_client.post(
                        "/api/worker-uploads/runs/",
                        {
                            "id": str(run.pk),
                            "ceiling_usd": "0.000004",
                            "preparations": [PREPARATION],
                            "embedding_mode": "server",
                        },
                        format="json",
                    ),
                ]
                self.assertEqual([r.status_code for r in responses], [200, 200, 201])
                for response in responses:
                    self.assertEqual(response.json()["last_error"], "run_policy_error")
                    self.assertNotIn(sensitive, response.content.decode())
                self.assertTrue(run.events.filter(code="run_policy_error").exists())
                self.assertNotIn(sensitive, run.operations.get().error_code)

    def test_exact_boundary_fits_and_next_byte_waits_without_a_reservation(self):
        run = self.new_run()
        self.reserve(run)
        route_embedding(self.document(run, "x"))
        self.assert_totals(run, accounted="0", reserved="0.000004")
        self.assertEqual(run.status, IngestionRun.Status.BUDGET_EXHAUSTED)
        waiting = run.operations.get(status=IngestionOperation.Status.WAITING)
        self.assertEqual(waiting.estimated_usd, Decimal("0.000001"))
        self.assertFalse(waiting.reservations.exists())

    def test_competing_admissions_cannot_both_spend_the_same_allowance(self):
        run = self.new_run()
        docs = [self.document(run), self.document(run)]
        barrier = Barrier(2)

        def admit(pk):
            close_old_connections()
            try:
                doc = Document.objects.get(pk=pk)
                barrier.wait(timeout=10)
                route_embedding(doc)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(admit, [doc.pk for doc in docs]))
        self.assertEqual(IngestionReservation.objects.count(), 1)
        self.assertEqual(run.operations.filter(status="WAITING").count(), 1)
        self.assert_totals(run, accounted="0", reserved="0.000004")

    def test_usage_settles_once_and_redelivery_never_calls_the_provider_again(self):
        from opencontractserver.documents.readiness import assess_document

        run = self.new_run()
        doc, reservation = self.reserve(run)
        with patch.object(
            OpenAIEmbedder, "embed_text_accounted", return_value=([0.25] * 384, 2)
        ) as provider:
            execute_reservation(reservation.pk)
            execute_reservation(reservation.pk)
            route_embedding(doc)
        provider.assert_called_once_with("abcd")
        self.assert_totals(run, accounted="0.000002", reserved="0")
        self.assertEqual(Embedding.objects.filter(document=doc).count(), 1)
        doc.processing_status = DocumentProcessingStatus.COMPLETED
        doc.backend_lock = False
        doc.save(update_fields=["processing_status", "backend_lock"])
        assessment = assess_document(doc, self.corpus)
        self.assertEqual(assessment["state"], "ready", assessment)
        report = run_report(run)
        self.assertEqual(report["remaining_usd"], "0.000002000")
        self.assertEqual(report["reservations"][0]["accounted_tokens"], 2)
        self.assertIsInstance(report["reservations"][0]["amount_usd"], str)

    def test_unverified_vector_cannot_skip_budgeted_generation(self):
        run = self.new_run()
        doc = self.document(run)
        doc.add_embedding(OPENAI, [0.25] * 384)
        self.assertTrue(route_embedding(doc))
        self.assertEqual(run.operations.count(), 1)
        self.assert_totals(run, accounted="0", reserved="0.000004")

    def test_model_revision_change_blocks_reserved_work(self):
        run = self.new_run()
        _, reservation = self.reserve(run)
        with override_settings(EMBEDDING_MODEL_REVISIONS={OPENAI: "new-revision"}):
            with patch.object(OpenAIEmbedder, "embed_text_accounted") as provider:
                execute_reservation(reservation.pk)
        provider.assert_not_called()
        run.refresh_from_db()
        self.assertEqual(run.status, IngestionRun.Status.POLICY_VIOLATION)
        self.assertEqual(run.last_error, "provider_configuration_changed")
        self.assert_totals(run, accounted="0", reserved="0.000004")

    def test_duplicate_admission_reserves_only_one_operation(self):
        run = self.new_run()
        doc, reservation = self.reserve(run)
        route_embedding(Document.objects.get(pk=doc.pk))
        self.assertEqual(run.operations.count(), 1)
        self.assertEqual(IngestionReservation.objects.get().pk, reservation.pk)
        self.assert_totals(run, accounted="0", reserved="0.000004")

    def test_cosmetic_provider_source_changes_allow_resume(self):
        run = self.new_run()
        _, reservation = self.reserve(run)
        control_run(run.pk, "pause")
        with TemporaryDirectory() as directory:
            source = Path(directory) / "openai_embedder.py"
            source.write_text(
                Path(inspect.getfile(OpenAIEmbedder)).read_text()
                + "\n# Deployment annotation; no behavior change.\n"
            )
            with patch("inspect.getfile", return_value=str(source)), patch.object(
                OpenAIEmbedder, "embed_text_accounted", return_value=([0.25] * 384, 2)
            ) as provider:
                control_run(run.pk, "resume")
                execute_reservation(reservation.pk)
        provider.assert_called_once()
        self.assert_totals(run, accounted="0.000002", reserved="0")

    def test_accounting_adapter_revision_change_blocks_reserved_work(self):
        run = self.new_run()
        _, reservation = self.reserve(run)
        with patch.object(
            OpenAIEmbedder, "accounting_version", "next-version", create=True
        ), patch.object(OpenAIEmbedder, "embed_text_accounted") as provider:
            execute_reservation(reservation.pk)
        provider.assert_not_called()
        self.assert_totals(run, accounted="0", reserved="0.000004")
        self.assertEqual(run.last_error, "provider_configuration_changed")

    def test_invalid_usage_is_reported_separately_and_keeps_the_reservation(self):
        for tokens in (None, -1, True, 5):
            with self.subTest(tokens=tokens):
                run = self.new_run()
                doc, reservation = self.reserve(run)
                with patch.object(
                    OpenAIEmbedder,
                    "embed_text_accounted",
                    return_value=([0.25] * 384, tokens),
                ):
                    execute_reservation(reservation.pk)
                self.assert_totals(run, accounted="0", reserved="0.000004")
                self.assertEqual(run.last_error, "invalid_usage_receipt")
                self.assertEqual(
                    run.operations.get().error_code, "invalid_usage_receipt"
                )
                reservation.refresh_from_db()
                self.assertEqual(
                    reservation.status, IngestionReservation.Status.UNCERTAIN
                )
                self.assertFalse(Embedding.objects.filter(document=doc).exists())

    def test_cross_corpus_copy_does_not_pause_or_redirect_the_original_run(self):
        from opencontractserver.tasks.corpus_tasks import ensure_embeddings_for_corpus
        from opencontractserver.tasks.embeddings_task import (
            calculate_embeddings_for_annotation_batch,
        )
        from opencontractserver.utils.structural_sets import (
            create_structural_annotation_set,
        )

        run = self.new_run()
        doc, reservation = self.reserve(run)
        label = AnnotationLabel.objects.create(text="Span", creator=self.user)
        Annotation.objects.create(
            document=doc,
            corpus=self.corpus,
            annotation_label=label,
            raw_text="Shared text",
            structural=True,
            creator=self.user,
        )
        create_structural_annotation_set(doc, self.user, parser_name="TextParser")
        other = Corpus.objects.create(
            title="Copy destination",
            creator=self.user,
            preferred_embedder="unapproved.Provider",
        )
        with patch.object(
            ensure_embeddings_for_corpus,
            "delay",
            side_effect=ensure_embeddings_for_corpus.run,
        ), patch.object(
            calculate_embeddings_for_annotation_batch,
            "delay",
            side_effect=calculate_embeddings_for_annotation_batch.run,
        ), patch(
            "opencontractserver.tasks.embeddings_task.get_component_by_name"
        ) as legacy_provider:
            copied, _, _ = other.add_document(document=doc, user=self.user)
        legacy_provider.assert_not_called()
        self.assertEqual(copied.ingestion_run_id, run.pk)
        self.assertEqual(
            copied.structural_annotation_set_id, doc.structural_annotation_set_id
        )
        self.assert_totals(run, accounted="0", reserved="0.000004")
        self.assertEqual(run.status, IngestionRun.Status.ACTIVE)
        self.assertEqual(run.operations.count(), 1)
        self.assertTrue(run.events.filter(code="suppressed_corpus_embedding").exists())
        with patch.object(
            OpenAIEmbedder, "embed_text_accounted", return_value=([0.25] * 384, 2)
        ) as provider:
            execute_reservation(reservation.pk)
        provider.assert_called_once()
        self.assert_totals(run, accounted="0.000002", reserved="0")

    def test_corpus_deletion_reports_retained_run_records_without_deleting_them(self):
        from opencontractserver.corpuses.services.corpus_service import CorpusService

        run = self.new_run()
        control_run(run.pk, "cancel")
        result = CorpusService.delete_corpus(self.user, self.corpus)
        self.assertFalse(result.ok)
        self.assertIn("retained records", result.error)
        self.assertTrue(Corpus.objects.filter(pk=self.corpus.pk).exists())
        self.assertTrue(IngestionRun.objects.filter(pk=run.pk).exists())

    def test_run_suppression_preserves_worker_task_permission_checks(self):
        from opencontractserver.tasks.doc_tasks import (
            convert_document_to_pdf,
            ingest_doc,
        )

        run = self.new_run()
        doc = self.document(run)
        outsider = get_user_model().objects.create_user("outsider")
        for task in (convert_document_to_pdf, ingest_doc):
            with self.subTest(task=task.name):
                result = task(user_id=outsider.pk, doc_id=doc.pk)
                self.assertEqual(
                    result.get("error"), "User lacks permission for this document"
                )
        self.assertFalse(run.events.filter(code__startswith="suppressed_").exists())

    def test_run_policy_rejects_parse_retry_without_clearing_failed_state(self):
        from opencontractserver.tasks.doc_tasks import retry_document_processing

        doc = self.document(self.new_run())
        doc.processing_status = DocumentProcessingStatus.FAILED
        doc.processing_error = "Original failure"
        doc.save(update_fields=["processing_status", "processing_error"])
        with patch("opencontractserver.tasks.doc_tasks.chain") as pipeline:
            result = retry_document_processing(user_id=self.user.pk, doc_id=doc.pk)
        self.assertEqual(result["status"], "error")
        self.assertIn("run policy", result["message"])
        pipeline.assert_not_called()
        doc.refresh_from_db()
        self.assertEqual(doc.processing_status, DocumentProcessingStatus.FAILED)
        self.assertEqual(doc.processing_error, "Original failure")

    def test_late_attempt_accounts_usage_but_cannot_overwrite_retry_result(self):
        run = self.new_run("0.000008")
        doc, original = self.reserve(run)
        calls = []

        def complete_retry_before_original(text):
            calls.append(text)
            if len(calls) == 1:
                control_run(
                    run.pk, "retry_operation", operation_id=original.operation_id
                )
                retry = original.operation.reservations.get(attempt=2)
                execute_reservation(retry.pk)
                return [0.5] * 384, 1
            return [0.25] * 384, 1

        with patch.object(
            OpenAIEmbedder,
            "embed_text_accounted",
            side_effect=complete_retry_before_original,
        ):
            execute_reservation(original.pk)
        self.assertEqual(calls, ["abcd", "abcd"])
        self.assertEqual(list(doc.get_embedding(OPENAI, 384)), [0.25] * 384)
        self.assertEqual(
            original.operation.reservations.filter(status="SETTLED").count(), 2
        )
        self.assert_totals(run, accounted="0.000002", reserved="0")

    def test_text_changed_during_request_cannot_receive_the_old_vector(self):
        run = self.new_run()
        doc, reservation = self.reserve(run)

        def change_text(text):
            doc.txt_extract_file = ContentFile(b"changed text", name="changed.txt")
            doc.save(update_fields=["txt_extract_file"])
            return [0.25] * 384, 2

        with patch.object(
            OpenAIEmbedder, "embed_text_accounted", side_effect=change_text
        ) as provider:
            execute_reservation(reservation.pk)
            execute_reservation(reservation.pk)
        provider.assert_called_once()
        self.assertFalse(Embedding.objects.filter(document=doc).exists())
        self.assert_totals(run, accounted="0.000002", reserved="0")
        self.assertEqual(run.status, "POLICY_VIOLATION")
        operation = run.operations.get()
        self.assertEqual(
            (operation.status, operation.error_code),
            ("FAILED", "operation_input_changed"),
        )

    def test_annotation_rehomed_during_request_cannot_receive_a_run_vector(self):
        run = self.new_run("1")
        doc = self.document(run)
        other = Document.objects.create(
            title="Outside run", creator=self.user, processing_started=timezone.now()
        )
        label = AnnotationLabel.objects.create(text="Span", creator=self.user)
        annotation = Annotation.objects.create(
            document=doc,
            corpus=self.corpus,
            annotation_label=label,
            raw_text="abcd",
            creator=self.user,
        )
        route_embedding(annotation)
        reservation = IngestionReservation.objects.get()

        def rehome_annotation(text):
            Annotation.objects.filter(pk=annotation.pk).update(document=other)
            return [0.25] * 384, 1

        with patch.object(
            OpenAIEmbedder, "embed_text_accounted", side_effect=rehome_annotation
        ):
            execute_reservation(reservation.pk)
        self.assertFalse(Embedding.objects.filter(annotation=annotation).exists())
        self.assert_totals(run, accounted="0.000001", reserved="0")
        self.assertEqual(run.last_error, "operation_input_changed")

    def relationship(self, run):
        doc = self.document(run)
        label = AnnotationLabel.objects.create(text="Span", creator=self.user)
        annotation = Annotation.objects.create(
            document=doc,
            corpus=self.corpus,
            annotation_label=label,
            raw_text="abcd",
            creator=self.user,
        )
        relationship = Relationship.objects.create(
            document=doc,
            corpus=self.corpus,
            relationship_label=label,
            creator=self.user,
        )
        relationship.source_annotations.add(annotation)
        relationship.target_annotations.add(annotation)
        return relationship, annotation

    def test_relationship_endpoint_text_changed_in_flight_blocks_publication(self):
        run = self.new_run("1")
        relationship, endpoint = self.relationship(run)
        route_embedding(relationship)
        reservation = IngestionReservation.objects.get()

        def change_endpoint(text):
            Annotation.objects.filter(pk=endpoint.pk).update(raw_text="changed")
            return [0.25] * 384, 1

        with patch.object(
            OpenAIEmbedder, "embed_text_accounted", side_effect=change_endpoint
        ):
            execute_reservation(reservation.pk)
        self.assertFalse(Embedding.objects.filter(relationship=relationship).exists())
        self.assert_totals(run, accounted="0.000001", reserved="0")
        self.assertEqual(run.last_error, "operation_input_changed")

    def test_relationship_publication_lock_blocks_endpoint_mutations(self):
        run = self.new_run("1")
        relationship, endpoint = self.relationship(run)
        extra = Annotation.objects.create(
            document=endpoint.document,
            corpus=self.corpus,
            annotation_label=endpoint.annotation_label,
            raw_text="new endpoint",
            creator=self.user,
        )
        route_embedding(relationship)
        operation = run.operations.get()

        def concurrent_edit(action):
            close_old_connections()
            try:
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute("SET LOCAL lock_timeout = '200ms'")
                    if action == "remove":
                        relationship.source_annotations.remove(endpoint)
                    elif action == "add":
                        relationship.source_annotations.add(extra)
                    else:
                        Annotation.objects.filter(pk=endpoint.pk).update(
                            raw_text="changed"
                        )
                return False
            except OperationalError as exc:
                return "lock timeout" in str(exc)
            finally:
                close_old_connections()

        with transaction.atomic():
            lock_target(operation)
            with ThreadPoolExecutor(max_workers=1) as pool:
                self.assertTrue(pool.submit(concurrent_edit, "edit").result(timeout=10))
                self.assertTrue(
                    pool.submit(concurrent_edit, "remove").result(timeout=10)
                )
                self.assertTrue(pool.submit(concurrent_edit, "add").result(timeout=10))
        endpoint.refresh_from_db()
        self.assertEqual(endpoint.raw_text, "abcd")
        self.assertTrue(relationship.source_annotations.filter(pk=endpoint.pk).exists())
        self.assertFalse(relationship.source_annotations.filter(pk=extra.pk).exists())

    def test_invalid_vector_settles_usage_and_explicit_retry_reserves_only_new_cost(
        self,
    ):
        run = self.new_run("0.000008")
        doc, reservation = self.reserve(run)
        with patch.object(
            OpenAIEmbedder, "embed_text_accounted", return_value=([0.25] * 768, 2)
        ) as provider:
            execute_reservation(reservation.pk)
            execute_reservation(reservation.pk)
        provider.assert_called_once()
        self.assertFalse(Embedding.objects.filter(document=doc).exists())
        self.assert_totals(run, accounted="0.000002", reserved="0")
        self.assertEqual(run.operations.get().status, "FAILED")
        control_run(run.pk, "retry_operation", operation_id=reservation.operation_id)
        control_run(run.pk, "resume")
        self.assert_totals(run, accounted="0.000002", reserved="0.000004")

    def test_embedding_storage_error_does_not_discard_known_usage(self):
        run = self.new_run()
        doc, reservation = self.reserve(run)
        with patch.object(
            OpenAIEmbedder, "embed_text_accounted", return_value=([0.25] * 384, 2)
        ) as provider, patch.object(
            Document,
            "add_embedding",
            side_effect=IntegrityError("private storage details"),
        ):
            execute_reservation(reservation.pk)
            execute_reservation(reservation.pk)
        provider.assert_called_once()
        self.assertFalse(Embedding.objects.filter(document=doc).exists())
        self.assert_totals(run, accounted="0.000002", reserved="0")
        self.assertEqual(run.last_error, "embedding_publication_failed")
        self.assertNotIn(
            "private storage details", json.dumps(run_report(run), default=str)
        )

    def test_deleted_target_still_settles_known_provider_usage(self):
        run = self.new_run()
        doc, reservation = self.reserve(run)

        def delete_target(text):
            with patch("opencontractserver.documents.signals._flush_blob_cleanup"):
                doc.delete()
            return [0.25] * 384, 2

        with patch.object(
            OpenAIEmbedder, "embed_text_accounted", side_effect=delete_target
        ):
            execute_reservation(reservation.pk)
        self.assert_totals(run, accounted="0.000002", reserved="0")
        self.assertEqual(run.last_error, "operation_target_missing")

    def test_retry_limit_keeps_all_three_uncertain_reservations(self):
        run = self.new_run("0.000020")
        _, original = self.reserve(run)
        with patch.object(
            OpenAIEmbedder, "embed_text_accounted", side_effect=TimeoutError
        ) as provider:
            for attempt in range(1, 4):
                execute_reservation(
                    original.operation.reservations.get(attempt=attempt).pk
                )
                if attempt < 3:
                    control_run(
                        run.pk, "retry_operation", operation_id=original.operation_id
                    )
                    control_run(run.pk, "resume")
        with self.assertRaisesRegex(RunPolicyError, "retry_exhausted"):
            control_run(run.pk, "retry_operation", operation_id=original.operation_id)
        self.assertEqual(provider.call_count, 3)
        self.assertEqual(IngestionOperation.objects.get().status, "UNCERTAIN")
        self.assert_totals(run, accounted="0", reserved="0.000012")

    def test_provider_timeout_retains_bound_and_retry_reserves_additional_allowance(
        self,
    ):
        run = self.new_run("0.000008")
        _, reservation = self.reserve(run)
        with patch.object(
            OpenAIEmbedder,
            "embed_text_accounted",
            side_effect=TimeoutError("secret-provider-credential"),
        ):
            execute_reservation(reservation.pk)
        self.assert_totals(run, accounted="0", reserved="0.000004")
        operation = reservation.operation
        control_run(run.pk, "retry_operation", operation_id=operation.pk)
        control_run(run.pk, "resume")
        retry = operation.reservations.get(attempt=2)
        self.assert_totals(run, accounted="0", reserved="0.000008")
        with patch.object(
            OpenAIEmbedder, "embed_text_accounted", return_value=([0.25] * 384, 1)
        ):
            execute_reservation(retry.pk)
        self.assert_totals(run, accounted="0.000001", reserved="0.000004")
        self.assertNotIn(
            "secret-provider-credential", json.dumps(run_report(run), default=str)
        )

    def test_crash_after_started_claim_keeps_reservation_on_redelivery_and_cancel(self):
        run = self.new_run()
        _, reservation = self.reserve(run)
        with patch.object(
            OpenAIEmbedder, "embed_text_accounted", side_effect=SystemExit
        ) as provider:
            with self.assertRaises(SystemExit):
                execute_reservation(reservation.pk)
            execute_reservation(reservation.pk)
        provider.assert_called_once()
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, IngestionReservation.Status.STARTED)
        control_run(run.pk, "cancel")
        self.assert_totals(run, accounted="0", reserved="0.000004")

    def test_cancel_before_claim_releases_unused_reservation_and_blocks_delivery(self):
        run = self.new_run()
        _, reservation = self.reserve(run)
        control_run(run.pk, "cancel")
        with patch.object(OpenAIEmbedder, "embed_text_accounted") as provider:
            execute_reservation(reservation.pk)
        provider.assert_not_called()
        self.assert_totals(run, accounted="0", reserved="0")

    def test_cancellation_during_request_accounts_usage_without_publishing_result(self):
        run = self.new_run()
        doc, reservation = self.reserve(run)

        def cancel_during_request(text):
            control_run(run.pk, "cancel")
            return [0.25] * 384, 1

        with patch.object(
            OpenAIEmbedder, "embed_text_accounted", side_effect=cancel_during_request
        ):
            execute_reservation(reservation.pk)
        self.assert_totals(run, accounted="0.000001", reserved="0")
        self.assertFalse(Embedding.objects.filter(document=doc).exists())

    def test_pause_keeps_queued_reservation_and_resume_dispatches_it(self):
        run = self.new_run()
        _, reservation = self.reserve(run)
        control_run(run.pk, "pause")
        with patch.object(OpenAIEmbedder, "embed_text_accounted") as provider:
            execute_reservation(reservation.pk)
        provider.assert_not_called()
        control_run(run.pk, "resume")
        self.assert_totals(run, accounted="0", reserved="0.000004")
        self.assertGreaterEqual(self.nudge.call_count, 2)

    def test_budget_increase_is_audited_and_admits_preserved_waiting_operation(self):
        run = self.new_run("0")
        doc = self.document(run)
        route_embedding(doc)
        original_operation = run.operations.get()
        control_run(run.pk, "resume", ceiling_usd="0.000004")
        self.assertEqual(run.operations.get().pk, original_operation.pk)
        self.assert_totals(run, accounted="0", reserved="0.000004")
        self.assertEqual(
            run.events.get(code="ceiling_increased").detail,
            {"previous": "0E-9", "current": "0.000004"},
        )

    @override_settings(INGESTION_RUN_PRICING={})
    def test_unknown_pricing_is_not_admitted_as_free(self):
        with self.assertRaisesRegex(RunPolicyError, "unknown_pricing"):
            self.new_run()
        self.assertFalse(IngestionRun.objects.exists())

    @override_settings(INGESTION_RUN_PRICING={})
    def test_prepared_only_run_suppresses_server_embedding_with_zero_allowance(self):
        from opencontractserver.tasks.embeddings_task import (
            calculate_embedding_for_doc_text,
        )

        run = create_run(
            self.token,
            ceiling_usd="0",
            preparations=[PREPARATION],
            embedding_mode="prepared",
        )
        doc = self.document(run)
        with patch(
            "opencontractserver.tasks.embeddings_task.get_component_by_name"
        ) as legacy, patch(
            "opencontractserver.worker_uploads.run_policy.resolve_provider"
        ) as accounted:
            calculate_embedding_for_doc_text(doc_id=doc.pk)
        legacy.assert_not_called()
        accounted.assert_not_called()
        self.assertFalse(run.operations.exists())
        self.assertFalse(Embedding.objects.filter(document=doc).exists())
        self.assert_totals(run, accounted="0", reserved="0")
        self.assertEqual(run.status, "ACTIVE")

    def test_provider_change_between_admission_and_execution_blocks_request(self):
        run = self.new_run()
        _, reservation = self.reserve(run)
        self.pipeline.component_settings[OPENAI]["openai_embedding_dimensions"] = 768
        self.pipeline.save()
        with patch.object(OpenAIEmbedder, "embed_text_accounted") as provider:
            execute_reservation(reservation.pk)
        provider.assert_not_called()
        self.assert_totals(run, accounted="0", reserved="0.000004")
        self.assertEqual(run.last_error, "provider_configuration_changed")

    def test_changed_pricing_pauses_reserved_work_before_provider_call(self):
        run = self.new_run()
        _, reservation = self.reserve(run)
        with override_settings(
            INGESTION_RUN_PRICING={**PRICING, "version": "new-price-v2"}
        ), patch.object(OpenAIEmbedder, "embed_text_accounted") as provider:
            execute_reservation(reservation.pk)
        provider.assert_not_called()
        self.assert_totals(run, accounted="0", reserved="0.000004")
        self.assertEqual(run.last_error, "pricing_changed")

    def test_global_provider_change_before_admission_creates_no_reservation(self):
        Corpus.objects.filter(pk=self.corpus.pk).update(preferred_embedder=None)
        run = self.new_run()
        self.pipeline.default_embedder = (
            "opencontractserver.pipeline.embedders.test_embedder.TestEmbedder"
        )
        self.pipeline.save()
        route_embedding(self.document(run))
        self.assertFalse(IngestionReservation.objects.exists())
        run.refresh_from_db()
        self.assertEqual(run.status, IngestionRun.Status.POLICY_VIOLATION)

    def test_disabling_corpus_provider_blocks_already_reserved_work(self):
        run = self.new_run()
        _, reservation = self.reserve(run)
        self.pipeline.enabled_components = [
            "opencontractserver.pipeline.embedders.test_embedder.TestEmbedder"
        ]
        self.pipeline.save()
        with patch.object(OpenAIEmbedder, "embed_text_accounted") as provider:
            execute_reservation(reservation.pk)
        provider.assert_not_called()
        self.assert_totals(run, accounted="0", reserved="0.000004")
        self.assertEqual(run.last_error, "unbounded_provider")

    def test_dimension_larger_than_the_model_supports_is_rejected_at_creation(self):
        self.pipeline.component_settings[OPENAI]["openai_embedding_dimensions"] = 3072
        self.pipeline.save()
        with self.assertRaisesRegex(RunPolicyError, "unsupported_embedding_dimension"):
            self.new_run()
        self.assertFalse(IngestionRun.objects.exists())

    def test_custom_provider_endpoint_is_not_assumed_to_have_openai_pricing(self):
        self.pipeline.component_settings[OPENAI][
            "openai_api_base_url"
        ] = "https://secret@proxy.invalid/v1"
        self.pipeline.save()
        with self.assertRaisesRegex(RunPolicyError, "unbounded_provider"):
            self.new_run()

    def test_multimodal_to_text_fallback_is_prohibited(self):
        run = self.new_run()
        doc = self.document(run)
        label = AnnotationLabel.objects.create(text="Image", creator=self.user)
        annot = Annotation.objects.create(
            document=doc,
            corpus=self.corpus,
            annotation_label=label,
            creator=self.user,
            raw_text="image caption",
            content_modalities=["IMAGE"],
        )
        with patch.object(OpenAIEmbedder, "embed_text_accounted") as provider:
            route_embedding(annot)
        provider.assert_not_called()
        self.assertFalse(IngestionReservation.objects.exists())
        run.refresh_from_db()
        self.assertEqual(run.last_error, "prohibited_multimodal_fallback")

    def test_queued_annotation_cannot_gain_an_unapproved_modality(self):
        run = self.new_run("1")
        doc = self.document(run)
        label = AnnotationLabel.objects.create(text="Span", creator=self.user)
        annotation = Annotation.objects.create(
            document=doc,
            corpus=self.corpus,
            annotation_label=label,
            raw_text="abcd",
            creator=self.user,
        )
        route_embedding(annotation)
        reservation = IngestionReservation.objects.get()
        Annotation.objects.filter(pk=annotation.pk).update(content_modalities=["IMAGE"])
        with patch.object(OpenAIEmbedder, "embed_text_accounted") as provider:
            execute_reservation(reservation.pk)
        provider.assert_not_called()
        run.refresh_from_db()
        self.assertEqual(run.last_error, "prohibited_multimodal_fallback")

    def test_database_rejects_policy_edits_and_removal_of_document_binding(self):
        run = self.new_run()
        doc = self.document(run)
        with self.assertRaises(IntegrityError), transaction.atomic():
            IngestionRun.objects.filter(pk=run.pk).update(policy={"secret": "attempt"})
        with self.assertRaises(IntegrityError), transaction.atomic():
            Document.objects.filter(pk=doc.pk).update(ingestion_run=None)

    def test_database_rejects_retargeting_or_repricing_admitted_operations(self):
        run = self.new_run()
        _, reservation = self.reserve(run)
        other_run = self.new_run()
        changes = {
            "run_id": other_run.pk,
            "key": "replacement",
            "target_type": "annotation",
            "target_id": 99999,
            "input_digest": "b" * 64,
            "estimated_usd": "0.5",
        }
        for field, value in changes.items():
            with self.subTest(field=field), self.assertRaisesRegex(
                IntegrityError, "operation identity is immutable"
            ), transaction.atomic():
                IngestionOperation.objects.filter(pk=reservation.operation_id).update(
                    **{field: value}
                )
        self.assert_totals(run, accounted="0", reserved="0.000004")

    def test_database_rejects_reassigning_or_resizing_a_reservation(self):
        run = self.new_run()
        _, reservation = self.reserve(run)
        other = IngestionOperation.objects.create(
            run=run,
            key="other-operation",
            target_type="document",
            target_id=reservation.operation.target_id,
            input_digest="b" * 64,
            estimated_usd="0.000001",
        )
        for field, value in {
            "operation_id": other.pk,
            "attempt": 9,
            "amount_usd": "0.5",
        }.items():
            with self.subTest(field=field), self.assertRaisesRegex(
                IntegrityError, "reservation identity is immutable"
            ), transaction.atomic():
                IngestionReservation.objects.filter(pk=reservation.pk).update(
                    **{field: value}
                )
        self.assert_totals(run, accounted="0", reserved="0.000004")

    def test_run_status_and_controls_require_same_worker_and_corpus(self):
        run = self.new_run()
        other_corpus = Corpus.objects.create(title="Other", creator=self.user)
        _, key = CorpusAccessToken.create_token(
            worker_account=self.account, corpus=other_corpus
        )
        self.api_client.credentials(HTTP_AUTHORIZATION=f"WorkerKey {key}")
        url = f"/api/worker-uploads/runs/{run.pk}/"
        self.assertEqual(self.api_client.get(url).status_code, 404)
        self.assertEqual(
            self.api_client.post(url, {"action": "cancel"}, format="json").status_code,
            404,
        )
        run.refresh_from_db()
        self.assertEqual(run.status, IngestionRun.Status.ACTIVE)

    def test_create_replay_preserves_policy_and_rejects_a_different_ceiling(self):
        payload = {
            "id": str(uuid4()),
            "ceiling_usd": "1",
            "preparations": [PREPARATION],
            "embedding_mode": "server",
        }
        url = "/api/worker-uploads/runs/"
        first = self.api_client.post(url, payload, format="json")
        self.assertEqual(first.status_code, 201, first.data)
        control_run(payload["id"], "resume", ceiling_usd="2")
        replay = self.api_client.post(url, payload, format="json")
        self.assertEqual(replay.status_code, 201, replay.data)
        self.assertEqual(replay.data["id"], first.data["id"])
        self.assertEqual(Decimal(replay.data["ceiling_usd"]), Decimal(2))
        self.assertEqual(replay.data["policy"]["initial_ceiling_usd"], "1")
        self.assertNotIn(
            "secret-provider-credential", json.dumps(replay.data, default=str)
        )
        self.assertEqual(
            self.api_client.post(
                url, {**payload, "ceiling_usd": "3"}, format="json"
            ).status_code,
            409,
        )
        self.assertEqual(IngestionRun.objects.count(), 1)

    def test_report_pages_all_operations_with_their_reservations(self):
        run = self.new_run("1")
        operations = IngestionOperation.objects.bulk_create(
            [
                IngestionOperation(
                    run=run,
                    key=str(i),
                    target_type="document",
                    target_id=i,
                    input_digest="a" * 64,
                    estimated_usd="0.000001",
                )
                for i in range(101)
            ]
        )
        # Use the actual page ordering, including its stable UUID tie breaker.
        last = run.operations.order_by("created", "pk").last()
        reservation = IngestionReservation.objects.create(
            operation=last, attempt=1, amount_usd="0.000001"
        )
        IngestionRun.objects.filter(pk=run.pk).update(reserved_usd="0.000001")
        url = f"/api/worker-uploads/runs/{run.pk}/"
        first = self.api_client.get(url).json()
        second = self.api_client.get(url, {"offset": first["next_offset"]}).json()
        seen = {op["id"] for op in first["operations"] + second["operations"]}
        self.assertEqual(seen, {str(op.pk) for op in operations})
        self.assertEqual(second["reservations"][0]["id"], str(reservation.pk))
        self.assertIsNone(second["next_offset"])
        self.assertEqual(Decimal(run_report(run)["reserved_usd"]), Decimal("0.000001"))
        self.assertEqual(self.api_client.get(url, {"offset": -1}).status_code, 400)

    def test_upload_revalidation_does_not_persist_exception_details(self):
        sensitive = "provider credential=secret at /private/provider.py:42"
        run = self.new_run("1")
        metadata = _make_metadata(
            preparation_identity=PREPARATION["fingerprint"],
            parser_name="TextParser",
            parser_version="1.0",
            ingestion_run_id=str(run.pk),
        )
        upload, _ = stage_upload(self.token, _make_fake_pdf(), metadata, "safe-error")
        upload.status = UploadStatus.PROCESSING
        upload.processing_token = uuid4()
        upload.processing_attempts = 1
        upload.save()
        with patch(
            "opencontractserver.worker_uploads.run_policy.validate_preparation",
            side_effect=RunPolicyError(sensitive),
        ):
            self.assertFalse(_process_single_upload(upload.pk, upload.processing_token))
        upload.refresh_from_db()
        self.assertEqual(upload.status, UploadStatus.PENDING)
        self.assertEqual(upload.processing_attempts, 0)
        response = self.api_client.get(f"/api/worker-uploads/runs/{run.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["last_error"], "run_policy_error")
        self.assertTrue(run.events.filter(code="run_policy_error").exists())
        self.assertNotIn(sensitive, response.content.decode())

    def test_configuration_drift_keeps_accepted_upload_pending_without_an_attempt(self):
        run = self.new_run("1")
        metadata = _make_metadata(
            preparation_identity=PREPARATION["fingerprint"],
            parser_name="TextParser",
            parser_version="1.0",
            ingestion_run_id=str(run.pk),
        )
        upload, _ = stage_upload(self.token, _make_fake_pdf(), metadata, "drift-upload")
        upload.status = UploadStatus.PROCESSING
        upload.processing_token = uuid4()
        upload.processing_attempts = 1
        upload.save()
        self.pipeline.component_settings[OPENAI]["openai_embedding_dimensions"] = 768
        self.pipeline.save()
        self.assertFalse(_process_single_upload(upload.pk, upload.processing_token))
        upload.refresh_from_db()
        self.assertEqual(upload.status, UploadStatus.PENDING)
        self.assertEqual(upload.processing_attempts, 0)
        self.assertTrue(upload.file.storage.exists(upload.file.name))
        self.assertFalse(Document.objects.filter(ingestion_run=run).exists())
        run.refresh_from_db()
        self.assertEqual(run.status, "POLICY_VIOLATION")

    def test_upload_receipt_and_prepared_artifacts_survive_budget_exhaustion(self):
        run = self.new_run("0")
        metadata = _make_metadata(
            preparation_identity=PREPARATION["fingerprint"],
            parser_name="TextParser",
            parser_version="1.0",
            ingestion_run_id=str(run.pk),
        )
        upload, _ = stage_upload(
            self.token, _make_fake_pdf(), metadata, "budget-upload"
        )
        upload.status = UploadStatus.PROCESSING
        upload.processing_token = uuid4()
        upload.processing_attempts = 1
        upload.save()
        with patch.object(OpenAIEmbedder, "embed_text_accounted") as provider:
            self.assertTrue(_process_single_upload(upload.pk, upload.processing_token))
        provider.assert_not_called()
        upload.refresh_from_db()
        self.assertEqual(upload.status, UploadStatus.COMPLETED)
        self.assertEqual(upload.result_document.ingestion_run_id, run.pk)
        with upload.result_document.txt_extract_file.open("rb") as text:
            self.assertEqual(text.read().decode(), metadata["content"])
        run.refresh_from_db()
        self.assertEqual(run.status, IngestionRun.Status.BUDGET_EXHAUSTED)
        replay, created = stage_upload(
            self.token, _make_fake_pdf(), metadata, "budget-upload"
        )
        self.assertFalse(created)
        self.assertEqual(replay.pk, upload.pk)
        response = self.api_client.get(f"/api/worker-uploads/documents/{upload.pk}/")
        self.assertEqual(response.json()["run_status"], "BUDGET_EXHAUSTED")

    def test_crash_at_post_commit_dispatch_leaves_receipt_and_operations_recoverable(
        self,
    ):
        from opencontractserver.worker_uploads.run_tasks import (
            process_ingestion_operation,
            process_pending_ingestion_operations,
        )

        run = self.new_run("1")
        metadata = _structural_metadata()
        metadata.update(
            preparation_identity=PREPARATION["fingerprint"],
            parser_name="TextParser",
            parser_version="1.0",
            ingestion_run_id=str(run.pk),
        )
        upload, _ = stage_upload(self.token, _make_fake_pdf(), metadata, "crash-upload")
        upload.status = UploadStatus.PROCESSING
        upload.processing_token = uuid4()
        upload.processing_attempts = 1
        upload.save()
        self.nudge.side_effect = SystemExit
        with self.assertRaises(SystemExit):
            _process_single_upload(upload.pk, upload.processing_token)
        upload.refresh_from_db()
        self.assertEqual(upload.status, UploadStatus.COMPLETED)
        reservations = set(
            IngestionReservation.objects.filter(operation__run=run).values_list(
                "pk", flat=True
            )
        )
        self.assertGreaterEqual(
            len(reservations), 2
        )  # Document and imported text annotations.
        with patch.object(process_ingestion_operation, "delay") as dispatch:
            self.assertEqual(process_pending_ingestion_operations(), len(reservations))
        self.assertEqual(
            {call.args[0] for call in dispatch.call_args_list},
            {str(pk) for pk in reservations},
        )

    def test_identical_source_in_two_runs_has_independent_structural_work_and_costs(
        self,
    ):
        runs = [self.new_run("1"), self.new_run("1")]
        documents = []
        for run in runs:
            metadata = _structural_metadata(with_embeddings=False)
            metadata.update(
                preparation_identity=PREPARATION["fingerprint"],
                parser_name="TextParser",
                parser_version="1.0",
                ingestion_run_id=str(run.pk),
            )
            upload, _ = stage_upload(
                self.token, _make_fake_pdf(), metadata, str(run.pk)
            )
            upload.status = UploadStatus.PROCESSING
            upload.processing_token = uuid4()
            upload.processing_attempts = 1
            upload.save()
            self.assertTrue(_process_single_upload(upload.pk, upload.processing_token))
            upload.refresh_from_db()
            documents.append(upload.result_document)
        first, second = documents
        with first.pdf_file.open("rb") as first_source, second.pdf_file.open(
            "rb"
        ) as second_source:
            self.assertEqual(first_source.read(), second_source.read())
        self.assertNotEqual(
            first.structural_annotation_set_id, second.structural_annotation_set_id
        )
        with patch.object(
            OpenAIEmbedder, "embed_text_accounted", return_value=([0.25] * 384, 1)
        ):
            for reservation in IngestionReservation.objects.order_by("created"):
                execute_reservation(reservation.pk)
        for run in runs:
            run.refresh_from_db()
            self.assertEqual(run.status, "ACTIVE")
            self.assertGreater(run.operations.count(), 2)
            self.assertEqual(
                set(run.operations.values_list("status", flat=True)), {"COMPLETED"}
            )
            self.assert_totals(
                run,
                accounted=str(run.operations.count() * Decimal("0.000001")),
                reserved="0",
            )

    def test_populated_source_hash_cannot_share_structural_sets_across_run_boundaries(
        self,
    ):
        from opencontractserver.utils.structural_sets import (
            create_structural_annotation_set,
        )

        runs = [self.new_run("1"), self.new_run("1")]
        label = AnnotationLabel.objects.create(text="Span", creator=self.user)
        for run in [None, *runs]:
            doc = self.document(run)
            doc.pdf_file_hash = "a" * 64
            doc.save(update_fields=["pdf_file_hash"])
            annotation = Annotation.objects.create(
                document=doc,
                corpus=self.corpus,
                annotation_label=label,
                raw_text="same source",
                structural=True,
                creator=self.user,
            )
            create_structural_annotation_set(doc, self.user, parser_name="TextParser")
            annotation.refresh_from_db()
            self.assertEqual(route_embedding(annotation), run is not None)
        self.assertEqual(StructuralAnnotationSet.objects.count(), 3)
        for run in runs:
            run.refresh_from_db()
            self.assertEqual(run.status, "ACTIVE")
            self.assertEqual(run.operations.count(), 1)
            self.assertEqual(
                IngestionReservation.objects.filter(operation__run=run).count(), 1
            )

    def test_downstream_tasks_cannot_select_an_unpriced_stage_or_provider(self):
        from opencontractserver.analyzer.models import Analyzer
        from opencontractserver.corpuses.models import CorpusAction
        from opencontractserver.tasks.corpus_tasks import process_corpus_action
        from opencontractserver.tasks.doc_tasks import (
            convert_document_to_pdf,
            extract_thumbnail,
            ingest_doc,
        )
        from opencontractserver.tasks.embeddings_task import (
            calculate_embedding_for_doc_text,
            calculate_embeddings_for_annotation_batch,
            calculate_embeddings_for_relationship_batch,
        )

        run = self.new_run("1")
        doc = self.document(run)
        analyzer = Analyzer.objects.create(
            description="Chargeable analyzer",
            creator=self.user,
            task_name="budget.test_analyzer",
        )
        CorpusAction.objects.create(
            name="Automatic analysis",
            corpus=self.corpus,
            analyzer=analyzer,
            trigger="add_document",
            creator=self.user,
        )
        label = AnnotationLabel.objects.create(text="Span", creator=self.user)
        annot = Annotation.objects.create(
            document=doc,
            corpus=self.corpus,
            annotation_label=label,
            creator=self.user,
            raw_text="annotation",
        )
        rel = Relationship.objects.create(
            document=doc,
            corpus=self.corpus,
            relationship_label=label,
            creator=self.user,
        )
        rel.source_annotations.add(annot)
        rel.target_annotations.add(annot)
        with patch(
            "opencontractserver.tasks.doc_tasks.get_component_by_name"
        ) as parser, patch(
            "opencontractserver.tasks.embeddings_task.get_component_by_name"
        ) as legacy_provider, patch(
            "opencontractserver.tasks.corpus_tasks.process_analyzer", return_value=None
        ) as action:
            ingest_doc(user_id=self.user.pk, doc_id=doc.pk)
            convert_document_to_pdf(user_id=self.user.pk, doc_id=doc.pk)
            extract_thumbnail(doc_id=doc.pk)
            process_corpus_action(
                corpus_id=self.corpus.pk, document_ids=[doc.pk], user_id=self.user.pk
            )
            action.assert_not_called()
            calculate_embedding_for_doc_text(doc_id=doc.pk)
            calculate_embedding_for_doc_text(
                doc_id=doc.pk, embedder_path="unapproved.Provider"
            )
            calculate_embeddings_for_annotation_batch(
                annotation_ids=[annot.pk], embedder_path="unapproved.Provider"
            )
            calculate_embeddings_for_relationship_batch(
                relationship_ids=[rel.pk], embedder_path="unapproved.Provider"
            )
            ordinary = Document.objects.create(
                title="Ordinary", creator=self.user, processing_started=timezone.now()
            )
            process_corpus_action(
                corpus_id=self.corpus.pk,
                document_ids=[ordinary.pk],
                user_id=self.user.pk,
            )
        parser.assert_not_called()
        legacy_provider.assert_not_called()
        action.assert_called_once()
        self.assertEqual(run.operations.count(), 3)
        self.assertEqual(
            set(run.events.values_list("code", flat=True)) - {"created"},
            {
                "suppressed_parse",
                "suppressed_convert",
                "suppressed_thumbnail",
                "suppressed_corpus_action",
            },
        )


class AccountedOpenAIAdapterTests(SimpleTestCase):
    def test_request_disables_sdk_retries_and_returns_provider_usage(self):
        provider = OpenAIEmbedder(
            component_settings={
                "openai_api_key": "private-key",
                "openai_embedding_model": "text-embedding-3-small",
                "openai_embedding_dimensions": 384,
            }
        )
        client = MagicMock()
        client.with_options.return_value.__enter__.return_value = client
        client.embeddings.create.return_value = SimpleNamespace(
            data=[SimpleNamespace(embedding=[0.25] * 384)],
            usage=SimpleNamespace(prompt_tokens=2),
        )
        with patch.object(provider, "_build_client", return_value=client) as build:
            vector, tokens = provider.embed_text_accounted("abcd")
        build.assert_called_once_with(openai_api_base_url="https://api.openai.com/v1")
        client.with_options.assert_called_once_with(max_retries=0)
        client.embeddings.create.assert_called_once_with(
            input="abcd", model="text-embedding-3-small", dimensions=384
        )
        self.assertEqual((vector, tokens), ([0.25] * 384, 2))
