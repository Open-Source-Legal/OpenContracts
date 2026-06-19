"""AuthorityNamespace registry model (Phase 0)."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from opencontractserver.annotations.models import AuthorityNamespace
from opencontractserver.corpuses.models import Corpus
from opencontractserver.enrichment import constants as C
from opencontractserver.tests.factories import UserFactory


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

    def test_corpus_linked_namespace_cannot_be_global(self):
        """A corpus-linked namespace marked is_global would leak its aliases
        into every user's extraction regardless of corpus visibility — save()
        must refuse the incoherent combination."""
        user = UserFactory()
        corpus = Corpus.objects.create(title="Authority corpus", creator=user)
        with self.assertRaises(ValidationError):
            AuthorityNamespace.objects.create(
                prefix="corp-linked-global",
                display_name="Bad",
                authority_corpus=corpus,
                is_global=True,
            )
        # The corpus-scoped form (is_global=False) is accepted.
        ns = AuthorityNamespace.objects.create(
            prefix="corp-linked-scoped",
            display_name="Good",
            authority_corpus=corpus,
            is_global=False,
        )
        assert ns.authority_corpus_id == corpus.id
        assert ns.is_global is False

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


class AuthorityNamespaceFlushReseedTests(TestCase):
    """The ``post_migrate`` receiver must re-seed on the ``flush`` emission.

    The shipped namespaces are committed by migrations (``0082``/``0085``), so
    the rows live outside any test's transaction. Django's ``flush`` — run on
    every ``TransactionTestCase`` teardown — truncates
    ``annotations_authoritynamespace`` along with every other table
    (``serialized_rollback`` is ``False`` by default), so under
    ``pytest -n auto --dist loadscope`` any ``TransactionTestCase`` that runs
    before the seed/discovery ``TestCase``s on the same worker leaves them
    reading an empty registry — the exact CI failure this guards.

    The convergence hinges on a difference between the two commands that emit
    ``post_migrate``: ``migrate`` passes an ``apps`` kwarg (the historical
    project state) but ``flush`` does **not**
    (``django/core/management/commands/flush.py`` vs ``migrate.py``). This test
    emits the signal the apps-less way ``flush`` does and asserts the connected
    receiver still converges the registry — i.e. it does not bail when ``apps``
    is absent, mirroring Django's own ``create_contenttypes`` /
    ``create_permissions`` receivers.
    """

    def test_post_migrate_without_apps_reseeds(self):
        from django.apps import apps as global_apps
        from django.db.models.signals import post_migrate

        # Simulate the truncation a TransactionTestCase flush performs (the
        # delete rolls back with this TestCase's transaction).
        AuthorityNamespace.objects.all().delete()
        self.assertFalse(AuthorityNamespace.objects.exists())

        # Emit post_migrate exactly as flush.py does: sender=app_config and
        # NO `apps` kwarg. Pre-fix, the receiver returned early here.
        cfg = global_apps.get_app_config("annotations")
        post_migrate.send(
            sender=cfg,
            app_config=cfg,
            verbosity=0,
            interactive=False,
            using="default",
        )

        prefixes = set(C.AUTHORITY_PREFIX.values()) | {C.SEC_RULE_PREFIX}
        seeded = set(
            AuthorityNamespace.objects.filter(prefix__in=prefixes).values_list(
                "prefix", flat=True
            )
        )
        self.assertEqual(seeded, prefixes)
        self.assertTrue(AuthorityNamespace.objects.filter(prefix="dgcl").exists())
