"""
Coverage-focused tests for the strawberry-ported corpus folder mutations
in ``config/graphql/corpus_folder_mutations.py``.

``test_corpus_folder_mutations.py`` already covers the happy paths and the
"no permission at all" IDOR-safe responses. This module targets the
remaining error/validation branches left uncovered by that suite:

- Unauthenticated access (each of the six mutations)
- Visible-but-insufficient-service-permission responses (e.g. UPDATE
  without DELETE)
- "Object exists but isn't the right one" not-found responses (document
  not in corpus, folder not in corpus, nonexistent folder id)
- Malformed-global-id handling: ``CorpusFolder.objects.get(pk=...)`` (and
  the bulk ``int(from_global_id(...))`` conversion) let a non-numeric id
  raise ``ValueError``, which is NOT caught by the specific
  ``DoesNotExist`` handlers and falls through to each mutation's generic
  ``except Exception`` — a real defensive path, exercised here without
  any mocking.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from graphql_relay import to_global_id

from config.graphql.schema import schema
from config.graphql.testing import Client
from opencontractserver.corpuses.models import Corpus, CorpusFolder
from opencontractserver.documents.models import Document
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()

# A syntactically well-formed global id (round-tripped through
# ``to_global_id``) whose decoded raw pk is non-numeric. ``from_global_id``
# never raises on this (verified: ``unbase64`` swallows base64/unicode
# errors), but the subsequent ``CorpusFolder.objects.get(pk=...)`` /
# ``int(...)`` conversion does — exercising the generic ``except Exception``
# fallback in each mutation without needing to mock anything.
_MALFORMED_PK = "not-an-int"


class TestContext:
    """Minimal GraphQL test context (mirrors test_corpus_folder_mutations.py)."""

    def __init__(self, user):
        self.user = user


CREATE_FOLDER_MUTATION = """
    mutation CreateFolder($corpusId: ID!, $name: String!, $parentId: ID) {
        createCorpusFolder(corpusId: $corpusId, name: $name, parentId: $parentId) {
            ok
            message
            folder {
                id
            }
        }
    }
"""

UPDATE_FOLDER_MUTATION = """
    mutation UpdateFolder($folderId: ID!, $name: String) {
        updateCorpusFolder(folderId: $folderId, name: $name) {
            ok
            message
            folder {
                id
            }
        }
    }
"""

MOVE_FOLDER_MUTATION = """
    mutation MoveFolder($folderId: ID!, $newParentId: ID) {
        moveCorpusFolder(folderId: $folderId, newParentId: $newParentId) {
            ok
            message
            folder {
                id
            }
        }
    }
"""

DELETE_FOLDER_MUTATION = """
    mutation DeleteFolder($folderId: ID!, $deleteContents: Boolean) {
        deleteCorpusFolder(folderId: $folderId, deleteContents: $deleteContents) {
            ok
            message
        }
    }
"""

MOVE_DOCUMENT_MUTATION = """
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

