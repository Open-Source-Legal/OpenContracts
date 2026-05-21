# Service Layer Centralization — Phase 1 (Foundation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the shared `BaseService` foundation and standardized return/lookup conventions that every per-app service package in later phases will inherit.

**Architecture:** A new `opencontractserver/shared/services/` package holds (a) `conventions.py` — the `ServiceResult` write-result envelope and the IDOR-safe `get_for_user_or_none` lookup; and (b) `base.py` — `BaseService`, a staticmethod-based base class providing IDOR-safe lookup, permission-filtered queryset access, a uniform permission gate, and structured logging. No existing callers are migrated in this phase; it ships the primitives only, verified by unit tests.

**Tech Stack:** Python 3.12, Django 4.x, `django-guardian` permissions, existing `user_can` / `visible_to_user` manager API (`opencontractserver/shared/Managers.py`, `shared/QuerySets.py`, `shared/user_can_mixin.py`), `PermissionTypes` enum (`opencontractserver/types/enums.py`).

---

## Background

This is Phase 1 of the roadmap in `docs/refactor_plans/2026-05-19-service-layer-centralization-design.md`. Read that design doc first — §5.3 ("`BaseService` — the centralized machinery") defines what this phase builds.

Key facts about the existing code this phase depends on:

- **Permission checks.** Managers expose `Model.objects.user_can(user, instance, permission, *, include_group_permissions=True, request=None) -> bool`. `BaseVisibilityManager` and `PermissionedTreeQuerySet` both provide it via `UserCanMixin`. `Corpus.objects.user_can(...)` works (confirmed by `test_corpus_objs_service.py`).
- **Visibility filtering.** `Model.objects.visible_to_user(user) -> QuerySet` returns only rows the user may READ. The invariant `visible_to_user(u) ⟺ user_can(u, READ)` is pinned by `test_authorization_invariants`.
- **`PermissionTypes`** is a `str` enum (`opencontractserver/types/enums.py`): `READ`, `CREATE`, `UPDATE`, `EDIT`, `DELETE`, `COMMENT`, `PERMISSION`, `PUBLISH`, `CRUD`, `ALL`. Each member has a `.value` (e.g. `PermissionTypes.READ.value == "READ"`).
- **Existing services** (`DocumentService`, `CorpusObjsService`) are classmethod/staticmethod-based with no per-call instance. New services follow the same style.
- **Corpus creation in tests:** `Corpus.objects.create(title="X", creator=user, is_public=False)`. The creator automatically passes `corpus.user_can(creator, READ)` via the creator branch — no explicit guardian grant needed. A different user does NOT see it via `visible_to_user`.

Run backend tests inside Docker. The full suite takes 30+ minutes — this plan only ever runs the single new test module.

---

## File Structure

- Create: `opencontractserver/shared/services/__init__.py` — package root, re-exports `BaseService`, `ServiceResult`, `get_for_user_or_none`.
- Create: `opencontractserver/shared/services/conventions.py` — `ServiceResult` dataclass + `get_for_user_or_none` function.
- Create: `opencontractserver/shared/services/base.py` — `BaseService` class.
- Create: `opencontractserver/tests/test_base_service.py` — unit tests for all of the above.

`opencontractserver/shared/` already exists as a package (`__init__.py` present). The new `services/` subdirectory needs its own `__init__.py` (Task 5).

---

## Task 1: `ServiceResult` write-result envelope

**Files:**
- Create: `opencontractserver/shared/services/conventions.py`
- Test: `opencontractserver/tests/test_base_service.py`

- [x] **Step 1: Write the failing test**

Create `opencontractserver/tests/test_base_service.py`:

```python
"""Unit tests for the Phase 1 service-layer foundation.

Covers ``ServiceResult`` (no DB), ``get_for_user_or_none`` (DB), and
``BaseService`` (DB). See
docs/refactor_plans/2026-05-19-service-layer-phase1-foundation-plan.md.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from opencontractserver.shared.services.conventions import ServiceResult

User = get_user_model()


class TestServiceResult(SimpleTestCase):
    """SCENARIO: ServiceResult is the uniform write-operation envelope.

    BUSINESS RULE: a result is successful exactly when its error string is
    empty; it also tuple-unpacks to ``(value, error)`` so legacy callers
    written against the ``(obj, error)`` convention keep working.
    """

    def test_success_has_value_and_is_ok(self):
        result = ServiceResult.success(42)
        self.assertEqual(result.value, 42)
        self.assertEqual(result.error, "")
        self.assertTrue(result.ok)

    def test_failure_has_error_and_is_not_ok(self):
        result = ServiceResult.failure("boom")
        self.assertIsNone(result.value)
        self.assertEqual(result.error, "boom")
        self.assertFalse(result.ok)

    def test_failure_rejects_empty_error(self):
        with self.assertRaises(ValueError):
            ServiceResult.failure("")

    def test_tuple_unpacking_yields_value_then_error(self):
        value, error = ServiceResult.success("doc")
        self.assertEqual(value, "doc")
        self.assertEqual(error, "")
        value, error = ServiceResult.failure("nope")
        self.assertIsNone(value)
        self.assertEqual(error, "nope")
```

