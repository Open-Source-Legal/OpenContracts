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

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TransactionTestCase

from opencontractserver.corpuses.folder_service import DocumentFolderService
from opencontractserver.corpuses.models import (
    Corpus,
    CorpusFolder,
)
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


# =============================================================================
# BASE TEST CLASS - Disconnects signals to prevent Celery tasks
# =============================================================================


class DocumentFolderServiceTestBase(TransactionTestCase):
    """
    Base test class for document folder service tests.

    Note: Signal management is handled globally by conftest.py fixture
    `disable_document_processing_signals` - no need to disconnect/reconnect here.
    """

    pass


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
        self.assertTrue(
            DocumentFolderService.check_corpus_read_permission(
                self.creator, self.corpus
            )
        )

    def test_creator_can_write_to_corpus(self):
        """Creator should have WRITE (UPDATE) permission on their corpus."""
        self.assertTrue(
            DocumentFolderService.check_corpus_write_permission(
                self.creator, self.corpus
            )
        )

    def test_creator_can_delete_from_corpus(self):
        """Creator should have DELETE permission on their corpus."""
        self.assertTrue(
            DocumentFolderService.check_corpus_delete_permission(
                self.creator, self.corpus
            )
        )


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
        self.assertTrue(
            DocumentFolderService.check_corpus_read_permission(
                self.superuser, self.corpus
            )
        )

    def test_superuser_can_write_to_any_corpus(self):
        """Superuser should have WRITE permission on any corpus."""
        self.assertTrue(
            DocumentFolderService.check_corpus_write_permission(
                self.superuser, self.corpus
            )
        )

    def test_superuser_can_delete_from_any_corpus(self):
        """Superuser should have DELETE permission on any corpus."""
        self.assertTrue(
            DocumentFolderService.check_corpus_delete_permission(
                self.superuser, self.corpus
            )
        )


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
        self.assertTrue(
            DocumentFolderService.check_corpus_read_permission(
                self.random_user, self.corpus
            )
        )

    def test_random_user_cannot_write_to_public_corpus(self):
        """
        SECURITY: Users without explicit permission CANNOT write to public corpus.
        Public means readable, NOT editable.
        """
        self.assertFalse(
            DocumentFolderService.check_corpus_write_permission(
                self.random_user, self.corpus
            )
        )

    def test_random_user_cannot_delete_from_public_corpus(self):
        """
        SECURITY: Users without explicit permission CANNOT delete from public corpus.
        """
        self.assertFalse(
            DocumentFolderService.check_corpus_delete_permission(
                self.random_user, self.corpus
            )
        )


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

        self.assertTrue(
            DocumentFolderService.check_corpus_read_permission(self.reader, self.corpus)
        )

    def test_explicit_read_permission_does_not_grant_write_access(self):
        """User with only READ permission CANNOT write."""
        set_permissions_for_obj_to_user(
            self.reader, self.corpus, [PermissionTypes.READ]
        )

        self.assertFalse(
            DocumentFolderService.check_corpus_write_permission(
                self.reader, self.corpus
            )
        )

    def test_explicit_update_permission_grants_write_access(self):
        """User with explicit UPDATE permission can write to the corpus."""
        set_permissions_for_obj_to_user(
            self.editor, self.corpus, [PermissionTypes.UPDATE]
        )

        self.assertTrue(
            DocumentFolderService.check_corpus_write_permission(
                self.editor, self.corpus
            )
        )

    def test_explicit_delete_permission_grants_delete_access(self):
        """User with explicit DELETE permission can delete from the corpus."""
        set_permissions_for_obj_to_user(
            self.deleter, self.corpus, [PermissionTypes.DELETE]
        )

        self.assertTrue(
            DocumentFolderService.check_corpus_delete_permission(
                self.deleter, self.corpus
            )
        )


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
        self.assertFalse(
            DocumentFolderService.check_corpus_read_permission(
                self.stranger, self.corpus
            )
        )

    def test_stranger_cannot_write_to_private_corpus(self):
        """User without any permission cannot write to private corpus."""
        self.assertFalse(
            DocumentFolderService.check_corpus_write_permission(
                self.stranger, self.corpus
            )
        )

    def test_stranger_cannot_delete_from_private_corpus(self):
        """User without any permission cannot delete from private corpus."""
        self.assertFalse(
            DocumentFolderService.check_corpus_delete_permission(
                self.stranger, self.corpus
            )
        )


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
            DocumentFolderService.check_corpus_read_permission(
                self.anonymous, self.public_corpus
            )
        )

    def test_anonymous_cannot_read_private_corpus(self):
        """Anonymous user cannot read private corpus."""
        self.assertFalse(
            DocumentFolderService.check_corpus_read_permission(
                self.anonymous, self.private_corpus
            )
        )

    def test_anonymous_cannot_write_to_public_corpus(self):
        """SECURITY: Anonymous user CANNOT write even to public corpus."""
        self.assertFalse(
            DocumentFolderService.check_corpus_write_permission(
                self.anonymous, self.public_corpus
            )
        )

    def test_anonymous_cannot_delete_from_public_corpus(self):
        """SECURITY: Anonymous user CANNOT delete even from public corpus."""
        self.assertFalse(
            DocumentFolderService.check_corpus_delete_permission(
                self.anonymous, self.public_corpus
            )
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
        """Documents in deleted folder are moved to corpus root."""
        folder, _ = DocumentFolderService.create_folder(
            user=self.owner, corpus=self.corpus, name="Folder With Docs"
        )

        # Create document and put it in folder
        document = Document.objects.create(
            title="Test Doc", creator=self.owner, pdf_file="test.pdf"
        )
        DocumentPath.objects.create(
            document=document,
            corpus=self.corpus,
            creator=self.owner,
            folder=folder,
            path="/test.pdf",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        # Delete the folder
        DocumentFolderService.delete_folder(user=self.owner, folder=folder)

        # Document should now have no folder (at root)
        path = DocumentPath.objects.get(
            document=document, corpus=self.corpus, is_current=True
        )
        self.assertIsNone(path.folder)

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
        self.document_path.refresh_from_db()
        self.assertEqual(self.document_path.folder, self.folder_a)

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
        self.document_path.refresh_from_db()
        self.assertEqual(self.document_path.folder, self.folder_b)

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
        self.document_path.refresh_from_db()
        self.assertIsNone(self.document_path.folder)

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

    BUSINESS RULE: Every lifecycle event creates a new DocumentPath node (Rule P1).
    This maintains complete history and enables undo/restore.
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
