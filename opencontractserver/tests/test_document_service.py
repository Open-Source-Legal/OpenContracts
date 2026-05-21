"""
Smoke + structural tests for the split DocumentService / CorpusObjsService,
plus behavioural coverage of every public method on :class:`DocumentService`.

The structural cases verify that the service-layer split preserves:

- Importability of each class from its new home.
- Disjoint method sets (no accidental overlap that would create ambiguous MRO).

The behavioural cases drive each ``DocumentService`` method through its
branches — quota under/over cap, MIME validation happy / plaintext-fallback /
unknown / disallowed, document creation for PDF / TXT / unsupported MIME /
quota-blocked / validation-blocked / atomic-rollback, lookup IDOR safety
(owner / public / explicit READ grant / no access / nonexistent), and
permission management (owner / PERMISSION grant / denied / exception fall-
through). Codecov target #1685.
"""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.corpuses.corpus_objs_service import CorpusObjsService
from opencontractserver.documents.document_service import DocumentService
from opencontractserver.documents.models import Document
from opencontractserver.tests.fixtures import SAMPLE_PDF_FILE_ONE_PATH
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class TestServiceSplit_MethodPartition(TestCase):
    """
    SCENARIO: DocumentService and CorpusObjsService own disjoint methods.

    BUSINESS RULE: The split is along the seam *"is the document the noun,
    or is the corpus context the noun?"*. The two classes must not define
    methods with the same name; if they did, a shared subclass's MRO would
    silently pick one and the merge would be inconsistent.
    """

    def test_document_service_and_corpus_objs_service_have_no_method_collisions(self):
        ds_methods = {
            name
            for name, value in vars(DocumentService).items()
            if callable(value) and not name.startswith("__")
        }
        cos_methods = {
            name
            for name, value in vars(CorpusObjsService).items()
            if callable(value) and not name.startswith("__")
        }
        overlap = ds_methods & cos_methods
        self.assertFalse(
            overlap,
            f"DocumentService and CorpusObjsService share methods: {sorted(overlap)}. "
            f"The split must be disjoint — pick one home for each method.",
        )


class TestServiceSplit_DocumentServiceSurface(TestCase):
    """
    SCENARIO: DocumentService exposes the document-level operations.

    BUSINESS RULE: Anything where the document is the noun and corpus
    context is incidental lives on DocumentService.
    """

    def test_document_service_exposes_create_document(self):
        self.assertTrue(hasattr(DocumentService, "create_document"))

    def test_document_service_exposes_check_user_upload_quota(self):
        self.assertTrue(hasattr(DocumentService, "check_user_upload_quota"))

    def test_document_service_exposes_validate_file_type(self):
        self.assertTrue(hasattr(DocumentService, "validate_file_type"))

    def test_document_service_exposes_get_document_by_id(self):
        self.assertTrue(hasattr(DocumentService, "get_document_by_id"))

    def test_document_service_exposes_set_document_permissions(self):
        self.assertTrue(hasattr(DocumentService, "set_document_permissions"))


class TestServiceSplit_CorpusObjsServiceSurface(TestCase):
    """
    SCENARIO: CorpusObjsService exposes corpus-scoped operations.

    BUSINESS RULE: Anything of the form *"give me X inside corpus Y for
    user Z"* lives here, including the new convenience methods that close
    the legacy fusion pattern.
    """

    def test_corpus_objs_service_exposes_get_corpus_documents(self):
        self.assertTrue(hasattr(CorpusObjsService, "get_corpus_documents"))

    def test_corpus_objs_service_exposes_new_get_corpus_document_by_slug(self):
        self.assertTrue(hasattr(CorpusObjsService, "get_corpus_document_by_slug"))

    def test_corpus_objs_service_exposes_new_get_corpus_document_by_id(self):
        self.assertTrue(hasattr(CorpusObjsService, "get_corpus_document_by_id"))

    def test_corpus_objs_service_exposes_new_is_document_in_corpus(self):
        self.assertTrue(hasattr(CorpusObjsService, "is_document_in_corpus"))

    def test_corpus_objs_service_exposes_folder_crud(self):
        for name in ("create_folder", "update_folder", "move_folder", "delete_folder"):
            self.assertTrue(
                hasattr(CorpusObjsService, name),
                f"CorpusObjsService missing folder method {name!r}",
            )

    def test_corpus_objs_service_exposes_corpus_doc_lifecycle(self):
        for name in (
            "upload_document_to_corpus",
            "add_document_to_corpus",
            "remove_document_from_corpus",
            "soft_delete_document",
            "restore_document",
            "permanently_delete_document",
            "empty_trash",
        ):
            self.assertTrue(
                hasattr(CorpusObjsService, name),
                f"CorpusObjsService missing lifecycle method {name!r}",
            )


