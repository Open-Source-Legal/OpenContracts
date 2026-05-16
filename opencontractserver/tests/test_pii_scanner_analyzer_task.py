"""Tests for the ``pii_scanner_privacy_filter`` task-based analyzer.

The analyzer wraps the privacy-filter HTTP microservice. These tests
mock ``adetect_pii`` so no network calls are made; they exercise:

  * SPAN_LABEL creation for text/markdown documents
  * TOKEN_LABEL creation for PDF documents
  * ``min_score`` knob filtering
  * Unknown ``entity_group`` skip
  * Empty / missing text input
  * Service failure (``RuntimeError`` from ``adetect_pii``)
  * Invalid file types
  * Label colour/icon parity with ``ENTITY_GROUP_LABELS``
  * Auto-registration via ``auto_create_doc_analyzers``
"""

from __future__ import annotations

import json
import logging
from typing import Any
from unittest.mock import AsyncMock, patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from opencontractserver.analyzer.models import Analysis, Analyzer
from opencontractserver.analyzer.utils import auto_create_doc_analyzers
from opencontractserver.annotations.models import (
    SPAN_LABEL,
    TOKEN_LABEL,
    Annotation,
    AnnotationLabel,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.llms.tools.core_tools._privacy_filter_client import Detection
from opencontractserver.llms.tools.core_tools.pii import ENTITY_GROUP_LABELS
from opencontractserver.tests.fixtures import (
    SAMPLE_PAWLS_FILE_ONE_PATH,
    SAMPLE_TXT_FILE_ONE_PATH,
)

User = get_user_model()
logger = logging.getLogger(__name__)

PII_TASK_NAME = "opencontractserver.tasks.doc_analysis_tasks.pii_scanner_privacy_filter"


def _det(
    group: str, start: int, end: int, score: float = 0.95, text: str = ""
) -> Detection:
    return Detection(entity_group=group, score=score, start=start, end=end, text=text)


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
    PRIVACY_FILTER_URL="http://privacy_filter:8000",
    PRIVACY_FILTER_API_KEY="dev-only-not-secret",
)
class _BasePiiScannerAnalyzerTestCase(TransactionTestCase):
    """Shared setup: user + corpus + (text and pdf) docs + Analyzer/Analysis."""

    def setUp(self) -> None:
        super().setUp()
        self.user = User.objects.create_user("pii_scanner_user", password="pw")
        self.corpus = Corpus.objects.create(
            title="PII Scanner Corpus", creator=self.user
        )

        # The analyzer is auto-created by the 0009 migration in normal runs.
        # In the test DB we may or may not have run that migration; either
        # way, use get_or_create so the suite is self-contained.
        self.analyzer, _ = Analyzer.objects.get_or_create(
            id=PII_TASK_NAME,
            defaults={
                "creator": self.user,
                "task_name": PII_TASK_NAME,
                "is_public": True,
                "disabled": False,
                "manifest": {},
                "description": "PII Scanner via privacy-filter service.",
            },
        )

    def _make_text_doc(self, content: bytes | None = None) -> Document:
        body = content or SAMPLE_TXT_FILE_ONE_PATH.read_bytes()
        doc = Document.objects.create(
            creator=self.user,
            title="PII Text Doc",
            file_type="text/plain",
            processing_started=timezone.now(),
        )
        doc.txt_extract_file.save("pii.txt", ContentFile(body))
        doc, _, _ = self.corpus.add_document(document=doc, user=self.user)
        return doc

    def _make_pdf_doc(self) -> tuple[Document, str]:
        pawls_json = SAMPLE_PAWLS_FILE_ONE_PATH.read_text()
        doc = Document.objects.create(
            creator=self.user,
            title="PII PDF Doc",
            file_type="application/pdf",
            page_count=len(json.loads(pawls_json)),
            processing_started=timezone.now(),
        )
        doc.pawls_parse_file.save(
            SAMPLE_PAWLS_FILE_ONE_PATH.name, ContentFile(pawls_json.encode())
        )
        # The decorator also reads txt_extract_file for the PDF branch when
        # available, but the persistence path uses pawls. Save a sidecar
        # txt extract so the decorator's preflight doesn't get None back.
        doc.txt_extract_file.save("pdf.txt", ContentFile(b"placeholder"))
        doc, _, _ = self.corpus.add_document(document=doc, user=self.user)

        # Build the doc_text the decorator's PlasmaPDF layer will derive so
        # we can compute a valid detection range that maps to real tokens.
        from plasmapdf.models.PdfDataLayer import build_translation_layer

        from opencontractserver.utils.compact_pawls import expand_pawls_pages

        with doc.pawls_parse_file.open("r") as f:
            pawls_tokens = expand_pawls_pages(json.load(f))
        layer = build_translation_layer(pawls_tokens)
        return doc, layer.doc_text

    def _make_analysis(self) -> Analysis:
        return Analysis.objects.create(
            analyzer=self.analyzer,
            analyzed_corpus=self.corpus,
            creator=self.user,
        )

    def _run_task(self, *, doc_id: int, analysis_id: int, **kwargs: Any) -> Any:
        from opencontractserver.tasks.doc_analysis_tasks import (
            pii_scanner_privacy_filter,
        )

        # ``pii_scanner_privacy_filter`` is wrapped by ``@async_doc_analyzer_task``
        # which returns a Celery task whose ``.si`` is dynamically attached;
        # mypy can't see it through the decorator's ``Callable[..., Any]`` typing.
        return (
            pii_scanner_privacy_filter.si(  # type: ignore[attr-defined]
                doc_id=doc_id,
                analysis_id=analysis_id,
                corpus_id=self.corpus.id,
                **kwargs,
            )
            .apply()
            .get()
        )


