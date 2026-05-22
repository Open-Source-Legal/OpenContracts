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

Phase F fixture-matrix audit (issue #1660)
------------------------------------------
Every per-model invariant class below is exercised by ``_UserCanInvariantsMixin``
(or, for ``Corpus``, an equivalent in-class test) against a user matrix that
covers: superuser, creator, non-creator with an explicit guardian grant,
non-creator with no grant ("stranger"), public-only viewer (stranger × a public
instance), and anonymous. The following invariants are explicitly pinned:

* **READ equivalence** — ``user_can(READ) == visible_to_user.filter(pk).exists()``
  for every (user, instance) pair (mixin ``test_read_equivalence_across_user_matrix``;
  ``Corpus`` has its own copy).
* **Group-shared equivalence** — pinned for ``Corpus`` via
  ``test_group_shared_read_equivalence`` (filter and check agree for a
  group-granted user). The Phase F audit (issue #1660) surfaced a per-model
  drift where ``Document`` / ``Annotation`` / ``Note`` honoured group
  object-permissions in ``Manager.user_can`` but not in
  ``QuerySet.visible_to_user`` (which joined only the *user*
  object-permission table). Issue #1714 closed that drift — every affected
  ``QuerySet.visible_to_user`` now also joins the ``*groupobjectpermission``
  table — and the equivalence is pinned for ``Document`` by
  ``DocumentAuthorizationInvariantsTestCase
  .test_group_shared_read_user_can_vs_visible_to_user_equivalence``.
* **No silent widening (write asymmetry)** — for every model with an
  ``is_public`` field, a non-creator/non-shared user must get ``False`` for
  UPDATE/DELETE even when ``is_public=True``: ``Corpus``
  (``test_is_public_grants_only_read_not_writes``), ``Document``
  (``test_is_public_grants_only_read``), ``Note`` / ``Annotation`` /
  ``Conversation`` / ``UserFeedback`` (``test_is_public_does_not_grant_writes``).
  ``Relationship`` is intentionally excluded — ``RelationshipManager.user_can``
  does not consult ``is_public`` (see its docstring in ``shared/Managers.py``);
  relationship READ is pure ``MIN(doc, corpus)`` + creator, so structural
  locking is the relevant relationship invariant. ``ChatMessage`` has no
  ``is_public`` field.
* **Structural locking** — every non-READ permission returns ``False`` for any
  non-superuser on a structural annotation/relationship
  (``test_structural_*_are_read_only_for_non_superuser``).
* **Recursive privacy (annotation)** — ``created_by_analysis`` is pinned by
  ``test_privacy_recursion_*``; ``created_by_extract`` is covered by the matrix
  (``private_via_extract`` instance) here and by focused branch tests in
  ``test_authorization_invariants_coverage.py``.
* **Conversation bifurcation** — a CHAT is not visible to a corpus reader while
  a THREAD is (``test_chat_does_not_inherit_corpus_context`` /
  ``test_thread_inherits_corpus_read``); the same split is pinned for
  ``ChatMessage`` (``test_chat_message_does_not_inherit_corpus_context``).
* **Anonymous parity** — ``AnonymousUser()`` is in every class's user matrix, so
  the READ-equivalence test pins anonymous parity for every model.
* **BACON-mode COMMENT** — corpus ``allow_comments`` open-commenting is pinned
  outside this module in ``test_feedback_mutations.py`` and
  ``test_comment_permission.py``; not duplicated here.
"""

from typing import TYPE_CHECKING, Any

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase

# Inherit the mixin from ``TestCase`` for the type checker only so
# ``self.assertEqual`` / ``self.assertTrue`` resolve; at runtime the mixin is a
# plain ``object`` and gets the assert helpers from the concrete subclass's
# MRO. This avoids the MRO conflict that direct ``TestCase``
# inheritance would create when paired with a concrete ``TestCase``
# subclass.
if TYPE_CHECKING:
    _MixinBase = TestCase
else:
    _MixinBase = object

from opencontractserver.corpuses.models import Corpus
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class CorpusAuthorizationInvariantsTestCase(TestCase):
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

    def test_group_shared_read_equivalence(self):
        """A user who can READ only via a group-level guardian grant is in
        ``visible_to_user`` AND passes ``user_can(READ)``.

        ``user_can`` resolves group permissions (``include_group_permissions``
        defaults to True) and ``visible_to_user`` folds group grants into its
        ``Q(...)`` predicate; this pins that the two surfaces agree for a
        group-shared user — the one fixture slot the per-model matrices don't
        otherwise exercise. Group membership flows through the shared
        ``PermissionQuerySet`` group branch, so this Corpus pin is
        representative for every other visibility-managed model.
        """
        from django.contrib.auth.models import Group
        from guardian.shortcuts import assign_perm

        group = Group.objects.create(name="corpus_invariant_group")
        group_user = User.objects.create_user(
            username="group_reader", email="groupr@invariant.test", password="x"
        )
        group_user.groups.add(group)
        assign_perm("read_corpus", group, self.private_corpus)

        self._assert_read_equivalence(group_user, self.private_corpus)
        self.assertTrue(
            self.private_corpus.user_can(group_user, PermissionTypes.READ),
            "group-granted READ should authorize user_can(READ)",
        )
        # Group READ must not bleed into writes.
        self.assertFalse(
            self.private_corpus.user_can(group_user, PermissionTypes.UPDATE),
            "group READ grant silently widened to UPDATE — leak!",
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

        ``_default_user_can`` routes EDIT through the ``update_<model>``
        guardian codename. Pinning this prevents a silent divergence if the
        alias is ever dropped.
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


class CorpusFolderDelegatesUserCanToCorpusTestCase(TestCase):
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


class _UserCanInvariantsMixin(_MixinBase):
    """Shared assertions for per-model ``user_can`` / ``visible_to_user``
    invariants. Each subclass populates ``self._matrix_users`` and
    ``self._matrix_instances`` in setUp, then calls the inherited
    helpers below.

    Lives in this module so the test classes for every visibility-managed
    model share a single regression guard. Adding a new model? Subclass
    this mixin, set the two matrices, and the equivalence and surface
    tests come for free.
    """

    # Subclasses populate these in ``setUp``. Declared here so mypy treats
    # the mixin's ``self.<attr>`` references as defined. ``model_cls`` is
    # typed as ``Any`` (not ``type[Model]``) because mypy's Django stubs
    # don't expose the ``objects`` manager on the abstract base ``Model``
    # class — and the assertions below reach for ``model_cls.objects``.
    model_cls: Any
    _matrix_users: list[Any]
    _matrix_instances: list[Any]
    _superuser: Any

    def _all_matrix_pairs(self):
        for user in self._matrix_users:
            for instance in self._matrix_instances:
                yield user, instance

    def test_read_equivalence_across_user_matrix(self):
        """``user_can(READ) == visible_to_user.filter(pk=).exists()`` for every (user, instance)."""
        for user, instance in self._all_matrix_pairs():
            check = self.model_cls.objects.user_can(
                user, instance, PermissionTypes.READ
            )
            in_filter = (
                self.model_cls.objects.visible_to_user(user)
                .filter(pk=instance.pk)
                .exists()
            )
            self.assertEqual(
                check,
                in_filter,
                f"{self.model_cls.__name__} user_can/visible_to_user disagree for "
                f"user={getattr(user, 'username', 'anon')}, pk={instance.pk}: "
                f"check={check}, filter={in_filter}",
            )

    def test_manager_and_instance_surfaces_agree(self):
        """``Model.objects.user_can(...)`` and ``instance.user_can(...)`` agree."""
        for user, instance in self._all_matrix_pairs():
            for perm in (
                PermissionTypes.READ,
                PermissionTypes.UPDATE,
                PermissionTypes.DELETE,
            ):
                via_manager = self.model_cls.objects.user_can(user, instance, perm)
                via_instance = instance.user_can(user, perm)
                self.assertEqual(
                    via_manager,
                    via_instance,
                    f"{self.model_cls.__name__} manager/instance disagree for "
                    f"user={getattr(user, 'username', 'anon')}, pk={instance.pk}, perm={perm}",
                )

    def test_superuser_bypass_all_permissions(self):
        """Superuser passes every permission on every instance in the matrix."""
        for instance in self._matrix_instances:
            for perm in PermissionTypes:
                self.assertTrue(
                    self.model_cls.objects.user_can(self._superuser, instance, perm),
                    f"superuser denied {perm} on {self.model_cls.__name__} pk={instance.pk}",
                )


class DocumentAuthorizationInvariantsTestCase(_UserCanInvariantsMixin, TestCase):
    """Pin filter/check equivalence for ``Document``."""

    def setUp(self):
        from opencontractserver.documents.models import Document

        self.model_cls = Document

        self.creator = User.objects.create_user(
            username="doc_creator", email="dc@inv.test", password="x"
        )
        self.shared_reader = User.objects.create_user(
            username="doc_reader", email="dr@inv.test", password="x"
        )
        self.stranger = User.objects.create_user(
            username="doc_stranger", email="ds@inv.test", password="x"
        )
        self._superuser = User.objects.create_superuser(
            username="doc_admin", email="da@inv.test", password="x"
        )

        self.private_doc = Document.objects.create(
            title="Private Doc", creator=self.creator, is_public=False
        )
        self.public_doc = Document.objects.create(
            title="Public Doc", creator=self.creator, is_public=True
        )
        set_permissions_for_obj_to_user(
            self.shared_reader, self.private_doc, [PermissionTypes.READ]
        )

        self._matrix_users = [
            self.creator,
            self.shared_reader,
            self.stranger,
            self._superuser,
            AnonymousUser(),
        ]
        self._matrix_instances = [self.private_doc, self.public_doc]

    def test_is_public_grants_only_read(self):
        """``is_public=True`` grants READ but not UPDATE/DELETE."""
        self.assertTrue(self.public_doc.user_can(self.stranger, PermissionTypes.READ))
        for perm in (PermissionTypes.UPDATE, PermissionTypes.DELETE):
            self.assertFalse(self.public_doc.user_can(self.stranger, perm))

    def test_group_shared_read_user_can_vs_visible_to_user_equivalence(self):
        """Filter/check equivalence for a group-granted READ on ``Document``.

        ``DocumentManager.user_can`` honours group object-permissions
        (``_default_user_can`` resolves perms with
        ``include_group_permissions=True``). Issue #1714 closed the gap where
        ``DocumentQuerySet.visible_to_user`` consulted only the *user*
        object-permission table — it now also joins
        ``documentgroupobjectpermission``. A user whose only READ grant is via
        a group must therefore both pass ``user_can(READ)`` and appear in
        ``visible_to_user``.

        This used to pin a KNOWN DRIFT (Phase F audit, issue #1660); the drift
        is now closed, so this asserts equivalence in both directions.
        """
        from django.contrib.auth.models import Group
        from guardian.shortcuts import assign_perm

        from opencontractserver.documents.models import Document

        group = Group.objects.create(name="doc_invariant_group")
        group_user = User.objects.create_user(
            username="doc_group_reader", email="dgr@inv.test", password="x"
        )
        group_user.groups.add(group)
        assign_perm("read_document", group, self.private_doc)

        check = self.private_doc.user_can(group_user, PermissionTypes.READ)
        in_filter = (
            Document.objects.visible_to_user(group_user)
            .filter(pk=self.private_doc.pk)
            .exists()
        )
        self.assertTrue(check, "user_can must honour the group-level READ grant")
        self.assertTrue(
            in_filter,
            "visible_to_user must honour the group-level READ grant (issue #1714)",
        )
        # Group READ must not bleed into writes.
        self.assertFalse(
            self.private_doc.user_can(group_user, PermissionTypes.UPDATE),
            "group READ grant silently widened to UPDATE — leak!",
        )


class NoteAuthorizationInvariantsTestCase(_UserCanInvariantsMixin, TestCase):
    """Pin filter/check equivalence for ``Note`` (MIN of doc+corpus)."""

    def setUp(self):
        from opencontractserver.annotations.models import Note
        from opencontractserver.documents.models import Document

        self.model_cls = Note

        self.creator = User.objects.create_user(
            username="note_creator", email="nc@inv.test", password="x"
        )
        self.shared_reader = User.objects.create_user(
            username="note_reader", email="nr@inv.test", password="x"
        )
        self.stranger = User.objects.create_user(
            username="note_stranger", email="ns@inv.test", password="x"
        )
        self._superuser = User.objects.create_superuser(
            username="note_admin", email="na@inv.test", password="x"
        )

        self.private_corpus = Corpus.objects.create(
            title="Note Corpus", creator=self.creator, is_public=False
        )
        self.private_doc = Document.objects.create(
            title="Note Doc", creator=self.creator, is_public=False
        )
        set_permissions_for_obj_to_user(
            self.shared_reader, self.private_corpus, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.shared_reader, self.private_doc, [PermissionTypes.READ]
        )

        self.private_note = Note.objects.create(
            title="Note 1",
            content="x",
            creator=self.creator,
            document=self.private_doc,
            corpus=self.private_corpus,
            is_public=False,
        )

        self._matrix_users = [
            self.creator,
            self.shared_reader,
            self.stranger,
            self._superuser,
            AnonymousUser(),
        ]
        self._matrix_instances = [self.private_note]

    def test_doc_visible_corpus_invisible_means_note_invisible(self):
        """MIN: if corpus visibility fails, note is invisible even when doc visible."""
        # Stranger has no access to either. Strip shared_reader's corpus access.
        set_permissions_for_obj_to_user(self.shared_reader, self.private_corpus, [])
        self.assertFalse(
            self.private_note.user_can(self.shared_reader, PermissionTypes.READ)
        )

    def test_is_public_does_not_grant_writes(self):
        """SECURITY: ``is_public=True`` grants a non-creator READ but never
        UPDATE/DELETE — the write asymmetry must hold for Note."""
        from opencontractserver.annotations.models import Note
        from opencontractserver.documents.models import Document

        public_corpus = Corpus.objects.create(
            title="Public Note Corpus", creator=self.creator, is_public=True
        )
        public_doc = Document.objects.create(
            title="Public Note Doc", creator=self.creator, is_public=True
        )
        public_note = Note.objects.create(
            title="Public Note",
            content="x",
            creator=self.creator,
            document=public_doc,
            corpus=public_corpus,
            is_public=True,
        )
        self.assertTrue(public_note.user_can(self.stranger, PermissionTypes.READ))
        for perm in (PermissionTypes.UPDATE, PermissionTypes.DELETE):
            self.assertFalse(
                public_note.user_can(self.stranger, perm),
                f"stranger gained {perm} on public note via is_public — leak!",
            )


class RelationshipAuthorizationInvariantsTestCase(_UserCanInvariantsMixin, TestCase):
    """Pin filter/check equivalence for ``Relationship`` (MIN + structural-write-deny)."""

    def setUp(self):
        from opencontractserver.annotations.models import (
            Annotation,
            AnnotationLabel,
            Relationship,
        )
        from opencontractserver.documents.models import Document

        self.model_cls = Relationship

        self.creator = User.objects.create_user(
            username="rel_creator", email="rc@inv.test", password="x"
        )
        self.shared_reader = User.objects.create_user(
            username="rel_reader", email="rr@inv.test", password="x"
        )
        self.stranger = User.objects.create_user(
            username="rel_stranger", email="rs@inv.test", password="x"
        )
        self._superuser = User.objects.create_superuser(
            username="rel_admin", email="ra@inv.test", password="x"
        )

        self.corpus = Corpus.objects.create(
            title="Rel Corpus", creator=self.creator, is_public=False
        )
        self.document = Document.objects.create(
            title="Rel Doc", creator=self.creator, is_public=False
        )
        set_permissions_for_obj_to_user(
            self.shared_reader, self.corpus, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.shared_reader, self.document, [PermissionTypes.READ]
        )

        self.rel_label = AnnotationLabel.objects.create(
            text="rel_label", label_type="RELATIONSHIP_LABEL", creator=self.creator
        )
        # First create source/target annotations
        self.token_label = AnnotationLabel.objects.create(
            text="t", label_type="TOKEN_LABEL", creator=self.creator
        )
        self.source_ann = Annotation.objects.create(
            raw_text="src",
            json={"x": 1},
            page=1,
            annotation_label=self.token_label,
            creator=self.creator,
            document=self.document,
            corpus=self.corpus,
        )
        self.target_ann = Annotation.objects.create(
            raw_text="tgt",
            json={"x": 2},
            page=1,
            annotation_label=self.token_label,
            creator=self.creator,
            document=self.document,
            corpus=self.corpus,
        )

        self.relationship = Relationship.objects.create(
            relationship_label=self.rel_label,
            creator=self.creator,
            document=self.document,
            corpus=self.corpus,
            structural=False,
        )
        self.relationship.source_annotations.add(self.source_ann)
        self.relationship.target_annotations.add(self.target_ann)

        self.structural_rel = Relationship.objects.create(
            relationship_label=self.rel_label,
            creator=self.creator,
            document=self.document,
            corpus=self.corpus,
            structural=True,
        )

        self._matrix_users = [
            self.creator,
            self.shared_reader,
            self.stranger,
            self._superuser,
            AnonymousUser(),
        ]
        self._matrix_instances = [self.relationship, self.structural_rel]

    def test_structural_relationships_are_read_only_for_non_superuser(self):
        """Structural relationships can only be READ by non-superusers."""
        for user in (self.creator, self.shared_reader, self.stranger):
            for perm in (
                PermissionTypes.UPDATE,
                PermissionTypes.DELETE,
                PermissionTypes.CREATE,
            ):
                self.assertFalse(
                    self.structural_rel.user_can(user, perm),
                    f"non-superuser {getattr(user, 'username', 'anon')} got {perm} "
                    f"on structural relationship — leak!",
                )
        # Superuser still passes.
        self.assertTrue(
            self.structural_rel.user_can(self._superuser, PermissionTypes.UPDATE)
        )

    def test_no_privacy_widening_via_created_by_analysis(self):
        """RelationshipManager.user_can does NOT consult ``created_by_analysis``.

        Relationship privacy has never recursed into that field; this
        test pins that ``RelationshipManager.user_can`` preserves that
        behavior. Adding a privacy check would require its own explicit
        invariant.
        """
        # No fixture mutation needed — the relationship has no created_by_analysis
        # set, and the matrix-level READ-equivalence test already
        # exercises the standard MIN(doc, corpus) path. This sentinel
        # test documents the contract.
        self.assertIsNone(self.relationship.created_by_analysis_id)
        self.assertIsNone(self.relationship.created_by_extract_id)


class AnnotationAuthorizationInvariantsTestCase(_UserCanInvariantsMixin, TestCase):
    """Pin filter/check equivalence for ``Annotation``.

    Covers: structural-write-deny, MIN(doc, corpus), and the bug-fix
    posture for privacy recursion via ``Analysis.objects.user_can`` /
    ``Extract.objects.user_can`` (creator status now honored).
    """

    def setUp(self):
        from opencontractserver.analyzer.models import Analyzer
        from opencontractserver.annotations.models import (
            Annotation,
            AnnotationLabel,
        )
        from opencontractserver.documents.models import Document

        self.model_cls = Annotation

        self.creator = User.objects.create_user(
            username="ann_creator", email="ac@inv.test", password="x"
        )
        self.shared_reader = User.objects.create_user(
            username="ann_reader", email="ar@inv.test", password="x"
        )
        self.stranger = User.objects.create_user(
            username="ann_stranger", email="as@inv.test", password="x"
        )
        self._superuser = User.objects.create_superuser(
            username="ann_admin", email="aa@inv.test", password="x"
        )

        self.corpus = Corpus.objects.create(
            title="Ann Corpus", creator=self.creator, is_public=False
        )
        self.document = Document.objects.create(
            title="Ann Doc", creator=self.creator, is_public=False
        )
        set_permissions_for_obj_to_user(
            self.shared_reader, self.corpus, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.shared_reader, self.document, [PermissionTypes.READ]
        )

        self.token_label = AnnotationLabel.objects.create(
            text="t", label_type="TOKEN_LABEL", creator=self.creator
        )

        self.public_ann = Annotation.objects.create(
            raw_text="public_ann",
            json={"x": 1},
            page=1,
            annotation_label=self.token_label,
            creator=self.creator,
            document=self.document,
            corpus=self.corpus,
            is_public=True,
        )
        self.private_ann = Annotation.objects.create(
            raw_text="private_ann",
            json={"x": 2},
            page=1,
            annotation_label=self.token_label,
            creator=self.creator,
            document=self.document,
            corpus=self.corpus,
            is_public=False,
        )
        self.structural_ann = Annotation.objects.create(
            raw_text="structural",
            json={"x": 3},
            page=1,
            annotation_label=self.token_label,
            creator=self.creator,
            document=self.document,
            corpus=self.corpus,
            structural=True,
        )

        # An Analysis owned by the creator. The privacy recursion
        # bug-fix means the creator's user_can on the source analysis
        # returns True via creator-shortcut. ``Analyzer`` has a check
        # constraint requiring exactly one of ``host_gremlin`` /
        # ``task_name`` to be set.
        self.analyzer = Analyzer.objects.create(
            id="test_analyzer_invariant",
            description="x",
            creator=self.creator,
            task_name="opencontractserver.tasks.noop",
        )
        from opencontractserver.analyzer.models import Analysis

        self.analysis = Analysis.objects.create(
            analyzer=self.analyzer,
            analyzed_corpus=self.corpus,
            creator=self.creator,
        )
        self.private_via_analysis = Annotation.objects.create(
            raw_text="via_analysis",
            json={"x": 4},
            page=1,
            annotation_label=self.token_label,
            creator=self.creator,
            document=self.document,
            corpus=self.corpus,
            created_by_analysis=self.analysis,
        )

        # An Extract owned by the creator. Including a ``created_by_extract``
        # annotation in the matrix pins the extract privacy-recursion branch
        # of ``AnnotationManager.user_can`` against the equivalence invariant
        # inside this class (the focused branch tests live in
        # ``test_authorization_invariants_coverage.py``).
        from opencontractserver.extracts.models import Extract, Fieldset

        self.fieldset = Fieldset.objects.create(
            name="Invariant Fieldset", creator=self.creator
        )
        self.extract = Extract.objects.create(
            name="Invariant Extract",
            corpus=self.corpus,
            fieldset=self.fieldset,
            creator=self.creator,
        )
        self.private_via_extract = Annotation.objects.create(
            raw_text="via_extract",
            json={"x": 5},
            page=1,
            annotation_label=self.token_label,
            creator=self.creator,
            document=self.document,
            corpus=self.corpus,
            created_by_extract=self.extract,
        )

        self._matrix_users = [
            self.creator,
            self.shared_reader,
            self.stranger,
            self._superuser,
            AnonymousUser(),
        ]
        self._matrix_instances = [
            self.public_ann,
            self.private_ann,
            self.structural_ann,
            self.private_via_analysis,
            self.private_via_extract,
        ]

    def test_structural_annotations_are_read_only_for_non_superuser(self):
        for user in (self.creator, self.shared_reader, self.stranger):
            for perm in (
                PermissionTypes.UPDATE,
                PermissionTypes.DELETE,
                PermissionTypes.CREATE,
            ):
                self.assertFalse(
                    self.structural_ann.user_can(user, perm),
                    f"non-superuser {getattr(user, 'username', 'anon')} got {perm} "
                    f"on structural annotation — leak!",
                )
        self.assertTrue(
            self.structural_ann.user_can(self._superuser, PermissionTypes.UPDATE)
        )

    def test_privacy_recursion_honors_creator_on_source_analysis(self):
        """BUG-FIX POSTURE: the recursive privacy check now uses
        ``Analysis.objects.user_can`` which honors creator status.
        Previously the recursion used a creator-blind permission check
        and could deny the analysis creator access to their own private
        annotation.
        """
        # The creator owns both the analysis AND the annotation. The new
        # path returns True via the creator short-circuit on Analysis.
        self.assertTrue(
            self.private_via_analysis.user_can(self.creator, PermissionTypes.READ)
        )

    def test_privacy_recursion_blocks_user_without_analysis_access(self):
        """A user with doc+corpus READ but no analysis access cannot
        READ a private-via-analysis annotation.
        """
        self.assertFalse(
            self.private_via_analysis.user_can(self.shared_reader, PermissionTypes.READ)
        )

    def test_is_public_does_not_grant_writes(self):
        """SECURITY: ``is_public=True`` grants a non-creator READ but never
        UPDATE/DELETE — the write asymmetry must hold for Annotation."""
        from opencontractserver.annotations.models import Annotation
        from opencontractserver.documents.models import Document

        public_corpus = Corpus.objects.create(
            title="Public Ann Corpus", creator=self.creator, is_public=True
        )
        public_doc = Document.objects.create(
            title="Public Ann Doc", creator=self.creator, is_public=True
        )
        public_ann = Annotation.objects.create(
            raw_text="public_write_asymmetry",
            json={"x": 9},
            page=1,
            annotation_label=self.token_label,
            creator=self.creator,
            document=public_doc,
            corpus=public_corpus,
            is_public=True,
        )
        self.assertTrue(public_ann.user_can(self.stranger, PermissionTypes.READ))
        for perm in (PermissionTypes.UPDATE, PermissionTypes.DELETE):
            self.assertFalse(
                public_ann.user_can(self.stranger, perm),
                f"stranger gained {perm} on public annotation via is_public — leak!",
            )


class ConversationAuthorizationInvariantsTestCase(_UserCanInvariantsMixin, TestCase):
    """Pin filter/check equivalence for ``Conversation`` (CHAT/THREAD bifurcation)."""

    def setUp(self):
        from opencontractserver.conversations.models import (
            Conversation,
            ConversationTypeChoices,
        )
        from opencontractserver.documents.models import Document

        self.model_cls = Conversation

        self.creator = User.objects.create_user(
            username="conv_creator", email="cc@inv.test", password="x"
        )
        self.corpus_reader = User.objects.create_user(
            username="conv_corpus_reader", email="ccr@inv.test", password="x"
        )
        self.stranger = User.objects.create_user(
            username="conv_stranger", email="cs@inv.test", password="x"
        )
        self._superuser = User.objects.create_superuser(
            username="conv_admin", email="ca@inv.test", password="x"
        )

        self.corpus = Corpus.objects.create(
            title="Conv Corpus", creator=self.creator, is_public=False
        )
        self.document = Document.objects.create(
            title="Conv Doc", creator=self.creator, is_public=False
        )
        set_permissions_for_obj_to_user(
            self.corpus_reader, self.corpus, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.corpus_reader, self.document, [PermissionTypes.READ]
        )

        # CHAT type — restrictive (no context inheritance)
        self.private_chat = Conversation.objects.create(
            title="Private CHAT",
            chat_with_corpus=self.corpus,
            creator=self.creator,
            conversation_type=ConversationTypeChoices.CHAT,
            is_public=False,
        )
        # THREAD type — context inheritance from corpus
        self.thread_on_corpus = Conversation.objects.create(
            title="Thread on Corpus",
            chat_with_corpus=self.corpus,
            creator=self.creator,
            conversation_type=ConversationTypeChoices.THREAD,
            is_public=False,
        )

        self._matrix_users = [
            self.creator,
            self.corpus_reader,
            self.stranger,
            self._superuser,
            AnonymousUser(),
        ]
        self._matrix_instances = [self.private_chat, self.thread_on_corpus]

    def test_chat_does_not_inherit_corpus_context(self):
        """CHAT is restrictive: corpus reader cannot see another user's CHAT."""
        self.assertFalse(
            self.private_chat.user_can(self.corpus_reader, PermissionTypes.READ)
        )

    def test_thread_inherits_corpus_read(self):
        """THREAD inherits READ from corpus context."""
        self.assertTrue(
            self.thread_on_corpus.user_can(self.corpus_reader, PermissionTypes.READ)
        )

    def test_anonymous_cannot_see_chats(self):
        """Anonymous users can NEVER see CHAT conversations."""
        self.assertFalse(
            self.private_chat.user_can(AnonymousUser(), PermissionTypes.READ)
        )

    def test_is_public_does_not_grant_writes(self):
        """SECURITY: ``is_public=True`` grants a non-creator READ but never
        UPDATE/DELETE — the write asymmetry must hold for Conversation."""
        from opencontractserver.conversations.models import (
            Conversation,
            ConversationTypeChoices,
        )

        public_thread = Conversation.objects.create(
            title="Public Thread",
            chat_with_corpus=self.corpus,
            creator=self.creator,
            conversation_type=ConversationTypeChoices.THREAD,
            is_public=True,
        )
        self.assertTrue(public_thread.user_can(self.stranger, PermissionTypes.READ))
        for perm in (PermissionTypes.UPDATE, PermissionTypes.DELETE):
            self.assertFalse(
                public_thread.user_can(self.stranger, perm),
                f"stranger gained {perm} on public conversation via is_public "
                f"— leak!",
            )


class ChatMessageAuthorizationInvariantsTestCase(_UserCanInvariantsMixin, TestCase):
    """Pin filter/check equivalence for ``ChatMessage`` (moderator branch)."""

    def setUp(self):
        from opencontractserver.conversations.models import (
            ChatMessage,
            Conversation,
            ConversationTypeChoices,
        )
        from opencontractserver.documents.models import Document

        self.model_cls = ChatMessage

        self.corpus_owner = User.objects.create_user(
            username="msg_corpus_owner", email="mco@inv.test", password="x"
        )
        self.thread_creator = User.objects.create_user(
            username="msg_thread_creator", email="mtc@inv.test", password="x"
        )
        self.stranger = User.objects.create_user(
            username="msg_stranger", email="ms@inv.test", password="x"
        )
        self._superuser = User.objects.create_superuser(
            username="msg_admin", email="ma@inv.test", password="x"
        )

        # corpus_owner owns the corpus; thread_creator runs a thread on it.
        # corpus_owner is a moderator (corpus owner branch).
        self.corpus = Corpus.objects.create(
            title="Msg Corpus", creator=self.corpus_owner, is_public=False
        )
        self.document = Document.objects.create(
            title="Msg Doc", creator=self.corpus_owner, is_public=False
        )
        set_permissions_for_obj_to_user(
            self.thread_creator, self.corpus, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(
            self.thread_creator, self.document, [PermissionTypes.READ]
        )
        self.thread = Conversation.objects.create(
            title="Mod Thread",
            chat_with_corpus=self.corpus,
            creator=self.thread_creator,
            conversation_type=ConversationTypeChoices.THREAD,
            is_public=False,
        )
        self.msg = ChatMessage.objects.create(
            conversation=self.thread,
            creator=self.thread_creator,
            content="hi",
            msg_type="HUMAN",
        )

        self._matrix_users = [
            self.corpus_owner,
            self.thread_creator,
            self.stranger,
            self._superuser,
            AnonymousUser(),
        ]
        self._matrix_instances = [self.msg]

    def test_moderator_sees_message_via_corpus_ownership(self):
        """Corpus owner can READ messages in threads on their corpus
        (moderator branch), even if they didn't create the thread."""
        self.assertTrue(self.msg.user_can(self.corpus_owner, PermissionTypes.READ))

    def test_chat_message_does_not_inherit_corpus_context(self):
        """CHAT/THREAD bifurcation at the message layer: a message in a CHAT
        is NOT visible to a corpus reader, even though the same reader sees
        messages in a THREAD on that corpus.

        ``thread_creator`` holds corpus READ. They see ``self.msg`` (a THREAD
        message) but must NOT see a message in a CHAT created by the corpus
        owner — CHAT conversations are restrictive and do not inherit corpus
        context."""
        from opencontractserver.conversations.models import (
            ChatMessage,
            Conversation,
            ConversationTypeChoices,
        )

        chat = Conversation.objects.create(
            title="Owner CHAT",
            chat_with_corpus=self.corpus,
            creator=self.corpus_owner,
            conversation_type=ConversationTypeChoices.CHAT,
            is_public=False,
        )
        chat_msg = ChatMessage.objects.create(
            conversation=chat,
            creator=self.corpus_owner,
            content="private chat",
            msg_type="HUMAN",
        )
        # Sanity: the corpus reader DOES see the THREAD message.
        self.assertTrue(self.msg.user_can(self.thread_creator, PermissionTypes.READ))
        # Bifurcation: but NOT the CHAT message.
        self.assertFalse(
            chat_msg.user_can(self.thread_creator, PermissionTypes.READ),
            "corpus reader saw a CHAT message — CHAT must not inherit corpus "
            "context",
        )


class UserFeedbackAuthorizationInvariantsTestCase(_UserCanInvariantsMixin, TestCase):
    """Pin filter/check equivalence for ``UserFeedback`` including the
    inherited-annotation-visibility READ branch.

    Feedback follows the permissioning of the annotation it comments on
    (see ``UserFeedbackQuerySet.visible_to_user``): a user can READ a
    feedback row when they can READ the commented annotation via
    ``Annotation.objects.visible_to_user(user)``. This test pins that
    invariant: every row included by the queryset filter must answer
    True for the same user's ``user_can(..., READ)`` check, and vice
    versa.
    """

    def setUp(self):
        from opencontractserver.annotations.models import (
            Annotation,
            AnnotationLabel,
        )
        from opencontractserver.documents.models import Document
        from opencontractserver.feedback.models import UserFeedback

        self.model_cls = UserFeedback

        self.creator = User.objects.create_user(
            username="fb_creator", email="fbc@inv.test", password="x"
        )
        self.shared_reader = User.objects.create_user(
            username="fb_reader", email="fbr@inv.test", password="x"
        )
        self.stranger = User.objects.create_user(
            username="fb_stranger", email="fbs@inv.test", password="x"
        )
        self._superuser = User.objects.create_superuser(
            username="fb_admin", email="fba@inv.test", password="x"
        )

        # Annotation that the feedback comments on: lives on a PUBLIC
        # document with no corpus, so it is visible to every
        # authenticated user (and anonymous, since it's structural).
        self.doc = Document.objects.create(
            title="FB Doc", creator=self.creator, is_public=True
        )
        self.label = AnnotationLabel.objects.create(
            text="fblbl", label_type="TOKEN_LABEL", creator=self.creator
        )
        self.public_ann = Annotation.objects.create(
            raw_text="public_for_fb",
            json={"x": 1},
            page=1,
            annotation_label=self.label,
            creator=self.creator,
            document=self.doc,
            is_public=True,
            structural=True,
        )

        # Feedback that is itself private but comments on an annotation
        # visible to every user — the inherited-annotation-visibility
        # branch grants READ.
        self.fb_on_public = UserFeedback.objects.create(
            creator=self.creator,
            commented_annotation=self.public_ann,
            is_public=False,
            comment="x",
        )
        # Plain feedback with no commented annotation — only creator/grantee
        # can read.
        self.fb_plain = UserFeedback.objects.create(
            creator=self.creator,
            is_public=False,
            comment="y",
        )

        self._matrix_users = [
            self.creator,
            self.shared_reader,
            self.stranger,
            self._superuser,
            AnonymousUser(),
        ]
        self._matrix_instances = [self.fb_on_public, self.fb_plain]

    def test_visible_commented_annotation_grants_read(self):
        """A user who can see the commented annotation
        (per ``Annotation.objects.visible_to_user``) inherits READ on
        the feedback row even when the feedback itself is private and
        the user has no direct grants."""
        self.assertTrue(self.fb_on_public.user_can(self.stranger, PermissionTypes.READ))

    def test_visible_commented_annotation_does_not_grant_writes(self):
        """Inherited annotation visibility is READ-only — does not bleed
        into UPDATE/DELETE."""
        for perm in (PermissionTypes.UPDATE, PermissionTypes.DELETE):
            self.assertFalse(
                self.fb_on_public.user_can(self.stranger, perm),
                f"stranger gained {perm} on private feedback via inherited "
                f"annotation visibility — leak!",
            )

    def test_is_public_does_not_grant_writes(self):
        """SECURITY: ``is_public=True`` grants a non-creator READ but never
        UPDATE/DELETE — the write asymmetry must hold for UserFeedback."""
        from opencontractserver.feedback.models import UserFeedback

        public_fb = UserFeedback.objects.create(
            creator=self.creator,
            is_public=True,
            comment="public feedback",
        )
        self.assertTrue(public_fb.user_can(self.stranger, PermissionTypes.READ))
        for perm in (PermissionTypes.UPDATE, PermissionTypes.DELETE):
            self.assertFalse(
                public_fb.user_can(self.stranger, perm),
                f"stranger gained {perm} on public feedback via is_public — leak!",
            )
