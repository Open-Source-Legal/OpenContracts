"""
Tests for IngestionSource CRUD mutations, query resolvers, UploadDocument
integration, and export/import round-trip.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.document_types import DocumentPathType
from config.graphql.schema import schema
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import (
    Document,
    DocumentPath,
    IngestionSource,
    IngestionSourceCategory,
)
from opencontractserver.tasks.import_tasks_v2 import _import_ingestion_sources
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.export_v2 import package_ingestion_sources
from opencontractserver.utils.files import base_64_encode_bytes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class TestContext:
    def __init__(self, user):
        self.user = user


class AnonymousContext:
    """Anonymous user context for GraphQL client."""

    class AnonymousUser:
        is_authenticated = False
        is_superuser = False
        id = None

        @property
        def is_anonymous(self):
            return True

    user = AnonymousUser()


# ------------------------------------------------------------------ #
# GraphQL mutation / query strings
# ------------------------------------------------------------------ #

CREATE_MUTATION = """
    mutation CreateIngestionSource(
        $name: String!,
        $sourceType: IngestionSourceTypeEnum,
        $config: GenericScalar
    ) {
        createIngestionSource(
            name: $name,
            sourceType: $sourceType,
            config: $config
        ) {
            ok
            message
            ingestionSource {
                id
                name
                sourceType
                active
            }
        }
    }
"""

UPDATE_MUTATION = """
    mutation UpdateIngestionSource(
        $id: ID!,
        $name: String,
        $sourceType: IngestionSourceTypeEnum,
        $config: GenericScalar,
        $active: Boolean
    ) {
        updateIngestionSource(
            id: $id,
            name: $name,
            sourceType: $sourceType,
            config: $config,
            active: $active
        ) {
            ok
            message
            ingestionSource {
                id
                name
                sourceType
                active
            }
        }
    }
"""

DELETE_MUTATION = """
    mutation DeleteIngestionSource($id: ID!) {
        deleteIngestionSource(id: $id) {
            ok
            message
        }
    }
"""

UPLOAD_DOCUMENT_MUTATION = """
    mutation UploadDocument(
        $file: String!,
        $filename: String!,
        $title: String!,
        $description: String!,
        $customMeta: GenericScalar!,
        $makePublic: Boolean!,
        $ingestionSourceId: ID
    ) {
        uploadDocument(
            base64FileString: $file,
            filename: $filename,
            title: $title,
            description: $description,
            customMeta: $customMeta,
            makePublic: $makePublic,
            ingestionSourceId: $ingestionSourceId
        ) {
            ok
            message
            document { id title }
        }
    }
