"""
Tests for creator-based permission fallback in get_users_permissions_for_obj.

Models without django-guardian permission tables (like AnnotationLabel) use
creator-based permissions instead. This test file verifies that:
1. Superusers get all CRUD permissions
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
from opencontractserver.utils.permissioning import (
    get_users_permissions_for_obj,
    user_has_permission_for_obj,
)

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

    def test_superuser_gets_all_permissions_on_annotation_label(self):
        """Superuser should get all CRUD permissions on AnnotationLabel."""
        permissions = get_users_permissions_for_obj(
            user=self.superuser,
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
            f"Superuser should have all CRUD permissions, got: {permissions}",
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

    def test_user_has_permission_for_obj_read_creator(self):
        """user_has_permission_for_obj should return True for creator reading."""
        has_read = user_has_permission_for_obj(
            user_val=self.user1,
            instance=self.annotation_label,
            permission=PermissionTypes.READ,
        )
        self.assertTrue(has_read, "Creator should have READ permission")

    def test_user_has_permission_for_obj_update_creator(self):
        """user_has_permission_for_obj should return True for creator updating."""
        has_update = user_has_permission_for_obj(
            user_val=self.user1,
            instance=self.annotation_label,
            permission=PermissionTypes.UPDATE,
        )
        self.assertTrue(has_update, "Creator should have UPDATE permission")

    def test_user_has_permission_for_obj_delete_creator(self):
        """user_has_permission_for_obj should return True for creator deleting."""
        has_delete = user_has_permission_for_obj(
            user_val=self.user1,
            instance=self.annotation_label,
            permission=PermissionTypes.DELETE,
        )
        self.assertTrue(has_delete, "Creator should have DELETE permission")

    def test_user_has_permission_for_obj_read_other_user(self):
        """user_has_permission_for_obj should return False for other user reading private."""
        has_read = user_has_permission_for_obj(
            user_val=self.user2,
            instance=self.annotation_label,
            permission=PermissionTypes.READ,
        )
        self.assertFalse(
            has_read, "Other user should NOT have READ permission on private label"
        )

    def test_user_has_permission_for_obj_superuser(self):
        """user_has_permission_for_obj should return True for superuser on any permission."""
        for perm in [
            PermissionTypes.READ,
            PermissionTypes.UPDATE,
            PermissionTypes.DELETE,
        ]:
            has_perm = user_has_permission_for_obj(
                user_val=self.superuser,
                instance=self.annotation_label,
                permission=perm,
            )
            self.assertTrue(has_perm, f"Superuser should have {perm} permission")


class GuardianModelSuperuserPermissionsTestCase(TestCase):
    """
    Tests that superusers get the full extended permission set on
    guardian-enabled models (comment, publish, permission beyond CRUD).
    """

    def setUp(self):
        with transaction.atomic():
            self.superuser = User.objects.create_superuser(
                username="guardian_superuser", password="super12345"
            )
            self.other_user = User.objects.create_user(
                username="guardian_other", password="test12345"
            )

        # Create a corpus owned by a different user
        from opencontractserver.corpuses.models import Corpus

        with transaction.atomic():
            self.corpus = Corpus.objects.create(
                title="Superuser Test Corpus",
                description="Corpus for testing superuser guardian permissions",
                creator=self.other_user,
            )

    def test_superuser_gets_all_guardian_permissions(self):
        """Superuser who is NOT the creator should get the full 7-permission set."""
        permissions = get_users_permissions_for_obj(
            user=self.superuser,
            instance=self.corpus,
        )

        expected_perms = {
            "create_corpus",
            "read_corpus",
            "update_corpus",
            "remove_corpus",
            "comment_corpus",
            "publish_corpus",
            "permission_corpus",
        }

        self.assertEqual(
            permissions,
            expected_perms,
            f"Superuser should have all 7 guardian permissions, got: {permissions}",
        )

    def test_superuser_has_each_permission_type(self):
        """Verify user_has_permission_for_obj returns True for every permission type."""
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
            has_perm = user_has_permission_for_obj(
                user_val=self.superuser,
                instance=self.corpus,
                permission=perm,
            )
            self.assertTrue(
                has_perm,
                f"Superuser should have {perm} permission on corpus, but got False",
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
            instance=mock_instance,
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
            instance=mock_instance,
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
        """user_has_permission_for_obj should work with user ID as well as user object."""
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
        has_read = user_has_permission_for_obj(
            user_val=self.user1.id,
            instance=label,
            permission=PermissionTypes.READ,
        )
        self.assertTrue(has_read, "Should work with user ID")

        # Test with user ID (string)
        has_read_str = user_has_permission_for_obj(
            user_val=str(self.user1.id),
            instance=label,
            permission=PermissionTypes.READ,
        )
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
        has_crud = user_has_permission_for_obj(
            user_val=self.user1,
            instance=label,
            permission=PermissionTypes.CRUD,
        )
        self.assertTrue(has_crud, "Creator should have CRUD permissions")

        # Other user should NOT have CRUD
        has_crud_other = user_has_permission_for_obj(
            user_val=self.user2,
            instance=label,
            permission=PermissionTypes.CRUD,
        )
        self.assertFalse(has_crud_other, "Other user should NOT have CRUD permissions")