- [x] **Step 2: Run test to verify it fails**

Run: `docker compose -f test.yml run --rm django python manage.py test opencontractserver.tests.test_base_service.TestServiceResult --keepdb`
Expected: FAIL — `ModuleNotFoundError: No module named 'opencontractserver.shared.services'`

- [x] **Step 3: Write minimal implementation**

Create `opencontractserver/shared/services/conventions.py`:

```python
"""Shared return-type conventions and IDOR-safe lookup for the service layer.

Every service in ``opencontractserver/*/services/`` returns results through
``ServiceResult`` (write operations) or permission-filtered querysets /
``None`` (read operations). This module is the single home for those
conventions so the service layer presents one uniform surface to GraphQL
resolvers, MCP tools, REST views, and Celery tasks.

Part of the Phase 1 service-layer foundation — see
docs/refactor_plans/2026-05-19-service-layer-centralization-design.md.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class ServiceResult(Generic[T]):
    """Uniform envelope returned by service-layer write operations.

    ``ok`` is derived: a result is successful exactly when ``error`` is
    empty. Construct via the ``success`` / ``failure`` classmethods rather
    than the bare constructor so intent is explicit at the call site.

    Tuple-unpacking is supported (``value, error = result``) so callers
    written against the legacy ``(obj, error)`` / ``(ok, error)``
    convention keep working while the service layer is migrated.
    """

    value: T | None = None
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error

    @classmethod
    def success(cls, value: T) -> "ServiceResult[T]":
        return cls(value=value, error="")

    @classmethod
    def failure(cls, error: str) -> "ServiceResult[T]":
        if not error:
            raise ValueError(
                "ServiceResult.failure requires a non-empty error message"
            )
        return cls(value=None, error=error)

    def __iter__(self) -> Iterator[Any]:
        """Yield ``(value, error)`` for backward-compatible tuple unpacking."""
        yield self.value
        yield self.error
```

- [x] **Step 4: Run test to verify it passes**

Run: `docker compose -f test.yml run --rm django python manage.py test opencontractserver.tests.test_base_service.TestServiceResult --keepdb`
Expected: PASS — 4 tests OK

- [x] **Step 5: Commit**

```bash
git add opencontractserver/shared/services/conventions.py opencontractserver/tests/test_base_service.py
git commit -m "Add ServiceResult write-result envelope (service layer Phase 1)"
```

---

## Task 2: `get_for_user_or_none` IDOR-safe lookup

**Files:**
- Modify: `opencontractserver/shared/services/conventions.py`
- Test: `opencontractserver/tests/test_base_service.py`

- [x] **Step 1: Write the failing test**

Append to `opencontractserver/tests/test_base_service.py`:

```python
from opencontractserver.corpuses.models import Corpus
from opencontractserver.shared.services.conventions import get_for_user_or_none
from opencontractserver.types.enums import PermissionTypes


class TestGetForUserOrNone(TestCase):
    """SCENARIO: get_for_user_or_none is the IDOR-safe single-object lookup.

    BUSINESS RULE: it returns the instance only when it exists AND the user
    holds the requested permission. Every other case — not-found,
    permission-denied, malformed pk — returns None, so a caller cannot
    distinguish "does not exist" from "exists but forbidden".
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.other = User.objects.create_user(
            username="other", email="other@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Owned Corpus", creator=self.owner, is_public=False
        )

    def test_owner_gets_instance(self):
        result = get_for_user_or_none(Corpus, self.corpus.pk, self.owner)
        self.assertEqual(result, self.corpus)

    def test_other_user_gets_none(self):
        result = get_for_user_or_none(Corpus, self.corpus.pk, self.other)
        self.assertIsNone(result)

    def test_nonexistent_pk_gets_none(self):
        result = get_for_user_or_none(Corpus, 999999999, self.owner)
        self.assertIsNone(result)

    def test_malformed_pk_gets_none(self):
        result = get_for_user_or_none(Corpus, "not-a-pk", self.owner)
        self.assertIsNone(result)

    def test_permission_argument_is_honored(self):
        # Owner has full CRUD on their own corpus, so UPDATE also resolves.
        result = get_for_user_or_none(
            Corpus, self.corpus.pk, self.owner, PermissionTypes.UPDATE
        )
        self.assertEqual(result, self.corpus)
```

