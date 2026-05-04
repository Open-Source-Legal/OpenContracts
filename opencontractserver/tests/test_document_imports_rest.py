"""
Tests for the multipart REST document import endpoints.

Covers:
- DocumentImportView (POST /api/imports/documents/)
- DocumentsZipImportView (POST /api/imports/documents-zip/)
- Shared services in opencontractserver.document_imports.services

The previous transport (base64-over-GraphQL) hit Apollo's
"Payload allocation size overflow" invariant for large files because
the entire base64 string had to be allocated and JSON-stringified into
the GraphQL request body before any network I/O. Multipart streaming
avoids both copies. These tests exercise the new endpoints end-to-end
and validate the IDOR-safe error contracts.
"""

from __future__ import annotations

import io
import json
import zipfile

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from graphql_relay import to_global_id
from rest_framework.test import APIClient

from opencontractserver.constants.zip_import import (
    BULK_UPLOAD_OWNER_CACHE_PREFIX,
)
from opencontractserver.corpuses.models import Corpus, CorpusFolder
from opencontractserver.documents.models import Document
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


# Minimal but valid PDF; ``filetype`` recognises the magic bytes.
PDF_BYTES = (
    b"%PDF-1.7\n"
    b"1 0 obj\n<</Type/Catalog/Pages 2 0 R>>\nendobj\n"
    b"2 0 obj\n<</Type/Pages/Kids[3 0 R]/Count 1>>\nendobj\n"
    b"3 0 obj\n<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>\nendobj\n"
    b"xref\n0 4\n0000000000 65535 f\n0000000010 00000 n\n"
    b"0000000053 00000 n\n0000000102 00000 n\n"
    b"trailer\n<</Size 4/Root 1 0 R>>\nstartxref\n178\n%%EOF"
)
TXT_BYTES = b"hello world from a plain text doc"


