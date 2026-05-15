"""Add ``Embedding.relationship`` polymorphic FK + partial unique constraint.

Issue #1645: enable vector search over materialised ``OC_SUBTREE_GROUP``
relationships so semantic search can return relationships (not just
annotations). The new column is nullable so existing rows keep working
unchanged; only the subtree-group materialiser writes to it today.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("annotations", "0072_annotation_link_url"),
    ]

    operations = [
        migrations.AddField(
            model_name="embedding",
            name="relationship",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "References the Relationship this embedding belongs to " "(if any)."
                ),
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name="embedding_set",
                to="annotations.relationship",
            ),
        ),
        migrations.AddConstraint(
            model_name="embedding",
            constraint=models.UniqueConstraint(
                condition=models.Q(("relationship__isnull", False)),
                fields=("embedder_path", "relationship"),
                name="unique_embedding_per_relationship_embedder",
            ),
        ),
    ]
