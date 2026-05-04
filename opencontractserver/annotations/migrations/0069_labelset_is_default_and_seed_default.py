"""Add ``LabelSet.is_default`` flag with a partial unique constraint.

Schema-only migration. The default LabelSet is seeded in
``0070_seed_default_labelset`` so that PostgreSQL does not refuse to create
the new index while FK trigger events queued by the data seeder are still
pending in the same transaction.
"""

import django.db.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("annotations", "0068_enforce_embedder_path_not_null"),
    ]

    operations = [
        migrations.AddField(
            model_name="labelset",
            name="is_default",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddConstraint(
            model_name="labelset",
            constraint=models.UniqueConstraint(
                condition=django.db.models.Q(("is_default", True)),
                fields=("is_default",),
                name="only_one_default_labelset",
            ),
        ),
    ]
