"""
Tests for corpus folder GraphQL mutations.

Tests cover:
- Creating folders
- Updating folder properties
- Moving folders to different parents
- Deleting folders (with and without contents)
- Moving documents to folders
- Bulk moving documents
- Permission checks for all operations
"""

import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.corpuses.models import (
    Corpus,
    CorpusDocumentFolder,
    CorpusFolder,
)
from opencontractserver.documents.models import Document
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class TestContext:
    """Test context for GraphQL client."""

    def __init__(self, user):
        self.user = user


class TestCreateCorpusFolderMutation(TestCase):
    """Test CreateCorpusFolder mutation."""

    MUTATION = """
        mutation CreateFolder(
            $corpusId: ID!
            $name: String!
            $parentId: ID
            $description: String
            $color: String
            $icon: String
            $tags: [String]
        ) {
            createCorpusFolder(
                corpusId: $corpusId
                name: $name
                parentId: $parentId
                description: $description
                color: $color
                icon: $icon
                tags: $tags
            ) {
                ok
                message
                folder {
                    id
                    name
                    description
                    color
                    icon
                    tags
                    parent {
                        id
                    }
                }
            }
        }
    """

    def test_create_root_folder(self):
        """Test creating a folder at corpus root."""
        user = User.objects.create_user(username="testuser", password="test")
        corpus = Corpus.objects.create(title="Test Corpus", creator=user)

        # Give user CREATE permission
        set_permissions_for_obj_to_user(user, corpus, [PermissionTypes.CREATE])

        variables = {
            "corpusId": to_global_id("CorpusType", corpus.id),
            "name": "Research",
            "description": "Research documents",
            "color": "#ff0000",
            "icon": "folder",
            "tags": ["important", "review"],
        }

        client = Client(schema, context_value=TestContext(user))
        result = client.execute(self.MUTATION, variable_values=variables)

        # Debug: print full result
        if result.get("errors"):
            print(f"GraphQL Errors: {result['errors']}")
        if not result.get("data", {}).get("createCorpusFolder", {}).get("ok"):
            print(f"Full result: {result}")
            print(
                f"Message: {result.get('data', {}).get('createCorpusFolder', {}).get('message')}"
            )

        assert result["data"]["createCorpusFolder"]["ok"] is True
        folder_data = result["data"]["createCorpusFolder"]["folder"]
        assert folder_data["name"] == "Research"
        assert folder_data["description"] == "Research documents"
        assert folder_data["color"] == "#ff0000"
        assert folder_data["icon"] == "folder"
        # Tags come back as JSON string from GraphQL
        tags = (
            json.loads(folder_data["tags"])
            if isinstance(folder_data["tags"], str)
            else folder_data["tags"]
        )
        assert tags == ["important", "review"]
        assert folder_data["parent"] is None

    def test_create_nested_folder(self):
        """Test creating a folder under a parent."""
        user = User.objects.create_user(username="testuser", password="test")
        corpus = Corpus.objects.create(title="Test Corpus", creator=user)
        parent = CorpusFolder.objects.create(name="Parent", corpus=corpus, creator=user)

        set_permissions_for_obj_to_user(user, corpus, [PermissionTypes.CREATE])

        variables = {
            "corpusId": to_global_id("CorpusType", corpus.id),
            "name": "Child",
            "parentId": to_global_id("CorpusFolderType", parent.id),
        }

        client = Client(schema, context_value=TestContext(user))
        result = client.execute(self.MUTATION, variable_values=variables)

        assert result["data"]["createCorpusFolder"]["ok"] is True
        folder_data = result["data"]["createCorpusFolder"]["folder"]
        assert folder_data["name"] == "Child"
        assert folder_data["parent"]["id"] == to_global_id(
            "CorpusFolderType", parent.id
        )

    def test_create_folder_without_permission(self):
        """Test that creating folder without permission fails."""
        owner = User.objects.create_user(username="owner", password="test")
        other_user = User.objects.create_user(username="other", password="test")
        corpus = Corpus.objects.create(title="Test Corpus", creator=owner)

        # other_user has no permissions on corpus

        variables = {
            "corpusId": to_global_id("CorpusType", corpus.id),
            "name": "Research",
        }

        client = Client(schema, context_value=TestContext(other_user))
        result = client.execute(self.MUTATION, variable_values=variables)

        assert result["data"]["createCorpusFolder"]["ok"] is False
        assert "permission" in result["data"]["createCorpusFolder"]["message"].lower()

    def test_create_duplicate_folder_name(self):
        """Test that duplicate folder names under same parent fail."""
        user = User.objects.create_user(username="testuser", password="test")
        corpus = Corpus.objects.create(title="Test Corpus", creator=user)
        parent = CorpusFolder.objects.create(name="Parent", corpus=corpus, creator=user)

        # Create first folder
        CorpusFolder.objects.create(
            name="Research", corpus=corpus, creator=user, parent=parent
        )

        set_permissions_for_obj_to_user(user, corpus, [PermissionTypes.CREATE])

        # Try to create duplicate
        variables = {
            "corpusId": to_global_id("CorpusType", corpus.id),
            "name": "Research",
            "parentId": to_global_id("CorpusFolderType", parent.id),
        }

        client = Client(schema, context_value=TestContext(user))
        result = client.execute(self.MUTATION, variable_values=variables)

        assert result["data"]["createCorpusFolder"]["ok"] is False
        assert (
            "already exists" in result["data"]["createCorpusFolder"]["message"].lower()
        )


