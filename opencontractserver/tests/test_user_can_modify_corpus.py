"""
Tests for ``opencontractserver.utils.permissioning.user_can_modify_corpus``.

The helper consolidates the inline
``user.is_superuser or corpus.creator_id == user.id or
user_has_permission_for_obj(user, corpus, UPDATE, ...)`` pattern from
``badge_mutations`` and ``document_mutations``. These tests pin the
contract so the helper stays a faithful drop-in replacement: superuser,
creator, explicit guardian UPDATE (user- and group-level), and the
no-access / anonymous denial branches.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group
from django.test import TestCase
from guardian.shortcuts import assign_perm

from opencontractserver.corpuses.models import Corpus
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import (
    set_permissions_for_obj_to_user,
    user_can_modify_corpus,
)

User = get_user_model()


class UserCanModifyCorpusTests(TestCase):
    """Pin the canonical "is_superuser OR creator OR UPDATE" matrix."""

    def setUp(self) -> None:
        self.owner = User.objects.create_user(username="owner", password="pw")
        self.editor = User.objects.create_user(username="editor", password="pw")
        self.outsider = User.objects.create_user(username="outsider", password="pw")
        self.group_member = User.objects.create_user(
            username="group_member", password="pw"
        )
        self.superuser = User.objects.create_superuser(
            username="root", password="pw", email="root@example.com"
        )

        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.owner)

        # Grant ``editor`` explicit guardian UPDATE on the corpus.
        set_permissions_for_obj_to_user(
            self.editor, self.corpus, [PermissionTypes.UPDATE]
        )

        # Grant a group UPDATE on the corpus, and put group_member in it.
        # Use the existing django-guardian helpers to avoid coupling the
        # test to internal grant code paths.
        self.update_group = Group.objects.create(name="corpus-editors")
        self.group_member.groups.add(self.update_group)
        assign_perm("update_corpus", self.update_group, self.corpus)

    def test_superuser_can_modify(self) -> None:
        self.assertTrue(user_can_modify_corpus(self.superuser, self.corpus))

    def test_creator_can_modify(self) -> None:
        self.assertTrue(user_can_modify_corpus(self.owner, self.corpus))

    def test_user_with_explicit_update_can_modify(self) -> None:
        self.assertTrue(user_can_modify_corpus(self.editor, self.corpus))

    def test_user_with_group_update_can_modify(self) -> None:
        self.assertTrue(user_can_modify_corpus(self.group_member, self.corpus))

    def test_group_perm_ignored_when_disabled(self) -> None:
        """``include_group_permissions=False`` must skip group grants."""
        self.assertFalse(
            user_can_modify_corpus(
                self.group_member, self.corpus, include_group_permissions=False
            )
        )

    def test_outsider_cannot_modify(self) -> None:
        self.assertFalse(user_can_modify_corpus(self.outsider, self.corpus))

    def test_anonymous_user_cannot_modify(self) -> None:
        self.assertFalse(user_can_modify_corpus(AnonymousUser(), self.corpus))

    def test_none_user_cannot_modify(self) -> None:
        self.assertFalse(user_can_modify_corpus(None, self.corpus))

    def test_accepts_user_id(self) -> None:
        """Helper accepts an integer/str id as well as a User instance."""
        self.assertTrue(user_can_modify_corpus(self.owner.id, self.corpus))
        self.assertTrue(user_can_modify_corpus(str(self.owner.id), self.corpus))
        self.assertFalse(user_can_modify_corpus(self.outsider.id, self.corpus))

    def test_dangling_id_returns_false(self) -> None:
        """Non-existent user ids must return False, not raise DoesNotExist."""
        # Pick a high id unlikely to exist; assert it really doesn't.
        dangling_id = 99_999_999
        self.assertFalse(User.objects.filter(id=dangling_id).exists())
        self.assertFalse(user_can_modify_corpus(dangling_id, self.corpus))
        self.assertFalse(user_can_modify_corpus(str(dangling_id), self.corpus))
