"""AuthorityNamespace registry model (Phase 0)."""

from django.db import IntegrityError
from django.test import TestCase

from opencontractserver.annotations.models import AuthorityNamespace
from opencontractserver.enrichment import constants as C


class AuthorityNamespaceModelTests(TestCase):
    def test_create_and_query(self):
        ns = AuthorityNamespace.objects.create(
            prefix="tx-boc",
            display_name="Texas Business Organizations Code",
            jurisdiction="us-tx",
            authority_type=C.AUTHORITY_TYPE_STATUTE,
            aliases=["tex. bus. orgs. code", "texas business organizations code"],
            is_global=True,
        )
        ns.refresh_from_db()
        assert ns.prefix == "tx-boc"
        assert "tex. bus. orgs. code" in ns.aliases
        assert ns.is_global is True

    def test_prefix_is_unique(self):
        AuthorityNamespace.objects.create(prefix="dgcl", display_name="DGCL")
        with self.assertRaises(IntegrityError):
            AuthorityNamespace.objects.create(prefix="dgcl", display_name="dup")
