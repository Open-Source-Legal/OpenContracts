"""Structural tests for the ``corpuses/services/`` package (issue #1716).

Phase 2 of the service-layer centralization roadmap split the ~2,900-line
``corpus_objs_service.py`` monolith into the segmented
``opencontractserver.corpuses.services`` package. The behaviour of every
relocated method is regression-covered, unchanged, by
``test_corpus_objs_service.py`` (which exercises the methods through the
backward-compatible ``CorpusObjsService`` facade).

This module instead covers the *structural contract* of Phase A:

1. PACKAGE STRUCTURE — the segmented services exist, are importable, and each
   inherits ``BaseService``.
2. SHIM / FACADE — ``CorpusObjsService`` remains importable from its old
   location, aggregates all segmented services, and adds no behaviour of its own.
3. STANDALONE OPERATION — each segmented service works when called directly,
   without going through the facade (the whole point of the split).
4. CROSS-SERVICE DELEGATION — ``FolderCRUDService`` / ``FolderDocumentService``
   correctly reach helpers that now live on ``CorpusPathService`` /
   ``CorpusDocumentService``, both standalone and via the facade.

See ``docs/refactor_plans/2026-05-21-service-layer-phase2-corpus-services-plan.md``.
"""

from __future__ import annotations

import warnings
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from opencontractserver.corpuses.models import Corpus, CorpusFolder
from opencontractserver.corpuses.services import (
    CorpusDocumentService,
    CorpusPathService,
    DocumentLifecycleService,
    FolderCRUDService,
    FolderDocumentService,
)
from opencontractserver.documents.document_service import DocumentService
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.shared.services.base import BaseService
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

# The shim module emits a DeprecationWarning at import time, by design — it is
# the runtime signal Phase 2C uses for call-site discovery. Import it under a
# warnings filter so test collection stays clean even if pytest is later run
# with ``filterwarnings = error``. ``test_shim_import_emits_deprecation_warning``
# still asserts the warning fires (it re-triggers it via ``importlib.reload``).
with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from opencontractserver.corpuses.corpus_objs_service import CorpusObjsService

User = get_user_model()

# The five segmented services, in the order they are documented in the issue.
SEGMENTED_SERVICES = (
    FolderCRUDService,
    FolderDocumentService,
    CorpusDocumentService,
    DocumentLifecycleService,
    CorpusPathService,
)


# =============================================================================
# 1. PACKAGE STRUCTURE
# =============================================================================


class TestServicesPackageStructure(SimpleTestCase):
    """SCENARIO: the monolith is now a segmented ``services/`` package.

    BUSINESS RULE: each cohesive responsibility lives in its own module, and
    every service class inherits the shared ``BaseService`` machinery so it
    gains the common ``get_or_none`` / ``filter_visible`` / ``require_permission``
    / ``log_action`` helpers without re-implementing them.
    """

    def test_each_service_inherits_base_service(self):
        for service in SEGMENTED_SERVICES:
            with self.subTest(service=service.__name__):
                self.assertTrue(issubclass(service, BaseService))

    def test_package_reexports_the_segmented_services(self):
        from opencontractserver.corpuses import services

        self.assertEqual(
            sorted(services.__all__),
            sorted(
                [
                    "FolderCRUDService",
                    "FolderDocumentService",
                    "CorpusDocumentService",
                    "DocumentLifecycleService",
                    "CorpusPathService",
                ]
            ),
        )

    def test_each_service_lives_in_its_own_module(self):
        # A cohesive module per responsibility — no service shares a module.
        modules = {service.__module__ for service in SEGMENTED_SERVICES}
        self.assertEqual(len(modules), len(SEGMENTED_SERVICES))
        for service in SEGMENTED_SERVICES:
            with self.subTest(service=service.__name__):
                self.assertTrue(
                    service.__module__.startswith(
                        "opencontractserver.corpuses.services."
                    )
                )

    def test_segmented_services_share_no_method_names(self):
        """The facade relies on the segmented services having disjoint methods.

        If two services defined a method with the same name, the facade's
        method-resolution order would silently pick one — a latent bug. Pin
        the disjointness so a future name collision fails loudly here.
        """
        seen: dict[str, str] = {}
        for service in SEGMENTED_SERVICES:
            for name, value in vars(service).items():
                if name.startswith("__"):
                    continue
                if not callable(getattr(service, name)):
                    continue
                self.assertNotIn(
                    name,
                    seen,
                    f"{name} defined on both {seen.get(name)} and "
                    f"{service.__name__}",
                )
                seen[name] = service.__name__


# =============================================================================
# 2. SHIM / FACADE BACKWARD COMPATIBILITY
# =============================================================================