class TestUpdateCorpusFolderMutation(TestCase):
    """Test UpdateCorpusFolder mutation."""

    MUTATION = """
        mutation UpdateFolder(
            $folderId: ID!
            $name: String
            $description: String
            $color: String
            $icon: String
            $tags: [String]
        ) {
            updateCorpusFolder(
                folderId: $folderId
                name: $name
                description: $description
                color: $color
                icon: $icon
                tags: $tags
            ) {
                ok
                message
                folder {
                    id
                    name
                    description
                    color
                    icon
                    tags
                }
            }
        }
    """

    def test_update_folder_properties(self):
        """Test updating folder properties."""
        user = User.objects.create_user(username="testuser", password="test")
        corpus = Corpus.objects.create(title="Test Corpus", creator=user)
        folder = CorpusFolder.objects.create(
            name="Old Name",
            corpus=corpus,
            creator=user,
            description="Old desc",
            color="#000000",
        )

        set_permissions_for_obj_to_user(user, corpus, [PermissionTypes.UPDATE])

        variables = {
            "folderId": to_global_id("CorpusFolderType", folder.id),
            "name": "New Name",
            "description": "New desc",
            "color": "#ffffff",
            "icon": "archive",
            "tags": ["updated"],
        }

        client = Client(schema, context_value=TestContext(user))
        result = client.execute(self.MUTATION, variable_values=variables)

        assert result["data"]["updateCorpusFolder"]["ok"] is True
        folder_data = result["data"]["updateCorpusFolder"]["folder"]
        assert folder_data["name"] == "New Name"
        assert folder_data["description"] == "New desc"
        assert folder_data["color"] == "#ffffff"
        assert folder_data["icon"] == "archive"
        tags = (
            json.loads(folder_data["tags"])
            if isinstance(folder_data["tags"], str)
            else folder_data["tags"]
        )
        assert tags == ["updated"]

    def test_update_folder_without_permission(self):
        """Test that updating without permission fails."""
        owner = User.objects.create_user(username="owner", password="test")
        other_user = User.objects.create_user(username="other", password="test")
        corpus = Corpus.objects.create(title="Test Corpus", creator=owner)
        folder = CorpusFolder.objects.create(name="Test", corpus=corpus, creator=owner)

        # other_user has no permissions on corpus

        variables = {
            "folderId": to_global_id("CorpusFolderType", folder.id),
            "name": "New Name",
        }

        client = Client(schema, context_value=TestContext(other_user))
        result = client.execute(self.MUTATION, variable_values=variables)

        assert result["data"]["updateCorpusFolder"]["ok"] is False
        assert "permission" in result["data"]["updateCorpusFolder"]["message"].lower()


