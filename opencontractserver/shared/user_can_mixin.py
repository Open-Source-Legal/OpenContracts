"""Shared ``user_can`` bodies for both Manager/QuerySet and instance surfaces.

Lives in its own module so ``shared/Managers.py``, ``shared/QuerySets.py``,
and any model that needs the instance-side delegate (``BaseOCModel`` and the
``TreeNode``-rooted ``Corpus`` / ``CorpusFolder``) can mix these in without
dragging ``utils/permissioning`` — which calls ``get_user_model()`` at
import time via the GraphQL middleware — into the early ``shared.Models``
⇄ ``users.models`` startup chain.

Two mixins, two signatures:

- ``UserCanMixin`` — for Managers and QuerySets. Method takes
  ``(self, user, instance, permission)``. Used by ``BaseVisibilityManager``
  and ``PermissionedTreeQuerySet``.

- ``InstanceUserCanMixin`` — for model classes. Method takes
  ``(self, user, permission)`` and routes through
  ``type(self)._default_manager.user_can`` so per-model overrides live in
  one place (the Manager / QuerySet). Used by ``BaseOCModel`` and by
  ``TreeNode``-rooted models whose default manager exposes the same
  contract (``Corpus``, ``CorpusFolder``).
"""

from __future__ import annotations

from typing import Any


class UserCanMixin:
    """Delegating ``user_can(user, instance, permission)`` for managers/querysets.

    The actual authorization body lives in
    ``opencontractserver.utils.permissioning._default_user_can``; we import
    it lazily inside the method to avoid pulling that module — which calls
    ``get_user_model()`` at import time via the GraphQL middleware — into
    the early ``shared.Models`` ⇄ ``users.models`` startup chain.

    Important when mixed onto a QuerySet (e.g. ``PermissionedTreeQuerySet``):
    ``user_can`` is a **single-object authorization check on the supplied
    ``instance`` argument**. It does NOT consult the QuerySet's current
    WHERE clause. ``Corpus.objects.filter(is_public=True).user_can(user,
    some_private_corpus, READ)`` evaluates against ``some_private_corpus``
    on its own merits — the ``filter(is_public=True)`` is ignored. Use
    ``visible_to_user`` if you want a queryset filter.
    """

    def user_can(
        self,
        user: Any,
        instance: Any,
        permission: Any,
        *,
        include_group_permissions: bool = True,
    ) -> bool:
        from opencontractserver.utils.permissioning import _default_user_can

        return _default_user_can(
            user,
            instance,
            permission,
            include_group_permissions=include_group_permissions,
        )


class InstanceUserCanMixin:
    """Ergonomic ``self.user_can(user, permission)`` delegate for model classes.

    Routes through ``type(self)._default_manager.user_can`` so per-model
    overrides live in the Manager / QuerySet (a single source of truth)
    rather than getting duplicated on every model class.

    Hard contract: the model's ``_default_manager`` MUST implement
    ``user_can`` (typically by inheriting ``UserCanMixin`` —
    ``BaseVisibilityManager`` and ``PermissionedTreeQuerySet`` both do).
    If the guard below fires, override ``user_can`` on the specific model
    or fix the manager — never paper over the ``AttributeError``.
    """

    def user_can(
        self,
        user: Any,
        permission: Any,
        *,
        include_group_permissions: bool = True,
    ) -> bool:
        # ``_default_manager`` is supplied by every concrete Django model
        # class this mixin is paired with — not by the mixin itself — so
        # mypy can't see it on ``type(self)``.  Suppressing here is
        # narrower than weakening the mixin's static type.
        manager = type(self)._default_manager  # type: ignore[attr-defined]
        if not hasattr(manager, "user_can"):
            raise TypeError(
                f"{type(self).__name__}._default_manager "
                f"({type(manager).__name__}) does not implement user_can(). "
                "Override user_can() on the model or ensure the manager "
                "extends BaseVisibilityManager / UserCanMixin."
            )
        return manager.user_can(
            user,
            self,
            permission,
            include_group_permissions=include_group_permissions,
        )
