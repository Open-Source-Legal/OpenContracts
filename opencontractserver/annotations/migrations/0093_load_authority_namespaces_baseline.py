from django.db import migrations


def load_namespaces(apps, schema_editor):
    # Idempotently upsert the global AuthorityNamespace registry rows from the
    # YAML ``prefixes:`` section. Migrations 0082/0085 already seeded these from
    # the (now YAML-derived) constants; this re-runnable migration reconciles
    # already-migrated (live) DBs with the declarative file going forward, so
    # adding/editing a body of law is a YAML edit + a release migration calling
    # the loader (or `manage.py load_authority_mappings`), not a code change.
    #
    # NOTE: calls the LIVE-model loader (imports the current AuthorityNamespace),
    # not apps.get_model. Safe only while AuthorityNamespace's schema is frozen;
    # if a later migration alters it, snapshot the upsert logic into this
    # migration instead of importing the live service. The loader skips
    # corpus-linked rows (is_global=False), so a bootstrap-owned namespace is
    # never flipped to global.
    from opencontractserver.enrichment.services.authority_mapping_loader import (
        AuthorityMappingLoader,
    )

    AuthorityMappingLoader.load_namespaces()


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
