"""Structural tests for the ``corpuses/services/`` package (issue #1716).

Phase 2 of the service-layer centralization roadmap split the ~2,900-line
``corpus_objs_service.py`` monolith into the segmented
``opencontractserver.corpuses.services`` package. The behaviour of every
relocated method is regression-covered, unchanged, by
``test_corpus_objs_service.py``; Corpus-row CRUD is covered by
``test_corpus_service.py``.

This module instead covers the *structural contract* of the package:

1. PACKAGE STRUCTURE — the segmented services exist, are importable, and each
   inherits ``BaseService``.
2. STANDALONE OPERATION — each segmented service works when called directly.
3. CROSS-SERVICE DELEGATION — ``FolderCRUDService`` / ``FolderDocumentService``
   correctly reach helpers that now live on ``CorpusPathService`` /
   ``CorpusDocumentService``.

See ``docs/refactor_plans/2026-05-21-service-layer-phase2-corpus-services-plan.md``
and ``docs/refactor_plans/2026-05-22-service-layer-phase2bc-corpus-service-and-caller-migration.md``.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from opencontractserver.corpuses.models import Corpus, CorpusFolder
from opencontractserver.corpuses.services import (
    CorpusActionService,
    CorpusCategoryService,
    CorpusDocumentService,
    CorpusPathService,
    CorpusService,
    CorpusVoteService,
    DocumentLifecycleService,
    FolderCRUDService,
    FolderDocumentService,
)
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.shared.services.base import BaseService

User = get_user_model()

# The segmented services that make up the corpus service layer.
SEGMENTED_SERVICES = (
    FolderCRUDService,
    FolderDocumentService,
    CorpusDocumentService,
    CorpusService,
    DocumentLifecycleService,
    CorpusPathService,
    CorpusVoteService,
    CorpusActionService,
    CorpusCategoryService,
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
                    "CorpusService",
                    "DocumentLifecycleService",
                    "CorpusPathService",
                    "CorpusVoteService",
                    "CorpusActionService",
                    "CorpusCategoryService",
                    "BatchRunSummary",
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

    def test_corpus_objs_service_shim_is_deleted(self):
        """The deprecated ``corpus_objs_service`` re-export shim is gone.

        Phase 2C deleted ``opencontractserver/corpuses/corpus_objs_service.py``
        and the ``CorpusObjsService`` facade (CLAUDE.md no-dead-code rule).
        Importing it must fail — this pins the deletion so the module cannot
        be silently resurrected.
        """
        with self.assertRaises(ModuleNotFoundError):
            import opencontractserver.corpuses.corpus_objs_service  # noqa: F401

    def test_segmented_services_share_no_method_names(self):
        """The segmented services have disjoint method names.

        Each responsibility lives on exactly one service; a name appearing on
        two services would signal a botched split. Pin the disjointness so a
        future collision fails loudly here.
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
# 3. STANDALONE OPERATION OF EACH SEGMENTED SERVICE
# =============================================================================


class TestFolderCRUDServiceStandalone(TestCase):
    """SCENARIO: ``FolderCRUDService`` is usable directly.

    BUSINESS RULE: code imports and calls the segmented service
    (``FolderCRUDService.create_folder(...)``) directly.
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
    """SCENARIO: ``FolderDocumentService`` is usable directly.

    BUSINESS RULE: document-in-folder placement, lookup, and listing resolve
    through the segmented service. ``FolderDocumentService`` reaches folder-CRUD
    helpers only through explicit sibling-service references, so it works
    standalone — it does not depend on ``FolderCRUDService`` being mixed in.
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
