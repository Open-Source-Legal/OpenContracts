"""Re-run the AuthorityNamespace seed so it converges on already-migrated DBs.

``0082_seed_authority_namespaces`` is a data migration. Once Django records it
as applied, its ``RunPython`` never executes again — so any database that had
an intermediate revision of this branch applied (notably the self-hosted CI
runner's persistent, ``--reuse-db`` test volume) keeps an empty
``AuthorityNamespace`` table even after the seed body is correct. Re-running the
same idempotent ``update_or_create`` seed from a brand-new migration forces
convergence everywhere without re-touching 0082's recorded state.

Idempotent on a freshly-seeded DB (update_or_create is a no-op there), so it is
safe to ship to production where 0082 already populated the table.
"""

import importlib

from django.db import migrations

# Reuse 0082's seed function verbatim — module name starts with a digit, so it
# can't be imported with a normal ``import`` statement.
_seed_module = importlib.import_module(
    "opencontractserver.annotations.migrations.0082_seed_authority_namespaces"
)


def reseed(apps, schema_editor):
    _seed_module.seed(apps, schema_editor)


class Migration(migrations.Migration):

    dependencies = [
        ("annotations", "0084_corpusreference_detection"),
    ]

    # Reverse is a no-op: 0082 owns the unseed path, and re-applying this
    # migration's forward op must never delete rows it merely refreshed.
    operations = [migrations.RunPython(reseed, migrations.RunPython.noop)]