class TestCorpusObjsServiceShimFacade(SimpleTestCase):
    """SCENARIO: ``CorpusObjsService`` survives the split as a deprecated facade.

    BUSINESS RULE: existing callers import ``CorpusObjsService`` from
    ``opencontractserver.corpuses.corpus_objs_service`` and call its methods.
    The shim keeps that import path and every ``CorpusObjsService.<method>``
    call working until call sites are migrated, by multiply-inheriting the
    five segmented services. The facade itself adds no behaviour.
    """

    def test_facade_subclasses_every_segmented_service(self):
        for service in SEGMENTED_SERVICES:
            with self.subTest(service=service.__name__):
                self.assertTrue(issubclass(CorpusObjsService, service))

    def test_facade_is_a_base_service(self):
        self.assertTrue(issubclass(CorpusObjsService, BaseService))

    def test_facade_defines_no_methods_of_its_own(self):
        """The facade is a pure aggregation point — it overrides nothing."""
        own = {
            name
            for name, value in vars(CorpusObjsService).items()
            if not name.startswith("__")
        }
        self.assertEqual(own, set())

    def test_facade_exposes_every_segmented_method(self):
        """Every public + private method of each service is callable via the
        facade — this is what keeps the 300+ existing call sites working."""
        for service in SEGMENTED_SERVICES:
            for name, value in vars(service).items():
                if name.startswith("__") or not callable(getattr(service, name)):
                    continue
                with self.subTest(method=name):
                    # The facade attribute resolves (via MRO) to the very same
                    # underlying function defined on the owning segmented
                    # service. ``classmethod`` access yields a bound method, so
                    # compare the underlying ``__func__``; ``staticmethod``
                    # access yields the plain function (no ``__func__``).
                    facade_attr = getattr(CorpusObjsService, name)
                    service_attr = getattr(service, name)
                    facade_fn = getattr(facade_attr, "__func__", facade_attr)
                    service_fn = getattr(service_attr, "__func__", service_attr)
                    self.assertIs(facade_fn, service_fn)

    def test_facade_mro_is_unambiguous(self):
        """C3 linearisation succeeds and visits all segmented services + BaseService."""
        mro = CorpusObjsService.__mro__
        for service in SEGMENTED_SERVICES:
            self.assertIn(service, mro)
        self.assertIn(BaseService, mro)

    def test_shim_module_reexports_the_segmented_services_too(self):
        from opencontractserver.corpuses import corpus_objs_service as shim

        self.assertIs(shim.FolderCRUDService, FolderCRUDService)
        self.assertIs(shim.FolderDocumentService, FolderDocumentService)
        self.assertIs(shim.CorpusDocumentService, CorpusDocumentService)
        self.assertIs(shim.DocumentLifecycleService, DocumentLifecycleService)
        self.assertIs(shim.CorpusPathService, CorpusPathService)

    def test_shim_import_emits_deprecation_warning(self):
        """Importing the shim fires a ``DeprecationWarning`` — the runtime
        signal Phase 2C relies on for call-site discovery."""
        import importlib
        import warnings

        from opencontractserver.corpuses import corpus_objs_service as shim

        # The shim's ``warnings.warn`` fires at module-execution time, and the
        # module is already cached (imported at this file's top), so the
        # warning has long since fired and been deduplicated. ``reload``
        # re-executes the module body to fire it again; it must run inside
        # ``catch_warnings`` so the re-emission is observed in isolation.
        # ``reload`` is safe here only because the shim and the segmented
        # service modules have no module-level side effects beyond that single
        # ``warnings.warn`` (no signal registration, no global mutation).
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            importlib.reload(shim)

        self.assertTrue(
            any(issubclass(w.category, DeprecationWarning) for w in caught),
            "shim import should emit a DeprecationWarning",
        )


# =============================================================================
# 3. STANDALONE OPERATION OF EACH SEGMENTED SERVICE
# =============================================================================