"""


# ------------------------------------------------------------------ #
# CreateIngestionSourceMutation
# ------------------------------------------------------------------ #


class TestCreateIngestionSourceMutation(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client = Client(schema, context_value=TestContext(self.user))

    def test_create_happy_path(self):
        result = self.client.execute(
            CREATE_MUTATION,
            variables={"name": "my_crawler", "sourceType": "CRAWLER"},
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["createIngestionSource"]
        self.assertTrue(data["ok"])
        self.assertEqual(data["message"], "Success")
        self.assertEqual(data["ingestionSource"]["name"], "my_crawler")
        # graphene-django auto-enum converts choice values to uppercase names
        self.assertEqual(data["ingestionSource"]["sourceType"], "CRAWLER")
        self.assertTrue(data["ingestionSource"]["active"])

        # Verify DB record
        source = IngestionSource.objects.get(name="my_crawler", creator=self.user)
        self.assertEqual(source.source_type, IngestionSourceCategory.CRAWLER)

    def test_create_defaults_to_manual(self):
        result = self.client.execute(
            CREATE_MUTATION,
            variables={"name": "default_source"},
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["createIngestionSource"]
        self.assertTrue(data["ok"])

        source = IngestionSource.objects.get(name="default_source", creator=self.user)
        self.assertEqual(source.source_type, IngestionSourceCategory.MANUAL)

    def test_create_duplicate_name(self):
        IngestionSource.objects.create(
            name="dup_name", creator=self.user, source_type="manual"
        )

        result = self.client.execute(
            CREATE_MUTATION,
            variables={"name": "dup_name"},
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["createIngestionSource"]
        self.assertFalse(data["ok"])
        self.assertIn("already exists", data["message"])

    def test_create_unauthenticated(self):
        anon_client = Client(schema, context_value=AnonymousContext())
        result = anon_client.execute(
            CREATE_MUTATION,
            variables={"name": "should_fail"},
        )
        # graphql_jwt returns errors for unauthenticated
        self.assertIsNotNone(result.get("errors"))


# ------------------------------------------------------------------ #
# UpdateIngestionSourceMutation
# ------------------------------------------------------------------ #


class TestUpdateIngestionSourceMutation(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.source = IngestionSource.objects.create(
            name="original_name",
            source_type=IngestionSourceCategory.MANUAL,
            creator=self.user,
            config={"key": "value"},
        )
        set_permissions_for_obj_to_user(self.user, self.source, [PermissionTypes.CRUD])
        self.global_id = to_global_id("IngestionSourceType", self.source.pk)
        self.client = Client(schema, context_value=TestContext(self.user))

    def test_update_field_values(self):
        result = self.client.execute(
            UPDATE_MUTATION,
            variables={
                "id": self.global_id,
                "name": "updated_name",
                "sourceType": "API",
            },
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["updateIngestionSource"]
        self.assertTrue(data["ok"])
        self.assertEqual(data["ingestionSource"]["name"], "updated_name")
        self.assertEqual(data["ingestionSource"]["sourceType"], "API")

    def test_update_active_toggle(self):
        result = self.client.execute(
            UPDATE_MUTATION,
            variables={"id": self.global_id, "active": False},
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["updateIngestionSource"]
        self.assertTrue(data["ok"])
        self.assertFalse(data["ingestionSource"]["active"])

        self.source.refresh_from_db()
        self.assertFalse(self.source.active)

    def test_update_active_reactivation(self):
        """Deactivate then re-activate a source."""
        # First deactivate
        self.client.execute(
            UPDATE_MUTATION,
            variables={"id": self.global_id, "active": False},
        )
        self.source.refresh_from_db()
        self.assertFalse(self.source.active)

        # Now re-activate
        result = self.client.execute(
            UPDATE_MUTATION,
            variables={"id": self.global_id, "active": True},
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["updateIngestionSource"]
        self.assertTrue(data["ok"])
        self.assertTrue(data["ingestionSource"]["active"])

        self.source.refresh_from_db()
        self.assertTrue(self.source.active)

    def test_update_not_found(self):
        bad_id = to_global_id("IngestionSourceType", 999999)
        result = self.client.execute(
            UPDATE_MUTATION,
            variables={"id": bad_id, "name": "x"},
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["updateIngestionSource"]
        self.assertFalse(data["ok"])
        self.assertIn("not found", data["message"])

    def test_update_other_users_source(self):
        other_user = User.objects.create_user(username="other", password="otherpass")
        other_source = IngestionSource.objects.create(
            name="other_source", creator=other_user
        )
        other_id = to_global_id("IngestionSourceType", other_source.pk)

        result = self.client.execute(
            UPDATE_MUTATION,
            variables={"id": other_id, "name": "hijack"},
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["updateIngestionSource"]
        self.assertFalse(data["ok"])
        self.assertIn("not found", data["message"])


# ------------------------------------------------------------------ #
# DeleteIngestionSourceMutation
# ------------------------------------------------------------------ #


class TestDeleteIngestionSourceMutation(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client = Client(schema, context_value=TestContext(self.user))

    def test_delete_happy_path(self):
        source = IngestionSource.objects.create(name="to_delete", creator=self.user)
        set_permissions_for_obj_to_user(self.user, source, [PermissionTypes.CRUD])
        global_id = to_global_id("IngestionSourceType", source.pk)

        result = self.client.execute(DELETE_MUTATION, variables={"id": global_id})
        self.assertIsNone(result.get("errors"))
        data = result["data"]["deleteIngestionSource"]
        self.assertTrue(data["ok"])
        self.assertFalse(IngestionSource.objects.filter(pk=source.pk).exists())

    def test_delete_not_found(self):
        bad_id = to_global_id("IngestionSourceType", 999999)
        result = self.client.execute(DELETE_MUTATION, variables={"id": bad_id})
        self.assertIsNone(result.get("errors"))
        data = result["data"]["deleteIngestionSource"]
        self.assertFalse(data["ok"])
        self.assertIn("not found", data["message"])

    def test_delete_sets_null_on_document_path(self):
        """Verify FK SET_NULL: deleting a source nullifies DocumentPath references."""
        source = IngestionSource.objects.create(
            name="source_with_paths", creator=self.user
        )
        set_permissions_for_obj_to_user(self.user, source, [PermissionTypes.CRUD])

        corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)
        doc = Document.objects.create(
            title="Test Doc", creator=self.user, pdf_file="test.pdf"
        )
        doc_path = DocumentPath.objects.create(
            document=doc,
            corpus=corpus,
            path="/documents/test.pdf",
            version_number=1,
            ingestion_source=source,
            creator=self.user,
        )

        global_id = to_global_id("IngestionSourceType", source.pk)
        result = self.client.execute(DELETE_MUTATION, variables={"id": global_id})
        self.assertTrue(result["data"]["deleteIngestionSource"]["ok"])

        doc_path.refresh_from_db()
        self.assertIsNone(doc_path.ingestion_source)


# ------------------------------------------------------------------ #
# UploadDocument with ingestion_source_id
# ------------------------------------------------------------------ #


class TestUploadDocumentWithIngestionSource(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client = Client(schema, context_value=TestContext(self.user))
        self.source = IngestionSource.objects.create(
            name="upload_source",
            source_type=IngestionSourceCategory.API,
            creator=self.user,
        )
        set_permissions_for_obj_to_user(self.user, self.source, [PermissionTypes.CRUD])

    def test_upload_with_valid_source(self):
        pdf_content = b"%PDF-1.5\n%\xe2\xe3\xcf\xd3\n"
        pdf_base64 = base_64_encode_bytes(pdf_content)
        source_gid = to_global_id("IngestionSourceType", self.source.pk)

        mock_doc = Document(id=999999, title="Test PDF", description="desc")
        mock_path = DocumentPath(id=999999, path="/documents/test.pdf")

        with patch(
            "opencontractserver.corpuses.models.Corpus.import_content"
        ) as mock_import, patch(
            "opencontractserver.document_imports.services.set_permissions_for_obj_to_user"
        ):
            mock_import.return_value = (mock_doc, "created", mock_path)
            result = self.client.execute(
                UPLOAD_DOCUMENT_MUTATION,
                variables={
                    "file": pdf_base64,
                    "filename": "test.pdf",
                    "title": "Test PDF",
                    "description": "desc",
                    "customMeta": {},
                    "makePublic": False,
                    "ingestionSourceId": source_gid,
                },
            )

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["uploadDocument"]["ok"])

    def test_upload_with_other_users_source(self):
        """Source belonging to another user should be rejected."""
        other_user = User.objects.create_user(username="other", password="otherpass")
        other_source = IngestionSource.objects.create(
            name="other_source", creator=other_user
        )
        bad_gid = to_global_id("IngestionSourceType", other_source.pk)

        pdf_content = b"%PDF-1.5\n%\xe2\xe3\xcf\xd3\n"
        pdf_base64 = base_64_encode_bytes(pdf_content)

        result = self.client.execute(
            UPLOAD_DOCUMENT_MUTATION,
            variables={
                "file": pdf_base64,
                "filename": "test.pdf",
                "title": "Test PDF",
                "description": "desc",
                "customMeta": {},
                "makePublic": False,
                "ingestionSourceId": bad_gid,
            },
        )

        self.assertIsNone(result.get("errors"))
        data = result["data"]["uploadDocument"]
        self.assertFalse(data["ok"])
        self.assertIn("not found", data["message"])


# ------------------------------------------------------------------ #
# Export / import round-trip for ingestion sources
# ------------------------------------------------------------------ #


class TestIngestionSourceExportImport(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.corpus = Corpus.objects.create(
            title="Export Test Corpus", creator=self.user
        )
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.ALL])

    def test_package_ingestion_sources_strips_config(self):
        """Config must not leak credentials in exports."""
        source = IngestionSource.objects.create(
            name="secret_crawler",
            source_type=IngestionSourceCategory.CRAWLER,
            config={"api_key": "super_secret_123", "endpoint": "https://example.com"},
            creator=self.user,
        )
        doc = Document.objects.create(
            title="Doc", creator=self.user, pdf_file="doc.pdf"
        )
        DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            path="/documents/doc.pdf",
            version_number=1,
            ingestion_source=source,
            creator=self.user,
        )

        exported = package_ingestion_sources(self.corpus)
        self.assertEqual(len(exported), 1)
        self.assertEqual(exported[0]["name"], "secret_crawler")
        self.assertEqual(exported[0]["source_type"], IngestionSourceCategory.CRAWLER)
        # Config must be empty - credentials should NOT leak
        self.assertEqual(exported[0]["config"], {})

    def test_package_returns_empty_for_no_sources(self):
        """Corpus with no ingestion sources should return empty list."""
        exported = package_ingestion_sources(self.corpus)
        self.assertEqual(exported, [])

    def test_round_trip_export_import(self):
        """Export sources -> import on different user -> verify re-creation."""
        source = IngestionSource.objects.create(
            name="roundtrip_source",
            source_type=IngestionSourceCategory.API,
            config={"key": "should_be_stripped"},
            active=True,
            creator=self.user,
        )
        doc = Document.objects.create(
            title="Doc", creator=self.user, pdf_file="doc.pdf"
        )
        DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            path="/documents/doc.pdf",
            version_number=1,
            ingestion_source=source,
            creator=self.user,
        )

        # Export
        exported = package_ingestion_sources(self.corpus)
        self.assertEqual(len(exported), 1)

        # Import as a different user
        importer = User.objects.create_user(username="importer", password="importpass")
        source_map = _import_ingestion_sources(exported, importer)

        self.assertIn("roundtrip_source", source_map)
        imported_source = source_map["roundtrip_source"]
        self.assertEqual(imported_source.creator, importer)
        self.assertEqual(imported_source.source_type, IngestionSourceCategory.API)
        self.assertTrue(imported_source.active)

    def test_import_idempotent(self):
        """Re-importing the same source name reuses existing record."""
        sources_data = [
            {
                "name": "reuse_me",
                "source_type": IngestionSourceCategory.MANUAL,
                "config": {},
                "active": True,
            }
        ]

        first_map = _import_ingestion_sources(sources_data, self.user)
        first_id = first_map["reuse_me"].pk

        second_map = _import_ingestion_sources(sources_data, self.user)
        second_id = second_map["reuse_me"].pk

        self.assertEqual(first_id, second_id)
        self.assertEqual(
            IngestionSource.objects.filter(creator=self.user, name="reuse_me").count(),
            1,
        )


# ------------------------------------------------------------------ #
# resolve_ingestion_source query (single-object resolver)
# ------------------------------------------------------------------ #


SINGLE_SOURCE_QUERY = """
    query GetIngestionSource($id: ID!) {
        ingestionSource(id: $id) {
            id
            name
            sourceType
            active
        }
    }
