import django
from django.contrib.auth import get_user_model
from guardian.models import GroupObjectPermissionBase, UserObjectPermissionBase

from opencontractserver.annotations.models import Annotation
from opencontractserver.documents.models import Document
from opencontractserver.shared.defaults import jsonfield_default_value
from opencontractserver.shared.fields import NullableJSONField
from opencontractserver.shared.Models import BaseOCModel

User = get_user_model()

# Define metadata data types
METADATA_DATA_TYPES = [
    ('STRING', 'String'),
    ('TEXT', 'Text (Multiline)'),
    ('BOOLEAN', 'Boolean'),
    ('INTEGER', 'Integer'),
    ('FLOAT', 'Float'),
    ('DATE', 'Date'),
    ('DATETIME', 'DateTime'),
    ('URL', 'URL'),
    ('EMAIL', 'Email'),
    ('CHOICE', 'Choice (Select)'),
    ('MULTI_CHOICE', 'Multiple Choice'),
    ('JSON', 'JSON Object'),
]


class Fieldset(BaseOCModel):
    name = django.db.models.CharField(max_length=256, null=False, blank=False)
    description = django.db.models.TextField(null=False, blank=False)
    
    # NEW: Optional corpus link for metadata schemas
    corpus = django.db.models.OneToOneField(
        "corpuses.Corpus",
        null=True,
        blank=True,
        on_delete=django.db.models.CASCADE,
        related_name="metadata_schema",
        help_text="If set, this fieldset defines the metadata schema for the corpus"
    )

    class Meta:
        permissions = (
            ("permission_fieldset", "permission fieldset"),
            ("create_fieldset", "create fieldset"),
            ("read_fieldset", "read fieldset"),
            ("update_fieldset", "update fieldset"),
            ("remove_fieldset", "delete fieldset"),
        )


class FieldsetUserObjectPermission(UserObjectPermissionBase):
    content_object = django.db.models.ForeignKey(
        "Fieldset", on_delete=django.db.models.CASCADE
    )


class FieldsetGroupObjectPermission(GroupObjectPermissionBase):
    content_object = django.db.models.ForeignKey(
        "Fieldset", on_delete=django.db.models.CASCADE
    )


class Column(BaseOCModel):
    name = django.db.models.CharField(
        max_length=256, null=False, blank=False, default=""
    )
    fieldset = django.db.models.ForeignKey(
        "Fieldset", related_name="columns", on_delete=django.db.models.CASCADE
    )

    # TODO - Should set up validations so EITHER of these can be null but not both.
    query = django.db.models.TextField(null=True, blank=True)
    match_text = django.db.models.TextField(null=True, blank=True)
    must_contain_text = django.db.models.TextField(null=True, blank=True)

    output_type = django.db.models.TextField(null=False, blank=False)
    limit_to_label = django.db.models.CharField(max_length=512, null=True, blank=True)
    instructions = django.db.models.TextField(null=True, blank=True)
    extract_is_list = django.db.models.BooleanField(default=False)
    task_name = django.db.models.CharField(
        max_length=1024,
        null=False,
        blank=False,
        default="opencontractserver.tasks.data_extract_tasks.doc_extract_query_task",
    )
    
    # NEW: Metadata-specific fields
    data_type = django.db.models.CharField(
        max_length=32,
        choices=METADATA_DATA_TYPES,
        null=True,
        blank=True,
        help_text="Structured data type for manual entry fields"
    )
    validation_config = NullableJSONField(
        default=jsonfield_default_value,
        null=True,
        blank=True,
        help_text="Validation rules for manual entry"
    )
    is_manual_entry = django.db.models.BooleanField(
        default=False,
        help_text="True for manual metadata, False for extraction"
    )
    default_value = NullableJSONField(
        default=None,
        null=True,
        blank=True,
        help_text="Default value for manual entry fields"
    )
    help_text = django.db.models.TextField(
        null=True,
        blank=True,
        help_text="Help text to display for manual entry fields"
    )
    display_order = django.db.models.IntegerField(
        default=0,
        help_text="Order in which to display manual entry fields"
    )
    
    def clean(self):
        """Validate configuration based on entry mode."""
        super().clean()
        
        if self.is_manual_entry:
            # Manual entry requires data_type
            if not self.data_type:
                raise django.core.exceptions.ValidationError({
                    'data_type': 'Manual entry columns require data_type'
                })
            # Validate validation_config structure
            if self.data_type in ['CHOICE', 'MULTI_CHOICE'] and self.validation_config:
                if not self.validation_config.get('choices') or not isinstance(self.validation_config['choices'], list):
                    raise django.core.exceptions.ValidationError({
                        'validation_config': 'Choice fields require choices list in validation_config'
                    })
        else:
            # Extraction requires query or match_text
            if not (self.query or self.match_text):
                raise django.core.exceptions.ValidationError(
                    "Extraction columns require query or match_text"
                )

    class Meta:
        permissions = (
            ("permission_column", "permission column"),
            ("create_column", "create column"),
            ("read_column", "read column"),
            ("update_column", "update column"),
            ("remove_column", "delete column"),
        )
        indexes = [
            django.db.models.Index(fields=["fieldset", "display_order"]),
            django.db.models.Index(fields=["is_manual_entry"]),
        ]


