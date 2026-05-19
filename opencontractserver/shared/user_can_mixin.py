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

Also exports :func:`resolve_user_for_user_can` — the shared int/str-id →
``User`` resolver used by every per-model ``user_can`` override and by the
``_default_user_can`` body. Centralising it here removes the ~40 lines of
duplicated resolution boilerplate that previously lived in every manager
(see Claude review on PR #1663) and ensures the int/str/None/AnonymousUser
contract stays consistent across surfaces.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from django.contrib.auth.models import AnonymousUser
    from django.db.models import Model

    from opencontractserver.types.enums import PermissionTypes
    from opencontractserver.users.models import User as UserModel

logger = logging.getLogger(__name__)


def resolve_user_for_user_can(user_val: Any) -> Any | None:
    """Normalise the ``user`` argument that every ``user_can`` override accepts.

    Returns:
        ``None`` when the caller passed ``None`` or an int/str id that doesn't
        resolve to a row (these are the "deny" cases — callers map ``None``
        to ``False``). Otherwise returns the resolved ``User`` instance (or
        ``AnonymousUser`` when that was passed in verbatim).

    Resolution rules — must match the legacy duplicated bodies in
    ``AnnotationManager.user_can``, ``NoteManager.user_can``,
    ``RelationshipManager.user_can`` and ``_default_user_can``:

    - ``None`` → ``None`` (caller maps to ``False``).
    - ``int`` / ``str`` → ``User.objects.get(id=user_val)``; both
      ``DoesNotExist`` and ``ValueError`` (raised when the str isn't a
      valid PK — e.g. ``""``, a GraphQL global id, or an arbitrary
      label) → ``None``. The legacy duplicated bodies caught
      ``DoesNotExist`` only and would propagate ``ValueError``; the
      unified contract treats both as a deny so callers can stay
      try-free.
    - Anything else (a ``User``, ``AnonymousUser``, or duck-typed user) →
      returned as-is.

    The ``str`` branch is defensive: GraphQL's PK serialisers sometimes hand
    back string-encoded integers and we want one resolver to handle both.
    """
    if user_val is None:
        return None
    if isinstance(user_val, (int, str)):
        # Lazy import — keeps this module out of the ``shared.Models`` ⇄
        # ``users.models`` startup chain at import time.
        from django.contrib.auth import get_user_model

        user_cls = get_user_model()
        try:
            return user_cls.objects.get(id=user_val)
        except user_cls.DoesNotExist:
            return None
        except ValueError:
            # ValueError on a user-id lookup usually signals a
            # programming bug (a caller passing a base64 GraphQL global
            # id like ``"VXNlcjox"`` instead of a raw PK, or some other
            # type-coercion miss). The unified contract still maps
            # this to a deny so the caller doesn't have to wrap every
            # site in try/except, but we surface the defect in logs
            # rather than swallowing it silently.
            logger.warning(
                "resolve_user_for_user_can: invalid user id %r — treating as deny. "
                "If you see this in production, a caller is passing a non-integer "
                "id (often a GraphQL global id from from_global_id missing) to "
                "user_can or user_has_permission_for_obj.",
                user_val,
            )
            return None
    return user_val


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
        user: int | str | UserModel | AnonymousUser | None,
        instance: Model,
        permission: PermissionTypes,
        *,
        include_group_permissions: bool = True,
        request: Any = None,
    ) -> bool:
        from opencontractserver.utils.permissioning import _default_user_can

        return _default_user_can(
            user,
            instance,
            permission,
            include_group_permissions=include_group_permissions,
            request=request,
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

    def __getstate__(self) -> Any:
        """Strip the Tier 1 permission cache before pickling.

        ``get_users_permissions_for_obj`` stashes a ``frozenset`` cache
        under ``INSTANCE_PERMS_CACHE_ATTR`` on the instance. If a model is
        passed verbatim into a Celery task (the well-known anti-pattern
        the project warns against in ``constants/permissioning.py``), the
        default pickle would carry that cache to the worker, where it
        could mask out-of-band guardian-row mutations made between
        ``apply_async`` and the worker picking the task up. Dropping the
        attribute at pickle time makes the footgun impossible rather than
        merely documented — the worker always re-reads from the DB.

        Calls ``super().__getstate__()`` so Django's
        ``Model.__getstate__`` (which copies ``_state`` defensively)
        still runs. The producer-side instance keeps the cache attribute
        intact; only the serialised state is scrubbed. Return type is
        ``Any`` because ``object.__getstate__`` may legitimately return
        ``None`` for instances without ``__dict__`` — pickle handles that
        case identically.

        MRO assumption: ``super().__getstate__()`` resolves to
        ``Model.__getstate__`` (Django 4.2+) or, failing that,
        ``object.__getstate__`` (Python 3.11+). Both define the method,
        so the call is safe as long as this mixin is composed with a
        ``Model`` subclass — the project's only consumer pattern. If
        anyone ever reuses ``InstanceUserCanMixin`` on a non-Model class
        under Python ≤3.10, ``super().__getstate__()`` will raise
        ``AttributeError`` and a fallback (``getattr(super(),
        "__getstate__", lambda: self.__dict__.copy())()``) would be
        required.
        """
        # Lazy import avoids pulling ``constants/permissioning`` into the
        # shared.Models ⇄ users.models startup chain.
        from opencontractserver.constants.permissioning import (
            INSTANCE_PERMS_CACHE_ATTR,
        )

        state = super().__getstate__()
        if isinstance(state, dict):
            state.pop(INSTANCE_PERMS_CACHE_ATTR, None)
        return state

    def user_can(
        self,
        user: int | str | UserModel | AnonymousUser | None,
        permission: PermissionTypes,
        *,
        include_group_permissions: bool = True,
        request: Any = None,
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
            request=request,
        )
