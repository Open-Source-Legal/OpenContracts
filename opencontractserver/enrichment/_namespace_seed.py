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

    The one-shot ``RunPython`` seed (0082) only runs once per migration ledger,
    so the rows it commits live *outside* any test transaction. Django's
    ``flush`` — run on every ``TransactionTestCase`` teardown — truncates
    ``annotations_authoritynamespace`` along with every other table, and with
    ``serialized_rollback`` disabled (the default) nothing restores it. Under
    ``pytest -n auto --dist loadscope`` any ``TransactionTestCase`` that runs
    before the seed/discovery tests on the same worker therefore leaves them
    reading an empty registry. Re-running the idempotent ``update_or_create``
    seed on every ``post_migrate`` converges the table again after each flush
    (and re-seeds reused/poisoned CI volumes at DB setup). It stays a no-op on
    freshly-seeded and production databases.

    ``migrate`` emits ``post_migrate`` with an ``apps`` kwarg (the historical
    project state); ``flush`` emits it *without* one
    (``django/core/management/commands/flush.py`` vs ``migrate.py``). The
    flush-path emission is precisely the one that has to re-seed, so — exactly
    like Django's own ``create_contenttypes`` / ``create_permissions``
    receivers — fall back to the global app registry when ``apps`` is absent
    rather than bailing.

    Connected with ``sender=AnnotationsConfig`` so it fires exactly once per
    emission, after the ``annotations`` app's tables exist.
    """
    if apps is None:
        from django.apps import apps as global_apps  # flush path: no apps kwarg

        apps = global_apps
    seed(apps, None)
