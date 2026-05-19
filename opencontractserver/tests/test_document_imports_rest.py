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

from django.conf import settings
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

    def test_import_document_for_user_honors_group_permission(self):
        """Phase E widening: ``import_document_for_user`` now routes the
        EDIT gate through ``corpus.user_can(...)``, which defaults to
        ``include_group_permissions=True``. The legacy
        ``user_has_permission_for_obj`` shim defaulted to ``False``, so a
        user who only held ``update_corpus`` via a Django ``Group`` would
        have been blocked before Phase E. This pins the new behavior at
        the import-service boundary so future refactors can't quietly
        revert to user-only checks.
        """
        from django.contrib.auth.models import Group
        from guardian.shortcuts import assign_perm

        from opencontractserver.document_imports.services import (
            import_document_for_user,
        )

        # Corpus owned by ``self.other``. Make it public so
        # ``Corpus.objects.visible_to_user(self.user)`` resolves the row —
        # the EDIT widening is the focus of this test, not visibility.
        # ``BaseVisibilityManager.visible_to_user`` only checks
        # user-direct guardian perms (not group perms) for non-public rows,
        # so without ``is_public=True`` the lookup would 404 before reaching
        # the user_can gate that this test exercises.
        shared_corpus = Corpus.objects.create(
            title="Group-shared",
            creator=self.other,
            backend_lock=False,
            is_public=True,
        )

        # Group holds ``update_corpus``; ``self.user`` is a member.
        # No direct user grant on ``self.user`` for ``update_corpus`` —
        # under the legacy shim default this would fail the EDIT check.
        editors = Group.objects.create(name="phase-e-corpus-editors")
        self.user.groups.add(editors)
        assign_perm("corpuses.update_corpus", editors, shared_corpus)

        result = import_document_for_user(
            user=self.user,
            file_bytes=PDF_BYTES,
            filename="x.pdf",
            title="X",
            description="d",
            make_public=False,
            add_to_corpus_id=str(shared_corpus.id),
        )

        # Group-derived EDIT lets the import land in the foreign corpus.
        self.assertIsNone(result.error)
        self.assertIsNotNone(result.document)

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


