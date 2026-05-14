"""
Comprehensive tests for DocumentFolderService.

This test suite is organized into human-readable scenario groups:

1. PERMISSION SCENARIOS - Validates all permission checks work correctly
2. FOLDER CRUD SCENARIOS - Tests folder create, read, update, delete operations
3. FOLDER HIERARCHY SCENARIOS - Tests nested folders, moves, and circular reference prevention
4. DOCUMENT-IN-FOLDER SCENARIOS - Tests moving documents between folders
5. VERSIONING SCENARIOS - Tests DocumentPath versioning (soft delete, restore, version chains)
6. CORPUS ISOLATION SCENARIOS - Tests that adding documents creates isolated copies
7. EDGE CASES AND ERROR HANDLING - Tests boundary conditions and error states

Each test is named descriptively to serve as documentation of expected behavior.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.db import IntegrityError
from django.test import TransactionTestCase

from opencontractserver.constants.document_processing import (
    MAX_PATH_CREATE_RETRIES,
    MAX_PATH_DISAMBIGUATION_SUFFIX,
    PATH_CONFLICT_MSG,
)
from opencontractserver.corpuses.folder_service import DocumentFolderService
from opencontractserver.corpuses.models import (
    Corpus,
    CorpusFolder,
)
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


def _make_constraint_error(
    message: str = "unique_active_path_per_corpus",
) -> IntegrityError:
    """Create an IntegrityError that mimics real Django/psycopg2 constraint violations.

    Production IntegrityErrors from psycopg2 have a ``__cause__`` with a
    ``pgcode`` attribute (``"23505"`` for UniqueViolation).  The service
    layer's ``_create_successor_path_with_retry`` guards on this pgcode
    before retrying, so test mocks must chain the cause correctly.
    """
    cause = Exception()
    cause.pgcode = "23505"  # PostgreSQL UniqueViolation
    exc = IntegrityError(message)
    exc.__cause__ = cause
    return exc


# =============================================================================
# BASE TEST CLASS - Disconnects signals to prevent Celery tasks
# =============================================================================


class DocumentFolderServiceTestBase(TransactionTestCase):
    """
    Base test class for document folder service tests.

    Note: Signal management is handled globally by conftest.py fixture
    `disable_document_processing_signals` - no need to disconnect/reconnect here.
    """

    def _get_current_path(self, document=None):
        """Helper to get the current active DocumentPath for a document."""
        doc = document or self.document
        return DocumentPath.objects.get(
            document=doc, corpus=self.corpus, is_current=True, is_deleted=False
        )


# =============================================================================
# 1. PERMISSION SCENARIOS
# =============================================================================


class TestPermission_CorpusCreatorHasFullAccess(TransactionTestCase):
    """
    SCENARIO: Corpus creator should have full read, write, and delete access.

    BUSINESS RULE: The user who creates a corpus owns it and has unrestricted access.
    """

    def setUp(self):
        self.creator = User.objects.create_user(
            username="creator", email="creator@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="My Corpus", creator=self.creator, is_public=False
        )

    def test_creator_can_read_corpus(self):
        """Creator should have READ permission on their corpus."""
        self.assertTrue(self.corpus.user_can(self.creator, PermissionTypes.READ))

    def test_creator_can_write_to_corpus(self):
        """Creator should have WRITE (UPDATE) permission on their corpus."""
        self.assertTrue(self.corpus.user_can(self.creator, PermissionTypes.UPDATE))

    def test_creator_can_delete_from_corpus(self):
        """Creator should have DELETE permission on their corpus."""
        self.assertTrue(self.corpus.user_can(self.creator, PermissionTypes.DELETE))


class TestPermission_SuperuserBypassesAllChecks(TransactionTestCase):
    """
    SCENARIO: Superusers should have all permissions on any corpus.

    BUSINESS RULE: Superusers are system administrators with unrestricted access.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.superuser = User.objects.create_superuser(
            username="admin", email="admin@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Private Corpus", creator=self.owner, is_public=False
        )

    def test_superuser_can_read_any_corpus(self):
        """Superuser should have READ permission on any corpus."""
        self.assertTrue(self.corpus.user_can(self.superuser, PermissionTypes.READ))

    def test_superuser_can_write_to_any_corpus(self):
        """Superuser should have WRITE permission on any corpus."""
        self.assertTrue(self.corpus.user_can(self.superuser, PermissionTypes.UPDATE))

    def test_superuser_can_delete_from_any_corpus(self):
        """Superuser should have DELETE permission on any corpus."""
        self.assertTrue(self.corpus.user_can(self.superuser, PermissionTypes.DELETE))


class TestPermission_PublicCorpusGrantsReadOnly(TransactionTestCase):
    """
    SCENARIO: Public corpus should grant read-only access to everyone.

    BUSINESS RULE: is_public=True allows anyone to VIEW but NOT modify.
    This is a SECURITY-CRITICAL rule to prevent unauthorized modifications.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.random_user = User.objects.create_user(
            username="random", email="random@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Public Corpus", creator=self.owner, is_public=True
        )

    def test_random_user_can_read_public_corpus(self):
        """Any authenticated user should be able to READ a public corpus."""
        self.assertTrue(self.corpus.user_can(self.random_user, PermissionTypes.READ))

    def test_random_user_cannot_write_to_public_corpus(self):
        """
        SECURITY: Users without explicit permission CANNOT write to public corpus.
        Public means readable, NOT editable.
        """
        self.assertFalse(self.corpus.user_can(self.random_user, PermissionTypes.UPDATE))

    def test_random_user_cannot_delete_from_public_corpus(self):
        """
        SECURITY: Users without explicit permission CANNOT delete from public corpus.
        """
        self.assertFalse(self.corpus.user_can(self.random_user, PermissionTypes.DELETE))


class TestPermission_ExplicitPermissionsViaGuardian(TransactionTestCase):
    """
    SCENARIO: Users can be granted specific permissions via django-guardian.

    BUSINESS RULE: Permissions can be granted at granular level (READ, UPDATE, DELETE).
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.reader = User.objects.create_user(
            username="reader", email="reader@test.com", password="test"
        )
        self.editor = User.objects.create_user(
            username="editor", email="editor@test.com", password="test"
        )
        self.deleter = User.objects.create_user(
            username="deleter", email="deleter@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Private Corpus", creator=self.owner, is_public=False
        )

    def test_explicit_read_permission_grants_read_access(self):
        """User with explicit READ permission can read the corpus."""
        set_permissions_for_obj_to_user(
            self.reader, self.corpus, [PermissionTypes.READ]
        )

        self.assertTrue(self.corpus.user_can(self.reader, PermissionTypes.READ))

    def test_explicit_read_permission_does_not_grant_write_access(self):
        """User with only READ permission CANNOT write."""
        set_permissions_for_obj_to_user(
            self.reader, self.corpus, [PermissionTypes.READ]
        )

        self.assertFalse(self.corpus.user_can(self.reader, PermissionTypes.UPDATE))

    def test_explicit_update_permission_grants_write_access(self):
        """User with explicit UPDATE permission can write to the corpus."""
        set_permissions_for_obj_to_user(
            self.editor, self.corpus, [PermissionTypes.UPDATE]
        )

        self.assertTrue(self.corpus.user_can(self.editor, PermissionTypes.UPDATE))

    def test_explicit_delete_permission_grants_delete_access(self):
        """User with explicit DELETE permission can delete from the corpus."""
        set_permissions_for_obj_to_user(
            self.deleter, self.corpus, [PermissionTypes.DELETE]
        )

        self.assertTrue(self.corpus.user_can(self.deleter, PermissionTypes.DELETE))


class TestPermission_NoAccessDeniesEverything(TransactionTestCase):
    """
    SCENARIO: User with no permissions should be denied all access.

    BUSINESS RULE: Default is deny-all for private corpuses.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.stranger = User.objects.create_user(
            username="stranger", email="stranger@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Private Corpus", creator=self.owner, is_public=False
        )

    def test_stranger_cannot_read_private_corpus(self):
        """User without any permission cannot read private corpus."""
        self.assertFalse(self.corpus.user_can(self.stranger, PermissionTypes.READ))

    def test_stranger_cannot_write_to_private_corpus(self):
        """User without any permission cannot write to private corpus."""
        self.assertFalse(self.corpus.user_can(self.stranger, PermissionTypes.UPDATE))

    def test_stranger_cannot_delete_from_private_corpus(self):
        """User without any permission cannot delete from private corpus."""
        self.assertFalse(self.corpus.user_can(self.stranger, PermissionTypes.DELETE))


class TestPermission_AnonymousUserAccess(TransactionTestCase):
    """
    SCENARIO: Anonymous users should only access public resources.

    BUSINESS RULE: Unauthenticated users can view public corpuses but never modify anything.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.anonymous = AnonymousUser()
        self.public_corpus = Corpus.objects.create(
            title="Public Corpus", creator=self.owner, is_public=True
        )
        self.private_corpus = Corpus.objects.create(
            title="Private Corpus", creator=self.owner, is_public=False
        )

    def test_anonymous_can_read_public_corpus(self):
        """Anonymous user can read public corpus."""
        self.assertTrue(
            self.public_corpus.user_can(self.anonymous, PermissionTypes.READ)
        )

    def test_anonymous_cannot_read_private_corpus(self):
        """Anonymous user cannot read private corpus."""
        self.assertFalse(
            self.private_corpus.user_can(self.anonymous, PermissionTypes.READ)
        )

    def test_anonymous_cannot_write_to_public_corpus(self):
        """SECURITY: Anonymous user CANNOT write even to public corpus."""
        self.assertFalse(
            self.public_corpus.user_can(self.anonymous, PermissionTypes.UPDATE)
        )

    def test_anonymous_cannot_delete_from_public_corpus(self):
        """SECURITY: Anonymous user CANNOT delete even from public corpus."""
        self.assertFalse(
            self.public_corpus.user_can(self.anonymous, PermissionTypes.DELETE)
        )


# =============================================================================
# 2. FOLDER CRUD SCENARIOS
# =============================================================================


class TestFolderCreate_BasicOperations(TransactionTestCase):
    """
    SCENARIO: Creating folders in a corpus.

    BUSINESS RULE: Users with WRITE permission can create folders.
    Folder names must be unique within the same parent.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.owner, is_public=False
        )

    def test_create_folder_at_root_level(self):
        """Owner can create a folder at corpus root."""
        folder, error = DocumentFolderService.create_folder(
            user=self.owner,
            corpus=self.corpus,
            name="Contracts",
            description="Legal contracts",
            color="#3B82F6",
            icon="folder",
        )

        self.assertIsNotNone(folder)
        self.assertEqual(error, "")
        self.assertEqual(folder.name, "Contracts")
        self.assertEqual(folder.description, "Legal contracts")
        self.assertEqual(folder.color, "#3B82F6")
        self.assertEqual(folder.corpus, self.corpus)
        self.assertIsNone(folder.parent)  # Root level

    def test_create_folder_preserves_all_metadata(self):
        """Folder should preserve all provided metadata (tags, icon, etc)."""
        folder, error = DocumentFolderService.create_folder(
            user=self.owner,
            corpus=self.corpus,
            name="Tagged Folder",
            description="Has tags",
            color="#FF0000",
            icon="star",
            tags=["important", "legal", "2024"],
        )

        self.assertIsNotNone(folder)
        self.assertEqual(folder.icon, "star")
        self.assertEqual(folder.tags, ["important", "legal", "2024"])

    def test_create_folder_with_duplicate_name_fails(self):
        """Cannot create two folders with same name at same level."""
        DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Duplicates"
        )

        folder, error = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Duplicates"
        )

        self.assertIsNone(folder)
        self.assertIn("already exists", error)

    def test_create_folder_without_write_permission_fails(self):
        """User without WRITE permission cannot create folders."""
        reader = User.objects.create_user(
            username="reader", email="reader@test.com", password="test"
        )
        set_permissions_for_obj_to_user(reader, self.corpus, [PermissionTypes.READ])

        folder, error = DocumentFolderService.create_folder(
            user=reader, corpus=self.corpus, name="Unauthorized"
        )

        self.assertIsNone(folder)
        self.assertIn("Permission denied", error)


class TestFolderUpdate_BasicOperations(TransactionTestCase):
    """
    SCENARIO: Updating folder properties.

    BUSINESS RULE: Users with WRITE permission can update folder metadata.
    Name changes must not conflict with siblings.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.owner, is_public=False
        )
        self.folder, _ = DocumentFolderService.create_folder(
            user=self.owner,
            corpus=self.corpus,
            name="Original Name",
            description="Original description",
            color="#000000",
        )

    def test_update_folder_name(self):
        """Owner can rename a folder."""
        success, error = DocumentFolderService.update_folder(
            user=self.owner, folder=self.folder, name="New Name"
        )

        self.assertTrue(success)
        self.assertEqual(error, "")
        self.folder.refresh_from_db()
        self.assertEqual(self.folder.name, "New Name")

    def test_update_folder_preserves_unchanged_fields(self):
        """Updating one field should not affect others."""
        original_description = self.folder.description
        original_color = self.folder.color

        success, error = DocumentFolderService.update_folder(
            user=self.owner, folder=self.folder, name="Changed Name Only"
        )

        self.assertTrue(success)
        self.folder.refresh_from_db()
        self.assertEqual(self.folder.name, "Changed Name Only")
        self.assertEqual(self.folder.description, original_description)
        self.assertEqual(self.folder.color, original_color)

    def test_update_folder_multiple_fields_at_once(self):
        """Can update multiple fields in single operation."""
        success, error = DocumentFolderService.update_folder(
            user=self.owner,
            folder=self.folder,
            name="Fully Updated",
            description="New description",
            color="#FF0000",
            icon="star",
            tags=["new", "tags"],
        )

        self.assertTrue(success)
        self.folder.refresh_from_db()
        self.assertEqual(self.folder.name, "Fully Updated")
        self.assertEqual(self.folder.description, "New description")
        self.assertEqual(self.folder.color, "#FF0000")
        self.assertEqual(self.folder.icon, "star")
        self.assertEqual(self.folder.tags, ["new", "tags"])

    def test_update_folder_name_conflict_with_sibling_fails(self):
        """Cannot rename to a name that conflicts with sibling folder."""
        DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Existing Sibling"
        )

        success, error = DocumentFolderService.update_folder(
            user=self.owner, folder=self.folder, name="Existing Sibling"
        )

        self.assertFalse(success)
        self.assertIn("already exists", error)