class TestFolderCRUDServiceStandalone(TestCase):
    """SCENARIO: ``FolderCRUDService`` is usable directly, without the facade.

    BUSINESS RULE: new code imports and calls the segmented service
    (``FolderCRUDService.create_folder(...)``) — it does not need, and should
    not use, the deprecated ``CorpusObjsService`` facade.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="fs_owner", email="fs_owner@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="FolderCRUDService Corpus", creator=self.owner, is_public=False
        )

    def test_create_read_update_delete_folder_directly(self):
        folder, error = FolderCRUDService.create_folder(
            user=self.owner, corpus=self.corpus, name="Contracts"
        )
        self.assertEqual(error, "")
        self.assertIsNotNone(folder)
        assert folder is not None

        visible = FolderCRUDService.get_visible_folders(self.owner, self.corpus.id)
        self.assertIn(folder.id, {f.id for f in visible})

        ok, error = FolderCRUDService.update_folder(
            user=self.owner, folder=folder, name="Renamed"
        )
        self.assertTrue(ok)
        folder.refresh_from_db()
        self.assertEqual(folder.name, "Renamed")

        ok, error = FolderCRUDService.delete_folder(user=self.owner, folder=folder)
        self.assertTrue(ok)
        self.assertFalse(CorpusFolder.objects.filter(id=folder.id).exists())


class TestFolderDocumentServiceStandalone(TestCase):
    """SCENARIO: ``FolderDocumentService`` is usable directly, without the facade.

    BUSINESS RULE: document-in-folder placement, lookup, and listing resolve
    through the segmented service. ``FolderDocumentService`` reaches folder-CRUD
    helpers only through explicit sibling-service references, so it works
    standalone — it does not depend on the facade or on ``FolderCRUDService``
    being mixed in.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="fds_owner", email="fds_owner@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="FolderDocumentService Corpus",
            creator=self.owner,
            is_public=False,
        )
        folder, _ = FolderCRUDService.create_folder(
            user=self.owner, corpus=self.corpus, name="Inbox"
        )
        assert folder is not None
        self.folder = folder
        self.document = Document.objects.create(
            title="Doc", creator=self.owner, pdf_file="fds.pdf"
        )
        DocumentPath.objects.create(
            document=self.document,
            corpus=self.corpus,
            creator=self.owner,
            folder=None,
            path="/fds.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

    def test_move_then_list_and_lookup_document_in_folder(self):
        ok, error = FolderDocumentService.move_document_to_folder(
            user=self.owner,
            document=self.document,
            corpus=self.corpus,
            folder=self.folder,
        )
        self.assertTrue(ok, error)

        current_folder = FolderDocumentService.get_document_folder(
            user=self.owner, document=self.document, corpus=self.corpus
        )
        self.assertIsNotNone(current_folder)
        assert current_folder is not None
        self.assertEqual(current_folder.id, self.folder.id)

        docs_in_folder = FolderDocumentService.get_folder_documents(
            user=self.owner, corpus_id=self.corpus.id, folder_id=self.folder.id
        )
        self.assertIn(self.document.id, {d.id for d in docs_in_folder})

        count = FolderDocumentService.get_folder_document_count(
            user=self.owner, folder=self.folder
        )
        self.assertEqual(count, 1)


class TestCorpusDocumentServiceStandalone(TestCase):
    """SCENARIO: ``CorpusDocumentService`` is usable directly.

    BUSINESS RULE: corpus-scoped document reads and membership checks resolve
    through the segmented service without the facade.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="cds_owner", email="cds_owner@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="CorpusDocumentService Corpus",
            creator=self.owner,
            is_public=False,
        )
        self.document = Document.objects.create(
            title="Doc", creator=self.owner, pdf_file="cds.pdf"
        )
        DocumentPath.objects.create(
            document=self.document,
            corpus=self.corpus,
            creator=self.owner,
            folder=None,
            path="/cds.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

    def test_get_corpus_documents_directly(self):
        docs = CorpusDocumentService.get_corpus_documents(self.owner, self.corpus)
        self.assertIn(self.document.id, {d.id for d in docs})

    def test_is_document_in_corpus_directly(self):
        self.assertTrue(
            CorpusDocumentService.is_document_in_corpus(
                self.owner, self.corpus, self.document.id
            )
        )

    def test_membership_helper_directly(self):
        self.assertTrue(
            CorpusDocumentService._check_document_in_corpus(self.document, self.corpus)
        )


class TestDocumentLifecycleServiceStandalone(TestCase):
    """SCENARIO: ``DocumentLifecycleService`` is usable directly.

    BUSINESS RULE: soft-delete / restore / trash work through the segmented
    service. ``soft_delete_document`` additionally exercises a CROSS-service
    call into ``CorpusDocumentService._check_document_in_corpus``.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="dls_owner", email="dls_owner@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="DocumentLifecycleService Corpus",
            creator=self.owner,
            is_public=False,
        )
        self.document = Document.objects.create(
            title="Doc", creator=self.owner, pdf_file="dls.pdf"
        )
        DocumentPath.objects.create(
            document=self.document,
            corpus=self.corpus,
            creator=self.owner,
            folder=None,
            path="/dls.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

    def test_soft_delete_then_restore_directly(self):
        ok, error = DocumentLifecycleService.soft_delete_document(
            user=self.owner, document=self.document, corpus=self.corpus
        )
        self.assertTrue(ok, error)

        deleted = DocumentLifecycleService.get_deleted_documents(
            self.owner, self.corpus.id
        )
        deleted_path = deleted.get(document=self.document)

        ok, error = DocumentLifecycleService.restore_document(
            user=self.owner, document_path=deleted_path
        )
        self.assertTrue(ok, error)

    def test_soft_delete_rejects_document_not_in_corpus(self):
        """The cross-service membership guard fires for a foreign document."""
        other_corpus = Corpus.objects.create(
            title="Other", creator=self.owner, is_public=False
        )
        ok, error = DocumentLifecycleService.soft_delete_document(
            user=self.owner, document=self.document, corpus=other_corpus
        )
        self.assertFalse(ok)
        self.assertIn("does not belong", error)


class TestCorpusPathServiceStandalone(SimpleTestCase):
    """SCENARIO: ``CorpusPathService`` holds the pure path helpers.

    BUSINESS RULE: path-string computation is permission-free and
    side-effect-free — it can be exercised without a database.
    """

    def test_compute_moved_path_to_root(self):
        self.assertEqual(
            CorpusPathService._compute_moved_path("/old/dir/report.pdf", None),
            "/report.pdf",
        )

    def test_target_directory_string_for_root(self):
        self.assertEqual(
            CorpusPathService._target_directory_string_from_path(None), "/"
        )

    def test_target_directory_string_for_nested_folder(self):
        self.assertEqual(
            CorpusPathService._target_directory_string_from_path("Legal/Contracts"),
            "/Legal/Contracts/",
        )


# =============================================================================
# 4. CROSS-SERVICE DELEGATION (standalone) + FACADE EQUIVALENCE
# =============================================================================


class TestCrossServiceDelegation(TestCase):
    """SCENARIO: folder write operations reach helpers on sibling services.

    BUSINESS RULE: ``FolderDocumentService`` move operations and
    ``FolderCRUDService.delete_folder`` delegate path disambiguation to
    ``CorpusPathService`` and membership checks to ``CorpusDocumentService``
    via explicit class references. The relocation must work when those
    services are used STANDALONE — the explicit references do not depend on
    being reached through the facade.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="xsd_owner", email="xsd_owner@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="CrossService Corpus", creator=self.owner, is_public=False
        )
        folder, _ = FolderCRUDService.create_folder(
            user=self.owner, corpus=self.corpus, name="Target"
        )
        assert folder is not None
        self.folder = folder
        self.documents = []
        for i in range(2):
            doc = Document.objects.create(
                title=f"Doc {i}", creator=self.owner, pdf_file=f"xsd{i}.pdf"
            )
            DocumentPath.objects.create(
                document=doc,
                corpus=self.corpus,
                creator=self.owner,
                folder=None,
                path=f"/xsd{i}.pdf",
                version_number=1,
                is_current=True,
                is_deleted=False,
            )
            self.documents.append(doc)

    def test_move_document_to_folder_standalone_uses_path_service(self):
        """``FolderDocumentService.move_document_to_folder`` -> ``CorpusPathService``."""
        ok, error = FolderDocumentService.move_document_to_folder(
            user=self.owner,
            document=self.documents[0],
            corpus=self.corpus,
            folder=self.folder,
        )
        self.assertTrue(ok, error)
        current = DocumentPath.objects.get(
            document=self.documents[0],
            corpus=self.corpus,
            is_current=True,
            is_deleted=False,
        )
        self.assertEqual(current.folder_id, self.folder.id)

    def test_bulk_move_standalone_uses_path_service(self):
        """``FolderDocumentService.move_documents_to_folder`` disambiguates paths
        via ``CorpusPathService`` even though the two now live in separate
        modules."""
        doc_ids = [d.id for d in self.documents]
        moved, error = FolderDocumentService.move_documents_to_folder(
            user=self.owner,
            document_ids=doc_ids,
            corpus=self.corpus,
            folder=self.folder,
        )
        self.assertEqual(error, "")
        self.assertEqual(moved, 2)
        for doc in self.documents:
            current = DocumentPath.objects.get(
                document=doc,
                corpus=self.corpus,
                is_current=True,
                is_deleted=False,
            )
            self.assertEqual(current.folder_id, self.folder.id)

    def test_delete_folder_standalone_relocates_documents(self):
        """``FolderCRUDService.delete_folder`` displaces documents to root via
        the ``CorpusPathService`` disambiguation helpers."""
        FolderDocumentService.move_documents_to_folder(
            user=self.owner,
            document_ids=[d.id for d in self.documents],
            corpus=self.corpus,
            folder=self.folder,
        )
        ok, error = FolderCRUDService.delete_folder(user=self.owner, folder=self.folder)
        self.assertTrue(ok, error)
        for doc in self.documents:
            current = DocumentPath.objects.get(
                document=doc,
                corpus=self.corpus,
                is_current=True,
                is_deleted=False,
            )
            self.assertIsNone(current.folder_id)


class TestFacadeEquivalence(TestCase):
    """SCENARIO: the facade and the segmented service produce identical results.

    BUSINESS RULE: routing a call through ``CorpusObjsService`` (legacy) or
    through the segmented service directly (new code) must behave identically —
    the facade is a pure pass-through, so the migration of call sites in later
    phases is a no-op behaviourally.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="fe_owner", email="fe_owner@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="FacadeEquivalence Corpus", creator=self.owner, is_public=False
        )

    def test_create_folder_via_facade_matches_segmented_service(self):
        via_facade, facade_err = CorpusObjsService.create_folder(
            user=self.owner, corpus=self.corpus, name="ViaFacade"
        )
        via_service, service_err = FolderCRUDService.create_folder(
            user=self.owner, corpus=self.corpus, name="ViaService"
        )
        self.assertEqual(facade_err, "")
        self.assertEqual(service_err, "")
        assert via_facade is not None
        assert via_service is not None
        self.assertEqual(via_facade.corpus_id, via_service.corpus_id)
        self.assertEqual(type(via_facade), type(via_service))

    def test_bulk_move_via_facade_matches_segmented_service(self):
        """A cross-module operation (bulk move -> path disambiguation) behaves
        identically whether dispatched through the facade or the service."""
        folder, _ = FolderCRUDService.create_folder(
            user=self.owner, corpus=self.corpus, name="Dest"
        )
        results = {}
        for label, entrypoint in (
            ("facade", CorpusObjsService),
            ("service", FolderDocumentService),
        ):
            doc = Document.objects.create(
                title=f"Doc {label}",
                creator=self.owner,
                pdf_file=f"fe_{label}.pdf",
            )
            DocumentPath.objects.create(
                document=doc,
                corpus=self.corpus,
                creator=self.owner,
                folder=None,
                path=f"/fe_{label}.pdf",
                version_number=1,
                is_current=True,
                is_deleted=False,
            )
            moved, error = entrypoint.move_documents_to_folder(
                user=self.owner,
                document_ids=[doc.id],
                corpus=self.corpus,
                folder=folder,
            )
            results[label] = (moved, error)

        self.assertEqual(results["facade"], results["service"])
        self.assertEqual(results["facade"], (1, ""))


