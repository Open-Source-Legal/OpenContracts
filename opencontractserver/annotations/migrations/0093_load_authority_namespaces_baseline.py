from django.db import migrations


def load_namespaces(apps, schema_editor):
    # Idempotently upsert the global AuthorityNamespace registry rows from the
    # YAML ``prefixes:`` section. Migrations 0082/0085 already seeded these from
    # the (now YAML-derived) constants; this re-runnable migration reconciles
    # already-migrated (live) DBs with the declarative file going forward, so
    # adding/editing a body of law is a YAML edit + a release migration calling
    # the loader (or `manage.py load_authority_mappings`), not a code change.
    #
    # The upsert is INLINED against ``apps.get_model`` (the historical
    # AuthorityNamespace) rather than the live ``AuthorityMappingLoader``
    # service, so a fresh-DB ``migrate`` runs it against the schema as of this
    # migration. If a later migration alters AuthorityNamespace, this frozen
    # copy keeps working; the live service can diverge freely. ``iter_prefixes``
    # only parses the YAML (no model access), so it is safe to call here.
    # Corpus-linked rows (``is_global=False``, bootstrap-owned) are skipped so a
    # re-load never flips a corpus namespace to global.
    from opencontractserver.enrichment.data import mappings as _mappings

    AuthorityNamespace = apps.get_model("annotations", "AuthorityNamespace")

    for prefix, spec in _mappings.iter_prefixes().items():
        existing = AuthorityNamespace.objects.filter(prefix=prefix).first()
        if existing is not None and existing.authority_corpus_id:
            # A corpus-scoped namespace owns this prefix; never overwrite it.
            continue
        AuthorityNamespace.objects.update_or_create(
            prefix=prefix,
            defaults={
                "display_name": spec["display_name"],
                "jurisdiction": spec["jurisdiction"],
                "authority_type": spec["authority_type"],
                "aliases": sorted(set(spec["aliases"])),
                "is_global": True,
            },
        )


def noop_reverse(apps, schema_editor):
    # No-op reverse: AuthorityNamespace rows are shipped reference data also
    # seeded by 0082/0085; deleting them on reverse would strip legitimately
    # seeded global registry rows. Reversing this migration simply stops the
    # forward reconciliation — the rows themselves stay.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("annotations", "0092_load_authority_mappings_baseline"),
    ]

    operations = [
        migrations.RunPython(load_namespaces, noop_reverse),
    ]
