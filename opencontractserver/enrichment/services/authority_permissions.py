"""The single authority-admin permission gate.

The authority-management surface (namespaces, the discovery frontier, runtime
key-equivalences) is system-wide global data with **no per-object permissions**,
so it cannot use the corpus/document guardian model. Before this module each
surface re-derived its own ``user.is_superuser`` check inline (the node
``get_queryset`` overrides, ``AuthorityKeyEquivalenceService.is_superuser``,
``AuthorityFrontierService.admin_state_counts``), so widening the role later
would mean hunting down every copy.

``is_authority_admin`` is the ONE definition every authority service, node, and
mutation funnels through. Today it is "an authenticated superuser"; the single
future seam to widen it (a dedicated group / a ``law_librarian`` flag that may
curate namespaces + mappings without full superuser) lives here and nowhere
else. The companion ``DENIED`` string is the opaque denial every authority
surface returns — identical whether the row is missing or the caller lacks
access, so the superuser-only surface is no existence oracle.
"""

from __future__ import annotations

from typing import Any

# Opaque denial — identical for "not found" and "not permitted" so the
# authority surface (no per-object perms) leaks no existence signal.
DENIED = "Resource not found or you do not have permission."


def is_authority_admin(user: Any) -> bool:
    """Return ``True`` iff ``user`` may administer global authority data.

    The single gate for the whole authority-management surface. Authenticated
    superuser today; widen HERE (and only here) to introduce a finer-grained
    law-librarian role later.
    """
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and getattr(user, "is_superuser", False)
    )
