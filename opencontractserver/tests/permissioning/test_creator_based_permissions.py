"""
Tests for creator-based permission fallback in get_users_permissions_for_obj.

Models without django-guardian permission tables (like AnnotationLabel) use
creator-based permissions instead. This test file verifies that:
1. Superusers are computed like any other user (no blanket grant) — a
   no-grant superuser is a "stranger" and gets only what is_public/creator
   would give.
2. Creators get all CRUD permissions on their own objects
3. Other users get no permissions on private objects
4. All users get read permission on public objects
"""

import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase

from opencontractserver.annotations.models import TOKEN_LABEL, AnnotationLabel, LabelSet
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import get_users_permissions_for_obj

User = get_user_model()
logger = logging.getLogger(__name__)


class CreatorBasedPermissionsTestCase(TestCase):
    """
    Tests that creator-based permission fallback works correctly for models
    without django-guardian permission tables (e.g., AnnotationLabel).
    """

    def setUp(self):
        """Set up test users and objects."""
        # Create regular users
        with transaction.atomic():
            self.user1 = User.objects.create_user(
                username="creator_user", password="test12345"
            )
            self.user2 = User.objects.create_user(
                username="other_user", password="test12345"
            )
            self.superuser = User.objects.create_superuser(
                username="super_user", password="super12345"
            )

        # Create a labelset owned by user1
        with transaction.atomic():
            self.labelset = LabelSet.objects.create(
                title="Test LabelSet",
                description="Test labelset for permissions",
                creator=self.user1,
            )

        # Create an annotation label owned by user1 (linked to labelset)
        with transaction.atomic():
            self.annotation_label = AnnotationLabel.objects.create(
                text="Test Label",
                description="A test label",
                color="#FF0000",
                icon="tag",
                label_type=TOKEN_LABEL,
                creator=self.user1,
            )
            # Link to labelset
            self.labelset.annotation_labels.add(self.annotation_label)

    def test_annotation_label_lacks_guardian_permissions(self):
        """Verify that AnnotationLabel doesn't have guardian permission tables."""
        model_name = self.annotation_label._meta.model_name
        has_guardian_perms = hasattr(
            self.annotation_label, f"{model_name}userobjectpermission_set"
        )
        self.assertFalse(
            has_guardian_perms,
            "AnnotationLabel should NOT have django-guardian permission tables",
        )

    def test_no_grant_superuser_treated_as_stranger_on_annotation_label(self):
        """A no-grant superuser is computed like a stranger on a private label.

        Under the scoped-admin contract (2026-05) a superuser gets NO blanket
        grant. The label here is owned by ``user1`` and is not public, so the
        superuser — who is neither the creator nor helped by ``is_public`` —
        gets an empty permission set, exactly like any other non-creator.
        """
        permissions = get_users_permissions_for_obj(
            user=self.superuser,
            instance=self.annotation_label,
        )

        self.assertEqual(
            permissions,
            set(),
            "No-grant superuser should be treated as a stranger (empty set) on "
            f"a private, stranger-owned label, got: {permissions}",
        )

    def test_creator_gets_all_permissions_on_own_annotation_label(self):
        """Creator should get all CRUD permissions on their own AnnotationLabel."""
        permissions = get_users_permissions_for_obj(
            user=self.user1,
            instance=self.annotation_label,
        )

        expected_perms = {
            "create_annotationlabel",
            "read_annotationlabel",
            "update_annotationlabel",
            "remove_annotationlabel",
        }

        self.assertEqual(
            permissions,
            expected_perms,
            f"Creator should have all CRUD permissions, got: {permissions}",
        )

    def test_other_user_gets_no_permissions_on_private_annotation_label(self):
        """Non-creator, non-superuser should get no permissions on private label."""
        permissions = get_users_permissions_for_obj(
            user=self.user2,
            instance=self.annotation_label,
        )

        self.assertEqual(
            permissions,
            set(),
            f"Other user should have no permissions on private label, got: {permissions}",
        )

    def test_user_can_read_creator(self):
        """user_can should return True for creator reading."""
        has_read = self.annotation_label.user_can(self.user1, PermissionTypes.READ)
        self.assertTrue(has_read, "Creator should have READ permission")

    def test_user_can_update_creator(self):
        """user_can should return True for creator updating."""
        has_update = self.annotation_label.user_can(self.user1, PermissionTypes.UPDATE)
        self.assertTrue(has_update, "Creator should have UPDATE permission")

    def test_user_can_delete_creator(self):
        """user_can should return True for creator deleting."""
        has_delete = self.annotation_label.user_can(self.user1, PermissionTypes.DELETE)
        self.assertTrue(has_delete, "Creator should have DELETE permission")

    def test_user_can_read_other_user(self):
        """user_can should return False for other user reading private."""
        has_read = self.annotation_label.user_can(self.user2, PermissionTypes.READ)
        self.assertFalse(
            has_read, "Other user should NOT have READ permission on private label"
        )

    def test_user_can_superuser_computed_normally(self):
        """user_can is computed normally for a no-grant superuser.

        The label is owned by ``user1`` and is not public, so a superuser with
        no grants is denied every permission (READ/UPDATE/DELETE) exactly like
        a stranger — there is no blanket superuser bypass for data access.
        """
        for perm in [
            PermissionTypes.READ,
            PermissionTypes.UPDATE,
            PermissionTypes.DELETE,
        ]:
            has_perm = self.annotation_label.user_can(self.superuser, perm)
            self.assertFalse(
                has_perm,
                f"No-grant superuser should be denied {perm} on a private, "
                "stranger-owned label",
            )