class TestMoveCorpusFolderMutation(TestCase):
    """Test MoveCorpusFolder mutation."""

    MUTATION = """
        mutation MoveFolder($folderId: ID!, $newParentId: ID) {
            moveCorpusFolder(folderId: $folderId, newParentId: $newParentId) {
                ok
                message
                folder {
                    id
                    name
                    parent {
                        id
                        name
                    }
                }
            }
        }
    """

    def test_move_folder_to_new_parent(self):
        """Test moving folder to a new parent."""
        user = User.objects.create_user(username="testuser", password="test")
        corpus = Corpus.objects.create(title="Test Corpus", creator=user)
        parent1 = CorpusFolder.objects.create(
            name="Parent1", corpus=corpus, creator=user
        )
        parent2 = CorpusFolder.objects.create(
            name="Parent2", corpus=corpus, creator=user
        )
        folder = CorpusFolder.objects.create(
            name="Child", corpus=corpus, creator=user, parent=parent1
        )

        set_permissions_for_obj_to_user(user, corpus, [PermissionTypes.UPDATE])

        variables = {
            "folderId": to_global_id("CorpusFolderType", folder.id),
            "newParentId": to_global_id("CorpusFolderType", parent2.id),
        }

        client = Client(schema, context_value=TestContext(user))
        result = client.execute(self.MUTATION, variable_values=variables)

        assert result["data"]["moveCorpusFolder"]["ok"] is True
        folder_data = result["data"]["moveCorpusFolder"]["folder"]
        assert folder_data["parent"]["name"] == "Parent2"

    def test_move_folder_to_root(self):
        """Test moving folder to corpus root."""
        user = User.objects.create_user(username="testuser", password="test")
        corpus = Corpus.objects.create(title="Test Corpus", creator=user)
        parent = CorpusFolder.objects.create(name="Parent", corpus=corpus, creator=user)
        folder = CorpusFolder.objects.create(
            name="Child", corpus=corpus, creator=user, parent=parent
        )

        set_permissions_for_obj_to_user(user, corpus, [PermissionTypes.UPDATE])

        variables = {
            "folderId": to_global_id("CorpusFolderType", folder.id),
            "newParentId": None,
        }

        client = Client(schema, context_value=TestContext(user))
        result = client.execute(self.MUTATION, variable_values=variables)

        assert result["data"]["moveCorpusFolder"]["ok"] is True
        folder_data = result["data"]["moveCorpusFolder"]["folder"]
        assert folder_data["parent"] is None

    def test_prevent_moving_into_descendant(self):
        """Test that moving folder into its descendant fails."""
        user = User.objects.create_user(username="testuser", password="test")
        corpus = Corpus.objects.create(title="Test Corpus", creator=user)
        parent = CorpusFolder.objects.create(name="Parent", corpus=corpus, creator=user)
        child = CorpusFolder.objects.create(
            name="Child", corpus=corpus, creator=user, parent=parent
        )
        grandchild = CorpusFolder.objects.create(
            name="Grandchild", corpus=corpus, creator=user, parent=child
        )

        set_permissions_for_obj_to_user(user, corpus, [PermissionTypes.UPDATE])

        # Try to move parent into grandchild
        variables = {
            "folderId": to_global_id("CorpusFolderType", parent.id),
            "newParentId": to_global_id("CorpusFolderType", grandchild.id),
        }

        client = Client(schema, context_value=TestContext(user))
        result = client.execute(self.MUTATION, variable_values=variables)

        assert result["data"]["moveCorpusFolder"]["ok"] is False
        assert "descendant" in result["data"]["moveCorpusFolder"]["message"].lower()


