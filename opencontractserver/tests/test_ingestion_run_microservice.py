"""Policy-bound self-hosted embeddings use normal readiness and retry machinery."""

import hashlib
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import requests
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import SimpleTestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from config.graphql.schema import schema
from config.graphql.testing import Client
from opencontractserver.annotations.models import Embedding, LabelSet
from opencontractserver.constants.document_processing import (
    EMBEDDER_SINGLE_REQUEST_TIMEOUT_SECONDS,
    OPENAI_EMBEDDER_MAX_INPUT_CHARS,
)
from opencontractserver.constants.embeddings import MICROSERVICE_EMBEDDER_PATH as MICRO
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, PipelineSettings
from opencontractserver.documents.readiness import assess_document, effective_embedder
from opencontractserver.pipeline.embedders.sent_transformer_microservice import (
    MicroserviceEmbedder,
)
from opencontractserver.tests.test_ingestion_run_budget import PREPARATION
from opencontractserver.tests.test_worker_uploads import (
    _make_fake_pdf,
    _structural_metadata,
)
from opencontractserver.utils.embedding_identity import embedding_configuration
from opencontractserver.worker_uploads.models import (
    CorpusAccessToken,
    UploadStatus,
    WorkerAccount,
)
from opencontractserver.worker_uploads.run_models import (
    IngestionReservation,
    IngestionRun,
)
from opencontractserver.worker_uploads.run_policy import RunPolicyError
from opencontractserver.worker_uploads.run_services import (
    control_run,
    create_run,
    execute_reservation,
    route_embedding,
    run_report,
)
from opencontractserver.worker_uploads.tasks import _process_single_upload
from opencontractserver.worker_uploads.upload_recovery import stage_upload

SERVICE_SETTINGS = {
    "embeddings_microservice_url": "https://embedder.invalid",
    "vector_embedder_api_key": "private-service-key",
    "embedding_model_revision": "multi-qa-MiniLM-L6-cos-v1@immutable-revision",
    "no_external_provider_fees": True,
}