class GuardianModelSuperuserComputedLikeNormalUserTestCase(TestCase):
    """
    Regression guard for the scoped-admin contract (2026-05): on
    guardian-enabled models a superuser is computed exactly like a normal
    user. A no-grant superuser gets NO blanket grant — its permission set is
    the real guardian/creator/is_public grant set, which here (stranger-owned,
    private corpus) is empty.
    """

    def setUp(self):
        with transaction.atomic():
            self.superuser = User.objects.create_superuser(
                username="guardian_superuser", password="super12345"
            )
            self.other_user = User.objects.create_user(
                username="guardian_other", password="test12345"
            )
            # A normal, non-creator user with NO grants — the "stranger"
            # baseline the superuser is cross-checked against.
            self.other_user_no_grants = User.objects.create_user(
                username="guardian_stranger", password="test12345"
            )

        # Create a corpus owned by a different user
        from opencontractserver.corpuses.models import Corpus

        with transaction.atomic():
            self.corpus = Corpus.objects.create(
                title="Superuser Test Corpus",
                description="Corpus for testing superuser guardian permissions",
                creator=self.other_user,
            )

    def test_no_grant_superuser_gets_real_grant_set(self):
        """A no-grant superuser gets the REAL grant set, not the full 7 perms.

        The corpus is owned by ``other_user`` and is private, so the superuser
        — neither creator nor aided by ``is_public`` and holding no guardian
        grants — has an empty permission set, identical to what a normal
        non-creator user with no grants would have.
        """
        permissions = get_users_permissions_for_obj(
            user=self.superuser,
            instance=self.corpus,
        )

        # Cross-check: a normal stranger user computes to the same empty set.
        normal_user_permissions = get_users_permissions_for_obj(
            user=self.other_user_no_grants,
            instance=self.corpus,
        )

        self.assertEqual(
            permissions,
            set(),
            "No-grant superuser should get the real (empty) grant set on a "
            f"private, stranger-owned corpus, got: {permissions}",
        )
        self.assertEqual(
            permissions,
            normal_user_permissions,
            "Superuser grant set should equal a normal stranger's grant set",
        )

    def test_no_grant_superuser_has_each_permission_type_like_normal_user(self):
        """user_can is computed normally for every permission type.

        With no grants on a private, stranger-owned corpus, a superuser is
        denied every permission — exactly like a normal non-creator user.
        """
        for perm in [
            PermissionTypes.READ,
            PermissionTypes.CREATE,
            PermissionTypes.UPDATE,
            PermissionTypes.DELETE,
            PermissionTypes.COMMENT,
            PermissionTypes.PUBLISH,
            PermissionTypes.PERMISSION,
            PermissionTypes.ALL,
        ]:
            has_perm = self.corpus.user_can(self.superuser, perm)
            self.assertFalse(
                has_perm,
                f"No-grant superuser should be denied {perm} on a private, "
                "stranger-owned corpus",
            )


