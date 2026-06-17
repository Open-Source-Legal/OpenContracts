"""Shared AuthorityNamespace seed logic for the seed/re-seed data migrations.

Lives outside the migrations package so both ``0082_seed_authority_namespaces``
and ``0085_reseed_authority_namespaces`` can import it with a normal ``import``
statement — a migration module name starts with a digit and can't be imported
directly, and ``importlib.import_module`` of one migration from another creates
a runtime coupling outside Django's dependency graph (``squashmigrations`` /
renaming would silently break it).

Both ``seed`` and ``unseed`` take the migration ``(apps, schema_editor)`` pair
so they operate on the historical ``AuthorityNamespace`` model, never the live
one. ``seed`` is idempotent (``update_or_create``).
"""


def seed(apps, schema_editor):
    from opencontractserver.enrichment import constants as C

    AuthorityNamespace = apps.get_model("annotations", "AuthorityNamespace")

    # Collect aliases per prefix from the reverse of AUTHORITY_PREFIX.
    aliases_by_prefix: dict[str, list[str]] = {}
    for alias, prefix in C.AUTHORITY_PREFIX.items():
        aliases_by_prefix.setdefault(prefix, []).append(alias.lower())

    prefixes = set(C.AUTHORITY_PREFIX.values()) | {C.SEC_RULE_PREFIX}
    for prefix in prefixes:
        # Graceful fallback so adding a prefix to AUTHORITY_PREFIX without its
        # classification/display-name entry can never crash ``migrate`` on a
        # clean schema (the constants test still enforces full coverage in CI).
        jur, typ = C.PREFIX_CLASSIFICATION.get(prefix, (None, None))
        AuthorityNamespace.objects.update_or_create(
            prefix=prefix,
            defaults={
                "display_name": C.PREFIX_DISPLAY_NAME.get(prefix, prefix),
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


def ensure_seeded(sender=None, *, apps=None, using=None, **kwargs):
    """``post_migrate`` receiver that converges the shipped namespace rows.

    A one-shot ``RunPython`` seed (0082) only ever runs once per migration
    ledger, so a persistent test-database volume reused across runs
    (``pytest --reuse-db`` on the self-hosted CI runner) keeps an empty
    ``AuthorityNamespace`` table forever once the seed migration is recorded
    applied — and a follow-up reseed migration (0085) cannot help, because it
    too is recorded applied on that same volume after its first run. Django
    emits ``post_migrate`` on *every* ``migrate`` invocation (including the
    keepdb path pytest-django uses for ``--reuse-db``), so seeding here
    converges any reused/poisoned database. ``seed`` is idempotent
    (``update_or_create``), so this is a no-op on freshly-seeded and
    production databases.

    Connected with ``sender=AnnotationsConfig`` so it fires exactly once, after
    the ``annotations`` app's tables exist.
    """
    if apps is None:
        return
    seed(apps, None)
