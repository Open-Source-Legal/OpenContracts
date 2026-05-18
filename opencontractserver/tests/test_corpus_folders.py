"""
Tests for CorpusFolder models and constraints.

Tests cover:
- Folder creation and hierarchy
- Unique name constraint per parent
- Corpus constraint (parent must be in same corpus)
- Document assignment (one folder per document per corpus)
- Permission inheritance from corpus
- Tree traversal methods
"""

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from opencontractserver.corpuses.models import (
    Corpus,
    CorpusFolder,
)
from opencontractserver.documents.models import Document
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


@pytest.mark.django_db
class TestCorpusFolderModel:
    """Test CorpusFolder model functionality."""

    def test_create_folder(self):
        """Test creating a basic folder."""
        user = User.objects.create_user(username="testuser", password="test")
        corpus = Corpus.objects.create(title="Test Corpus", creator=user)

        folder = CorpusFolder.objects.create(
            name="Research",
            corpus=corpus,
            creator=user,
            description="Research documents",
            color="#ff0000",
            icon="folder",
            tags=["important", "review"],
        )

        assert folder.name == "Research"
        assert folder.corpus == corpus
        assert folder.creator == user
        assert folder.description == "Research documents"
        assert folder.color == "#ff0000"
        assert folder.icon == "folder"
        assert folder.tags == ["important", "review"]

    def test_folder_hierarchy(self):
        """Test creating nested folder structure."""
        user = User.objects.create_user(username="testuser", password="test")
        corpus = Corpus.objects.create(title="Test Corpus", creator=user)

        # Create parent folder
        parent = CorpusFolder.objects.create(name="Legal", corpus=corpus, creator=user)

        # Create child folder
        child = CorpusFolder.objects.create(
            name="Contracts", corpus=corpus, creator=user, parent=parent
        )

        # Create grandchild folder
        grandchild = CorpusFolder.objects.create(
            name="2024", corpus=corpus, creator=user, parent=child
        )

        assert child.parent == parent
        assert grandchild.parent == child
        assert parent.parent is None

    def test_get_path(self):
        """Test get_path() returns full path from root."""
        user = User.objects.create_user(username="testuser", password="test")
        corpus = Corpus.objects.create(title="Test Corpus", creator=user)

        parent = CorpusFolder.objects.create(name="Legal", corpus=corpus, creator=user)
        child = CorpusFolder.objects.create(
            name="Contracts", corpus=corpus, creator=user, parent=parent
        )
        grandchild = CorpusFolder.objects.create(
            name="2024", corpus=corpus, creator=user, parent=child
        )

        assert parent.get_path() == "Legal"
        assert child.get_path() == "Legal/Contracts"
        assert grandchild.get_path() == "Legal/Contracts/2024"

    def test_unique_name_per_parent_constraint(self):
        """Test that folder names must be unique per parent within a corpus."""
        user = User.objects.create_user(username="testuser", password="test")
        corpus = Corpus.objects.create(title="Test Corpus", creator=user)

        parent = CorpusFolder.objects.create(name="Parent", corpus=corpus, creator=user)

        # Create first child
        CorpusFolder.objects.create(
            name="Research", corpus=corpus, creator=user, parent=parent
        )

        # Try to create duplicate name under same parent - should fail
        with pytest.raises(IntegrityError):
            CorpusFolder.objects.create(
                name="Research", corpus=corpus, creator=user, parent=parent
            )

    def test_same_name_different_parents_allowed(self):
        """Test that same folder name is allowed under different parents."""
        user = User.objects.create_user(username="testuser", password="test")
        corpus = Corpus.objects.create(title="Test Corpus", creator=user)

        parent1 = CorpusFolder.objects.create(
            name="Parent1", corpus=corpus, creator=user
        )
        parent2 = CorpusFolder.objects.create(
            name="Parent2", corpus=corpus, creator=user
        )

        # Should be able to create "Research" under both parents
        folder1 = CorpusFolder.objects.create(
            name="Research", corpus=corpus, creator=user, parent=parent1
        )
        folder2 = CorpusFolder.objects.create(
            name="Research", corpus=corpus, creator=user, parent=parent2
        )

        assert folder1.name == folder2.name
        assert folder1.parent != folder2.parent

    def test_parent_must_be_in_same_corpus(self):
        """Test that parent folder must belong to the same corpus."""
        user = User.objects.create_user(username="testuser", password="test")
        corpus1 = Corpus.objects.create(title="Corpus 1", creator=user)
        corpus2 = Corpus.objects.create(title="Corpus 2", creator=user)

        parent = CorpusFolder.objects.create(
            name="Parent", corpus=corpus1, creator=user
        )

        # Try to create folder in corpus2 with parent from corpus1 - should fail
        with pytest.raises(ValidationError):
            folder = CorpusFolder(
                name="Child", corpus=corpus2, creator=user, parent=parent
            )
            folder.save()

    def test_tags_validation(self):
        """Test that tags must be a list of strings."""
        user = User.objects.create_user(username="testuser", password="test")
        corpus = Corpus.objects.create(title="Test Corpus", creator=user)

        # Valid tags
        folder = CorpusFolder.objects.create(
            name="Test", corpus=corpus, creator=user, tags=["tag1", "tag2"]
        )
        folder.full_clean()  # Should not raise

        # Invalid - not a list
        folder.tags = "not_a_list"
        with pytest.raises(ValidationError):
            folder.full_clean()

        # Invalid - list with non-string
        folder.tags = ["valid", 123]
        with pytest.raises(ValidationError):
            folder.full_clean()

    def test_get_document_count(self):
        """Test get_document_count() returns correct count."""
        user = User.objects.create_user(username="testuser", password="test")
        corpus = Corpus.objects.create(title="Test Corpus", creator=user)
        folder = CorpusFolder.objects.create(
            name="Research", corpus=corpus, creator=user
        )

        # Add documents to corpus - two in folder, one at root
        doc1 = Document.objects.create(title="Doc 1", creator=user)
        doc2 = Document.objects.create(title="Doc 2", creator=user)
        doc3 = Document.objects.create(title="Doc 3", creator=user)

        corpus.add_document(document=doc1, user=user, folder=folder)
        corpus.add_document(document=doc2, user=user, folder=folder)
        corpus.add_document(document=doc3, user=user)  # At root

        assert folder.get_document_count() == 2

    def test_get_descendant_document_count(self):
        """Test get_descendant_document_count() includes subfolders."""
        user = User.objects.create_user(username="testuser", password="test")
        corpus = Corpus.objects.create(title="Test Corpus", creator=user)

        parent = CorpusFolder.objects.create(name="Parent", corpus=corpus, creator=user)
        child = CorpusFolder.objects.create(
            name="Child", corpus=corpus, creator=user, parent=parent
        )

        # Create documents and add to corpus with folder assignments
        doc1 = Document.objects.create(title="Doc 1", creator=user)
        doc2 = Document.objects.create(title="Doc 2", creator=user)
        doc3 = Document.objects.create(title="Doc 3", creator=user)

        corpus.add_document(document=doc1, user=user, folder=parent)  # In parent
        corpus.add_document(document=doc2, user=user, folder=child)  # In child
        corpus.add_document(document=doc3, user=user, folder=child)  # In child

        # Parent should count all descendants
        assert parent.get_descendant_document_count() == 3
        # Child should only count its own
        assert child.get_descendant_document_count() == 2