class TestFolderDelete_BasicOperations(DocumentFolderServiceTestBase):
    """
    SCENARIO: Deleting folders from a corpus.

    BUSINESS RULE: Users with DELETE permission can delete folders.
    Documents in deleted folders are moved to root.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.owner, is_public=False
        )

    def test_delete_empty_folder(self):
        """Owner can delete an empty folder."""
        folder, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="To Delete"
        )
        folder_id = folder.id

        success, error = DocumentFolderService.delete_folder(
            user=self.owner, folder=folder
        )

        self.assertTrue(success)
        self.assertEqual(error, "")
        self.assertFalse(CorpusFolder.objects.filter(id=folder_id).exists())

    def test_delete_folder_reparents_child_folders(self):
        """When deleting folder, child folders are reparented to grandparent."""
        parent, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Parent"
        )
        child, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Child", parent=parent
        )
        grandchild, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Grandchild", parent=child
        )

        # Delete the middle folder (Child)
        success, error = DocumentFolderService.delete_folder(
            user=self.owner, folder=child, move_children_to_parent=True
        )

        self.assertTrue(success)
        grandchild.refresh_from_db()
        self.assertEqual(grandchild.parent, parent)  # Now child of Parent

    def test_delete_folder_moves_documents_to_root(self):
        """Documents in deleted folder are moved to corpus root with history."""
        folder, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Folder With Docs"
        )

        # Create document and put it in folder
        document = Document.objects.create(
            title="Test Doc", creator=self.owner, pdf_file="test.pdf"
        )
        original_path = DocumentPath.objects.create(
            document=document,
            corpus=self.corpus,
            creator=self.owner,
            folder=folder,
            path="/Folder With Docs/test.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        # Delete the folder
        DocumentFolderService.delete_folder(user=self.owner, folder=folder)

        # Document should now have no folder (at root) via a new path record
        current = DocumentPath.objects.get(
            document=document, corpus=self.corpus, is_current=True, is_deleted=False
        )
        self.assertIsNone(current.folder)
        # Should be linked to original via parent (history chain)
        self.assertEqual(current.parent_id, original_path.id)
        # Original should no longer be current
        original_path.refresh_from_db()
        self.assertFalse(original_path.is_current)

    def test_delete_folder_disambiguates_same_filename_from_subfolders(self):
        """Two documents in different sub-paths under the same folder
        share the same root filename (report.pdf). When the folder is
        deleted both are relocated to root; the second should be
        disambiguated (e.g. /report_1.pdf).

        This exercises the batch disambiguation in delete_folder: all
        candidate paths are resolved in-memory against a single
        pre-fetched occupancy snapshot, with each newly-claimed path
        added to the shared set so siblings in the same batch get
        unique suffixes.
        """
        folder, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="MyFolder"
        )

        # Two documents whose paths differ (satisfying the DB unique
        # constraint) but share the same leaf filename.  Both belong
        # to the same folder FK, simulating documents that were
        # originally in different sub-directories.
        doc_a = Document.objects.create(
            title="Report A", creator=self.owner, pdf_file="report.pdf"
        )
        path_a = DocumentPath.objects.create(
            document=doc_a,
            corpus=self.corpus,
            creator=self.owner,
            folder=folder,
            path="/MyFolder/SubA/report.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        doc_b = Document.objects.create(
            title="Report B", creator=self.owner, pdf_file="report.pdf"
        )
        path_b = DocumentPath.objects.create(
            document=doc_b,
            corpus=self.corpus,
            creator=self.owner,
            folder=folder,
            path="/MyFolder/SubB/report.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        # Delete the folder — both docs should move to root
        success, error = DocumentFolderService.delete_folder(
            user=self.owner, folder=folder
        )

        self.assertTrue(success, f"delete_folder failed: {error}")

        # Both documents should now be at root with unique paths
        current_a = DocumentPath.objects.get(
            document=doc_a, corpus=self.corpus, is_current=True, is_deleted=False
        )
        current_b = DocumentPath.objects.get(
            document=doc_b, corpus=self.corpus, is_current=True, is_deleted=False
        )

        # Both should be at root (no folder)
        self.assertIsNone(current_a.folder)
        self.assertIsNone(current_b.folder)

        # Paths should be distinct — one keeps the original name, the other
        # gets a disambiguation suffix
        paths = {current_a.path, current_b.path}
        self.assertEqual(len(paths), 2, "Both paths should be unique")
        self.assertIn("/report.pdf", paths)
        self.assertIn("/report_1.pdf", paths)

        # Verify history chain
        self.assertEqual(current_a.parent_id, path_a.id)
        self.assertEqual(current_b.parent_id, path_b.id)

    def test_delete_folder_without_permission_fails(self):
        """User without DELETE permission cannot delete folder."""
        reader = User.objects.create_user(
            username="reader", email="reader@test.com", password="test"
        )
        set_permissions_for_obj_to_user(reader, self.corpus, [PermissionTypes.READ])

        folder, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Protected"
        )

        success, error = DocumentFolderService.delete_folder(user=reader, folder=folder)

        self.assertFalse(success)
        self.assertIn("Permission denied", error)


# =============================================================================
# 3. FOLDER HIERARCHY SCENARIOS
# =============================================================================


class TestFolderHierarchy_NestedFolders(TransactionTestCase):
    """
    SCENARIO: Creating and navigating nested folder structures.

    BUSINESS RULE: Folders can be nested to any depth.
    Same names are allowed in different parents.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.owner, is_public=False
        )

    def test_create_deeply_nested_folder_structure(self):
        """Can create folders nested multiple levels deep."""
        level1, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Level 1"
        )
        level2, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Level 2", parent=level1
        )
        level3, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Level 3", parent=level2
        )
        level4, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Level 4", parent=level3
        )

        self.assertEqual(level4.parent, level3)
        self.assertEqual(level3.parent, level2)
        self.assertEqual(level2.parent, level1)
        self.assertIsNone(level1.parent)

    def test_same_name_allowed_in_different_parents(self):
        """Two folders can have same name if in different parents."""
        parent_a, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Parent A"
        )
        parent_b, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Parent B"
        )

        child_in_a, error_a = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Documents", parent=parent_a
        )
        child_in_b, error_b = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Documents", parent=parent_b
        )

        self.assertIsNotNone(child_in_a)
        self.assertIsNotNone(child_in_b)
        self.assertEqual(child_in_a.name, child_in_b.name)
        self.assertNotEqual(child_in_a.parent, child_in_b.parent)

    def test_get_folder_tree_returns_nested_structure(self):
        """get_folder_tree() returns properly nested structure."""
        parent, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Root Folder"
        )
        child, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Child Folder", parent=parent
        )

        tree = DocumentFolderService.get_folder_tree(
            user=self.owner, corpus_id=self.corpus.id
        )

        self.assertEqual(len(tree), 1)  # One root folder
        self.assertEqual(tree[0]["name"], "Root Folder")
        self.assertEqual(len(tree[0]["children"]), 1)
        self.assertEqual(tree[0]["children"][0]["name"], "Child Folder")


class TestFolderHierarchy_MovePreventsCircularReferences(TransactionTestCase):
    """
    SCENARIO: Moving folders must prevent circular references.

    BUSINESS RULE: A folder cannot be moved into itself or any of its descendants.
    This would create an infinite loop in the folder tree.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.owner, is_public=False
        )
        # Create hierarchy: Parent -> Child -> Grandchild
        self.parent, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Parent"
        )
        self.child, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Child", parent=self.parent
        )
        self.grandchild, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Grandchild", parent=self.child
        )

    def test_cannot_move_folder_into_itself(self):
        """Moving folder into itself should fail."""
        success, error = DocumentFolderService.move_folder(
            user=self.owner, folder=self.parent, new_parent=self.parent
        )

        self.assertFalse(success)
        self.assertIn("itself", error.lower())

    def test_cannot_move_folder_into_direct_child(self):
        """Moving folder into its direct child should fail."""
        success, error = DocumentFolderService.move_folder(
            user=self.owner, folder=self.parent, new_parent=self.child
        )

        self.assertFalse(success)
        self.assertIn("descendant", error.lower())

    def test_cannot_move_folder_into_grandchild(self):
        """Moving folder into its grandchild should fail."""
        success, error = DocumentFolderService.move_folder(
            user=self.owner, folder=self.parent, new_parent=self.grandchild
        )

        self.assertFalse(success)
        self.assertIn("descendant", error.lower())

    def test_can_move_folder_to_unrelated_folder(self):
        """Moving folder to an unrelated folder should succeed."""
        unrelated, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Unrelated"
        )

        success, error = DocumentFolderService.move_folder(
            user=self.owner, folder=self.grandchild, new_parent=unrelated
        )

        self.assertTrue(success)
        self.grandchild.refresh_from_db()
        self.assertEqual(self.grandchild.parent, unrelated)

    def test_can_move_folder_to_root(self):
        """Moving nested folder to root should succeed."""
        success, error = DocumentFolderService.move_folder(
            user=self.owner, folder=self.grandchild, new_parent=None
        )

        self.assertTrue(success)
        self.grandchild.refresh_from_db()
        self.assertIsNone(self.grandchild.parent)


class TestFolderHierarchy_CrossCorpusMovePrevented(TransactionTestCase):
    """
    SCENARIO: Folders cannot be moved between different corpuses.

    BUSINESS RULE: Folder hierarchy is contained within a single corpus.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.corpus_a = Corpus.objects.create(
            title="Corpus A", creator=self.owner, is_public=False
        )
        self.corpus_b = Corpus.objects.create(
            title="Corpus B", creator=self.owner, is_public=False
        )
        self.folder_in_a, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus_a, name="Folder in A"
        )
        self.folder_in_b, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus_b, name="Folder in B"
        )

    def test_cannot_move_folder_to_different_corpus(self):
        """Moving folder to parent in different corpus should fail."""
        success, error = DocumentFolderService.move_folder(
            user=self.owner, folder=self.folder_in_a, new_parent=self.folder_in_b
        )

        self.assertFalse(success)
        self.assertIn("different corpus", error.lower())


# =============================================================================
# 4. DOCUMENT-IN-FOLDER SCENARIOS
# =============================================================================