class CreatorBasedPermissionsPublicObjectTestCase(TestCase):
    """
    Tests for public objects with creator-based permissions.
    Note: AnnotationLabel doesn't have is_public field, so we test with a mock
    or skip this if there's no suitable model.
    """

    def setUp(self):
        """Set up test users."""
        with transaction.atomic():
            self.user1 = User.objects.create_user(
                username="creator_public", password="test12345"
            )
            self.user2 = User.objects.create_user(
                username="reader_public", password="test12345"
            )

    def test_public_labelset_readable_by_all(self):
        """
        LabelSet with is_public=True should be readable by all users.
        Note: LabelSet uses guardian permissions, but this tests the is_public check
        in the guardian permission path (line 265-266 in permissioning.py)
        """
        # Create a public labelset
        with transaction.atomic():
            public_labelset = LabelSet.objects.create(
                title="Public LabelSet",
                description="A public labelset",
                creator=self.user1,
                is_public=True,
            )

        # LabelSet has guardian permissions, so this tests the is_public check
        # in the guardian permission path (line 265-266 in permissioning.py)
        permissions = get_users_permissions_for_obj(
            user=self.user2,
            instance=public_labelset,
        )

        # Should at least have read permission due to is_public
        self.assertIn(
            "read_labelset",
            permissions,
            "Public labelset should be readable by any user",
        )

    def test_public_object_without_guardian_permissions_readable_by_all(self):
        """
        Test the is_public branch in creator-based permissions code path.

        This tests the case where a model without guardian permission tables
        has is_public=True, which should grant read permission to any user.
        We use a simple class to simulate this since AnnotationLabel doesn't
        have an is_public field.
        """

        # Create a simple class that simulates a model without guardian permissions
        # but with is_public=True
        class MockModelMeta:
            model_name = "mockmodel"
            app_label = "mockapp"

        class MockPublicModel:
            _meta = MockModelMeta()
            creator_id = -999  # Different from any real user
            is_public = True

        mock_instance = MockPublicModel()

        permissions = get_users_permissions_for_obj(
            user=self.user2,
            instance=mock_instance,  # type: ignore[arg-type]
        )

        # Should have read permission due to is_public=True
        self.assertIn(
            "read_mockmodel",
            permissions,
            "Public object without guardian permissions should be readable by any user",
        )

    def test_non_public_non_creator_object_without_guardian_permissions(self):
        """
        Test that non-public objects without guardian permissions are not readable
        by non-creator, non-superuser users.
        """

        # Create a simple class that simulates a model without guardian permissions
        # and is_public=False
        class MockModelMeta:
            model_name = "mockmodel"
            app_label = "mockapp"

        class MockPrivateModel:
            _meta = MockModelMeta()
            creator_id = -999  # Different from any real user
            is_public = False

        mock_instance = MockPrivateModel()

        permissions = get_users_permissions_for_obj(
            user=self.user2,
            instance=mock_instance,  # type: ignore[arg-type]
        )

        # Should have no permissions
        self.assertEqual(
            permissions,
            set(),
            "Non-public object without guardian permissions should not be readable by other users",
        )


class CreatorBasedPermissionsEdgeCasesTestCase(TestCase):
    """Edge cases for creator-based permission fallback."""

    def setUp(self):
        """Set up test users."""
        with transaction.atomic():
            self.user1 = User.objects.create_user(
                username="edge_user1", password="test12345"
            )
            self.user2 = User.objects.create_user(
                username="edge_user2", password="test12345"
            )

    def test_permissions_with_user_id_instead_of_user_object(self):
        """user_can should work with user ID as well as user object."""
        with transaction.atomic():
            label = AnnotationLabel.objects.create(
                text="ID Test Label",
                description="Test",
                color="#00FF00",
                icon="tag",
                label_type=TOKEN_LABEL,
                creator=self.user1,
            )

        # Test with user ID (integer)
        has_read = label.user_can(self.user1.id, PermissionTypes.READ)
        self.assertTrue(has_read, "Should work with user ID")

        # Test with user ID (string)
        has_read_str = label.user_can(str(self.user1.id), PermissionTypes.READ)
        self.assertTrue(has_read_str, "Should work with user ID as string")

    def test_crud_permission_check(self):
        """Test CRUD permission type checking for creator-based permissions."""
        with transaction.atomic():
            label = AnnotationLabel.objects.create(
                text="CRUD Test Label",
                description="Test",
                color="#0000FF",
                icon="tag",
                label_type=TOKEN_LABEL,
                creator=self.user1,
            )

        # Creator should have CRUD
        has_crud = label.user_can(self.user1, PermissionTypes.CRUD)
        self.assertTrue(has_crud, "Creator should have CRUD permissions")

        # Other user should NOT have CRUD
        has_crud_other = label.user_can(self.user2, PermissionTypes.CRUD)
        self.assertFalse(has_crud_other, "Other user should NOT have CRUD permissions")
