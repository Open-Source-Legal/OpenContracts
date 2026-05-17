"""
Smoke + structural tests for the split DocumentService / CorpusObjsService.

These verify that the service-layer split preserves:

- Importability of each class from its new home.
- Disjoint method sets (no accidental overlap that would create ambiguous MRO).
- Backwards-compat: ``DocumentFolderService`` exposes the full merged surface
  so existing ``from opencontractserver.corpuses.folder_service import
  DocumentFolderService`` imports keep working until the deprecation issue
  retires the alias.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.corpuses.corpus_objs_service import CorpusObjsService
from opencontractserver.corpuses.folder_service import DocumentFolderService
from opencontractserver.documents.document_service import DocumentService
from opencontractserver.types.enums import PermissionTypes

User = get_user_model()


class TestServiceSplit_MethodPartition(TestCase):
    """
    SCENARIO: DocumentService and CorpusObjsService own disjoint methods.

    BUSINESS RULE: The split is along the seam *"is the document the noun,
    or is the corpus context the noun?"*. The two classes must not define
    methods with the same name; if they did, ``DocumentFolderService``'s MRO
    would silently pick one and the merge would be inconsistent.
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


class TestServiceSplit_BackwardsCompatAlias(TestCase):
    """
    SCENARIO: DocumentFolderService still works as a back-compat alias.

    BUSINESS RULE: ~18 production files import ``DocumentFolderService``.
    The shim must expose the full merged surface from both new services so
    those imports continue to work until the follow-up migration issue
    retires the alias.
    """

    def test_dfs_mro_includes_both_new_services(self):
        mro_names = [c.__name__ for c in DocumentFolderService.__mro__]
        self.assertIn("CorpusObjsService", mro_names)
        self.assertIn("DocumentService", mro_names)

    def test_dfs_exposes_corpus_objs_service_methods(self):
        # Spot-check a corpus-scoped method.
        self.assertTrue(hasattr(DocumentFolderService, "get_corpus_documents"))
        self.assertTrue(hasattr(DocumentFolderService, "create_folder"))
        self.assertTrue(hasattr(DocumentFolderService, "soft_delete_document"))

    def test_dfs_exposes_document_service_methods(self):
        # Spot-check a document-only method.
        self.assertTrue(hasattr(DocumentFolderService, "create_document"))
        self.assertTrue(hasattr(DocumentFolderService, "set_document_permissions"))

    def test_dfs_exposes_new_convenience_methods_via_inheritance(self):
        # The new convenience methods on CorpusObjsService should be
        # visible on the shim via inheritance.
        self.assertTrue(hasattr(DocumentFolderService, "get_corpus_document_by_slug"))
        self.assertTrue(hasattr(DocumentFolderService, "get_corpus_document_by_id"))
        self.assertTrue(hasattr(DocumentFolderService, "is_document_in_corpus"))


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
