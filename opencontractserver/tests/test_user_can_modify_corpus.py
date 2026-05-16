"""Tests for the canonical "can this user modify this corpus" matrix.

Historically this matrix was encoded in the ``user_can_modify_corpus`` helper
(``opencontractserver.utils.permissioning``). Phase A of permission-
centralization (issue #1655) deleted that helper and routes the same check
through ``corpus.user_can(user, PermissionTypes.UPDATE)`` — a single source
of truth that mirrors ``visible_to_user`` semantics and honors creator
status (which the legacy helper did via an explicit shortcut, and which
``_default_user_can`` now does as part of the standard rules).

These tests pin the contract under the new API: superuser, creator,
explicit guardian UPDATE (user- and group-level), and the no-access /
anonymous denial branches. Same assertions as before — only the call
site changed.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group
from django.test import TestCase
from guardian.shortcuts import assign_perm

from opencontractserver.corpuses.models import Corpus
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

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
        self.assertTrue(self.corpus.user_can(self.superuser, PermissionTypes.UPDATE))

    def test_creator_can_modify(self) -> None:
        self.assertTrue(self.corpus.user_can(self.owner, PermissionTypes.UPDATE))

    def test_user_with_explicit_update_can_modify(self) -> None:
        self.assertTrue(self.corpus.user_can(self.editor, PermissionTypes.UPDATE))

    def test_user_with_group_update_can_modify(self) -> None:
        self.assertTrue(self.corpus.user_can(self.group_member, PermissionTypes.UPDATE))

    def test_group_perm_ignored_when_disabled(self) -> None:
        """``include_group_permissions=False`` must skip group grants."""
        self.assertFalse(
            self.corpus.user_can(
                self.group_member,
                PermissionTypes.UPDATE,
                include_group_permissions=False,
            )
        )

    def test_outsider_cannot_modify(self) -> None:
        self.assertFalse(self.corpus.user_can(self.outsider, PermissionTypes.UPDATE))

    def test_anonymous_user_cannot_modify(self) -> None:
        self.assertFalse(self.corpus.user_can(AnonymousUser(), PermissionTypes.UPDATE))

    def test_none_user_cannot_modify(self) -> None:
        self.assertFalse(self.corpus.user_can(None, PermissionTypes.UPDATE))

    def test_accepts_user_id(self) -> None:
        """API accepts an integer/str id as well as a User instance."""
        self.assertTrue(self.corpus.user_can(self.owner.id, PermissionTypes.UPDATE))
        self.assertTrue(
            self.corpus.user_can(str(self.owner.id), PermissionTypes.UPDATE)
        )
        self.assertFalse(self.corpus.user_can(self.outsider.id, PermissionTypes.UPDATE))

    def test_dangling_id_returns_false(self) -> None:
        """Non-existent user ids must return False, not raise DoesNotExist."""
        dangling_id = 99_999_999
        self.assertFalse(User.objects.filter(id=dangling_id).exists())
        self.assertFalse(self.corpus.user_can(dangling_id, PermissionTypes.UPDATE))
        self.assertFalse(self.corpus.user_can(str(dangling_id), PermissionTypes.UPDATE))
