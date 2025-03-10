import logging
import pathlib
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.corpuses.models import Corpus
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import (
    generate_permissions_md_table_for_object,
    get_user_permissions_table_data,
    get_users_permissions_for_obj,
    set_permissions_for_obj_to_user,
)

User = get_user_model()
logger = logging.getLogger(__name__)


class TestContext:
    def __init__(self, user):
        self.user = user


class PermissionUtilsTestCase(TestCase):
    """
    Tests for the permission utility functions, specifically:
    - get_users_permissions_for_obj
    - generate_permissions_md_table_for_object
    """

    fixtures_path = pathlib.Path(__file__).parent / "fixtures"

    def setUp(self):
        """
        Set up test data:
        - Create users with different roles
        - Create a corpus owned by one user
        - Set up different permissions for different users
        """
        # Create users
        self.owner = User.objects.create_user(
            username="owner", email="owner@example.com", password="password"
        )
        self.manager = User.objects.create_user(
            username="manager", email="manager@example.com", password="password"
        )
        self.viewer = User.objects.create_user(
            username="viewer", email="viewer@example.com", password="password"
        )
        self.outsider = User.objects.create_user(
            username="outsider", email="outsider@example.com", password="password"
        )
        self.superuser = User.objects.create_superuser(
            username="superuser", email="superuser@example.com", password="password"
        )

        # Create a corpus owned by the owner
        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            description="A corpus for testing permissions",
            creator=self.owner,
            is_public=False,
        )

        # Set up permissions
        # Manager gets CRUD permissions
        set_permissions_for_obj_to_user(
            self.manager, self.corpus, [PermissionTypes.CRUD]
        )
        
        # Viewer gets only READ permission
        set_permissions_for_obj_to_user(
            self.viewer, self.corpus, [PermissionTypes.READ]
        )
        
        # Outsider gets no permissions

    def test_get_users_permissions_for_obj(self):
        """
        Test that get_users_permissions_for_obj correctly returns permissions for all users.
        """
        logger.info("Testing get_users_permissions_for_obj function")
        
        # Get permissions for all users
        users = [self.owner, self.manager, self.viewer, self.outsider, self.superuser]
        permissions_map = get_user_permissions_table_data(users, self.corpus)
        
        # Check that all users are in the map
        self.assertEqual(len(permissions_map), 5)
        self.assertIn(self.owner.id, permissions_map)
        self.assertIn(self.manager.id, permissions_map)
        self.assertIn(self.viewer.id, permissions_map)
        self.assertIn(self.outsider.id, permissions_map)
        self.assertIn(self.superuser.id, permissions_map)
        
        # Check owner permissions (should have CRUD as creator)
        owner_perms = permissions_map[self.owner.id]
        self.assertTrue(owner_perms["CREATE"])
        self.assertTrue(owner_perms["READ"])
        self.assertTrue(owner_perms["UPDATE"])
        self.assertTrue(owner_perms["DELETE"])
        self.assertTrue(owner_perms["CRUD"])
        self.assertFalse(owner_perms["PUBLISH"])  # Owner doesn't automatically get PUBLISH
        self.assertFalse(owner_perms["ALL"])      # Owner doesn't automatically get ALL
        
        # Check manager permissions (should have CRUD from explicit grant)
        manager_perms = permissions_map[self.manager.id]
        self.assertTrue(manager_perms["CREATE"])
        self.assertTrue(manager_perms["READ"])
        self.assertTrue(manager_perms["UPDATE"])
        self.assertTrue(manager_perms["DELETE"])
        self.assertTrue(manager_perms["CRUD"])
        self.assertFalse(manager_perms["PUBLISH"])
        self.assertFalse(manager_perms["ALL"])
        
        # Check viewer permissions (should have only READ)
        viewer_perms = permissions_map[self.viewer.id]
        self.assertFalse(viewer_perms["CREATE"])
        self.assertTrue(viewer_perms["READ"])
        self.assertFalse(viewer_perms["UPDATE"])
        self.assertFalse(viewer_perms["DELETE"])
        self.assertFalse(viewer_perms["CRUD"])
        self.assertFalse(viewer_perms["PUBLISH"])
        self.assertFalse(viewer_perms["ALL"])
        
        # Check outsider permissions (should have none)
        outsider_perms = permissions_map[self.outsider.id]
        self.assertFalse(outsider_perms["CREATE"])
        self.assertFalse(outsider_perms["READ"])
        self.assertFalse(outsider_perms["UPDATE"])
        self.assertFalse(outsider_perms["DELETE"])
        self.assertFalse(outsider_perms["CRUD"])
        self.assertFalse(outsider_perms["PUBLISH"])
        self.assertFalse(outsider_perms["ALL"])
        
        # Check superuser permissions (should have all)
        superuser_perms = permissions_map[self.superuser.id]
        self.assertTrue(superuser_perms["CREATE"])
        self.assertTrue(superuser_perms["READ"])
        self.assertTrue(superuser_perms["UPDATE"])
        self.assertTrue(superuser_perms["DELETE"])
        self.assertTrue(superuser_perms["PERMISSION"])
        self.assertTrue(superuser_perms["PUBLISH"])
        self.assertTrue(superuser_perms["CRUD"])
        self.assertTrue(superuser_perms["ALL"])

    def test_generate_permissions_md_table_for_object(self):
        """
        Test that generate_permissions_md_table_for_object correctly generates a markdown table.
        """
        logger.info("Testing generate_permissions_md_table_for_object function")
        
        # Generate markdown table for all users
        users = [self.owner, self.manager, self.viewer, self.outsider, self.superuser]
        md_table = generate_permissions_md_table_for_object(users, self.corpus)
        
        # Check that the table has the correct structure
        lines = md_table.strip().split("\n")
        self.assertEqual(len(lines), 7)  # Header + separator + 5 users
        
        # Check header
        self.assertIn("Username", lines[0])
        self.assertIn("CREATE", lines[0])
        self.assertIn("READ", lines[0])
        self.assertIn("UPDATE", lines[0])
        self.assertIn("DELETE", lines[0])
        self.assertIn("PERMISSION", lines[0])
        self.assertIn("PUBLISH", lines[0])
        self.assertIn("CRUD", lines[0])
        self.assertIn("ALL", lines[0])
        
        # Check owner row
        owner_row = [line for line in lines if "owner" in line][0]
        self.assertIn("Yes", owner_row)  # Should have some permissions
        
        # Check viewer row
        viewer_row = [line for line in lines if "viewer" in line][0]
        self.assertIn("Yes", viewer_row)  # Should have READ permission
        self.assertIn("No", viewer_row)   # Should not have other permissions
        
        # Check outsider row
        outsider_row = [line for line in lines if "outsider" in line][0]
        self.assertIn("No", outsider_row)  # Should have no permissions
        self.assertNotIn("Yes", outsider_row)
        
        # Check superuser row
        superuser_row = [line for line in lines if "superuser" in line][0]
        self.assertNotIn("No", superuser_row)  # Should have all permissions
        
        # Make corpus public and check changes
        self.corpus.is_public = True
        self.corpus.save()
        
        md_table_public = generate_permissions_md_table_for_object(users, self.corpus)
        lines_public = md_table_public.strip().split("\n")
        
        # Now outsider should have READ permission
        outsider_row_public = [line for line in lines_public if "outsider" in line][0]
        self.assertIn("Yes", outsider_row_public)  # Should now have READ permission

    def test_with_empty_user_list(self):
        """
        Test that the functions handle empty user lists gracefully.
        """
        # Test with empty user list
        empty_permissions = get_user_permissions_table_data([], self.corpus)
        self.assertEqual(empty_permissions, {})
        
        empty_table = generate_permissions_md_table_for_object([], self.corpus)
        lines = empty_table.strip().split("\n")
        self.assertEqual(len(lines), 2)  # Just header + separator, no user rows

    def test_with_user_without_id(self):
        """
        Test that the functions handle users without IDs gracefully.
        """
        # Create a user without saving (so it has no ID)
        user_without_id = User(username="no_id", email="no_id@example.com")
        
        # Test with user without ID
        permissions = get_user_permissions_table_data([user_without_id], self.corpus)
        self.assertEqual(permissions, {})
        
        table = generate_permissions_md_table_for_object([user_without_id], self.corpus)
        lines = table.strip().split("\n")
        print(f"test_with_user_without_id - lines: {lines}")
        self.assertEqual(len(lines), 2)  # Just header + separator, no user rows
