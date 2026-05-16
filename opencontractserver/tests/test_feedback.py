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
    """Tests for UserFeedbackQuerySet.visible_to_user and manager delegation."""

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
        cls.document = Document.objects.create(
            title="Vis Doc",
            creator=cls.owner,
            file_type="application/pdf",
        )
        cls.label = AnnotationLabel.objects.create(
            text="VisLabel",
            creator=cls.owner,
            label_type=LabelType.TOKEN_LABEL,
        )
        cls.public_annotation = Annotation.objects.create(
            page=1,
            raw_text="Public",
            annotation_label=cls.label,
            document=cls.document,
            corpus=cls.corpus,
            creator=cls.owner,
            is_public=True,
        )
        cls.private_annotation = Annotation.objects.create(
            page=2,
            raw_text="Private",
            annotation_label=cls.label,
            document=cls.document,
            corpus=cls.corpus,
            creator=cls.owner,
            is_public=False,
        )

        # Public feedback
        cls.public_feedback = UserFeedback.objects.create(
            creator=cls.owner,
            commented_annotation=cls.public_annotation,
            is_public=True,
            comment="Public fb",
        )
        # Private feedback by owner, on public annotation
        cls.private_feedback_public_ann = UserFeedback.objects.create(
            creator=cls.owner,
            commented_annotation=cls.public_annotation,
            is_public=False,
            comment="Private fb, public ann",
        )
        # Private feedback by owner, on private annotation
        cls.private_feedback_private_ann = UserFeedback.objects.create(
            creator=cls.owner,
            commented_annotation=cls.private_annotation,
            is_public=False,
            comment="Private fb, private ann",
        )
        # Private feedback by other user
        cls.other_user_feedback = UserFeedback.objects.create(
            creator=cls.other_user,
            commented_annotation=cls.private_annotation,
            is_public=False,
            comment="Other user fb",
        )

    def test_superuser_sees_all(self):
        qs = UserFeedback.objects.visible_to_user(self.superuser)
        self.assertEqual(qs.count(), 4)

    def test_anonymous_sees_public_or_on_public_annotation(self):
        """Anonymous READ visibility mirrors ``UserFeedbackManager.user_can``
        (Phase A invariant): a feedback is visible to anonymous when it
        is itself public OR comments on a public annotation. The
        commented-annotation grant is symmetric across the anonymous
        and authenticated branches so the manager check and the
        queryset filter answer the same question for the same user."""
        anon = AnonymousUser()
        qs = UserFeedback.objects.visible_to_user(anon)
        ids = set(qs.values_list("id", flat=True))
        # Public feedback → visible.
        self.assertIn(self.public_feedback.id, ids)
        # Private feedback on a PUBLIC annotation → visible (new in Phase A,
        # mirrors user_can's commented_annotation.is_public READ grant).
        self.assertIn(self.private_feedback_public_ann.id, ids)
        # Private feedback on a PRIVATE annotation → NOT visible.
        self.assertNotIn(self.private_feedback_private_ann.id, ids)
        self.assertNotIn(self.other_user_feedback.id, ids)

    def test_owner_sees_own_and_public(self):
        qs = UserFeedback.objects.visible_to_user(self.owner)
        ids = set(qs.values_list("id", flat=True))
        # Owner sees: public feedback, own private feedbacks (all 3 are owned)
        # Also sees other_user_feedback if public annotation linked - but
        # other_user_feedback is linked to private annotation
        self.assertEqual(qs.count(), 3)
        self.assertIn(self.public_feedback.id, ids)
        self.assertIn(self.private_feedback_public_ann.id, ids)
        self.assertIn(self.private_feedback_private_ann.id, ids)

    def test_other_user_sees_own_public_and_public_annotation(self):
        qs = UserFeedback.objects.visible_to_user(self.other_user)
        ids = set(qs.values_list("id", flat=True))
        # Sees: public_feedback (is_public=True)
        # Sees: private_feedback_public_ann (commented_annotation.is_public=True)
        # Sees: other_user_feedback (creator=other_user)
        self.assertIn(self.public_feedback.id, ids)
        self.assertIn(self.private_feedback_public_ann.id, ids)
        self.assertIn(self.other_user_feedback.id, ids)
        # Does NOT see: private_feedback_private_ann
        self.assertNotIn(self.private_feedback_private_ann.id, ids)

    def test_get_or_none_existing(self):
        result = UserFeedback.objects.get_or_none(pk=self.public_feedback.pk)
        self.assertEqual(result, self.public_feedback)

    def test_get_or_none_nonexistent(self):
        result = UserFeedback.objects.get_or_none(pk=999999)
        self.assertIsNone(result)
