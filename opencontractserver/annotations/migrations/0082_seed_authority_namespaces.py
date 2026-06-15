"""Seed AuthorityNamespace from the static AUTHORITY_PREFIX registry.

Reproduces today's in-code alias map as queryable rows so the registry is
extensible without a code change. Idempotent on re-run via update_or_create.
"""
from django.db import migrations


def seed(apps, schema_editor):
    from opencontractserver.enrichment import constants as C

    AuthorityNamespace = apps.get_model("annotations", "AuthorityNamespace")

    # Collect aliases per prefix from the reverse of AUTHORITY_PREFIX.
    aliases_by_prefix: dict[str, list[str]] = {}
    for alias, prefix in C.AUTHORITY_PREFIX.items():
        aliases_by_prefix.setdefault(prefix, []).append(alias.lower())

    prefixes = set(C.AUTHORITY_PREFIX.values()) | {C.SEC_RULE_PREFIX}
    for prefix in prefixes:
        jur, typ = C.PREFIX_CLASSIFICATION[prefix]
        AuthorityNamespace.objects.update_or_create(
            prefix=prefix,
            defaults={
                "display_name": C.PREFIX_DISPLAY_NAME[prefix],
                "jurisdiction": jur,
                "authority_type": typ,
                "aliases": sorted(set(aliases_by_prefix.get(prefix, []))),
                "is_global": True,
            },
        )


def unseed(apps, schema_editor):
    from opencontractserver.enrichment import constants as C

    AuthorityNamespace = apps.get_model("annotations", "AuthorityNamespace")
    prefixes = set(C.AUTHORITY_PREFIX.values()) | {C.SEC_RULE_PREFIX}
    AuthorityNamespace.objects.filter(prefix__in=prefixes).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("annotations", "0081_authoritynamespace"),
    ]

    operations = [migrations.RunPython(seed, unseed)]