class TestDocumentService_QuotaSmoke(TestCase):
    """
    SCENARIO: DocumentService.check_user_upload_quota basic happy path.

    BUSINESS RULE: Users without ``is_usage_capped`` should always be
    allowed to upload regardless of how many documents they already have.
    """

    def test_uncapped_user_can_always_upload(self):
        user = User.objects.create_user(
            username="uncapped", email="u@test.com", password="test"
        )
        # Default user is_usage_capped should be False.
        user.is_usage_capped = False
        user.save(update_fields=["is_usage_capped"])
        can_upload, err = DocumentService.check_user_upload_quota(user)
        self.assertTrue(can_upload)
        self.assertEqual(err, "")


class TestDocumentService_PermissionEnumIntegration(TestCase):
    """
    SCENARIO: DocumentService's permission methods use the shared
    PermissionTypes enum.

    BUSINESS RULE: Permission constants must round-trip through the
    centralised enum so service callers don't have to know the underlying
    guardian codename.
    """

    def test_permission_types_enum_is_importable(self):
        # If the enum can be imported and has the expected members the
        # service-layer permission checks won't blow up at runtime.
        self.assertTrue(hasattr(PermissionTypes, "READ"))
        self.assertTrue(hasattr(PermissionTypes, "UPDATE"))
        self.assertTrue(hasattr(PermissionTypes, "DELETE"))
        self.assertTrue(hasattr(PermissionTypes, "CRUD"))


# =============================================================================
# BEHAVIOURAL COVERAGE — every public method, every branch
# =============================================================================


