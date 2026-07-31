"""V3 export emission + validator gating.

Verifies (a) the corpus export emitter produces ``version="3.0"`` without
the legacy ``md_description`` / ``md_description_revisions`` top-level
fields and (b) :mod:`opencontractserver.utils.validate_export` gates the
required-fields check by version — V2 still requires the legacy keys (for
back-compat artifacts), V3 forbids them entirely. Under V3 the Readme.CAML
Document rides in ``annotated_docs`` exactly like every other Document.

Spec: Canonical-CAML Corpus Description Refactor §4.8.
"""

from __future__ import annotations

import hashlib
import json
import zipfile

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase
from django.utils import timezone

from opencontractserver.annotations.models import LabelSet
from opencontractserver.corpuses.models import Corpus
from opencontractserver.corpuses.services.corpus_service import CorpusService
from opencontractserver.documents.models import Document, DocumentPath

User = get_user_model()

pytestmark = pytest.mark.django_db


class ExportV3SchemaTest(TestCase):
    """V3 export emits version=3.0 without md_description fields."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="exp-v3", password="x")
        # LabelSet is required for V2/V3 corpus export packaging.
        cls.labelset = LabelSet.objects.create(title="V3 LabelSet", creator=cls.user)
        cls.corpus = Corpus.objects.create(
            title="V3 Corpus",
            creator=cls.user,
            label_set=cls.labelset,
        )

    def _build_export_json(self) -> dict:
        """Run ``build_corpus_v2_zip`` and return the parsed data.json."""
        from opencontractserver.tasks.export_tasks_v2 import build_corpus_v2_zip

        with build_corpus_v2_zip(
            corpus_pk=self.corpus.id,
            user_for_visibility=self.user,
            include_conversations=False,
        ) as buf:
            with zipfile.ZipFile(buf, "r") as zf:
                with zf.open("data.json") as f:
                    return json.load(f)

    def _publisher_source_document(self, *, source_hash: str | None = None) -> Document:
        portable = b"portable extracted text"
        publisher_source = b"<html><body>publisher source</body></html>"
        content_hash = source_hash or hashlib.sha256(publisher_source).hexdigest()
        source_member = "publisher-source-rule.html"
        document = Document.objects.create(
            title="Publisher Rule",
            creator=self.user,
            file_type="text/plain",
            pdf_file=ContentFile(portable, name="publisher-rule.txt"),
            pdf_file_hash=hashlib.sha256(portable).hexdigest(),
            txt_extract_file=ContentFile(portable, name="extracted.txt"),
            pawls_parse_file=ContentFile(b"[]", name="pawls.json"),
            original_file=ContentFile(publisher_source, name=source_member),
            original_file_type="text/html",
            custom_meta={
                "publisher_source_member": source_member,
                "publisher_source_content_hash": content_hash,
                "publisher_source_mime_type": "text/html",
                "publisher_source_packaging": "sidecar",
            },
            processing_started=timezone.now(),
        )
        DocumentPath.objects.create(
            document=document,
            corpus=self.corpus,
            path="/documents/publisher-rule.txt",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )
        return document

    def test_export_emits_version_3_0(self):
        data = self._build_export_json()
        self.assertEqual(data["version"], "3.0")

    def test_export_omits_md_description_fields(self):
        # Drive a description write through the canonical service so a
        # Readme.CAML Document exists in the corpus.
        with self.captureOnCommitCallbacks(execute=True):
            CorpusService.update_description(
                self.user, self.corpus, "# V3 Body\n\nHello."
            )

        data = self._build_export_json()
        self.assertNotIn(
            "md_description",
            data,
            "V3 export must drop the legacy md_description top-level key.",
        )
        self.assertNotIn(
            "md_description_revisions",
            data,
            "V3 export must drop the legacy md_description_revisions top-level key.",
        )

    def test_export_still_emits_other_v2_fields(self):
        """V3 keeps every other V2 top-level field — only the two are dropped."""
        data = self._build_export_json()
        for f in (
            "annotated_docs",
            "doc_labels",
            "text_labels",
            "corpus",
            "label_set",
            "structural_annotation_sets",
            "folders",
            "document_paths",
            "relationships",
            "agent_config",
            "post_processors",
        ):
            self.assertIn(f, data, f"V3 export missing expected field {f!r}")

    def test_export_reemits_verified_publisher_original_file(self):
        self._publisher_source_document()
        from opencontractserver.tasks.export_tasks_v2 import build_corpus_v2_zip

        with build_corpus_v2_zip(
            corpus_pk=self.corpus.id,
            user_for_visibility=self.user,
        ) as buf:
            with zipfile.ZipFile(buf) as archive:
                data = json.loads(archive.read("data.json"))
                _filename, exported = next(iter(data["annotated_docs"].items()))
                source_member = exported["custom_meta"]["publisher_source_member"]
                self.assertEqual(
                    archive.read(source_member),
                    b"<html><body>publisher source</body></html>",
                )
                self.assertEqual(
                    exported["custom_meta"]["publisher_source_packaging"],
                    "sidecar",
                )

    def test_export_rejects_publisher_original_file_hash_mismatch(self):
        self._publisher_source_document(source_hash="0" * 64)
        from opencontractserver.tasks.export_tasks_v2 import build_corpus_v2_zip

        with self.assertRaisesRegex(
            ValueError,
            "does not match Document.original_file",
        ):
            build_corpus_v2_zip(
                corpus_pk=self.corpus.id,
                user_for_visibility=self.user,
            )


class ValidatorVersionGatingTest(TestCase):
    """validate_export.py gates required/forbidden fields by version."""

    def _base_v3(self) -> dict:
        """Minimum shape that exercises the V3 required-fields path."""
        return {
            "version": "3.0",
            "annotated_docs": {},
            "doc_labels": {},
            "text_labels": {},
            "corpus": {
                "title": "C",
                "description": "",
                "creator": "u@example.com",
            },
            "label_set": {
                "title": "LS",
                "description": "",
                "icon_name": "",
                "creator": "u@example.com",
            },
            "structural_annotation_sets": {},
            "folders": [],
            "document_paths": [],
            "relationships": [],
            "agent_config": {
                "corpus_agent_instructions": None,
                "document_agent_instructions": None,
            },
            "post_processors": [],
        }

    def test_v3_payload_without_md_description_validates(self):
        from opencontractserver.utils.validate_export import validate_data_json

        result = validate_data_json(self._base_v3())
        md_errors = [e for e in result.errors if "md_description" in e]
        self.assertEqual(
            md_errors,
            [],
            f"V3 must not flag missing md_description: {md_errors}",
        )

    def test_v3_payload_with_md_description_is_rejected(self):
        from opencontractserver.utils.validate_export import validate_data_json

        payload = self._base_v3()
        payload["md_description"] = "should not be here"
        result = validate_data_json(payload)
        self.assertTrue(
            any("md_description" in e for e in result.errors),
            f"expected md_description rejection in V3, got: {result.errors}",
        )

    def test_v3_payload_with_md_description_revisions_is_rejected(self):
        from opencontractserver.utils.validate_export import validate_data_json

        payload = self._base_v3()
        payload["md_description_revisions"] = []
        result = validate_data_json(payload)
        self.assertTrue(
            any("md_description_revisions" in e for e in result.errors),
            f"expected md_description_revisions rejection in V3, got: {result.errors}",
        )

    def test_v2_payload_still_requires_md_description(self):
        from opencontractserver.utils.validate_export import validate_data_json

        payload = self._base_v3()
        payload["version"] = "2.0"
        # md_description and md_description_revisions intentionally missing.
        result = validate_data_json(payload)
        self.assertTrue(
            any("md_description" in e for e in result.errors),
            f"V2 must still flag missing md_description: {result.errors}",
        )

    def test_v3_is_a_known_version(self):
        """Version 3.0 must not produce the unrecognised-version warning."""
        from opencontractserver.utils.validate_export import validate_data_json

        result = validate_data_json(self._base_v3())
        self.assertFalse(
            any("3.0" in w and "Unrecognised" in w for w in result.warnings),
            f"3.0 should be recognised; got warnings: {result.warnings}",
        )