class ServiceHelperUnitTests(TestCase):
    """Unit-level coverage of the small pure helpers in services.py."""

    def test_resolve_pk_none_returns_none(self):
        from opencontractserver.document_imports.services import _resolve_pk

        self.assertIsNone(_resolve_pk(None))

    def test_resolve_pk_raw_string_pk_passes_through(self):
        from opencontractserver.document_imports.services import _resolve_pk

        # Non-base64 input — ``from_global_id`` decodes to empty type/id
        # and the helper should fall back to the raw string.
        self.assertEqual(_resolve_pk("42"), "42")

    def test_resolve_pk_global_id_decodes_to_pk(self):
        from opencontractserver.document_imports.services import _resolve_pk

        # Round-trip a Relay global id; helper should return just the pk.
        self.assertEqual(_resolve_pk(to_global_id("CorpusType", "7")), "7")

    def test_resolve_pk_malformed_input_falls_back_to_raw(self):
        from opencontractserver.document_imports.services import _resolve_pk

        # Bytes payload that triggers ``from_global_id`` to raise; the
        # helper logs and returns the stringified raw input.
        result = _resolve_pk("\udcff-bad")
        self.assertEqual(result, "\udcff-bad")

    def test_detect_mime_type_markdown_extension_for_plaintext(self):
        from opencontractserver.document_imports.services import detect_mime_type

        # ``filetype.guess`` returns ``None`` for plain text, then we
        # promote ``.md`` / ``.markdown`` / ``.caml`` filenames to
        # ``text/markdown``.
        self.assertEqual(detect_mime_type(b"# heading", "notes.md"), "text/markdown")
        self.assertEqual(
            detect_mime_type(b"# heading", "doc.markdown"), "text/markdown"
        )
        self.assertEqual(detect_mime_type(b"# heading", "x.caml"), "text/markdown")
        self.assertEqual(detect_mime_type(b"hello", "x.txt"), "text/plain")

    def test_peek_zip_magic_logs_warning_when_seek_fails(self):
        """A non-seekable stream surfaces a warning instead of silently
        truncating the archive on the subsequent storage write."""
        import io
        import logging

        from opencontractserver.document_imports.services import _peek_zip_magic

        class _NoSeek(io.BytesIO):
            def seek(self, *a, **k):
                raise OSError("non-seekable stream")

        zip_bytes = _make_zip({"a.pdf": PDF_BYTES})
        # ``_peek_zip_magic`` only invokes the file-like branch for
        # non-bytes inputs, so wrap in a SimpleUploadedFile-like shim.
        from django.core.files.uploadedfile import SimpleUploadedFile

        uploaded = SimpleUploadedFile("z.zip", zip_bytes)
        # Patch the underlying file with our non-seekable wrapper.
        uploaded.file = _NoSeek(zip_bytes)

        with self.assertLogs(
            "opencontractserver.document_imports.services", level=logging.WARNING
        ) as cm:
            self.assertTrue(_peek_zip_magic(uploaded))
        self.assertTrue(
            any("Failed to rewind upload stream" in m for m in cm.output),
            cm.output,
        )

    def test_normalise_optional_blank_string_becomes_none(self):
        from opencontractserver.document_imports.views import _normalise_optional

        self.assertIsNone(_normalise_optional(""))
        self.assertIsNone(_normalise_optional("   "))
        self.assertIsNone(_normalise_optional(None))
        self.assertEqual(_normalise_optional("kept"), "kept")

    def test_resolve_pk_swallows_decode_errors(self):
        """``from_global_id`` may raise on invalid base64; the helper
        must log and fall back to the raw input rather than propagating."""
        from unittest.mock import patch

        from opencontractserver.document_imports.services import _resolve_pk

        with patch(
            "opencontractserver.document_imports.services.from_global_id",
            side_effect=ValueError("invalid b64"),
        ):
            self.assertEqual(_resolve_pk("anything"), "anything")

    def test_import_document_for_user_rejects_disallowed_filetype(self):
        """Branch where ``filetype.guess`` returns a recognised mime that
        is *not* on the upload allowlist."""
        user = User.objects.create_user(
            username="svc_filetype", password="pw", is_usage_capped=False
        )
        from opencontractserver.document_imports.services import (
            import_document_for_user,
        )

        # ``filetype`` recognises ELF binaries; not an allowed upload type.
        elf_bytes = b"\x7fELF" + b"\x00" * 100
        result = import_document_for_user(
            user=user,
            file_bytes=elf_bytes,
            filename="not-a-doc.bin",
            title="X",
            description="d",
            make_public=False,
        )
        self.assertIsNotNone(result.error)
        self.assertIn("Unallowed filetype", result.error or "")

    def test_import_document_for_user_wraps_storage_failure(self):
        """When ``corpus.import_content`` raises, the service surfaces a
        user-safe error message instead of propagating the exception."""
        from unittest.mock import patch

        user = User.objects.create_user(
            username="svc_storage_fail", password="pw", is_usage_capped=False
        )
        from opencontractserver.document_imports.services import (
            import_document_for_user,
        )

        with patch(
            "opencontractserver.corpuses.models.Corpus.import_content",
            side_effect=RuntimeError("disk on fire"),
        ):
            result = import_document_for_user(
                user=user,
                file_bytes=PDF_BYTES,
                filename="x.pdf",
                title="X",
                description="d",
                make_public=False,
            )
        self.assertIsNone(result.document)
        self.assertIn("Import failed due to error", result.error or "")
        self.assertIn("disk on fire", result.error or "")

    def test_import_documents_zip_for_user_wraps_staging_failure(self):
        """An exception raised while staging the ZIP into the
        TemporaryFileHandle returns an explicit error rather than
        bubbling up."""
        from unittest.mock import patch

        user = User.objects.create_user(
            username="svc_zip_stage_fail", password="pw", is_usage_capped=False
        )
        from opencontractserver.document_imports.services import (
            import_documents_zip_for_user,
        )

        zip_bytes = _make_zip({"a.pdf": PDF_BYTES})
        with patch(
            "opencontractserver.document_imports.services."
            "TemporaryFileHandle.objects.create",
            side_effect=RuntimeError("staging boom"),
        ):
            result = import_documents_zip_for_user(
                user=user,
                zip_source=zip_bytes,
                make_public=False,
            )
        self.assertIsNone(result.job_id)
        self.assertIn("Failed to stage zip", result.error or "")
        self.assertIn("staging boom", result.error or "")

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_import_documents_zip_for_user_eager_dispatch_path(self):
        """Eager mode should dispatch the chain synchronously rather
        than wiring through ``transaction.on_commit``."""
        from unittest.mock import patch

        user = User.objects.create_user(
            username="svc_zip_eager", password="pw", is_usage_capped=False
        )
        from opencontractserver.document_imports.services import (
            import_documents_zip_for_user,
        )

        zip_bytes = _make_zip({"a.pdf": PDF_BYTES})
        # Patch ``apply_async`` to short-circuit actual task execution while
        # confirming the eager dispatch branch runs.
        with patch(
            "celery.canvas._chain.apply_async", return_value=None
        ) as mocked_apply:
            result = import_documents_zip_for_user(
                user=user,
                zip_source=zip_bytes,
                make_public=False,
            )
        self.assertIsNone(result.error)
        self.assertTrue(result.job_id)
        self.assertTrue(mocked_apply.called)


