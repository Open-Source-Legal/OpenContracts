"""Seed AuthorityNamespace from the static AUTHORITY_PREFIX registry.

Reproduces today's in-code alias map as queryable rows so the registry is
extensible without a code change. Idempotent on re-run via update_or_create.

Coupling note: ``seed`` reads live ``enrichment.constants`` (AUTHORITY_PREFIX,
PREFIX_CLASSIFICATION, PREFIX_DISPLAY_NAME) rather than a frozen snapshot. A
future constants change therefore will NOT retroactively reach databases where
this migration is already recorded as applied — ship such changes as a new
re-seed migration (see 0085). The constants test enforces full coverage in CI.

The seed/unseed bodies live in ``enrichment._namespace_seed`` so 0085 can reuse
them with a normal import (a migration module name starts with a digit and can't
be imported directly).
"""

from django.db import migrations

from opencontractserver.enrichment._namespace_seed import seed, unseed


class Migration(migrations.Migration):

    dependencies = [
        ("annotations", "0081_authoritynamespace"),
    ]

    operations = [migrations.RunPython(seed, unseed)]
