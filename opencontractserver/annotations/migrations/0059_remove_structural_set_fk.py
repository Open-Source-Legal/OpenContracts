"""
Remove structural_set FK and index from Annotation and Relationship models.

After the data migration moved all annotations to point to documents,
we can now safely remove the structural_set foreign key fields.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("annotations", "0058_migrate_structural_to_documents"),
    ]

    operations = [
        # Remove index on structural_set from Annotation
        migrations.RemoveIndex(
            model_name="annotation",
            name="annotations_structu_3ad1ab_idx",
        ),
        # Remove structural_set FK from Annotation
        migrations.RemoveField(
            model_name="annotation",
            name="structural_set",
        ),
        # Remove index on structural_set from Relationship
        migrations.RemoveIndex(
            model_name="relationship",
            name="annotations_structu_dbe65e_idx",
        ),
        # Remove structural_set FK from Relationship
        migrations.RemoveField(
            model_name="relationship",
            name="structural_set",
        ),
    ]
