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
        # Use a non-seeded prefix so the seed migration's "dgcl" row doesn't
        # cause the first create() to fail instead of the second.
        AuthorityNamespace.objects.create(prefix="tx-boc-unique", display_name="TBOC")
        with self.assertRaises(IntegrityError):
            AuthorityNamespace.objects.create(
                prefix="tx-boc-unique", display_name="dup"
            )


class AuthorityNamespaceSeedTests(TestCase):
    """The data migration seeds one namespace per shipped prefix."""

    def test_every_shipped_prefix_seeded(self):
        from opencontractserver.annotations.models import AuthorityNamespace

        prefixes = set(C.AUTHORITY_PREFIX.values()) | {C.SEC_RULE_PREFIX}
        for prefix in prefixes:
            ns = AuthorityNamespace.objects.filter(prefix=prefix).first()
            assert ns is not None, f"{prefix} not seeded"
            assert ns.is_global is True
            jur, typ = C.PREFIX_CLASSIFICATION[prefix]
            assert ns.jurisdiction == jur
            assert ns.authority_type == typ

    def test_dgcl_aliases_seeded(self):
        from opencontractserver.annotations.models import AuthorityNamespace

        ns = AuthorityNamespace.objects.get(prefix="dgcl")
        assert "dgcl" in ns.aliases
        assert "delaware general corporation law" in ns.aliases
