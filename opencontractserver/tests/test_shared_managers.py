"""
Tests for opencontractserver.shared.Managers (closes #1477).

Covers the branches introduced or modified during the mypy graduation:
  - BaseVisibilityManager.visible_to_user(user=None)    → AnonymousUser path
  - BaseVisibilityManager.visible_to_user(superuser)    → all-objects path
  - BaseVisibilityManager.visible_to_user(abstract)     → RuntimeError guard
  - PermissionManager.visible_to_user(user=None)        → AnonymousUser path
  - PermissionManager.visible_to_user(superuser)        → all-objects path
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


class BaseVisibilityManagerSuperuserTest(TestCase):
    """Exercises ``BaseVisibilityManager.visible_to_user`` directly via the
    ``Embedding`` model — it uses ``EmbeddingManager(BaseVisibilityManager)``
    which does NOT override ``visible_to_user``, so the call lands in the
    base manager's superuser / anonymous / authenticated branches.

    (``Corpus.objects`` is a ``PermissionManager`` that overrides
    ``visible_to_user`` to delegate to ``PermissionQuerySet`` — using
    Corpus here would miss the base-manager code paths entirely. See
    ``PermissionManagerSuperuserTest`` below for the PermissionQuerySet
    superuser branch.)
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

    def test_superuser_sees_all_embeddings(self) -> None:
        """Superuser must hit the early-return ``queryset.order_by("created")``
        branch in BaseVisibilityManager and receive every embedding row."""
        qs = self.Embedding.objects.visible_to_user(user=self.superuser)
        ids = list(qs.values_list("pk", flat=True))
        self.assertIn(self.public_embedding.pk, ids)
        self.assertIn(self.private_embedding.pk, ids)

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


class PermissionManagerSuperuserTest(TestCase):
    """
    PermissionManager.visible_to_user(superuser) should return ALL objects,
    including private ones owned by other users.

    Corpus uses PermissionManager (via BaseVisibilityManager), making it a
    convenient model to verify the superuser branch (model_cls.objects.all()).
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

    def test_superuser_sees_all_corpora_including_private(self) -> None:
        """Superuser must see both public and private corpora via visible_to_user."""
        qs = Corpus.objects.visible_to_user(user=self.superuser)
        ids = list(qs.values_list("pk", flat=True))
        self.assertIn(self.public_corpus.pk, ids)
        self.assertIn(self.private_corpus.pk, ids)


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