class TestDocumentInFolder_MoveOperations(DocumentFolderServiceTestBase):
    """
    SCENARIO: Moving documents between folders.

    BUSINESS RULE: Documents can be moved between folders within same corpus.
    DocumentPath is updated to reflect the new folder assignment.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.owner, is_public=False
        )
        self.folder_a, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Folder A"
        )
        self.folder_b, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Folder B"
        )
        # Create document at root
        self.document = Document.objects.create(
            title="Test Document", creator=self.owner, pdf_file="test.pdf"
        )
        self.document_path = DocumentPath.objects.create(
            document=self.document,
            corpus=self.corpus,
            creator=self.owner,
            folder=None,  # At root
            path="/test.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

    def test_move_document_from_root_to_folder(self):
        """Can move document from corpus root into a folder."""
        success, error = DocumentFolderService.move_document_to_folder(
            user=self.owner,
            document=self.document,
            corpus=self.corpus,
            folder=self.folder_a,
        )

        self.assertTrue(success)
        current = self._get_current_path()
        self.assertEqual(current.folder, self.folder_a)
        # Original path should no longer be current
        self.document_path.refresh_from_db()
        self.assertFalse(self.document_path.is_current)
        # New path should be linked to original via parent
        self.assertEqual(current.parent_id, self.document_path.id)

    def test_move_document_between_folders(self):
        """Can move document from one folder to another."""
        # First move to folder A
        DocumentFolderService.move_document_to_folder(
            user=self.owner,
            document=self.document,
            corpus=self.corpus,
            folder=self.folder_a,
        )

        # Then move to folder B
        success, error = DocumentFolderService.move_document_to_folder(
            user=self.owner,
            document=self.document,
            corpus=self.corpus,
            folder=self.folder_b,
        )

        self.assertTrue(success)
        current = self._get_current_path()
        self.assertEqual(current.folder, self.folder_b)
        # Should have 3 path records total (original + 2 moves)
        total = DocumentPath.objects.filter(
            document=self.document, corpus=self.corpus
        ).count()
        self.assertEqual(total, 3)

    def test_move_document_from_folder_to_root(self):
        """Can move document from folder back to corpus root."""
        # First move to folder
        DocumentFolderService.move_document_to_folder(
            user=self.owner,
            document=self.document,
            corpus=self.corpus,
            folder=self.folder_a,
        )

        # Then move to root
        success, error = DocumentFolderService.move_document_to_folder(
            user=self.owner,
            document=self.document,
            corpus=self.corpus,
            folder=None,  # Root
        )

        self.assertTrue(success)
        current = self._get_current_path()
        self.assertIsNone(current.folder)

        # Verify full parent chain: root(original) -> folder_a -> root(current)
        self.assertIsNotNone(current.parent)
        mid = current.parent
        self.assertEqual(mid.folder, self.folder_a)
        self.assertIsNotNone(mid.parent)
        original = mid.parent
        self.assertIsNone(original.folder)
        self.assertIsNone(original.parent)

    def test_move_document_path_reflects_folder(self):
        """Moving a document updates the path string to reflect the folder."""
        success, error = DocumentFolderService.move_document_to_folder(
            user=self.owner,
            document=self.document,
            corpus=self.corpus,
            folder=self.folder_a,
        )

        self.assertTrue(success)
        current = self._get_current_path()
        self.assertEqual(current.path, "/Folder A/test.pdf")

    def test_move_document_preserves_version_number(self):
        """Moving a document does NOT increment the version number.

        Per path tree rule P5 (see versioning.py), version_number increments
        only on content changes, not folder moves.
        """
        original_version = self.document_path.version_number

        DocumentFolderService.move_document_to_folder(
            user=self.owner,
            document=self.document,
            corpus=self.corpus,
            folder=self.folder_a,
        )

        current = self._get_current_path()
        self.assertEqual(current.version_number, original_version)

    def test_move_to_same_folder_is_noop(self):
        """Moving to the folder the doc is already in creates no new record."""
        initial_count = DocumentPath.objects.filter(
            document=self.document, corpus=self.corpus
        ).count()

        success, error = DocumentFolderService.move_document_to_folder(
            user=self.owner,
            document=self.document,
            corpus=self.corpus,
            folder=None,  # Already at root
        )

        self.assertTrue(success)
        final_count = DocumentPath.objects.filter(
            document=self.document, corpus=self.corpus
        ).count()
        self.assertEqual(initial_count, final_count)

    def test_bulk_move_multiple_documents(self):
        """Can bulk move multiple documents at once."""
        doc2 = Document.objects.create(
            title="Doc 2", creator=self.owner, pdf_file="test2.pdf"
        )
        doc3 = Document.objects.create(
            title="Doc 3", creator=self.owner, pdf_file="test3.pdf"
        )
        DocumentPath.objects.create(
            document=doc2,
            corpus=self.corpus,
            creator=self.owner,
            folder=None,
            path="/test2.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )
        DocumentPath.objects.create(
            document=doc3,
            corpus=self.corpus,
            creator=self.owner,
            folder=None,
            path="/test3.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        moved_count, error = DocumentFolderService.move_documents_to_folder(
            user=self.owner,
            document_ids=[self.document.id, doc2.id, doc3.id],
            corpus=self.corpus,
            folder=self.folder_a,
        )

        self.assertEqual(moved_count, 3)
        self.assertEqual(error, "")

        # Verify all are in folder A
        count_in_folder = DocumentPath.objects.filter(
            corpus=self.corpus, folder=self.folder_a, is_current=True, is_deleted=False
        ).count()
        self.assertEqual(count_in_folder, 3)


class TestDocumentInFolder_PermissionEnforcement(DocumentFolderServiceTestBase):
    """
    SCENARIO: Document move operations require proper permissions.

    BUSINESS RULE: Only users with WRITE permission can move documents.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.reader = User.objects.create_user(
            username="reader", email="reader@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.owner, is_public=False
        )
        set_permissions_for_obj_to_user(
            self.reader, self.corpus, [PermissionTypes.READ]
        )

        self.folder, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Folder"
        )
        self.document = Document.objects.create(
            title="Test Doc", creator=self.owner, pdf_file="test.pdf"
        )
        DocumentPath.objects.create(
            document=self.document,
            corpus=self.corpus,
            creator=self.owner,
            folder=None,
            path="/test.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

    def test_reader_cannot_move_document(self):
        """User with only READ permission cannot move documents."""
        success, error = DocumentFolderService.move_document_to_folder(
            user=self.reader,
            document=self.document,
            corpus=self.corpus,
            folder=self.folder,
        )

        self.assertFalse(success)
        self.assertIn("Permission denied", error)


# =============================================================================
# 5. VERSIONING SCENARIOS
# =============================================================================


class TestVersioning_SoftDeleteCreatesNewPath(DocumentFolderServiceTestBase):
    """
    SCENARIO: Soft delete creates new DocumentPath with is_deleted=True.

    BUSINESS RULE: Every lifecycle event creates a new DocumentPath node
    (path tree rule P1, see versioning.py). This maintains complete
    history and enables undo/restore.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.owner, is_public=False
        )
        self.document = Document.objects.create(
            title="Test Document", creator=self.owner, pdf_file="test.pdf"
        )
        self.original_path = DocumentPath.objects.create(
            document=self.document,
            corpus=self.corpus,
            creator=self.owner,
            folder=None,
            path="/test.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

    def test_soft_delete_marks_original_as_not_current(self):
        """Original path should be marked as is_current=False after delete."""
        DocumentFolderService.soft_delete_document(
            user=self.owner, document=self.document, corpus=self.corpus
        )

        self.original_path.refresh_from_db()
        self.assertFalse(self.original_path.is_current)

    def test_soft_delete_creates_new_deleted_path(self):
        """Soft delete creates new DocumentPath with is_deleted=True."""
        DocumentFolderService.soft_delete_document(
            user=self.owner, document=self.document, corpus=self.corpus
        )

        deleted_path = DocumentPath.objects.get(
            document=self.document, corpus=self.corpus, is_current=True
        )
        self.assertTrue(deleted_path.is_deleted)

    def test_soft_delete_new_path_has_parent_chain(self):
        """New deleted path should have parent pointing to original path."""
        DocumentFolderService.soft_delete_document(
            user=self.owner, document=self.document, corpus=self.corpus
        )

        deleted_path = DocumentPath.objects.get(
            document=self.document, corpus=self.corpus, is_current=True
        )
        self.assertEqual(deleted_path.parent, self.original_path)

    def test_soft_delete_preserves_version_number(self):
        """Version number should be preserved in deleted path."""
        original_version = self.original_path.version_number

        DocumentFolderService.soft_delete_document(
            user=self.owner, document=self.document, corpus=self.corpus
        )

        deleted_path = DocumentPath.objects.get(
            document=self.document, corpus=self.corpus, is_current=True
        )
        self.assertEqual(deleted_path.version_number, original_version)


class TestVersioning_RestoreCreatesNewPath(DocumentFolderServiceTestBase):
    """
    SCENARIO: Restore creates new DocumentPath with is_deleted=False.

    BUSINESS RULE: Restoring a document creates another node in the version chain,
    maintaining audit trail of delete -> restore operations.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.owner, is_public=False
        )
        self.document = Document.objects.create(
            title="Test Document", creator=self.owner, pdf_file="test.pdf"
        )
        self.original_path = DocumentPath.objects.create(
            document=self.document,
            corpus=self.corpus,
            creator=self.owner,
            folder=None,
            path="/test.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )
        # Soft delete the document first
        DocumentFolderService.soft_delete_document(
            user=self.owner, document=self.document, corpus=self.corpus
        )
        self.deleted_path = DocumentPath.objects.get(
            document=self.document, corpus=self.corpus, is_current=True
        )

    def test_restore_marks_deleted_path_as_not_current(self):
        """Deleted path should be marked as is_current=False after restore."""
        DocumentFolderService.restore_document(
            user=self.owner, document_path=self.deleted_path
        )

        self.deleted_path.refresh_from_db()
        self.assertFalse(self.deleted_path.is_current)

    def test_restore_creates_new_active_path(self):
        """Restore creates new DocumentPath with is_deleted=False."""
        DocumentFolderService.restore_document(
            user=self.owner, document_path=self.deleted_path
        )

        restored_path = DocumentPath.objects.get(
            document=self.document, corpus=self.corpus, is_current=True
        )
        self.assertFalse(restored_path.is_deleted)

    def test_restore_new_path_has_parent_chain(self):
        """Restored path should have parent pointing to deleted path."""
        DocumentFolderService.restore_document(
            user=self.owner, document_path=self.deleted_path
        )

        restored_path = DocumentPath.objects.get(
            document=self.document, corpus=self.corpus, is_current=True
        )
        self.assertEqual(restored_path.parent, self.deleted_path)

    def test_full_version_chain_after_delete_and_restore(self):
        """
        After delete and restore, we should have a 3-node chain:
        original -> deleted -> restored
        """
        DocumentFolderService.restore_document(
            user=self.owner, document_path=self.deleted_path
        )

        # Get all paths for this document in corpus
        paths = DocumentPath.objects.filter(
            document=self.document, corpus=self.corpus
        ).order_by("created")

        self.assertEqual(paths.count(), 3)

        # Verify chain
        original = paths[0]
        deleted = paths[1]
        restored = paths[2]

        self.assertIsNone(original.parent)
        self.assertEqual(deleted.parent, original)
        self.assertEqual(restored.parent, deleted)

        # Verify states
        self.assertFalse(original.is_current)
        self.assertFalse(deleted.is_current)
        self.assertTrue(restored.is_current)

        self.assertFalse(original.is_deleted)
        self.assertTrue(deleted.is_deleted)
        self.assertFalse(restored.is_deleted)


class TestVersioning_DeletedDocumentsQueryable(DocumentFolderServiceTestBase):
    """
    SCENARIO: Soft-deleted documents should be queryable for "trash" view.

    BUSINESS RULE: Users can see and restore deleted documents.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.owner, is_public=False
        )
        # Create and delete multiple documents
        for i in range(3):
            doc = Document.objects.create(
                title=f"Deleted Doc {i}", creator=self.owner, pdf_file=f"deleted{i}.pdf"
            )
            DocumentPath.objects.create(
                document=doc,
                corpus=self.corpus,
                creator=self.owner,
                folder=None,
                path=f"/deleted{i}.pdf",
                version_number=1,
                is_current=True,
                is_deleted=False,
            )
            DocumentFolderService.soft_delete_document(
                user=self.owner, document=doc, corpus=self.corpus
            )

        # Create one active document (not deleted)
        self.active_doc = Document.objects.create(
            title="Active Doc", creator=self.owner, pdf_file="active.pdf"
        )
        DocumentPath.objects.create(
            document=self.active_doc,
            corpus=self.corpus,
            creator=self.owner,
            folder=None,
            path="/active.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

    def test_get_deleted_documents_returns_only_deleted(self):
        """get_deleted_documents() should return only soft-deleted documents."""
        deleted = DocumentFolderService.get_deleted_documents(
            user=self.owner, corpus_id=self.corpus.id
        )

        self.assertEqual(deleted.count(), 3)
        for path in deleted:
            self.assertTrue(path.is_deleted)

    def test_get_folder_documents_excludes_deleted_by_default(self):
        """get_folder_documents() should exclude deleted documents by default."""
        docs = DocumentFolderService.get_folder_documents(
            user=self.owner, corpus_id=self.corpus.id, folder_id=None
        )

        self.assertEqual(docs.count(), 1)
        self.assertEqual(docs.first(), self.active_doc)


# =============================================================================
# 6. CORPUS ISOLATION SCENARIOS
# =============================================================================


class TestCorpusIsolation_AddDocumentCreatesIsolatedCopy(DocumentFolderServiceTestBase):
    """
    SCENARIO: Adding a document to a corpus creates a corpus-isolated copy.

    BUSINESS RULE: Documents in a corpus have independent version trees.
    The original document is unchanged - a NEW document is created.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.owner, is_public=False
        )
        # Create a source document (not in any corpus)
        self.source_document = Document.objects.create(
            title="Source Document",
            description="Original description",
            creator=self.owner,
            pdf_file="source.pdf",
        )

    def test_add_document_creates_new_document(self):
        """Adding document should create a NEW document, not modify original."""
        corpus_doc, status, error = DocumentFolderService.add_document_to_corpus(
            user=self.owner, document=self.source_document, corpus=self.corpus
        )

        self.assertIsNotNone(corpus_doc)
        self.assertNotEqual(corpus_doc.id, self.source_document.id)
        self.assertEqual(status, "added")

    def test_corpus_copy_has_source_document_provenance(self):
        """Corpus copy should track source_document for provenance."""
        corpus_doc, _, _ = DocumentFolderService.add_document_to_corpus(
            user=self.owner, document=self.source_document, corpus=self.corpus
        )

        self.assertEqual(corpus_doc.source_document, self.source_document)

    def test_corpus_copy_has_independent_version_tree(self):
        """Corpus copy should have its own version_tree_id."""
        corpus_doc, _, _ = DocumentFolderService.add_document_to_corpus(
            user=self.owner, document=self.source_document, corpus=self.corpus
        )

        self.assertIsNotNone(corpus_doc.version_tree_id)
        self.assertNotEqual(
            corpus_doc.version_tree_id, self.source_document.version_tree_id
        )

    def test_original_document_unchanged(self):
        """Source document should not be modified when adding to corpus."""
        original_title = self.source_document.title
        original_description = self.source_document.description

        DocumentFolderService.add_document_to_corpus(
            user=self.owner, document=self.source_document, corpus=self.corpus
        )

        self.source_document.refresh_from_db()
        self.assertEqual(self.source_document.title, original_title)
        self.assertEqual(self.source_document.description, original_description)

    def test_corpus_copy_has_document_path(self):
        """Corpus copy should have DocumentPath linking it to corpus."""
        corpus_doc, _, _ = DocumentFolderService.add_document_to_corpus(
            user=self.owner, document=self.source_document, corpus=self.corpus
        )

        path_exists = DocumentPath.objects.filter(
            document=corpus_doc, corpus=self.corpus, is_current=True, is_deleted=False
        ).exists()
        self.assertTrue(path_exists)


class TestCorpusIsolation_Deduplication(DocumentFolderServiceTestBase):
    """
    SCENARIO: Adding same document twice should deduplicate within corpus.

    BUSINESS RULE: Deduplication is based on pdf_file_hash.
    If hash is NULL, no deduplication occurs.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.owner, is_public=False
        )
        self.document_with_hash = Document.objects.create(
            title="Doc With Hash",
            creator=self.owner,
            pdf_file="hashed.pdf",
            pdf_file_hash="abc123hash",
        )
        self.document_without_hash = Document.objects.create(
            title="Doc Without Hash",
            creator=self.owner,
            pdf_file="nohash.pdf",
            pdf_file_hash=None,
        )

    def test_adding_same_document_twice_creates_separate_copies(self):
        """Adding document multiple times creates separate corpus copies (no dedup)."""
        corpus_doc1, status1, _ = DocumentFolderService.add_document_to_corpus(
            user=self.owner, document=self.document_with_hash, corpus=self.corpus
        )
        corpus_doc2, status2, _ = DocumentFolderService.add_document_to_corpus(
            user=self.owner, document=self.document_with_hash, corpus=self.corpus
        )

        # Both should be "added" - no content-based deduplication
        self.assertEqual(status1, "added")
        self.assertEqual(status2, "added")
        # Different corpus-isolated documents created
        self.assertNotEqual(corpus_doc1.id, corpus_doc2.id)

    def test_adding_document_without_hash_creates_new_each_time(self):
        """Documents are not deduplicated regardless of hash presence."""
        corpus_doc1, status1, _ = DocumentFolderService.add_document_to_corpus(
            user=self.owner, document=self.document_without_hash, corpus=self.corpus
        )
        corpus_doc2, status2, _ = DocumentFolderService.add_document_to_corpus(
            user=self.owner, document=self.document_without_hash, corpus=self.corpus
        )

        # Both should be "added" - each call creates a new document
        self.assertEqual(status1, "added")
        self.assertEqual(status2, "added")
        self.assertNotEqual(corpus_doc1.id, corpus_doc2.id)


class TestCorpusIsolation_AddToFolder(DocumentFolderServiceTestBase):
    """
    SCENARIO: Adding document to corpus with folder placement.

    BUSINESS RULE: Documents can be placed directly in a folder when added.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.owner, is_public=False
        )
        self.folder, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Target Folder"
        )
        self.source_document = Document.objects.create(
            title="Source Document", creator=self.owner, pdf_file="source.pdf"
        )

    def test_add_document_to_corpus_with_folder(self):
        """Can add document directly to a folder in corpus."""
        corpus_doc, status, error = DocumentFolderService.add_document_to_corpus(
            user=self.owner,
            document=self.source_document,
            corpus=self.corpus,
            folder=self.folder,
        )

        self.assertIsNotNone(corpus_doc)
        self.assertEqual(error, "")

        # Verify document is in folder
        path = DocumentPath.objects.get(
            document=corpus_doc, corpus=self.corpus, is_current=True, is_deleted=False
        )
        self.assertEqual(path.folder, self.folder)


# =============================================================================
# 7. EDGE CASES AND ERROR HANDLING
# =============================================================================


class TestEdgeCases_NonexistentResources(TransactionTestCase):
    """
    SCENARIO: Operations on nonexistent resources should fail gracefully.

    BUSINESS RULE: Return empty results or error messages, never crash.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.owner, is_public=False
        )

    def test_get_visible_folders_with_nonexistent_corpus_returns_empty(self):
        """Querying folders for nonexistent corpus returns empty queryset."""
        folders = DocumentFolderService.get_visible_folders(
            user=self.owner, corpus_id=99999
        )
        self.assertEqual(folders.count(), 0)

    def test_get_folder_by_id_with_nonexistent_id_returns_none(self):
        """Querying nonexistent folder returns None (IDOR protection)."""
        folder = DocumentFolderService.get_folder_by_id(
            user=self.owner, folder_id=99999
        )
        self.assertIsNone(folder)

    def test_get_deleted_documents_with_nonexistent_corpus_returns_empty(self):
        """Querying deleted docs for nonexistent corpus returns empty."""
        deleted = DocumentFolderService.get_deleted_documents(
            user=self.owner, corpus_id=99999
        )
        self.assertEqual(deleted.count(), 0)


class TestEdgeCases_IDORProtection(TransactionTestCase):
    """
    SCENARIO: IDOR (Insecure Direct Object Reference) protection.

    BUSINESS RULE: Same error message for "not found" and "no permission"
    to prevent information disclosure.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.attacker = User.objects.create_user(
            username="attacker", email="attacker@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Private Corpus", creator=self.owner, is_public=False
        )
        self.folder, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Secret Folder"
        )

    def test_get_folder_by_id_returns_none_for_unauthorized_user(self):
        """Attacker cannot discover folder existence through get_folder_by_id."""
        folder = DocumentFolderService.get_folder_by_id(
            user=self.attacker, folder_id=self.folder.id
        )

        # Should return None (same as if folder doesn't exist)
        self.assertIsNone(folder)

    def test_get_visible_folders_returns_empty_for_unauthorized_user(self):
        """Attacker cannot see folders they don't have access to."""
        folders = DocumentFolderService.get_visible_folders(
            user=self.attacker, corpus_id=self.corpus.id
        )

        self.assertEqual(folders.count(), 0)


