"""
Tests for document versioning GraphQL API in OpenContracts.

This module tests the GraphQL schema enhancements for versioning UI features.

Tests cover:
1. Version metadata fields (version_number, has_version_history, etc.)
2. Lazy-loaded history fields (version_history, path_history)
3. Permission checks for versioning features
4. Integration with DocumentPath model
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.documents.versioning import (
    delete_document,
    import_document,
    move_document,
    restore_document,
)
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class TestVersionMetadataFields(TestCase):
    """Test GraphQL queries for version metadata fields."""

    def setUp(self):
        """Create test data for each test."""
        self.client = Client(schema)

        self.user = User.objects.create_user(
            username="version_tester",
            password="testpass123",
            email="version@test.com",
        )

        self.corpus = Corpus.objects.create(
            title="Version Test Corpus",
            creator=self.user,
            is_public=True,
        )

        # Create document with version history
        content_v1 = b"Version 1 content"
        content_v2 = b"Version 2 content"

        self.doc_v1, _, self.path_v1 = import_document(
            corpus=self.corpus,
            path="/test_doc.pdf",
            content=content_v1,
            user=self.user,
            title="Test Document v1",
        )

        self.doc_v2, _, self.path_v2 = import_document(
            corpus=self.corpus,
            path="/test_doc.pdf",
            content=content_v2,
            user=self.user,
            title="Test Document v2",
        )

        # Create a simple document without history
        self.simple_doc, _, self.simple_path = import_document(
            corpus=self.corpus,
            path="/simple_doc.pdf",
            content=b"Simple content",
            user=self.user,
            title="Simple Document",
        )

    def test_version_number_field(self):
        """Test that version_number correctly returns DocumentPath version."""
        corpus_id = to_global_id("CorpusType", self.corpus.id)
        doc_id = to_global_id("DocumentType", self.doc_v2.id)

        query = f"""
            query {{
                document(id: "{doc_id}") {{
                    id
                    title
                    versionNumber(corpusId: "{corpus_id}")
                }}
            }}
        """

        result = self.client.execute(
            query, context_value=type("Request", (), {"user": self.user})()
        )

        self.assertIsNone(result.get("errors"))
        self.assertEqual(result["data"]["document"]["versionNumber"], 2)

    def test_version_number_for_simple_document(self):
        """Test version_number returns 1 for new document."""
        corpus_id = to_global_id("CorpusType", self.corpus.id)
        doc_id = to_global_id("DocumentType", self.simple_doc.id)

        query = f"""
            query {{
                document(id: "{doc_id}") {{
                    id
                    versionNumber(corpusId: "{corpus_id}")
                }}
            }}
        """

        result = self.client.execute(
            query, context_value=type("Request", (), {"user": self.user})()
        )

        self.assertIsNone(result.get("errors"))
        self.assertEqual(result["data"]["document"]["versionNumber"], 1)

    def test_has_version_history_true(self):
        """Test has_version_history returns True for document with parent."""
        doc_id = to_global_id("DocumentType", self.doc_v2.id)

        query = f"""
            query {{
                document(id: "{doc_id}") {{
                    id
                    hasVersionHistory
                }}
            }}
        """

        result = self.client.execute(
            query, context_value=type("Request", (), {"user": self.user})()
        )

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["document"]["hasVersionHistory"])

    def test_has_version_history_false(self):
        """Test has_version_history returns False for document without parent."""
        doc_id = to_global_id("DocumentType", self.simple_doc.id)

        query = f"""
            query {{
                document(id: "{doc_id}") {{
                    id
                    hasVersionHistory
                }}
            }}
        """

        result = self.client.execute(
            query, context_value=type("Request", (), {"user": self.user})()
        )

        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["document"]["hasVersionHistory"])

    def test_version_count(self):
        """Test version_count returns total versions in tree."""
        doc_id = to_global_id("DocumentType", self.doc_v2.id)

        query = f"""
            query {{
                document(id: "{doc_id}") {{
                    id
                    versionCount
                }}
            }}
        """

        result = self.client.execute(
            query, context_value=type("Request", (), {"user": self.user})()
        )

        self.assertIsNone(result.get("errors"))
        self.assertEqual(result["data"]["document"]["versionCount"], 2)

    def test_version_count_single_version(self):
        """Test version_count returns 1 for single version document."""
        doc_id = to_global_id("DocumentType", self.simple_doc.id)

        query = f"""
            query {{
                document(id: "{doc_id}") {{
                    id
                    versionCount
                }}
            }}
        """

        result = self.client.execute(
            query, context_value=type("Request", (), {"user": self.user})()
        )

        self.assertIsNone(result.get("errors"))
        self.assertEqual(result["data"]["document"]["versionCount"], 1)

    def test_is_latest_version_true(self):
        """Test is_latest_version returns True for current document."""
        doc_id = to_global_id("DocumentType", self.doc_v2.id)

        query = f"""
            query {{
                document(id: "{doc_id}") {{
                    id
                    isLatestVersion
                }}
            }}
        """

        result = self.client.execute(
            query, context_value=type("Request", (), {"user": self.user})()
        )

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["document"]["isLatestVersion"])

    def test_is_latest_version_false(self):
        """Test is_latest_version returns False for old version."""
        # Refresh v1 to get updated is_current flag
        self.doc_v1.refresh_from_db()
        doc_id = to_global_id("DocumentType", self.doc_v1.id)

        query = f"""
            query {{
                document(id: "{doc_id}") {{
                    id
                    isLatestVersion
                }}
            }}
        """

        result = self.client.execute(
            query, context_value=type("Request", (), {"user": self.user})()
        )

        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["document"]["isLatestVersion"])

    def test_last_modified_field(self):
        """Test last_modified returns DocumentPath created timestamp."""
        corpus_id = to_global_id("CorpusType", self.corpus.id)
        doc_id = to_global_id("DocumentType", self.doc_v2.id)

        query = f"""
            query {{
                document(id: "{doc_id}") {{
                    id
                    lastModified(corpusId: "{corpus_id}")
                }}
            }}
        """

        result = self.client.execute(
            query, context_value=type("Request", (), {"user": self.user})()
        )

        self.assertIsNone(result.get("errors"))
        # Just verify it returns a timestamp
        self.assertIsNotNone(result["data"]["document"]["lastModified"])


class TestVersionHistoryLazyLoading(TestCase):
    """Test lazy-loaded version history field."""

    def setUp(self):
        """Create test data with version history."""
        self.client = Client(schema)

        self.user = User.objects.create_user(
            username="history_tester",
            password="testpass123",
            email="history@test.com",
        )

        self.corpus = Corpus.objects.create(
            title="History Test Corpus",
            creator=self.user,
            is_public=True,
        )

        # Create document with 3 versions
        self.doc_v1, _, _ = import_document(
            corpus=self.corpus,
            path="/versioned.pdf",
            content=b"Version 1",
            user=self.user,
            title="Doc v1",
        )

        self.doc_v2, _, _ = import_document(
            corpus=self.corpus,
            path="/versioned.pdf",
            content=b"Version 2",
            user=self.user,
            title="Doc v2",
        )

        self.doc_v3, _, _ = import_document(
            corpus=self.corpus,
            path="/versioned.pdf",
            content=b"Version 3",
            user=self.user,
            title="Doc v3",
        )

    def test_version_history_returns_all_versions(self):
        """Test version_history returns complete history."""
        doc_id = to_global_id("DocumentType", self.doc_v3.id)

        query = f"""
            query {{
                document(id: "{doc_id}") {{
                    id
                    versionHistory {{
                        versions {{
                            id
                            versionNumber
                            changeType
                            hash
                            createdBy {{
                                username
                            }}
                        }}
                        currentVersion {{
                            id
                            versionNumber
                        }}
                    }}
                }}
            }}
        """

        result = self.client.execute(
            query, context_value=type("Request", (), {"user": self.user})()
        )

        self.assertIsNone(result.get("errors"))
        history = result["data"]["document"]["versionHistory"]

        # Should have 3 versions
        self.assertEqual(len(history["versions"]), 3)

        # Verify version numbers
        version_numbers = [v["versionNumber"] for v in history["versions"]]
        self.assertEqual(version_numbers, [1, 2, 3])

        # First version should have INITIAL change type
        self.assertEqual(history["versions"][0]["changeType"], "INITIAL")

        # Others should have CONTENT_UPDATE
        self.assertEqual(history["versions"][1]["changeType"], "CONTENT_UPDATE")
        self.assertEqual(history["versions"][2]["changeType"], "CONTENT_UPDATE")

        # Current version should be v3
        expected_current_id = to_global_id("DocumentType", self.doc_v3.id)
        self.assertEqual(history["currentVersion"]["id"], expected_current_id)
        self.assertEqual(history["currentVersion"]["versionNumber"], 3)

    def test_version_history_includes_creator_info(self):
        """Test version_history includes user info for each version."""
        doc_id = to_global_id("DocumentType", self.doc_v3.id)

        query = f"""
            query {{
                document(id: "{doc_id}") {{
                    versionHistory {{
                        versions {{
                            createdBy {{
                                username
                            }}
                        }}
                    }}
                }}
            }}
        """

        result = self.client.execute(
            query, context_value=type("Request", (), {"user": self.user})()
        )

        self.assertIsNone(result.get("errors"))
        versions = result["data"]["document"]["versionHistory"]["versions"]

        for version in versions:
            self.assertEqual(version["createdBy"]["username"], "history_tester")


class TestPathHistoryLazyLoading(TestCase):
    """Test lazy-loaded path history field."""

    def setUp(self):
        """Create test data with path history."""
        self.client = Client(schema)

        self.user = User.objects.create_user(
            username="path_tester",
            password="testpass123",
            email="path@test.com",
        )

        self.corpus = Corpus.objects.create(
            title="Path Test Corpus",
            creator=self.user,
            is_public=True,
        )

        # Create document with path history
        self.doc, _, path1 = import_document(
            corpus=self.corpus,
            path="/original.pdf",
            content=b"Test content",
            user=self.user,
            title="Test Doc",
        )

        # Move it
        move_document(
            corpus=self.corpus,
            old_path="/original.pdf",
            new_path="/moved.pdf",
            user=self.user,
        )

        # Delete it
        delete_document(corpus=self.corpus, path="/moved.pdf", user=self.user)

        # Restore it
        self.current_path = restore_document(
            corpus=self.corpus, path="/moved.pdf", user=self.user
        )

    def test_path_history_returns_all_events(self):
        """Test path_history returns all lifecycle events."""
        corpus_id = to_global_id("CorpusType", self.corpus.id)
        doc_id = to_global_id("DocumentType", self.doc.id)

        query = f"""
            query {{
                document(id: "{doc_id}") {{
                    pathHistory(corpusId: "{corpus_id}") {{
                        events {{
                            id
                            action
                            path
                            versionNumber
                            user {{
                                username
                            }}
                        }}
                        currentPath
                        originalPath
                        moveCount
                    }}
                }}
            }}
        """

        result = self.client.execute(
            query, context_value=type("Request", (), {"user": self.user})()
        )

        self.assertIsNone(result.get("errors"))
        path_history = result["data"]["document"]["pathHistory"]

        # Should have 4 events: IMPORTED, MOVED, DELETED, RESTORED
        self.assertEqual(len(path_history["events"]), 4)

        # Verify actions
        actions = [e["action"] for e in path_history["events"]]
        self.assertEqual(actions[0], "IMPORTED")
        self.assertEqual(actions[1], "MOVED")
        self.assertEqual(actions[2], "DELETED")
        self.assertEqual(actions[3], "RESTORED")

        # Verify paths
        self.assertEqual(path_history["originalPath"], "/original.pdf")
        self.assertEqual(path_history["currentPath"], "/moved.pdf")

        # Verify move count
        self.assertEqual(path_history["moveCount"], 1)

    def test_path_history_version_unchanged_on_move(self):
        """Test that version number doesn't change on move operations."""
        corpus_id = to_global_id("CorpusType", self.corpus.id)
        doc_id = to_global_id("DocumentType", self.doc.id)

        query = f"""
            query {{
                document(id: "{doc_id}") {{
                    pathHistory(corpusId: "{corpus_id}") {{
                        events {{
                            action
                            versionNumber
                        }}
                    }}
                }}
            }}
        """

        result = self.client.execute(
            query, context_value=type("Request", (), {"user": self.user})()
        )

        self.assertIsNone(result.get("errors"))
        events = result["data"]["document"]["pathHistory"]["events"]

        # All operations on same version, so version number should be 1
        for event in events:
            self.assertEqual(
                event["versionNumber"],
                1,
                f"{event['action']} should have version 1",
            )