# =============================================================================
# 5. ERROR & EDGE-CASE COVERAGE OF THE SEGMENTED SERVICES
# =============================================================================
#
# The behavioural regression net (``test_corpus_objs_service.py``) exercises the
# happy paths of every relocated method. The classes below pin the permission,
# error, and edge branches that the regression net does not reach — keeping the
# segmented ``services/`` package at full diff coverage now that each module is
# new code in Codecov's eyes.


class _SegmentedServiceCoverageBase(TestCase):
    """Shared fixtures + helpers for the segmented-service coverage classes."""

    PDF_BYTES = b"%PDF-1.4 minimal pdf content"

    def setUp(self):
        self.owner = User.objects.create_user(
            username="cov_owner", email="cov_owner@test.com", password="test"
        )
        self.stranger = User.objects.create_user(
            username="cov_stranger", email="cov_stranger@test.com", password="test"
        )
        self.reader = User.objects.create_user(
            username="cov_reader", email="cov_reader@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Coverage Corpus", creator=self.owner, is_public=False
        )
        set_permissions_for_obj_to_user(
            self.reader, self.corpus, [PermissionTypes.READ]
        )

    def _doc_with_path(
        self,
        filename: str,
        *,
        corpus: Corpus | None = None,
        folder: CorpusFolder | None = None,
        path: str | None = None,
        is_current: bool = True,
        is_deleted: bool = False,
    ) -> tuple[Document, DocumentPath]:
        """Create a standalone Document plus a DocumentPath placing it in a corpus."""
        target_corpus = corpus or self.corpus
        document = Document.objects.create(
            title=filename, creator=self.owner, pdf_file=filename
        )
        document_path = DocumentPath.objects.create(
            document=document,
            corpus=target_corpus,
            creator=self.owner,
            folder=folder,
            path=path if path is not None else f"/{filename}",
            version_number=1,
            is_current=is_current,
            is_deleted=is_deleted,
        )
        return document, document_path