class ColumnUserObjectPermission(UserObjectPermissionBase):
    content_object = django.db.models.ForeignKey(
        "Column", on_delete=django.db.models.CASCADE
    )


class ColumnGroupObjectPermission(GroupObjectPermissionBase):
    content_object = django.db.models.ForeignKey(
        "Column", on_delete=django.db.models.CASCADE
    )


class Extract(BaseOCModel):
    corpus = django.db.models.ForeignKey(
        "corpuses.Corpus",  # Using string reference instead of direct import
        related_name="extracts",
        on_delete=django.db.models.SET_NULL,
        null=True,
        blank=True,
    )
    documents = django.db.models.ManyToManyField(
        Document,
        related_name="extracts",
        related_query_name="extract",
        blank=True,
    )
    name = django.db.models.CharField(max_length=512, null=False, blank=False)
    fieldset = django.db.models.ForeignKey(
        "Fieldset",
        related_name="extracts",
        on_delete=django.db.models.PROTECT,
        null=False,
    )
    created = django.db.models.DateTimeField(auto_now_add=True)
    started = django.db.models.DateTimeField(null=True, blank=True)
    finished = django.db.models.DateTimeField(null=True, blank=True)
    error = django.db.models.TextField(null=True, blank=True)

    # If applicable, what CorpusAction ran?
    corpus_action = django.db.models.ForeignKey(
        "corpuses.CorpusAction",  # Using string reference instead of direct import
        related_name="extracts",
        blank=True,
        null=True,
        on_delete=django.db.models.SET_NULL,
    )

    class Meta:
        permissions = (
            ("permission_extract", "permission extract"),
            ("create_extract", "create extract"),
            ("read_extract", "read extract"),
            ("update_extract", "update extract"),
            ("remove_extract", "delete extract"),
        )


class ExtractUserObjectPermission(UserObjectPermissionBase):
    content_object = django.db.models.ForeignKey(
        "Extract", on_delete=django.db.models.CASCADE
    )


class ExtractGroupObjectPermission(GroupObjectPermissionBase):
    content_object = django.db.models.ForeignKey(
        "Extract", on_delete=django.db.models.CASCADE
    )