def _make_zip(entries: dict[str, bytes]) -> bytes:
    """Build a zip in memory from {filename: content}."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return buf.getvalue()


SINGLE_URL = "/api/imports/documents/"
ZIP_URL = "/api/imports/documents-zip/"


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=False,  # zip path uses transaction.on_commit
)
class DocumentImportViewTests(TestCase):
    """Multipart single-document upload (POST /api/imports/documents/)."""

    # Override the parent ``Client`` annotation so mypy knows that ``setUp``
    # swaps in DRF's APIClient (which is the only client with ``force_authenticate``).
    client: APIClient

    def setUp(self):
        self.user = User.objects.create_user(
            username="alice",
            password="pw",
            is_usage_capped=False,
        )
        self.other_user = User.objects.create_user(
            username="bob",
            password="pw",
            is_usage_capped=False,
        )
        self.corpus = Corpus.objects.create(
            title="Alice Corpus",
            creator=self.user,
            backend_lock=False,
        )
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.CRUD])
        self.client = APIClient()

    def _login(self, user=None):
        self.client.force_authenticate(user=user or self.user)

    def _upload(self, **overrides):
        payload = {
            "file": SimpleUploadedFile(
                "doc.pdf", PDF_BYTES, content_type="application/pdf"
            ),
            "title": "My Doc",
            "description": "Hello",
            "make_public": "false",
        }
        payload.update(overrides)
        return self.client.post(SINGLE_URL, payload, format="multipart")

    # ---- auth ----

    def test_unauthenticated_request_is_rejected(self):
        response = self._upload()
        self.assertIn(response.status_code, (401, 403))

    # ---- happy paths ----

    def test_uploads_to_personal_corpus_when_no_corpus_specified(self):
        self._login()
        response = self._upload()
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertIn("document_id", body)
        document = Document.objects.get(pk=body["document_id"])
        self.assertEqual(document.creator, self.user)
        # The service should have created the user's personal corpus.
        self.assertTrue(
            Corpus.objects.filter(creator=self.user, is_personal=True).exists()
        )

    def test_uploads_to_specified_corpus_via_global_id(self):
        self._login()
        gid = to_global_id("CorpusType", str(self.corpus.id))
        response = self._upload(add_to_corpus_id=gid, title="Targeted")
        self.assertEqual(response.status_code, 201, response.content)
        document = Document.objects.get(pk=response.json()["document_id"])
        self.assertEqual(document.title, "Targeted")

    def test_uploads_to_specified_corpus_via_raw_pk(self):
        """REST callers should be able to send a raw pk too."""
        self._login()
        response = self._upload(add_to_corpus_id=str(self.corpus.id))
        self.assertEqual(response.status_code, 201, response.content)

    def test_uploads_to_specified_folder(self):
        self._login()
        folder = CorpusFolder.objects.create(
            corpus=self.corpus, name="Inbox", creator=self.user
        )
        response = self._upload(
            add_to_corpus_id=str(self.corpus.id),
            add_to_folder_id=str(folder.id),
        )
        self.assertEqual(response.status_code, 201, response.content)

    def test_text_file_upload_is_accepted(self):
        self._login()
        response = self._upload(
            file=SimpleUploadedFile("notes.txt", TXT_BYTES, content_type="text/plain")
        )
        self.assertEqual(response.status_code, 201, response.content)

    def test_custom_meta_json_is_stored(self):
        self._login()
        response = self._upload(custom_meta=json.dumps({"source": "test"}))
        self.assertEqual(response.status_code, 201, response.content)
        document = Document.objects.get(pk=response.json()["document_id"])
        self.assertEqual(document.custom_meta.get("source"), "test")

    # ---- validation / errors ----

    def test_missing_file_is_validation_error(self):
        self._login()
        response = self.client.post(
            SINGLE_URL,
            {"title": "no file"},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)

    def test_missing_title_is_validation_error(self):
        self._login()
        response = self.client.post(
            SINGLE_URL,
            {
                "file": SimpleUploadedFile(
                    "doc.pdf", PDF_BYTES, content_type="application/pdf"
                ),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)

    def test_unsupported_filetype_returns_400(self):
        self._login()
        # Random binary content with no recognised magic bytes & non-text
        response = self._upload(
            file=SimpleUploadedFile(
                "junk.bin",
                b"\x00\x01\x02\x03binary garbage\x88\x99",
                content_type="application/octet-stream",
            )
        )
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertFalse(body["ok"])
        # Either "Unable to determine file type" or "Unallowed filetype"
        self.assertIn("type", body["error"].lower())

    def test_inaccessible_corpus_returns_unified_idor_message(self):
        """
        A corpus that exists but the user cannot edit must return the same
        message as a non-existent corpus, preventing enumeration.
        """
        other = Corpus.objects.create(
            title="Bob's Corpus", creator=self.other_user, backend_lock=False
        )
        # Alice has no perms on Bob's corpus
        self._login()
        response = self._upload(add_to_corpus_id=str(other.id))
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertFalse(body["ok"])
        self.assertIn("Corpus not found", body["error"])

        # Also verify the non-existent path returns the SAME message
        response2 = self._upload(add_to_corpus_id="999999999")
        self.assertEqual(response2.status_code, 400)
        self.assertEqual(response2.json()["error"], body["error"])

    def test_visible_but_read_only_corpus_returns_idor_message(self):
        """
        Corpus visible-to-user (READ) but without EDIT permission must
        also collapse into the unified not-found message.
        """
        public_corpus = Corpus.objects.create(
            title="Public",
            creator=self.other_user,
            is_public=True,
            backend_lock=False,
        )
        self._login()
        response = self._upload(add_to_corpus_id=str(public_corpus.id))
        self.assertEqual(response.status_code, 400)
        self.assertIn("Corpus not found", response.json()["error"])

    def test_folder_not_in_corpus_returns_400(self):
        self._login()
        other = Corpus.objects.create(
            title="other", creator=self.user, backend_lock=False
        )
        set_permissions_for_obj_to_user(self.user, other, [PermissionTypes.CRUD])
        folder = CorpusFolder.objects.create(corpus=other, name="x", creator=self.user)
        response = self._upload(
            add_to_corpus_id=str(self.corpus.id),
            add_to_folder_id=str(folder.id),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Folder", response.json()["error"])

    def test_oversize_file_returns_413(self):
        self._login()
        with override_settings(MAX_DOCUMENT_IMPORT_SIZE_BYTES=10):
            response = self._upload()
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["max_bytes"], 10)

    def test_usage_capped_user_over_doc_cap_is_rejected(self):
        capped = User.objects.create_user(
            username="capped", password="pw", is_usage_capped=True
        )
        self.client.force_authenticate(user=capped)
        # Pre-create cap-many docs to push capped user over the limit
        with override_settings(USAGE_CAPPED_USER_DOC_CAP_COUNT=1):
            Document.objects.create(
                title="placeholder",
                description="",
                creator=capped,
                backend_lock=False,
            )
            response = self._upload()
        # PermissionError is mapped to 403
        self.assertEqual(response.status_code, 403)


@override_settings(CELERY_TASK_ALWAYS_EAGER=False)
class DocumentsZipImportViewTests(TestCase):
    """
    Multipart bulk-zip upload (POST /api/imports/documents-zip/).

    With ``CELERY_TASK_ALWAYS_EAGER=False`` the queued ``process_documents_zip``
    task is registered via ``transaction.on_commit``; under
    :class:`TestCase` the outer transaction is rolled back so the callback
    never fires. That keeps these tests focused on the view contract
    (staging, job_id, IDOR semantics) rather than the import pipeline
    (covered by test_bulk_document_upload).
    """

    client: APIClient

    def setUp(self):
        self.user = User.objects.create_user(
            username="alice", password="pw", is_usage_capped=False
        )
        self.other_user = User.objects.create_user(
            username="bob", password="pw", is_usage_capped=False
        )
        self.corpus = Corpus.objects.create(
            title="Alice Corpus", creator=self.user, backend_lock=False
        )
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.CRUD])
        self.client = APIClient()
        self.zip_bytes = _make_zip({"a.pdf": PDF_BYTES, "b.txt": TXT_BYTES})

    def _login(self, user=None):
        self.client.force_authenticate(user=user or self.user)

    def _upload(self, **overrides):
        payload = {
            "file": SimpleUploadedFile(
                "bundle.zip", self.zip_bytes, content_type="application/zip"
            ),
            "make_public": "false",
        }
        payload.update(overrides)
        return self.client.post(ZIP_URL, payload, format="multipart")

    def test_unauthenticated_request_is_rejected(self):
        response = self.client.post(
            ZIP_URL,
            {
                "file": SimpleUploadedFile(
                    "bundle.zip", self.zip_bytes, content_type="application/zip"
                ),
                "make_public": "false",
            },
            format="multipart",
        )
        self.assertIn(response.status_code, (401, 403))

    def test_zip_upload_returns_job_id_and_caches_owner(self):
        self._login()
        response = self._upload()
        self.assertEqual(response.status_code, 202, response.content)
        body = response.json()
        self.assertTrue(body["ok"])
        job_id = body["job_id"]
        self.assertTrue(job_id)
        # IDOR cache must bind the job to its owner so the status resolver
        # can refuse cross-user reads.
        cached_owner = cache.get(f"{BULK_UPLOAD_OWNER_CACHE_PREFIX}{job_id}")
        self.assertEqual(cached_owner, self.user.id)

    def test_zip_upload_to_owned_corpus_succeeds(self):
        self._login()
        response = self._upload(add_to_corpus_id=str(self.corpus.id))
        self.assertEqual(response.status_code, 202, response.content)

    def test_zip_upload_to_inaccessible_corpus_is_rejected_uniformly(self):
        other = Corpus.objects.create(
            title="Bob", creator=self.other_user, backend_lock=False
        )
        self._login()
        response = self._upload(add_to_corpus_id=str(other.id))
        self.assertEqual(response.status_code, 400)
        self.assertIn("Corpus not found", response.json()["error"])

        # Non-existent corpus returns the same message — collapses both
        # failure modes to prevent enumeration of inaccessible corpora.
        response2 = self._upload(add_to_corpus_id="999999999")
        self.assertEqual(response2.status_code, 400)
        self.assertEqual(response2.json()["error"], response.json()["error"])

    def test_zip_upload_to_read_only_corpus_is_rejected_uniformly(self):
        public = Corpus.objects.create(
            title="Public",
            creator=self.other_user,
            is_public=True,
            backend_lock=False,
        )
        self._login()
        response = self._upload(add_to_corpus_id=str(public.id))
        self.assertEqual(response.status_code, 400)
        self.assertIn("Corpus not found", response.json()["error"])

    def test_missing_file_is_validation_error(self):
        self._login()
        response = self.client.post(
            ZIP_URL, {"make_public": "false"}, format="multipart"
        )
        self.assertEqual(response.status_code, 400)

    def test_oversize_zip_returns_413(self):
        self._login()
        with override_settings(MAX_DOCUMENT_IMPORT_SIZE_BYTES=10):
            response = self.client.post(
                ZIP_URL,
                {
                    "file": SimpleUploadedFile(
                        "big.zip", self.zip_bytes, content_type="application/zip"
                    ),
                    "make_public": "false",
                },
                format="multipart",
            )
        self.assertEqual(response.status_code, 413)

    @override_settings(USAGE_CAPPED_USER_CAN_IMPORT_CORPUS=False)
    def test_usage_capped_user_cannot_zip_upload(self):
        capped = User.objects.create_user(
            username="capped", password="pw", is_usage_capped=True
        )
        self.client.force_authenticate(user=capped)
        response = self._upload()
        self.assertEqual(response.status_code, 403)


@override_settings(CELERY_TASK_ALWAYS_EAGER=False)
class ImportServicesTests(TestCase):
    """
    Direct tests for the shared service functions, ensuring the GraphQL
    and REST transports route through identical logic.

    ``CELERY_TASK_ALWAYS_EAGER=False`` keeps the queued
    ``process_documents_zip`` task from executing under TestCase
    (the wrapping transaction is rolled back, so on_commit never fires).
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="svc", password="pw", is_usage_capped=False
        )
        self.other = User.objects.create_user(
            username="svc_other", password="pw", is_usage_capped=False
        )

    def test_import_document_for_user_creates_document(self):
        from opencontractserver.document_imports.services import (
            import_document_for_user,
        )

        result = import_document_for_user(
            user=self.user,
            file_bytes=PDF_BYTES,
            filename="x.pdf",
            title="X",
            description="d",
            make_public=False,
        )
        self.assertIsNone(result.error)
        self.assertIsNotNone(result.document)

    def test_import_document_for_user_rejects_inaccessible_corpus_with_idor_msg(
        self,
    ):
        from opencontractserver.document_imports.services import (
            CORPUS_NOT_FOUND_MSG,
            import_document_for_user,
        )

        other_corpus = Corpus.objects.create(
            title="Other", creator=self.other, backend_lock=False
        )
        result_no_perm = import_document_for_user(
            user=self.user,
            file_bytes=PDF_BYTES,
            filename="x.pdf",
            title="X",
            description="d",
            make_public=False,
            add_to_corpus_id=str(other_corpus.id),
        )
        result_no_exist = import_document_for_user(
            user=self.user,
            file_bytes=PDF_BYTES,
            filename="x.pdf",
            title="X",
            description="d",
            make_public=False,
            add_to_corpus_id="9999999",
        )
        self.assertEqual(result_no_perm.error, CORPUS_NOT_FOUND_MSG)
        self.assertEqual(result_no_exist.error, CORPUS_NOT_FOUND_MSG)

    def test_import_documents_zip_for_user_accepts_uploaded_file(self):
        from opencontractserver.document_imports.services import (
            import_documents_zip_for_user,
        )

        zip_bytes = _make_zip({"a.pdf": PDF_BYTES})
        uploaded = SimpleUploadedFile(
            "z.zip", zip_bytes, content_type="application/zip"
        )
        result = import_documents_zip_for_user(
            user=self.user,
            zip_source=uploaded,
            make_public=False,
        )
        self.assertIsNone(result.error)
        self.assertTrue(result.job_id)

    def test_import_documents_zip_for_user_accepts_bytes(self):
        """Legacy/GraphQL path passes raw bytes; same code path must work."""
        from opencontractserver.document_imports.services import (
            import_documents_zip_for_user,
        )

        zip_bytes = _make_zip({"a.pdf": PDF_BYTES})
        result = import_documents_zip_for_user(
            user=self.user,
            zip_source=zip_bytes,
            make_public=False,
        )
        self.assertIsNone(result.error)
        self.assertTrue(result.job_id)