class TestCorpusDocumentServiceCoverage(_SegmentedServiceCoverageBase):
    """Permission / error branches of ``CorpusDocumentService`` writes."""

    def test_upload_document_to_corpus_happy_path(self):
        corpus_doc, status, error = CorpusDocumentService.upload_document_to_corpus(
            user=self.owner,
            corpus=self.corpus,
            file_bytes=self.PDF_BYTES,
            filename="upload.pdf",
            title="Uploaded",
        )
        self.assertEqual(error, "")
        self.assertEqual(status, "added")
        self.assertIsNotNone(corpus_doc)

    def test_upload_document_to_corpus_requires_corpus_write(self):
        corpus_doc, status, error = CorpusDocumentService.upload_document_to_corpus(
            user=self.reader,
            corpus=self.corpus,
            file_bytes=self.PDF_BYTES,
            filename="upload.pdf",
            title="Uploaded",
        )
        self.assertIsNone(corpus_doc)
        self.assertEqual(status, "")
        self.assertIn("Permission denied", error)

    def test_upload_document_to_corpus_propagates_create_failure(self):
        with patch.object(
            DocumentService, "create_document", return_value=(None, "create boom")
        ):
            corpus_doc, status, error = CorpusDocumentService.upload_document_to_corpus(
                user=self.owner,
                corpus=self.corpus,
                file_bytes=self.PDF_BYTES,
                filename="upload.pdf",
                title="Uploaded",
            )
        self.assertIsNone(corpus_doc)
        self.assertEqual(error, "create boom")

    def test_upload_document_to_corpus_propagates_add_failure(self):
        with patch.object(
            CorpusDocumentService,
            "add_document_to_corpus",
            return_value=(None, "", "add boom"),
        ):
            corpus_doc, status, error = CorpusDocumentService.upload_document_to_corpus(
                user=self.owner,
                corpus=self.corpus,
                file_bytes=self.PDF_BYTES,
                filename="upload.pdf",
                title="Uploaded",
            )
        self.assertIsNone(corpus_doc)
        self.assertEqual(error, "add boom")

    def test_add_document_to_corpus_requires_corpus_write(self):
        document, _ = self._doc_with_path("addme.pdf")
        corpus_doc, status, error = CorpusDocumentService.add_document_to_corpus(
            user=self.reader, document=document, corpus=self.corpus
        )
        self.assertIsNone(corpus_doc)
        self.assertIn("write access", error)

    def test_add_document_to_corpus_requires_document_read(self):
        private_doc = Document.objects.create(
            title="Private", creator=self.stranger, pdf_file="private.pdf"
        )
        corpus_doc, status, error = CorpusDocumentService.add_document_to_corpus(
            user=self.owner, document=private_doc, corpus=self.corpus
        )
        self.assertIsNone(corpus_doc)
        self.assertIn("access to this document", error)

    def test_add_document_to_corpus_wraps_unexpected_error(self):
        document = Document.objects.create(
            title="Doc", creator=self.owner, pdf_file="doc.pdf"
        )
        with patch.object(Corpus, "add_document", side_effect=Exception("kaboom")):
            corpus_doc, status, error = CorpusDocumentService.add_document_to_corpus(
                user=self.owner, document=document, corpus=self.corpus
            )
        self.assertIsNone(corpus_doc)
        self.assertIn("Error adding document to corpus", error)

    def test_add_documents_to_corpus_requires_corpus_write(self):
        added_count, added_ids, error = CorpusDocumentService.add_documents_to_corpus(
            user=self.reader, document_ids=[1], corpus=self.corpus
        )
        self.assertEqual(added_count, 0)
        self.assertEqual(added_ids, [])
        self.assertIn("write access", error)

    def test_add_documents_to_corpus_happy_path(self):
        docs = [
            Document.objects.create(
                title=f"Bulk {i}", creator=self.owner, pdf_file=f"bulk{i}.pdf"
            )
            for i in range(2)
        ]
        added_count, added_ids, error = CorpusDocumentService.add_documents_to_corpus(
            user=self.owner,
            document_ids=[d.id for d in docs],
            corpus=self.corpus,
        )
        self.assertEqual(added_count, 2)
        self.assertEqual(len(added_ids), 2)
        self.assertEqual(error, "")

    def test_add_documents_to_corpus_collects_per_document_errors(self):
        document = Document.objects.create(
            title="Doc", creator=self.owner, pdf_file="doc.pdf"
        )
        with patch.object(
            CorpusDocumentService,
            "add_document_to_corpus",
            return_value=(None, "", "per-doc boom"),
        ):
            added_count, added_ids, error = (
                CorpusDocumentService.add_documents_to_corpus(
                    user=self.owner,
                    document_ids=[document.id],
                    corpus=self.corpus,
                )
            )
        self.assertEqual(added_count, 0)
        self.assertEqual(added_ids, [])
        self.assertIn("per-doc boom", error)

    def test_remove_document_from_corpus_reports_missing_document(self):
        document = Document.objects.create(
            title="Loose", creator=self.owner, pdf_file="loose.pdf"
        )
        success, error = CorpusDocumentService.remove_document_from_corpus(
            user=self.owner, document=document, corpus=self.corpus
        )
        self.assertFalse(success)
        self.assertIn("not found in corpus", error)

    def test_remove_document_from_corpus_wraps_unexpected_error(self):
        document, _ = self._doc_with_path("removeme.pdf")
        with patch.object(Corpus, "remove_document", side_effect=Exception("kaboom")):
            success, error = CorpusDocumentService.remove_document_from_corpus(
                user=self.owner, document=document, corpus=self.corpus
            )
        self.assertFalse(success)
        self.assertIn("Error removing document from corpus", error)

    def test_remove_documents_from_corpus_requires_corpus_write(self):
        removed_count, error = CorpusDocumentService.remove_documents_from_corpus(
            user=self.reader, document_ids=[1], corpus=self.corpus
        )
        self.assertEqual(removed_count, 0)
        self.assertIn("write access", error)

    def test_remove_documents_from_corpus_collects_per_document_errors(self):
        corpus_doc, _, _ = CorpusDocumentService.add_document_to_corpus(
            user=self.owner,
            document=Document.objects.create(
                title="Doc", creator=self.owner, pdf_file="doc.pdf"
            ),
            corpus=self.corpus,
        )
        assert corpus_doc is not None
        with patch.object(
            CorpusDocumentService,
            "remove_document_from_corpus",
            return_value=(False, "per-doc boom"),
        ):
            removed_count, error = CorpusDocumentService.remove_documents_from_corpus(
                user=self.owner,
                document_ids=[corpus_doc.id],
                corpus=self.corpus,
            )
        self.assertEqual(removed_count, 0)
        self.assertIn("per-doc boom", error)


