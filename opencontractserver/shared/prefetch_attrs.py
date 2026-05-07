"""User-scoped guardian prefetch attribute names.

The producer (``_apply_document_prefetches`` in ``Managers.py``) writes
guardian permission rows onto each instance under user-id-suffixed
attribute names. The user-id suffix is what makes the cache safe under
a mismatched lookup: a different user simply finds no attribute and
the consumer falls through to the guardian query path.

Consumers: ``get_users_permissions_for_obj``
(``opencontractserver/utils/permissioning.py``) and
``resolve_my_permissions``
(``config/graphql/permissioning/permission_annotator/mixins.py``).
"""

from __future__ import annotations


def user_perm_attr(user_id: int | str) -> str:
    """Attribute name for the user's prefetched ``*UserObjectPermission`` rows."""
    return f"_prefetched_user_perms_uid_{user_id}"


def user_group_perm_attr(user_id: int | str) -> str:
    """Attribute name for the user's prefetched ``*GroupObjectPermission`` rows."""
    return f"_prefetched_user_group_perms_uid_{user_id}"
