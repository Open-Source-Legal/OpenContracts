"""Merge the two annotations migration leaves into one.

Merging the corpus-enrichment-runner branch (which carries
``0090_reseed_authority_namespaces_v2``, a no-op idempotent AuthorityNamespace
re-seed) into the enrichment-inflight-concurrency branch (which carries the
``0090_corpusreference_is_provisional`` → … → ``0094_authoritykeyequivalence_created_by``
schema chain) left two leaf nodes that share the ``0089`` ancestor. Django's
``migrate`` aborts on multiple leaves, so this empty merge migration depends on
both leaves to collapse the graph back to a single linear tip. The re-seed only
touches ``AuthorityNamespace`` rows and is order-independent of the schema
changes, so no ordering constraint is lost.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("annotations", "0090_reseed_authority_namespaces_v2"),
        ("annotations", "0094_authoritykeyequivalence_created_by"),
    ]

    operations = []