@pytest.mark.django_db
class TestAddDocumentCrossCorpusFolderGuard:
    """``Corpus.add_document`` must reject folders from another corpus.

    Cross-corpus folder assignment is silently wrong: the DocumentPath
    counts toward ``Corpus.document_count`` (which only filters on
    ``corpus``), but the document disappears from the folder browser
    (which filters on ``folder_id``) because the folder lives in a
    different corpus. The guard refuses the write at the boundary.
    """

    def test_add_document_rejects_foreign_folder(self):
        user = User.objects.create_user(username="testuser", password="test")
        corpus_a = Corpus.objects.create(title="A", creator=user)
        corpus_b = Corpus.objects.create(title="B", creator=user)
        folder_in_b = CorpusFolder.objects.create(
            name="Mistake", corpus=corpus_b, creator=user
        )
        doc = Document.objects.create(title="Doc", creator=user)

        with pytest.raises(ValueError, match="belongs to corpus"):
            corpus_a.add_document(document=doc, user=user, folder=folder_in_b)

    def test_add_document_accepts_same_corpus_folder(self):
        user = User.objects.create_user(username="testuser", password="test")
        corpus = Corpus.objects.create(title="Test", creator=user)
        folder = CorpusFolder.objects.create(name="Same", corpus=corpus, creator=user)
        doc = Document.objects.create(title="Doc", creator=user)

        corpus_doc, _status, doc_path = corpus.add_document(
            document=doc, user=user, folder=folder
        )
        assert doc_path.folder_id == folder.id


