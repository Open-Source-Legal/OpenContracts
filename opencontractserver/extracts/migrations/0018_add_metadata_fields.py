# Generated manually for metadata fields

from django.db import migrations, models
import django.db.models.deletion
import opencontractserver.shared.defaults
import opencontractserver.shared.fields


class Migration(migrations.Migration):

    dependencies = [
        ('corpuses', '0002_initial'),  # Adjust based on actual corpus migration
        ('extracts', '0017_alter_column_task_name'),
    ]

    operations = [
        # Add corpus field to Fieldset
        migrations.AddField(
            model_name='fieldset',
            name='corpus',
            field=models.OneToOneField(
                blank=True,
                help_text='If set, this fieldset defines the metadata schema for the corpus',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='metadata_schema',
                to='corpuses.corpus'
            ),
        ),
        
        # Add metadata fields to Column
        migrations.AddField(
            model_name='column',
            name='data_type',
            field=models.CharField(
                blank=True,
                choices=[
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
                ],
                help_text='Structured data type for manual entry fields',
                max_length=32,
                null=True
            ),
        ),
        migrations.AddField(
            model_name='column',
            name='validation_config',
            field=opencontractserver.shared.fields.NullableJSONField(
                blank=True,
                default=opencontractserver.shared.defaults.jsonfield_default_value,
                help_text='Validation rules for manual entry',
                null=True
            ),
        ),
        migrations.AddField(
            model_name='column',
            name='is_manual_entry',
            field=models.BooleanField(
                default=False,
                help_text='True for manual metadata, False for extraction'
            ),
        ),
        migrations.AddField(
            model_name='column',
            name='default_value',
            field=opencontractserver.shared.fields.NullableJSONField(
                blank=True,
                default=None,
                help_text='Default value for manual entry fields',
                null=True
            ),
        ),
        migrations.AddField(
            model_name='column',
            name='help_text',
            field=models.TextField(
                blank=True,
                help_text='Help text to display for manual entry fields',
                null=True
            ),
        ),
        migrations.AddField(
            model_name='column',
            name='display_order',
            field=models.IntegerField(
                default=0,
                help_text='Order in which to display manual entry fields'
            ),
        ),
        
        # Add indexes for Column
        migrations.AddIndex(
            model_name='column',
            index=models.Index(fields=['fieldset', 'display_order'], name='extracts_co_fieldse_c5f8d1_idx'),
        ),
        migrations.AddIndex(
            model_name='column',
            index=models.Index(fields=['is_manual_entry'], name='extracts_co_is_manu_7b8e9f_idx'),
        ),
        
        # Make extract nullable on Datacell
        migrations.AlterField(
            model_name='datacell',
            name='extract',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='extracted_datacells',
                to='extracts.extract'
            ),
        ),
        
        # Add unique constraint for manual metadata
        migrations.AddConstraint(
            model_name='datacell',
            constraint=models.UniqueConstraint(
                condition=models.Q(extract__isnull=True),
                fields=['document', 'column'],
                name='unique_manual_metadata_per_doc_column'
            ),
        ),
    ] 