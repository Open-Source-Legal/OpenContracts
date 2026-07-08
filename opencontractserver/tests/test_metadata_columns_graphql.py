from django.contrib.auth import get_user_model
from django.test import TestCase
from graphql_relay import to_global_id

from config.graphql.schema import schema
from config.graphql.testing import Client
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.extracts.models import Column, Datacell, Fieldset
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class TestContext:
    def __init__(self, user):
        self.user = user


class MetadataColumnsGraphQLTestCase(TestCase):
    """Test GraphQL mutations and queries for metadata columns."""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.graphene_client = Client(schema, context_value=TestContext(self.user))

        # Create test objects
        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)

        self.document = Document.objects.create(
            title="Test Document", creator=self.user
        )
        self.corpus.add_document(document=self.document, user=self.user)

        # Set permissions
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.CRUD])
        set_permissions_for_obj_to_user(
            self.user, self.document, [PermissionTypes.CRUD]
        )

    def test_create_metadata_column_mutation(self):
        """Test creating a metadata column via GraphQL."""
        mutation = """
            mutation CreateMetadataColumn($corpusId: ID!, $name: String!, $dataType: String!, $validationConfig: GenericScalar) {
                createMetadataColumn(
                    corpusId: $corpusId,
                    name: $name,
                    dataType: $dataType,
                    validationConfig: $validationConfig
                ) {
                    ok
                    message
                    obj {
                        id
                        name
                        dataType
                        validationConfig
                        isManualEntry
                    }
                }
            }
        """  # noqa: E501

        variables = {
            "corpusId": to_global_id("CorpusType", self.corpus.id),
            "name": "Document Status",
            "dataType": "CHOICE",
            "validationConfig": {
                "required": True,
                "choices": ["Draft", "Review", "Final"],
            },
        }

        result = self.graphene_client.execute(mutation, variables=variables)
        self.assertIsNone(result.get("errors"))

        data = result["data"]["createMetadataColumn"]
        self.assertTrue(data["ok"])
        self.assertEqual(data["obj"]["name"], "Document Status")
        self.assertEqual(data["obj"]["dataType"], "CHOICE")
        self.assertTrue(data["obj"]["isManualEntry"])
        self.assertEqual(len(data["obj"]["validationConfig"]["choices"]), 3)

        # Verify in database
        column = Column.objects.get(name="Document Status")
        self.assertEqual(column.data_type, "CHOICE")
        self.assertTrue(column.is_manual_entry)

        # Verify fieldset was created
        self.assertTrue(hasattr(self.corpus, "metadata_schema"))
        self.assertIsNotNone(self.corpus.metadata_schema)

    def test_create_metadata_column_without_permission(self):
        """Test that creating metadata requires corpus update permission."""
        other_user = User.objects.create_user(
            username="otheruser", password="otherpass"
        )
        other_client = Client(schema, context_value=TestContext(other_user))

        mutation = """
            mutation CreateMetadataColumn($corpusId: ID!, $name: String!, $dataType: String!) {
                createMetadataColumn(
                    corpusId: $corpusId,
                    name: $name,
                    dataType: $dataType
                ) {
                    ok
                    message
                }
            }
        """

        variables = {
            "corpusId": to_global_id("CorpusType", self.corpus.id),
            "name": "Unauthorized Field",
            "dataType": "STRING",
        }

        result = other_client.execute(mutation, variables=variables)
        self.assertIsNone(result.get("errors"))

        data = result["data"]["createMetadataColumn"]
        self.assertFalse(data["ok"])
        # IDOR-safe response: unified "not found or no permission" message blocks
        # enumeration of corpus IDs by users who lack UPDATE permission.
        self.assertIn(
            "Corpus not found or you do not have permission",
            data["message"],
        )

    def test_update_metadata_column_mutation(self):
        """Test updating a metadata column."""
        # Create a column first
        fieldset = Fieldset.objects.create(
            name="Test Fieldset",
            description="Test",
            corpus=self.corpus,
            creator=self.user,
        )
        column = Column.objects.create(
            fieldset=fieldset,
            name="Original Name",
            data_type="STRING",
            is_manual_entry=True,
            output_type="string",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(self.user, column, [PermissionTypes.CRUD])

        mutation = """
            mutation UpdateMetadataColumn($columnId: ID!, $name: String, $helpText: String) {
                updateMetadataColumn(
                    columnId: $columnId,
                    name: $name,
                    helpText: $helpText
                ) {
                    ok
                    message
                    obj {
                        id
                        name
                        helpText
                    }
                }
            }
        """

        variables = {
            "columnId": to_global_id("ColumnType", column.id),
            "name": "Updated Name",
            "helpText": "This field contains the author name",
        }

        result = self.graphene_client.execute(mutation, variables=variables)
        self.assertIsNone(result.get("errors"))

        data = result["data"]["updateMetadataColumn"]
        self.assertTrue(data["ok"])
        self.assertEqual(data["obj"]["name"], "Updated Name")
        self.assertEqual(data["obj"]["helpText"], "This field contains the author name")

    def test_set_metadata_value_mutation(self):
        """Test setting a metadata value."""
        # Create metadata column
        fieldset = Fieldset.objects.create(
            name="Test Fieldset",
            description="Test",
            corpus=self.corpus,
            creator=self.user,
        )
        column = Column.objects.create(
            fieldset=fieldset,
            name="Author",
            data_type="STRING",
            validation_config={"required": True},
            is_manual_entry=True,
            output_type="string",
            creator=self.user,
        )

        mutation = """
            mutation SetMetadataValue($documentId: ID!, $corpusId: ID!, $columnId: ID!, $value: GenericScalar!) {
                setMetadataValue(
                    documentId: $documentId,
                    corpusId: $corpusId,
                    columnId: $columnId,
                    value: $value
                ) {
                    ok
                    message
                    obj {
                        id
                        data
                        column {
                            name
                        }
                    }
                }
            }
        """

        variables = {
            "documentId": to_global_id("DocumentType", self.document.id),
            "corpusId": to_global_id("CorpusType", self.corpus.id),
            "columnId": to_global_id("ColumnType", column.id),
            "value": "John Doe",
        }

        result = self.graphene_client.execute(mutation, variables=variables)
        self.assertIsNone(result.get("errors"))

        data = result["data"]["setMetadataValue"]
        self.assertTrue(data["ok"])
        self.assertEqual(data["obj"]["data"]["value"], "John Doe")
        self.assertEqual(data["obj"]["column"]["name"], "Author")

        # Verify in database
        datacell = Datacell.objects.get(document=self.document, column=column)
        self.assertEqual(datacell.data["value"], "John Doe")

    def test_update_existing_metadata_value(self):
        """Test updating an existing metadata value."""
        # Create column and datacell
        fieldset = Fieldset.objects.create(
            name="Test Fieldset",
            description="Test",
            corpus=self.corpus,
            creator=self.user,
        )
        column = Column.objects.create(
            fieldset=fieldset,
            name="Version",
            data_type="STRING",
            is_manual_entry=True,
            output_type="string",
            creator=self.user,
        )

        datacell = Datacell.objects.create(
            document=self.document,
            column=column,
            data={"value": "1.0"},
            data_definition="string",
            creator=self.user,
        )

        mutation = """
            mutation SetMetadataValue($documentId: ID!, $corpusId: ID!, $columnId: ID!, $value: GenericScalar!) {
                setMetadataValue(
                    documentId: $documentId,
                    corpusId: $corpusId,
                    columnId: $columnId,
                    value: $value
                ) {
                    ok
                    message
                }
            }
        """

        variables = {
            "documentId": to_global_id("DocumentType", self.document.id),
            "corpusId": to_global_id("CorpusType", self.corpus.id),
            "columnId": to_global_id("ColumnType", column.id),
            "value": "2.0",
        }

        result = self.graphene_client.execute(mutation, variables=variables)
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["setMetadataValue"]["ok"])

        # Verify updated value
        datacell.refresh_from_db()
        self.assertEqual(datacell.data["value"], "2.0")

    def test_delete_metadata_value_mutation(self):
        """Test deleting a metadata value."""
        # Create column and datacell
        fieldset = Fieldset.objects.create(
            name="Test Fieldset",
            description="Test",
            corpus=self.corpus,
            creator=self.user,
        )
        column = Column.objects.create(
            fieldset=fieldset,
            name="To Delete",
            data_type="STRING",
            is_manual_entry=True,
            output_type="string",
            creator=self.user,
        )
        datacell = Datacell.objects.create(
            document=self.document,
            column=column,
            data={"value": "test"},
            data_definition="string",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(self.user, datacell, [PermissionTypes.CRUD])

        mutation = """
            mutation DeleteMetadataValue($documentId: ID!, $corpusId: ID!, $columnId: ID!) {
                deleteMetadataValue(
                    documentId: $documentId,
                    corpusId: $corpusId,
                    columnId: $columnId
                ) {
                    ok
                    message
                }
            }
        """

        variables = {
            "documentId": to_global_id("DocumentType", self.document.id),
            "corpusId": to_global_id("CorpusType", self.corpus.id),
            "columnId": to_global_id("ColumnType", column.id),
        }

        result = self.graphene_client.execute(mutation, variables=variables)
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["deleteMetadataValue"]["ok"])

        # Verify deletion
        self.assertFalse(Datacell.objects.filter(id=datacell.id).exists())

    def test_corpus_metadata_columns_query(self):
        """Test querying metadata columns for a corpus."""
        # Create metadata fieldset and columns
        fieldset = Fieldset.objects.create(
            name="Test Metadata",
            description="Test",
            corpus=self.corpus,
            creator=self.user,
        )

        columns = []
        for i in range(3):
            column = Column.objects.create(
                fieldset=fieldset,
                name=f"Field {i}",
                data_type="STRING",
                is_manual_entry=True,
                output_type="string",
                display_order=i,
                creator=self.user,
            )
            columns.append(column)

        query = """
            query GetCorpusMetadataColumns($corpusId: ID!) {
                corpusMetadataColumns(corpusId: $corpusId) {
                    id
                    name
                    dataType
                    isManualEntry
                    displayOrder
                }
            }
        """

        variables = {"corpusId": to_global_id("CorpusType", self.corpus.id)}

        result = self.graphene_client.execute(query, variables=variables)
        self.assertIsNone(result.get("errors"))

        data = result["data"]["corpusMetadataColumns"]
        self.assertEqual(len(data), 3)
        for i, item in enumerate(data):
            self.assertEqual(item["name"], f"Field {i}")
            self.assertEqual(item["dataType"], "STRING")
            self.assertTrue(item["isManualEntry"])
            self.assertEqual(item["displayOrder"], i)

    def test_document_metadata_datacells_query(self):
        """Test querying metadata datacells for a document."""
        # Create fieldset and columns
        fieldset = Fieldset.objects.create(
            name="Test Metadata",
            description="Test",
            corpus=self.corpus,
            creator=self.user,
        )

        column1 = Column.objects.create(
            fieldset=fieldset,
            name="Author",
            data_type="STRING",
            is_manual_entry=True,
            output_type="string",
            creator=self.user,
        )
        column2 = Column.objects.create(
            fieldset=fieldset,
            name="Reviewed",
            data_type="BOOLEAN",
            is_manual_entry=True,
            output_type="boolean",
            creator=self.user,
        )

        Datacell.objects.create(
            document=self.document,
            column=column1,
            data={"value": "Jane Doe"},
            data_definition="string",
            creator=self.user,
        )
        Datacell.objects.create(
            document=self.document,
            column=column2,
            data={"value": True},
            data_definition="boolean",
            creator=self.user,
        )

        query = """
            query GetDocumentMetadata($documentId: ID!, $corpusId: ID!) {
                documentMetadataDatacells(documentId: $documentId, corpusId: $corpusId) {
                    id
                    data
                    column {
                        name
                        dataType
                    }
                }
            }
        """

        variables = {
            "documentId": to_global_id("DocumentType", self.document.id),
            "corpusId": to_global_id("CorpusType", self.corpus.id),
        }

        result = self.graphene_client.execute(query, variables=variables)
        self.assertIsNone(result.get("errors"))

        data = result["data"]["documentMetadataDatacells"]
        self.assertEqual(len(data), 2)

        # Check values
        values_by_name = {
            item["column"]["name"]: item["data"]["value"] for item in data
        }
        self.assertEqual(values_by_name["Author"], "Jane Doe")
        self.assertTrue(values_by_name["Reviewed"])

    def test_metadata_completion_status_v2_query(self):
        """Test querying metadata completion status with new system."""
        # Create fieldset and columns (some required, some not)
        fieldset = Fieldset.objects.create(
            name="Test Metadata",
            description="Test",
            corpus=self.corpus,
            creator=self.user,
        )

        columns = []
        for i in range(5):
            column = Column.objects.create(
                fieldset=fieldset,
                name=f"Field {i}",
                data_type="STRING",
                validation_config={"required": i < 2},  # First 2 are required
                is_manual_entry=True,
                output_type="string",
                creator=self.user,
            )
            columns.append(column)

        # Create datacells for only some fields
        for i in [0, 2, 3]:  # Missing required field 1
            Datacell.objects.create(
                document=self.document,
                column=columns[i],
                data={"value": f"Value {i}"},
                data_definition="string",
                creator=self.user,
            )

        query = """
            query GetMetadataCompletion($documentId: ID!, $corpusId: ID!) {
                metadataCompletionStatusV2(documentId: $documentId, corpusId: $corpusId) {
                    totalFields
                    filledFields
                    missingFields
                    percentage
                    missingRequired
                }
            }
        """

        variables = {
            "documentId": to_global_id("DocumentType", self.document.id),
            "corpusId": to_global_id("CorpusType", self.corpus.id),
        }

        result = self.graphene_client.execute(query, variables=variables)
        self.assertIsNone(result.get("errors"))

        data = result["data"]["metadataCompletionStatusV2"]
        self.assertEqual(data["totalFields"], 5)
        self.assertEqual(data["filledFields"], 3)
        self.assertEqual(data["missingFields"], 2)
        self.assertEqual(data["percentage"], 60.0)
        self.assertEqual(data["missingRequired"], ["Field 1"])


