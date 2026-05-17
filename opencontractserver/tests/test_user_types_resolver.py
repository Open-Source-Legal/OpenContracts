"""Tests for :func:`opencontractserver.users.types.resolve_user_or_anon`.

Pins the contract of the shared user-id → user-or-anonymous resolver
that bridges ``AgentConfig.user_id`` / persisted creator IDs into
service-layer calls expecting an actual model instance. Previously a
private function on ``llms.agents.core_agents`` (``_resolve_user_or_anon``);
moved here so other service surfaces consume the same helper without
re-implementing it.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase

from opencontractserver.users.types import resolve_user_or_anon

User = get_user_model()


class ResolveUserOrAnonTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="resolver_user",
            email="ru@test.test",
            password="x",
        )

    def test_returns_user_for_existing_id(self) -> None:
        resolved = resolve_user_or_anon(self.user.id)
        self.assertEqual(resolved.pk, self.user.pk)
        self.assertTrue(resolved.is_authenticated)

    def test_returns_anonymous_for_none(self) -> None:
        resolved = resolve_user_or_anon(None)
        self.assertIsInstance(resolved, AnonymousUser)
        self.assertFalse(resolved.is_authenticated)

    def test_raises_user_does_not_exist_for_unknown_id(self) -> None:
        # The helper deliberately does NOT swallow ``DoesNotExist`` —
        # callers feeding stale ids (e.g. a persisted user_id whose row
        # has been deleted) should crash visibly, not silently downgrade
        # to anonymous. Anonymous is reserved for the explicit ``None``
        # case.
        with self.assertRaises(User.DoesNotExist):
            resolve_user_or_anon(999_999_999)
