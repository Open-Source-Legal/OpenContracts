"""
Remove XOR constraints related to StructuralAnnotationSet.

This migration removes the constraints that enforce mutual exclusivity between
document_id and structural_set_id on Annotation and Relationship models.

These constraints must be removed BEFORE the data migration that moves
structural annotations from structural_set to document.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("annotations", "0051_alter_annotation_backend_lock_and_more"),
    ]

    operations = [
        # Remove XOR constraint from Annotation
        migrations.RemoveConstraint(
            model_name="annotation",
            name="annotation_has_single_parent",
        ),
        # Remove structural flag constraint from Annotation
        migrations.RemoveConstraint(
            model_name="annotation",
            name="structural_set_requires_structural_flag",
        ),
        # Remove XOR constraint from Relationship
        migrations.RemoveConstraint(
            model_name="relationship",
            name="relationship_has_single_parent",
        ),
        # Remove structural flag constraint from Relationship
        migrations.RemoveConstraint(
            model_name="relationship",
            name="rel_structural_set_requires_structural_flag",
        ),
    ]
