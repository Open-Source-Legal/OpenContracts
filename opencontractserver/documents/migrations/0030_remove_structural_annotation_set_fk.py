"""
Remove structural_annotation_set FK from Document model.

After the data migration moved all annotations to point directly to documents,
and after removing the FK from Annotation/Relationship, we can now remove
the FK from Document that referenced StructuralAnnotationSet.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0029_alter_documentrelationshipuserobjectpermission_unique_together_and_more"),
        ("annotations", "0059_remove_structural_set_fk"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="document",
            name="structural_annotation_set",
        ),
    ]
