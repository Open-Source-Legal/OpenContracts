"""Classify existing CorpusReference law rows by their canonical_key prefix.

Idempotent and forward-only in effect (reverse is a no-op): only rows still
missing a jurisdiction are touched, so re-running never clobbers values a later
detection pass set.

Coupling note: this reads live ``enrichment.constants`` (PREFIX_CLASSIFICATION)
rather than inlining a frozen snapshot. The constants are large and stable, and
the ``jurisdiction__isnull=True`` guard makes a constants change harmless on
re-run (it never overwrites). Do not repurpose this migration to *re-classify*
existing rows if the mapping changes — add a new data migration instead.
"""

from django.db import migrations


def backfill(apps, schema_editor):
    from opencontractserver.enrichment import constants as C

    CorpusReference = apps.get_model("annotations", "CorpusReference")
    qs = CorpusReference.objects.filter(
        reference_type=C.REF_LAW, jurisdiction__isnull=True
    ).exclude(canonical_key__isnull=True)
    for ref in qs.iterator():
        prefix = (ref.canonical_key or "").split(":", 1)[0]
        classification = C.PREFIX_CLASSIFICATION.get(prefix)
        if classification is None:
            continue
        ref.jurisdiction, ref.authority_type = classification
        ref.save(update_fields=["jurisdiction", "authority_type"])


def noop(apps, schema_editor):
    # Reverse intentionally does nothing: classification is additive metadata.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("annotations", "0082_seed_authority_namespaces"),
    ]

    operations = [migrations.RunPython(backfill, noop)]