- [x] **Step 2: Run test to verify it fails**

Run: `docker compose -f test.yml run --rm django python manage.py test opencontractserver.tests.test_base_service.TestGetForUserOrNone --keepdb`
Expected: FAIL — `ImportError: cannot import name 'get_for_user_or_none'`

- [x] **Step 3: Write minimal implementation**

Append to `opencontractserver/shared/services/conventions.py`:

```python


def get_for_user_or_none(
    model: Any,
    pk: Any,
    user: Any,
    permission: Any = None,
    *,
    request: Any = None,
) -> Any | None:
    """IDOR-safe single-object lookup.

    Returns the instance only when it exists AND ``user`` holds
    ``permission`` on it. Returns ``None`` for every other case —
    not-found, permission-denied, or a malformed ``pk`` — so callers
    cannot distinguish "does not exist" from "exists but forbidden"
    (the IDOR-prevention contract from CLAUDE.md).

    The model's manager MUST implement ``user_can`` — i.e. it extends
    ``BaseVisibilityManager`` / ``UserCanMixin`` or is built from
    ``PermissionedTreeQuerySet``. Models with a plain manager (e.g.
    ``Notification``, which uses a simple ownership model) are not
    supported here; gate those with their own ownership filter.

    Args:
        model: The Django model class to look up.
        pk: Primary key of the desired row.
        user: Requesting user (``User``, ``AnonymousUser``, id, or None).
        permission: Required ``PermissionTypes`` — defaults to ``READ``.
        request: Optional request object, threaded into ``user_can`` so
            the request-scoped permission cache is shared.

    Returns:
        The instance, or ``None``.
    """
    from opencontractserver.types.enums import PermissionTypes

    if permission is None:
        permission = PermissionTypes.READ

    try:
        instance = model.objects.get(pk=pk)
    except model.DoesNotExist:
        return None
    except (ValueError, TypeError):
        # Malformed pk (e.g. a GraphQL global id passed instead of a raw
        # PK). Treat as not-found rather than raising.
        return None

    if model.objects.user_can(user, instance, permission, request=request):
        return instance
    return None
```

No import-block change is needed — `Any`, `Generic`, and `TypeVar` are already imported from Task 1, and `PermissionTypes` is imported lazily inside the function body.

- [x] **Step 4: Run test to verify it passes**

Run: `docker compose -f test.yml run --rm django python manage.py test opencontractserver.tests.test_base_service.TestGetForUserOrNone --keepdb`
Expected: PASS — 5 tests OK

- [x] **Step 5: Commit**

```bash
git add opencontractserver/shared/services/conventions.py opencontractserver/tests/test_base_service.py
git commit -m "Add IDOR-safe get_for_user_or_none lookup (service layer Phase 1)"
```

---

## Task 3: `BaseService` with `get_or_none` and `filter_visible`

**Files:**
- Create: `opencontractserver/shared/services/base.py`
- Test: `opencontractserver/tests/test_base_service.py`

- [x] **Step 1: Write the failing test**

Append to `opencontractserver/tests/test_base_service.py`:

```python
from opencontractserver.shared.services.base import BaseService


class TestBaseServiceLookup(TestCase):
    """SCENARIO: BaseService exposes the shared fetch primitives.

    BUSINESS RULE: ``get_or_none`` is the IDOR-safe single-object lookup
    and ``filter_visible`` returns the permission-filtered queryset — both
    delegate to the existing manager API so a subclass never re-implements
    permission logic.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="bs_owner", email="bs_owner@test.com", password="test"
        )
        self.other = User.objects.create_user(
            username="bs_other", email="bs_other@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="BaseService Corpus", creator=self.owner, is_public=False
        )

    def test_get_or_none_returns_instance_for_owner(self):
        self.assertEqual(
            BaseService.get_or_none(Corpus, self.corpus.pk, self.owner),
            self.corpus,
        )

    def test_get_or_none_returns_none_for_other_user(self):
        self.assertIsNone(
            BaseService.get_or_none(Corpus, self.corpus.pk, self.other)
        )

    def test_filter_visible_includes_owned_corpus(self):
        visible_ids = set(
            BaseService.filter_visible(Corpus, self.owner).values_list(
                "pk", flat=True
            )
        )
        self.assertIn(self.corpus.pk, visible_ids)

    def test_filter_visible_excludes_corpus_for_other_user(self):
        visible_ids = set(
            BaseService.filter_visible(Corpus, self.other).values_list(
                "pk", flat=True
            )
        )
        self.assertNotIn(self.corpus.pk, visible_ids)
```