class PiiScannerTextDocTests(_BasePiiScannerAnalyzerTestCase):
    """Text/plain documents produce SPAN_LABEL annotations."""

    def test_text_doc_creates_span_label_annotations(self) -> None:
        body = b"Hello Alice, please email alice@example.com or call 555-0100."
        doc = self._make_text_doc(body)
        analysis = self._make_analysis()

        # Build offsets that point at real substrings.
        text = body.decode()
        email_start = text.index("alice@example.com")
        email_end = email_start + len("alice@example.com")
        name_start = text.index("Alice")
        name_end = name_start + len("Alice")

        fake = [
            _det("private_email", email_start, email_end, score=0.99),
            _det("person_name", name_start, name_end, score=0.92),
        ]

        with patch(
            "opencontractserver.llms.tools.core_tools._privacy_filter_client.adetect_pii",
            new=AsyncMock(return_value=fake),
        ):
            result = self._run_task(doc_id=doc.id, analysis_id=analysis.id)

        self.assertTrue(result[3], f"task should succeed, got result={result}")
        metadata = result[2][0]["data"]
        self.assertEqual(metadata["detection_count"], 2)
        self.assertEqual(
            metadata["by_entity_group"],
            {"private_email": 1, "person_name": 1},
        )

        anns = Annotation.objects.filter(analysis=analysis).order_by(
            "annotation_label__text"
        )
        self.assertEqual(anns.count(), 2)
        for ann in anns:
            self.assertEqual(ann.annotation_type, SPAN_LABEL)
            self.assertEqual(ann.document_id, doc.id)
            self.assertIn("start", ann.json)
            self.assertIn("end", ann.json)
            # Decorator stores the raw text taken from txt_extract_file.
            self.assertTrue(ann.raw_text)

    def test_label_color_and_icon_match_entity_group_labels(self) -> None:
        body = b"Send mail to bob@example.com please."
        doc = self._make_text_doc(body)
        analysis = self._make_analysis()
        text = body.decode()
        s = text.index("bob@example.com")
        e = s + len("bob@example.com")
        fake = [_det("private_email", s, e, score=0.99)]

        with patch(
            "opencontractserver.llms.tools.core_tools._privacy_filter_client.adetect_pii",
            new=AsyncMock(return_value=fake),
        ):
            self._run_task(doc_id=doc.id, analysis_id=analysis.id)

        expected_text, expected_color, expected_icon = ENTITY_GROUP_LABELS[
            "private_email"
        ]
        label = AnnotationLabel.objects.get(
            text=expected_text,
            label_type=SPAN_LABEL,
            creator=self.user,
            analyzer=self.analyzer,
        )
        self.assertEqual(label.color, expected_color)
        self.assertEqual(label.icon, expected_icon)