MOVE_DOCUMENTS_MUTATION = """
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


class CreateCorpusFolderCoverageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="cff_create_user", password="pw")
        self.corpus = Corpus.objects.create(title="Coverage Corpus", creator=self.user)

    def test_unauthenticated_raises(self):
        client = Client(schema, context_value=TestContext(AnonymousUser()))
        result = client.execute(
            CREATE_FOLDER_MUTATION,
            variables={
                "corpusId": to_global_id("CorpusType", self.corpus.id),
                "name": "Anon Folder",
            },
        )
        self.assertIsNotNone(result.get("errors"))

    def test_malformed_parent_id_returns_generic_failure(self):
        """A syntactically valid but non-numeric parentId raises ValueError
        from ``CorpusFolder.objects.get(pk=...)``, uncaught by the
        ``(Corpus.DoesNotExist, CorpusFolder.DoesNotExist)`` handler."""
        client = Client(schema, context_value=TestContext(self.user))
        result = client.execute(
            CREATE_FOLDER_MUTATION,
            variables={
                "corpusId": to_global_id("CorpusType", self.corpus.id),
                "name": "Bad Parent",
                "parentId": to_global_id("CorpusFolderType", _MALFORMED_PK),
            },
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["createCorpusFolder"]
        self.assertFalse(data["ok"])
        self.assertIn("failed to create folder", data["message"].lower())
        self.assertFalse(CorpusFolder.objects.filter(corpus=self.corpus).exists())


class UpdateCorpusFolderCoverageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="cff_update_user", password="pw")
        self.corpus = Corpus.objects.create(title="Coverage Corpus", creator=self.user)
        self.folder_a = CorpusFolder.objects.create(
            name="Alpha", corpus=self.corpus, creator=self.user
        )
        self.folder_b = CorpusFolder.objects.create(
            name="Beta", corpus=self.corpus, creator=self.user
        )

    def test_unauthenticated_raises(self):
        client = Client(schema, context_value=TestContext(AnonymousUser()))
        result = client.execute(
            UPDATE_FOLDER_MUTATION,
            variables={
                "folderId": to_global_id("CorpusFolderType", self.folder_a.id),
                "name": "New Name",
            },
        )
        self.assertIsNotNone(result.get("errors"))

    def test_duplicate_name_returns_service_error(self):
        """Renaming folder_b to folder_a's name hits
        FolderCRUDService.update_folder's uniqueness check, surfacing the
        service error string rather than a generic failure."""
        client = Client(schema, context_value=TestContext(self.user))
        result = client.execute(
            UPDATE_FOLDER_MUTATION,
            variables={
                "folderId": to_global_id("CorpusFolderType", self.folder_b.id),
                "name": self.folder_a.name,
            },
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["updateCorpusFolder"]
        self.assertFalse(data["ok"])
        self.assertIn("already exists", data["message"].lower())

    def test_malformed_folder_id_returns_generic_failure(self):
        client = Client(schema, context_value=TestContext(self.user))
        result = client.execute(
            UPDATE_FOLDER_MUTATION,
            variables={
                "folderId": to_global_id("CorpusFolderType", _MALFORMED_PK),
                "name": "Whatever",
            },
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["updateCorpusFolder"]
        self.assertFalse(data["ok"])
        self.assertIn("failed to update folder", data["message"].lower())


class MoveCorpusFolderCoverageTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="cff_move_owner", password="pw")
        self.outsider = User.objects.create_user(
            username="cff_move_outsider", password="pw"
        )
        self.corpus = Corpus.objects.create(
            title="Private Corpus", creator=self.owner, is_public=False
        )
        self.folder = CorpusFolder.objects.create(
            name="Root", corpus=self.corpus, creator=self.owner
        )

    def test_unauthenticated_raises(self):
        client = Client(schema, context_value=TestContext(AnonymousUser()))
        result = client.execute(
            MOVE_FOLDER_MUTATION,
            variables={"folderId": to_global_id("CorpusFolderType", self.folder.id)},
        )
        self.assertIsNotNone(result.get("errors"))

    def test_corpus_not_visible_returns_folder_not_found(self):
        """``outsider`` has zero permissions on the private corpus, so even
        though the folder row exists, the corpus-visibility gate raises
        CorpusFolder.DoesNotExist (IDOR-safe: same message as a truly
        missing folder)."""
        client = Client(schema, context_value=TestContext(self.outsider))
        result = client.execute(
            MOVE_FOLDER_MUTATION,
            variables={"folderId": to_global_id("CorpusFolderType", self.folder.id)},
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["moveCorpusFolder"]
        self.assertFalse(data["ok"])
        self.assertIn("not found", data["message"].lower())

    def test_malformed_folder_id_returns_generic_failure(self):
        client = Client(schema, context_value=TestContext(self.owner))
        result = client.execute(
            MOVE_FOLDER_MUTATION,
            variables={"folderId": to_global_id("CorpusFolderType", _MALFORMED_PK)},
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["moveCorpusFolder"]
        self.assertFalse(data["ok"])
        self.assertIn("failed to move folder", data["message"].lower())


class DeleteCorpusFolderCoverageTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="cff_del_owner", password="pw")
        self.editor = User.objects.create_user(username="cff_del_editor", password="pw")
        self.corpus = Corpus.objects.create(title="Coverage Corpus", creator=self.owner)
        self.folder = CorpusFolder.objects.create(
            name="ToDelete", corpus=self.corpus, creator=self.owner
        )

    def test_unauthenticated_raises(self):
        client = Client(schema, context_value=TestContext(AnonymousUser()))
        result = client.execute(
            DELETE_FOLDER_MUTATION,
            variables={"folderId": to_global_id("CorpusFolderType", self.folder.id)},
        )
        self.assertIsNotNone(result.get("errors"))

    def test_update_permission_without_delete_is_denied(self):
        """``editor`` can see and edit the corpus (READ + UPDATE) but was
        never granted DELETE, so FolderCRUDService.delete_folder's own
        permission check (distinct from the outer corpus-visibility gate)
        rejects the request."""
        set_permissions_for_obj_to_user(
            self.editor, self.corpus, [PermissionTypes.READ, PermissionTypes.UPDATE]
        )
        client = Client(schema, context_value=TestContext(self.editor))
        result = client.execute(
            DELETE_FOLDER_MUTATION,
            variables={"folderId": to_global_id("CorpusFolderType", self.folder.id)},
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["deleteCorpusFolder"]
        self.assertFalse(data["ok"])
        self.assertIn("delete access", data["message"].lower())
        self.assertTrue(CorpusFolder.objects.filter(id=self.folder.id).exists())

    def test_malformed_folder_id_returns_generic_failure(self):
        client = Client(schema, context_value=TestContext(self.owner))
        result = client.execute(
            DELETE_FOLDER_MUTATION,
            variables={"folderId": to_global_id("CorpusFolderType", _MALFORMED_PK)},
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["deleteCorpusFolder"]
        self.assertFalse(data["ok"])
        self.assertIn("failed to delete folder", data["message"].lower())


class MoveDocumentToFolderCoverageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="cff_movedoc_user", password="pw")
        self.corpus = Corpus.objects.create(title="Coverage Corpus", creator=self.user)
        self.folder = CorpusFolder.objects.create(
            name="Research", corpus=self.corpus, creator=self.user
        )
        doc = Document.objects.create(title="In Corpus Doc", creator=self.user)
        self.document, _, _ = self.corpus.add_document(document=doc, user=self.user)

    def test_unauthenticated_raises(self):
        client = Client(schema, context_value=TestContext(AnonymousUser()))
        result = client.execute(
            MOVE_DOCUMENT_MUTATION,
            variables={
                "documentId": to_global_id("DocumentType", self.document.id),
                "corpusId": to_global_id("CorpusType", self.corpus.id),
            },
        )
        self.assertIsNotNone(result.get("errors"))

    def test_document_not_visible_returns_document_not_found(self):
        """A document the user cannot see (private, owned by someone else)
        makes ``BaseService.get_or_none`` return None, raising
        Document.DoesNotExist inside the mutation."""
        other_owner = User.objects.create_user(
            username="cff_movedoc_otherowner", password="pw"
        )
        hidden_doc = Document.objects.create(
            title="Hidden Doc", creator=other_owner, is_public=False
        )
        client = Client(schema, context_value=TestContext(self.user))
        result = client.execute(
            MOVE_DOCUMENT_MUTATION,
            variables={
                "documentId": to_global_id("DocumentType", hidden_doc.id),
                "corpusId": to_global_id("CorpusType", self.corpus.id),
            },
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["moveDocumentToFolder"]
        self.assertFalse(data["ok"])
        self.assertIn("document not found", data["message"].lower())

    def test_corpus_not_visible_returns_corpus_not_found(self):
        """A corpus the user cannot see makes ``BaseService.get_or_none``
        return None, raising Corpus.DoesNotExist inside the mutation."""
        other_owner = User.objects.create_user(
            username="cff_movedoc_othercorpusowner", password="pw"
        )
        hidden_corpus = Corpus.objects.create(
            title="Hidden Corpus", creator=other_owner, is_public=False
        )
        client = Client(schema, context_value=TestContext(self.user))
        result = client.execute(
            MOVE_DOCUMENT_MUTATION,
            variables={
                "documentId": to_global_id("DocumentType", self.document.id),
                "corpusId": to_global_id("CorpusType", hidden_corpus.id),
            },
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["moveDocumentToFolder"]
        self.assertFalse(data["ok"])
        self.assertIn("corpus not found", data["message"].lower())

    def test_nonexistent_folder_id_returns_folder_not_found(self):
        deleted_folder_id = self.folder.id
        self.folder.delete()
        client = Client(schema, context_value=TestContext(self.user))
        result = client.execute(
            MOVE_DOCUMENT_MUTATION,
            variables={
                "documentId": to_global_id("DocumentType", self.document.id),
                "corpusId": to_global_id("CorpusType", self.corpus.id),
                "folderId": to_global_id("CorpusFolderType", deleted_folder_id),
            },
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["moveDocumentToFolder"]
        self.assertFalse(data["ok"])
        self.assertIn("folder not found", data["message"].lower())

    def test_document_not_in_corpus_returns_service_error(self):
        """The document exists and is visible, but was never added to this
        corpus (no DocumentPath row), so
        FolderDocumentService.move_document_to_folder's membership check
        rejects the move."""
        orphan_doc = Document.objects.create(title="Orphan Doc", creator=self.user)
        client = Client(schema, context_value=TestContext(self.user))
        result = client.execute(
            MOVE_DOCUMENT_MUTATION,
            variables={
                "documentId": to_global_id("DocumentType", orphan_doc.id),
                "corpusId": to_global_id("CorpusType", self.corpus.id),
            },
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["moveDocumentToFolder"]
        self.assertFalse(data["ok"])
        self.assertIn("does not belong to this corpus", data["message"].lower())

    def test_malformed_folder_id_returns_generic_failure(self):
        client = Client(schema, context_value=TestContext(self.user))
        result = client.execute(
            MOVE_DOCUMENT_MUTATION,
            variables={
                "documentId": to_global_id("DocumentType", self.document.id),
                "corpusId": to_global_id("CorpusType", self.corpus.id),
                "folderId": to_global_id("CorpusFolderType", _MALFORMED_PK),
            },
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["moveDocumentToFolder"]
        self.assertFalse(data["ok"])
        self.assertIn("failed to move document", data["message"].lower())


class MoveDocumentsToFolderCoverageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="cff_movedocs_user", password="pw"
        )
        self.corpus = Corpus.objects.create(title="Coverage Corpus", creator=self.user)
        self.folder = CorpusFolder.objects.create(
            name="Research", corpus=self.corpus, creator=self.user
        )
        docs = [
            Document.objects.create(title=f"Bulk Doc {i}", creator=self.user)
            for i in range(2)
        ]
        self.documents = []
        for doc in docs:
            added, _, _ = self.corpus.add_document(document=doc, user=self.user)
            self.documents.append(added)

    def test_unauthenticated_raises(self):
        client = Client(schema, context_value=TestContext(AnonymousUser()))
        result = client.execute(
            MOVE_DOCUMENTS_MUTATION,
            variables={
                "documentIds": [
                    to_global_id("DocumentType", d.id) for d in self.documents
                ],
                "corpusId": to_global_id("CorpusType", self.corpus.id),
            },
        )
        self.assertIsNotNone(result.get("errors"))

    def test_corpus_not_visible_returns_corpus_not_found(self):
        other_owner = User.objects.create_user(
            username="cff_movedocs_othercorpusowner", password="pw"
        )
        hidden_corpus = Corpus.objects.create(
            title="Hidden Corpus", creator=other_owner, is_public=False
        )
        client = Client(schema, context_value=TestContext(self.user))
        result = client.execute(
            MOVE_DOCUMENTS_MUTATION,
            variables={
                "documentIds": [
                    to_global_id("DocumentType", d.id) for d in self.documents
                ],
                "corpusId": to_global_id("CorpusType", hidden_corpus.id),
            },
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["moveDocumentsToFolder"]
        self.assertFalse(data["ok"])
        self.assertIn("corpus not found", data["message"].lower())

    def test_nonexistent_folder_id_returns_folder_not_found(self):
        deleted_folder_id = self.folder.id
        self.folder.delete()
        client = Client(schema, context_value=TestContext(self.user))
        result = client.execute(
            MOVE_DOCUMENTS_MUTATION,
            variables={
                "documentIds": [
                    to_global_id("DocumentType", d.id) for d in self.documents
                ],
                "corpusId": to_global_id("CorpusType", self.corpus.id),
                "folderId": to_global_id("CorpusFolderType", deleted_folder_id),
            },
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["moveDocumentsToFolder"]
        self.assertFalse(data["ok"])
        self.assertIn("folder not found", data["message"].lower())

    def test_document_missing_from_corpus_returns_service_error(self):
        """One of the requested document ids was never added to this
        corpus, so FolderDocumentService.move_documents_to_folder's
        membership check rejects the whole batch (0 moved)."""
        orphan_doc = Document.objects.create(title="Orphan Doc", creator=self.user)
        client = Client(schema, context_value=TestContext(self.user))
        result = client.execute(
            MOVE_DOCUMENTS_MUTATION,
            variables={
                "documentIds": [
                    to_global_id("DocumentType", d.id) for d in self.documents
                ]
                + [to_global_id("DocumentType", orphan_doc.id)],
                "corpusId": to_global_id("CorpusType", self.corpus.id),
            },
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["moveDocumentsToFolder"]
        self.assertFalse(data["ok"])
        self.assertIn("do not belong to this corpus", data["message"].lower())
        self.assertEqual(data["movedCount"], 0)

    def test_malformed_folder_id_returns_generic_failure(self):
        client = Client(schema, context_value=TestContext(self.user))
        result = client.execute(
            MOVE_DOCUMENTS_MUTATION,
            variables={
                "documentIds": [
                    to_global_id("DocumentType", d.id) for d in self.documents
                ],
                "corpusId": to_global_id("CorpusType", self.corpus.id),
                "folderId": to_global_id("CorpusFolderType", _MALFORMED_PK),
            },
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["moveDocumentsToFolder"]
        self.assertFalse(data["ok"])
        self.assertIn("failed to move documents", data["message"].lower())
