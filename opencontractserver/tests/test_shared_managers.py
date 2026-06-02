"""
Tests for opencontractserver.shared.Managers (closes #1477).

Covers the branches introduced or modified during the mypy graduation:
  - BaseVisibilityManager.visible_to_user(user=None)    → AnonymousUser path
  - BaseVisibilityManager.visible_to_user(superuser)    → computed like a
        normal user (no blanket bypass; scoped admin access 2026-05)
  - BaseVisibilityManager.visible_to_user(abstract)     → RuntimeError guard
  - PermissionManager.visible_to_user(user=None)        → AnonymousUser path
  - PermissionManager.visible_to_user(superuser)        → computed like a
        normal user (no blanket bypass; scoped admin access 2026-05)
  - UserFeedbackManager.visible_to_user(user=None)      → AnonymousUser path
  - UserFeedbackManager.get_or_none()                   → hit and miss paths
  - DocumentManager.unique_blob_paths()                 → blob sharing logic
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase

from opencontractserver.corpuses.models import Corpus
from opencontractserver.feedback.models import UserFeedback

User = get_user_model()


class PermissionManagerVisibleToUserNoneTest(TestCase):
    """PermissionManager.visible_to_user(user=None) must coerce None → AnonymousUser."""

    def setUp(self) -> None:
        self.owner = User.objects.create_user(
            username="pm_owner",
            email="pm_owner@example.com",
        )
        # Public corpus
        self.public_corpus = Corpus.objects.create(
            title="Public Corpus",
            creator=self.owner,
            is_public=True,
        )
        # Private corpus
        self.private_corpus = Corpus.objects.create(
            title="Private Corpus",
            creator=self.owner,
            is_public=False,
        )

    def test_none_user_sees_only_public_items(self) -> None:
        """Calling visible_to_user(user=None) should behave like AnonymousUser."""
        qs = Corpus.objects.visible_to_user(user=None)
        ids = list(qs.values_list("pk", flat=True))
        self.assertIn(self.public_corpus.pk, ids)
        self.assertNotIn(self.private_corpus.pk, ids)

    def test_anonymous_user_object_sees_only_public_items(self) -> None:
        """Passing an AnonymousUser instance should return the same result."""
        qs = Corpus.objects.visible_to_user(user=AnonymousUser())
        ids = list(qs.values_list("pk", flat=True))
        self.assertIn(self.public_corpus.pk, ids)
        self.assertNotIn(self.private_corpus.pk, ids)

    def test_authenticated_user_sees_own_private_items(self) -> None:
        """Authenticated creator should see both public and their own private items."""
        qs = Corpus.objects.visible_to_user(user=self.owner)
        ids = list(qs.values_list("pk", flat=True))
        self.assertIn(self.public_corpus.pk, ids)
        self.assertIn(self.private_corpus.pk, ids)


class UserFeedbackManagerVisibleToUserNoneTest(TestCase):
    """UserFeedbackManager.visible_to_user(user=None) coerces None → AnonymousUser."""

    def setUp(self) -> None:
        self.owner = User.objects.create_user(
            username="uf_owner",
            email="uf_owner@example.com",
        )
        # Public feedback
        self.public_feedback = UserFeedback.objects.create(
            creator=self.owner,
            is_public=True,
            comment="public",
        )
        # Private feedback
        self.private_feedback = UserFeedback.objects.create(
            creator=self.owner,
            is_public=False,
            comment="private",
        )

    def test_none_user_sees_only_public_feedback(self) -> None:
        qs = UserFeedback.objects.visible_to_user(user=None)
        ids = list(qs.values_list("pk", flat=True))
        self.assertIn(self.public_feedback.pk, ids)
        self.assertNotIn(self.private_feedback.pk, ids)

    def test_anonymous_user_object_sees_only_public_feedback(self) -> None:
        qs = UserFeedback.objects.visible_to_user(user=AnonymousUser())
        ids = list(qs.values_list("pk", flat=True))
        self.assertIn(self.public_feedback.pk, ids)
        self.assertNotIn(self.private_feedback.pk, ids)

    def test_authenticated_owner_sees_own_private_feedback(self) -> None:
        qs = UserFeedback.objects.visible_to_user(user=self.owner)
        ids = list(qs.values_list("pk", flat=True))
        self.assertIn(self.public_feedback.pk, ids)
        self.assertIn(self.private_feedback.pk, ids)

    def test_other_user_cannot_see_private_feedback(self) -> None:
        other = User.objects.create_user(
            username="uf_other",
            email="uf_other@example.com",
        )
        qs = UserFeedback.objects.visible_to_user(user=other)
        ids = list(qs.values_list("pk", flat=True))
        self.assertIn(self.public_feedback.pk, ids)
        self.assertNotIn(self.private_feedback.pk, ids)


class UserFeedbackManagerGetOrNoneTest(TestCase):
    """UserFeedbackManager.get_or_none() returns None on miss, object on hit."""

    def setUp(self) -> None:
        self.owner = User.objects.create_user(
            username="gon_owner",
            email="gon_owner@example.com",
        )
        self.feedback = UserFeedback.objects.create(
            creator=self.owner,
            is_public=True,
            comment="find me",
        )

    def test_get_or_none_returns_object_on_hit(self) -> None:
        result = UserFeedback.objects.get_or_none(pk=self.feedback.pk)
        # ``assert`` narrows ``Optional[UserFeedback]`` for mypy and serves
        # as the not-None assertion for the test runner in one statement.
        assert result is not None
        self.assertEqual(result.pk, self.feedback.pk)

    def test_get_or_none_returns_none_on_miss(self) -> None:
        # Compute a pk strictly larger than any existing row so the lookup
        # is guaranteed to miss without baking in a magic constant
        # (CLAUDE.md §4: no magic numbers).
        max_existing_pk = (
            UserFeedback.objects.order_by("-pk").values_list("pk", flat=True).first()
            or 0
        )
        result = UserFeedback.objects.get_or_none(pk=max_existing_pk + 1)
        self.assertIsNone(result)

    def test_get_or_none_returns_none_for_wrong_lookup(self) -> None:
        result = UserFeedback.objects.get_or_none(comment="does-not-exist-xyz")
        self.assertIsNone(result)

    def test_get_or_none_with_kwargs_on_hit(self) -> None:
        result = UserFeedback.objects.get_or_none(
            pk=self.feedback.pk, comment="find me"
        )
        self.assertIsNotNone(result)

    def test_get_or_none_with_kwargs_on_miss(self) -> None:
        result = UserFeedback.objects.get_or_none(
            pk=self.feedback.pk, comment="wrong-comment"
        )
        self.assertIsNone(result)


class BaseVisibilityManagerSuperuserComputedNormallyTest(TestCase):
    """Exercises ``BaseVisibilityManager.visible_to_user`` directly via the
    ``Embedding`` model — it uses ``EmbeddingManager(BaseVisibilityManager)``
    which does NOT override ``visible_to_user``, so the call lands in the
    base manager's anonymous / authenticated branches.

    Scoped admin access (2026-05): there is NO superuser bypass. A no-grant
    superuser's visibility is computed exactly like a normal authenticated
    user (public + own + explicit guardian grant).

    (``Corpus.objects`` is a ``PermissionManager`` that overrides
    ``visible_to_user`` to delegate to ``PermissionQuerySet`` — using
    Corpus here would miss the base-manager code paths entirely. See
    ``PermissionManagerSuperuserComputedNormallyTest`` below for the
    PermissionQuerySet path.)
    """

    def setUp(self) -> None:
        # Lazy imports keep this test module loadable when the annotations /
        # documents apps haven't finished their AppConfig.ready() pass yet.
        from opencontractserver.annotations.models import Embedding
        from opencontractserver.documents.models import Document

        self.Embedding = Embedding

        self.owner = User.objects.create_user(
            username="bvm_owner",
            email="bvm_owner@example.com",
        )
        self.other = User.objects.create_user(
            username="bvm_other",
            email="bvm_other@example.com",
        )
        self.superuser = User.objects.create_superuser(
            username="bvm_super",
            email="bvm_super@example.com",
            password="s3cur3",
        )
        self.public_doc = Document.objects.create(
            title="Public BVM Doc", creator=self.owner, is_public=True
        )
        self.private_doc = Document.objects.create(
            title="Private BVM Doc", creator=self.owner, is_public=False
        )
        self.public_embedding = Embedding.objects.create(
            document=self.public_doc,
            embedder_path="bvm.embedder.public",
            vector_384=[0.1] * 384,
            creator=self.owner,
            is_public=True,
        )
        self.private_embedding = Embedding.objects.create(
            document=self.private_doc,
            embedder_path="bvm.embedder.private",
            vector_384=[0.2] * 384,
            creator=self.owner,
            is_public=False,
        )

    def test_superuser_has_no_blanket_access_to_embeddings(self) -> None:
        """A no-grant superuser is computed like a normal user: it sees only
        public + own + explicitly-shared embeddings, NOT the private embedding
        owned by another user (scoped admin access, 2026-05)."""
        qs = self.Embedding.objects.visible_to_user(user=self.superuser)
        ids = list(qs.values_list("pk", flat=True))
        self.assertIn(self.public_embedding.pk, ids)
        # Private embedding owned by ``self.owner`` is NOT visible to the
        # no-grant superuser.
        self.assertNotIn(self.private_embedding.pk, ids)

    def test_superuser_sees_private_embedding_via_creator(self) -> None:
        """Positive case: when the superuser is the creator of a private
        embedding it sees it through the normal creator path."""
        own_private = self.Embedding.objects.create(
            document=self.private_doc,
            embedder_path="bvm.embedder.super_own",
            vector_384=[0.3] * 384,
            creator=self.superuser,
            is_public=False,
        )
        qs = self.Embedding.objects.visible_to_user(user=self.superuser)
        ids = list(qs.values_list("pk", flat=True))
        self.assertIn(own_private.pk, ids)

    def test_anonymous_user_sees_only_public_embeddings(self) -> None:
        """Passing ``user=None`` is coerced to ``AnonymousUser`` and must
        filter to ``is_public=True`` only — the second branch in
        BaseVisibilityManager.visible_to_user."""
        qs = self.Embedding.objects.visible_to_user(user=None)
        ids = set(qs.values_list("pk", flat=True))
        self.assertIn(self.public_embedding.pk, ids)
        self.assertNotIn(self.private_embedding.pk, ids)

    def test_unrelated_user_only_sees_public_embeddings(self) -> None:
        """A non-superuser, non-owner must hit the guardian-fallback path
        and end up with public objects only (no creator match, no
        guardian rows for ``self.other``)."""
        qs = self.Embedding.objects.visible_to_user(user=self.other)
        ids = set(qs.values_list("pk", flat=True))
        self.assertIn(self.public_embedding.pk, ids)
        self.assertNotIn(self.private_embedding.pk, ids)


class PermissionManagerSuperuserComputedNormallyTest(TestCase):
    """
    PermissionManager.visible_to_user(superuser) is computed exactly like a
    normal user — NO blanket bypass (scoped admin access, 2026-05). A no-grant
    superuser does NOT see a private corpus owned by another user; granting
    READ via the normal guardian path makes it visible.

    Corpus.objects is a ``PermissionedTreeQuerySet.as_manager()`` whose
    ``visible_to_user`` filters on creator / is_public / explicit guardian
    grant, making it a convenient model to verify the normal-user computation.
    """

    def setUp(self) -> None:
        self.owner = User.objects.create_user(
            username="pm_super_owner",
            email="pm_super_owner@example.com",
        )
        self.superuser = User.objects.create_superuser(
            username="pm_superuser",
            email="pm_superuser@example.com",
            password="s3cur3",
        )
        self.public_corpus = Corpus.objects.create(
            title="PM Public Corpus",
            creator=self.owner,
            is_public=True,
        )
        self.private_corpus = Corpus.objects.create(
            title="PM Private Corpus",
            creator=self.owner,
            is_public=False,
        )

    def test_superuser_has_no_blanket_access_to_private_corpora(self) -> None:
        """No-grant superuser sees the public corpus but NOT a private corpus
        owned by another user."""
        qs = Corpus.objects.visible_to_user(user=self.superuser)
        ids = list(qs.values_list("pk", flat=True))
        self.assertIn(self.public_corpus.pk, ids)
        self.assertNotIn(self.private_corpus.pk, ids)

    def test_superuser_sees_private_corpus_after_grant(self) -> None:
        """Positive case: an explicit guardian READ grant makes the private
        corpus visible to the superuser via the normal path."""
        from guardian.shortcuts import assign_perm

        assign_perm("corpuses.read_corpus", self.superuser, self.private_corpus)
        qs = Corpus.objects.visible_to_user(user=self.superuser)
        ids = list(qs.values_list("pk", flat=True))
        self.assertIn(self.private_corpus.pk, ids)


class PermissionedTreeQuerySetSuperuserTreeFieldsTest(TestCase):
    """
    Regression guard for the ``PermissionedTreeQuerySet.visible_to_user``
    superuser branch (``shared/QuerySets.py``).

    Before the Phase A follow-up the superuser branch returned
    ``self.all().order_by("created")`` — i.e. it skipped
    ``.with_tree_fields()``, so superusers silently lost ``tree_depth`` /
    ``tree_path`` annotations on every tree queryset call. This test
    pins the post-fix invariant: the superuser path now goes through
    ``self.all().with_tree_fields()`` and the django-tree-queries
    annotations show up on each row.
    """

    def setUp(self) -> None:
        self.superuser = User.objects.create_superuser(
            username="tree_super",
            email="tree_super@example.com",
            password="s3cur3",
        )
        # Corpus.objects is a ``PermissionedTreeQuerySet.as_manager(
        # with_tree_fields=True)``, which is the surface this test pins.
        self.corpus = Corpus.objects.create(
            title="Tree Fields Corpus",
            creator=self.superuser,
            is_public=False,
        )

    def test_superuser_branch_applies_with_tree_fields(self) -> None:
        qs = Corpus.objects.visible_to_user(user=self.superuser)
        row = qs.get(pk=self.corpus.pk)
        # ``with_tree_fields`` annotates each row with ``tree_depth`` and
        # ``tree_path``; absence of either attribute means the superuser
        # branch regressed to a bare ``.all()`` call.
        self.assertTrue(
            hasattr(row, "tree_depth"),
            "Superuser visible_to_user must apply .with_tree_fields() "
            "(missing tree_depth attribute on returned row).",
        )
        self.assertTrue(
            hasattr(row, "tree_path"),
            "Superuser visible_to_user must apply .with_tree_fields() "
            "(missing tree_path attribute on returned row).",
        )


class PermissionManagerVisibleToUserViaNoteTest(TestCase):
    """``PermissionManager.visible_to_user`` is reached through models whose
    manager is built via ``PermissionManager.from_queryset(...)`` — i.e.,
    ``Note.objects`` (NoteManager) and ``Annotation.objects``.  The Corpus
    manager is a ``PermissionedTreeQuerySet.as_manager()`` and bypasses
    ``PermissionManager`` entirely, so Note is the right vehicle to verify
    the ``user is None → AnonymousUser`` coercion in the manager itself.
    """

    def setUp(self) -> None:
        from opencontractserver.annotations.models import Note
        from opencontractserver.documents.models import Document

        self.Note = Note

        self.owner = User.objects.create_user(
            username="pmnote_owner",
            email="pmnote_owner@example.com",
        )
        self.doc = Document.objects.create(
            title="PM Note Doc", creator=self.owner, is_public=True
        )
        self.public_note = Note.objects.create(
            title="public note",
            content="public",
            document=self.doc,
            creator=self.owner,
            is_public=True,
        )
        self.private_note = Note.objects.create(
            title="private note",
            content="private",
            document=self.doc,
            creator=self.owner,
            is_public=False,
        )

    def test_none_user_coerced_to_anonymous(self) -> None:
        """Calling visible_to_user(user=None) on a PermissionManager-backed
        model must coerce None → AnonymousUser and return public-only rows."""
        qs = self.Note.objects.visible_to_user(user=None)
        ids = set(qs.values_list("pk", flat=True))
        self.assertIn(self.public_note.pk, ids)
        self.assertNotIn(self.private_note.pk, ids)


class BaseVisibilityManagerAbstractModelGuardTest(TestCase):
    """``BaseVisibilityManager.visible_to_user`` raises ``RuntimeError`` when
    invoked on a manager whose ``Options.model_name`` is None — the
    Django-level invariant that signals an abstract model.  The guard is
    explicit (not ``assert``) so it survives ``python -O``.

    The check sits *outside* the broad ``except (ImportError, Exception)``
    inside ``visible_to_user`` so that the abstract-model bug surfaces
    instead of silently degrading into a creator/public fallback.
    """

    def test_runtime_error_guard_propagates_for_abstract_models(self) -> None:
        from opencontractserver.annotations.models import Embedding

        authenticated_user = User.objects.create_user(
            username="abs_guard_user",
            email="abs_guard@example.com",
        )

        # Force ``self.model._meta.model_name`` to None for the duration of
        # the call to simulate an abstract-model invocation without having
        # to register a real abstract model + manager just for the test.
        # ``_meta`` is a shared ``Options`` instance — fine for sequential
        # ``TestCase`` runs but worth being aware of: with pytest-xdist /
        # ``--dist loadscope``, classes run on isolated workers, so this
        # patch never overlaps with parallel ``Embedding`` queries.
        with patch.object(Embedding._meta, "model_name", None):
            with self.assertRaisesRegex(
                RuntimeError, "Concrete manager invoked on abstract model"
            ):
                list(Embedding.objects.visible_to_user(user=authenticated_user))