class PiiScannerPdfDocTests(_BasePiiScannerAnalyzerTestCase):
    """PDF documents produce TOKEN_LABEL annotations via PlasmaPDF."""

    def test_pdf_doc_creates_token_label_annotations(self) -> None:
        doc, doc_text = self._make_pdf_doc()
        analysis = self._make_analysis()

        # Pick a real word inside the PDF text so PlasmaPDF can map it to
        # tokens. The fixture is known to contain "Agreement".
        target = "Agreement"
        idx = doc_text.find(target)
        self.assertGreaterEqual(idx, 0, "fixture must contain 'Agreement'")
        fake = [
            _det("person_name", idx, idx + len(target), score=0.92, text=target),
        ]

        with patch(
            "opencontractserver.llms.tools.core_tools._privacy_filter_client.adetect_pii",
            new=AsyncMock(return_value=fake),
        ):
            result = self._run_task(doc_id=doc.id, analysis_id=analysis.id)

        self.assertTrue(result[3])
        ann = Annotation.objects.get(analysis=analysis)
        self.assertEqual(ann.annotation_type, TOKEN_LABEL)
        # PlasmaPDF stores token JSON as a non-empty dict.
        self.assertIsInstance(ann.json, dict)
        self.assertTrue(ann.json)
        self.assertIn("Agreement", ann.raw_text)

        label = ann.annotation_label
        expected_text, expected_color, expected_icon = ENTITY_GROUP_LABELS[
            "person_name"
        ]
        self.assertEqual(label.text, expected_text)
        self.assertEqual(label.color, expected_color)
        self.assertEqual(label.icon, expected_icon)
        self.assertEqual(label.label_type, TOKEN_LABEL)


class PiiScannerKnobTests(_BasePiiScannerAnalyzerTestCase):
    """``min_score`` filtering and unknown groups."""

    def test_min_score_filters_low_confidence(self) -> None:
        body = b"Reach me at carol@example.com or dave@example.com please."
        doc = self._make_text_doc(body)
        analysis = self._make_analysis()
        text = body.decode()
        s1 = text.index("carol@example.com")
        s2 = text.index("dave@example.com")
        fake = [
            _det("private_email", s1, s1 + len("carol@example.com"), score=0.3),
            _det("private_email", s2, s2 + len("dave@example.com"), score=0.99),
        ]

        with patch(
            "opencontractserver.llms.tools.core_tools._privacy_filter_client.adetect_pii",
            new=AsyncMock(return_value=fake),
        ):
            result = self._run_task(
                doc_id=doc.id, analysis_id=analysis.id, min_score=0.5
            )

        metadata = result[2][0]["data"]
        self.assertEqual(metadata["detection_count"], 1)
        self.assertEqual(metadata["skipped_low_score"], 1)
        self.assertEqual(metadata["min_score"], 0.5)
        self.assertEqual(Annotation.objects.filter(analysis=analysis).count(), 1)

    def test_unknown_entity_group_is_dropped_silently(self) -> None:
        body = b"Some text with mystery_term in it."
        doc = self._make_text_doc(body)
        analysis = self._make_analysis()
        text = body.decode()
        s = text.index("mystery_term")
        fake = [
            _det("private_email", 0, len("Some"), score=0.9),
            _det("unknown_made_up_group", s, s + len("mystery_term"), score=0.99),
        ]

        with patch(
            "opencontractserver.llms.tools.core_tools._privacy_filter_client.adetect_pii",
            new=AsyncMock(return_value=fake),
        ):
            result = self._run_task(doc_id=doc.id, analysis_id=analysis.id)

        metadata = result[2][0]["data"]
        self.assertEqual(metadata["detection_count"], 1)
        self.assertEqual(
            metadata["skipped_unknown_groups"], {"unknown_made_up_group": 1}
        )
        self.assertEqual(Annotation.objects.filter(analysis=analysis).count(), 1)

    def test_invalid_min_score_fails_cleanly(self) -> None:
        doc = self._make_text_doc()
        analysis = self._make_analysis()
        with patch(
            "opencontractserver.llms.tools.core_tools._privacy_filter_client.adetect_pii",
            new=AsyncMock(return_value=[]),
        ):
            result = self._run_task(
                doc_id=doc.id, analysis_id=analysis.id, min_score=2.0
            )
        self.assertFalse(result[3])
        self.assertIn("min_score", str(result[2]))

    def test_invalid_detection_offsets_are_skipped(self) -> None:
        body = b"Short text."
        doc = self._make_text_doc(body)
        analysis = self._make_analysis()
        # 999 is past the end of the txt extract; decorator-relative bound
        # checks should drop it.
        fake = [_det("private_email", 0, 999, score=0.99)]
        with patch(
            "opencontractserver.llms.tools.core_tools._privacy_filter_client.adetect_pii",
            new=AsyncMock(return_value=fake),
        ):
            result = self._run_task(doc_id=doc.id, analysis_id=analysis.id)
        self.assertTrue(result[3])
        self.assertEqual(result[2][0]["data"]["detection_count"], 0)
        self.assertEqual(Annotation.objects.filter(analysis=analysis).count(), 0)