class TestDocumentService_CheckUserUploadQuota_Capped(TestCase):
    """
    SCENARIO: ``check_user_upload_quota`` for a usage-capped user.

    BUSINESS RULE: Capped users may only upload until they reach the
    configured ``USAGE_CAPPED_USER_DOC_CAP_COUNT`` (default 10). At-cap
    or over-cap MUST return ``(False, message)`` with a user-visible
    explanation so the API can refuse cleanly.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="capped", email="c@test.com", password="test"
        )
        self.user.is_usage_capped = True
        self.user.save(update_fields=["is_usage_capped"])

    def test_capped_user_under_cap_can_upload(self):
        # Default cap is 10; zero docs is comfortably under.
        ok, err = DocumentService.check_user_upload_quota(self.user)
        self.assertTrue(ok)
        self.assertEqual(err, "")

    def test_capped_user_at_cap_is_blocked_with_message(self):
        # Patch the cap down to 1 so we don't have to fabricate 10 docs.
        with self.settings(USAGE_CAPPED_USER_DOC_CAP_COUNT=1):
            Document.objects.create(
                creator=self.user, title="t", description="", custom_meta={}
            )
            ok, err = DocumentService.check_user_upload_quota(self.user)
        self.assertFalse(ok)
        # The message must include the cap value and reference the limit.
        self.assertIn("1", err)
        self.assertIn("capped", err.lower())


class TestDocumentService_ValidateFileType(TestCase):
    """
    SCENARIO: ``validate_file_type`` MIME-detection cases.

    BUSINESS RULE: ``filetype.guess`` recognises every binary type we
    accept. Plaintext doesn't have a magic-byte signature, so callers
    that pass plaintext content must still be admitted via the
    ``is_plaintext_content`` fallback. Anything else (random binary,
    disallowed MIME) returns ``(None, error)``.
    """

    def test_known_pdf_bytes_return_application_pdf(self):
        pdf_bytes = SAMPLE_PDF_FILE_ONE_PATH.read_bytes()
        mime, err = DocumentService.validate_file_type(pdf_bytes)
        self.assertEqual(mime, "application/pdf")
        self.assertEqual(err, "")

    def test_plaintext_falls_back_to_text_plain(self):
        # ``filetype.guess`` returns None for plaintext; the
        # is_plaintext_content branch must take over.
        mime, err = DocumentService.validate_file_type(b"hello world\n")
        self.assertEqual(mime, "text/plain")
        self.assertEqual(err, "")

    def test_unrecognisable_binary_returns_explicit_error(self):
        # Random binary bytes — no magic match, fails the plaintext check.
        mime, err = DocumentService.validate_file_type(b"\x00\x01\x02\xff\xfe")
        self.assertIsNone(mime)
        self.assertIn("Unable to determine file type", err)

    def test_disallowed_mime_is_rejected_with_message(self):
        # ZIP magic bytes "PK\x03\x04" are recognised by ``filetype``
        # but ZIP is not on the allowed-mime list, so validation must
        # surface the rejection rather than silently accepting.
        zip_magic = b"PK\x03\x04" + b"\x00" * 50
        mime, err = DocumentService.validate_file_type(zip_magic)
        self.assertIsNone(mime)
        self.assertIn("Unallowed filetype", err)


class TestDocumentService_CreateDocument(TestCase):
    """
    SCENARIO: ``create_document`` across the supported MIME branches plus
    every short-circuit.

    BUSINESS RULE: PDF / DOCX / PPTX / XLSX go into ``pdf_file``; text/plain
    into ``txt_extract_file``; anything else returns
    ``(None, "Unsupported file type: ...")``. Quota / validation failures
    return ``(None, error)`` *before* any DB write; runtime errors during
    the atomic block are caught and surfaced as
    ``(None, "Error creating document: ...")``.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="creator", email="cr@test.com", password="test"
        )
        # Default User.is_usage_capped is True; uncap for the happy paths.
        self.user.is_usage_capped = False
        self.user.save(update_fields=["is_usage_capped"])

    def test_pdf_create_lands_in_pdf_file_with_creator_perms(self):
        pdf_bytes = SAMPLE_PDF_FILE_ONE_PATH.read_bytes()
        doc, err = DocumentService.create_document(
            self.user,
            pdf_bytes,
            filename="sample.pdf",
            title="Sample PDF",
            description="from test",
            is_public=False,
        )
        assert doc is not None, f"create_document failed: {err}"
        self.assertEqual(err, "")
        self.assertEqual(doc.file_type, "application/pdf")
        self.assertTrue(doc.pdf_file)
        self.assertFalse(doc.txt_extract_file)
        # Creator must have CRUD on their new doc — the service grants this
        # via set_permissions_for_obj_to_user(PermissionTypes.CRUD).
        self.assertTrue(doc.user_can(self.user, PermissionTypes.READ))
        self.assertTrue(doc.user_can(self.user, PermissionTypes.UPDATE))

    def test_txt_create_lands_in_txt_extract_file(self):
        doc, err = DocumentService.create_document(
            self.user,
            b"plain text body\n",
            filename="notes.txt",
            title="Notes",
        )
        assert doc is not None, f"create_document failed: {err}"
        self.assertEqual(err, "")
        self.assertEqual(doc.file_type, "text/plain")
        self.assertTrue(doc.txt_extract_file)
        self.assertFalse(doc.pdf_file)

    def test_quota_blocked_short_circuits_before_validation(self):
        # Cap to 1 and create one doc directly, then attempt to create
        # a second through the service — the quota check should fire
        # before validate_file_type even runs.
        self.user.is_usage_capped = True
        self.user.save(update_fields=["is_usage_capped"])
        Document.objects.create(
            creator=self.user, title="existing", description="", custom_meta={}
        )
        with self.settings(USAGE_CAPPED_USER_DOC_CAP_COUNT=1):
            doc, err = DocumentService.create_document(
                self.user, b"\x00", filename="x", title="x"
            )
        self.assertIsNone(doc)
        self.assertIn("capped", err.lower())

    def test_validation_failure_returns_type_error(self):
        # Random unrecognised binary — validation must fail before any
        # Document row is written.
        doc, err = DocumentService.create_document(
            self.user, b"\x00\x01\x02\xff", filename="weird", title="weird"
        )
        self.assertIsNone(doc)
        self.assertIn("Unable to determine file type", err)
        self.assertFalse(Document.objects.filter(title="weird").exists())

    def test_unsupported_mime_inside_atomic_block_returns_explicit_message(self):
        # The atomic block runs *after* validate_file_type approves a MIME.
        # To exercise the inner "Unsupported file type" branch we must
        # have a MIME that passes validate_file_type's allowed-list AND
        # isn't in the PDF / DOCX / TXT switch — patch
        # validate_file_type to admit a synthetic MIME so we drop
        # directly into the else.
        with patch.object(
            DocumentService,
            "validate_file_type",
            return_value=("application/x-synthetic", ""),
        ):
            doc, err = DocumentService.create_document(
                self.user, b"\x00", filename="x", title="x"
            )
        self.assertIsNone(doc)
        self.assertIn("Unsupported file type: application/x-synthetic", err)

    def test_db_error_inside_atomic_block_is_surfaced_not_swallowed(self):
        # Force the inner Document.objects.create call to blow up so the
        # ``except Exception`` branch reports the error instead of
        # silently corrupting state.
        from opencontractserver.documents import models as doc_models

        def _boom(*args, **kwargs):
            raise RuntimeError("simulated database failure")

        with patch.object(doc_models.Document.objects, "create", side_effect=_boom):
            doc, err = DocumentService.create_document(
                self.user,
                SAMPLE_PDF_FILE_ONE_PATH.read_bytes(),
                filename="sample.pdf",
                title="boom",
            )
        self.assertIsNone(doc)
        self.assertIn("Error creating document", err)
        # Recovery: subsequent successful calls still work (no torn state).
        doc2, err2 = DocumentService.create_document(
            self.user,
            SAMPLE_PDF_FILE_ONE_PATH.read_bytes(),
            filename="ok.pdf",
            title="ok",
        )
        self.assertIsNotNone(doc2)
        self.assertEqual(err2, "")