"""


class TestIngestionSourceQuery(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client = Client(schema, context_value=TestContext(self.user))
        self.source = IngestionSource.objects.create(
            name="query_source",
            source_type=IngestionSourceCategory.CRAWLER,
            creator=self.user,
        )
        set_permissions_for_obj_to_user(self.user, self.source, [PermissionTypes.CRUD])

    def test_resolve_existing_source(self):
        gid = to_global_id("IngestionSourceType", self.source.pk)
        result = self.client.execute(SINGLE_SOURCE_QUERY, variables={"id": gid})
        self.assertIsNone(result.get("errors"))
        data = result["data"]["ingestionSource"]
        self.assertIsNotNone(data)
        self.assertEqual(data["name"], "query_source")
        self.assertEqual(data["sourceType"], "CRAWLER")

    def test_resolve_not_found_returns_none(self):
        """Should return None rather than 500 on missing source."""
        bad_id = to_global_id("IngestionSourceType", 999999)
        result = self.client.execute(SINGLE_SOURCE_QUERY, variables={"id": bad_id})
        # Should not have GraphQL errors (no 500)
        self.assertIsNone(result.get("errors"))
        self.assertIsNone(result["data"]["ingestionSource"])

    def test_resolve_malformed_global_id_returns_none(self):
        """Malformed base64 global ID should return None, not 500."""
        result = self.client.execute(
            SINGLE_SOURCE_QUERY, variables={"id": "not-valid-base64!@#$"}
        )
        self.assertIsNone(result.get("errors"))
        self.assertIsNone(result["data"]["ingestionSource"])

    def test_resolve_other_users_source_returns_none(self):
        """Source owned by a different user should not be visible."""
        other_user = User.objects.create_user(username="other", password="otherpass")
        other_source = IngestionSource.objects.create(
            name="private_source", creator=other_user
        )
        gid = to_global_id("IngestionSourceType", other_source.pk)
        result = self.client.execute(SINGLE_SOURCE_QUERY, variables={"id": gid})
        self.assertIsNone(result.get("errors"))
        self.assertIsNone(result["data"]["ingestionSource"])

    def test_internal_fields_not_exposed_on_type(self):
        """``userLock``, ``backendLock``, and ``isPublic`` from BaseOCModel
        must not be queryable on IngestionSourceType — they were explicitly
        excluded from the Meta fields allowlist to avoid leaking internal
        state (user_lock would leak the username of whoever holds the lock).
        """
        leak_query = """
            query GetIngestionSource($id: ID!) {
                ingestionSource(id: $id) {
                    id
                    userLock { username }
                    backendLock
                    isPublic
                }
            }
        """
        gid = to_global_id("IngestionSourceType", self.source.pk)
        result = self.client.execute(leak_query, variables={"id": gid})
        # A GraphQL validation error is expected because these fields should
        # not exist on the type at all.
        self.assertIsNotNone(result.get("errors"))
        error_messages = " ".join(str(e.get("message", "")) for e in result["errors"])
        self.assertIn("userLock", error_messages)


# ------------------------------------------------------------------ #
# ingestionSources list query
# ------------------------------------------------------------------ #

LIST_SOURCES_QUERY = """
    query ListIngestionSources($activeOnly: Boolean) {
        ingestionSources(activeOnly: $activeOnly) {
            id
            name
            sourceType
            active
        }
    }