@override_settings(INGESTION_RUN_PRICING={}, EMBEDDING_MODEL_REVISIONS={})
class MicroserviceIngestionRunTests(TransactionTestCase):
    def setUp(self):
        nudge = patch("opencontractserver.worker_uploads.run_services._nudge")
        nudge.start()
        self.addCleanup(nudge.stop)
        self.user = get_user_model().objects.create_superuser(
            "sentence-owner", "sentence@example.com", "pw"
        )
        account = WorkerAccount.create_with_user(
            name="Sentence worker", creator=self.user
        )
        self.pipeline = PipelineSettings.get_instance(use_cache=False)
        self.pipeline.default_embedder = MICRO
        self.pipeline.component_settings = {MICRO: dict(SERVICE_SETTINGS)}
        self.pipeline.save()
        self.addCleanup(PipelineSettings.clear_cache)
        self.corpus = Corpus.objects.create(
            title="Sentence corpus",
            creator=self.user,
            label_set=LabelSet.objects.create(title="Labels", creator=self.user),
        )
        self.token, self.key = CorpusAccessToken.create_token(
            worker_account=account, corpus=self.corpus
        )
        self.assertEqual(self.corpus.preferred_embedder, MICRO)

    def test_public_settings_and_run_apis_enable_default_service_with_zero_ceiling(
        self,
    ):
        client = Client(schema, context_value=SimpleNamespace(user=self.user))
        mutation = """
            mutation Configure($componentSettings: GenericScalar, $embedder: String) {
                updatePipelineSettings(
                    componentSettings: $componentSettings, defaultEmbedder: $embedder
                ) { ok message }
            }
        """
        config = {
            key: value
            for key, value in SERVICE_SETTINGS.items()
            if key != "vector_embedder_api_key"
        }
        result = client.execute(
            mutation,
            variables={"componentSettings": {MICRO: config}, "embedder": MICRO},
        )
        self.assertIsNone(result.get("errors"), result)
        self.assertTrue(result["data"]["updatePipelineSettings"]["ok"], result)
        # Corpus.save normally snapshots the default; an unset preference must
        # also resolve through the application-configured default at run creation.
        Corpus.objects.filter(pk=self.corpus.pk).update(preferred_embedder="")
        self.corpus.refresh_from_db()
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f"WorkerKey {self.key}")
        response = api.post(
            "/api/worker-uploads/runs/",
            {
                "ceiling_usd": "0",
                "preparations": [PREPARATION],
                "embedding_mode": "server",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        run = IngestionRun.objects.get(pk=response.data["id"])
        self.assertEqual(run.ceiling_usd, 0)
        self.assertEqual(run.policy["provider"]["path"], MICRO)
        self.assertEqual(
            run.policy["provider"]["model"],
            SERVICE_SETTINGS["embedding_model_revision"],
        )
        self.assertEqual(run.policy["pricing"]["usd_per_million_tokens"], "0")
        for key, invalid in (
            ("no_external_provider_fees", "yes"),
            ("embedding_model_revision", ["invalid"]),
        ):
            with self.subTest(key=key):
                result = client.execute(
                    mutation,
                    variables={"componentSettings": {MICRO: {**config, key: invalid}}},
                )
                self.assertIsNone(result.get("errors"), result)
                self.assertFalse(result["data"]["updatePipelineSettings"]["ok"], result)

    def new_run(self):
        return create_run(
            self.token,
            ceiling_usd="0",
            preparations=[PREPARATION],
            embedding_mode="server",
        )

    def reserve(self, run):
        document = Document.objects.create(
            title="Text",
            creator=self.user,
            ingestion_run=run,
            file_type="text/plain",
            processing_started=timezone.now(),
            txt_extract_file=ContentFile(b"hello", name="body.txt"),
        )
        self.assertTrue(route_embedding(document))
        return document, IngestionReservation.objects.get(
            operation__target_id=document.pk
        )

    def test_zero_ceiling_upload_generates_searchable_document_and_annotation_vectors(
        self,
    ):
        run = self.new_run()
        metadata = _structural_metadata(with_embeddings=False)
        metadata.update(
            preparation_identity=PREPARATION["fingerprint"],
            parser_name="TextParser",
            parser_version="1.0",
            ingestion_run_id=str(run.pk),
        )
        upload, _ = stage_upload(
            self.token, _make_fake_pdf(), metadata, "sentence-upload"
        )
        upload.status = UploadStatus.PROCESSING
        upload.processing_token = uuid4()
        upload.processing_attempts = 1
        upload.save()
        self.assertTrue(_process_single_upload(upload.pk, upload.processing_token))
        upload.refresh_from_db()
        self.assertEqual(upload.status, UploadStatus.COMPLETED)
        reservations = list(IngestionReservation.objects.filter(operation__run=run))
        self.assertGreater(len(reservations), 1)
        with patch.object(
            MicroserviceEmbedder, "embed_text_accounted", return_value=([0.25] * 384, 0)
        ) as provider:
            for reservation in reservations:
                execute_reservation(reservation.pk)
                execute_reservation(
                    reservation.pk
                )  # Redelivery is not a second request.
        self.assertEqual(provider.call_count, len(reservations))
        run.refresh_from_db()
        self.assertEqual(
            (run.status, run.accounted_usd, run.reserved_usd), ("ACTIVE", 0, 0)
        )
        self.assertEqual(
            set(run.operations.values_list("status", flat=True)), {"COMPLETED"}
        )
        document = upload.result_document
        assessment = assess_document(document, self.corpus)
        self.assertEqual(assessment["state"], "ready", assessment)
        fingerprint = effective_embedder(self.corpus)[2]
        self.assertEqual(run.policy["provider"]["configuration"], fingerprint)
        self.assertEqual(
            set(Embedding.objects.values_list("configuration", flat=True)),
            {fingerprint},
        )
        report = json.dumps(run_report(run), default=str)
        self.assertNotIn("private-service-key", report)
        self.assertNotIn("https://embedder.invalid", report)

    def test_fee_declaration_and_model_revision_are_required(self):
        for missing, code in (
            ("no_external_provider_fees", "unknown_pricing"),
            ("embedding_model_revision", "provider_model_revision_required"),
        ):
            with self.subTest(missing=missing):
                self.pipeline.component_settings = {MICRO: dict(SERVICE_SETTINGS)}
                self.pipeline.component_settings[MICRO].pop(missing)
                self.pipeline.save()
                with self.assertRaisesRegex(RunPolicyError, code):
                    self.new_run()

    def test_existing_deployment_model_revision_is_still_supported(self):
        self.pipeline.component_settings[MICRO].pop("embedding_model_revision")
        self.pipeline.save()
        with override_settings(
            EMBEDDING_MODEL_REVISIONS={MICRO: "legacy-model@revision"}
        ):
            self.assertEqual(
                self.new_run().policy["provider"]["model"], "legacy-model@revision"
            )

    def test_changed_configuration_or_revoked_fee_declaration_blocks_provider_calls(
        self,
    ):
        for key, value in (
            ("embedding_model_revision", "other-model@revision"),
            ("embeddings_microservice_url", "https://different.invalid"),
            ("no_external_provider_fees", False),
        ):
            with self.subTest(key=key):
                self.pipeline.component_settings = {MICRO: dict(SERVICE_SETTINGS)}
                self.pipeline.save()
                run = self.new_run()
                _, reservation = self.reserve(run)
                self.pipeline.component_settings[MICRO][key] = value
                self.pipeline.save()
                with patch.object(
                    MicroserviceEmbedder, "embed_text_accounted"
                ) as provider:
                    execute_reservation(reservation.pk)
                provider.assert_not_called()
                run.refresh_from_db()
                self.assertEqual(run.status, "POLICY_VIOLATION")

    def test_unknown_providers_and_credential_bearing_endpoints_are_rejected(self):
        for url in (
            "file:///tmp/embedder",
            "https://user:secret@embedder.invalid",
            "https://embedder.invalid?key=secret",
        ):
            with self.subTest(url=url):
                self.pipeline.component_settings[MICRO][
                    "embeddings_microservice_url"
                ] = url
                self.pipeline.save()
                with self.assertRaisesRegex(RunPolicyError, "unbounded_provider"):
                    self.new_run()
        self.corpus.preferred_embedder = "custom.UnpricedEmbedder"
        self.corpus.save()
        with self.assertRaisesRegex(RunPolicyError, "unbounded_provider"):
            self.new_run()

    def test_zero_fee_timeouts_still_require_explicit_bounded_retries(self):
        run = self.new_run()
        document, original = self.reserve(run)
        with patch.object(
            MicroserviceEmbedder,
            "embed_text_accounted",
            side_effect=requests.Timeout("private-service-key"),
        ) as provider:
            for attempt in range(1, 4):
                reservation = original.operation.reservations.get(attempt=attempt)
                execute_reservation(reservation.pk)
                execute_reservation(reservation.pk)
                if attempt < 3:
                    control_run(
                        run.pk, "retry_operation", operation_id=original.operation_id
                    )
                    control_run(run.pk, "resume")
        self.assertEqual(provider.call_count, 3)
        with self.assertRaisesRegex(RunPolicyError, "retry_exhausted"):
            control_run(run.pk, "retry_operation", operation_id=original.operation_id)
        self.assertFalse(Embedding.objects.filter(document=document).exists())
        run.refresh_from_db()
        self.assertEqual(
            (run.status, run.accounted_usd, run.reserved_usd), ("PAUSED", 0, 0)
        )
        self.assertNotIn(
            "private-service-key", json.dumps(run_report(run), default=str)
        )

    def test_invalid_vector_never_produces_readiness(self):
        run = self.new_run()
        document, reservation = self.reserve(run)
        with patch.object(
            MicroserviceEmbedder, "embed_text_accounted", return_value=([0.25] * 768, 0)
        ):
            execute_reservation(reservation.pk)
        self.assertFalse(Embedding.objects.filter(document=document).exists())
        run.refresh_from_db()
        self.assertEqual(
            (run.status, run.last_error), ("PAUSED", "invalid_embedding_result")
        )


class AccountedMicroserviceAdapterTests(SimpleTestCase):
    def test_single_request_is_bounded_without_retry_or_redirect_and_uses_snapshot(
        self,
    ):
        provider = MicroserviceEmbedder(component_settings=SERVICE_SETTINGS)
        session = MagicMock()
        session.post.return_value.status_code = 200
        session.post.return_value.json.return_value = {"embeddings": [[0.25] * 384]}
        with patch("requests.Session") as constructor:
            constructor.return_value.__enter__.return_value = session
            vector, tokens = provider.embed_text_accounted("x" * 40_000)
        session.post.assert_called_once_with(
            "https://embedder.invalid/embeddings",
            json={"text": "x" * OPENAI_EMBEDDER_MAX_INPUT_CHARS},
            headers={
                "Content-Type": "application/json",
                "X-API-Key": "private-service-key",
            },
            timeout=EMBEDDER_SINGLE_REQUEST_TIMEOUT_SECONDS,
            allow_redirects=False,
        )
        self.assertEqual(
            {call.args[0] for call in session.mount.call_args_list},
            {"http://", "https://"},
        )
        for call in session.mount.call_args_list:
            self.assertEqual(call.args[1].max_retries.total, 0)
        self.assertEqual((vector, tokens), ([0.25] * 384, 0))

    def test_http_errors_and_redirects_do_not_fallback_or_return_vectors(self):
        provider = MicroserviceEmbedder(component_settings=SERVICE_SETTINGS)
        for status in (302, 401, 429, 500):
            with self.subTest(status=status), patch("requests.Session") as constructor:
                session = constructor.return_value.__enter__.return_value
                session.post.return_value.status_code = status
                with self.assertRaisesRegex(ValueError, "embedding_request_failed"):
                    provider.embed_text_accounted("hello")
                session.post.assert_called_once()

    def test_malformed_and_nonfinite_responses_are_rejected(self):
        provider = MicroserviceEmbedder(component_settings=SERVICE_SETTINGS)
        bodies: tuple[dict[str, object], ...] = (
            {},
            {"embeddings": []},
            {"embeddings": [True]},
            {"embeddings": [float("nan")]},
            {"embeddings": [float("inf")]},
        )
        for body in bodies:
            with self.subTest(body=body), patch("requests.Session") as constructor:
                session = constructor.return_value.__enter__.return_value
                session.post.return_value.status_code = 200
                session.post.return_value.json.return_value = body
                with self.assertRaises(ValueError):
                    provider.embed_text_accounted("hello")
                session.post.assert_called_once()

    @override_settings(EMBEDDING_MODEL_REVISIONS={})
    def test_billing_setting_does_not_change_vector_identity_or_legacy_fingerprint(
        self,
    ):
        config: dict[str, str | bool] = {
            "embeddings_microservice_url": "https://embedder.invalid",
            "vector_embedder_api_key": "private-service-key",
        }
        legacy = {
            "embeddings_microservice_url": config["embeddings_microservice_url"],
            "use_cloud_run_iam_auth": False,
        }
        expected = hashlib.sha256(
            json.dumps([MICRO, 384, legacy, ""], sort_keys=True).encode()
        ).hexdigest()
        provider = MicroserviceEmbedder(component_settings=config)
        self.assertEqual(embedding_configuration(provider), expected)
        config["no_external_provider_fees"] = True
        self.assertEqual(
            embedding_configuration(MicroserviceEmbedder(component_settings=config)),
            expected,
        )
        config["embedding_model_revision"] = "model@new-revision"
        self.assertNotEqual(
            embedding_configuration(MicroserviceEmbedder(component_settings=config)),
            expected,
        )