class DeleteMetadataColumnTestCase(TestCase):
    """``deleteMetadataColumn`` — schema-validated counterpart of the
    frontend's DELETE_METADATA_COLUMN document (which previously called a
    mutation that did not exist; the un-validated endpoint silently ignored
    it and the delete never happened)."""

    def setUp(self):
        self.user = User.objects.create_user(username="del-owner", password="x")
        self.stranger = User.objects.create_user(username="del-stranger", password="x")
        self.column_creator = User.objects.create_user(
            username="del-column-creator", password="x"
        )
        self.client_owner = Client(schema, context_value=TestContext(self.user))
        self.client_stranger = Client(schema, context_value=TestContext(self.stranger))
        self.client_column_creator = Client(
            schema, context_value=TestContext(self.column_creator)
        )
        self.corpus = Corpus.objects.create(title="Del Corpus", creator=self.user)
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.CRUD])
        self.fieldset = Fieldset.objects.create(
            name="md", description="md", corpus=self.corpus, creator=self.user
        )
        self.column = Column.objects.create(
            fieldset=self.fieldset,
            name="Reviewed By",
            output_type="str",
            is_manual_entry=True,
            creator=self.user,
        )
        set_permissions_for_obj_to_user(self.user, self.column, [PermissionTypes.CRUD])

    MUTATION = """
        mutation DeleteMetadataColumn($columnId: ID!) {
            deleteMetadataColumn(columnId: $columnId) { ok message }
        }
    """

    def test_creator_can_delete(self):
        result = self.client_owner.execute(
            self.MUTATION,
            variables={"columnId": to_global_id("ColumnType", self.column.pk)},
        )
        payload = result["data"]["deleteMetadataColumn"]
        self.assertTrue(payload["ok"], payload["message"])
        self.assertFalse(Column.objects.filter(pk=self.column.pk).exists())

    def test_corpus_delete_without_column_delete_can_delete(self):
        """Corpus DELETE alone authorizes the delete — column-level DELETE is
        NOT required. Discriminates the corpus-scoped gate from the old
        column-level one: a revert to ``require_permission(column, DELETE)``
        would fail this test.

        The mutation READ-gates the column lookup through the service layer
        (``BaseService.get_or_none``), so the user must be able to *read* the
        column for the lookup to resolve. We therefore grant only column READ
        (never column DELETE) plus corpus DELETE — proving the destructive
        authorization comes from the corpus, not the column.
        """
        corpus_admin = User.objects.create_user(
            username="del-corpus-only", password="x"
        )
        set_permissions_for_obj_to_user(
            corpus_admin, self.corpus, [PermissionTypes.DELETE]
        )

        column = Column.objects.create(
            fieldset=self.fieldset,
            name="Corpus Only Col",
            output_type="str",
            is_manual_entry=True,
            creator=self.user,
        )
        # READ so the lookup resolves; deliberately NOT DELETE.
        set_permissions_for_obj_to_user(corpus_admin, column, [PermissionTypes.READ])

        client = Client(schema, context_value=TestContext(corpus_admin))
        result = client.execute(
            self.MUTATION,
            variables={"columnId": to_global_id("ColumnType", column.pk)},
        )
        payload = result["data"]["deleteMetadataColumn"]
        self.assertTrue(payload["ok"], payload["message"])
        self.assertFalse(Column.objects.filter(pk=column.pk).exists())

    def test_column_creator_without_corpus_delete_cannot_delete(self):
        vulnerable_column = Column.objects.create(
            fieldset=self.fieldset,
            name="Creator Owned",
            output_type="str",
            is_manual_entry=True,
            creator=self.column_creator,
        )
        set_permissions_for_obj_to_user(
            self.column_creator, vulnerable_column, [PermissionTypes.CRUD]
        )

        result = self.client_column_creator.execute(
            self.MUTATION,
            variables={"columnId": to_global_id("ColumnType", vulnerable_column.pk)},
        )

        payload = result["data"]["deleteMetadataColumn"]
        self.assertFalse(payload["ok"])
        self.assertIn("not found", payload["message"].lower())
        self.assertTrue(Column.objects.filter(pk=vulnerable_column.pk).exists())

    def test_stranger_gets_unified_not_found(self):
        result = self.client_stranger.execute(
            self.MUTATION,
            variables={"columnId": to_global_id("ColumnType", self.column.pk)},
        )
        payload = result["data"]["deleteMetadataColumn"]
        self.assertFalse(payload["ok"])
        self.assertIn("not found", payload["message"].lower())
        self.assertTrue(Column.objects.filter(pk=self.column.pk).exists())

    def test_non_manual_column_refused(self):
        extract_col = Column.objects.create(
            fieldset=self.fieldset,
            name="LLM col",
            query="q",
            output_type="str",
            is_manual_entry=False,
            creator=self.user,
        )
        set_permissions_for_obj_to_user(self.user, extract_col, [PermissionTypes.CRUD])
        result = self.client_owner.execute(
            self.MUTATION,
            variables={"columnId": to_global_id("ColumnType", extract_col.pk)},
        )
        payload = result["data"]["deleteMetadataColumn"]
        self.assertFalse(payload["ok"])
        self.assertTrue(Column.objects.filter(pk=extract_col.pk).exists())

    def test_fieldset_without_corpus_cannot_delete(self):
        """``Fieldset.corpus`` is nullable. A column whose fieldset has no
        linked corpus has no corpus to authorize a destructive write
        against, so the lookup must fall through to the unified not-found
        message rather than deleting (or crashing on a ``None`` corpus)."""
        orphan_fieldset = Fieldset.objects.create(
            name="orphan", description="orphan", corpus=None, creator=self.user
        )
        orphan_column = Column.objects.create(
            fieldset=orphan_fieldset,
            name="Orphan Col",
            output_type="str",
            is_manual_entry=True,
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, orphan_column, [PermissionTypes.CRUD]
        )

        result = self.client_owner.execute(
            self.MUTATION,
            variables={"columnId": to_global_id("ColumnType", orphan_column.pk)},
        )
        payload = result["data"]["deleteMetadataColumn"]
        self.assertFalse(payload["ok"])
        self.assertIn("not found", payload["message"].lower())
        self.assertTrue(Column.objects.filter(pk=orphan_column.pk).exists())


