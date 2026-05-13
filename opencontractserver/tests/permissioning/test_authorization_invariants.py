"""
Authorization invariants — single source of truth pinning.

These tests pin the contract that the new ``Manager.user_can(user, instance,
permission)`` API and the existing ``Manager.visible_to_user(user)`` queryset
filter agree with each other for every visibility-managed model. Centralizing
permission logic in the Manager layer is only safe if filter and check answer
the same question; this module is the regression guard.

Step 0 scope: Corpus only. Subsequent migration phases extend this module to
cover Document, Annotation, Relationship, Note, Conversation, ChatMessage,
Extract, Analysis, etc.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TransactionTestCase

from opencontractserver.corpuses.models import Corpus
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class CorpusAuthorizationInvariantsTestCase(TransactionTestCase):
    """Pin the filter/check equivalence and no-silent-widening invariants for Corpus."""

    def setUp(self):
        self.creator = User.objects.create_user(
            username="creator", email="creator@invariant.test", password="x"
        )
        self.shared_reader = User.objects.create_user(
            username="shared_reader", email="reader@invariant.test", password="x"
        )
        self.shared_editor = User.objects.create_user(
            username="shared_editor", email="editor@invariant.test", password="x"
        )
        self.stranger = User.objects.create_user(
            username="stranger", email="stranger@invariant.test", password="x"
        )
        self.superuser = User.objects.create_superuser(
            username="invariant_admin", email="admin@invariant.test", password="x"
        )

        self.private_corpus = Corpus.objects.create(
            title="Private", creator=self.creator, is_public=False
        )
        self.public_corpus = Corpus.objects.create(
            title="Public", creator=self.creator, is_public=True
        )

        set_permissions_for_obj_to_user(
            self.shared_reader, self.private_corpus, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.shared_editor, self.private_corpus, [PermissionTypes.UPDATE]
        )

    def _assert_read_equivalence(self, user, corpus):
        check = corpus.user_can(user, PermissionTypes.READ)
        in_filter = Corpus.objects.visible_to_user(user).filter(pk=corpus.pk).exists()
        self.assertEqual(
            check,
            in_filter,
            f"user_can/visible_to_user disagree for "
            f"user={getattr(user, 'username', 'anon')}, corpus={corpus.title}: "
            f"check={check}, filter={in_filter}",
        )

    def test_read_equivalence_across_user_matrix(self):
        """For every (user, corpus), user_can(READ) == visible_to_user.exists()."""
        users = [
            self.creator,
            self.shared_reader,
            self.shared_editor,
            self.stranger,
            self.superuser,
            AnonymousUser(),
        ]
        for corpus in (self.private_corpus, self.public_corpus):
            for user in users:
                self._assert_read_equivalence(user, corpus)

    def test_manager_and_instance_surfaces_agree(self):
        """``Corpus.objects.user_can(...)`` and ``corpus.user_can(...)`` agree."""
        for user in (self.creator, self.shared_reader, self.stranger, AnonymousUser()):
            for corpus in (self.private_corpus, self.public_corpus):
                for perm in (
                    PermissionTypes.READ,
                    PermissionTypes.UPDATE,
                    PermissionTypes.DELETE,
                ):
                    via_manager = Corpus.objects.user_can(user, corpus, perm)
                    via_instance = corpus.user_can(user, perm)
                    self.assertEqual(
                        via_manager,
                        via_instance,
                        f"manager/instance disagree for "
                        f"user={getattr(user, 'username', 'anon')}, "
                        f"corpus={corpus.title}, perm={perm}",
                    )

    def test_superuser_bypass_all_permissions(self):
        """Superuser gets True for every permission on every corpus."""
        for corpus in (self.private_corpus, self.public_corpus):
            for perm in (
                PermissionTypes.READ,
                PermissionTypes.CREATE,
                PermissionTypes.UPDATE,
                PermissionTypes.DELETE,
                PermissionTypes.COMMENT,
                PermissionTypes.PUBLISH,
                PermissionTypes.PERMISSION,
                PermissionTypes.CRUD,
                PermissionTypes.ALL,
            ):
                self.assertTrue(
                    corpus.user_can(self.superuser, perm),
                    f"superuser denied {perm} on {corpus.title}",
                )

    def test_creator_gets_all_base_perms_without_explicit_grants(self):
        """Corpus creator has READ/UPDATE/DELETE without a guardian assignment."""
        for perm in (
            PermissionTypes.READ,
            PermissionTypes.UPDATE,
            PermissionTypes.DELETE,
        ):
            self.assertTrue(
                self.private_corpus.user_can(self.creator, perm),
                f"creator missing {perm} on their own corpus",
            )

    def test_is_public_grants_only_read_not_writes(self):
        """SECURITY: ``is_public=True`` must NOT grant UPDATE / DELETE / CREATE.

        This is the read/write asymmetry that the deleted
        ``FolderService.check_corpus_write_permission`` enforced
        (``corpus.is_public=True`` → readable, NOT editable). Pinning here
        ensures the centralization didn't widen writes.
        """
        for perm in (
            PermissionTypes.UPDATE,
            PermissionTypes.DELETE,
            PermissionTypes.CREATE,
        ):
            self.assertFalse(
                self.public_corpus.user_can(self.stranger, perm),
                f"stranger gained {perm} on public corpus via is_public — leak!",
            )
        # Sanity: stranger CAN read the public corpus.
        self.assertTrue(
            self.public_corpus.user_can(self.stranger, PermissionTypes.READ)
        )

    def test_anonymous_only_reads_public(self):
        """AnonymousUser reads only public corpuses; never writes anything."""
        anon = AnonymousUser()
        self.assertTrue(self.public_corpus.user_can(anon, PermissionTypes.READ))
        self.assertFalse(self.private_corpus.user_can(anon, PermissionTypes.READ))
        for perm in (
            PermissionTypes.UPDATE,
            PermissionTypes.DELETE,
            PermissionTypes.CREATE,
            PermissionTypes.PUBLISH,
        ):
            self.assertFalse(self.public_corpus.user_can(anon, perm))
            self.assertFalse(self.private_corpus.user_can(anon, perm))

    def test_explicit_read_does_not_grant_update(self):
        """Guardian READ-only grant does not bleed into UPDATE."""
        self.assertTrue(
            self.private_corpus.user_can(self.shared_reader, PermissionTypes.READ)
        )
        self.assertFalse(
            self.private_corpus.user_can(self.shared_reader, PermissionTypes.UPDATE)
        )

    def test_explicit_update_grant_works_for_non_creator(self):
        """Guardian UPDATE grant authorizes writes for non-creator non-superuser."""
        self.assertTrue(
            self.private_corpus.user_can(self.shared_editor, PermissionTypes.UPDATE)
        )

    def test_stranger_denied_all_on_private(self):
        """Non-shared, non-creator user gets nothing on a private corpus."""
        for perm in (
            PermissionTypes.READ,
            PermissionTypes.UPDATE,
            PermissionTypes.DELETE,
            PermissionTypes.CREATE,
        ):
            self.assertFalse(
                self.private_corpus.user_can(self.stranger, perm),
                f"stranger gained {perm} on private corpus — leak!",
            )

    def test_none_user_is_denied(self):
        """Passing ``None`` as the user is rejected, never raises."""
        for corpus in (self.private_corpus, self.public_corpus):
            for perm in (
                PermissionTypes.READ,
                PermissionTypes.UPDATE,
                PermissionTypes.DELETE,
            ):
                self.assertFalse(corpus.user_can(None, perm))
