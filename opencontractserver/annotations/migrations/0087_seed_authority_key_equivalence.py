"""Seed curated act-section <-> USC canonical-key equivalence pairs.

Loads the hand-curated Exchange Act and Securities Act <-> USC-15 pairs
from the enrichment seed module.  Each pair is ``update_or_create``'d so
the migration is safe to re-apply and a subsequent data-import migration
can extend the set without conflicts.
"""

from __future__ import annotations

from django.db import migrations


def seed(apps, schema_editor):
    from opencontractserver.enrichment.data.authority_key_equivalence_seed import (
        CURATED_EQUIVALENCES,
    )

    AuthorityKeyEquivalence = apps.get_model("annotations", "AuthorityKeyEquivalence")
    for from_key, to_key in CURATED_EQUIVALENCES:
        AuthorityKeyEquivalence.objects.update_or_create(
            from_key=from_key,
            to_key=to_key,
            defaults={"source": "manual", "confidence": 1.0},
        )


def unseed(apps, schema_editor):
    from opencontractserver.enrichment.data.authority_key_equivalence_seed import (
        CURATED_EQUIVALENCES,
    )

    AuthorityKeyEquivalence = apps.get_model("annotations", "AuthorityKeyEquivalence")
    for from_key, to_key in CURATED_EQUIVALENCES:
        AuthorityKeyEquivalence.objects.filter(
            from_key=from_key, to_key=to_key, source="manual"
        ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("annotations", "0086_authorityfrontier_keyequivalence"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