"""


class TestIngestionSourceListQuery(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client = Client(schema, context_value=TestContext(self.user))

        self.active_source = IngestionSource.objects.create(
            name="active_crawler",
            source_type=IngestionSourceCategory.CRAWLER,
            active=True,
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, self.active_source, [PermissionTypes.CRUD]
        )

        self.inactive_source = IngestionSource.objects.create(
            name="inactive_api",
            source_type=IngestionSourceCategory.API,
            active=False,
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, self.inactive_source, [PermissionTypes.CRUD]
        )

    def test_list_all_sources(self):
        """Default query returns both active and inactive sources."""
        result = self.client.execute(LIST_SOURCES_QUERY)
        self.assertIsNone(result.get("errors"))
        sources = result["data"]["ingestionSources"]
        names = [s["name"] for s in sources]
        self.assertIn("active_crawler", names)
        self.assertIn("inactive_api", names)

    def test_list_active_only(self):
        """active_only=True filters out inactive sources."""
        result = self.client.execute(LIST_SOURCES_QUERY, variables={"activeOnly": True})
        self.assertIsNone(result.get("errors"))
        sources = result["data"]["ingestionSources"]
        names = [s["name"] for s in sources]
        self.assertIn("active_crawler", names)
        self.assertNotIn("inactive_api", names)

    def test_list_excludes_other_users_sources(self):
        """Sources from other users should not appear in the list."""
        other_user = User.objects.create_user(username="other", password="otherpass")
        IngestionSource.objects.create(
            name="other_source", creator=other_user, active=True
        )

        result = self.client.execute(LIST_SOURCES_QUERY)
        self.assertIsNone(result.get("errors"))
        sources = result["data"]["ingestionSources"]
        names = [s["name"] for s in sources]
        self.assertNotIn("other_source", names)


# ------------------------------------------------------------------ #
# DocumentPathType.resolve_action coverage
# ------------------------------------------------------------------ #


class TestDocumentPathResolveAction(TestCase):
    """Test the resolve_action method on DocumentPathType for all branches."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)
        self.doc = Document.objects.create(
            title="Test Doc", creator=self.user, pdf_file="test.pdf"
        )

    def test_action_imported_no_parent(self):
        """A path with no parent is an IMPORTED action."""
        path = DocumentPath.objects.create(
            document=self.doc,
            corpus=self.corpus,
            path="/documents/test.pdf",
            version_number=1,
            parent=None,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )
        result = DocumentPathType.resolve_action(path, info=None)
        self.assertEqual(result, "IMPORTED")

    def test_action_deleted(self):
        """A deleted path returns DELETED regardless of parent."""
        root = DocumentPath.objects.create(
            document=self.doc,
            corpus=self.corpus,
            path="/documents/test.pdf",
            version_number=1,
            parent=None,
            is_current=False,
            is_deleted=False,
            creator=self.user,
        )
        deleted_path = DocumentPath.objects.create(
            document=self.doc,
            corpus=self.corpus,
            path="/documents/test.pdf",
            version_number=1,
            parent=root,
            is_current=True,
            is_deleted=True,
            creator=self.user,
        )
        result = DocumentPathType.resolve_action(deleted_path, info=None)
        self.assertEqual(result, "DELETED")

    def test_action_moved_different_path(self):
        """A path with a different path from parent is MOVED."""
        root = DocumentPath.objects.create(
            document=self.doc,
            corpus=self.corpus,
            path="/documents/old.pdf",
            version_number=1,
            parent=None,
            is_current=False,
            is_deleted=False,
            creator=self.user,
        )
        moved_path = DocumentPath.objects.create(
            document=self.doc,
            corpus=self.corpus,
            path="/documents/new.pdf",
            version_number=1,
            parent=root,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )
        result = DocumentPathType.resolve_action(moved_path, info=None)
        self.assertEqual(result, "MOVED")

    def test_action_updated_different_version(self):
        """A path with same path but different version from parent is UPDATED."""
        root = DocumentPath.objects.create(
            document=self.doc,
            corpus=self.corpus,
            path="/documents/test.pdf",
            version_number=1,
            parent=None,
            is_current=False,
            is_deleted=False,
            creator=self.user,
        )
        updated_path = DocumentPath.objects.create(
            document=self.doc,
            corpus=self.corpus,
            path="/documents/test.pdf",
            version_number=2,
            parent=root,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )
        result = DocumentPathType.resolve_action(updated_path, info=None)
        self.assertEqual(result, "UPDATED")

    def test_action_updated_same_version_same_path(self):
        """A path with parent, same path and same version falls through to UPDATED."""
        root = DocumentPath.objects.create(
            document=self.doc,
            corpus=self.corpus,
            path="/documents/test.pdf",
            version_number=1,
            parent=None,
            is_current=False,
            is_deleted=False,
            creator=self.user,
        )
        child = DocumentPath.objects.create(
            document=self.doc,
            corpus=self.corpus,
            path="/documents/test.pdf",
            version_number=1,
            parent=root,
            is_current=True,
            is_deleted=False,
            creator=self.user,
        )
        result = DocumentPathType.resolve_action(child, info=None)
        self.assertEqual(result, "UPDATED")


# ------------------------------------------------------------------ #
# Export with lineage fields round-trip
# ------------------------------------------------------------------ #


class TestExportWithLineageFields(TestCase):
    """Test package_document_paths includes ingestion lineage fields."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.ALL])

    def test_export_includes_lineage_fields(self):
        """Exported paths should include ingestion_source_name, external_id,
        and ingestion_metadata when present."""
        source = IngestionSource.objects.create(
            name="test_crawler",
            source_type=IngestionSourceCategory.CRAWLER,
            creator=self.user,
        )
        doc = Document.objects.create(
            title="Lineage Doc", creator=self.user, pdf_file="doc.pdf"
        )
        DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            path="/documents/doc.pdf",
            version_number=1,
            ingestion_source=source,
            external_id="ext-123",
            ingestion_metadata={"url": "https://example.com"},
            creator=self.user,
        )

        from opencontractserver.utils.export_v2 import package_document_paths

        exported = package_document_paths(self.corpus)
        self.assertEqual(len(exported), 1)
        entry = exported[0]
        self.assertEqual(entry.get("ingestion_source_name"), "test_crawler")
        self.assertEqual(entry.get("external_id"), "ext-123")
        self.assertEqual(
            entry.get("ingestion_metadata"), {"url": "https://example.com"}
        )

    def test_export_omits_lineage_fields_when_absent(self):
        """Exported paths without lineage data should not include those keys."""
        doc = Document.objects.create(
            title="Plain Doc", creator=self.user, pdf_file="doc.pdf"
        )
        DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            path="/documents/plain.pdf",
            version_number=1,
            creator=self.user,
            ingestion_metadata=None,
        )

        from opencontractserver.utils.export_v2 import package_document_paths

        exported = package_document_paths(self.corpus)
        self.assertEqual(len(exported), 1)
        entry = exported[0]
        self.assertNotIn("ingestion_source_name", entry)
        self.assertNotIn("external_id", entry)
        self.assertNotIn("ingestion_metadata", entry)

    def test_export_omits_empty_dict_ingestion_metadata(self):
        """Paths with default empty-dict ingestion_metadata should not export
        the field, avoiding noise in the export output."""
        doc = Document.objects.create(
            title="Default Meta Doc", creator=self.user, pdf_file="doc.pdf"
        )
        # Create path without explicitly setting ingestion_metadata;
        # the model default (jsonfield_default_value) produces {}.
        path = DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            path="/documents/default_meta.pdf",
            version_number=1,
            creator=self.user,
        )
        # Confirm the default is indeed an empty dict
        self.assertEqual(path.ingestion_metadata, {})

        from opencontractserver.utils.export_v2 import package_document_paths

        exported = package_document_paths(self.corpus)
        self.assertEqual(len(exported), 1)
        entry = exported[0]
        # Empty dict should be omitted from export (truthiness check)
        self.assertNotIn("ingestion_metadata", entry)


# ------------------------------------------------------------------ #
# Import with lineage fields
# ------------------------------------------------------------------ #


class TestImportReconstructLineage(TestCase):
    """Test _reconstruct_document_paths restores ingestion lineage fields."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.corpus = Corpus.objects.create(title="Import Corpus", creator=self.user)
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.ALL])

    def test_reconstruct_with_lineage_fields(self):
        """_reconstruct_document_paths should set lineage fields on existing paths."""
        from opencontractserver.tasks.import_tasks_v2 import (
            _import_ingestion_sources,
            _reconstruct_document_paths,
        )

        # Create a doc and path (simulating what corpus.add_document does)
        doc = Document.objects.create(
            title="Test Doc",
            creator=self.user,
            pdf_file="test.pdf",
            pdf_file_hash="abc123",
        )
        doc_path = DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            path="/documents/test.pdf",
            version_number=1,
            is_current=True,
            creator=self.user,
        )

        # Import sources
        source_data = [
            {
                "name": "my_crawler",
                "source_type": "crawler",
                "config": {},
                "active": True,
            }
        ]
        source_map = _import_ingestion_sources(source_data, self.user)
        self.assertIn("my_crawler", source_map)

        # Reconstruct paths with lineage
        path_data = [
            {
                "document_ref": "abc123",
                "path": "/documents/test.pdf",
                "version_number": 1,
                "is_current": True,
                "is_deleted": False,
                "ingestion_source_name": "my_crawler",
                "external_id": "ext-456",
                "ingestion_metadata": {"job_id": "job-789"},
            }
        ]
        _reconstruct_document_paths(
            path_data, self.corpus, {"abc123": doc}, [], {}, source_map
        )

        doc_path.refresh_from_db()
        self.assertEqual(doc_path.ingestion_source, source_map["my_crawler"])
        self.assertEqual(doc_path.external_id, "ext-456")
        self.assertEqual(doc_path.ingestion_metadata, {"job_id": "job-789"})

    def test_reconstruct_without_source_map(self):
        """_reconstruct_document_paths should handle None source_name_map."""
        from opencontractserver.tasks.import_tasks_v2 import _reconstruct_document_paths

        doc = Document.objects.create(
            title="Test Doc",
            creator=self.user,
            pdf_file="test.pdf",
            pdf_file_hash="def456",
        )
        DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            path="/documents/test2.pdf",
            version_number=1,
            is_current=True,
            creator=self.user,
        )

        path_data = [
            {
                "document_ref": "def456",
                "path": "/documents/test2.pdf",
                "version_number": 1,
                "is_current": True,
                "is_deleted": False,
            }
        ]
        # Should not raise even with None source_name_map
        _reconstruct_document_paths(
            path_data, self.corpus, {"def456": doc}, [], {}, None
        )


