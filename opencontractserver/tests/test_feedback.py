"""
Tests for the feedback module: UserFeedback model, UserFeedbackQuerySet,
and UserFeedbackManager.

Covers model validation, queryset filtering methods, and visibility logic.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from opencontractserver.annotations.models import Annotation, AnnotationLabel
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.feedback.models import (
    UserFeedback,
    UserFeedbackGroupObjectPermission,
    UserFeedbackUserObjectPermission,
)
from opencontractserver.types.enums import LabelType

User = get_user_model()


class TestUserFeedbackModel(TestCase):
    """Tests for UserFeedback model fields, validation, and save logic."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="feedback_user", password="testpass123"
        )
        cls.corpus = Corpus.objects.create(
            title="Test Corpus", creator=cls.user, is_public=True
        )
        cls.document = Document.objects.create(
            title="Test Doc",
            creator=cls.user,
            file_type="application/pdf",
        )
        cls.label = AnnotationLabel.objects.create(
            text="TestLabel",
            creator=cls.user,
            label_type=LabelType.TOKEN_LABEL,
        )
        cls.annotation = Annotation.objects.create(
            page=1,
            raw_text="Test text",
            annotation_label=cls.label,
            document=cls.document,
            corpus=cls.corpus,
            creator=cls.user,
        )

    def test_create_feedback_defaults(self):
        feedback = UserFeedback.objects.create(
            creator=self.user,
            commented_annotation=self.annotation,
        )
        self.assertFalse(feedback.approved)
        self.assertFalse(feedback.rejected)
        self.assertEqual(feedback.comment, "")
        self.assertEqual(feedback.markdown, "")
        self.assertEqual(feedback.metadata, {})
        self.assertFalse(feedback.is_public)
        self.assertIsNotNone(feedback.created)
        self.assertIsNotNone(feedback.modified)

    def test_create_approved_feedback(self):
        feedback = UserFeedback.objects.create(
            creator=self.user,
            commented_annotation=self.annotation,
            approved=True,
            comment="Looks good",
        )
        self.assertTrue(feedback.approved)
        self.assertFalse(feedback.rejected)
        self.assertEqual(feedback.comment, "Looks good")

    def test_create_rejected_feedback(self):
        feedback = UserFeedback.objects.create(
            creator=self.user,
            commented_annotation=self.annotation,
            rejected=True,
            comment="Needs work",
        )
        self.assertFalse(feedback.approved)
        self.assertTrue(feedback.rejected)

    def test_create_both_approved_and_rejected_raises(self):
        with self.assertRaises(ValidationError):
            UserFeedback.objects.create(
                creator=self.user,
                commented_annotation=self.annotation,
                approved=True,
                rejected=True,
            )

    def test_update_to_approved_clears_rejected(self):
        """When updating an existing rejected feedback to approved,
        the clean method should set rejected=False."""
        feedback = UserFeedback.objects.create(
            creator=self.user,
            commented_annotation=self.annotation,
            rejected=True,
        )
        feedback.approved = True
        # Now both are True - clean() should resolve by clearing rejected
        feedback.save()
        feedback.refresh_from_db()
        self.assertTrue(feedback.approved)
        self.assertFalse(feedback.rejected)

    def test_update_to_rejected_clears_approved(self):
        """When updating an existing approved feedback to rejected,
        the clean method should set approved=False."""
        feedback = UserFeedback.objects.create(
            creator=self.user,
            commented_annotation=self.annotation,
            approved=True,
        )
        feedback.rejected = True
        # Now both are True - clean() should resolve by clearing approved
        feedback.save()
        feedback.refresh_from_db()
        self.assertFalse(feedback.approved)
        self.assertTrue(feedback.rejected)

    def test_create_without_annotation(self):
        feedback = UserFeedback.objects.create(
            creator=self.user,
            comment="General feedback",
        )
        self.assertIsNone(feedback.commented_annotation)
        self.assertEqual(feedback.comment, "General feedback")

    def test_annotation_deletion_sets_null(self):
        """ForeignKey has on_delete=SET_NULL."""
        annotation = Annotation.objects.create(
            page=1,
            raw_text="Temp",
            annotation_label=self.label,
            document=self.document,
            corpus=self.corpus,
            creator=self.user,
        )
        feedback = UserFeedback.objects.create(
            creator=self.user,
            commented_annotation=annotation,
        )
        annotation.delete()
        feedback.refresh_from_db()
        self.assertIsNone(feedback.commented_annotation)

    def test_metadata_nullable_json(self):
        feedback = UserFeedback.objects.create(
            creator=self.user,
            metadata={"key": "value", "nested": [1, 2, 3]},
        )
        feedback.refresh_from_db()
        self.assertEqual(feedback.metadata["key"], "value")
        self.assertEqual(feedback.metadata["nested"], [1, 2, 3])

    def test_metadata_null(self):
        feedback = UserFeedback.objects.create(
            creator=self.user,
            metadata=None,
        )
        feedback.refresh_from_db()
        self.assertIsNone(feedback.metadata)

    def test_custom_permissions_exist(self):
        perm_codenames = {p[0] for p in UserFeedback._meta.permissions}
        expected = {
            "permission_userfeedback",
            "publish_userfeedback",
            "create_userfeedback",
            "read_userfeedback",
            "update_userfeedback",
            "remove_userfeedback",
            "comment_userfeedback",
        }
        self.assertEqual(perm_codenames, expected)

    def test_guardian_user_permission_model(self):
        from django.contrib.auth.models import Permission

        feedback = UserFeedback.objects.create(creator=self.user)
        permission = Permission.objects.get(
            codename="read_userfeedback",
            content_type__app_label="feedback",
        )
        perm = UserFeedbackUserObjectPermission(
            content_object=feedback,
            user=self.user,
            permission=permission,
        )
        self.assertEqual(perm.content_object, feedback)

    def test_guardian_group_permission_model(self):
        from django.contrib.auth.models import Group, Permission

        feedback = UserFeedback.objects.create(creator=self.user)
        group = Group.objects.create(name="test_feedback_group")
        permission = Permission.objects.get(
            codename="read_userfeedback",
            content_type__app_label="feedback",
        )
        perm = UserFeedbackGroupObjectPermission(
            content_object=feedback,
            group=group,
            permission=permission,
        )
        self.assertEqual(perm.content_object, feedback)


