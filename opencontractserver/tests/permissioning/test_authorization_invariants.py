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

    def test_crud_with_full_explicit_guardian_grants(self):
        """Guardian CRUD grant (CREATE+READ+UPDATE+DELETE) authorizes CRUD.

        The CRUD compound check requires all four base perms in the granted
        set. This is the main happy path; pinning it ensures a future
        refactor of the compound logic doesn't silently break it.
        """
        full_crud_user = User.objects.create_user(
            username="full_crud", email="crud@invariant.test", password="x"
        )
        set_permissions_for_obj_to_user(
            full_crud_user, self.private_corpus, [PermissionTypes.CRUD]
        )
        self.assertTrue(
            self.private_corpus.user_can(full_crud_user, PermissionTypes.CRUD),
            "CRUD grant should authorize CRUD compound check",
        )

    def test_crud_satisfied_by_public_read_plus_explicit_writes(self):
        """CRUD on a public corpus is satisfied by guardian write grants alone.

        SECURITY-ADJACENT invariant. A user with explicit guardian
        CREATE+UPDATE+DELETE on a public corpus should pass CRUD because
        ``get_users_permissions_for_obj`` folds ``is_public`` into the
        granted set as ``read_corpus``. If a refactor ever pulls the
        is_public substitution out of that helper without re-introducing
        it for compound checks, this test catches the regression.
        """
        writes_only_user = User.objects.create_user(
            username="writes_only", email="writes@invariant.test", password="x"
        )
        # Explicit guardian grants for CREATE + UPDATE + DELETE only —
        # READ comes from the corpus being public.
        set_permissions_for_obj_to_user(
            writes_only_user,
            self.public_corpus,
            [PermissionTypes.CREATE, PermissionTypes.UPDATE, PermissionTypes.DELETE],
        )
        self.assertTrue(
            self.public_corpus.user_can(writes_only_user, PermissionTypes.CRUD),
            "CRUD should pass when explicit writes + is_public cover READ",
        )

    def test_all_perm_requires_every_codename(self):
        """ALL requires the full 7-codename set; partial grants don't satisfy it."""
        partial_user = User.objects.create_user(
            username="partial_all", email="partall@invariant.test", password="x"
        )
        # Grant CRUD (4 perms) — missing COMMENT/PUBLISH/PERMISSION
        set_permissions_for_obj_to_user(
            partial_user, self.private_corpus, [PermissionTypes.CRUD]
        )
        self.assertFalse(
            self.private_corpus.user_can(partial_user, PermissionTypes.ALL),
            "ALL should require the full 7-codename set",
        )

        full_user = User.objects.create_user(
            username="full_all", email="fullall@invariant.test", password="x"
        )
        set_permissions_for_obj_to_user(
            full_user, self.private_corpus, [PermissionTypes.ALL]
        )
        self.assertTrue(
            self.private_corpus.user_can(full_user, PermissionTypes.ALL),
            "ALL grant should authorize ALL compound check",
        )

    def test_comment_publish_permission_grants_for_non_creator(self):
        """COMMENT / PUBLISH / PERMISSION are gated on explicit guardian grants."""
        scoped_user = User.objects.create_user(
            username="scoped", email="scoped@invariant.test", password="x"
        )
        set_permissions_for_obj_to_user(
            scoped_user,
            self.private_corpus,
            [
                PermissionTypes.COMMENT,
                PermissionTypes.PUBLISH,
                PermissionTypes.PERMISSION,
            ],
        )
        for perm in (
            PermissionTypes.COMMENT,
            PermissionTypes.PUBLISH,
            PermissionTypes.PERMISSION,
        ):
            self.assertTrue(
                self.private_corpus.user_can(scoped_user, perm),
                f"explicit {perm} grant did not authorize {perm}",
            )
        # Stranger lacking these grants gets denied for each.
        for perm in (
            PermissionTypes.COMMENT,
            PermissionTypes.PUBLISH,
            PermissionTypes.PERMISSION,
        ):
            self.assertFalse(
                self.private_corpus.user_can(self.stranger, perm),
                f"stranger gained {perm} on private corpus — leak!",
            )

    def test_queryset_user_can_matches_manager_and_instance(self):
        """``Corpus.objects.all().user_can(...)`` matches manager + instance surfaces.

        Catches divergence if a future refactor changes one surface and
        forgets the other (e.g. QuerySet override without the equivalent
        Manager change).
        """
        for user in (
            self.creator,
            self.shared_reader,
            self.shared_editor,
            self.stranger,
            AnonymousUser(),
        ):
            for corpus in (self.private_corpus, self.public_corpus):
                for perm in (
                    PermissionTypes.READ,
                    PermissionTypes.UPDATE,
                    PermissionTypes.DELETE,
                ):
                    via_queryset = Corpus.objects.all().user_can(user, corpus, perm)
                    via_manager = Corpus.objects.user_can(user, corpus, perm)
                    via_instance = corpus.user_can(user, perm)
                    self.assertEqual(
                        via_queryset,
                        via_manager,
                        f"queryset/manager disagree for "
                        f"user={getattr(user, 'username', 'anon')}, "
                        f"corpus={corpus.title}, perm={perm}",
                    )
                    self.assertEqual(
                        via_queryset,
                        via_instance,
                        f"queryset/instance disagree for "
                        f"user={getattr(user, 'username', 'anon')}, "
                        f"corpus={corpus.title}, perm={perm}",
                    )

    def test_str_and_int_user_id_inputs(self):
        """``user_can`` accepts user ids (int or str) and resolves them."""
        # int id should behave identically to the User instance.
        self.assertTrue(
            self.private_corpus.user_can(self.creator.id, PermissionTypes.READ)
        )
        self.assertEqual(
            self.private_corpus.user_can(self.creator.id, PermissionTypes.UPDATE),
            self.private_corpus.user_can(self.creator, PermissionTypes.UPDATE),
        )
        # str id (string-encoded int) should behave identically too.
        self.assertEqual(
            self.private_corpus.user_can(
                str(self.shared_reader.id), PermissionTypes.READ
            ),
            self.private_corpus.user_can(self.shared_reader, PermissionTypes.READ),
        )
        # Non-existent id is rejected without raising.
        self.assertFalse(
            self.private_corpus.user_can(999_999_999, PermissionTypes.READ),
            "non-existent user id should return False, not raise",
        )

    def test_creator_passes_compound_perms_without_explicit_grants(self):
        """Corpus creator passes CRUD and ALL via the creator short-circuit.

        The ``creator_id == user.id`` early-return in ``_default_user_can``
        fires BEFORE the compound-permission branches, so the corpus creator
        never needs explicit guardian CREATE/UPDATE/DELETE/COMMENT/PUBLISH/
        PERMISSION grants to satisfy ``CRUD`` or ``ALL``. This mirrors the
        deleted ``FolderService`` behavior (creators had implicit full
        access) and is the main happy path for owner-driven flows.
        """
        for perm in (PermissionTypes.CRUD, PermissionTypes.ALL):
            self.assertTrue(
                self.private_corpus.user_can(self.creator, perm),
                f"creator denied {perm} on their own corpus",
            )
            self.assertTrue(
                self.public_corpus.user_can(self.creator, perm),
                f"creator denied {perm} on their own public corpus",
            )

    def test_edit_is_alias_for_update(self):
        """``PermissionTypes.EDIT`` is treated identically to ``UPDATE``.

        Both ``_default_user_can`` and the legacy ``user_has_permission_for_obj``
        route EDIT through the ``update_<model>`` guardian codename. Pinning
        this prevents a silent divergence if either side ever forgets the
        alias.
        """
        for user, corpus in (
            (self.creator, self.private_corpus),
            (self.shared_editor, self.private_corpus),
            (self.shared_reader, self.private_corpus),
            (self.stranger, self.public_corpus),
        ):
            self.assertEqual(
                corpus.user_can(user, PermissionTypes.EDIT),
                corpus.user_can(user, PermissionTypes.UPDATE),
                f"EDIT/UPDATE disagree for "
                f"user={getattr(user, 'username', 'anon')}, "
                f"corpus={corpus.title}",
            )

    def test_user_can_raises_typeerror_when_default_manager_lacks_method(self):
        """``obj.user_can`` raises a clear TypeError if the manager surface is missing.

        Regression guard for the ``InstanceUserCanMixin`` contract: if a
        model whose ``_default_manager`` doesn't implement ``user_can``
        ever inherits the mixin, we want an eager, actionable error —
        not a confusing ``AttributeError`` deep in the auth flow.

        Verifies by mixing ``InstanceUserCanMixin`` into a tiny fake class
        whose ``_default_manager`` is a bare object lacking ``user_can``.
        This exercises the guard directly without disturbing Django's real
        manager registration for other tests in the class.
        """
        from opencontractserver.shared.user_can_mixin import InstanceUserCanMixin

        class _BareManager:
            pass

        class _FakeModel(InstanceUserCanMixin):
            _default_manager = _BareManager()

        with self.assertRaises(TypeError) as cm:
            _FakeModel().user_can(self.creator, PermissionTypes.READ)

        message = str(cm.exception)
        self.assertIn("user_can", message)
        self.assertIn("_BareManager", message)


