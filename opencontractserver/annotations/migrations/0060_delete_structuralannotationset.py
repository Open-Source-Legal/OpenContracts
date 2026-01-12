"""
Delete the StructuralAnnotationSet model.

This is the final migration in the removal of StructuralAnnotationSet.
At this point:
1. All constraints have been removed
2. All data has been migrated to documents
3. All FK references have been removed

The table can now be safely dropped.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("annotations", "0059_remove_structural_set_fk"),
        ("documents", "0030_remove_structural_annotation_set_fk"),
    ]

    operations = [
        migrations.DeleteModel(
            name="StructuralAnnotationSet",
        ),
    ]