# ------------------------------------------------------------------ #
# _import_ingestion_sources IntegrityError fallback
# ------------------------------------------------------------------ #


class TestImportIngestionSourcesIntegrityFallback(TestCase):
    """Test that _import_ingestion_sources handles the get_or_create race."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")

    def test_integrity_error_fallback_resolves_existing(self):
        """When get_or_create raises IntegrityError (race condition), the
        fallback .get() should resolve the existing record."""
        from django.db import IntegrityError

        # Pre-create the source so the fallback .get() has something to find
        existing = IngestionSource.objects.create(
            name="race_source",
            source_type=IngestionSourceCategory.API,
            creator=self.user,
        )

        sources_data = [
            {
                "name": "race_source",
                "source_type": "api",
                "config": {"url": "https://example.com"},
                "active": True,
            }
        ]

        # Mock get_or_create to simulate a race condition: it raises
        # IntegrityError as if a concurrent process created the row
        # between the SELECT and INSERT.
        with patch.object(
            type(IngestionSource.objects),
            "get_or_create",
            side_effect=IntegrityError("duplicate key value"),
        ):
            source_map = _import_ingestion_sources(sources_data, self.user)

        self.assertIn("race_source", source_map)
        self.assertEqual(source_map["race_source"].pk, existing.pk)
        self.assertEqual(source_map["race_source"].source_type, "api")

    def test_integrity_error_fallback_skips_vanished_row(self):
        """When the row vanishes between IntegrityError and the fallback
        .get() (concurrent created-then-deleted), the import should log a
        warning and skip the source rather than aborting the entire corpus
        import with a bubbled DoesNotExist."""
        from django.db import IntegrityError

        sources_data = [
            {
                "name": "vanished_source",
                "source_type": "api",
                "config": {},
                "active": True,
            }
        ]

        # Patch get_or_create to always raise IntegrityError, and do NOT
        # pre-create the row.  The fallback .get() will then raise
        # DoesNotExist, simulating the "created-then-deleted between the
        # IntegrityError and the fallback" race.  The import must not
        # bubble DoesNotExist; it must log a warning and continue.
        with patch.object(
            type(IngestionSource.objects),
            "get_or_create",
            side_effect=IntegrityError("duplicate key value"),
        ):
            source_map = _import_ingestion_sources(sources_data, self.user)

        # Vanished source is silently skipped rather than aborting the
        # whole corpus import.
        self.assertNotIn("vanished_source", source_map)
        self.assertEqual(source_map, {})


# ------------------------------------------------------------------ #
# IngestionSource model __str__
# ------------------------------------------------------------------ #


class TestIngestionSourceModel(TestCase):
    """Test IngestionSource model methods."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")

    def test_str_representation(self):
        source = IngestionSource.objects.create(
            name="test_source",
            source_type=IngestionSourceCategory.CRAWLER,
            active=True,
            creator=self.user,
        )
        result = str(source)
        self.assertIn("test_source", result)
        self.assertIn("crawler", result)
        self.assertIn("True", result)

    def test_unique_constraint_per_creator(self):
        """Same name for same creator should fail."""
        IngestionSource.objects.create(
            name="dup", creator=self.user, source_type="manual"
        )
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            IngestionSource.objects.create(
                name="dup", creator=self.user, source_type="manual"
            )

    def test_same_name_different_creators(self):
        """Same name for different creators should succeed."""
        other_user = User.objects.create_user(username="other", password="otherpass")
        IngestionSource.objects.create(
            name="shared_name", creator=self.user, source_type="manual"
        )
        source2 = IngestionSource.objects.create(
            name="shared_name", creator=other_user, source_type="manual"
        )
        self.assertIsNotNone(source2.pk)


# ------------------------------------------------------------------ #
# Update mutation: duplicate name check
# ------------------------------------------------------------------ #


