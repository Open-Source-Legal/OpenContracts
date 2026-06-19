from django.db import migrations


def load_mappings(apps, schema_editor):
    from opencontractserver.enrichment.data.authority_key_equivalence_seed import (
        CURATED_EQUIVALENCES,
    )
    from opencontractserver.enrichment.services.authority_mapping_loader import (
        AuthorityMappingLoader,
    )

    AuthorityKeyEquivalence = apps.get_model("annotations", "AuthorityKeyEquivalence")
    # One-time legacy reconciliation: migration 0087 seeded these 19 pairs as
    # source="manual" before the "baseline" source existed. They are shipped
    # reference data (loader-owned), NOT runtime curator overrides — so reclassify
    # them to "baseline" on both fresh and already-migrated (live) DBs, so the
    # idempotent loader owns them consistently going forward. No genuine runtime
    # "manual" override can exist for these pairs at this point.
    for from_key, to_key in CURATED_EQUIVALENCES:
        AuthorityKeyEquivalence.objects.filter(
            from_key=from_key, to_key=to_key, source="manual"
        ).update(source="baseline")

    # NOTE: calls the LIVE-model loader (imports the current AuthorityKeyEquivalence),
    # not apps.get_model. Safe only while this model's schema is frozen; if a later
    # migration alters AuthorityKeyEquivalence, snapshot the loader's upsert logic
    # into this migration instead of importing the live service.
    AuthorityMappingLoader.load()


def unload_baseline(apps, schema_editor):
    # Lossy reverse: deletes ALL baseline rows, including the 19 reclassified from the
    # legacy 0087 "manual" seed (they are NOT restored to "manual"). Acceptable for
    # shipped baseline reference data.
    AuthorityKeyEquivalence = apps.get_model("annotations", "AuthorityKeyEquivalence")
    AuthorityKeyEquivalence.objects.filter(source="baseline").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("annotations", "0091_alter_authoritykeyequivalence_source"),
    ]

    operations = [
        migrations.RunPython(load_mappings, unload_baseline),
    ]
