"""Add iteration lineage + captured model config to Extract.

`parent_extract` lets the UI walk an iteration series; `model_config`
captures the run-time model snapshot so two iterations sharing a fieldset
can be compared for model drift.
"""

import django.db.models.deletion
from django.db import migrations, models

import opencontractserver.shared.defaults
import opencontractserver.shared.fields


class Migration(migrations.Migration):

    dependencies = [
        ("extracts", "0028_rename_placeholder_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="extract",
            name="parent_extract",
            field=models.ForeignKey(
                blank=True,
                db_index=True,
                help_text=(
                    "Extract this iteration was forked from. Null for the "
                    "root of an iteration series."
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="iterations",
                to="extracts.extract",
            ),
        ),
        migrations.AddField(
            model_name="extract",
            name="model_config",
            field=opencontractserver.shared.fields.NullableJSONField(
                blank=True,
                default=opencontractserver.shared.defaults.jsonfield_default_value,
                help_text="Model/run configuration captured for this iteration.",
                null=True,
            ),
        ),
    ]
