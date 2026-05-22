"""IDOR-safe lookup helper tests (Phase D, issue #1658).

Pins the contract for ``get_for_user_or_none``: missing pks and inaccessible
pks must both return ``None`` so callers can render a single unified error
message and never leak object existence via differential error text.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.corpuses.models import Corpus
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import (
    get_for_user_or_none,
    set_permissions_for_obj_to_user,
)

User = get_user_model()


class GetForUserOrNoneTestCase(TestCase):
    """Exercise the IDOR-safe lookup helper against the standard
    ``BaseVisibilityManager`` rules (creator, public, explicit grant,
    superuser, anonymous).
    """

    def setUp(self) -> None:
        self.owner = User.objects.create_user(username="d_owner", password="x")
        self.other = User.objects.create_user(username="d_other", password="x")
        self.superuser = User.objects.create_superuser(
            username="d_root", password="x", email="d_root@example.com"
        )
        self.private_corpus = Corpus.objects.create(
            title="Phase D Private",
            creator=self.owner,
            is_public=False,
        )
        self.public_corpus = Corpus.objects.create(
            title="Phase D Public",
            creator=self.owner,
            is_public=True,
        )

    def test_returns_instance_for_creator(self):
        result = get_for_user_or_none(Corpus, self.private_corpus.pk, self.owner)
        self.assertEqual(result, self.private_corpus)

    def test_returns_instance_for_public(self):
        result = get_for_user_or_none(Corpus, self.public_corpus.pk, self.other)
        self.assertEqual(result, self.public_corpus)

    def test_returns_none_for_missing_pk(self):
        bogus_pk = self.private_corpus.pk + 999_999
        self.assertIsNone(get_for_user_or_none(Corpus, bogus_pk, self.owner))

    def test_returns_none_for_inaccessible_pk(self):
        """IDOR contract: a pk the caller can't READ must look identical to a
        non-existent pk — both return None."""
        self.assertIsNone(
            get_for_user_or_none(Corpus, self.private_corpus.pk, self.other)
        )

    def test_explicit_read_grant_unlocks_lookup(self):
        set_permissions_for_obj_to_user(
            self.other, self.private_corpus, [PermissionTypes.READ]
        )
        result = get_for_user_or_none(Corpus, self.private_corpus.pk, self.other)
        self.assertEqual(result, self.private_corpus)

    def test_superuser_sees_everything(self):
        result = get_for_user_or_none(Corpus, self.private_corpus.pk, self.superuser)
        self.assertEqual(result, self.private_corpus)

    def test_none_user_returns_none_for_private(self):
        """Unauthenticated lookup of a private object collapses to None."""
        self.assertIsNone(get_for_user_or_none(Corpus, self.private_corpus.pk, None))

    def test_none_user_can_see_public(self):
        """Public objects remain visible to anonymous callers."""
        result = get_for_user_or_none(Corpus, self.public_corpus.pk, None)
        self.assertEqual(result, self.public_corpus)

    def test_invalid_pk_type_returns_none(self):
        """Garbage pk input (non-integer string on integer-pk model) returns
        None rather than raising — callers receive untrusted GraphQL ids and
        must not surface a 500 on malformed input."""
        self.assertIsNone(get_for_user_or_none(Corpus, "not-an-int", self.owner))

    def test_none_pk_returns_none(self):
        self.assertIsNone(get_for_user_or_none(Corpus, None, self.owner))

    def test_raises_on_model_without_visibility_manager(self):
        """Fail-loud guardrail: applying the helper to a model whose default
        manager lacks ``visible_to_user`` (i.e. a non-permissioned model) is a
        developer error and must surface as ``TypeError`` rather than
        silently bypassing IDOR protection.
        """
        from django.contrib.auth.models import Permission

        with self.assertRaises(TypeError):
            get_for_user_or_none(Permission, 1, self.owner)