class TestEdgeCases_DocumentNotInCorpus(DocumentFolderServiceTestBase):
    """
    SCENARIO: Operations on documents not in the target corpus.

    BUSINESS RULE: Should fail with clear error message.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.corpus_a = Corpus.objects.create(
            title="Corpus A", creator=self.owner, is_public=False
        )
        self.corpus_b = Corpus.objects.create(
            title="Corpus B", creator=self.owner, is_public=False
        )
        self.folder_in_a, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus_a, name="Folder in A"
        )
        # Document only in corpus B
        self.document_in_b = Document.objects.create(
            title="Doc in B", creator=self.owner, pdf_file="doc_b.pdf"
        )
        DocumentPath.objects.create(
            document=self.document_in_b,
            corpus=self.corpus_b,
            creator=self.owner,
            folder=None,
            path="/doc_b.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

    def test_move_document_to_wrong_corpus_folder_fails(self):
        """Cannot move document to folder in different corpus."""
        success, error = DocumentFolderService.move_document_to_folder(
            user=self.owner,
            document=self.document_in_b,
            corpus=self.corpus_a,  # Wrong corpus
            folder=self.folder_in_a,
        )

        self.assertFalse(success)
        self.assertIn("does not belong", error)


class TestEdgeCases_UploadQuota(DocumentFolderServiceTestBase):
    """
    SCENARIO: Upload quota enforcement for capped users.

    BUSINESS RULE: Usage-capped users have document limits.
    """

    def setUp(self):
        self.capped_user = User.objects.create_user(
            username="capped", email="capped@test.com", password="test"
        )
        self.capped_user.is_usage_capped = True
        self.capped_user.save()

        self.uncapped_user = User.objects.create_user(
            username="uncapped", email="uncapped@test.com", password="test"
        )
        self.uncapped_user.is_usage_capped = False
        self.uncapped_user.save()

    def test_uncapped_user_passes_quota_check(self):
        """Uncapped user should always pass quota check."""
        can_upload, error = DocumentFolderService.check_user_upload_quota(
            self.uncapped_user
        )

        self.assertTrue(can_upload)
        self.assertEqual(error, "")

    def test_capped_user_with_room_passes_quota_check(self):
        """Capped user under limit should pass quota check."""
        can_upload, error = DocumentFolderService.check_user_upload_quota(
            self.capped_user
        )

        self.assertTrue(can_upload)
        self.assertEqual(error, "")


class TestEdgeCases_EmptyOperations(TransactionTestCase):
    """
    SCENARIO: Operations with empty inputs should handle gracefully.

    BUSINESS RULE: Empty inputs should not crash, return appropriate results.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.owner, is_public=False
        )

    def test_search_folders_with_empty_query_returns_all(self):
        """Searching with empty string returns all folders."""
        DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Folder 1"
        )
        DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Folder 2"
        )

        results = DocumentFolderService.search_folders(
            user=self.owner, corpus_id=self.corpus.id, query=""
        )

        self.assertEqual(results.count(), 2)

    def test_search_folders_with_whitespace_query_returns_all(self):
        """Searching with whitespace-only returns all folders."""
        DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Folder"
        )

        results = DocumentFolderService.search_folders(
            user=self.owner, corpus_id=self.corpus.id, query="   "
        )

        self.assertEqual(results.count(), 1)

    def test_get_folder_tree_for_empty_corpus(self):
        """Getting folder tree for corpus with no folders returns empty list."""
        tree = DocumentFolderService.get_folder_tree(
            user=self.owner, corpus_id=self.corpus.id
        )

        self.assertEqual(tree, [])


# =============================================================================
# 9. M2M RELATIONSHIP BACKWARD COMPATIBILITY
# =============================================================================


class TestM2MBackwardCompatibility(DocumentFolderServiceTestBase):
    """
    SCENARIO: M2M relationship (corpus.documents) is maintained for backward compatibility.

    BUSINESS RULE: Legacy code using corpus.documents should continue to work.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.owner, is_public=False
        )
        self.source_document = Document.objects.create(
            title="Source Document", creator=self.owner, pdf_file="source.pdf"
        )

    def test_document_path_query_finds_added_document(self):
        """Documents can be found via DocumentPath query after add_document."""
        corpus_doc, _, _ = DocumentFolderService.add_document_to_corpus(
            user=self.owner, document=self.source_document, corpus=self.corpus
        )

        # Query via DocumentPath - the new pattern
        from opencontractserver.documents.models import DocumentPath

        doc_ids = DocumentPath.objects.filter(
            corpus=self.corpus, is_current=True, is_deleted=False
        ).values_list("document_id", flat=True)
        found = Document.objects.filter(id__in=doc_ids)
        self.assertIn(corpus_doc, found)


# =============================================================================
# 10. REMOVE DOCUMENT SCENARIOS
# =============================================================================


class TestRemoveDocument_BasicOperations(DocumentFolderServiceTestBase):
    """
    SCENARIO: Removing documents from corpus.

    BUSINESS RULE: Remove creates soft-delete, maintains history.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.owner, is_public=False
        )
        self.source_document = Document.objects.create(
            title="Source Document", creator=self.owner, pdf_file="source.pdf"
        )
        self.corpus_doc, _, _ = DocumentFolderService.add_document_to_corpus(
            user=self.owner, document=self.source_document, corpus=self.corpus
        )

    def test_remove_document_from_corpus(self):
        """Can remove document from corpus."""
        success, error = DocumentFolderService.remove_document_from_corpus(
            user=self.owner, document=self.corpus_doc, corpus=self.corpus
        )

        self.assertTrue(success)
        self.assertEqual(error, "")

    def test_removed_document_is_soft_deleted(self):
        """Removed document should have is_deleted=True path."""
        DocumentFolderService.remove_document_from_corpus(
            user=self.owner, document=self.corpus_doc, corpus=self.corpus
        )

        path = DocumentPath.objects.get(
            document=self.corpus_doc, corpus=self.corpus, is_current=True
        )
        self.assertTrue(path.is_deleted)

    def test_remove_without_permission_fails(self):
        """Cannot remove document without write permission."""
        reader = User.objects.create_user(
            username="reader", email="reader@test.com", password="test"
        )
        set_permissions_for_obj_to_user(reader, self.corpus, [PermissionTypes.READ])

        success, error = DocumentFolderService.remove_document_from_corpus(
            user=reader, document=self.corpus_doc, corpus=self.corpus
        )

        self.assertFalse(success)
        self.assertIn("Permission denied", error)

    def test_bulk_remove_documents(self):
        """Can bulk remove multiple documents."""
        doc2 = Document.objects.create(
            title="Doc 2", creator=self.owner, pdf_file="doc2.pdf"
        )
        corpus_doc2, _, _ = DocumentFolderService.add_document_to_corpus(
            user=self.owner, document=doc2, corpus=self.corpus
        )

        removed_count, error = DocumentFolderService.remove_documents_from_corpus(
            user=self.owner,
            document_ids=[self.corpus_doc.id, corpus_doc2.id],
            corpus=self.corpus,
        )

        self.assertEqual(removed_count, 2)
        self.assertEqual(error, "")


# =============================================================================
# 8. FILE TYPE VALIDATION SCENARIOS
# =============================================================================


class TestValidateFileType(DocumentFolderServiceTestBase):
    """Tests for validate_file_type classmethod."""

    def test_validate_file_type_accepts_pdf(self):
        """PDF bytes should pass validation."""
        pdf_bytes = b"%PDF-1.4 minimal pdf content"
        mime_type, error = DocumentFolderService.validate_file_type(pdf_bytes)
        self.assertEqual(mime_type, "application/pdf")
        self.assertEqual(error, "")

    def test_validate_file_type_rejects_unknown(self):
        """Random binary data that isn't a known type should be rejected."""
        # Bytes that filetype library can identify but aren't in our allowed list
        # Use a GIF header which is identifiable but not in our pipeline
        gif_bytes = b"GIF89a" + b"\x00" * 100
        mime_type, error = DocumentFolderService.validate_file_type(gif_bytes)
        self.assertIsNone(mime_type)
        self.assertIn("Unallowed filetype", error)


# =============================================================================
# 9. DOCUMENT PATH HISTORY TRACKING SCENARIOS
# =============================================================================


class _DocumentPathHistoryTestBase(DocumentFolderServiceTestBase):
    """
    Shared fixtures for the DocumentPathHistory_* test group.

    Every test in this group needs an owner and a corpus. Subclasses layer on
    whatever folders / documents their specific scenarios require by calling
    ``super().setUp()`` first.
    """

    def setUp(self):
        super().setUp()
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.owner, is_public=False
        )


class TestDocumentPathHistory_MoveTracking(_DocumentPathHistoryTestBase):
    """
    SCENARIO: Document moves create auditable history via DocumentPath tree.

    BUSINESS RULE: Every folder move creates a new DocumentPath node linked
    to the previous one, enabling full lifecycle traversal.
    """

    def setUp(self):
        super().setUp()
        self.folder_a, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Folder A"
        )
        self.folder_b, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Folder B"
        )
        self.document = Document.objects.create(
            title="Test Document", creator=self.owner, pdf_file="test.pdf"
        )
        self.document_path = DocumentPath.objects.create(
            document=self.document,
            corpus=self.corpus,
            creator=self.owner,
            folder=None,
            path="/test.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

    def test_single_move_creates_two_path_records(self):
        """One move should produce the original + one new record."""
        DocumentFolderService.move_document_to_folder(
            user=self.owner,
            document=self.document,
            corpus=self.corpus,
            folder=self.folder_a,
        )

        total = DocumentPath.objects.filter(
            document=self.document, corpus=self.corpus
        ).count()
        self.assertEqual(total, 2)

    def test_multi_move_chain_creates_correct_record_count(self):
        """Three moves should produce 4 records total (original + 3)."""
        for folder in [self.folder_a, self.folder_b, None]:
            DocumentFolderService.move_document_to_folder(
                user=self.owner,
                document=self.document,
                corpus=self.corpus,
                folder=folder,
            )

        total = DocumentPath.objects.filter(
            document=self.document, corpus=self.corpus
        ).count()
        self.assertEqual(total, 4)

    def test_multi_move_chain_parent_links(self):
        """Each move's parent should point to the immediately previous path."""
        DocumentFolderService.move_document_to_folder(
            user=self.owner,
            document=self.document,
            corpus=self.corpus,
            folder=self.folder_a,
        )
        DocumentFolderService.move_document_to_folder(
            user=self.owner,
            document=self.document,
            corpus=self.corpus,
            folder=self.folder_b,
        )

        # Walk from current back to root
        current = self._get_current_path()
        self.assertEqual(current.folder, self.folder_b)
        self.assertIsNotNone(current.parent)
        self.assertEqual(current.parent.folder, self.folder_a)
        self.assertIsNotNone(current.parent.parent)
        self.assertIsNone(current.parent.parent.folder)  # Original at root
        self.assertIsNone(current.parent.parent.parent)  # Root of chain

    def test_only_one_current_path_after_multiple_moves(self):
        """Only the latest path record should have is_current=True."""
        DocumentFolderService.move_document_to_folder(
            user=self.owner,
            document=self.document,
            corpus=self.corpus,
            folder=self.folder_a,
        )
        DocumentFolderService.move_document_to_folder(
            user=self.owner,
            document=self.document,
            corpus=self.corpus,
            folder=self.folder_b,
        )

        current_count = DocumentPath.objects.filter(
            document=self.document,
            corpus=self.corpus,
            is_current=True,
            is_deleted=False,
        ).count()
        self.assertEqual(current_count, 1)

    def test_move_does_not_change_document_content(self):
        """Moving only affects the path — document FK stays the same."""
        DocumentFolderService.move_document_to_folder(
            user=self.owner,
            document=self.document,
            corpus=self.corpus,
            folder=self.folder_a,
        )

        current = self._get_current_path()
        self.assertEqual(current.document_id, self.document.id)

    def test_move_no_active_path_returns_error(self):
        """If the document has no active path, the move should fail gracefully."""
        self.document_path.is_current = False
        self.document_path.save(update_fields=["is_current"])

        success, error = DocumentFolderService.move_document_to_folder(
            user=self.owner,
            document=self.document,
            corpus=self.corpus,
            folder=self.folder_a,
        )

        self.assertFalse(success)
        self.assertIn("No active document path found", error)


class TestDocumentPathHistory_ComputeMovedPath(_DocumentPathHistoryTestBase):
    """
    SCENARIO: _compute_moved_path() correctly builds new path strings.

    BUSINESS RULE: When moving, the path should reflect the target folder
    hierarchy while preserving the document filename.
    """

    def test_move_to_root_strips_folder_prefix(self):
        """Moving to root produces /<filename>."""
        result = DocumentFolderService._compute_moved_path(
            "/some/deep/path/report.pdf", None
        )
        self.assertEqual(result, "/report.pdf")

    def test_move_to_folder_prepends_folder_path(self):
        """Moving to a folder produces /<folder_path>/<filename>."""
        folder, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Legal"
        )
        result = DocumentFolderService._compute_moved_path("/report.pdf", folder)
        self.assertEqual(result, "/Legal/report.pdf")

    def test_move_to_nested_folder(self):
        """Moving to a nested folder produces the full ancestor path."""
        parent, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Legal"
        )
        child, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Contracts", parent=parent
        )
        result = DocumentFolderService._compute_moved_path("/report.pdf", child)
        self.assertEqual(result, "/Legal/Contracts/report.pdf")

    def test_preserves_filename_with_special_characters(self):
        """Filenames with dots, hyphens, underscores are preserved."""
        result = DocumentFolderService._compute_moved_path(
            "/old-folder/my_report.v2.final.pdf", None
        )
        self.assertEqual(result, "/my_report.v2.final.pdf")

    def test_handles_path_without_leading_slash(self):
        """Even if the existing path lacks a leading slash, filename is extracted."""
        result = DocumentFolderService._compute_moved_path("documents/report.pdf", None)
        self.assertEqual(result, "/report.pdf")

    def test_precomputed_target_folder_path_matches_on_demand(self):
        """Passing target_folder_path produces the same result as on-demand computation."""
        folder, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Cached"
        )
        current_path = "/old/dir/report.pdf"

        on_demand = DocumentFolderService._compute_moved_path(current_path, folder)
        precomputed = DocumentFolderService._compute_moved_path(
            current_path, folder, target_folder_path=folder.get_path()
        )

        self.assertEqual(on_demand, precomputed)
        self.assertEqual(precomputed, "/Cached/report.pdf")

    def test_precomputed_target_folder_path_takes_precedence(self):
        """The pre-computed value is used over the folder's actual path."""
        folder, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="RealName"
        )
        # Pass a different path to verify the pre-computed value wins.
        result = DocumentFolderService._compute_moved_path(
            "/doc.pdf", folder, target_folder_path="Override/Path"
        )
        self.assertEqual(result, "/Override/Path/doc.pdf")

    def test_none_target_folder_path_falls_back_to_get_path(self):
        """Only None triggers the on-demand get_path() fallback."""
        folder, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Fallback"
        )
        result = DocumentFolderService._compute_moved_path(
            "/doc.pdf", folder, target_folder_path=None
        )
        self.assertEqual(result, "/Fallback/doc.pdf")