- [x] **Step 2: Run test to verify it fails**

Run: `docker compose -f test.yml run --rm django python manage.py test opencontractserver.tests.test_base_service.TestBaseServiceLookup --keepdb`
Expected: FAIL — `ModuleNotFoundError: No module named 'opencontractserver.shared.services.base'`

- [x] **Step 3: Write minimal implementation**

Create `opencontractserver/shared/services/base.py`:

```python
"""``BaseService`` — shared machinery for the OpenContracts service layer.

Every concrete service (``opencontractserver/*/services/*.py``) inherits
``BaseService``. It centralises the cross-cutting behaviour so per-model
services stay small and contain only model-specific fetch/mutate logic:

- IDOR-safe single-object lookup (``get_or_none``)
- permission-filtered queryset access (``filter_visible``)
- a uniform permission gate for write operations (``require_permission``)
- structured action logging (``log_action``)

Services are classmethod/staticmethod based — there is no per-call service
instance. Subclasses call ``cls.get_or_none(...)`` etc. directly.

Part of the Phase 1 service-layer foundation — see
docs/refactor_plans/2026-05-19-service-layer-centralization-design.md.
"""

from __future__ import annotations

import logging
from typing import Any

from opencontractserver.shared.services.conventions import get_for_user_or_none

logger = logging.getLogger(__name__)


class BaseService:
    """Base class for all service-layer services."""

    @staticmethod
    def get_or_none(
        model: Any,
        pk: Any,
        user: Any,
        permission: Any = None,
        *,
        request: Any = None,
    ) -> Any | None:
        """IDOR-safe single-object lookup.

        Thin delegate to ``conventions.get_for_user_or_none`` — see that
        function for the full contract. ``permission`` defaults to
        ``PermissionTypes.READ`` when omitted.
        """
        return get_for_user_or_none(
            model, pk, user, permission, request=request
        )

    @staticmethod
    def filter_visible(model: Any, user: Any) -> Any:
        """Return ``model`` rows visible to ``user`` (permission-filtered).

        Delegates to the model's ``visible_to_user`` manager method, which
        encodes the per-model READ visibility rules.
        """
        return model.objects.visible_to_user(user)
```

- [x] **Step 4: Run test to verify it passes**

Run: `docker compose -f test.yml run --rm django python manage.py test opencontractserver.tests.test_base_service.TestBaseServiceLookup --keepdb`
Expected: PASS — 4 tests OK

- [x] **Step 5: Commit**

```bash
git add opencontractserver/shared/services/base.py opencontractserver/tests/test_base_service.py
git commit -m "Add BaseService with get_or_none and filter_visible (service layer Phase 1)"
```

---

## Task 4: `BaseService.require_permission`

**Files:**
- Modify: `opencontractserver/shared/services/base.py`
- Test: `opencontractserver/tests/test_base_service.py`

- [x] **Step 1: Write the failing test**

Append to `opencontractserver/tests/test_base_service.py`:

```python
class TestBaseServiceRequirePermission(TestCase):
    """SCENARIO: require_permission is the uniform write-operation gate.

    BUSINESS RULE: it returns an empty string when the user holds the
    permission, and a human-readable denial string otherwise — so a
    service can feed the return value straight into ServiceResult.failure.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="rp_owner", email="rp_owner@test.com", password="test"
        )
        self.other = User.objects.create_user(
            username="rp_other", email="rp_other@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="RequirePermission Corpus", creator=self.owner, is_public=False
        )

    def test_owner_passes_returns_empty_string(self):
        error = BaseService.require_permission(
            self.corpus, self.owner, PermissionTypes.UPDATE
        )
        self.assertEqual(error, "")

    def test_other_user_denied_returns_nonempty_error(self):
        error = BaseService.require_permission(
            self.corpus, self.other, PermissionTypes.UPDATE
        )
        self.assertNotEqual(error, "")
        self.assertIn("Permission denied", error)

    def test_custom_error_message_is_used_on_denial(self):
        error = BaseService.require_permission(
            self.corpus,
            self.other,
            PermissionTypes.UPDATE,
            error_message="You cannot edit this corpus",
        )
        self.assertEqual(error, "You cannot edit this corpus")

    def test_custom_error_message_ignored_on_success(self):
        error = BaseService.require_permission(
            self.corpus,
            self.owner,
            PermissionTypes.UPDATE,
            error_message="You cannot edit this corpus",
        )
        self.assertEqual(error, "")
```

