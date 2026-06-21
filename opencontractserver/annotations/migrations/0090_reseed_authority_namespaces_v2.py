"""Second convergence re-seed of AuthorityNamespace (see 0085 for the rationale).

``0085_reseed_authority_namespaces`` was itself recorded as applied on the
self-hosted runner's persistent ``--reuse-db`` test volume *before* the seed
body and its supporting constants reached their final shape (the Phase 0+1
review hardening — extracting the seed into ``enrichment._namespace_seed`` and
finishing the prefix/classification maps — landed in a later commit on the same
branch). Because ``RunPython`` never re-executes a migration Django already
records as applied, that volume kept a stale ``AuthorityNamespace`` table and
``AuthorityNamespaceSeedTests`` (and the grammar-tier discovery test) failed in
CI even though they pass on a freshly created database.

Re-running the same idempotent ``update_or_create`` seed from a brand-new
migration forces convergence everywhere without re-touching the recorded state
of 0082/0085. Idempotent on an already-seeded DB, so it is a no-op in production
where the table is already populated.

Chained on top of the Phase 3/4/5 frontier/gate/crawl migrations so the whole
authority-discovery stack keeps a single linear migration leaf; the re-seed only
touches ``AuthorityNamespace`` and is order-independent of those migrations.

It also depends on ``0086_reseed_authority_namespaces_v2`` (the equivalent
re-seed that reached ``main`` independently) so that merging ``main`` into this
branch collapses the two parallel re-seed leaves into this single one instead of
leaving a multi-leaf migration graph. Both re-seeds are idempotent ``seed()``
no-ops, so the convergence edge is order-independent and safe.
"""

from django.db import migrations


def reseed(apps, schema_editor):
    # Import inside the function body (not at module load time) so a future
    # move/rename of _namespace_seed cannot break every makemigrations/migrate
    # invocation that merely loads this historical migration file.
    from opencontractserver.enrichment._namespace_seed import seed

    seed(apps, schema_editor)


class Migration(migrations.Migration):

    dependencies = [
        # 0089_authorityfrontier_deferred_cap_state is the Phase 5 leaf; it
        # transitively pulls in 0088_authorityfrontier_gate_states → 0087 (and
        # below). 0086_reseed is the parallel re-seed leaf that reached main
        # independently. Depending on both collapses the two leaves into this
        # single one after merging the Phase 4 base (which carries main).
        ("annotations", "0089_authorityfrontier_deferred_cap_state"),
        ("annotations", "0086_reseed_authority_namespaces_v2"),
    ]

    # Reverse is a no-op: 0082 owns the unseed path, and re-applying this
    # migration's forward op must never delete rows it merely refreshed.
    operations = [migrations.RunPython(reseed, migrations.RunPython.noop)]
