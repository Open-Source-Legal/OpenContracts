import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.schema import schema
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
        self.user = User.objects.create_user(
            username="testuser",
            password="testpass"
        )
        self.client = Client(schema, context_value=TestContext(self.user))
        
        # Create test objects
        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            creator=self.user
        )
        
        self.document = Document.objects.create(
            title="Test Document",
            creator=self.user
        )
        self.corpus.documents.add(self.document)
        
        # Set permissions
        set_permissions_for_obj_to_user(self.user, self.corpus, [PermissionTypes.CRUD])
        set_permissions_for_obj_to_user(self.user, self.document, [PermissionTypes.CRUD])
    
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
        """
        
        variables = {
            'corpusId': to_global_id('CorpusType', self.corpus.id),
            'name': 'Document Status',
            'dataType': 'CHOICE',
            'validationConfig': {
                'required': True,
                'choices': ['Draft', 'Review', 'Final']
            }
        }
        
        result = self.client.execute(mutation, variables=variables)
        self.assertIsNone(result.get('errors'))
        
        data = result['data']['createMetadataColumn']
        self.assertTrue(data['ok'])
        self.assertEqual(data['obj']['name'], 'Document Status')
        self.assertEqual(data['obj']['dataType'], 'CHOICE')
        self.assertTrue(data['obj']['isManualEntry'])
        self.assertEqual(len(data['obj']['validationConfig']['choices']), 3)
        
        # Verify in database
        column = Column.objects.get(name='Document Status')
        self.assertEqual(column.data_type, 'CHOICE')
        self.assertTrue(column.is_manual_entry)
        
        # Verify fieldset was created
        self.assertTrue(hasattr(self.corpus, 'metadata_schema'))
        self.assertIsNotNone(self.corpus.metadata_schema)
    
    def test_create_metadata_column_without_permission(self):
        """Test that creating metadata requires corpus update permission."""
        other_user = User.objects.create_user(
            username="otheruser",
            password="otherpass"
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
            'corpusId': to_global_id('CorpusType', self.corpus.id),
            'name': 'Unauthorized Field',
            'dataType': 'STRING'
        }
        
        result = other_client.execute(mutation, variables=variables)
        self.assertIsNone(result.get('errors'))
        
        data = result['data']['createMetadataColumn']
        self.assertFalse(data['ok'])
        self.assertIn("don't have permission", data['message'])
    
    def test_update_metadata_column_mutation(self):
        """Test updating a metadata column."""
        # Create a column first
        fieldset = Fieldset.objects.create(
            name="Test Fieldset",
            description="Test",
            corpus=self.corpus,
            creator=self.user
        )
        column = Column.objects.create(
            fieldset=fieldset,
            name="Original Name",
            data_type='STRING',
            is_manual_entry=True,
            output_type='string',
            creator=self.user
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
            'columnId': to_global_id('ColumnType', column.id),
            'name': 'Updated Name',
            'helpText': 'This field contains the author name'
        }
        
        result = self.client.execute(mutation, variables=variables)
        self.assertIsNone(result.get('errors'))
        
        data = result['data']['updateMetadataColumn']
        self.assertTrue(data['ok'])
        self.assertEqual(data['obj']['name'], 'Updated Name')
        self.assertEqual(data['obj']['helpText'], 'This field contains the author name')
    
    def test_set_metadata_value_mutation(self):
        """Test setting a metadata value."""
        # Create metadata column
        fieldset = Fieldset.objects.create(
            name="Test Fieldset",
            description="Test",
            corpus=self.corpus,
            creator=self.user
        )
        column = Column.objects.create(
            fieldset=fieldset,
            name="Author",
            data_type='STRING',
            validation_config={'required': True},
            is_manual_entry=True,
            output_type='string',
            creator=self.user
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
            'documentId': to_global_id('DocumentType', self.document.id),
            'corpusId': to_global_id('CorpusType', self.corpus.id),
            'columnId': to_global_id('ColumnType', column.id),
            'value': 'John Doe'
        }
        
        result = self.client.execute(mutation, variables=variables)
        self.assertIsNone(result.get('errors'))
        
        data = result['data']['setMetadataValue']
        self.assertTrue(data['ok'])
        self.assertEqual(data['obj']['data']['value'], 'John Doe')
        self.assertEqual(data['obj']['column']['name'], 'Author')
        
        # Verify in database
        datacell = Datacell.objects.get(
            document=self.document,
            column=column
        )
        self.assertEqual(datacell.data['value'], 'John Doe')
    
    def test_update_existing_metadata_value(self):
        """Test updating an existing metadata value."""
        # Create column and datacell
        fieldset = Fieldset.objects.create(
            name="Test Fieldset",
            description="Test",
            corpus=self.corpus,
            creator=self.user
        )
        column = Column.objects.create(
            fieldset=fieldset,
            name="Version",
            data_type='STRING',
            is_manual_entry=True,
            output_type='string',
            creator=self.user
        )
        
        datacell = Datacell.objects.create(
            document=self.document,
            column=column,
            data={'value': '1.0'},
            data_definition='string',
            creator=self.user
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
            'documentId': to_global_id('DocumentType', self.document.id),
            'corpusId': to_global_id('CorpusType', self.corpus.id),
            'columnId': to_global_id('ColumnType', column.id),
            'value': '2.0'
        }
        
        result = self.client.execute(mutation, variables=variables)
        self.assertIsNone(result.get('errors'))
        self.assertTrue(result['data']['setMetadataValue']['ok'])
        
        # Verify updated value
        datacell.refresh_from_db()
        self.assertEqual(datacell.data['value'], '2.0')
    
    def test_delete_metadata_value_mutation(self):
        """Test deleting a metadata value."""
        # Create column and datacell
        fieldset = Fieldset.objects.create(
            name="Test Fieldset",
            description="Test",
            corpus=self.corpus,
            creator=self.user
        )
        column = Column.objects.create(
            fieldset=fieldset,
            name="To Delete",
            data_type='STRING',
            is_manual_entry=True,
            output_type='string',
            creator=self.user
        )
        datacell = Datacell.objects.create(
            document=self.document,
            column=column,
            data={'value': 'test'},
            data_definition='string',
            creator=self.user
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
            'documentId': to_global_id('DocumentType', self.document.id),
            'corpusId': to_global_id('CorpusType', self.corpus.id),
            'columnId': to_global_id('ColumnType', column.id)
        }
        
        result = self.client.execute(mutation, variables=variables)
        self.assertIsNone(result.get('errors'))
        self.assertTrue(result['data']['deleteMetadataValue']['ok'])
        
        # Verify deletion
        self.assertFalse(
            Datacell.objects.filter(id=datacell.id).exists()
        )
    
    def test_corpus_metadata_columns_query(self):
        """Test querying metadata columns for a corpus."""
        # Create metadata fieldset and columns
        fieldset = Fieldset.objects.create(
            name="Test Metadata",
            description="Test",
            corpus=self.corpus,
            creator=self.user
        )
        
        columns = []
        for i in range(3):
            column = Column.objects.create(
                fieldset=fieldset,
                name=f"Field {i}",
                data_type='STRING',
                is_manual_entry=True,
                output_type='string',
                display_order=i,
                creator=self.user
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
        
        variables = {
            'corpusId': to_global_id('CorpusType', self.corpus.id)
        }
        
        result = self.client.execute(query, variables=variables)
        self.assertIsNone(result.get('errors'))
        
        data = result['data']['corpusMetadataColumns']
        self.assertEqual(len(data), 3)
        for i, item in enumerate(data):
            self.assertEqual(item['name'], f"Field {i}")
            self.assertEqual(item['dataType'], 'STRING')
            self.assertTrue(item['isManualEntry'])
            self.assertEqual(item['displayOrder'], i)
    
    def test_document_metadata_datacells_query(self):
        """Test querying metadata datacells for a document."""
        # Create fieldset and columns
        fieldset = Fieldset.objects.create(
            name="Test Metadata",
            description="Test",
            corpus=self.corpus,
            creator=self.user
        )
        
        column1 = Column.objects.create(
            fieldset=fieldset,
            name="Author",
            data_type='STRING',
            is_manual_entry=True,
            output_type='string',
            creator=self.user
        )
        column2 = Column.objects.create(
            fieldset=fieldset,
            name="Reviewed",
            data_type='BOOLEAN',
            is_manual_entry=True,
            output_type='boolean',
            creator=self.user
        )
        
        Datacell.objects.create(
            document=self.document,
            column=column1,
            data={'value': 'Jane Doe'},
            data_definition='string',
            creator=self.user
        )
        Datacell.objects.create(
            document=self.document,
            column=column2,
            data={'value': True},
            data_definition='boolean',
            creator=self.user
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
            'documentId': to_global_id('DocumentType', self.document.id),
            'corpusId': to_global_id('CorpusType', self.corpus.id)
        }
        
        result = self.client.execute(query, variables=variables)
        self.assertIsNone(result.get('errors'))
        
        data = result['data']['documentMetadataDatacells']
        self.assertEqual(len(data), 2)
        
        # Check values
        values_by_name = {
            item['column']['name']: item['data']['value']
            for item in data
        }
        self.assertEqual(values_by_name['Author'], 'Jane Doe')
        self.assertTrue(values_by_name['Reviewed'])
    
    def test_metadata_completion_status_v2_query(self):
        """Test querying metadata completion status with new system."""
        # Create fieldset and columns (some required, some not)
        fieldset = Fieldset.objects.create(
            name="Test Metadata",
            description="Test",
            corpus=self.corpus,
            creator=self.user
        )
        
        columns = []
        for i in range(5):
            column = Column.objects.create(
                fieldset=fieldset,
                name=f"Field {i}",
                data_type='STRING',
                validation_config={'required': i < 2},  # First 2 are required
                is_manual_entry=True,
                output_type='string',
                creator=self.user
            )
            columns.append(column)
        
        # Create datacells for only some fields
        for i in [0, 2, 3]:  # Missing required field 1
            Datacell.objects.create(
                document=self.document,
                column=columns[i],
                data={'value': f'Value {i}'},
                data_definition='string',
                creator=self.user
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
            'documentId': to_global_id('DocumentType', self.document.id),
            'corpusId': to_global_id('CorpusType', self.corpus.id)
        }
        
        result = self.client.execute(query, variables=variables)
        self.assertIsNone(result.get('errors'))
        
        data = result['data']['metadataCompletionStatusV2']
        self.assertEqual(data['totalFields'], 5)
        self.assertEqual(data['filledFields'], 3)
        self.assertEqual(data['missingFields'], 2)
        self.assertEqual(data['percentage'], 60.0)
        self.assertEqual(data['missingRequired'], ['Field 1']) 