class TestVersioningPermissions(TestCase):
    """Test permission checks for versioning features."""

    def setUp(self):
        """Create test data with permission scenarios."""
        self.client = Client(schema)

        # Document owner
        self.owner = User.objects.create_user(
            username="doc_owner",
            password="testpass123",
            email="owner@test.com",
        )

        # Another user with no permissions
        self.other_user = User.objects.create_user(
            username="other_user",
            password="testpass123",
            email="other@test.com",
        )

        # User with UPDATE permission
        self.editor = User.objects.create_user(
            username="editor_user",
            password="testpass123",
            email="editor@test.com",
        )

        # Create corpus and document
        self.corpus = Corpus.objects.create(
            title="Permission Test Corpus",
            creator=self.owner,
            is_public=False,
        )

        self.doc, _, _ = import_document(
            corpus=self.corpus,
            path="/test.pdf",
            content=b"Test content",
            user=self.owner,
            title="Test Doc",
        )

        # Grant CRUD permission to owner (document creator)
        set_permissions_for_obj_to_user(
            self.owner,
            self.doc,
            [PermissionTypes.CRUD],
        )
        set_permissions_for_obj_to_user(
            self.owner,
            self.corpus,
            [PermissionTypes.CRUD],
        )

        # Grant UPDATE permission to editor
        set_permissions_for_obj_to_user(
            self.editor,
            self.doc,
            [PermissionTypes.READ, PermissionTypes.UPDATE],
        )
        set_permissions_for_obj_to_user(
            self.editor,
            self.corpus,
            [PermissionTypes.READ, PermissionTypes.UPDATE],
        )

        # Grant only READ permission to other_user
        set_permissions_for_obj_to_user(
            self.other_user,
            self.doc,
            [PermissionTypes.READ],
        )
        set_permissions_for_obj_to_user(
            self.other_user,
            self.corpus,
            [PermissionTypes.READ],
        )

    def test_can_restore_true_for_owner(self):
        """Test can_restore returns True for document owner."""
        corpus_id = to_global_id("CorpusType", self.corpus.id)
        doc_id = to_global_id("DocumentType", self.doc.id)

        query = f"""
            query {{
                document(id: "{doc_id}") {{
                    canRestore(corpusId: "{corpus_id}")
                }}
            }}
        """

        result = self.client.execute(
            query, context_value=type("Request", (), {"user": self.owner})()
        )

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["document"]["canRestore"])

    def test_can_restore_true_for_editor(self):
        """Test can_restore returns True for user with UPDATE permission."""
        corpus_id = to_global_id("CorpusType", self.corpus.id)
        doc_id = to_global_id("DocumentType", self.doc.id)

        query = f"""
            query {{
                document(id: "{doc_id}") {{
                    canRestore(corpusId: "{corpus_id}")
                }}
            }}
        """

        result = self.client.execute(
            query, context_value=type("Request", (), {"user": self.editor})()
        )

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["document"]["canRestore"])

    def test_can_restore_false_for_readonly_user(self):
        """Test can_restore returns False for user with only READ permission."""
        corpus_id = to_global_id("CorpusType", self.corpus.id)
        doc_id = to_global_id("DocumentType", self.doc.id)

        query = f"""
            query {{
                document(id: "{doc_id}") {{
                    canRestore(corpusId: "{corpus_id}")
                }}
            }}
        """

        result = self.client.execute(
            query, context_value=type("Request", (), {"user": self.other_user})()
        )

        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["document"]["canRestore"])

    def test_can_view_history_true_for_public_document(self):
        """Test can_view_history returns True for public documents."""
        # Make document public
        self.doc.is_public = True
        self.doc.save()

        doc_id = to_global_id("DocumentType", self.doc.id)

        query = f"""
            query {{
                document(id: "{doc_id}") {{
                    canViewHistory
                }}
            }}
        """

        result = self.client.execute(
            query, context_value=type("Request", (), {"user": self.other_user})()
        )

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["document"]["canViewHistory"])

    def test_can_view_history_true_for_user_with_read_permission(self):
        """Test can_view_history returns True for user with READ permission."""
        doc_id = to_global_id("DocumentType", self.doc.id)

        query = f"""
            query {{
                document(id: "{doc_id}") {{
                    canViewHistory
                }}
            }}
        """

        result = self.client.execute(
            query, context_value=type("Request", (), {"user": self.other_user})()
        )

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["document"]["canViewHistory"])