class TestDeleteCorpusFolderMutation(TestCase):
    """Test DeleteCorpusFolder mutation."""

    MUTATION = """
        mutation DeleteFolder($folderId: ID!, $deleteContents: Boolean) {
            deleteCorpusFolder(folderId: $folderId, deleteContents: $deleteContents) {
                ok
                message
            }
        }
    """

    def test_delete_empty_folder(self):
        """Test deleting an empty folder."""
        user = User.objects.create_user(username="testuser", password="test")
        corpus = Corpus.objects.create(title="Test Corpus", creator=user)
        folder = CorpusFolder.objects.create(name="Test", corpus=corpus, creator=user)

        set_permissions_for_obj_to_user(user, corpus, [PermissionTypes.DELETE])

        variables = {
            "folderId": to_global_id("CorpusFolderType", folder.id),
        }

        client = Client(schema, context_value=TestContext(user))
        result = client.execute(self.MUTATION, variable_values=variables)

        assert result["data"]["deleteCorpusFolder"]["ok"] is True
        assert not CorpusFolder.objects.filter(id=folder.id).exists()

    def test_delete_folder_moves_children_to_parent(self):
        """Test that deleting folder moves children to parent when deleteContents=False."""
        user = User.objects.create_user(username="testuser", password="test")
        corpus = Corpus.objects.create(title="Test Corpus", creator=user)
        grandparent = CorpusFolder.objects.create(
            name="Grandparent", corpus=corpus, creator=user
        )
        parent = CorpusFolder.objects.create(
            name="Parent", corpus=corpus, creator=user, parent=grandparent
        )
        child = CorpusFolder.objects.create(
            name="Child", corpus=corpus, creator=user, parent=parent
        )

        set_permissions_for_obj_to_user(user, corpus, [PermissionTypes.DELETE])

        variables = {
            "folderId": to_global_id("CorpusFolderType", parent.id),
            "deleteContents": False,
        }

        client = Client(schema, context_value=TestContext(user))
        result = client.execute(self.MUTATION, variable_values=variables)

        assert result["data"]["deleteCorpusFolder"]["ok"] is True

        # Child should now be under grandparent
        child.refresh_from_db()
        assert child.parent == grandparent

    def test_delete_folder_with_contents(self):
        """Test deleting folder with all contents when deleteContents=True."""
        user = User.objects.create_user(username="testuser", password="test")
        corpus = Corpus.objects.create(title="Test Corpus", creator=user)
        parent = CorpusFolder.objects.create(name="Parent", corpus=corpus, creator=user)
        child = CorpusFolder.objects.create(
            name="Child", corpus=corpus, creator=user, parent=parent
        )

        set_permissions_for_obj_to_user(user, corpus, [PermissionTypes.DELETE])

        variables = {
            "folderId": to_global_id("CorpusFolderType", parent.id),
            "deleteContents": True,
        }

        client = Client(schema, context_value=TestContext(user))
        result = client.execute(self.MUTATION, variable_values=variables)

        assert result["data"]["deleteCorpusFolder"]["ok"] is True

        # Both parent and child should be deleted
        assert not CorpusFolder.objects.filter(id=parent.id).exists()
        assert not CorpusFolder.objects.filter(id=child.id).exists()


class TestMoveDocumentToFolderMutation(TestCase):
    """Test MoveDocumentToFolder mutation."""

    MUTATION = """
        mutation MoveDocument($documentId: ID!, $corpusId: ID!, $folderId: ID) {
            moveDocumentToFolder(
                documentId: $documentId
                corpusId: $corpusId
                folderId: $folderId
            ) {
                ok
                message
                document {
                    id
                }
            }
        }
    """

    def test_move_document_to_folder(self):
        """Test moving a document to a folder."""
        user = User.objects.create_user(username="testuser", password="test")
        corpus = Corpus.objects.create(title="Test Corpus", creator=user)
        folder = CorpusFolder.objects.create(
            name="Research", corpus=corpus, creator=user
        )
        doc = Document.objects.create(title="Test Doc", creator=user)
        doc, _, _ = corpus.add_document(document=doc, user=user)

        set_permissions_for_obj_to_user(user, corpus, [PermissionTypes.UPDATE])

        variables = {
            "documentId": to_global_id("DocumentType", doc.id),
            "corpusId": to_global_id("CorpusType", corpus.id),
            "folderId": to_global_id("CorpusFolderType", folder.id),
        }

        client = Client(schema, context_value=TestContext(user))
        result = client.execute(self.MUTATION, variable_values=variables)

        assert result["data"]["moveDocumentToFolder"]["ok"] is True

        # Verify assignment
        assignment = CorpusDocumentFolder.objects.get(document=doc, corpus=corpus)
        assert assignment.folder == folder

    def test_move_document_to_root(self):
        """Test moving document to corpus root."""
        user = User.objects.create_user(username="testuser", password="test")
        corpus = Corpus.objects.create(title="Test Corpus", creator=user)
        folder = CorpusFolder.objects.create(
            name="Research", corpus=corpus, creator=user
        )
        doc = Document.objects.create(title="Test Doc", creator=user)
        doc, _, _ = corpus.add_document(document=doc, user=user)

        # Initially in folder
        CorpusDocumentFolder.objects.create(document=doc, corpus=corpus, folder=folder)

        set_permissions_for_obj_to_user(user, corpus, [PermissionTypes.UPDATE])

        # Move to root
        variables = {
            "documentId": to_global_id("DocumentType", doc.id),
            "corpusId": to_global_id("CorpusType", corpus.id),
            "folderId": None,
        }

        client = Client(schema, context_value=TestContext(user))
        result = client.execute(self.MUTATION, variable_values=variables)

        assert result["data"]["moveDocumentToFolder"]["ok"] is True

        # Verify document is now in root (no assignment)
        assert not CorpusDocumentFolder.objects.filter(
            document=doc, corpus=corpus
        ).exists()


