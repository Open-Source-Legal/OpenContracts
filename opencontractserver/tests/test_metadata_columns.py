from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from opencontractserver.extracts.models import METADATA_DATA_TYPES
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.extracts.models import Column, Datacell, Fieldset
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


@override_settings(VALIDATE_ANNOTATION_JSON=True)
class TestMetadataColumns(TestCase):
    """Test metadata functionality using Column/Datacell models."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            password="testpass"
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            creator=self.user
        )
        self.document = Document.objects.create(
            title="Test Document",
            creator=self.user
        )
        self.corpus.documents.add(self.document)
        
        # Create metadata fieldset
        self.fieldset = Fieldset.objects.create(
            name=f"{self.corpus.title} Metadata",
            description="Metadata schema",
            corpus=self.corpus,
            creator=self.user
        )
    
    def test_create_metadata_column(self):
        """Test creating a metadata column."""
        column = Column.objects.create(
            fieldset=self.fieldset,
            name="Author",
            data_type='STRING',
            validation_config={
                'required': True,
                'min_length': 1,
                'max_length': 100
            },
            is_manual_entry=True,
            output_type='string',
            creator=self.user
        )
        
        self.assertEqual(column.data_type, 'STRING')
        self.assertTrue(column.is_manual_entry)
        self.assertTrue(column.validation_config['required'])
    
    def test_column_validation_for_manual_entry(self):
        """Test that manual entry columns require data_type."""
        column = Column(
            fieldset=self.fieldset,
            name="Invalid",
            is_manual_entry=True,
            output_type='string',
            creator=self.user
        )
        
        with self.assertRaises(ValidationError) as context:
            column.full_clean()
        self.assertIn('data_type', context.exception.message_dict)
    
    def test_choice_column_requires_choices(self):
        """Test that choice columns require choices in config."""
        column = Column(
            fieldset=self.fieldset,
            name="Status",
            data_type='CHOICE',
            is_manual_entry=True,
            output_type='string',
            validation_config={'required': True},  # Missing choices
            creator=self.user
        )
        
        with self.assertRaises(ValidationError):
            column.full_clean()
    
    def test_datacell_boolean_validation(self):
        """Test boolean datacell validation."""
        column = Column.objects.create(
            fieldset=self.fieldset,
            name="Is Reviewed",
            data_type='BOOLEAN',
            is_manual_entry=True,
            output_type='boolean',
            creator=self.user
        )
        
        # Valid boolean
        datacell = Datacell(
            column=column,
            document=self.document,
            data={'value': True},
            data_definition='boolean',
            creator=self.user
        )
        datacell.full_clean()  # Should not raise
        datacell.save()
        
        # Invalid boolean - update the same datacell to avoid unique constraint
        datacell.data = {'value': 'yes'}
        with self.assertRaises(ValidationError) as context:
            datacell.save()  # save() calls full_clean() for manual entries
        self.assertIn('must be a boolean', str(context.exception))
    
    def test_integer_range_validation(self):
        """Test integer validation with min/max constraints."""
        column = Column.objects.create(
            fieldset=self.fieldset,
            name="Priority",
            data_type='INTEGER',
            validation_config={
                'min_value': 1,
                'max_value': 10
            },
            is_manual_entry=True,
            output_type='integer',
            creator=self.user
        )
        
        # Valid integer
        datacell = Datacell(
            column=column,
            document=self.document,
            data={'value': 5},
            data_definition='integer',
            creator=self.user
        )
        datacell.save()
        
        # Too low
        datacell.data = {'value': 0}
        with self.assertRaises(ValidationError) as context:
            datacell.save()
        self.assertIn('must be at least 1', str(context.exception))
    
    def test_string_length_validation(self):
        """Test string length constraints."""
        column = Column.objects.create(
            fieldset=self.fieldset,
            name="Code",
            data_type='STRING',
            validation_config={
                'min_length': 3,
                'max_length': 10
            },
            is_manual_entry=True,
            output_type='string',
            creator=self.user
        )
        
        # Valid length
        datacell = Datacell(
            column=column,
            document=self.document,
            data={'value': 'ABC123'},
            data_definition='string',
            creator=self.user
        )
        datacell.save()
        
        # Too short
        datacell.data = {'value': 'AB'}
        with self.assertRaises(ValidationError) as context:
            datacell.save()
        self.assertIn('at least 3 characters', str(context.exception))
    
    def test_email_validation(self):
        """Test email field validation."""
        column = Column.objects.create(
            fieldset=self.fieldset,
            name="Contact Email",
            data_type='EMAIL',
            is_manual_entry=True,
            output_type='string',
            creator=self.user
        )
        
        # Valid email
        datacell = Datacell(
            column=column,
            document=self.document,
            data={'value': 'test@example.com'},
            data_definition='string',
            creator=self.user
        )
        datacell.save()
        
        # Invalid email
        datacell.data = {'value': 'not-an-email'}
        with self.assertRaises(ValidationError) as context:
            datacell.save()
        self.assertIn('valid email address', str(context.exception))
    
    def test_date_format_validation(self):
        """Test date format validation."""
        column = Column.objects.create(
            fieldset=self.fieldset,
            name="Due Date",
            data_type='DATE',
            is_manual_entry=True,
            output_type='string',
            creator=self.user
        )
        
        # Valid date
        datacell = Datacell(
            column=column,
            document=self.document,
            data={'value': '2024-01-15'},
            data_definition='string',
            creator=self.user
        )
        datacell.save()
        
        # Invalid format
        datacell.data = {'value': '01/15/2024'}
        with self.assertRaises(ValidationError) as context:
            datacell.save()
        self.assertIn('YYYY-MM-DD format', str(context.exception))
    
    def test_multi_choice_validation(self):
        """Test multi-choice field validation."""
        column = Column.objects.create(
            fieldset=self.fieldset,
            name="Tags",
            data_type='MULTI_CHOICE',
            validation_config={
                'choices': ['Legal', 'Financial', 'Technical']
            },
            is_manual_entry=True,
            output_type='list',
            creator=self.user
        )
        
        # Valid choices
        datacell = Datacell(
            column=column,
            document=self.document,
            data={'value': ['Legal', 'Technical']},
            data_definition='list',
            creator=self.user
        )
        datacell.save()
        
        # Invalid choice
        datacell.data = {'value': ['Legal', 'Invalid']}
        with self.assertRaises(ValidationError) as context:
            datacell.save()
        self.assertIn('values must be from', str(context.exception))
    
    def test_required_field_validation(self):
        """Test required field validation."""
        column = Column.objects.create(
            fieldset=self.fieldset,
            name="Required Field",
            data_type='STRING',
            validation_config={'required': True},
            is_manual_entry=True,
            output_type='string',
            creator=self.user
        )
        
        # Missing value
        datacell = Datacell(
            column=column,
            document=self.document,
            data={'value': None},
            data_definition='string',
            creator=self.user
        )
        
        with self.assertRaises(ValidationError) as context:
            datacell.save()
        self.assertIn('is required', str(context.exception))
    
    def test_unique_constraint_per_document_column(self):
        """Test that only one datacell can exist per document/column for manual entries."""
        column = Column.objects.create(
            fieldset=self.fieldset,
            name="Unique Field",
            data_type='STRING',
            is_manual_entry=True,
            output_type='string',
            creator=self.user
        )
        
        # Create first datacell
        Datacell.objects.create(
            column=column,
            document=self.document,
            data={'value': 'First'},
            data_definition='string',
            creator=self.user
        )
        
        # Try to create duplicate - should violate constraint
        with self.assertRaises(Exception):  # IntegrityError
            Datacell.objects.create(
                column=column,
                document=self.document,
                data={'value': 'Second'},
                data_definition='string',
                creator=self.user
            )
    
    def test_regex_pattern_validation(self):
        """Test regex pattern validation."""
        column = Column.objects.create(
            fieldset=self.fieldset,
            name="Product Code",
            data_type='STRING',
            validation_config={
                'regex_pattern': r'^[A-Z]{2}-\d{4}$'
            },
            is_manual_entry=True,
            output_type='string',
            creator=self.user
        )
        
        # Valid pattern
        datacell = Datacell(
            column=column,
            document=self.document,
            data={'value': 'AB-1234'},
            data_definition='string',
            creator=self.user
        )
        datacell.save()
        
        # Invalid pattern
        datacell.data = {'value': 'abc-1234'}
        with self.assertRaises(ValidationError) as context:
            datacell.save()
        self.assertIn('format is invalid', str(context.exception))
    
    def test_extraction_columns_not_validated(self):
        """Test that extraction columns (is_manual_entry=False) don't trigger validation."""
        column = Column.objects.create(
            fieldset=self.fieldset,
            name="Extracted Data",
            query="Extract something",
            is_manual_entry=False,
            output_type='string',
            creator=self.user
        )
        
        # Invalid data that would fail manual validation
        datacell = Datacell(
            column=column,
            document=self.document,
            data={'random': 'data'},
            data_definition='string',
            creator=self.user
        )
        
        # Should save without validation errors
        datacell.save()
        self.assertTrue(datacell.id) 