class TestFolderDocumentServiceCoverage(_SegmentedServiceCoverageBase):
    """Permission / error branches of ``FolderDocumentService``."""

    def test_get_folder_documents_missing_corpus_is_empty(self):
        result = FolderDocumentService.get_folder_documents(
            user=self.owner, corpus_id=9_999_999
        )
        self.assertEqual(list(result), [])

    def test_get_folder_documents_without_permission_is_empty(self):
        result = FolderDocumentService.get_folder_documents(
            user=self.stranger, corpus_id=self.corpus.id
        )
        self.assertEqual(list(result), [])

    def test_get_folder_document_ids_root_and_folder(self):
        folder, _ = FolderCRUDService.create_folder(
            user=self.owner, corpus=self.corpus, name="Inbox"
        )
        assert folder is not None
        root_doc, _ = self._doc_with_path("root.pdf")
        folder_doc, _ = self._doc_with_path("filed.pdf", folder=folder)

        root_ids = FolderDocumentService.get_folder_document_ids(
            user=self.owner, corpus_id=self.corpus.id, folder_id=None
        )
        folder_ids = FolderDocumentService.get_folder_document_ids(
            user=self.owner, corpus_id=self.corpus.id, folder_id=folder.id
        )
        self.assertEqual(root_ids, {root_doc.id})
        self.assertEqual(folder_ids, {folder_doc.id})

    def test_get_folder_document_ids_missing_corpus_is_empty(self):
        self.assertEqual(
            FolderDocumentService.get_folder_document_ids(
                user=self.owner, corpus_id=9_999_999
            ),
            set(),
        )

    def test_get_folder_document_ids_without_permission_is_empty(self):
        self.assertEqual(
            FolderDocumentService.get_folder_document_ids(
                user=self.stranger, corpus_id=self.corpus.id
            ),
            set(),
        )

    def test_get_folder_document_count_without_permission_is_zero(self):
        folder, _ = FolderCRUDService.create_folder(
            user=self.owner, corpus=self.corpus, name="Counted"
        )
        assert folder is not None
        self.assertEqual(
            FolderDocumentService.get_folder_document_count(
                user=self.stranger, folder=folder
            ),
            0,
        )

    def test_get_folder_document_count_include_descendants(self):
        folder, _ = FolderCRUDService.create_folder(
            user=self.owner, corpus=self.corpus, name="Tree"
        )
        assert folder is not None
        count = FolderDocumentService.get_folder_document_count(
            user=self.owner, folder=folder, include_descendants=True
        )
        self.assertEqual(count, 0)

    def test_move_document_to_folder_rejects_foreign_folder(self):
        document, _ = self._doc_with_path("move.pdf")
        other_corpus = Corpus.objects.create(
            title="Other", creator=self.owner, is_public=False
        )
        foreign_folder, _ = FolderCRUDService.create_folder(
            user=self.owner, corpus=other_corpus, name="Foreign"
        )
        success, error = FolderDocumentService.move_document_to_folder(
            user=self.owner,
            document=document,
            corpus=self.corpus,
            folder=foreign_folder,
        )
        self.assertFalse(success)
        self.assertIn("does not belong to this corpus", error)

    def test_move_document_to_folder_surfaces_path_value_error(self):
        document, _ = self._doc_with_path("rooted.pdf", path="/")
        folder, _ = FolderCRUDService.create_folder(
            user=self.owner, corpus=self.corpus, name="Dest"
        )
        assert folder is not None
        success, error = FolderDocumentService.move_document_to_folder(
            user=self.owner,
            document=document,
            corpus=self.corpus,
            folder=folder,
        )
        self.assertFalse(success)
        self.assertIn("Cannot extract filename", error)

    def test_move_documents_to_folder_requires_corpus_write(self):
        removed, error = FolderDocumentService.move_documents_to_folder(
            user=self.reader, document_ids=[1], corpus=self.corpus
        )
        self.assertEqual(removed, 0)
        self.assertIn("write access", error)

    def test_move_documents_to_folder_rejects_foreign_folder(self):
        other_corpus = Corpus.objects.create(
            title="Other", creator=self.owner, is_public=False
        )
        foreign_folder, _ = FolderCRUDService.create_folder(
            user=self.owner, corpus=other_corpus, name="Foreign"
        )
        moved, error = FolderDocumentService.move_documents_to_folder(
            user=self.owner,
            document_ids=[1],
            corpus=self.corpus,
            folder=foreign_folder,
        )
        self.assertEqual(moved, 0)
        self.assertIn("does not belong to this corpus", error)

    def test_move_documents_to_folder_reports_documents_not_in_corpus(self):
        document, _ = self._doc_with_path("present.pdf")
        moved, error = FolderDocumentService.move_documents_to_folder(
            user=self.owner,
            document_ids=[document.id, 9_999_999],
            corpus=self.corpus,
        )
        self.assertEqual(moved, 0)
        self.assertIn("do not belong to this corpus", error)

    def test_move_documents_to_folder_noop_when_already_in_target(self):
        document, _ = self._doc_with_path("stable.pdf")
        moved, error = FolderDocumentService.move_documents_to_folder(
            user=self.owner,
            document_ids=[document.id],
            corpus=self.corpus,
            folder=None,
        )
        self.assertEqual(moved, 0)
        self.assertEqual(error, "")

    def test_get_document_folder_without_permission_is_none(self):
        document, _ = self._doc_with_path("folderless.pdf")
        self.assertIsNone(
            FolderDocumentService.get_document_folder(
                user=self.stranger, document=document, corpus=self.corpus
            )
        )

    def test_get_document_folder_missing_path_is_none(self):
        document = Document.objects.create(
            title="Unpathed", creator=self.owner, pdf_file="unpathed.pdf"
        )
        self.assertIsNone(
            FolderDocumentService.get_document_folder(
                user=self.owner, document=document, corpus=self.corpus
            )
        )