class TestUserFeedbackQuerySet(TestCase):
    """Tests for UserFeedbackQuerySet filtering methods."""

    @classmethod
    def setUpTestData(cls):
        cls.user1 = User.objects.create_user(
            username="qs_user1", password="testpass123"
        )
        cls.user2 = User.objects.create_user(
            username="qs_user2", password="testpass123"
        )
        cls.corpus = Corpus.objects.create(
            title="QS Corpus", creator=cls.user1, is_public=True
        )
        cls.document = Document.objects.create(
            title="QS Doc",
            creator=cls.user1,
            file_type="application/pdf",
        )
        cls.label = AnnotationLabel.objects.create(
            text="QSLabel",
            creator=cls.user1,
            label_type=LabelType.TOKEN_LABEL,
        )
        cls.annotation = Annotation.objects.create(
            page=1,
            raw_text="QS text",
            annotation_label=cls.label,
            document=cls.document,
            corpus=cls.corpus,
            creator=cls.user1,
        )

        # Create various feedback items
        cls.approved_feedback = UserFeedback.objects.create(
            creator=cls.user1,
            commented_annotation=cls.annotation,
            approved=True,
            comment="Approved feedback",
        )
        cls.rejected_feedback = UserFeedback.objects.create(
            creator=cls.user1,
            commented_annotation=cls.annotation,
            rejected=True,
            comment="Rejected feedback",
        )
        cls.pending_feedback = UserFeedback.objects.create(
            creator=cls.user2,
            commented_annotation=cls.annotation,
            comment="",
        )
        cls.commented_pending = UserFeedback.objects.create(
            creator=cls.user2,
            commented_annotation=cls.annotation,
            comment="Has a comment but pending",
        )

    def test_approved_filter(self):
        qs = UserFeedback.objects.approved()
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first(), self.approved_feedback)

    def test_rejected_filter(self):
        qs = UserFeedback.objects.rejected()
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first(), self.rejected_feedback)

    def test_pending_filter(self):
        qs = UserFeedback.objects.pending()
        self.assertEqual(qs.count(), 2)
        ids = set(qs.values_list("id", flat=True))
        self.assertIn(self.pending_feedback.id, ids)
        self.assertIn(self.commented_pending.id, ids)

    def test_recent_filter(self):
        # All feedback is recent (created just now)
        qs = UserFeedback.objects.recent(days=1)
        self.assertEqual(qs.count(), 4)

    def test_recent_filter_with_old_data(self):
        # Create old feedback
        old = UserFeedback.objects.create(creator=self.user1)
        # Manually set created date to 60 days ago
        UserFeedback.objects.filter(pk=old.pk).update(
            created=timezone.now() - timedelta(days=60)
        )
        qs = UserFeedback.objects.recent(days=30)
        self.assertNotIn(old.pk, qs.values_list("id", flat=True))

    def test_with_comments_filter(self):
        qs = UserFeedback.objects.with_comments()
        self.assertEqual(qs.count(), 3)
        ids = set(qs.values_list("id", flat=True))
        self.assertNotIn(self.pending_feedback.id, ids)

    def test_by_creator_filter(self):
        qs = UserFeedback.objects.by_creator(self.user1)
        self.assertEqual(qs.count(), 2)
        for fb in qs:
            self.assertEqual(fb.creator, self.user1)

    def test_by_creator_filter_user2(self):
        qs = UserFeedback.objects.by_creator(self.user2)
        self.assertEqual(qs.count(), 2)
        for fb in qs:
            self.assertEqual(fb.creator, self.user2)

    def test_chained_filters(self):
        qs = UserFeedback.objects.by_creator(self.user2).with_comments()
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first(), self.commented_pending)