class CorpusFolderDelegatesUserCanToCorpusTestCase(TransactionTestCase):
    """Pin that ``CorpusFolder.user_can(user, perm)`` delegates to the
    parent ``Corpus`` instead of running against the folder row's
    (non-existent) guardian rows.

    Folders don't allocate per-row object-permission rows; sharing is
    inherited from the corpus. Calling the default
    ``InstanceUserCanMixin.user_can`` against the folder would silently
    return ``False`` for shared readers because the folder has no
    guardian grants. The override on ``CorpusFolder`` redirects the
    check to ``self.corpus.user_can`` so the API surface answers
    consistently with the rest of the permissioning system.
    """

    def setUp(self):
        self.creator = User.objects.create_user(
            username="folder_creator", email="cf_creator@inv.test", password="x"
        )
        self.shared_reader = User.objects.create_user(
            username="folder_reader", email="cf_reader@inv.test", password="x"
        )
        self.stranger = User.objects.create_user(
            username="folder_stranger", email="cf_stranger@inv.test", password="x"
        )
        self.superuser = User.objects.create_superuser(
            username="folder_admin", email="cf_admin@inv.test", password="x"
        )

        # Private corpus shared with ``shared_reader`` but not ``stranger``.
        self.private_corpus = Corpus.objects.create(
            title="Folder Owner Corpus", creator=self.creator, is_public=False
        )
        set_permissions_for_obj_to_user(
            self.shared_reader, self.private_corpus, [PermissionTypes.READ]
        )

        from opencontractserver.corpuses.models import CorpusFolder

        # Folder under the private corpus. Note: no per-folder grants are
        # ever set — that's the whole point of the delegation contract.
        self.folder = CorpusFolder.objects.create(
            name="Top Level", corpus=self.private_corpus, creator=self.creator
        )

    def test_creator_can_read_folder(self):
        """Folder creator is the corpus creator, so READ delegates to
        ``Corpus.user_can`` and returns True via the creator short-circuit."""
        self.assertTrue(self.folder.user_can(self.creator, PermissionTypes.READ))

    def test_shared_reader_can_read_folder_via_corpus_grant(self):
        """Shared reader has READ on the corpus and zero grants on the
        folder; delegation to the corpus must answer True.

        Without the override, this test would fail (False) because the
        folder row has no guardian permissions.
        """
        self.assertTrue(self.folder.user_can(self.shared_reader, PermissionTypes.READ))

    def test_stranger_cannot_read_folder(self):
        """Stranger has no grant on the corpus, so the delegated check
        returns False."""
        self.assertFalse(self.folder.user_can(self.stranger, PermissionTypes.READ))

    def test_anonymous_cannot_read_private_folder(self):
        """Anonymous users without an is_public corpus get False (delegated)."""
        self.assertFalse(self.folder.user_can(AnonymousUser(), PermissionTypes.READ))

    def test_superuser_bypass_via_corpus_delegate(self):
        """Superusers pass through the corpus delegate's superuser bypass."""
        self.assertTrue(self.folder.user_can(self.superuser, PermissionTypes.READ))

    def test_public_corpus_makes_folder_public_for_read(self):
        """Flipping the corpus to ``is_public=True`` flips the delegated
        folder check too — confirming the answer tracks the corpus, not
        the folder's own ``is_public`` field."""
        public_corpus = Corpus.objects.create(
            title="Public Folder Corpus", creator=self.creator, is_public=True
        )
        from opencontractserver.corpuses.models import CorpusFolder

        public_folder = CorpusFolder.objects.create(
            name="Public Folder", corpus=public_corpus, creator=self.creator
        )
        self.assertTrue(
            public_folder.user_can(self.stranger, PermissionTypes.READ),
            "stranger should read folder when its corpus is public",
        )
        self.assertTrue(
            public_folder.user_can(AnonymousUser(), PermissionTypes.READ),
            "anonymous should read folder when its corpus is public",
        )

    def test_folder_user_can_matches_corpus_user_can_under_matrix(self):
        """For every (user, perm) pair, ``folder.user_can`` returns the
        same value as ``folder.corpus.user_can``. The override has no
        independent decision logic."""
        users = [
            self.creator,
            self.shared_reader,
            self.stranger,
            self.superuser,
            AnonymousUser(),
        ]
        perms = [
            PermissionTypes.READ,
            PermissionTypes.UPDATE,
            PermissionTypes.DELETE,
            PermissionTypes.CREATE,
            PermissionTypes.PERMISSION,
            PermissionTypes.PUBLISH,
            PermissionTypes.CRUD,
            PermissionTypes.ALL,
        ]
        for user in users:
            for perm in perms:
                folder_answer = self.folder.user_can(user, perm)
                corpus_answer = self.private_corpus.user_can(user, perm)
                self.assertEqual(
                    folder_answer,
                    corpus_answer,
                    f"delegation mismatch user={getattr(user, 'username', 'anon')} "
                    f"perm={perm}: folder={folder_answer}, corpus={corpus_answer}",
                )
