"""Seed the install-wide default LabelSet (owned by the first superuser).

Split from ``0069_labelset_is_default_and_seed_default`` so that the schema
changes commit before any FK-bearing INSERTs run — PostgreSQL rejects the
new index creation when FK trigger events are still pending in the same
transaction.
"""

from django.db import migrations

from opencontractserver.annotations.label_set_seeds import (
    create_default_labelset,
    reverse_migration,
)


class Migration(migrations.Migration):

    dependencies = [
        ("annotations", "0069_labelset_is_default_and_seed_default"),
        # Need the install's first superuser to own the seeded labelset.
        ("users", "0003_create_initial_superuser"),
    ]

    operations = [
        migrations.RunPython(
            create_default_labelset,
            reverse_migration,
        ),
    ]