class TestDocumentService_GetDocumentById_IDORSafety(TestCase):
    """
    SCENARIO: ``get_document_by_id`` IDOR semantics.

    BUSINESS RULE: Three accept paths (owner / public / explicit READ
    grant) and two deny paths (no access / nonexistent) must all return
    indistinguishable shape (``None`` for both denies) so an attacker
    can't probe document existence via error timing.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="o@test.com", password="test"
        )
        self.outsider = User.objects.create_user(
            username="outsider", email="x@test.com", password="test"
        )
        self.grantee = User.objects.create_user(
            username="grantee", email="g@test.com", password="test"
        )
        self.private_doc = Document.objects.create(
            creator=self.owner, title="private", description="", custom_meta={}
        )
        self.public_doc = Document.objects.create(
            creator=self.owner,
            title="public",
            description="",
            custom_meta={},
            is_public=True,
        )
        set_permissions_for_obj_to_user(
            self.grantee, self.private_doc, [PermissionTypes.READ]
        )

    def test_owner_sees_their_private_document(self):
        got = DocumentService.get_document_by_id(self.owner, self.private_doc.id)
        self.assertEqual(got, self.private_doc)

    def test_anyone_sees_public_document(self):
        got = DocumentService.get_document_by_id(self.outsider, self.public_doc.id)
        self.assertEqual(got, self.public_doc)

    def test_explicit_read_grantee_sees_private_document(self):
        got = DocumentService.get_document_by_id(self.grantee, self.private_doc.id)
        self.assertEqual(got, self.private_doc)

    def test_outsider_cannot_see_private_document(self):
        self.assertIsNone(
            DocumentService.get_document_by_id(self.outsider, self.private_doc.id)
        )

    def test_nonexistent_id_returns_none_same_as_no_access(self):
        # Indistinguishable from the outsider case above — IDOR-safe.
        self.assertIsNone(DocumentService.get_document_by_id(self.outsider, 999_999))


class TestDocumentService_SetDocumentPermissions(TestCase):
    """
    SCENARIO: ``set_document_permissions`` authorization + side effects.

    BUSINESS RULE: Only the document creator or a user holding the
    ``PERMISSION`` codename may grant permissions to a third party.
    Anyone else gets ``(False, "Permission denied: ...")``. Unhandled
    exceptions in the grant call are caught and returned as
    ``(False, "Error setting permissions: ...")`` so resolvers don't
    crash on guardian misconfiguration.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="o@test.com", password="test"
        )
        self.deputy = User.objects.create_user(
            username="deputy", email="d@test.com", password="test"
        )
        self.target = User.objects.create_user(
            username="target", email="t@test.com", password="test"
        )
        self.stranger = User.objects.create_user(
            username="stranger", email="s@test.com", password="test"
        )
        self.doc = Document.objects.create(
            creator=self.owner, title="doc", description="", custom_meta={}
        )
        # Give deputy the PERMISSION codename — they should be able to
        # grant READ to target even though they aren't the creator.
        set_permissions_for_obj_to_user(
            self.deputy, self.doc, [PermissionTypes.PERMISSION]
        )

    def test_owner_can_grant_read_to_target(self):
        ok, err = DocumentService.set_document_permissions(
            self.owner, self.doc, self.target, [PermissionTypes.READ]
        )
        self.assertTrue(ok, f"unexpected failure: {err}")
        self.assertEqual(err, "")
        self.assertTrue(self.doc.user_can(self.target, PermissionTypes.READ))

    def test_permission_codename_holder_can_grant(self):
        ok, err = DocumentService.set_document_permissions(
            self.deputy, self.doc, self.target, [PermissionTypes.READ]
        )
        self.assertTrue(ok, f"unexpected failure: {err}")
        self.assertEqual(err, "")

    def test_stranger_is_denied_with_explicit_message(self):
        ok, err = DocumentService.set_document_permissions(
            self.stranger, self.doc, self.target, [PermissionTypes.READ]
        )
        self.assertFalse(ok)
        self.assertIn("Permission denied", err)

    def test_grant_call_exception_is_caught_and_returned(self):
        # Simulate a guardian-side blow-up during assign_perm to exercise
        # the ``except Exception`` branch — the service must return a
        # generic message rather than crash up the stack.
        with patch(
            "opencontractserver.documents.document_service.set_permissions_for_obj_to_user",
            side_effect=RuntimeError("guardian misconfigured"),
        ):
            ok, err = DocumentService.set_document_permissions(
                self.owner, self.doc, self.target, [PermissionTypes.READ]
            )
        self.assertFalse(ok)
        self.assertIn("Error setting permissions", err)