class TestUserFeedbackVisibility(TestCase):
    """Tests for UserFeedbackQuerySet.visible_to_user and manager delegation.

    Feedback inherits READ visibility from the annotation it comments on
    (see ``UserFeedbackQuerySet.visible_to_user``). The fixtures below
    create annotations with different visibility profiles so each branch
    of the inherited gate can be exercised:

    - ``visible_annotation`` is structural on a public document and so
      is visible to anonymous users (matches ``AnnotationQuerySet``'s
      anonymous predicate: ``structural=True`` AND public doc).
    - ``authenticated_only_annotation`` is non-structural on a public
      document — visible to authenticated users but NOT to anonymous.
    - ``hidden_annotation`` is on a private document with no grants —
      only the owner can see it.
    """

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="vis_owner", password="testpass123"
        )
        cls.other_user = User.objects.create_user(
            username="vis_other", password="testpass123"
        )
        cls.superuser = User.objects.create_superuser(
            username="vis_super", password="testpass123"
        )
        cls.corpus = Corpus.objects.create(
            title="Vis Corpus", creator=cls.owner, is_public=True
        )
        cls.public_document = Document.objects.create(
            title="Public Vis Doc",
            creator=cls.owner,
            file_type="application/pdf",
            is_public=True,
        )
        cls.private_document = Document.objects.create(
            title="Private Vis Doc",
            creator=cls.owner,
            file_type="application/pdf",
        )
        cls.label = AnnotationLabel.objects.create(
            text="VisLabel",
            creator=cls.owner,
            label_type=LabelType.TOKEN_LABEL,
        )
        # Structural annotation on a public document — visible to
        # anonymous, authenticated, and owner.
        cls.visible_annotation = Annotation.objects.create(
            page=1,
            raw_text="Visible",
            annotation_label=cls.label,
            document=cls.public_document,
            corpus=cls.corpus,
            creator=cls.owner,
            structural=True,
        )
        # Non-structural annotation on a public document — visible to
        # authenticated users and owner, NOT visible to anonymous
        # (anonymous annotation visibility requires structural=True).
        cls.authenticated_only_annotation = Annotation.objects.create(
            page=2,
            raw_text="AuthOnly",
            annotation_label=cls.label,
            document=cls.public_document,
            corpus=cls.corpus,
            creator=cls.owner,
        )
        # Annotation on a private document — only the owner can see it.
        cls.hidden_annotation = Annotation.objects.create(
            page=1,
            raw_text="Hidden",
            annotation_label=cls.label,
            document=cls.private_document,
            creator=cls.owner,
        )

        # Feedback row that is itself ``is_public=True`` — visible to
        # everyone regardless of the commented annotation. Pairing this
        # with ``hidden_annotation`` (a fully private annotation with no
        # inherited-visibility path for non-owners) is intentional: it
        # asserts the ``is_public=True`` branch on the feedback row alone
        # grants READ, independent of annotation visibility. Do not
        # repoint to a visible annotation — that would silently collapse
        # this row's coverage into the inherited-gate tests.
        cls.public_feedback = UserFeedback.objects.create(
            creator=cls.owner,
            commented_annotation=cls.hidden_annotation,
            is_public=True,
            comment="Public fb",
        )
        # Private feedback on the structural-on-public-doc annotation.
        # Inherits visibility from the annotation, so anonymous + all
        # authenticated users see it.
        cls.feedback_on_visible_ann = UserFeedback.objects.create(
            creator=cls.owner,
            commented_annotation=cls.visible_annotation,
            is_public=False,
            comment="On visible ann",
        )
        # Private feedback on the non-structural-on-public-doc annotation.
        # Authenticated users inherit visibility from the annotation,
        # but anonymous does NOT (annotation is not structural).
        cls.feedback_on_authenticated_only_ann = UserFeedback.objects.create(
            creator=cls.owner,
            commented_annotation=cls.authenticated_only_annotation,
            is_public=False,
            comment="On authenticated-only ann",
        )
        # Private feedback on a hidden annotation — only the owner can
        # see it via the creator branch.
        cls.feedback_on_hidden_ann = UserFeedback.objects.create(
            creator=cls.owner,
            commented_annotation=cls.hidden_annotation,
            is_public=False,
            comment="On hidden ann",
        )
        # Other user's feedback on the hidden annotation — only the
        # other user can see it (via creator).
        cls.other_user_feedback = UserFeedback.objects.create(
            creator=cls.other_user,
            commented_annotation=cls.hidden_annotation,
            is_public=False,
            comment="Other user fb",
        )

    def test_superuser_sees_all(self):
        qs = UserFeedback.objects.visible_to_user(self.superuser)
        self.assertEqual(qs.count(), 5)

    def test_anonymous_sees_public_or_on_visible_annotation(self):
        """Anonymous READ visibility mirrors ``UserFeedbackManager.user_can``
        (Phase A invariant): a feedback row is visible to anonymous when
        it is itself ``is_public=True`` OR comments on an annotation
        that ``Annotation.objects.visible_to_user(AnonymousUser())``
        includes. Anonymous annotation visibility is structural + public
        doc, so the feedback follows the same gate."""
        anon = AnonymousUser()
        qs = UserFeedback.objects.visible_to_user(anon)
        ids = set(qs.values_list("id", flat=True))
        # ``is_public=True`` on the feedback row → visible regardless
        # of whether anonymous can see the commented annotation.
        self.assertIn(self.public_feedback.id, ids)
        # Feedback on a structural-on-public-doc annotation → visible
        # via inherited annotation visibility.
        self.assertIn(self.feedback_on_visible_ann.id, ids)
        # Feedback on a non-structural annotation → NOT visible to
        # anonymous (annotation is not visible to anonymous).
        self.assertNotIn(self.feedback_on_authenticated_only_ann.id, ids)
        # Feedback on a hidden annotation → NOT visible to anonymous.
        self.assertNotIn(self.feedback_on_hidden_ann.id, ids)
        self.assertNotIn(self.other_user_feedback.id, ids)

    def test_owner_sees_own_and_inherited(self):
        qs = UserFeedback.objects.visible_to_user(self.owner)
        ids = set(qs.values_list("id", flat=True))
        # Owner created 4 of the 5 rows — visible via creator. The fifth
        # (other_user_feedback) is on hidden_annotation, which the owner
        # CAN see via document-creator, so the feedback row is inherited.
        self.assertEqual(qs.count(), 5)
        self.assertIn(self.public_feedback.id, ids)
        self.assertIn(self.feedback_on_visible_ann.id, ids)
        self.assertIn(self.feedback_on_authenticated_only_ann.id, ids)
        self.assertIn(self.feedback_on_hidden_ann.id, ids)
        self.assertIn(self.other_user_feedback.id, ids)

    def test_other_user_sees_public_and_visible_annotations(self):
        qs = UserFeedback.objects.visible_to_user(self.other_user)
        ids = set(qs.values_list("id", flat=True))
        # ``is_public=True`` feedback → visible.
        self.assertIn(self.public_feedback.id, ids)
        # Annotation visible to authenticated users (structural on public doc).
        self.assertIn(self.feedback_on_visible_ann.id, ids)
        # Annotation visible to authenticated users (non-structural on public doc).
        self.assertIn(self.feedback_on_authenticated_only_ann.id, ids)
        # other_user is the creator of their own feedback row.
        self.assertIn(self.other_user_feedback.id, ids)
        # Annotation on a private document with no grants — NOT visible.
        self.assertNotIn(self.feedback_on_hidden_ann.id, ids)

    def test_guardian_doc_grant_lets_user_see_feedback_on_private_annotation(self):
        """Direct regression for Bug #2: pre-fix, ``visible_to_user`` only
        considered ``commented_annotation.is_public=True`` instead of the
        annotation's full visibility model. A user with a guardian READ
        grant on the private document — which makes the annotation
        visible — would correctly see the annotation but NOT the
        feedback. After the fix, the feedback inherits the same
        visibility surface as the annotation, so the grant flows through.

        Uses doc-level guardian grant (the production grant scope —
        annotations have no per-row guardian table) so this also exercises
        ``Annotation.objects.visible_to_user`` via the doc path.
        """
        from guardian.shortcuts import assign_perm

        third_user = User.objects.create_user(
            username="vis_guardian", password="testpass123"
        )

        # Sanity: without any grant this user sees only ``is_public``
        # feedback (no creator branch, no annotation-visibility branch).
        before_qs = UserFeedback.objects.visible_to_user(third_user)
        self.assertNotIn(self.feedback_on_hidden_ann.id, set(before_qs))

        # Grant READ on the *document* — the standard guardian scope.
        # This makes ``hidden_annotation`` show up in
        # ``Annotation.objects.visible_to_user(third_user)``, which is
        # exactly the surface the new feedback filter rides on.
        assign_perm("read_document", third_user, self.private_document)

        after_qs = UserFeedback.objects.visible_to_user(third_user)
        ids = set(after_qs.values_list("id", flat=True))
        self.assertIn(
            self.feedback_on_hidden_ann.id,
            ids,
            "guardian READ on the document should grant READ on feedback "
            "of annotations within it (Bug #2 — UserFeedback used to gate "
            "only on commented_annotation.is_public)",
        )

        # And it should also propagate to other users' feedback on the
        # same now-visible annotation.
        self.assertIn(self.other_user_feedback.id, ids)

    def test_get_or_none_existing(self):
        result = UserFeedback.objects.get_or_none(pk=self.public_feedback.pk)
        self.assertEqual(result, self.public_feedback)

    def test_get_or_none_nonexistent(self):
        result = UserFeedback.objects.get_or_none(pk=999999)
        self.assertIsNone(result)