class TestUpdateDuplicateNameCheck(TestCase):
    """Test the duplicate-name guard in UpdateIngestionSourceMutation."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client = Client(schema, context_value=TestContext(self.user))
        self.source_a = IngestionSource.objects.create(
            name="source_a", creator=self.user
        )
        self.source_b = IngestionSource.objects.create(
            name="source_b", creator=self.user
        )
        set_permissions_for_obj_to_user(
            self.user, self.source_a, [PermissionTypes.CRUD]
        )
        set_permissions_for_obj_to_user(
            self.user, self.source_b, [PermissionTypes.CRUD]
        )

    def test_rename_to_existing_name_rejected(self):
        """Renaming source_a to source_b should fail."""
        gid = to_global_id("IngestionSourceType", self.source_a.pk)
        result = self.client.execute(
            UPDATE_MUTATION, variables={"id": gid, "name": "source_b"}
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["updateIngestionSource"]
        self.assertFalse(data["ok"])
        self.assertIn("already exists", data["message"])

    def test_rename_to_same_name_accepted(self):
        """Renaming source_a to source_a (no change) should succeed."""
        gid = to_global_id("IngestionSourceType", self.source_a.pk)
        result = self.client.execute(
            UPDATE_MUTATION, variables={"id": gid, "name": "source_a"}
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["updateIngestionSource"]
        self.assertTrue(data["ok"])

    def test_update_wrong_type_global_id(self):
        """Passing a wrong type_name in the global ID should return not found."""
        bad_gid = to_global_id("WrongType", self.source_a.pk)
        result = self.client.execute(
            UPDATE_MUTATION, variables={"id": bad_gid, "name": "x"}
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["updateIngestionSource"]
        self.assertFalse(data["ok"])
        self.assertIn("not found", data["message"])

    def test_delete_wrong_type_global_id(self):
        """Passing a wrong type_name in delete should return not found."""
        bad_gid = to_global_id("WrongType", self.source_a.pk)
        result = self.client.execute(DELETE_MUTATION, variables={"id": bad_gid})
        self.assertIsNone(result.get("errors"))
        data = result["data"]["deleteIngestionSource"]
        self.assertFalse(data["ok"])
        self.assertIn("not found", data["message"])

    def test_update_toctou_integrity_error_handled(self):
        """Concurrent rename to a name that becomes taken should be caught
        by the IntegrityError handler rather than crashing."""
        # Direct DB rename to simulate a concurrent request taking the name
        self.source_b.name = "new_unique_name"
        self.source_b.save(update_fields=["name"])

        # Now try to rename source_a to source_b's old name - but first
        # recreate source_b with its old name to trigger IntegrityError
        IngestionSource.objects.create(
            name="target_name", creator=self.user, source_type="manual"
        )

        # Try renaming source_a to target_name
        gid = to_global_id("IngestionSourceType", self.source_a.pk)
        result = self.client.execute(
            UPDATE_MUTATION, variables={"id": gid, "name": "target_name"}
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["updateIngestionSource"]
        self.assertFalse(data["ok"])
        self.assertIn("already exists", data["message"])


# ------------------------------------------------------------------ #
# Upload document with wrong global ID type
# ------------------------------------------------------------------ #


class TestUploadDocumentSourceTypeValidation(TestCase):
    """Test that UploadDocument validates the global ID type for ingestion_source_id."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client = Client(schema, context_value=TestContext(self.user))

    def test_upload_with_wrong_type_global_id(self):
        """Passing a CorpusType global ID as ingestion source should fail."""
        wrong_gid = to_global_id("CorpusType", 123)
        pdf_content = b"%PDF-1.5\n%\xe2\xe3\xcf\xd3\n"
        pdf_base64 = base_64_encode_bytes(pdf_content)

        result = self.client.execute(
            UPLOAD_DOCUMENT_MUTATION,
            variables={
                "file": pdf_base64,
                "filename": "test.pdf",
                "title": "Test PDF",
                "description": "desc",
                "customMeta": {},
                "makePublic": False,
                "ingestionSourceId": wrong_gid,
            },
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["uploadDocument"]
        self.assertFalse(data["ok"])
        self.assertIn("not found", data["message"])

    def test_upload_with_invalid_global_id(self):
        """Passing a non-base64 string as ingestion source ID should fail."""
        pdf_content = b"%PDF-1.5\n%\xe2\xe3\xcf\xd3\n"
        pdf_base64 = base_64_encode_bytes(pdf_content)

        result = self.client.execute(
            UPLOAD_DOCUMENT_MUTATION,
            variables={
                "file": pdf_base64,
                "filename": "test.pdf",
                "title": "Test PDF",
                "description": "desc",
                "customMeta": {},
                "makePublic": False,
                "ingestionSourceId": "not-a-valid-global-id",
            },
        )
        self.assertIsNone(result.get("errors"))
        data = result["data"]["uploadDocument"]
        self.assertFalse(data["ok"])
        self.assertIn("not found", data["message"])


# ------------------------------------------------------------------ #
# Upload document with lineage kwargs
# ------------------------------------------------------------------ #


class TestUploadDocumentLineageKwargs(TestCase):
    """Test that UploadDocument passes lineage kwargs to import_content."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client = Client(schema, context_value=TestContext(self.user))
        self.source = IngestionSource.objects.create(
            name="api_source",
            source_type=IngestionSourceCategory.API,
            creator=self.user,
        )
        set_permissions_for_obj_to_user(self.user, self.source, [PermissionTypes.CRUD])

    def _upload_mutation_with_meta(self):
        return """
            mutation UploadDocument(
                $file: String!,
                $filename: String!,
                $title: String!,
                $description: String!,
                $customMeta: GenericScalar!,
                $makePublic: Boolean!,
                $ingestionSourceId: ID,
                $externalId: String,
                $ingestionMetadata: GenericScalar
            ) {
                uploadDocument(
                    base64FileString: $file,
                    filename: $filename,
                    title: $title,
                    description: $description,
                    customMeta: $customMeta,
                    makePublic: $makePublic,
                    ingestionSourceId: $ingestionSourceId,
                    externalId: $externalId,
                    ingestionMetadata: $ingestionMetadata
                ) {
                    ok
                    message
                    document { id title }
                }
            }
        """

    def test_upload_with_external_id_and_metadata(self):
        """UploadDocument should pass external_id and ingestion_metadata through."""
        pdf_content = b"%PDF-1.5\n%\xe2\xe3\xcf\xd3\n"
        pdf_base64 = base_64_encode_bytes(pdf_content)
        source_gid = to_global_id("IngestionSourceType", self.source.pk)

        mock_doc = Document(id=999999, title="Test PDF", description="desc")
        mock_path = DocumentPath(id=999999, path="/documents/test.pdf")

        with patch(
            "opencontractserver.corpuses.models.Corpus.import_content"
        ) as mock_import, patch(
            "opencontractserver.document_imports.services.set_permissions_for_obj_to_user"
        ):
            mock_import.return_value = (mock_doc, "created", mock_path)
            result = self.client.execute(
                self._upload_mutation_with_meta(),
                variables={
                    "file": pdf_base64,
                    "filename": "test.pdf",
                    "title": "Test PDF",
                    "description": "desc",
                    "customMeta": {},
                    "makePublic": False,
                    "ingestionSourceId": source_gid,
                    "externalId": "ext-abc",
                    "ingestionMetadata": {"crawl_url": "https://example.com"},
                },
            )

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["uploadDocument"]["ok"])

        # Verify import_content was called with lineage kwargs
        call_kwargs = mock_import.call_args
        self.assertEqual(call_kwargs.kwargs.get("ingestion_source"), self.source)
        self.assertEqual(call_kwargs.kwargs.get("external_id"), "ext-abc")
        self.assertEqual(
            call_kwargs.kwargs.get("ingestion_metadata"),
            {"crawl_url": "https://example.com"},
        )

    def test_upload_without_lineage_kwargs(self):
        """UploadDocument without lineage args should not pass them to import_content."""
        pdf_content = b"%PDF-1.5\n%\xe2\xe3\xcf\xd3\n"
        pdf_base64 = base_64_encode_bytes(pdf_content)

        mock_doc = Document(id=999999, title="Test PDF", description="desc")
        mock_path = DocumentPath(id=999999, path="/documents/test.pdf")

        with patch(
            "opencontractserver.corpuses.models.Corpus.import_content"
        ) as mock_import, patch(
            "opencontractserver.document_imports.services.set_permissions_for_obj_to_user"
        ):
            mock_import.return_value = (mock_doc, "created", mock_path)
            result = self.client.execute(
                self._upload_mutation_with_meta(),
                variables={
                    "file": pdf_base64,
                    "filename": "test.pdf",
                    "title": "Test PDF",
                    "description": "desc",
                    "customMeta": {},
                    "makePublic": False,
                },
            )

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["uploadDocument"]["ok"])

        # Verify lineage kwargs are NOT passed
        call_kwargs = mock_import.call_args
        self.assertNotIn("ingestion_source", call_kwargs.kwargs)
        self.assertNotIn("external_id", call_kwargs.kwargs)
        self.assertNotIn("ingestion_metadata", call_kwargs.kwargs)


# ------------------------------------------------------------------ #
# Anonymous user queries return empty
# ------------------------------------------------------------------ #


class TestAnonymousIngestionSourceAccess(TestCase):
    """Test that anonymous users cannot access ingestion sources."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        IngestionSource.objects.create(
            name="test_source",
            source_type=IngestionSourceCategory.API,
            creator=self.user,
        )

    def test_anonymous_list_returns_errors(self):
        """Anonymous user should get auth errors for list query."""
        anon_client = Client(schema, context_value=AnonymousContext())
        result = anon_client.execute(LIST_SOURCES_QUERY)
        # @login_required should return errors
        self.assertIsNotNone(result.get("errors"))

    def test_anonymous_single_source_returns_errors(self):
        """Anonymous user should get auth errors for single source query."""
        anon_client = Client(schema, context_value=AnonymousContext())
        source = IngestionSource.objects.first()
        gid = to_global_id("IngestionSourceType", source.pk)
        result = anon_client.execute(SINGLE_SOURCE_QUERY, variables={"id": gid})
        self.assertIsNotNone(result.get("errors"))