class TestDocumentPathHistory_PathConflicts(_DocumentPathHistoryTestBase):
    """
    SCENARIO: Move operations handle path conflicts gracefully.

    BUSINESS RULE: If the computed path is already occupied by another
    active document, the path is disambiguated with a numeric suffix
    (e.g. ``report_1.pdf``) while still creating a proper history node
    with the new folder assignment.
    """

    def setUp(self):
        super().setUp()
        self.folder, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Target"
        )

    def test_move_with_path_conflict_disambiguates_path(self):
        """When computed path conflicts, a numeric suffix is appended."""
        # Create two documents
        doc1 = Document.objects.create(
            title="First", creator=self.owner, pdf_file="same.pdf"
        )
        doc2 = Document.objects.create(
            title="Second", creator=self.owner, pdf_file="same.pdf"
        )

        # doc1 is already at /Target/same.pdf
        DocumentPath.objects.create(
            document=doc1,
            corpus=self.corpus,
            creator=self.owner,
            folder=self.folder,
            path="/Target/same.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )
        DocumentPath.objects.create(
            document=doc2,
            corpus=self.corpus,
            creator=self.owner,
            folder=None,
            path="/same.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        # Move doc2 to same folder as doc1 — computed path /Target/same.pdf conflicts
        success, error = DocumentFolderService.move_document_to_folder(
            user=self.owner,
            document=doc2,
            corpus=self.corpus,
            folder=self.folder,
        )

        self.assertTrue(success)
        current = DocumentPath.objects.get(
            document=doc2, corpus=self.corpus, is_current=True, is_deleted=False
        )
        # Folder is updated
        self.assertEqual(current.folder, self.folder)
        # Path is disambiguated with _1 suffix
        self.assertEqual(current.path, "/Target/same_1.pdf")
        # History node still created
        self.assertIsNotNone(current.parent)

    def test_multiple_conflicts_increment_suffix(self):
        """Successive conflicts produce _1, _2, etc.

        All documents share the same filename (dup.pdf) so that moving them
        into a folder that already has /Target/dup.pdf forces actual
        disambiguation via numeric suffixes.
        """
        docs = []
        for i in range(3):
            d = Document.objects.create(
                title=f"Doc {i}", creator=self.owner, pdf_file="dup.pdf"
            )
            docs.append(d)

        # Place first doc in the folder at the canonical path
        DocumentPath.objects.create(
            document=docs[0],
            corpus=self.corpus,
            creator=self.owner,
            folder=self.folder,
            path="/Target/dup.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        # Create two more docs in different source folders — all share the
        # filename "dup.pdf" so _compute_moved_path produces /Target/dup.pdf
        # for each, triggering disambiguation.
        for idx, doc in enumerate(docs[1:], start=1):
            DocumentPath.objects.create(
                document=doc,
                corpus=self.corpus,
                creator=self.owner,
                folder=None,
                path=f"/source{idx}/dup.pdf",
                version_number=1,
                is_current=True,
                is_deleted=False,
            )

        # Move both to the same folder
        for doc in docs[1:]:
            DocumentFolderService.move_document_to_folder(
                user=self.owner,
                document=doc,
                corpus=self.corpus,
                folder=self.folder,
            )

        # Collect the new paths (excluding the original doc[0])
        new_paths = sorted(
            DocumentPath.objects.filter(
                document__in=docs[1:],
                corpus=self.corpus,
                is_current=True,
                is_deleted=False,
            ).values_list("path", flat=True)
        )
        self.assertIn("/Target/dup_1.pdf", new_paths)
        self.assertIn("/Target/dup_2.pdf", new_paths)

    def test_pre_existing_path_triggers_disambiguation(self):
        """Pre-creating a DocumentPath at the target triggers the fallback."""
        doc = Document.objects.create(
            title="Mover", creator=self.owner, pdf_file="report.pdf"
        )
        DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            creator=self.owner,
            folder=None,
            path="/report.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        # Pre-create a path at the would-be target
        blocker = Document.objects.create(
            title="Blocker", creator=self.owner, pdf_file="report.pdf"
        )
        DocumentPath.objects.create(
            document=blocker,
            corpus=self.corpus,
            creator=self.owner,
            folder=self.folder,
            path="/Target/report.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        success, _ = DocumentFolderService.move_document_to_folder(
            user=self.owner,
            document=doc,
            corpus=self.corpus,
            folder=self.folder,
        )
        self.assertTrue(success)

        current = DocumentPath.objects.get(
            document=doc, corpus=self.corpus, is_current=True, is_deleted=False
        )
        self.assertEqual(current.path, "/Target/report_1.pdf")
        self.assertEqual(current.folder, self.folder)

    def test_dotfile_disambiguation_preserves_leading_dot(self):
        """Dotfiles like .gitignore get suffix appended, not split on the dot."""
        doc1 = Document.objects.create(
            title="Config1", creator=self.owner, pdf_file=".gitignore"
        )
        doc2 = Document.objects.create(
            title="Config2", creator=self.owner, pdf_file=".gitignore"
        )

        # doc1 already occupies /Target/.gitignore
        DocumentPath.objects.create(
            document=doc1,
            corpus=self.corpus,
            creator=self.owner,
            folder=self.folder,
            path="/Target/.gitignore",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )
        DocumentPath.objects.create(
            document=doc2,
            corpus=self.corpus,
            creator=self.owner,
            folder=None,
            path="/.gitignore",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        # Move doc2 into the same folder — should disambiguate correctly
        success, error = DocumentFolderService.move_document_to_folder(
            user=self.owner,
            document=doc2,
            corpus=self.corpus,
            folder=self.folder,
        )

        self.assertTrue(success)
        current = DocumentPath.objects.get(
            document=doc2, corpus=self.corpus, is_current=True, is_deleted=False
        )
        # The leading dot must be preserved and the suffix appended to the
        # filename stem, not inserted before the dot.
        self.assertEqual(current.path, "/Target/.gitignore_1")

    def test_disambiguate_path_raises_after_max_suffix(self):
        """_disambiguate_path raises ValueError when suffix cap is exhausted."""
        from unittest.mock import patch

        # Build a set of all candidate paths the disambiguation loop will try.
        # _disambiguate_path pre-fetches occupied paths with a single query;
        # we patch that queryset's values_list to return every candidate so
        # all are "taken".
        base = "/Target/report"
        ext = ".pdf"
        all_candidates = {f"{base}{ext}"}
        for i in range(1, MAX_PATH_DISAMBIGUATION_SUFFIX + 1):
            all_candidates.add(f"{base}_{i}{ext}")

        with patch.object(
            DocumentPath.objects,
            "filter",
        ) as mock_filter:
            # _disambiguate_path now chains two .filter() calls (base filters,
            # then directory filter), so the mock must support the extra link:
            # filter().filter().exclude().values_list() and
            # filter().filter().values_list().
            inner = mock_filter.return_value.filter.return_value
            inner.exclude.return_value.values_list.return_value = all_candidates
            inner.values_list.return_value = all_candidates
            # Also keep the old single-filter chain working for safety.
            mock_filter.return_value.exclude.return_value.values_list.return_value = (
                all_candidates
            )
            mock_filter.return_value.values_list.return_value = all_candidates

            with self.assertRaises(ValueError) as ctx:
                DocumentFolderService._disambiguate_path(
                    "/Target/report.pdf", self.corpus
                )

            self.assertIn(str(MAX_PATH_DISAMBIGUATION_SUFFIX), str(ctx.exception))


class TestDocumentPathHistory_DeleteFolderTracking(_DocumentPathHistoryTestBase):
    """
    SCENARIO: Deleting a folder creates history nodes for displaced documents.

    BUSINESS RULE: When a folder is deleted, documents are moved to root
    with proper audit trail, not silent in-place updates.
    """

    def test_delete_folder_creates_history_for_each_document(self):
        """Each document in a deleted folder gets its own history node."""
        folder, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Doomed"
        )
        docs = []
        for i in range(3):
            doc = Document.objects.create(
                title=f"Doc {i}", creator=self.owner, pdf_file=f"doc{i}.pdf"
            )
            DocumentPath.objects.create(
                document=doc,
                corpus=self.corpus,
                creator=self.owner,
                folder=folder,
                path=f"/Doomed/doc{i}.pdf",
                version_number=1,
                is_current=True,
                is_deleted=False,
            )
            docs.append(doc)

        DocumentFolderService.delete_folder(user=self.owner, folder=folder)

        # Each document should have 2 records (original + moved-to-root)
        for doc in docs:
            total = DocumentPath.objects.filter(
                document=doc, corpus=self.corpus
            ).count()
            self.assertEqual(total, 2, f"Doc {doc.title} should have 2 path records")

            current = DocumentPath.objects.get(
                document=doc, corpus=self.corpus, is_current=True, is_deleted=False
            )
            self.assertIsNone(current.folder)
            self.assertIsNotNone(current.parent)

    def test_delete_folder_preserves_version_number(self):
        """Folder deletion does not increment version.

        Per path tree rule P5 (see versioning.py), version_number
        increments only on content changes.
        """
        folder, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="TempFolder"
        )
        doc = Document.objects.create(
            title="Test Doc", creator=self.owner, pdf_file="doc.pdf"
        )
        DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            creator=self.owner,
            folder=folder,
            path="/TempFolder/doc.pdf",
            version_number=3,
            is_current=True,
            is_deleted=False,
        )

        DocumentFolderService.delete_folder(user=self.owner, folder=folder)

        current = DocumentPath.objects.get(
            document=doc, corpus=self.corpus, is_current=True, is_deleted=False
        )
        self.assertEqual(current.version_number, 3)

    def test_delete_folder_updates_path_to_root(self):
        """Documents displaced by folder deletion get root-relative paths."""
        folder, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Reports"
        )
        doc = Document.objects.create(
            title="Test Doc", creator=self.owner, pdf_file="summary.pdf"
        )
        DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            creator=self.owner,
            folder=folder,
            path="/Reports/summary.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        DocumentFolderService.delete_folder(user=self.owner, folder=folder)

        current = DocumentPath.objects.get(
            document=doc, corpus=self.corpus, is_current=True, is_deleted=False
        )
        self.assertEqual(current.path, "/summary.pdf")

    @patch("opencontractserver.corpuses.folder_service.post_save")
    def test_delete_folder_dispatches_post_save_for_each_created_path(
        self, mock_signal
    ):
        """bulk_create in delete_folder bypasses signals; verify manual dispatch fires."""
        folder, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="ToDelete"
        )
        docs = []
        for i in range(3):
            doc = Document.objects.create(
                title=f"Doc {i}", creator=self.owner, pdf_file=f"del{i}.pdf"
            )
            DocumentPath.objects.create(
                document=doc,
                corpus=self.corpus,
                creator=self.owner,
                folder=folder,
                path=f"/ToDelete/del{i}.pdf",
                version_number=1,
                is_current=True,
                is_deleted=False,
            )
            docs.append(doc)

        success, error = DocumentFolderService.delete_folder(
            user=self.owner, folder=folder
        )

        self.assertTrue(success)
        self.assertEqual(error, "")

        # post_save.send should have been called exactly 3 times (once per doc)
        send_calls = mock_signal.send.call_args_list
        self.assertEqual(len(send_calls), 3)

        for call in send_calls:
            _, call_kwargs = call
            self.assertEqual(call_kwargs["sender"], DocumentPath)
            self.assertTrue(call_kwargs["created"])
            self.assertFalse(call_kwargs["raw"])
            self.assertIsNotNone(call_kwargs.get("using"))
            self.assertIsNone(call_kwargs.get("update_fields"))


class TestDocumentPathHistory_BulkMoveTracking(_DocumentPathHistoryTestBase):
    """
    SCENARIO: Bulk move operations create per-document history nodes.

    BUSINESS RULE: Each document in a bulk move gets its own history entry
    rather than a shared batch update.
    """

    def setUp(self):
        super().setUp()
        self.folder, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Archive"
        )

    def _create_doc_at_root(self, title, filename):
        doc = Document.objects.create(
            title=title, creator=self.owner, pdf_file=filename
        )
        path = DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            creator=self.owner,
            folder=None,
            path=f"/{filename}",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )
        return doc, path

    def test_bulk_move_creates_individual_history_nodes(self):
        """Each document in a bulk move gets its own new DocumentPath record."""
        doc1, _ = self._create_doc_at_root("Doc 1", "doc1.pdf")
        doc2, _ = self._create_doc_at_root("Doc 2", "doc2.pdf")

        moved_count, error = DocumentFolderService.move_documents_to_folder(
            user=self.owner,
            document_ids=[doc1.id, doc2.id],
            corpus=self.corpus,
            folder=self.folder,
        )

        self.assertEqual(moved_count, 2)

        # Each doc should have 2 path records
        for doc in [doc1, doc2]:
            total = DocumentPath.objects.filter(
                document=doc, corpus=self.corpus
            ).count()
            self.assertEqual(total, 2)

    def test_bulk_move_with_parent_chain(self):
        """Bulk-moved documents have proper parent links."""
        doc1, original_path = self._create_doc_at_root("Doc 1", "doc1.pdf")

        DocumentFolderService.move_documents_to_folder(
            user=self.owner,
            document_ids=[doc1.id],
            corpus=self.corpus,
            folder=self.folder,
        )

        current = DocumentPath.objects.get(
            document=doc1, corpus=self.corpus, is_current=True, is_deleted=False
        )
        self.assertEqual(current.parent_id, original_path.id)

    def test_bulk_move_skips_docs_already_in_target(self):
        """Documents already in the target folder are not moved again."""
        doc1, _ = self._create_doc_at_root("Doc 1", "doc1.pdf")
        doc2 = Document.objects.create(
            title="Doc 2", creator=self.owner, pdf_file="doc2.pdf"
        )
        DocumentPath.objects.create(
            document=doc2,
            corpus=self.corpus,
            creator=self.owner,
            folder=self.folder,  # Already in target
            path="/Archive/doc2.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        moved_count, error = DocumentFolderService.move_documents_to_folder(
            user=self.owner,
            document_ids=[doc1.id, doc2.id],
            corpus=self.corpus,
            folder=self.folder,
        )

        # Only doc1 should be moved
        self.assertEqual(moved_count, 1)
        # doc2 should still have only 1 path record
        self.assertEqual(
            DocumentPath.objects.filter(document=doc2, corpus=self.corpus).count(), 1
        )

    @patch("opencontractserver.corpuses.folder_service.post_save")
    def test_bulk_move_dispatches_post_save_for_each_created_path(self, mock_signal):
        """bulk_create bypasses Django signals; verify manual dispatch fires once per doc."""
        doc1, _ = self._create_doc_at_root("Doc 1", "doc1.pdf")
        doc2, _ = self._create_doc_at_root("Doc 2", "doc2.pdf")
        doc3, _ = self._create_doc_at_root("Doc 3", "doc3.pdf")

        moved_count, error = DocumentFolderService.move_documents_to_folder(
            user=self.owner,
            document_ids=[doc1.id, doc2.id, doc3.id],
            corpus=self.corpus,
            folder=self.folder,
        )

        self.assertEqual(moved_count, 3)
        self.assertEqual(error, "")

        # post_save.send should have been called exactly 3 times (once per doc)
        send_calls = mock_signal.send.call_args_list
        self.assertEqual(len(send_calls), 3)

        for call in send_calls:
            _, call_kwargs = call
            self.assertEqual(call_kwargs["sender"], DocumentPath)
            self.assertTrue(call_kwargs["created"])
            self.assertFalse(call_kwargs["raw"])
            self.assertIsNotNone(call_kwargs.get("using"))
            self.assertIsNone(call_kwargs.get("update_fields"))

    def test_document_path_has_no_pre_save_receivers(self):
        """
        REGRESSION GUARD: ``_dispatch_document_path_created_signals`` only
        replays ``post_save``.  If a ``pre_save`` receiver is ever connected
        to ``DocumentPath``, bulk-create paths will silently skip it — which
        would be a latent correctness bug.  Fail loudly here so the dispatch
        helper can be extended intentionally if this invariant changes.
        """
        from django.db.models.signals import pre_save

        self.assertFalse(
            pre_save.has_listeners(sender=DocumentPath),
            (
                "DocumentPath has pre_save receivers registered — update "
                "DocumentFolderService._dispatch_document_path_created_signals "
                "to dispatch pre_save before bulk_create, or this bulk path "
                "will silently drop the new behaviour."
            ),
        )