class TestVersionMetadataIntegration(TestCase):
    """Integration tests for version metadata in document queries."""

    def setUp(self):
        """Create complex test scenario."""
        self.client = Client(schema)

        self.user = User.objects.create_user(
            username="integration_tester",
            password="testpass123",
            email="integration@test.com",
        )

        self.corpus = Corpus.objects.create(
            title="Integration Test Corpus",
            creator=self.user,
            is_public=True,
        )

        # Create multiple documents with different version states
        self.doc1, _, _ = import_document(
            corpus=self.corpus,
            path="/doc1.pdf",
            content=b"Doc 1 v1",
            user=self.user,
            title="Document 1 v1",
        )

        self.doc1_v2, _, _ = import_document(
            corpus=self.corpus,
            path="/doc1.pdf",
            content=b"Doc 1 v2",
            user=self.user,
            title="Document 1 v2",
        )

        self.doc2, _, _ = import_document(
            corpus=self.corpus,
            path="/doc2.pdf",
            content=b"Doc 2 v1",
            user=self.user,
            title="Document 2",
        )

    def test_query_multiple_documents_with_version_metadata(self):
        """Test querying multiple documents includes version metadata."""
        corpus_id = to_global_id("CorpusType", self.corpus.id)

        # Query both documents and verify version info
        doc1_id = to_global_id("DocumentType", self.doc1_v2.id)
        doc2_id = to_global_id("DocumentType", self.doc2.id)

        query = f"""
            query {{
                doc1: document(id: "{doc1_id}") {{
                    id
                    title
                    versionNumber(corpusId: "{corpus_id}")
                    hasVersionHistory
                    versionCount
                    isLatestVersion
                }}
                doc2: document(id: "{doc2_id}") {{
                    id
                    title
                    versionNumber(corpusId: "{corpus_id}")
                    hasVersionHistory
                    versionCount
                    isLatestVersion
                }}
            }}
        """

        result = self.client.execute(
            query, context_value=type("Request", (), {"user": self.user})()
        )

        self.assertIsNone(result.get("errors"))

        # Doc1 v2 should show version 2, has history, is current
        doc1_data = result["data"]["doc1"]
        self.assertEqual(doc1_data["versionNumber"], 2)
        self.assertTrue(doc1_data["hasVersionHistory"])
        self.assertEqual(doc1_data["versionCount"], 2)
        self.assertTrue(doc1_data["isLatestVersion"])

        # Doc2 should show version 1, no history, is current
        doc2_data = result["data"]["doc2"]
        self.assertEqual(doc2_data["versionNumber"], 1)
        self.assertFalse(doc2_data["hasVersionHistory"])
        self.assertEqual(doc2_data["versionCount"], 1)
        self.assertTrue(doc2_data["isLatestVersion"])

    def test_version_metadata_with_missing_document_path(self):
        """Test version_number handles missing DocumentPath gracefully."""
        # Create another corpus (doc not in this corpus)
        other_corpus = Corpus.objects.create(
            title="Other Corpus",
            creator=self.user,
            is_public=True,
        )
        other_corpus_id = to_global_id("CorpusType", other_corpus.id)

        doc_id = to_global_id("DocumentType", self.doc2.id)

        # Query version_number for corpus where doc doesn't exist
        query = f"""
            query {{
                document(id: "{doc_id}") {{
                    id
                    versionNumber(corpusId: "{other_corpus_id}")
                }}
            }}
        """

        result = self.client.execute(
            query, context_value=type("Request", (), {"user": self.user})()
        )

        self.assertIsNone(result.get("errors"))
        # Should return 1 as default
        self.assertEqual(result["data"]["document"]["versionNumber"], 1)


