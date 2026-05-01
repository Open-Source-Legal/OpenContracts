"""Phase 4: per-column LLM override + per-cell forensic trace.

Adds:

* ``Column.preferred_llm`` — optional FK to ``llm_configs.RegisteredLLM``,
  ``on_delete=PROTECT``. When set, the extract resolver uses this row
  instead of ``LLMSettings.default_extract_llm``.
* ``Datacell.executed_llm`` — optional FK to ``llm_configs.RegisteredLLM``,
  ``on_delete=PROTECT``. Set by the extract task on success / failure
  so historical Datacells trace to the exact (immutable) lineage
  version that produced them.

PROTECT semantics align with the immutable-history contract on
``RegisteredLLM`` (no delete mutation exists in the GraphQL surface;
PROTECT is defence in depth at the DB layer).
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("extracts", "0028_rename_placeholder_indexes"),
        ("llm_configs", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="column",
            name="preferred_llm",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="columns",
                to="llm_configs.registeredllm",
                help_text=(
                    "Optional per-column LLM override. NULL falls back to "
                    "LLMSettings.default_extract_llm via the resolver."
                ),
            ),
        ),
        migrations.AddField(
            model_name="datacell",
            name="executed_llm",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="executed_datacells",
                to="llm_configs.registeredllm",
                help_text=(
                    "RegisteredLLM lineage version that produced this cell's "
                    "data. NULL for legacy / unexecuted cells."
                ),
            ),
        ),
    ]
