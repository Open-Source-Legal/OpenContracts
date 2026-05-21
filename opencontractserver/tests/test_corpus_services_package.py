"""Structural tests for the ``corpuses/services/`` package (issue #1716).

Phase 2 of the service-layer centralization roadmap split the ~2,900-line
``corpus_objs_service.py`` monolith into the segmented
``opencontractserver.corpuses.services`` package. The behaviour of every
relocated method is regression-covered, unchanged, by
``test_corpus_objs_service.py`` (which exercises the methods through the
backward-compatible ``CorpusObjsService`` facade).

This module instead covers the *structural contract* of Phase A:

1. PACKAGE STRUCTURE — the four services exist, are importable, and each
   inherits ``BaseService``.
2. SHIM / FACADE — ``CorpusObjsService`` remains importable from its old
   location, aggregates all four services, and adds no behaviour of its own.
3. STANDALONE OPERATION — each segmented service works when called directly,
   without going through the facade (the whole point of the split).
4. CROSS-SERVICE DELEGATION — ``FolderService`` / ``DocumentLifecycleService``
   correctly reach helpers that now live on ``CorpusPathService`` /
   ``CorpusDocumentService``, both standalone and via the facade.

See ``docs/refactor_plans/2026-05-21-service-layer-phase2-corpus-services-plan.md``.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from opencontractserver.corpuses.corpus_objs_service import CorpusObjsService
from opencontractserver.corpuses.models import Corpus, CorpusFolder
from opencontractserver.corpuses.services import (
    CorpusDocumentService,
    CorpusPathService,
    DocumentLifecycleService,
    FolderService,
)
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.shared.services.base import BaseService

User = get_user_model()

# The four segmented services, in the order they are documented in the issue.
SEGMENTED_SERVICES = (
    FolderService,
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

    def test_package_reexports_the_four_services(self):
        from opencontractserver.corpuses import services

        self.assertEqual(
            sorted(services.__all__),
            sorted(
                [
                    "FolderService",
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
        """The facade relies on the four services having disjoint methods.

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
    call working for one release, by multiply-inheriting the four segmented
    services. The facade itself adds no behaviour.
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
        """C3 linearisation succeeds and visits all four services + BaseService."""
        mro = CorpusObjsService.__mro__
        for service in SEGMENTED_SERVICES:
            self.assertIn(service, mro)
        self.assertIn(BaseService, mro)

    def test_shim_module_reexports_the_segmented_services_too(self):
        from opencontractserver.corpuses import corpus_objs_service as shim

        self.assertIs(shim.FolderService, FolderService)
        self.assertIs(shim.CorpusDocumentService, CorpusDocumentService)
        self.assertIs(shim.DocumentLifecycleService, DocumentLifecycleService)
        self.assertIs(shim.CorpusPathService, CorpusPathService)


# =============================================================================
# 3. STANDALONE OPERATION OF EACH SEGMENTED SERVICE
# =============================================================================


class TestFolderServiceStandalone(TestCase):
    """SCENARIO: ``FolderService`` is usable directly, without the facade.

    BUSINESS RULE: new code imports and calls the segmented service
    (``FolderService.create_folder(...)``) — it does not need, and should not
    use, the deprecated ``CorpusObjsService`` facade.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="fs_owner", email="fs_owner@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="FolderService Corpus", creator=self.owner, is_public=False
        )

    def test_create_read_update_delete_folder_directly(self):
        folder, error = FolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Contracts"
        )
        self.assertEqual(error, "")
        self.assertIsNotNone(folder)

        visible = FolderService.get_visible_folders(self.owner, self.corpus.id)
        self.assertIn(folder.id, {f.id for f in visible})

        ok, error = FolderService.update_folder(
            user=self.owner, folder=folder, name="Renamed"
        )
        self.assertTrue(ok)
        folder.refresh_from_db()
        self.assertEqual(folder.name, "Renamed")

        ok, error = FolderService.delete_folder(user=self.owner, folder=folder)
        self.assertTrue(ok)
        self.assertFalse(CorpusFolder.objects.filter(id=folder.id).exists())


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

    BUSINESS RULE: ``FolderService`` move/delete operations delegate path
    disambiguation to ``CorpusPathService`` and membership checks to
    ``CorpusDocumentService`` via explicit class references. The relocation
    must work when ``FolderService`` is used STANDALONE — the explicit
    references do not depend on being reached through the facade.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="xsd_owner", email="xsd_owner@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="CrossService Corpus", creator=self.owner, is_public=False
        )
        self.folder, _ = FolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Target"
        )
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
        """``FolderService.move_document_to_folder`` -> ``CorpusPathService``."""
        ok, error = FolderService.move_document_to_folder(
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
        """``FolderService.move_documents_to_folder`` disambiguates paths via
        ``CorpusPathService`` even though the two now live in separate
        modules."""
        doc_ids = [d.id for d in self.documents]
        moved, error = FolderService.move_documents_to_folder(
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
        """``FolderService.delete_folder`` displaces documents to root via the
        ``CorpusPathService`` disambiguation helpers."""
        FolderService.move_documents_to_folder(
            user=self.owner,
            document_ids=[d.id for d in self.documents],
            corpus=self.corpus,
            folder=self.folder,
        )
        ok, error = FolderService.delete_folder(user=self.owner, folder=self.folder)
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
        via_service, service_err = FolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="ViaService"
        )
        self.assertEqual(facade_err, "")
        self.assertEqual(service_err, "")
        self.assertEqual(via_facade.corpus_id, via_service.corpus_id)
        self.assertEqual(type(via_facade), type(via_service))

    def test_bulk_move_via_facade_matches_segmented_service(self):
        """A cross-module operation (bulk move -> path disambiguation) behaves
        identically whether dispatched through the facade or the service."""
        folder, _ = FolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Dest"
        )
        results = {}
        for label, entrypoint in (
            ("facade", CorpusObjsService),
            ("service", FolderService),
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