class TestDocumentPathHistory_FullLifecycleIntegration(_DocumentPathHistoryTestBase):
    """
    SCENARIO: Full lifecycle integration — move, delete, restore, move again.

    BUSINESS RULE: All lifecycle events are traversable via get_path_history()
    regardless of whether they were triggered through folder_service or
    versioning module.
    """

    def setUp(self):
        super().setUp()
        self.folder_a, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Active"
        )
        self.folder_b, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Archive"
        )

    def test_move_then_soft_delete_then_restore_history(self):
        """Complete lifecycle: create -> move -> delete -> restore."""
        from opencontractserver.documents.versioning import get_path_history

        doc = Document.objects.create(
            title="Lifecycle Doc", creator=self.owner, pdf_file="lifecycle.pdf"
        )
        DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            creator=self.owner,
            folder=None,
            path="/lifecycle.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        # Move to folder A
        DocumentFolderService.move_document_to_folder(
            user=self.owner, document=doc, corpus=self.corpus, folder=self.folder_a
        )

        # Soft delete
        DocumentFolderService.soft_delete_document(
            user=self.owner, document=doc, corpus=self.corpus
        )

        # Restore — find the current deleted path and pass it
        deleted_path = DocumentPath.objects.get(
            document=doc, corpus=self.corpus, is_current=True, is_deleted=True
        )
        DocumentFolderService.restore_document(
            user=self.owner, document_path=deleted_path
        )

        # Get final current path and check history
        current = DocumentPath.objects.get(
            document=doc, corpus=self.corpus, is_current=True, is_deleted=False
        )
        history = get_path_history(current)

        self.assertEqual(len(history), 4)
        self.assertEqual(history[0]["action"], "CREATED")
        self.assertEqual(history[1]["action"], "MOVED")
        self.assertEqual(history[2]["action"], "DELETED")
        self.assertEqual(history[3]["action"], "RESTORED")

    def test_move_history_includes_folder_id(self):
        """get_path_history entries include folder_id for move tracking."""
        from opencontractserver.documents.versioning import get_path_history

        doc = Document.objects.create(
            title="Folder Track Doc", creator=self.owner, pdf_file="track.pdf"
        )
        DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            creator=self.owner,
            folder=None,
            path="/track.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        DocumentFolderService.move_document_to_folder(
            user=self.owner, document=doc, corpus=self.corpus, folder=self.folder_a
        )
        DocumentFolderService.move_document_to_folder(
            user=self.owner, document=doc, corpus=self.corpus, folder=self.folder_b
        )

        current = DocumentPath.objects.get(
            document=doc, corpus=self.corpus, is_current=True, is_deleted=False
        )
        history = get_path_history(current)

        self.assertEqual(len(history), 3)
        # Verify folder_id in each entry
        self.assertIsNone(history[0]["folder_id"])  # Root
        self.assertEqual(history[1]["folder_id"], self.folder_a.id)
        self.assertEqual(history[2]["folder_id"], self.folder_b.id)

    def test_multiple_moves_all_detectable_as_moved(self):
        """Every move shows action=MOVED in history, not UNKNOWN."""
        from opencontractserver.documents.versioning import get_path_history

        doc = Document.objects.create(
            title="Multi Move", creator=self.owner, pdf_file="multi.pdf"
        )
        DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            creator=self.owner,
            folder=None,
            path="/multi.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        # Move through 3 folders
        for folder in [self.folder_a, self.folder_b, None]:
            DocumentFolderService.move_document_to_folder(
                user=self.owner, document=doc, corpus=self.corpus, folder=folder
            )

        current = DocumentPath.objects.get(
            document=doc, corpus=self.corpus, is_current=True, is_deleted=False
        )
        history = get_path_history(current)
        actions = [h["action"] for h in history]

        self.assertEqual(actions, ["CREATED", "MOVED", "MOVED", "MOVED"])

    def test_folder_only_move_detected_as_moved_in_history(self):
        """A folder change with an identical path string still shows MOVED.

        Regression guard for the versioning.py change that detects
        folder_id changes in determine_action(), not just path string
        differences.
        """
        from opencontractserver.documents.versioning import get_path_history

        doc = Document.objects.create(
            title="Same Path Doc", creator=self.owner, pdf_file="same.pdf"
        )
        original_path = DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            creator=self.owner,
            folder=None,
            path="/same.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        # Directly create a history node that changes only the folder_id
        # but keeps the same path string — simulates a move where the
        # path string happens to be unchanged.
        original_path.is_current = False
        original_path.save(update_fields=["is_current"])

        moved_path = DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            creator=self.owner,
            folder=self.folder_a,
            path="/same.pdf",  # same path string
            version_number=1,
            parent=original_path,
            is_current=True,
            is_deleted=False,
        )

        history = get_path_history(moved_path)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["action"], "CREATED")
        self.assertEqual(history[1]["action"], "MOVED")
        self.assertEqual(history[1]["folder_id"], self.folder_a.id)

    def test_delete_folder_creates_moved_event_in_history(self):
        """Documents displaced by folder deletion show MOVED in history."""
        from opencontractserver.documents.versioning import get_path_history

        folder, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Temporary"
        )
        doc = Document.objects.create(
            title="Displaced Doc", creator=self.owner, pdf_file="displaced.pdf"
        )
        DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            creator=self.owner,
            folder=folder,
            path="/Temporary/displaced.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        DocumentFolderService.delete_folder(user=self.owner, folder=folder)

        current = DocumentPath.objects.get(
            document=doc, corpus=self.corpus, is_current=True, is_deleted=False
        )
        history = get_path_history(current)

        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["action"], "CREATED")
        self.assertEqual(history[1]["action"], "MOVED")
        self.assertIsNone(history[1]["folder_id"])

    def test_folder_only_move_detected_as_moved(self):
        """A move that changes folder_id but keeps the same path is MOVED, not UNKNOWN."""
        from opencontractserver.documents.versioning import get_path_history

        doc = Document.objects.create(
            title="Folder-Only Move", creator=self.owner, pdf_file="fo.pdf"
        )
        # Manually create an initial path inside folder_a
        initial = DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            creator=self.owner,
            folder=self.folder_a,
            path="/shared_name/fo.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        # Manually create a second node with the SAME path but a different folder,
        # simulating a move where the path string is unchanged.
        initial.is_current = False
        initial.save(update_fields=["is_current"])

        DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            creator=self.owner,
            folder=self.folder_b,
            path="/shared_name/fo.pdf",  # Same path string
            version_number=1,
            parent=initial,
            is_current=True,
            is_deleted=False,
        )

        current = DocumentPath.objects.get(
            document=doc, corpus=self.corpus, is_current=True, is_deleted=False
        )
        history = get_path_history(current)

        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["action"], "CREATED")
        self.assertEqual(history[1]["action"], "MOVED")
        self.assertEqual(history[1]["folder_id"], self.folder_b.id)


# =============================================================================
# 9. ERROR PATH COVERAGE — exercises exception handlers and edge cases
# =============================================================================


class TestErrorPaths_ComputeMovedPathEdgeCases(TransactionTestCase):
    """
    SCENARIO: _compute_moved_path raises on malformed input.

    BUSINESS RULE: Root-only or empty paths have no filename to extract
    and should raise ValueError rather than silently produce bad data.
    """

    def test_root_only_path_raises_value_error(self):
        """Path '/' has no filename segment — must raise."""
        with self.assertRaises(ValueError) as ctx:
            DocumentFolderService._compute_moved_path("/", None)
        self.assertIn("empty or root-only", str(ctx.exception))

    def test_empty_path_raises_value_error(self):
        """Empty string has no filename — must raise."""
        with self.assertRaises(ValueError) as ctx:
            DocumentFolderService._compute_moved_path("", None)
        self.assertIn("empty or root-only", str(ctx.exception))


