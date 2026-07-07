"""Django system checks enforcing the OpenContracts architecture invariants.

The single check registered here mirrors the pytest invariant in
``opencontractserver/tests/architecture/test_graphql_service_layer.py``.
Phase 6 (issue #1720) made every GraphQL resolver/mutation route through
the service layer; this check fires on every management command (so
``runserver``, ``migrate``, ``shell``, ``test``, ``check --deploy``, ...)
and blocks startup if any ``config/graphql/`` file inlines a Tier-0
permission primitive.

Wired in by ``opencontractserver.users.apps.UsersConfig.ready`` (the same
``ready()`` that already registers the Auth0 superuser allowlist check).
"""

from typing import Any

from django.core.checks import Error, Warning, register


@register("architecture")
def check_graphql_service_layer(app_configs: Any, **kwargs: Any) -> list[Error]:
    """Fail Django startup on any inline Tier-0 use in ``config/graphql/``.

    Same scanner as the pytest invariant — both call
    ``opencontractserver.shared.architecture_audit.audit_graphql_modules``
    so there is one source of truth for what counts as a violation, and
    ``architecture_audit.format_violation`` builds the per-identifier
    recipe so both surfaces show byte-identical fix instructions.

    Severity is ``Error`` (``opencontracts.E001``): Django blocks any
    management command (``runserver``, ``migrate``, ``shell``, ``test``,
    ``check --deploy``) when an Error-level check fires, which is the
    "fail on startup" semantic we want.

    Cost note: the AST scan runs once per ``manage.py`` invocation
    (Django's system-check framework fires every registered check on
    every command — ``migrate``, ``shell``, ``runserver``, ``test``…).
    With ~41 files in ``config/graphql/`` this is sub-50 ms and
    negligible relative to Django startup, so the check intentionally
    runs synchronously rather than being fast-pathed or gated behind
    ``DEBUG`` — the "fail on first management command" semantic is the
    whole point of dual-enforcement, and skipping the scan in some
    contexts would create silent gaps. Revisit only if the scan ever
    becomes a measurable slice of cold-start time.
    """
    # Deferred import — keeps ``shared.checks`` cheap to import; the AST
    # scan only runs when the registered check actually fires.
    from opencontractserver.shared.architecture_audit import (
        audit_graphql_modules,
        format_violation,
    )

    issues: list[Error] = []
    for module_path, lineno, name in audit_graphql_modules():
        short, hint = format_violation(module_path, lineno, name)
        issues.append(Error(short, hint=hint, id="opencontracts.E001"))
    return issues


@register("settings")
def check_vector_search_backend(app_configs: Any, **kwargs: Any) -> list[Error]:
    """Fail startup on an invalid ``VECTOR_SEARCH_BACKEND`` value.

    The backend flag is compared by string equality at query time, so a typo
    (``objectstorage``, ``turbopuffer``…) would otherwise silently degrade to
    the pgvector path — exactly the kind of misconfiguration that should fail
    loudly at boot instead (``opencontracts.E002``).
    """
    from django.conf import settings

    from opencontractserver.constants.search import VALID_VECTOR_SEARCH_BACKENDS

    configured = getattr(settings, "VECTOR_SEARCH_BACKEND", None)
    if configured is not None and configured not in VALID_VECTOR_SEARCH_BACKENDS:
        return [
            Error(
                f"VECTOR_SEARCH_BACKEND={configured!r} is not a valid vector "
                f"search backend.",
                hint=f"Valid values: {sorted(VALID_VECTOR_SEARCH_BACKENDS)}.",
                id="opencontracts.E002",
            )
        ]
    return []


@register("settings")
def check_vector_search_cache(app_configs: Any, **kwargs: Any) -> list[Warning]:
    """Warn when the object-storage backend runs on a process-local cache.

    The per-namespace compaction mutex (``compact_object_vector_namespace``)
    is a ``cache.add`` lock, so it only serialises compactors if all Celery
    workers share one cache backend. ``LocMemCache`` is per-process: with it,
    two workers can compact the same namespace concurrently and clobber each
    other's manifest (last-writer-wins), losing one compaction's fold.
    Warning (``opencontracts.W003``), not Error, because single-process
    deployments (and eager-Celery test runs) are perfectly safe.
    """
    from django.conf import settings

    from opencontractserver.constants.search import (
        VECTOR_SEARCH_BACKEND_OBJECT_STORAGE,
    )

    if (
        getattr(settings, "VECTOR_SEARCH_BACKEND", None)
        != VECTOR_SEARCH_BACKEND_OBJECT_STORAGE
    ):
        return []
    default_cache = settings.CACHES.get("default", {}).get("BACKEND", "")
    if "locmem" in default_cache.lower() or "dummy" in default_cache.lower():
        return [
            Warning(
                "VECTOR_SEARCH_BACKEND=object_storage with a process-local "
                f"default cache ({default_cache}): the compaction lock cannot "
                "serialise compactors across worker processes.",
                hint=(
                    "Use a shared cache backend (e.g. django_redis) in any "
                    "multi-worker deployment, or compactions may race."
                ),
                id="opencontracts.W003",
            )
        ]
    return []


@register("settings")
def check_vector_index_storage_exposure(
    app_configs: Any, **kwargs: Any
) -> list[Warning]:
    """Warn when the vector index may live in publicly-readable storage.

    The object-storage index stores raw ``(parent_pk, vector)`` blobs with no
    ACL of their own — query-time permissions are enforced by the ORM
    re-filter, NOT at the storage layer. If the default storage bucket is
    independently readable (public ACL, unsigned URLs, or a CDN custom
    domain fronting the whole bucket), anyone with bucket read access could
    enumerate vectors for every document/annotation in the system outside
    Django auth entirely. Warning ``opencontracts.W004``; see the
    "Permissions" section of
    ``docs/architecture/object_storage_vector_search.md``.
    """
    from django.conf import settings

    from opencontractserver.constants.search import (
        VECTOR_SEARCH_BACKEND_OBJECT_STORAGE,
    )

    if (
        getattr(settings, "VECTOR_SEARCH_BACKEND", None)
        != VECTOR_SEARCH_BACKEND_OBJECT_STORAGE
    ):
        return []
    if getattr(settings, "STORAGE_BACKEND", "LOCAL") != "AWS":
        return []
    public_signals = []
    default_acl = getattr(settings, "AWS_DEFAULT_ACL", None)
    if default_acl in ("public-read", "public-read-write"):
        public_signals.append(f"AWS_DEFAULT_ACL={default_acl!r}")
    if getattr(settings, "AWS_QUERYSTRING_AUTH", True) is False:
        public_signals.append("AWS_QUERYSTRING_AUTH=False (unsigned URLs)")
    custom_domain = getattr(settings, "AWS_S3_CUSTOM_DOMAIN", None)
    if custom_domain:
        public_signals.append(
            f"AWS_S3_CUSTOM_DOMAIN={custom_domain!r} (CDN fronting the bucket)"
        )
    if public_signals:
        return [
            Warning(
                "VECTOR_SEARCH_BACKEND=object_storage but the default storage "
                "shows public-read signals: " + "; ".join(public_signals) + ". "
                "The vector index has no ACL of its own — a readable bucket "
                "leaks raw vectors and parent ids for private documents.",
                hint=(
                    "Keep VECTOR_INDEX_STORAGE_PREFIX in a non-public bucket/"
                    "path (e.g. block public access on the prefix, or use a "
                    "dedicated private bucket via a custom Storage)."
                ),
                id="opencontracts.W004",
            )
        ]
    return []