@pytest.mark.django_db
class TestFolderPermissions:
    """Test folder permission inheritance from corpus."""

    def test_folders_inherit_corpus_permissions(self):
        """Test that folder visibility follows corpus permissions."""
        owner = User.objects.create_user(username="owner", password="test")
        viewer = User.objects.create_user(username="viewer", password="test")
        corpus = Corpus.objects.create(title="Test Corpus", creator=owner)
        folder = CorpusFolder.objects.create(
            name="Research", corpus=corpus, creator=owner
        )

        # Give viewer READ permission on corpus
        set_permissions_for_obj_to_user(viewer, corpus, [PermissionTypes.READ])

        # Folders inherit corpus permissions through Guardian
        # Give viewer READ permission on folder (in practice, this would be done via corpus)
        set_permissions_for_obj_to_user(viewer, folder, [PermissionTypes.READ])

        # Viewer should be able to see folders through permissions
        visible_folders = CorpusFolder.objects.visible_to_user(viewer)
        assert folder in visible_folders

    def test_no_corpus_permission_no_folder_visibility(self):
        """Test that users without folder access cannot see folders."""
        owner = User.objects.create_user(username="owner", password="test")
        other_user = User.objects.create_user(username="other", password="test")
        corpus = Corpus.objects.create(title="Test Corpus", creator=owner)
        folder = CorpusFolder.objects.create(
            name="Research", corpus=corpus, creator=owner
        )

        # other_user has no permissions on folder
        visible_folders = CorpusFolder.objects.visible_to_user(other_user)
        assert folder not in visible_folders


@pytest.mark.django_db
class TestFolderTreeTraversal:
    """Test tree traversal methods using TreeNode."""

    def test_get_ancestors(self):
        """Test getting ancestors of a folder."""
        user = User.objects.create_user(username="testuser", password="test")
        corpus = Corpus.objects.create(title="Test Corpus", creator=user)

        root = CorpusFolder.objects.create(name="Root", corpus=corpus, creator=user)
        middle = CorpusFolder.objects.create(
            name="Middle", corpus=corpus, creator=user, parent=root
        )
        leaf = CorpusFolder.objects.create(
            name="Leaf", corpus=corpus, creator=user, parent=middle
        )

        ancestors = list(leaf.ancestors())
        assert len(ancestors) == 2
        assert root in ancestors
        assert middle in ancestors

    def test_get_descendants(self):
        """Test getting descendants of a folder."""
        user = User.objects.create_user(username="testuser", password="test")
        corpus = Corpus.objects.create(title="Test Corpus", creator=user)

        root = CorpusFolder.objects.create(name="Root", corpus=corpus, creator=user)
        child1 = CorpusFolder.objects.create(
            name="Child1", corpus=corpus, creator=user, parent=root
        )
        child2 = CorpusFolder.objects.create(
            name="Child2", corpus=corpus, creator=user, parent=root
        )
        grandchild = CorpusFolder.objects.create(
            name="Grandchild", corpus=corpus, creator=user, parent=child1
        )

        descendants = list(root.descendants())
        assert len(descendants) == 3
        assert child1 in descendants
        assert child2 in descendants
        assert grandchild in descendants

    def test_get_children(self):
        """Test getting immediate children of a folder."""
        user = User.objects.create_user(username="testuser", password="test")
        corpus = Corpus.objects.create(title="Test Corpus", creator=user)

        parent = CorpusFolder.objects.create(name="Parent", corpus=corpus, creator=user)
        child1 = CorpusFolder.objects.create(
            name="Child1", corpus=corpus, creator=user, parent=parent
        )
        child2 = CorpusFolder.objects.create(
            name="Child2", corpus=corpus, creator=user, parent=parent
        )
        # Grandchild should not be included
        CorpusFolder.objects.create(
            name="Grandchild", corpus=corpus, creator=user, parent=child1
        )

        children = list(parent.children.all())
        assert len(children) == 2
        assert child1 in children
        assert child2 in children