class TestRestoreDeletedDocumentMutation(TestCase):
    """Test RestoreDeletedDocument GraphQL mutation."""

    def setUp(self):
        """Create test data for each test."""
        self.client = Client(schema)

        self.user = User.objects.create_user(
            username="restore_tester",
            password="testpass123",
            email="restore@test.com",
        )

        self.other_user = User.objects.create_user(
            username="other_user",
            password="testpass123",
            email="other@test.com",
        )

        self.corpus = Corpus.objects.create(
            title="Restore Test Corpus",
            creator=self.user,
            is_public=True,
        )

        # Set permissions
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.CRUD])

        # Create and delete a document
        self.doc, _, self.path = import_document(
            corpus=self.corpus,
            path="/deletable_doc.pdf",
            content=b"Deletable content",
            user=self.user,
            title="Deletable Document",
        )

        set_permissions_for_obj_to_user(self.user, self.doc, [PermissionTypes.CRUD])

        # Delete the document
        self.deleted_path = delete_document(
            corpus=self.corpus, path="/deletable_doc.pdf", user=self.user
        )

    def test_restore_deleted_document_success(self):
        """Test successful restoration of deleted document."""
        doc_id = to_global_id("DocumentType", self.doc.id)
        corpus_id = to_global_id("CorpusType", self.corpus.id)

        mutation = f"""
            mutation {{
                restoreDeletedDocument(documentId: "{doc_id}", corpusId: "{corpus_id}") {{
                    ok
                    message
                    document {{
                        id
                        title
                    }}
                }}
            }}
        """

        result = self.client.execute(
            mutation, context_value=type("Request", (), {"user": self.user})()
        )

        self.assertIsNone(result.get("errors"))
        # Debug output
        if not result["data"]["restoreDeletedDocument"]["ok"]:
            print(
                f"Error message: {result['data']['restoreDeletedDocument']['message']}"
            )
        self.assertTrue(result["data"]["restoreDeletedDocument"]["ok"])
        self.assertIn("restored", result["data"]["restoreDeletedDocument"]["message"])
        self.assertEqual(
            result["data"]["restoreDeletedDocument"]["document"]["title"],
            "Deletable Document",
        )

        # Verify path is no longer deleted
        current_path = DocumentPath.objects.filter(
            document=self.doc, corpus=self.corpus, is_current=True
        ).first()
        self.assertIsNotNone(current_path)
        self.assertFalse(current_path.is_deleted)

    def test_restore_not_deleted_document_fails(self):
        """Test that restoring non-deleted document fails."""
        # Create a non-deleted document
        active_doc, _, active_path = import_document(
            corpus=self.corpus,
            path="/active_doc.pdf",
            content=b"Active content",
            user=self.user,
            title="Active Document",
        )
        set_permissions_for_obj_to_user(self.user, active_doc, [PermissionTypes.CRUD])

        doc_id = to_global_id("DocumentType", active_doc.id)
        corpus_id = to_global_id("CorpusType", self.corpus.id)

        mutation = f"""
            mutation {{
                restoreDeletedDocument(documentId: "{doc_id}", corpusId: "{corpus_id}") {{
                    ok
                    message
                }}
            }}
        """

        result = self.client.execute(
            mutation, context_value=type("Request", (), {"user": self.user})()
        )

        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["restoreDeletedDocument"]["ok"])
        self.assertIn(
            "Cannot restore document",
            result["data"]["restoreDeletedDocument"]["message"],
        )

    def test_restore_without_document_permission_fails(self):
        """Test that user without document permission cannot restore."""
        doc_id = to_global_id("DocumentType", self.doc.id)
        corpus_id = to_global_id("CorpusType", self.corpus.id)

        mutation = f"""
            mutation {{
                restoreDeletedDocument(documentId: "{doc_id}", corpusId: "{corpus_id}") {{
                    ok
                    message
                }}
            }}
        """

        result = self.client.execute(
            mutation, context_value=type("Request", (), {"user": self.other_user})()
        )

        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["restoreDeletedDocument"]["ok"])
        self.assertIn("permission", result["data"]["restoreDeletedDocument"]["message"])

    def test_restore_nonexistent_document_fails(self):
        """Test restoring non-existent document fails gracefully."""
        fake_doc_id = to_global_id("DocumentType", 99999)
        corpus_id = to_global_id("CorpusType", self.corpus.id)

        mutation = f"""
            mutation {{
                restoreDeletedDocument(documentId: "{fake_doc_id}", corpusId: "{corpus_id}") {{
                    ok
                    message
                }}
            }}
        """

        result = self.client.execute(
            mutation, context_value=type("Request", (), {"user": self.user})()
        )

        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["restoreDeletedDocument"]["ok"])
        self.assertIn("not found", result["data"]["restoreDeletedDocument"]["message"])