class TestErrorPaths_DisambiguateExtensionless(DocumentFolderServiceTestBase):
    """
    SCENARIO: _disambiguate_path handles files without extensions.

    BUSINESS RULE: Files like 'Makefile' or 'LICENSE' that lack a dot
    extension get suffixed as 'Makefile_1', 'LICENSE_1', etc.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.owner, is_public=False
        )

    def test_extensionless_file_disambiguates_with_suffix(self):
        """Extensionless file gets _1 appended directly to name."""
        doc = Document.objects.create(
            title="Makefile Doc", creator=self.owner, pdf_file="Makefile"
        )
        DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            creator=self.owner,
            folder=None,
            path="/Makefile",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        result = DocumentFolderService._disambiguate_path("/Makefile", self.corpus)
        self.assertEqual(result, "/Makefile_1")


class TestErrorPaths_DisambiguateRootLevel(DocumentFolderServiceTestBase):
    """
    SCENARIO: _disambiguate_path for root-level paths only considers
    top-level paths, not every path in the corpus.

    BUSINESS RULE: When disambiguating "/report.pdf", the method should
    only look at other root-level paths like "/other.pdf", not paths
    inside subdirectories like "/folder/report.pdf".  Without this,
    rsplit("/", 1)[0] produces "" -> directory="/", and
    path__startswith="/" would match EVERY active path in the corpus.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.owner, is_public=False
        )

    def test_root_disambiguation_ignores_nested_paths(self):
        """Root-level "/report.pdf" does not conflict with "/folder/report.pdf"."""
        doc1 = Document.objects.create(
            title="Nested Doc", creator=self.owner, pdf_file="r.pdf"
        )
        # A path nested inside a folder — should NOT count as a conflict.
        DocumentPath.objects.create(
            document=doc1,
            corpus=self.corpus,
            creator=self.owner,
            folder=None,
            path="/folder/report.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        # Disambiguating "/report.pdf" should return it unchanged because the
        # only existing "report.pdf" is inside "/folder/", not at root.
        result = DocumentFolderService._disambiguate_path("/report.pdf", self.corpus)
        self.assertEqual(result, "/report.pdf")

    def test_root_disambiguation_detects_root_conflict(self):
        """Root-level "/report.pdf" DOES conflict with another root "/report.pdf"."""
        doc1 = Document.objects.create(
            title="Root Doc", creator=self.owner, pdf_file="r.pdf"
        )
        # A path at the root level — this IS a real conflict.
        DocumentPath.objects.create(
            document=doc1,
            corpus=self.corpus,
            creator=self.owner,
            folder=None,
            path="/report.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )
        # Also add a nested path that should be ignored.
        doc2 = Document.objects.create(
            title="Nested Doc", creator=self.owner, pdf_file="r2.pdf"
        )
        DocumentPath.objects.create(
            document=doc2,
            corpus=self.corpus,
            creator=self.owner,
            folder=None,
            path="/folder/report.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        # Should get "_1" suffix because root "/report.pdf" is taken.
        result = DocumentFolderService._disambiguate_path("/report.pdf", self.corpus)
        self.assertEqual(result, "/report_1.pdf")


class TestErrorPaths_DeleteFolderAtomicRollback(DocumentFolderServiceTestBase):
    """
    SCENARIO: delete_folder is fully atomic — if ANY document relocation
    fails, the entire operation (all relocations + folder deletion) is
    rolled back.

    BUSINESS RULE: No partial-success state is ever visible.  Either all
    documents are relocated and the folder is deleted, or nothing changes.
    The caller can safely retry after a failure.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.owner, is_public=False
        )

    def test_delete_folder_rolls_back_all_on_failure(self):
        """When _disambiguate_path raises, the entire transaction is rolled
        back: no documents are relocated and the folder still exists."""
        folder, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Doomed"
        )
        doc = Document.objects.create(
            title="Stuck Doc", creator=self.owner, pdf_file="stuck.pdf"
        )
        DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            creator=self.owner,
            folder=folder,
            path="/Doomed/stuck.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        with patch.object(
            DocumentFolderService,
            "_disambiguate_path",
            side_effect=ValueError("all suffixes exhausted"),
        ):
            success, error = DocumentFolderService.delete_folder(
                user=self.owner, folder=folder
            )

        # Operation should fail
        self.assertFalse(success)
        self.assertIn("rolled back", error)
        # Folder must still exist
        self.assertTrue(CorpusFolder.objects.filter(pk=folder.pk).exists())
        # Document path must still point to the folder with is_current=True
        stuck_path = DocumentPath.objects.get(
            document=doc, corpus=self.corpus, is_current=True
        )
        self.assertEqual(stuck_path.folder_id, folder.id)

    def test_delete_folder_rolls_back_on_planning_failure(self):
        """When the second document fails path disambiguation during the
        planning phase (before any DB writes), the entire operation is
        rolled back atomically and no state changes are persisted."""
        folder, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Mixed"
        )

        # Create two documents in the folder
        doc1 = Document.objects.create(
            title="Doc 1", creator=self.owner, pdf_file="doc1.pdf"
        )
        path1 = DocumentPath.objects.create(
            document=doc1,
            corpus=self.corpus,
            creator=self.owner,
            folder=folder,
            path="/Mixed/doc1.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )
        doc2 = Document.objects.create(
            title="Doc 2", creator=self.owner, pdf_file="doc2.pdf"
        )
        path2 = DocumentPath.objects.create(
            document=doc2,
            corpus=self.corpus,
            creator=self.owner,
            folder=folder,
            path="/Mixed/doc2.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        original_disambiguate = DocumentFolderService._disambiguate_path
        call_count = 0

        def fail_on_second(base_path, corpus, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise ValueError("suffix exhausted")
            return original_disambiguate(base_path, corpus, **kwargs)

        with patch.object(
            DocumentFolderService,
            "_disambiguate_path",
            staticmethod(fail_on_second),
        ):
            success, error = DocumentFolderService.delete_folder(
                user=self.owner, folder=folder
            )

        # Entire operation should fail
        self.assertFalse(success)
        self.assertIn("rolled back", error)

        # Folder must still exist
        self.assertTrue(CorpusFolder.objects.filter(pk=folder.pk).exists())

        # BOTH documents must still be in their original location
        path1.refresh_from_db()
        self.assertTrue(path1.is_current)
        self.assertEqual(path1.folder_id, folder.id)

        path2.refresh_from_db()
        self.assertTrue(path2.is_current)
        self.assertEqual(path2.folder_id, folder.id)

        # No new DocumentPath records should have been created
        total_paths = DocumentPath.objects.filter(
            corpus=self.corpus, document__in=[doc1, doc2]
        ).count()
        self.assertEqual(total_paths, 2, "No new paths should exist after rollback")

    def test_delete_folder_retry_after_failure_succeeds(self):
        """After a failed delete_folder (full rollback), retrying with the
        underlying issue resolved should succeed cleanly."""
        folder, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Retryable"
        )
        doc = Document.objects.create(
            title="Retry Doc", creator=self.owner, pdf_file="retry.pdf"
        )
        DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            creator=self.owner,
            folder=folder,
            path="/Retryable/retry.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        # First attempt: fails
        with patch.object(
            DocumentFolderService,
            "_disambiguate_path",
            side_effect=ValueError("temporary failure"),
        ):
            success, error = DocumentFolderService.delete_folder(
                user=self.owner, folder=folder
            )
        self.assertFalse(success)

        # Folder still exists, doc still in folder
        self.assertTrue(CorpusFolder.objects.filter(pk=folder.pk).exists())

        # Second attempt: succeeds (no mock = real disambiguate)
        success, error = DocumentFolderService.delete_folder(
            user=self.owner, folder=folder
        )
        self.assertTrue(success, f"Retry should succeed, got error: {error}")
        self.assertEqual(error, "")

        # Folder is deleted
        self.assertFalse(CorpusFolder.objects.filter(pk=folder.pk).exists())

        # Document is now at root
        new_path = DocumentPath.objects.get(
            document=doc, corpus=self.corpus, is_current=True
        )
        self.assertIsNone(new_path.folder_id)

    def test_delete_folder_child_reparenting_rolled_back_on_failure(self):
        """Child folder reparenting is also rolled back when document
        relocation fails (part of the same atomic transaction)."""
        parent_folder, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Parent"
        )
        child_folder, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Child", parent=parent_folder
        )

        doc = Document.objects.create(
            title="Blocking Doc", creator=self.owner, pdf_file="blocking.pdf"
        )
        DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            creator=self.owner,
            folder=parent_folder,
            path="/Parent/blocking.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        with patch.object(
            DocumentFolderService,
            "_disambiguate_path",
            side_effect=ValueError("blocked"),
        ):
            success, _ = DocumentFolderService.delete_folder(
                user=self.owner, folder=parent_folder
            )

        self.assertFalse(success)
        # Child folder's parent should NOT have changed
        child_folder.refresh_from_db()
        self.assertEqual(child_folder.parent_id, parent_folder.id)


class TestErrorPaths_MoveDocumentIntegrityError(DocumentFolderServiceTestBase):
    """
    SCENARIO: move_document_to_folder handles concurrent path conflicts.

    BUSINESS RULE: An IntegrityError from a race condition returns a
    descriptive error instead of crashing.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.owner, is_public=False
        )
        self.folder, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Target"
        )
        self.document = Document.objects.create(
            title="Race Doc", creator=self.owner, pdf_file="race.pdf"
        )
        self.document_path = DocumentPath.objects.create(
            document=self.document,
            corpus=self.corpus,
            creator=self.owner,
            folder=None,
            path="/race.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

    def test_integrity_error_returns_conflict_message(self):
        """IntegrityError during create is caught and surfaced cleanly."""
        original_create = DocumentPath.objects.create

        def failing_create(**kwargs):
            if kwargs.get("parent") is not None:
                raise _make_constraint_error()
            return original_create(**kwargs)

        with patch.object(DocumentPath.objects, "create", side_effect=failing_create):
            success, error = DocumentFolderService.move_document_to_folder(
                user=self.owner,
                document=self.document,
                corpus=self.corpus,
                folder=self.folder,
            )

        self.assertFalse(success)
        self.assertIn(PATH_CONFLICT_MSG, error)

    def test_integrity_error_preserves_old_path_as_current(self):
        """IntegrityError must not orphan the document by leaving no active path.

        Regression guard: prior to the savepoint fix, current.save() was
        outside the inner savepoint so an IntegrityError on create would
        commit the is_current=False update, leaving the document with no
        active path at all.
        """
        original_create = DocumentPath.objects.create

        def failing_create(**kwargs):
            if kwargs.get("parent") is not None:
                raise _make_constraint_error()
            return original_create(**kwargs)

        with patch.object(DocumentPath.objects, "create", side_effect=failing_create):
            success, error = DocumentFolderService.move_document_to_folder(
                user=self.owner,
                document=self.document,
                corpus=self.corpus,
                folder=self.folder,
            )

        self.assertFalse(success)

        # The old path must still be the active path — not orphaned
        self.document_path.refresh_from_db()
        self.assertTrue(
            self.document_path.is_current,
            "Old path should remain is_current=True after IntegrityError rollback",
        )

    def test_disambiguate_exhaustion_returns_error(self):
        """ValueError from _disambiguate_path is surfaced as a user-facing error."""
        with patch.object(
            DocumentFolderService,
            "_disambiguate_path",
            side_effect=ValueError("all suffixes exhausted"),
        ):
            success, error = DocumentFolderService.move_document_to_folder(
                user=self.owner,
                document=self.document,
                corpus=self.corpus,
                folder=self.folder,
            )

        self.assertFalse(success)
        self.assertIn("all suffixes exhausted", error)


class TestErrorPaths_BulkMoveAtomicRollback(DocumentFolderServiceTestBase):
    """
    SCENARIO: move_documents_to_folder is fully atomic — if ANY document
    fails to move, the entire batch is rolled back.

    BUSINESS RULE: No partial-success state is ever visible.  Either all
    documents in the batch are moved, or none are.  The caller can safely
    retry after a failure.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.owner, is_public=False
        )
        self.folder, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Target"
        )

    def test_bulk_move_rolls_back_all_on_failure(self):
        """When one document fails during path computation, the entire batch
        is rolled back: no documents are moved."""
        docs = []
        paths = []
        for i in range(3):
            doc = Document.objects.create(
                title=f"Doc {i}", creator=self.owner, pdf_file=f"doc{i}.pdf"
            )
            p = DocumentPath.objects.create(
                document=doc,
                corpus=self.corpus,
                creator=self.owner,
                folder=None,
                path=f"/doc{i}.pdf",
                version_number=1,
                is_current=True,
                is_deleted=False,
            )
            docs.append(doc)
            paths.append(p)

        original_disambiguate = DocumentFolderService._disambiguate_path
        call_count = 0

        def selective_fail(base_path, corpus, **kwargs):
            nonlocal call_count
            call_count += 1
            # Fail on the second document only
            if call_count == 2:
                raise ValueError("suffix exhausted")
            return original_disambiguate(base_path, corpus, **kwargs)

        with patch.object(
            DocumentFolderService, "_disambiguate_path", staticmethod(selective_fail)
        ):
            moved_count, error = DocumentFolderService.move_documents_to_folder(
                user=self.owner,
                document_ids=[d.id for d in docs],
                corpus=self.corpus,
                folder=self.folder,
            )

        # All-or-nothing: zero documents moved
        self.assertEqual(moved_count, 0)
        self.assertIn("rolled back", error)

        # ALL documents must remain in their original locations
        for p in paths:
            p.refresh_from_db()
            self.assertTrue(p.is_current, f"Path {p.id} should still be current")
            self.assertIsNone(p.folder_id, f"Path {p.id} should still be at root")

        # No new DocumentPath records should have been created
        total_paths = DocumentPath.objects.filter(
            corpus=self.corpus, document__in=docs
        ).count()
        self.assertEqual(total_paths, 3, "No new paths should exist after rollback")

    def test_bulk_move_retry_after_failure_succeeds(self):
        """After a failed bulk move (full rollback), retrying with the
        underlying issue resolved should succeed cleanly."""
        docs = []
        for i in range(2):
            doc = Document.objects.create(
                title=f"Doc {i}", creator=self.owner, pdf_file=f"retry{i}.pdf"
            )
            DocumentPath.objects.create(
                document=doc,
                corpus=self.corpus,
                creator=self.owner,
                folder=None,
                path=f"/retry{i}.pdf",
                version_number=1,
                is_current=True,
                is_deleted=False,
            )
            docs.append(doc)

        # First attempt: fails
        with patch.object(
            DocumentFolderService,
            "_disambiguate_path",
            side_effect=ValueError("temporary failure"),
        ):
            moved_count, error = DocumentFolderService.move_documents_to_folder(
                user=self.owner,
                document_ids=[d.id for d in docs],
                corpus=self.corpus,
                folder=self.folder,
            )
        self.assertEqual(moved_count, 0)
        self.assertIn("rolled back", error)

        # All docs still at root
        for doc in docs:
            path = DocumentPath.objects.get(
                document=doc, corpus=self.corpus, is_current=True
            )
            self.assertIsNone(path.folder_id)

        # Second attempt: succeeds (no mock = real disambiguate)
        moved_count, error = DocumentFolderService.move_documents_to_folder(
            user=self.owner,
            document_ids=[d.id for d in docs],
            corpus=self.corpus,
            folder=self.folder,
        )
        self.assertEqual(moved_count, 2)
        self.assertEqual(error, "")

        # All docs now in target folder
        for doc in docs:
            path = DocumentPath.objects.get(
                document=doc, corpus=self.corpus, is_current=True
            )
            self.assertEqual(path.folder_id, self.folder.id)

    def test_bulk_move_within_batch_conflict_detection(self):
        """Two documents with the same filename moved to the same folder
        should both succeed with disambiguation, not conflict."""
        doc1 = Document.objects.create(
            title="Report A", creator=self.owner, pdf_file="report.pdf"
        )
        DocumentPath.objects.create(
            document=doc1,
            corpus=self.corpus,
            creator=self.owner,
            folder=None,
            path="/report.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        # Second doc with same filename but from a different source folder
        source_folder, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Source"
        )
        doc2 = Document.objects.create(
            title="Report B", creator=self.owner, pdf_file="report2.pdf"
        )
        DocumentPath.objects.create(
            document=doc2,
            corpus=self.corpus,
            creator=self.owner,
            folder=source_folder,
            path="/Source/report.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        # Move both to the same target folder — they both produce
        # "/Target/report.pdf" as the base path
        moved_count, error = DocumentFolderService.move_documents_to_folder(
            user=self.owner,
            document_ids=[doc1.id, doc2.id],
            corpus=self.corpus,
            folder=self.folder,
        )

        self.assertEqual(moved_count, 2)
        self.assertEqual(error, "")

        # Verify they got different paths
        path1 = DocumentPath.objects.get(
            document=doc1, corpus=self.corpus, is_current=True
        )
        path2 = DocumentPath.objects.get(
            document=doc2, corpus=self.corpus, is_current=True
        )
        self.assertNotEqual(path1.path, path2.path)
        self.assertEqual(path1.folder_id, self.folder.id)
        self.assertEqual(path2.folder_id, self.folder.id)

    def test_bulk_move_two_docs_same_filename_both_conflict_with_existing(self):
        """Two documents with the same filename moved to a folder that already
        contains a file with that name should all get distinct disambiguated
        paths (e.g. report_1.pdf, report_2.pdf)."""
        # Pre-existing document at /Target/report.pdf
        existing_doc = Document.objects.create(
            title="Existing", creator=self.owner, pdf_file="existing.pdf"
        )
        DocumentPath.objects.create(
            document=existing_doc,
            corpus=self.corpus,
            creator=self.owner,
            folder=self.folder,
            path="/Target/report.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        # Doc A named report.pdf at root
        doc_a = Document.objects.create(
            title="Report A", creator=self.owner, pdf_file="a.pdf"
        )
        DocumentPath.objects.create(
            document=doc_a,
            corpus=self.corpus,
            creator=self.owner,
            folder=None,
            path="/report.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        # Doc B named report.pdf in a different source folder
        source, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Source"
        )
        doc_b = Document.objects.create(
            title="Report B", creator=self.owner, pdf_file="b.pdf"
        )
        DocumentPath.objects.create(
            document=doc_b,
            corpus=self.corpus,
            creator=self.owner,
            folder=source,
            path="/Source/report.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        moved_count, error = DocumentFolderService.move_documents_to_folder(
            user=self.owner,
            document_ids=[doc_a.id, doc_b.id],
            corpus=self.corpus,
            folder=self.folder,
        )

        self.assertEqual(moved_count, 2)
        self.assertEqual(error, "")

        path_a = DocumentPath.objects.get(
            document=doc_a, corpus=self.corpus, is_current=True
        )
        path_b = DocumentPath.objects.get(
            document=doc_b, corpus=self.corpus, is_current=True
        )
        existing_path = DocumentPath.objects.get(
            document=existing_doc, corpus=self.corpus, is_current=True
        )

        # All three paths must be distinct
        all_paths = {existing_path.path, path_a.path, path_b.path}
        self.assertEqual(len(all_paths), 3)
        # The existing path is unchanged
        self.assertEqual(existing_path.path, "/Target/report.pdf")
        # Both new paths should be in /Target/ with _N suffixes
        self.assertTrue(path_a.path.startswith("/Target/report_"))
        self.assertTrue(path_b.path.startswith("/Target/report_"))


# =============================================================================
# 10. COVERAGE GAP TESTS — edge cases for uncovered code paths
# =============================================================================


class TestCoverageGapComputeMovedPathTrailingSlash(TransactionTestCase):
    """
    SCENARIO: _compute_moved_path encounters a path with a trailing slash
    (e.g. "/dir/") which produces an empty filename after rsplit.

    BUSINESS RULE: The secondary guard must raise ValueError, not silently
    produce a bad path.
    """

    def test_trailing_slash_raises_value_error(self):
        """Path '/dir/' produces empty filename after rsplit — must raise."""
        with self.assertRaises(ValueError) as ctx:
            DocumentFolderService._compute_moved_path("/dir/", None)
        self.assertIn("empty or root-only", str(ctx.exception))

    def test_nested_trailing_slash_raises_value_error(self):
        """Path '/a/b/c/' also has empty filename — must raise."""
        with self.assertRaises(ValueError) as ctx:
            DocumentFolderService._compute_moved_path("/a/b/c/", None)
        self.assertIn("empty or root-only", str(ctx.exception))


class TestCoverageGapComputeMovedPathWhitespace(TransactionTestCase):
    """
    SCENARIO: _compute_moved_path receives a whitespace-only path.

    BUSINESS RULE: Whitespace-only paths are effectively empty and must
    raise ValueError.
    """

    def test_whitespace_only_path_raises_value_error(self):
        """Path '   ' is whitespace-only — must raise."""
        with self.assertRaises(ValueError) as ctx:
            DocumentFolderService._compute_moved_path("   ", None)
        self.assertIn("empty or root-only", str(ctx.exception))

    def test_whitespace_with_slash_raises_value_error(self):
        """Path '  /  ' strips to '/' — must raise."""
        with self.assertRaises(ValueError) as ctx:
            DocumentFolderService._compute_moved_path("  /  ", None)
        self.assertIn("empty or root-only", str(ctx.exception))


class TestCoverageGapDisambiguateNoSlashPath(DocumentFolderServiceTestBase):
    """
    SCENARIO: _disambiguate_path is called with a path that has no slash
    (e.g. "report.pdf" instead of "/report.pdf").

    BUSINESS RULE: All stored paths start with "/".  A bare filename with
    no leading slash is structurally invalid and should raise ValueError
    rather than silently loading all active paths (which would mask a bug
    in the caller and degrade performance on large corpuses).
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.owner, is_public=False
        )

    def test_no_slash_path_raises_value_error(self):
        """A no-slash path raises ValueError (structurally invalid)."""
        with self.assertRaises(ValueError):
            DocumentFolderService._disambiguate_path("report.pdf", self.corpus)

    def test_no_slash_path_with_conflict_raises_value_error(self):
        """A no-slash path raises ValueError even when a conflict exists."""
        doc = Document.objects.create(
            title="Existing", creator=self.owner, pdf_file="report.pdf"
        )
        DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            creator=self.owner,
            folder=None,
            path="report.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        with self.assertRaises(ValueError):
            DocumentFolderService._disambiguate_path("report.pdf", self.corpus)

    def test_no_slash_extensionless_path_raises_value_error(self):
        """A no-slash, extensionless path raises ValueError."""
        doc = Document.objects.create(
            title="Existing", creator=self.owner, pdf_file="Makefile"
        )
        DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            creator=self.owner,
            folder=None,
            path="Makefile",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        with self.assertRaises(ValueError):
            DocumentFolderService._disambiguate_path("Makefile", self.corpus)


class TestCoverageGapBulkMoveIntegrityErrorRollback(DocumentFolderServiceTestBase):
    """
    SCENARIO: An IntegrityError during bulk move execution causes full
    atomic rollback.

    BUSINESS RULE: IntegrityError (e.g. from a concurrent path conflict
    hitting the unique constraint) is caught alongside ValueError and
    triggers the same all-or-nothing rollback.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.owner, is_public=False
        )
        self.folder, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Target"
        )

    def test_integrity_error_during_bulk_move_rolls_back(self):
        """IntegrityError during bulk insert rolls back the entire batch."""
        doc = Document.objects.create(
            title="Doc 1", creator=self.owner, pdf_file="doc1.pdf"
        )
        original_path = DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            creator=self.owner,
            folder=None,
            path="/doc1.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        # Simulate the ``unique_active_path_per_corpus`` partial unique
        # constraint violating on the batched INSERT (the DB-level guard
        # that catches TOCTOU races — see _disambiguate_path docstring).
        def failing_bulk_create(*args, **kwargs):
            raise IntegrityError("unique_active_path_per_corpus")

        with patch.object(
            DocumentPath.objects, "bulk_create", side_effect=failing_bulk_create
        ):
            moved_count, error = DocumentFolderService.move_documents_to_folder(
                user=self.owner,
                document_ids=[doc.id],
                corpus=self.corpus,
                folder=self.folder,
            )

        self.assertEqual(moved_count, 0)
        self.assertIn("rolled back", error)

        # Original path must still be current
        original_path.refresh_from_db()
        self.assertTrue(original_path.is_current)
        self.assertIsNone(original_path.folder_id)


class TestCoverageGapBulkMoveToRootRollback(DocumentFolderServiceTestBase):
    """
    SCENARIO: Bulk move to root (folder=None) fails and rolls back.

    BUSINESS RULE: The error handler's 'folder.id if folder else root'
    branch is exercised when folder is None.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.owner, is_public=False
        )
        self.source_folder, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Source"
        )

    def test_bulk_move_to_root_integrity_error_rolls_back(self):
        """IntegrityError when moving to root (folder=None) rolls back."""
        doc = Document.objects.create(
            title="Doc", creator=self.owner, pdf_file="doc.pdf"
        )
        original_path = DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            creator=self.owner,
            folder=self.source_folder,
            path="/Source/doc.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        def failing_bulk_create(*args, **kwargs):
            raise IntegrityError("unique_active_path_per_corpus")

        with patch.object(
            DocumentPath.objects, "bulk_create", side_effect=failing_bulk_create
        ):
            moved_count, error = DocumentFolderService.move_documents_to_folder(
                user=self.owner,
                document_ids=[doc.id],
                corpus=self.corpus,
                folder=None,  # Move to root
            )

        self.assertEqual(moved_count, 0)
        self.assertIn("rolled back", error)

        original_path.refresh_from_db()
        self.assertTrue(original_path.is_current)
        self.assertEqual(original_path.folder_id, self.source_folder.id)