- [x] **Step 2: Run test to verify it fails**

Run: `docker compose -f test.yml run --rm django python manage.py test opencontractserver.tests.test_base_service.TestBaseServiceRequirePermission --keepdb`
Expected: FAIL — `AttributeError: type object 'BaseService' has no attribute 'require_permission'`

- [x] **Step 3: Write minimal implementation**

Append a new method to the `BaseService` class in `opencontractserver/shared/services/base.py` (after `filter_visible`):

```python

    @staticmethod
    def require_permission(
        instance: Any,
        user: Any,
        permission: Any,
        *,
        request: Any = None,
        error_message: str | None = None,
    ) -> str:
        """Return ``""`` when ``user`` holds ``permission`` on ``instance``.

        Otherwise return a human-readable denial string. Services use the
        return value directly as the ``error`` field of a
        ``ServiceResult``::

            error = cls.require_permission(corpus, user, PermissionTypes.UPDATE)
            if error:
                return ServiceResult.failure(error)

        ``error_message`` overrides the default denial string; it is
        ignored when the check passes.

        The model's manager MUST implement ``user_can`` (see
        ``conventions.get_for_user_or_none`` for the same contract).
        """
        manager = type(instance).objects
        if manager.user_can(user, instance, permission, request=request):
            return ""
        if error_message is not None:
            return error_message
        return (
            f"Permission denied: cannot {permission.value} "
            f"this {type(instance).__name__}"
        )
```

- [x] **Step 4: Run test to verify it passes**

Run: `docker compose -f test.yml run --rm django python manage.py test opencontractserver.tests.test_base_service.TestBaseServiceRequirePermission --keepdb`
Expected: PASS — 4 tests OK

- [x] **Step 5: Commit**

```bash
git add opencontractserver/shared/services/base.py opencontractserver/tests/test_base_service.py
git commit -m "Add BaseService.require_permission write gate (service layer Phase 1)"
```

---

## Task 5: `BaseService.log_action` and package re-exports

**Files:**
- Modify: `opencontractserver/shared/services/base.py`
- Create: `opencontractserver/shared/services/__init__.py`
- Test: `opencontractserver/tests/test_base_service.py`

- [x] **Step 1: Write the failing test**

Append to `opencontractserver/tests/test_base_service.py`:

```python
class TestBaseServiceLogAction(TestCase):
    """SCENARIO: log_action emits a structured who-did-what log line.

    BUSINESS RULE: every service mutation logs the action, the object, and
    the acting user in one consistent format.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="log_owner", email="log_owner@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Log Corpus", creator=self.owner, is_public=False
        )

    def test_log_action_emits_info_line_with_action_model_and_user(self):
        with self.assertLogs(
            "opencontractserver.shared.services.base", level="INFO"
        ) as captured:
            BaseService.log_action("Created", self.corpus, self.owner)
        joined = "\n".join(captured.output)
        self.assertIn("Created", joined)
        self.assertIn("Corpus", joined)
        self.assertIn(str(self.corpus.pk), joined)
        self.assertIn(str(self.owner.id), joined)

    def test_log_action_includes_extra_kwargs(self):
        with self.assertLogs(
            "opencontractserver.shared.services.base", level="INFO"
        ) as captured:
            BaseService.log_action(
                "Updated", self.corpus, self.owner, field="title"
            )
        self.assertIn("field=title", "\n".join(captured.output))


class TestServicesPackageExports(SimpleTestCase):
    """SCENARIO: the package root re-exports the shared building blocks.

    BUSINESS RULE: callers import from the package
    (``from opencontractserver.shared.services import BaseService``) so the
    individual module layout can change without breaking imports.
    """

    def test_package_reexports_public_names(self):
        from opencontractserver.shared.services import (
            BaseService as ExportedBaseService,
        )
        from opencontractserver.shared.services import (
            ServiceResult as ExportedServiceResult,
        )
        from opencontractserver.shared.services import (
            get_for_user_or_none as exported_lookup,
        )

        self.assertIs(ExportedBaseService, BaseService)
        self.assertIs(ExportedServiceResult, ServiceResult)
        self.assertTrue(callable(exported_lookup))
```