class Datacell(BaseOCModel):
    extract = django.db.models.ForeignKey(
        "Extract",
        related_name="extracted_datacells",
        on_delete=django.db.models.CASCADE,
        null=True,  # NEW: Make nullable for manual metadata
        blank=True,
    )
    column = django.db.models.ForeignKey(
        "Column", related_name="extracted_datacells", on_delete=django.db.models.CASCADE
    )
    document = django.db.models.ForeignKey(
        Document, related_name="extracted_datacells", on_delete=django.db.models.CASCADE
    )
    sources = django.db.models.ManyToManyField(
        Annotation,
        blank=True,
        related_name="referencing_cells",
        related_query_name="referencing_cell",
    )
    data = NullableJSONField(default=jsonfield_default_value, null=True, blank=True)
    data_definition = django.db.models.TextField(null=False, blank=False)
    started = django.db.models.DateTimeField(null=True, blank=True)
    completed = django.db.models.DateTimeField(null=True, blank=True)
    failed = django.db.models.DateTimeField(null=True, blank=True)
    stacktrace = django.db.models.TextField(null=True, blank=True)

    approved_by = django.db.models.ForeignKey(
        get_user_model(),
        on_delete=django.db.models.CASCADE,
        null=True,
        blank=True,
        related_name="approved_cells",
    )
    rejected_by = django.db.models.ForeignKey(
        get_user_model(),
        on_delete=django.db.models.CASCADE,
        null=True,
        blank=True,
        related_name="rejected_cells",
    )
    corrected_data = NullableJSONField(default=None, null=True, blank=True)
    
    def clean(self):
        """Validate data against column configuration."""
        super().clean()
        
        if self.column.is_manual_entry:
            # Apply validation for manual entries based on data type and validation config
            self._validate_manual_entry()
    
    def _validate_manual_entry(self):
        """Validate manual entry data."""
        if not self.data:
            self.data = {}
        
        if 'value' not in self.data:
            if self.column.validation_config.get('required'):
                raise django.core.exceptions.ValidationError(
                    f"{self.column.name} is required"
                )
            return
        
        value = self.data['value']
        data_type = self.column.data_type
        config = self.column.validation_config or {}
        
        # Skip further validation if value is None
        if value is None:
            if config.get('required', False):
                raise django.core.exceptions.ValidationError(
                    f"{self.column.name} is required"
                )
            return
        
        # Type-specific validation
        if data_type == 'BOOLEAN':
            if not isinstance(value, bool):
                raise django.core.exceptions.ValidationError(
                    f"{self.column.name} must be a boolean"
                )
        
        elif data_type == 'INTEGER':
            if not isinstance(value, int) or isinstance(value, bool):
                raise django.core.exceptions.ValidationError(
                    f"{self.column.name} must be an integer"
                )
            self._validate_numeric_range(value, config, self.column.name)
        
        elif data_type == 'FLOAT':
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise django.core.exceptions.ValidationError(
                    f"{self.column.name} must be a number"
                )
            self._validate_numeric_range(value, config, self.column.name)
        
        elif data_type in ['STRING', 'TEXT', 'URL', 'EMAIL']:
            if not isinstance(value, str):
                raise django.core.exceptions.ValidationError(
                    f"{self.column.name} must be a string"
                )
            self._validate_string_constraints(value, config, data_type, self.column.name)
        
        elif data_type == 'DATE':
            if not isinstance(value, str):
                raise django.core.exceptions.ValidationError(
                    f"{self.column.name} must be a date string"
                )
            try:
                from datetime import datetime
                datetime.strptime(value, '%Y-%m-%d')
            except ValueError:
                raise django.core.exceptions.ValidationError(
                    f"{self.column.name} must be in YYYY-MM-DD format"
                )
        
        elif data_type == 'DATETIME':
            if not isinstance(value, str):
                raise django.core.exceptions.ValidationError(
                    f"{self.column.name} must be a datetime string"
                )
            try:
                from datetime import datetime
                datetime.fromisoformat(value.replace('Z', '+00:00'))
            except ValueError:
                raise django.core.exceptions.ValidationError(
                    f"{self.column.name} must be in ISO datetime format"
                )
        
        elif data_type == 'CHOICE':
            choices = config.get('choices', [])
            if value not in choices:
                raise django.core.exceptions.ValidationError(
                    f"{self.column.name} must be one of: {', '.join(choices)}"
                )
        
        elif data_type == 'MULTI_CHOICE':
            if not isinstance(value, list):
                raise django.core.exceptions.ValidationError(
                    f"{self.column.name} must be a list"
                )
            choices = config.get('choices', [])
            for v in value:
                if v not in choices:
                    raise django.core.exceptions.ValidationError(
                        f"{self.column.name} values must be from: {', '.join(choices)}"
                    )
        
        elif data_type == 'JSON':
            if not isinstance(value, (dict, list)):
                raise django.core.exceptions.ValidationError(
                    f"{self.column.name} must be a JSON object or array"
                )
    
    def _validate_numeric_range(self, value, config, field_name):
        """Validate numeric constraints."""
        if 'min_value' in config and value < config['min_value']:
            raise django.core.exceptions.ValidationError(
                f"{field_name} must be at least {config['min_value']}"
            )
        if 'max_value' in config and value > config['max_value']:
            raise django.core.exceptions.ValidationError(
                f"{field_name} must be at most {config['max_value']}"
            )
    
    def _validate_string_constraints(self, value, config, data_type, field_name):
        """Validate string constraints."""
        if 'min_length' in config and len(value) < config['min_length']:
            raise django.core.exceptions.ValidationError(
                f"{field_name} must be at least {config['min_length']} characters"
            )
        if 'max_length' in config and len(value) > config['max_length']:
            raise django.core.exceptions.ValidationError(
                f"{field_name} must be at most {config['max_length']} characters"
            )
        
        if data_type == 'EMAIL':
            import re
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, value):
                raise django.core.exceptions.ValidationError(
                    f"{field_name} must be a valid email address"
                )
        
        elif data_type == 'URL':
            import re
            url_pattern = r'^https?://[^\s/$.?#].[^\s]*$'
            if not re.match(url_pattern, value):
                raise django.core.exceptions.ValidationError(
                    f"{field_name} must be a valid URL"
                )
        
        if 'regex_pattern' in config and config['regex_pattern']:
            import re
            if not re.match(config['regex_pattern'], value):
                raise django.core.exceptions.ValidationError(
                    f"{field_name} format is invalid"
                )
    
    def save(self, *args, **kwargs):
        """Override save to validate manual entry data."""
        if self.column.is_manual_entry:
            self.full_clean()
        return super().save(*args, **kwargs)

    class Meta:
        permissions = (
            ("permission_datacell", "permission datacell"),
            ("create_datacell", "create datacell"),
            ("read_datacell", "read datacell"),
            ("update_datacell", "update datacell"),
            ("remove_datacell", "delete datacell"),
        )
        constraints = [
            django.db.models.UniqueConstraint(
                fields=["document", "column"],
                condition=django.db.models.Q(extract__isnull=True),
                name="unique_manual_metadata_per_doc_column"
            )
        ]


class DatacellUserObjectPermission(UserObjectPermissionBase):
    content_object = django.db.models.ForeignKey(
        "Datacell", on_delete=django.db.models.CASCADE
    )


class DatacellGroupObjectPermission(GroupObjectPermissionBase):
    content_object = django.db.models.ForeignKey(
        "Datacell", on_delete=django.db.models.CASCADE
    )