class TestMoveDocumentIntegrityRecovery(DocumentFolderServiceTestBase):
    """
    SCENARIO: A transient IntegrityError on the
    ``unique_active_path_per_corpus`` partial unique index — caused by a
    concurrent transaction claiming the same target path between
    ``_disambiguate_path``'s SELECT and ``DocumentPath.objects.create``'s
    INSERT — is automatically recovered via retry inside
    ``_create_successor_path_with_retry``.

    BUSINESS RULE: Callers do not have to retry move operations on
    transient races; the helper retries with a fresh disambiguation
    (treating the lost path as occupied) until either an attempt succeeds
    or ``MAX_PATH_CREATE_RETRIES`` is exhausted.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.owner, is_public=False
        )
        self.folder, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Target"
        )
        self.document = Document.objects.create(
            title="Race Doc", creator=self.owner, pdf_file="race.pdf"
        )
        self.original_path = DocumentPath.objects.create(
            document=self.document,
            corpus=self.corpus,
            creator=self.owner,
            folder=None,
            path="/race.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

    def test_first_attempt_fails_second_succeeds(self):
        """A single IntegrityError on create is recovered by retrying with
        a freshly disambiguated path."""
        original_create = DocumentPath.objects.create
        attempts = {"count": 0}

        def flaky_create(**kwargs):
            # Only fail successor inserts (parent is set), and only on
            # the very first attempt; subsequent attempts succeed.
            if kwargs.get("parent") is not None:
                attempts["count"] += 1
                if attempts["count"] == 1:
                    raise _make_constraint_error()
            return original_create(**kwargs)

        with patch.object(DocumentPath.objects, "create", side_effect=flaky_create):
            success, error = DocumentFolderService.move_document_to_folder(
                user=self.owner,
                document=self.document,
                corpus=self.corpus,
                folder=self.folder,
            )

        self.assertTrue(success, f"Retry should succeed, got error: {error}")
        self.assertEqual(error, "")
        # The mock fails on attempt 1 and succeeds on attempt 2 — exactly 2 creates.
        self.assertEqual(attempts["count"], 2)

        # The new path should be committed and live in the target folder
        new_path = DocumentPath.objects.get(
            document=self.document,
            corpus=self.corpus,
            is_current=True,
            is_deleted=False,
        )
        self.assertEqual(new_path.folder_id, self.folder.id)
        self.assertEqual(new_path.parent_id, self.original_path.id)

        # The original path is no longer current
        self.original_path.refresh_from_db()
        self.assertFalse(self.original_path.is_current)

    def test_retry_uses_disambiguated_path_after_loss(self):
        """After an IntegrityError, the next disambiguation should treat
        the previously-tried path as occupied and pick a different one."""
        original_create = DocumentPath.objects.create
        observed_paths: list[str] = []

        def flaky_create(**kwargs):
            if kwargs.get("parent") is not None:
                observed_paths.append(kwargs["path"])
                if len(observed_paths) == 1:
                    raise _make_constraint_error()
            return original_create(**kwargs)

        with patch.object(DocumentPath.objects, "create", side_effect=flaky_create):
            success, error = DocumentFolderService.move_document_to_folder(
                user=self.owner,
                document=self.document,
                corpus=self.corpus,
                folder=self.folder,
            )

        self.assertTrue(success, f"Retry should succeed, got error: {error}")
        self.assertEqual(len(observed_paths), 2)
        # Second attempt must have used a different disambiguated path
        self.assertNotEqual(
            observed_paths[0],
            observed_paths[1],
            "Retry should use a fresh disambiguated path, not the same one",
        )

    def test_persistent_failure_returns_error_after_exhausting_retries(self):
        """If every attempt fails, the move ultimately surfaces a path
        conflict error and the original path remains active."""
        original_create = DocumentPath.objects.create
        attempts = {"count": 0}

        def always_failing_create(**kwargs):
            if kwargs.get("parent") is not None:
                attempts["count"] += 1
                raise _make_constraint_error()
            return original_create(**kwargs)

        with patch.object(
            DocumentPath.objects, "create", side_effect=always_failing_create
        ):
            success, error = DocumentFolderService.move_document_to_folder(
                user=self.owner,
                document=self.document,
                corpus=self.corpus,
                folder=self.folder,
            )

        self.assertFalse(success)
        self.assertIn(PATH_CONFLICT_MSG, error)
        # All MAX_PATH_CREATE_RETRIES + 1 attempts must have run
        self.assertEqual(attempts["count"], MAX_PATH_CREATE_RETRIES + 1)

        # The original path must still be the active one — savepoint
        # rollbacks must have restored is_current=True after every loss.
        self.original_path.refresh_from_db()
        self.assertTrue(self.original_path.is_current)
        self.assertIsNone(self.original_path.folder_id)

    def test_non_constraint_integrity_error_is_not_retried(self):
        """An IntegrityError that does NOT mention the partial unique
        constraint should propagate immediately without retry."""
        original_create = DocumentPath.objects.create
        attempts = {"count": 0}

        def fk_violation_create(**kwargs):
            if kwargs.get("parent") is not None:
                attempts["count"] += 1
                raise IntegrityError("null value in column 'corpus_id'")
            return original_create(**kwargs)

        with patch.object(
            DocumentPath.objects, "create", side_effect=fk_violation_create
        ):
            success, error = DocumentFolderService.move_document_to_folder(
                user=self.owner,
                document=self.document,
                corpus=self.corpus,
                folder=self.folder,
            )

        # Should fail immediately on the first attempt (no retries)
        self.assertEqual(attempts["count"], 1)
        self.assertFalse(success)
        # The non-constraint IntegrityError is re-raised from the helper and
        # caught by move_document_to_folder's outer IntegrityError handler,
        # which formats a PATH_CONFLICT_MSG error string.
        self.assertIn(PATH_CONFLICT_MSG, error)


class TestCoverageGapDeleteFolderMultiDocHistory(DocumentFolderServiceTestBase):
    """
    SCENARIO: Deleting a folder with multiple documents creates a history
    node for each document.

    BUSINESS RULE: Every document displaced by folder deletion gets its
    own history entry with proper parent chain and version preservation.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.owner, is_public=False
        )

    def test_delete_folder_creates_history_for_multiple_documents(self):
        """Each document in a deleted folder gets a proper history node."""
        folder, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="ToDelete"
        )

        docs_and_paths = []
        for i in range(3):
            doc = Document.objects.create(
                title=f"Doc {i}", creator=self.owner, pdf_file=f"doc{i}.pdf"
            )
            path = DocumentPath.objects.create(
                document=doc,
                corpus=self.corpus,
                creator=self.owner,
                folder=folder,
                path=f"/ToDelete/doc{i}.pdf",
                version_number=1,
                is_current=True,
                is_deleted=False,
            )
            docs_and_paths.append((doc, path))

        success, error = DocumentFolderService.delete_folder(
            user=self.owner, folder=folder
        )
        self.assertTrue(success)
        self.assertEqual(error, "")

        for doc, original_path in docs_and_paths:
            # Each doc should have 2 path records (original + moved)
            total = DocumentPath.objects.filter(
                document=doc, corpus=self.corpus
            ).count()
            self.assertEqual(total, 2, f"Doc {doc.title} should have 2 paths")

            # Current path should be at root with parent link
            current = DocumentPath.objects.get(
                document=doc, corpus=self.corpus, is_current=True, is_deleted=False
            )
            self.assertIsNone(current.folder_id)
            self.assertEqual(current.parent_id, original_path.id)
            self.assertEqual(current.version_number, 1)

            # Original path should be marked not current
            original_path.refresh_from_db()
            self.assertFalse(original_path.is_current)


class TestCoverageGapBulkMoveVersionPreservation(DocumentFolderServiceTestBase):
    """
    SCENARIO: Bulk move preserves version numbers and creates proper
    parent chain for each document.

    BUSINESS RULE: Moves do not bump version numbers, and each new
    DocumentPath links back to its predecessor.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.owner, is_public=False
        )
        self.folder, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Target"
        )

    def test_bulk_move_preserves_version_and_parent_chain(self):
        """Bulk move preserves version_number and sets parent correctly."""
        docs = []
        original_paths = []
        for i in range(3):
            doc = Document.objects.create(
                title=f"Doc {i}", creator=self.owner, pdf_file=f"doc{i}.pdf"
            )
            path = DocumentPath.objects.create(
                document=doc,
                corpus=self.corpus,
                creator=self.owner,
                folder=None,
                path=f"/doc{i}.pdf",
                version_number=i + 1,  # Different versions
                is_current=True,
                is_deleted=False,
            )
            docs.append(doc)
            original_paths.append(path)

        moved_count, error = DocumentFolderService.move_documents_to_folder(
            user=self.owner,
            document_ids=[d.id for d in docs],
            corpus=self.corpus,
            folder=self.folder,
        )

        self.assertEqual(moved_count, 3)
        self.assertEqual(error, "")

        for i, (doc, original_path) in enumerate(zip(docs, original_paths)):
            current = DocumentPath.objects.get(
                document=doc, corpus=self.corpus, is_current=True, is_deleted=False
            )
            # Version preserved (not incremented)
            self.assertEqual(
                current.version_number,
                i + 1,
                f"Doc {i} version should be preserved",
            )
            # Parent chain links back
            self.assertEqual(
                current.parent_id,
                original_path.id,
                f"Doc {i} parent should link to original",
            )
            # Folder updated
            self.assertEqual(current.folder_id, self.folder.id)
            # Path updated
            self.assertIn(f"/Target/doc{i}.pdf", current.path)

            # Original marked not current
            original_path.refresh_from_db()
            self.assertFalse(original_path.is_current)


class TestCoverageGapDeleteFolderIntegrityErrorRollback(DocumentFolderServiceTestBase):
    """
    SCENARIO: An IntegrityError during delete_folder's bulk_create causes
    full atomic rollback.

    BUSINESS RULE: delete_folder uses the same bulk_create -> signal dispatch
    pattern as move_documents_to_folder.  An IntegrityError (e.g. from a
    concurrent path conflict hitting the unique constraint) after the
    filter().update(is_current=False) must roll back both the deactivation
    and the folder deletion.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.owner, is_public=False
        )

    def test_delete_folder_integrity_error_during_bulk_create_rolls_back(self):
        """IntegrityError during bulk_create rolls back delete_folder entirely."""
        folder, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="ToDelete"
        )
        doc = Document.objects.create(
            title="Doc 1", creator=self.owner, pdf_file="doc1.pdf"
        )
        original_path = DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            creator=self.owner,
            folder=folder,
            path="/ToDelete/doc1.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        def failing_bulk_create(*args, **kwargs):
            raise IntegrityError("unique_active_path_per_corpus")

        with patch.object(
            DocumentPath.objects, "bulk_create", side_effect=failing_bulk_create
        ):
            success, error = DocumentFolderService.delete_folder(
                user=self.owner, folder=folder
            )

        self.assertFalse(success)
        self.assertIn("rolled back", error)

        # Folder must still exist
        self.assertTrue(CorpusFolder.objects.filter(pk=folder.pk).exists())

        # Original path must still be current and in the folder
        original_path.refresh_from_db()
        self.assertTrue(original_path.is_current)
        self.assertEqual(original_path.folder_id, folder.id)


class TestCoverageGapTargetDirectoryStringFromPathEdgeCases(
    DocumentFolderServiceTestBase
):
    """
    SCENARIO: _target_directory_string_from_path raises on an empty
    non-root path and normalises the root-equivalent inputs ('/' and
    ``None``) to the canonical root directory.

    BUSINESS RULE: A non-root folder whose path resolves to empty is a
    data integrity violation.  The method must raise ValueError rather
    than producing the malformed directory string "//".  The literal
    "/" and ``None``, however, are legitimate root-equivalent inputs and
    must normalise to "/".
    """

    def test_raises_on_empty_string(self):
        """ValueError raised when folder_path is empty after stripping."""
        with self.assertRaises(ValueError):
            DocumentFolderService._target_directory_string_from_path("")

    def test_slash_normalises_to_root(self):
        """Bare '/' is treated as the root directory (not an error)."""
        self.assertEqual(
            DocumentFolderService._target_directory_string_from_path("/"), "/"
        )

    def test_root_returns_slash(self):
        """None (root) returns '/'."""
        self.assertEqual(
            DocumentFolderService._target_directory_string_from_path(None), "/"
        )

    def test_normal_path(self):
        """Normal folder path returns canonical directory string."""
        self.assertEqual(
            DocumentFolderService._target_directory_string_from_path("Legal/Contracts"),
            "/Legal/Contracts/",
        )


class TestCoverageGapBulkMoveGetPathCallCount(DocumentFolderServiceTestBase):
    """
    SCENARIO: Bulk move caches the target folder path before the loop.

    BUSINESS RULE: CorpusFolder.get_path() issues a recursive CTE query per
    invocation.  The bulk-move method must resolve the target folder's path
    exactly once, regardless of how many documents are moved.  This test
    locks in that performance invariant so a future refactor cannot
    accidentally regress to O(N) CTE queries.
    """

    def setUp(self):
        super().setUp()
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.owner, is_public=False
        )
        self.folder, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Target"
        )

    def test_bulk_move_calls_get_path_once(self):
        """get_path() is called at most once during a bulk move (cached path)."""
        docs = []
        for i in range(5):
            doc = Document.objects.create(
                title=f"Doc {i}", creator=self.owner, pdf_file=f"doc{i}.pdf"
            )
            DocumentPath.objects.create(
                document=doc,
                corpus=self.corpus,
                creator=self.owner,
                folder=None,
                path=f"/doc{i}.pdf",
                version_number=1,
                is_current=True,
                is_deleted=False,
            )
            docs.append(doc)

        original_get_path = CorpusFolder.get_path

        with patch.object(
            CorpusFolder, "get_path", autospec=True, side_effect=original_get_path
        ) as mock_get_path:
            moved_count, error = DocumentFolderService.move_documents_to_folder(
                user=self.owner,
                document_ids=[d.id for d in docs],
                corpus=self.corpus,
                folder=self.folder,
            )

        self.assertEqual(moved_count, 5)
        self.assertEqual(error, "")
        self.assertEqual(
            mock_get_path.call_count,
            1,
            f"get_path() should be called exactly once for a bulk move of "
            f"{len(docs)} documents, but was called {mock_get_path.call_count} "
            f"times — the cached path optimisation may have regressed",
        )
