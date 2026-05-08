"""User-scoped guardian prefetch attribute names.

User-id suffix makes the cache safe under a mismatched lookup: a different
user finds no attribute and falls through to the guardian query path.
Producer: ``_apply_document_prefetches`` (``Managers.py``). Consumers:
``get_users_permissions_for_obj`` (``utils/permissioning.py``) and
``resolve_my_permissions`` (``permission_annotator/mixins.py``).
"""

from __future__ import annotations


def user_perm_attr(user_id: int | str) -> str:
    """Attr name for the user's prefetched ``*UserObjectPermission`` rows."""
    return f"_prefetched_user_perms_uid_{user_id}"


def user_group_perm_attr(user_id: int | str) -> str:
    """Attr name for the user's prefetched ``*GroupObjectPermission`` rows."""
    return f"_prefetched_user_group_perms_uid_{user_id}"
