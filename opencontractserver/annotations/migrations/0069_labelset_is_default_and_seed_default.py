"""
Add ``LabelSet.is_default`` flag with a partial unique constraint and seed an
install-wide default LabelSet (owned by the first superuser, public, with a
small starter palette).
"""

import django.db.models
from django.db import migrations, models

from opencontractserver.annotations.label_set_seeds import (
    create_default_labelset,
    reverse_migration,
)


class Migration(migrations.Migration):

    dependencies = [
        ("annotations", "0068_enforce_embedder_path_not_null"),
        # Need the install's first superuser to own the seeded labelset.
        ("users", "0003_create_initial_superuser"),
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
        migrations.RunPython(
            create_default_labelset,
            reverse_migration,
        ),
    ]
