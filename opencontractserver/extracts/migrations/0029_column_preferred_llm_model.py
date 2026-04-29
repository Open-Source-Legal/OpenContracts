"""Add Column.preferred_llm_model FK pointing at the new LLM config registry.

Nullable + ``SET_NULL`` so existing columns default to the system fallback,
and a deleted LLMModel never cascades into a deleted Column.
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("extracts", "0028_rename_placeholder_indexes"),
        ("llms", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="column",
            name="preferred_llm_model",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="columns",
                to="llms.llmmodel",
                help_text=(
                    "LLM to use when running this column. Leave blank to use "
                    "the system default."
                ),
            ),
        ),
    ]
