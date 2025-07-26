# Generated manually to remove metadata fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('annotations', '0034_annotationlabel_data_type_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='annotationlabel',
            name='data_type',
        ),
        migrations.RemoveField(
            model_name='annotationlabel',
            name='metadata_config',
        ),
        # Remove METADATA_LABEL from label_type choices
        migrations.AlterField(
            model_name='annotationlabel',
            name='label_type',
            field=models.CharField(
                choices=[
                    ('RELATIONSHIP_LABEL', 'Relationship label.'),
                    ('DOC_TYPE_LABEL', 'Document-level type label.'),
                    ('TOKEN_LABEL', 'Token-level labels for token-based labeling'),
                    ('SPAN_LABEL', 'Span labels for span-based labeling'),
                ],
                default='TOKEN_LABEL',
                max_length=128
            ),
        ),
        migrations.AlterField(
            model_name='annotation',
            name='annotation_type',
            field=models.CharField(
                choices=[
                    ('RELATIONSHIP_LABEL', 'Relationship label.'),
                    ('DOC_TYPE_LABEL', 'Document-level type label.'),
                    ('TOKEN_LABEL', 'Token-level labels for token-based labeling'),
                    ('SPAN_LABEL', 'Span labels for span-based labeling'),
                ],
                default='TOKEN_LABEL',
                max_length=128
            ),
        ),
    ] 