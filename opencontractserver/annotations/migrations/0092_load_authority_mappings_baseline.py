from django.db import migrations


def load_mappings(apps, schema_editor):
    # Pure YAML reader (no Django models) — safe to import at any migration state.
    from opencontractserver.enrichment.data import mappings as _mappings
    from opencontractserver.enrichment.data.authority_key_equivalence_seed import (
        CURATED_EQUIVALENCES,
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

    # SNAPSHOT of AuthorityMappingLoader.load()'s equivalence upsert, run against
    # the HISTORICAL model (apps.get_model) rather than the live service. This was
    # made explicit by 0092's original note: a later migration (0094) added
    # ``created_by`` to AuthorityKeyEquivalence, so calling the live loader here
    # would emit a SELECT for ``created_by_id`` before that column exists on a
    # fresh DB. The logic below mirrors the loader exactly (validate, dedupe,
    # skip source="manual", upsert source="baseline") so the end state is identical
    # and the loader remains the runtime source of truth.
    seen = set()
    for entry in _mappings.iter_equivalences():
        pair = (entry["from_key"], entry["to_key"])
        if pair in seen:
            continue
        seen.add(pair)
        existing = AuthorityKeyEquivalence.objects.filter(
            from_key=pair[0], to_key=pair[1]
        ).first()
        if existing is not None and existing.source == "manual":
            continue
        AuthorityKeyEquivalence.objects.update_or_create(
            from_key=pair[0],
            to_key=pair[1],
            defaults={
                "source": "baseline",
                "confidence": 1.0,
                "note": entry.get("note") or None,
            },
        )


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