class TestRestoreDocumentToVersionMutation(TestCase):
    """Test RestoreDocumentToVersion GraphQL mutation."""

    def setUp(self):
        """Create test data with version history."""
        self.client = Client(schema)

        self.user = User.objects.create_user(
            username="version_restore_tester",
            password="testpass123",
            email="vrestore@test.com",
        )

        self.other_user = User.objects.create_user(
            username="other_version_user",
            password="testpass123",
            email="otherv@test.com",
        )

        self.corpus = Corpus.objects.create(
            title="Version Restore Test Corpus",
            creator=self.user,
            is_public=True,
        )

        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.CRUD])

        # Create document with multiple versions
        self.doc_v1, _, self.path_v1 = import_document(
            corpus=self.corpus,
            path="/versioned_doc.pdf",
            content=b"Version 1 content",
            user=self.user,
            title="Document Version 1",
        )
        set_permissions_for_obj_to_user(self.user, self.doc_v1, [PermissionTypes.CRUD])

        self.doc_v2, _, self.path_v2 = import_document(
            corpus=self.corpus,
            path="/versioned_doc.pdf",
            content=b"Version 2 content",
            user=self.user,
            title="Document Version 2",
        )
        set_permissions_for_obj_to_user(self.user, self.doc_v2, [PermissionTypes.CRUD])

        self.doc_v3, _, self.path_v3 = import_document(
            corpus=self.corpus,
            path="/versioned_doc.pdf",
            content=b"Version 3 content",
            user=self.user,
            title="Document Version 3",
        )
        set_permissions_for_obj_to_user(self.user, self.doc_v3, [PermissionTypes.CRUD])

    def test_restore_to_previous_version_success(self):
        """Test successful restoration to a previous version."""
        # Restore to version 1
        old_version_id = to_global_id("DocumentType", self.doc_v1.id)
        corpus_id = to_global_id("CorpusType", self.corpus.id)

        mutation = f"""
            mutation {{
                restoreDocumentToVersion(documentId: "{old_version_id}", corpusId: "{corpus_id}") {{
                    ok
                    message
                    document {{
                        id
                        title
                        isCurrent
                    }}
                    newVersionNumber
                }}
            }}
        """

        result = self.client.execute(
            mutation, context_value=type("Request", (), {"user": self.user})()
        )

        self.assertIsNone(result.get("errors"))
        # Debug output to see actual error
        if not result["data"]["restoreDocumentToVersion"]["ok"]:
            print(
                f"Error message: {result['data']['restoreDocumentToVersion']['message']}"
            )
        self.assertTrue(result["data"]["restoreDocumentToVersion"]["ok"])
        self.assertEqual(
            result["data"]["restoreDocumentToVersion"]["newVersionNumber"], 4
        )
        self.assertEqual(
            result["data"]["restoreDocumentToVersion"]["document"]["title"],
            "Document Version 1",
        )

        # Verify old current is no longer current
        self.doc_v3.refresh_from_db()
        self.assertFalse(self.doc_v3.is_current)

        # Verify new document is current
        new_current = Document.objects.filter(
            version_tree_id=self.doc_v1.version_tree_id, is_current=True
        ).first()
        self.assertIsNotNone(new_current)
        self.assertEqual(new_current.title, "Document Version 1")

    def test_restore_to_current_version_fails(self):
        """Test that restoring to current version fails."""
        current_version_id = to_global_id("DocumentType", self.doc_v3.id)
        corpus_id = to_global_id("CorpusType", self.corpus.id)

        mutation = f"""
            mutation {{
                restoreDocumentToVersion(documentId: "{current_version_id}", corpusId: "{corpus_id}") {{
                    ok
                    message
                }}
            }}
        """

        result = self.client.execute(
            mutation, context_value=type("Request", (), {"user": self.user})()
        )

        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["restoreDocumentToVersion"]["ok"])
        self.assertIn(
            "current version", result["data"]["restoreDocumentToVersion"]["message"]
        )

    def test_restore_version_without_permission_fails(self):
        """Test that user without permission cannot restore version."""
        old_version_id = to_global_id("DocumentType", self.doc_v1.id)
        corpus_id = to_global_id("CorpusType", self.corpus.id)

        mutation = f"""
            mutation {{
                restoreDocumentToVersion(documentId: "{old_version_id}", corpusId: "{corpus_id}") {{
                    ok
                    message
                }}
            }}
        """

        result = self.client.execute(
            mutation, context_value=type("Request", (), {"user": self.other_user})()
        )

        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["restoreDocumentToVersion"]["ok"])
        self.assertIn(
            "permission", result["data"]["restoreDocumentToVersion"]["message"]
        )

    def test_restore_version_increments_path_version(self):
        """Test that restoring creates correct version number in path."""
        old_version_id = to_global_id("DocumentType", self.doc_v2.id)
        corpus_id = to_global_id("CorpusType", self.corpus.id)

        mutation = f"""
            mutation {{
                restoreDocumentToVersion(documentId: "{old_version_id}", corpusId: "{corpus_id}") {{
                    ok
                    newVersionNumber
                }}
            }}
        """

        result = self.client.execute(
            mutation, context_value=type("Request", (), {"user": self.user})()
        )

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["restoreDocumentToVersion"]["ok"])
        # Version 4 because we have v1, v2, v3, and now v4 (restored from v2)
        self.assertEqual(
            result["data"]["restoreDocumentToVersion"]["newVersionNumber"], 4
        )

        # Verify path tree is intact
        current_path = DocumentPath.objects.filter(
            document__version_tree_id=self.doc_v1.version_tree_id,
            corpus=self.corpus,
            is_current=True,
        ).first()
        self.assertIsNotNone(current_path)
        self.assertEqual(current_path.version_number, 4)
        self.assertIsNotNone(current_path.parent)

    def test_restore_nonexistent_version_fails(self):
        """Test restoring non-existent version fails gracefully."""
        fake_doc_id = to_global_id("DocumentType", 99999)
        corpus_id = to_global_id("CorpusType", self.corpus.id)

        mutation = f"""
            mutation {{
                restoreDocumentToVersion(documentId: "{fake_doc_id}", corpusId: "{corpus_id}") {{
                    ok
                    message
                }}
            }}
        """

        result = self.client.execute(
            mutation, context_value=type("Request", (), {"user": self.user})()
        )

        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["restoreDocumentToVersion"]["ok"])
        self.assertIn(
            "not found", result["data"]["restoreDocumentToVersion"]["message"]
        )