class TestMoveDocumentsToFolderMutation(TestCase):
    """Test MoveDocumentsToFolder bulk mutation."""

    MUTATION = """
        mutation MoveDocuments($documentIds: [ID]!, $corpusId: ID!, $folderId: ID) {
            moveDocumentsToFolder(
                documentIds: $documentIds
                corpusId: $corpusId
                folderId: $folderId
            ) {
                ok
                message
                movedCount
            }
        }
    """

    def test_bulk_move_documents(self):
        """Test moving multiple documents to a folder."""
        user = User.objects.create_user(username="testuser", password="test")
        corpus = Corpus.objects.create(title="Test Corpus", creator=user)
        folder = CorpusFolder.objects.create(
            name="Research", corpus=corpus, creator=user
        )

        # Create multiple documents
        docs = [
            Document.objects.create(title=f"Doc {i}", creator=user) for i in range(3)
        ]
        # Update docs list with returned documents from add_document
        for i, doc in enumerate(docs):
            docs[i], _, _ = corpus.add_document(document=doc, user=user)

        set_permissions_for_obj_to_user(user, corpus, [PermissionTypes.UPDATE])

        variables = {
            "documentIds": [to_global_id("DocumentType", doc.id) for doc in docs],
            "corpusId": to_global_id("CorpusType", corpus.id),
            "folderId": to_global_id("CorpusFolderType", folder.id),
        }

        client = Client(schema, context_value=TestContext(user))
        result = client.execute(self.MUTATION, variable_values=variables)

        assert result["data"]["moveDocumentsToFolder"]["ok"] is True
        assert result["data"]["moveDocumentsToFolder"]["movedCount"] == 3

        # Verify all documents are in folder
        for doc in docs:
            assignment = CorpusDocumentFolder.objects.get(document=doc, corpus=corpus)
            assert assignment.folder == folder

    def test_bulk_move_documents_to_root(self):
        """Test moving multiple documents to corpus root."""
        user = User.objects.create_user(username="testuser", password="test")
        corpus = Corpus.objects.create(title="Test Corpus", creator=user)
        folder = CorpusFolder.objects.create(
            name="Research", corpus=corpus, creator=user
        )

        docs = [
            Document.objects.create(title=f"Doc {i}", creator=user) for i in range(3)
        ]
        for i, doc in enumerate(docs):
            # add_document returns corpus-isolated copy and creates DocumentPath
            docs[i], _, _ = corpus.add_document(document=doc, user=user, folder=folder)
            # Don't manually create CorpusDocumentFolder - add_document handles this
            # via DocumentPath folder parameter

        set_permissions_for_obj_to_user(user, corpus, [PermissionTypes.UPDATE])

        variables = {
            "documentIds": [to_global_id("DocumentType", doc.id) for doc in docs],
            "corpusId": to_global_id("CorpusType", corpus.id),
            "folderId": None,
        }

        client = Client(schema, context_value=TestContext(user))
        result = client.execute(self.MUTATION, variable_values=variables)

        assert result["data"]["moveDocumentsToFolder"]["ok"] is True
        assert result["data"]["moveDocumentsToFolder"]["movedCount"] == 3

        # Verify all documents are in root
        for doc in docs:
            assert not CorpusDocumentFolder.objects.filter(
                document=doc, corpus=corpus
            ).exists()