class UpdateMetadataColumnTestCase(TestCase):
    """``updateMetadataColumn`` must authorize against the parent corpus
    (not the child ``Column``) — the mirror image of
    ``DeleteMetadataColumnTestCase``. A user granted ``change_column``
    directly on a corpus-metadata column, without holding corpus UPDATE,
    must not be able to rename it or otherwise alter its schema."""

    def setUp(self):
        self.user = User.objects.create_user(username="upd-owner", password="x")
        self.stranger = User.objects.create_user(username="upd-stranger", password="x")
        self.column_creator = User.objects.create_user(
            username="upd-column-creator", password="x"
        )
        self.client_owner = Client(schema, context_value=TestContext(self.user))
        self.client_stranger = Client(schema, context_value=TestContext(self.stranger))
        self.client_column_creator = Client(
            schema, context_value=TestContext(self.column_creator)
        )
        self.corpus = Corpus.objects.create(title="Upd Corpus", creator=self.user)
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.CRUD])
        self.fieldset = Fieldset.objects.create(
            name="md", description="md", corpus=self.corpus, creator=self.user
        )
        self.column = Column.objects.create(
            fieldset=self.fieldset,
            name="Reviewed By",
            output_type="str",
            is_manual_entry=True,
            creator=self.user,
        )
        set_permissions_for_obj_to_user(self.user, self.column, [PermissionTypes.CRUD])

    MUTATION = """
        mutation UpdateMetadataColumn($columnId: ID!, $name: String) {
            updateMetadataColumn(columnId: $columnId, name: $name) { ok message }
        }
    """

    def test_corpus_update_without_column_update_can_update(self):
        """Corpus UPDATE alone authorizes the write — column-level UPDATE is
        NOT required. Discriminates the corpus-scoped gate from the old
        column-level one: a revert to ``require_permission(column, UPDATE)``
        would fail this test.
        """
        corpus_editor = User.objects.create_user(
            username="upd-corpus-only", password="x"
        )
        set_permissions_for_obj_to_user(
            corpus_editor, self.corpus, [PermissionTypes.UPDATE]
        )

        column = Column.objects.create(
            fieldset=self.fieldset,
            name="Corpus Only Col",
            output_type="str",
            is_manual_entry=True,
            creator=self.user,
        )
        # READ so the lookup resolves; deliberately NOT UPDATE.
        set_permissions_for_obj_to_user(corpus_editor, column, [PermissionTypes.READ])

        client = Client(schema, context_value=TestContext(corpus_editor))
        result = client.execute(
            self.MUTATION,
            variables={
                "columnId": to_global_id("ColumnType", column.pk),
                "name": "Renamed By Corpus Editor",
            },
        )
        payload = result["data"]["updateMetadataColumn"]
        self.assertTrue(payload["ok"], payload["message"])
        column.refresh_from_db()
        self.assertEqual(column.name, "Renamed By Corpus Editor")

    def test_column_creator_without_corpus_update_cannot_update(self):
        """The privilege-escalation bypass this test pins: a user with only
        direct Column-level UPDATE (no corpus UPDATE) must not be able to
        alter a corpus-scoped metadata column."""
        vulnerable_column = Column.objects.create(
            fieldset=self.fieldset,
            name="Creator Owned",
            output_type="str",
            is_manual_entry=True,
            creator=self.column_creator,
        )
        set_permissions_for_obj_to_user(
            self.column_creator, vulnerable_column, [PermissionTypes.CRUD]
        )

        result = self.client_column_creator.execute(
            self.MUTATION,
            variables={
                "columnId": to_global_id("ColumnType", vulnerable_column.pk),
                "name": "Hacked Name",
            },
        )

        payload = result["data"]["updateMetadataColumn"]
        self.assertFalse(payload["ok"])
        self.assertIn("not found", payload["message"].lower())
        vulnerable_column.refresh_from_db()
        self.assertEqual(vulnerable_column.name, "Creator Owned")

    def test_stranger_gets_unified_not_found(self):
        result = self.client_stranger.execute(
            self.MUTATION,
            variables={
                "columnId": to_global_id("ColumnType", self.column.pk),
                "name": "Hacked Name",
            },
        )
        payload = result["data"]["updateMetadataColumn"]
        self.assertFalse(payload["ok"])
        self.assertIn("not found", payload["message"].lower())
        self.column.refresh_from_db()
        self.assertEqual(self.column.name, "Reviewed By")

    def test_fieldset_without_corpus_cannot_update(self):
        """``Fieldset.corpus`` is nullable. A column whose fieldset has no
        linked corpus has no corpus to authorize a write against, so the
        lookup must fall through to the unified not-found message."""
        orphan_fieldset = Fieldset.objects.create(
            name="orphan", description="orphan", corpus=None, creator=self.user
        )
        orphan_column = Column.objects.create(
            fieldset=orphan_fieldset,
            name="Orphan Col",
            output_type="str",
            is_manual_entry=True,
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, orphan_column, [PermissionTypes.CRUD]
        )

        result = self.client_owner.execute(
            self.MUTATION,
            variables={
                "columnId": to_global_id("ColumnType", orphan_column.pk),
                "name": "Nope",
            },
        )
        payload = result["data"]["updateMetadataColumn"]
        self.assertFalse(payload["ok"])
        self.assertIn("not found", payload["message"].lower())
        orphan_column.refresh_from_db()
        self.assertEqual(orphan_column.name, "Orphan Col")