class PiiScannerErrorPathTests(_BasePiiScannerAnalyzerTestCase):

    def test_empty_text_extract_returns_failure(self) -> None:
        # NOTE: ``async_doc_analyzer_task`` (unlike its sync sibling) does
        # NOT propagate ``task_pass=False`` into ``analysis.error_message``,
        # so we assert on the returned tuple only.
        doc = self._make_text_doc(b"")  # empty file → empty extract
        analysis = self._make_analysis()
        # No need to patch adetect_pii — empty text short-circuits.
        result = self._run_task(doc_id=doc.id, analysis_id=analysis.id)
        self.assertFalse(result[3])
        self.assertIn("No document text", str(result[2]))

    def test_adetect_pii_runtime_error_fails_cleanly(self) -> None:
        doc = self._make_text_doc()
        analysis = self._make_analysis()
        with patch(
            "opencontractserver.llms.tools.core_tools._privacy_filter_client.adetect_pii",
            new=AsyncMock(side_effect=RuntimeError("service unreachable")),
        ):
            result = self._run_task(doc_id=doc.id, analysis_id=analysis.id)
        self.assertFalse(result[3])
        self.assertIn("service unreachable", str(result[2]))

    def test_unsupported_file_type_fails_cleanly(self) -> None:
        # The decorator only annotates application/pdf and text/plain
        # (and a small set of related types). Use a type the wrapped
        # function will reject before calling the service.
        doc = Document.objects.create(
            creator=self.user,
            title="Other doc",
            file_type="application/octet-stream",
            processing_started=timezone.now(),
        )
        doc.txt_extract_file.save("ot.txt", ContentFile(b"some bytes"))
        doc, _, _ = self.corpus.add_document(document=doc, user=self.user)
        analysis = self._make_analysis()
        result = self._run_task(doc_id=doc.id, analysis_id=analysis.id)
        self.assertFalse(result[3])
        self.assertIn("Unsupported file_type", str(result[2]))


class PiiScannerRegistrationTests(TransactionTestCase):
    """``auto_create_doc_analyzers`` must register the new task."""

    def test_auto_create_picks_up_pii_scanner_task(self) -> None:
        # The task module is already imported by Django's autodiscover at
        # this point, so the decorator has registered the Celery task and
        # the historical-model utility should create an Analyzer row.
        User.objects.get_or_create(
            username="auto_registration_user",
            defaults={"password": "pw", "is_superuser": True},
        )
        # Idempotent: clear any pre-existing row so we observe creation.
        Analyzer.objects.filter(task_name=PII_TASK_NAME).delete()

        auto_create_doc_analyzers(
            AnalyzerModel=Analyzer, UserModel=User, fallback_superuser=True
        )

        self.assertTrue(
            Analyzer.objects.filter(task_name=PII_TASK_NAME).exists(),
            "pii_scanner_privacy_filter should be registered as an Analyzer",
        )
        a = Analyzer.objects.get(task_name=PII_TASK_NAME)
        self.assertIsNotNone(a.input_schema)
        self.assertIn("min_score", a.input_schema.get("properties", {}))