# ------------------------------------------------------------------ #
# Superuser access to ingestion sources
# ------------------------------------------------------------------ #


class TestSuperuserIngestionSourceAccess(TestCase):
    """Test that superusers can see all ingestion sources."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="is_admin_superuser", password="adminpass"
        )
        self.regular_user = User.objects.create_user(
            username="regular", password="regularpass"
        )
        self.source = IngestionSource.objects.create(
            name="regular_source",
            source_type=IngestionSourceCategory.API,
            creator=self.regular_user,
        )
        set_permissions_for_obj_to_user(
            self.regular_user, self.source, [PermissionTypes.CRUD]
        )

    def test_superuser_list_sees_all_sources(self):
        """Superuser should see sources from all users."""
        admin_client = Client(schema, context_value=TestContext(self.superuser))
        result = admin_client.execute(LIST_SOURCES_QUERY)
        self.assertIsNone(result.get("errors"))
        sources = result["data"]["ingestionSources"]
        names = [s["name"] for s in sources]
        self.assertIn("regular_source", names)

    def test_superuser_single_source(self):
        """Superuser should be able to query any source by ID."""
        admin_client = Client(schema, context_value=TestContext(self.superuser))
        gid = to_global_id("IngestionSourceType", self.source.pk)
        result = admin_client.execute(SINGLE_SOURCE_QUERY, variables={"id": gid})
        self.assertIsNone(result.get("errors"))
        data = result["data"]["ingestionSource"]
        self.assertIsNotNone(data)
        self.assertEqual(data["name"], "regular_source")


# ------------------------------------------------------------------ #
# Versioning lineage preservation tests
# ------------------------------------------------------------------ #


class TestVersioningLineagePreservation(TestCase):
    """Test that move/delete/restore operations preserve lineage fields."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)
        self.source = IngestionSource.objects.create(
            name="lineage_source",
            source_type=IngestionSourceCategory.CRAWLER,
            creator=self.user,
        )

    def _create_doc_with_lineage(self):
        """Create a document with lineage fields on its path."""
        from opencontractserver.documents.versioning import import_document

        content = b"%PDF-1.5 test content"
        doc, status, path = import_document(
            corpus=self.corpus,
            path="/documents/lineage_test.pdf",
            content=content,
            user=self.user,
            ingestion_source=self.source,
            external_id="ext-lineage-001",
            ingestion_metadata={"crawl_url": "https://example.com/doc1"},
        )
        return doc, path

    def test_import_document_stores_lineage_on_path(self):
        """import_document with lineage kwargs should store them on the path."""
        doc, path = self._create_doc_with_lineage()
        self.assertEqual(path.ingestion_source, self.source)
        self.assertEqual(path.external_id, "ext-lineage-001")
        self.assertEqual(
            path.ingestion_metadata, {"crawl_url": "https://example.com/doc1"}
        )

    def test_move_preserves_lineage(self):
        """move_document should copy lineage fields to the new path record."""
        from opencontractserver.documents.versioning import move_document

        _, original_path = self._create_doc_with_lineage()
        new_path = move_document(
            corpus=self.corpus,
            old_path="/documents/lineage_test.pdf",
            new_path="/documents/moved_lineage.pdf",
            user=self.user,
        )
        self.assertEqual(new_path.ingestion_source, self.source)
        self.assertEqual(new_path.external_id, "ext-lineage-001")
        self.assertEqual(
            new_path.ingestion_metadata, {"crawl_url": "https://example.com/doc1"}
        )

    def test_delete_preserves_lineage(self):
        """delete_document should copy lineage fields to the deleted path record."""
        from opencontractserver.documents.versioning import delete_document

        self._create_doc_with_lineage()
        deleted_path = delete_document(
            corpus=self.corpus,
            path="/documents/lineage_test.pdf",
            user=self.user,
        )
        self.assertTrue(deleted_path.is_deleted)
        self.assertEqual(deleted_path.ingestion_source, self.source)
        self.assertEqual(deleted_path.external_id, "ext-lineage-001")
        self.assertEqual(
            deleted_path.ingestion_metadata, {"crawl_url": "https://example.com/doc1"}
        )

    def test_restore_preserves_lineage(self):
        """restore_document should copy lineage fields to the restored path record."""
        from opencontractserver.documents.versioning import (
            delete_document,
            restore_document,
        )

        self._create_doc_with_lineage()
        delete_document(
            corpus=self.corpus,
            path="/documents/lineage_test.pdf",
            user=self.user,
        )
        restored_path = restore_document(
            corpus=self.corpus,
            path="/documents/lineage_test.pdf",
            user=self.user,
        )
        self.assertFalse(restored_path.is_deleted)
        self.assertEqual(restored_path.ingestion_source, self.source)
        self.assertEqual(restored_path.external_id, "ext-lineage-001")
        self.assertEqual(
            restored_path.ingestion_metadata, {"crawl_url": "https://example.com/doc1"}
        )

    def test_import_document_without_lineage(self):
        """import_document without lineage kwargs should leave fields at defaults."""
        from opencontractserver.documents.versioning import import_document

        content = b"%PDF-1.5 no lineage content"
        doc, status, path = import_document(
            corpus=self.corpus,
            path="/documents/no_lineage.pdf",
            content=content,
            user=self.user,
        )
        self.assertIsNone(path.ingestion_source)
        self.assertEqual(path.external_id, "")
        self.assertFalse(path.ingestion_metadata)


# ------------------------------------------------------------------ #
# Corpus.import_content lineage kwargs passthrough
# ------------------------------------------------------------------ #