- [x] **Step 2: Run test to verify it fails**

Run: `docker compose -f test.yml run --rm django python manage.py test opencontractserver.tests.test_base_service.TestBaseServiceLogAction opencontractserver.tests.test_base_service.TestServicesPackageExports --keepdb`
Expected: FAIL — `AttributeError: type object 'BaseService' has no attribute 'log_action'`

- [x] **Step 3: Write minimal implementation**

Append a new method to the `BaseService` class in `opencontractserver/shared/services/base.py` (after `require_permission`):

```python

    @staticmethod
    def log_action(action: str, instance: Any, user: Any, **extra: Any) -> None:
        """Emit a structured who-did-what-to-which-object log line.

        Args:
            action: Verb describing the operation (e.g. ``"Created"``).
            instance: The affected model instance.
            user: The acting user.
            **extra: Additional ``key=value`` context appended to the line.
        """
        details = " ".join(f"{key}={value}" for key, value in extra.items())
        logger.info(
            "%s %s(id=%s) by user=%s %s",
            action,
            type(instance).__name__,
            getattr(instance, "pk", None),
            getattr(user, "id", user),
            details,
        )
```

Create `opencontractserver/shared/services/__init__.py`:

```python
"""Service-layer package root.

Re-exports the shared building blocks so services and their callers can
``from opencontractserver.shared.services import BaseService, ServiceResult``.

Part of the Phase 1 service-layer foundation — see
docs/refactor_plans/2026-05-19-service-layer-centralization-design.md.
"""

from opencontractserver.shared.services.base import BaseService
from opencontractserver.shared.services.conventions import (
    ServiceResult,
    get_for_user_or_none,
)

__all__ = ["BaseService", "ServiceResult", "get_for_user_or_none"]
```

- [x] **Step 4: Run the full test module to verify everything passes**

Run: `docker compose -f test.yml run --rm django python manage.py test opencontractserver.tests.test_base_service --keepdb`
Expected: PASS — all tests OK (4 + 5 + 4 + 4 + 2 + 1 = 20 tests)

- [x] **Step 5: Run pre-commit and commit**

Run pre-commit first (CLAUDE.md baseline rule — black, isort, flake8 must pass):

```bash
pre-commit run --files \
  opencontractserver/shared/services/__init__.py \
  opencontractserver/shared/services/base.py \
  opencontractserver/shared/services/conventions.py \
  opencontractserver/tests/test_base_service.py
```

Expected: all hooks pass (or auto-fix formatting — if files are modified, re-stage them). Then:

```bash
git add opencontractserver/shared/services/__init__.py \
  opencontractserver/shared/services/base.py \
  opencontractserver/tests/test_base_service.py
git commit -m "Add BaseService.log_action and service package re-exports (service layer Phase 1)"
```

---

## Self-Review Notes

- **Spec coverage:** This plan implements design doc §5.3 ("`BaseService` — the centralized machinery") and §6 Phase 1 ("Foundation"). The §5.3 bullets map as: request threading → `request=` kwarg on `get_or_none` / `require_permission`; return conventions → `ServiceResult`; IDOR-safe lookup → `get_for_user_or_none` / `get_or_none`; permission delegation → `require_permission` / `filter_visible`; logging convention → `log_action`. Transaction convention is intentionally NOT a `BaseService` helper — services use `transaction.atomic()` directly (matching existing `DocumentService` / `CorpusObjsService`); this is noted as a deliberate scope decision, not a gap.
- **No callers migrated:** Phase 1 ships primitives only. `DocumentService` / `CorpusObjsService` are migrated in Phases 2–3.
- **Type consistency:** `get_for_user_or_none(model, pk, user, permission=None, *, request=None)` — `permission=None` resolves to `PermissionTypes.READ` inside the body (avoids importing the enum at module top-level, consistent with the lazy-import style used across the codebase). `BaseService.get_or_none` mirrors that signature exactly and passes `permission` straight through. `require_permission(instance, user, permission, *, request, error_message)` takes a required `permission`. `ServiceResult.success`/`failure`/`ok`/`value`/`error` names are used identically in tests and implementation.
- **Test count:** 20 tests across 6 test classes — `TestServiceResult` (4), `TestGetForUserOrNone` (5), `TestBaseServiceLookup` (4), `TestBaseServiceRequirePermission` (4), `TestBaseServiceLogAction` (2), `TestServicesPackageExports` (1).