class TestFolderCRUDServiceCoverage(_SegmentedServiceCoverageBase):
    """Permission / error branches of ``FolderCRUDService``."""

    def test_get_visible_folders_filters_by_parent(self):
        parent, _ = FolderCRUDService.create_folder(
            user=self.owner, corpus=self.corpus, name="Parent"
        )
        assert parent is not None
        child, _ = FolderCRUDService.create_folder(
            user=self.owner, corpus=self.corpus, name="Child", parent=parent
        )
        assert child is not None
        visible = FolderCRUDService.get_visible_folders(
            self.owner, self.corpus.id, parent_id=parent.id
        )
        self.assertEqual({f.id for f in visible}, {child.id})

    def test_create_folder_rejects_parent_from_other_corpus(self):
        other_corpus = Corpus.objects.create(
            title="Other", creator=self.owner, is_public=False
        )
        foreign_parent, _ = FolderCRUDService.create_folder(
            user=self.owner, corpus=other_corpus, name="Foreign"
        )
        folder, error = FolderCRUDService.create_folder(
            user=self.owner,
            corpus=self.corpus,
            name="Child",
            parent=foreign_parent,
        )
        self.assertIsNone(folder)
        self.assertIn("same corpus", error)

    def test_update_folder_requires_corpus_write(self):
        folder, _ = FolderCRUDService.create_folder(
            user=self.owner, corpus=self.corpus, name="Locked"
        )
        assert folder is not None
        success, error = FolderCRUDService.update_folder(
            user=self.reader, folder=folder, name="Renamed"
        )
        self.assertFalse(success)
        self.assertIn("write access", error)

    def test_move_folder_requires_corpus_write(self):
        folder, _ = FolderCRUDService.create_folder(
            user=self.owner, corpus=self.corpus, name="Movable"
        )
        assert folder is not None
        success, error = FolderCRUDService.move_folder(
            user=self.reader, folder=folder, new_parent=None
        )
        self.assertFalse(success)
        self.assertIn("write access", error)

    def test_get_folder_path_returns_path_or_none(self):
        folder, _ = FolderCRUDService.create_folder(
            user=self.owner, corpus=self.corpus, name="Pathy"
        )
        assert folder is not None
        path = FolderCRUDService.get_folder_path(user=self.owner, folder=folder)
        self.assertIsNotNone(path)
        assert path is not None
        self.assertTrue(path.startswith("/"))
        self.assertIsNone(
            FolderCRUDService.get_folder_path(user=self.stranger, folder=folder)
        )

    def test_search_folders_filters_by_name(self):
        FolderCRUDService.create_folder(
            user=self.owner, corpus=self.corpus, name="Contracts"
        )
        FolderCRUDService.create_folder(
            user=self.owner, corpus=self.corpus, name="Invoices"
        )
        matches = FolderCRUDService.search_folders(
            user=self.owner, corpus_id=self.corpus.id, query="contr"
        )
        self.assertEqual({f.name for f in matches}, {"Contracts"})

    def test_create_folder_structure_reuses_existing_under_target(self):
        target, _ = FolderCRUDService.create_folder(
            user=self.owner, corpus=self.corpus, name="Target"
        )
        assert target is not None
        existing, _ = FolderCRUDService.create_folder(
            user=self.owner, corpus=self.corpus, name="sub", parent=target
        )
        assert existing is not None
        folder_map, created, reused, error = (
            FolderCRUDService.create_folder_structure_from_paths(
                user=self.owner,
                corpus=self.corpus,
                folder_paths=["sub"],
                target_folder=target,
            )
        )
        self.assertEqual(error, "")
        self.assertEqual(created, 0)
        self.assertEqual(reused, 1)
        self.assertEqual(folder_map["sub"].id, existing.id)

    def test_create_folder_structure_resolves_parent_from_existing_corpus_folder(
        self,
    ):
        FolderCRUDService.create_folder(
            user=self.owner, corpus=self.corpus, name="docs"
        )
        folder_map, created, reused, error = (
            FolderCRUDService.create_folder_structure_from_paths(
                user=self.owner,
                corpus=self.corpus,
                folder_paths=["docs/contracts"],
            )
        )
        self.assertEqual(error, "")
        self.assertEqual(created, 1)
        self.assertIn("docs/contracts", folder_map)

    def test_create_folder_structure_errors_on_missing_parent(self):
        folder_map, created, reused, error = (
            FolderCRUDService.create_folder_structure_from_paths(
                user=self.owner,
                corpus=self.corpus,
                folder_paths=["ghost/child"],
            )
        )
        self.assertEqual(folder_map, {})
        self.assertIn("Parent folder not found", error)