class TestCorpusImportContentLineage(TestCase):
    """Test that Corpus.import_content passes lineage kwargs to DocumentPath."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.ALL])
        self.source = IngestionSource.objects.create(
            name="corpus_test_source",
            source_type=IngestionSourceCategory.API,
            creator=self.user,
        )

    def test_import_content_with_lineage_kwargs(self):
        """Corpus.import_content should pass lineage kwargs through to DocumentPath."""
        pdf_content = b"%PDF-1.5 test"
        doc, status, path = self.corpus.import_content(
            filename="lineage_doc.pdf",
            content=pdf_content,
            user=self.user,
            ingestion_source=self.source,
            external_id="ext-corpus-001",
            ingestion_metadata={"import_job": "batch-42"},
        )
        self.assertIsNotNone(path)
        path.refresh_from_db()
        self.assertEqual(path.ingestion_source, self.source)
        self.assertEqual(path.external_id, "ext-corpus-001")
        self.assertEqual(path.ingestion_metadata, {"import_job": "batch-42"})


# ------------------------------------------------------------------ #
# Corpus.add_document lineage kwargs passthrough
# ------------------------------------------------------------------ #


class TestCorpusAddDocumentLineage(TestCase):
    """Test that Corpus.add_document passes lineage kwargs to DocumentPath."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.ALL])
        self.source = IngestionSource.objects.create(
            name="add_doc_source",
            source_type=IngestionSourceCategory.API,
            creator=self.user,
        )

    def test_add_document_with_lineage_kwargs(self):
        """Corpus.add_document should extract lineage kwargs and pass to DocumentPath."""
        original_doc = Document.objects.create(
            title="Original Doc",
            creator=self.user,
            pdf_file="original.pdf",
        )
        corpus_doc, status, path = self.corpus.add_document(
            document=original_doc,
            user=self.user,
            ingestion_source=self.source,
            external_id="ext-add-001",
            ingestion_metadata={"batch": "add-42"},
        )
        self.assertIsNotNone(path)
        path.refresh_from_db()
        self.assertEqual(path.ingestion_source, self.source)
        self.assertEqual(path.external_id, "ext-add-001")
        self.assertEqual(path.ingestion_metadata, {"batch": "add-42"})


# ------------------------------------------------------------------ #
# import_document update path with lineage kwargs
# ------------------------------------------------------------------ #


class TestImportDocumentUpdateLineage(TestCase):
    """Test import_document update path (existing path) with lineage kwargs."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)
        self.source = IngestionSource.objects.create(
            name="update_source",
            source_type=IngestionSourceCategory.CRAWLER,
            creator=self.user,
        )

    def test_update_existing_path_with_lineage(self):
        """Updating an existing path should store lineage kwargs on the new version."""
        from opencontractserver.documents.versioning import import_document

        # Create initial document at a path
        content_v1 = b"%PDF-1.5 version 1"
        doc_v1, status_v1, path_v1 = import_document(
            corpus=self.corpus,
            path="/documents/update_lineage.pdf",
            content=content_v1,
            user=self.user,
        )
        self.assertEqual(status_v1, "created")
        self.assertIsNone(path_v1.ingestion_source)

        # Update same path with new content and lineage kwargs
        content_v2 = b"%PDF-1.5 version 2 different"
        doc_v2, status_v2, path_v2 = import_document(
            corpus=self.corpus,
            path="/documents/update_lineage.pdf",
            content=content_v2,
            user=self.user,
            ingestion_source=self.source,
            external_id="ext-update-001",
            ingestion_metadata={"crawl_run": "run-99"},
        )
        self.assertEqual(status_v2, "updated")
        self.assertEqual(path_v2.ingestion_source, self.source)
        self.assertEqual(path_v2.external_id, "ext-update-001")
        self.assertEqual(path_v2.ingestion_metadata, {"crawl_run": "run-99"})


# ------------------------------------------------------------------ #
# Export document_ref fallback paths
# ------------------------------------------------------------------ #


class TestExportDocumentRefFallbacks(TestCase):
    """Test package_document_paths document_ref fallback logic."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)

    def test_document_ref_uses_hash_when_available(self):
        """document_ref should use pdf_file_hash when available."""
        from opencontractserver.utils.export_v2 import package_document_paths

        doc = Document.objects.create(
            title="Hash Doc",
            creator=self.user,
            pdf_file="hash_doc.pdf",
            pdf_file_hash="sha256_abc123",
        )
        DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            path="/documents/hash_doc.pdf",
            version_number=1,
            creator=self.user,
        )
        exported = package_document_paths(self.corpus)
        self.assertEqual(len(exported), 1)
        self.assertEqual(exported[0]["document_ref"], "sha256_abc123")

    def test_document_ref_falls_back_to_filename(self):
        """document_ref should fall back to filename when hash is empty."""
        from opencontractserver.utils.export_v2 import package_document_paths

        doc = Document.objects.create(
            title="No Hash Doc",
            creator=self.user,
            pdf_file="subdir/fallback_doc.pdf",
            pdf_file_hash="",
        )
        DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            path="/documents/fallback_doc.pdf",
            version_number=1,
            creator=self.user,
        )
        exported = package_document_paths(self.corpus)
        self.assertEqual(len(exported), 1)
        self.assertEqual(exported[0]["document_ref"], "fallback_doc.pdf")

    def test_document_ref_falls_back_to_id(self):
        """document_ref should fall back to the synthesized placeholder filename
        when no hash and no file are present. This mirrors
        ``build_document_export``'s synthesized filename so the import-side
        doc-ref map (keyed by hash OR zip filename) finds the entry."""
        from opencontractserver.utils.export_v2 import package_document_paths

        doc = Document.objects.create(
            title="No File Doc",
            creator=self.user,
            pdf_file_hash="",
        )
        DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            path="/documents/no_file_doc.pdf",
            version_number=1,
            creator=self.user,
        )
        exported = package_document_paths(self.corpus)
        self.assertEqual(len(exported), 1)
        self.assertEqual(exported[0]["document_ref"], f"document_{doc.id}.placeholder")

    def test_export_parent_version_number(self):
        """Exported paths should include parent_version_number when parent exists."""
        from opencontractserver.utils.export_v2 import package_document_paths

        doc = Document.objects.create(
            title="Versioned Doc",
            creator=self.user,
            pdf_file="versioned.pdf",
            pdf_file_hash="hash_versioned",
        )
        root_path = DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            path="/documents/versioned.pdf",
            version_number=1,
            is_current=False,
            creator=self.user,
        )
        DocumentPath.objects.create(
            document=doc,
            corpus=self.corpus,
            path="/documents/versioned.pdf",
            version_number=2,
            parent=root_path,
            is_current=True,
            creator=self.user,
        )
        exported = package_document_paths(self.corpus)
        self.assertEqual(len(exported), 2)
        # Find the child entry
        child_entry = next(e for e in exported if e["version_number"] == 2)
        self.assertEqual(child_entry["parent_version_number"], 1)
