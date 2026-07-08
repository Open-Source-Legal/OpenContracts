"""Strawberry GraphQL core framework for OpenContracts.

This package reproduces, on top of strawberry-graphql, the graphene /
graphene-django runtime semantics the OpenContracts schema was built
against — relay global IDs, countable connections with graphene-django's
slicing + ``offset`` argument, django-filter FilterSet-backed connection
arguments, the ``GenericScalar`` / ``JSONString`` scalars, and the
permission-annotation fields (``myPermissions`` / ``isPublished`` /
``objectSharedWith``).

The wire contract (query shapes, type names, argument names, cursor
format) is pinned by ``opencontractserver/tests/test_schema_parity.py``
against the golden SDL captured from the graphene schema at migration
time (``config/graphql/schema.graphql``).
"""

from config.graphql.core.auth import (  # noqa: F401
    PermissionDenied,
    login_required,
    staff_member_required,
    superuser_required,
    user_passes_test,
)
from config.graphql.core.scalars import (  # noqa: F401
    BigInt,
    GenericScalar,
    JSONString,
)