class TestDocumentLifecycleServiceCoverage(_SegmentedServiceCoverageBase):
    """Permission / error branches of ``DocumentLifecycleService``."""

    def test_soft_delete_document_requires_corpus_delete(self):
        document, _ = self._doc_with_path("trash.pdf")
        success, error = DocumentLifecycleService.soft_delete_document(
            user=self.reader, document=document, corpus=self.corpus
        )
        self.assertFalse(success)
        self.assertIn("delete access", error)

    def test_soft_delete_document_without_active_path(self):
        # The document is "in" the corpus (a path row exists) but its only
        # current path is already soft-deleted, so there is no active path.
        document, _ = self._doc_with_path(
            "already-deleted.pdf", is_current=True, is_deleted=True
        )
        success, error = DocumentLifecycleService.soft_delete_document(
            user=self.owner, document=document, corpus=self.corpus
        )
        self.assertFalse(success)
        self.assertIn("no active path", error)

    def test_restore_document_rejects_non_deleted_path(self):
        _, document_path = self._doc_with_path("live.pdf")
        success, error = DocumentLifecycleService.restore_document(
            user=self.owner, document_path=document_path
        )
        self.assertFalse(success)
        self.assertIn("not deleted", error)

    def test_restore_document_rejects_non_current_path(self):
        _, document_path = self._doc_with_path(
            "stale.pdf", is_current=False, is_deleted=True
        )
        success, error = DocumentLifecycleService.restore_document(
            user=self.owner, document_path=document_path
        )
        self.assertFalse(success)
        self.assertIn("not current", error)

    def test_permanently_delete_document_rejects_foreign_document(self):
        document = Document.objects.create(
            title="Foreign", creator=self.owner, pdf_file="foreign.pdf"
        )
        success, error = DocumentLifecycleService.permanently_delete_document(
            user=self.owner, document=document, corpus=self.corpus
        )
        self.assertFalse(success)
        self.assertIn("does not belong", error)

    def test_empty_trash_summarises_partial_errors(self):
        with patch(
            "opencontractserver.documents.versioning."
            "permanently_delete_all_in_trash",
            return_value=(2, ["e1", "e2", "e3", "e4"]),
        ):
            deleted_count, error = DocumentLifecycleService.empty_trash(
                user=self.owner, corpus=self.corpus
            )
        self.assertEqual(deleted_count, 2)
        self.assertIn("with 4 errors", error)
        self.assertIn("and 1 more", error)


class TestCorpusPathServiceCoverage(_SegmentedServiceCoverageBase):
    """Edge branches of ``CorpusPathService`` path helpers."""

    def test_fetch_occupied_paths_rejects_empty_directory(self):
        with self.assertRaises(ValueError):
            CorpusPathService._fetch_occupied_paths_in_directory(self.corpus, "")
