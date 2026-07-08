"""Regression guard for the singular ``<entity>(id:)`` IDOR bug class.

During the graphene→strawberry migration, several top-level singular
"fetch one object by global Relay ID" query fields were ported to call
``config.graphql.core.relay.get_node_from_global_id(...)``. That helper,
when the target type is registered WITHOUT a ``get_node`` / ``get_queryset``
hook, falls back to an UNFILTERED ``model._default_manager.get(pk=...)`` —
so any caller (even anonymous) could fetch a private object by forging its
global id (``base64("MessageType:<id>")``, trivially guessable).

The graphene originals filtered these through
``BaseService.get_or_none`` / ``filter_visible`` (or a service). This test
pins the fix mechanically: EVERY type resolved via
``get_node_from_global_id`` must carry a permission-aware registry hook, so
a future ported/added singular resolver cannot silently reintroduce the
unfiltered path.

It also exercises the runtime path for a representative, easy-to-fixture
type (``UserExport`` via ``userexport(id:)``) to prove a non-owner is
actually denied.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase
from graphql_relay import to_global_id

from config.graphql.core.relay import get_registry_entry
from config.graphql.schema import schema
from config.graphql.testing import Client
from opencontractserver.users.models import User, UserExport

# ``get_user_model()`` returns the same concrete ``User`` imported above; the
# alias keeps the ``User.objects`` calls below reading like the rest of the
# suite while the concrete import above is what mypy uses for annotations.
assert get_user_model() is User

_GRAPHQL_DIR = Path(__file__).resolve().parents[2] / "config" / "graphql"
_NODE_CALL = re.compile(
    r'get_node_from_global_id\(\s*info,\s*id,\s*only_type_name="([A-Za-z_]+)"\s*\)'
)


def _types_resolved_via_node_fallback() -> set[str]:
    names: set[str] = set()
    for path in _GRAPHQL_DIR.glob("*.py"):
        names.update(_NODE_CALL.findall(path.read_text()))
    return names


class SingularNodeIDORStructureTests(TestCase):
    def test_every_get_node_target_has_permission_hook(self) -> None:
        """No singular by-ID query may resolve through the unfiltered
        ``get_node_from_global_id`` fallback — each target type must register a
        ``get_node`` or ``get_queryset`` hook (the permission boundary)."""
        offenders = []
        targets = _types_resolved_via_node_fallback()
        # Sanity: the scan must actually find the singular resolvers.
        self.assertIn("MessageType", targets)
        self.assertIn("DatacellType", targets)
        for type_name in sorted(targets):
            entry = get_registry_entry(type_name)
            if entry is None or entry.model is None:
                # Non-model types never hit the ORM fallback.
                continue
            if entry.get_node is None and entry.get_queryset is None:
                offenders.append(type_name)
        self.assertEqual(
            offenders,
            [],
            "Singular by-ID query fields resolve these model-backed types via "
            "get_node_from_global_id with NO permission hook, so "
            "get_node_from_global_id falls back to an UNFILTERED .get(pk=) — an "
            "IDOR. Give each a get_node/get_queryset hook mirroring the graphene "
            f"resolver (BaseService.get_or_none / filter_visible): {offenders}",
        )


class SingularNodeIDORBehaviorTests(TestCase):
    owner: User
    attacker: User
    export: UserExport

    @classmethod
    def setUpTestData(cls) -> None:
        cls.owner = User.objects.create_user(username="owner", password="pw")
        cls.attacker = User.objects.create_user(username="attacker", password="pw")
        cls.export = UserExport.objects.create(creator=cls.owner, name="private export")

    def _fetch_userexport_as(self, user):
        return Client(schema).execute(
            """
            query ($id: ID!) {
              userexport(id: $id) { id }
            }
            """,
            variables={"id": to_global_id("UserExportType", self.export.pk)},
            context_value=type("Ctx", (), {"user": user})(),
        )

    def test_non_owner_cannot_fetch_private_userexport_by_id(self) -> None:
        result = self._fetch_userexport_as(self.attacker)
        self.assertIsNone(
            result.get("data", {}).get("userexport"),
            "attacker fetched the owner's private UserExport by forged global id",
        )

    def test_owner_can_fetch_own_userexport_by_id(self) -> None:
        result = self._fetch_userexport_as(self.owner)
        node = result.get("data", {}).get("userexport")
        self.assertIsNotNone(node, f"owner denied their own export: {result}")
        self.assertEqual(node["id"], to_global_id("UserExportType", self.export.pk))