# ---------------------------------------------------------------------------
# Security-focused tests
#
# The fixtures above lean on ``APIClient.force_authenticate``, which bypasses
# every authentication class on the view. That means the tests above never
# exercise the actual JWT validation path on these endpoints. The classes
# below close that gap: they mint a real JWT and post via
# ``Authorization: Bearer …`` so the pinned
# ``GraphQLJWTAuthentication`` is genuinely on the call path.
# ---------------------------------------------------------------------------


@override_settings(CELERY_TASK_ALWAYS_EAGER=False)
class DocumentImportRealJWTAuthTests(TestCase):
    """End-to-end tests of the real bearer-JWT auth path on import views."""

    client: APIClient

    def setUp(self):
        self.user = User.objects.create_user(
            username="jwt_alice", password="pw", is_usage_capped=False
        )
        self.client = APIClient()

    def _set_bearer(self, token: str) -> None:
        """
        Inject ``Authorization: Bearer <token>`` on every subsequent request
        without using ``client.force_authenticate`` (which bypasses the auth
        classes entirely and would defeat the purpose of these tests).
        """
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def _payload(self) -> dict:
        return {
            "file": SimpleUploadedFile(
                "doc.pdf", PDF_BYTES, content_type="application/pdf"
            ),
            "title": "Real-JWT Doc",
            "make_public": "false",
        }

    def test_real_jwt_authenticates_single_doc_upload(self):
        """A valid JWT minted via graphql_jwt must authorise the upload."""
        from graphql_jwt.shortcuts import get_token

        self._set_bearer(get_token(self.user))
        response = self.client.post(
            SINGLE_URL,
            self._payload(),
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertTrue(body["ok"])
        document = Document.objects.get(pk=body["document_id"])
        self.assertEqual(document.creator, self.user)

    def test_missing_authorization_header_is_rejected(self):
        """No bearer header → IsAuthenticated → 401/403."""
        response = self.client.post(
            SINGLE_URL,
            self._payload(),
            format="multipart",
        )
        self.assertIn(response.status_code, (401, 403))

    def test_tampered_jwt_is_rejected(self):
        """A token with a flipped signature byte must NOT authenticate."""
        from graphql_jwt.shortcuts import get_token

        token = get_token(self.user)
        # Flip a char in the middle of the signature segment. The trailing
        # base64url char of an HS256 signature encodes only 4 data bits + 2
        # padding bits, so flipping it can leave the decoded signature bytes
        # unchanged when only padding bits differ — flaky in ~6% of cases.
        head, _, sig = token.rpartition(".")
        mid = len(sig) // 2
        original = sig[mid]
        replacement = "A" if original != "A" else "B"
        tampered_sig = sig[:mid] + replacement + sig[mid + 1 :]
        self._set_bearer(f"{head}.{tampered_sig}")
        response = self.client.post(
            SINGLE_URL,
            self._payload(),
            format="multipart",
        )
        self.assertIn(response.status_code, (401, 403))
        # Document must NOT have been created.
        self.assertFalse(
            Document.objects.filter(creator=self.user, title="Real-JWT Doc").exists()
        )

    def test_expired_jwt_is_rejected(self):
        """An expired bearer JWT must be rejected with 401/403."""
        from datetime import timedelta

        from graphql_jwt.shortcuts import get_token

        # JWT_EXPIRATION_DELTA is read at import time; emit a token whose
        # exp is firmly in the past by overriding the setting for this test.
        with override_settings(
            GRAPHQL_JWT=(
                {
                    **settings.GRAPHQL_JWT,
                    "JWT_EXPIRATION_DELTA": timedelta(seconds=-1),
                }
                if hasattr(settings, "GRAPHQL_JWT")
                else {}
            )
        ):
            token = get_token(self.user)
        self._set_bearer(token)
        response = self.client.post(
            SINGLE_URL,
            self._payload(),
            format="multipart",
        )
        self.assertIn(response.status_code, (401, 403))


@override_settings(CELERY_TASK_ALWAYS_EAGER=False)
class DocumentsZipNonZipRejectionTests(TestCase):
    """The ZIP endpoint must reject anything that isn't a real ZIP archive."""

    client: APIClient

    def setUp(self):
        self.user = User.objects.create_user(
            username="zip_alice", password="pw", is_usage_capped=False
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_pdf_posted_to_zip_endpoint_is_rejected(self):
        """A PDF must NOT be accepted by /api/imports/documents-zip/."""
        response = self.client.post(
            ZIP_URL,
            {
                "file": SimpleUploadedFile(
                    "not-a-zip.pdf",
                    PDF_BYTES,
                    content_type="application/pdf",
                ),
                "make_public": "false",
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 400, response.content)
        body = response.json()
        self.assertFalse(body["ok"])
        self.assertIn("ZIP", body["error"])

    def test_random_garbage_posted_to_zip_endpoint_is_rejected(self):
        """Bytes lacking the ZIP magic prefix must be rejected."""
        response = self.client.post(
            ZIP_URL,
            {
                "file": SimpleUploadedFile(
                    "garbage.zip",
                    b"\x00\x01\x02\x03not actually a zip archive",
                    content_type="application/zip",
                ),
                "make_public": "false",
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("ZIP", response.json()["error"])


@override_settings(CELERY_TASK_ALWAYS_EAGER=False)
class DocumentImportFolderIDORTests(TestCase):
    """
    Folder-membership IDOR contract: ``add_to_folder_id`` referencing a folder
    in a corpus the caller does NOT own must collapse to the same generic
    "Folder not found in the specified corpus" message — and crucially
    must NOT cause the document to be created in the foreign corpus.
    """

    client: APIClient

    def setUp(self):
        self.alice = User.objects.create_user(
            username="alice_idor", password="pw", is_usage_capped=False
        )
        self.bob = User.objects.create_user(
            username="bob_idor", password="pw", is_usage_capped=False
        )
        self.alice_corpus = Corpus.objects.create(
            title="Alice", creator=self.alice, backend_lock=False
        )
        set_permissions_for_obj_to_user(
            self.alice, self.alice_corpus, [PermissionTypes.CRUD]
        )
        self.bob_corpus = Corpus.objects.create(
            title="Bob", creator=self.bob, backend_lock=False
        )
        set_permissions_for_obj_to_user(
            self.bob, self.bob_corpus, [PermissionTypes.CRUD]
        )
        self.bob_folder = CorpusFolder.objects.create(
            corpus=self.bob_corpus, name="bob-secrets", creator=self.bob
        )
        self.client = APIClient()

    def test_cross_user_folder_id_with_own_corpus_id_is_rejected(self):
        """
        Attacker case: alice owns ``alice_corpus`` and submits
        ``add_to_corpus_id=alice_corpus.id`` (which she can edit) but
        smuggles ``add_to_folder_id=bob_folder.id`` (which lives in
        bob's corpus). The view must reject with the unified "Folder
        not found in the specified corpus" message and NOT silently
        succeed by ignoring the cross-corpus folder.
        """
        self.client.force_authenticate(user=self.alice)
        response = self.client.post(
            SINGLE_URL,
            {
                "file": SimpleUploadedFile(
                    "doc.pdf", PDF_BYTES, content_type="application/pdf"
                ),
                "title": "IDOR attempt",
                "add_to_corpus_id": str(self.alice_corpus.id),
                "add_to_folder_id": str(self.bob_folder.id),
                "make_public": "false",
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("Folder", response.json()["error"])
        # No document should have been created.
        self.assertFalse(
            Document.objects.filter(creator=self.alice, title="IDOR attempt").exists()
        )

    def test_cross_user_folder_id_with_foreign_corpus_id_is_rejected(self):
        """
        Stricter attacker case: alice submits ``add_to_corpus_id=bob_corpus.id``
        AND the matching ``add_to_folder_id``. The corpus visibility/EDIT
        check must trip first and return the unified
        ``CORPUS_NOT_FOUND_MSG`` — not the folder-specific message and
        not a 201.
        """
        from opencontractserver.document_imports.services import (
            CORPUS_NOT_FOUND_MSG,
        )

        self.client.force_authenticate(user=self.alice)
        response = self.client.post(
            SINGLE_URL,
            {
                "file": SimpleUploadedFile(
                    "doc.pdf", PDF_BYTES, content_type="application/pdf"
                ),
                "title": "IDOR attempt 2",
                "add_to_corpus_id": str(self.bob_corpus.id),
                "add_to_folder_id": str(self.bob_folder.id),
                "make_public": "false",
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["error"], CORPUS_NOT_FOUND_MSG)
        self.assertFalse(
            Document.objects.filter(creator=self.alice, title="IDOR attempt 2").exists()
        )
