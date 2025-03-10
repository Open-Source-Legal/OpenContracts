import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import Signal
from django.test import TestCase
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.analyzer.models import GremlinEngine
from opencontractserver.analyzer.signals import install_gremlin_on_creation
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.documents.signals import process_doc_on_create_atomic
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import (
    get_users_permissions_for_obj,
    set_permissions_for_obj_to_user,
    user_has_permission_for_obj,
)

User = get_user_model()

logger = logging.getLogger(__name__)


class TestContext:
    def __init__(self, user):
        self.user = user


class SetUserCorpusPermissionsTestCase(TestCase):
    """
    Tests the SetUserCorpusPermissions mutation to ensure that:
    1. Users with PERMISSION rights can grant permissions to other users
    2. Users without PERMISSION rights cannot grant permissions
    3. The permissions are correctly applied to the target user
    """

    def tearDown(self):
        # Reconnect the django signals for gremlinengine create
        post_save.connect(
            install_gremlin_on_creation,
            sender=GremlinEngine,
            dispatch_uid="install_gremlin_on_creation",
        )

    def setUp(self):
        # Turn off signals to avoid side effects during testing
        Signal.disconnect(
            post_save,
            receiver=install_gremlin_on_creation,
            sender=GremlinEngine,
            dispatch_uid="Signal.disconnect.install_gremlin_on_creation",
        )

        Signal.disconnect(
            post_save,
            receiver=process_doc_on_create_atomic,
            sender=Document,
            dispatch_uid="Signal.disconnect.process_doc_on_create_atomic",
        )

        # Create three users for testing
        with transaction.atomic():
            # Owner of the corpus with full permissions
            self.owner = User.objects.create_user(
                username="Owner", password="password123"
            )
            self.owner_client = Client(schema, context_value=TestContext(self.owner))

            # User who will be granted PERMISSION rights by the owner
            self.manager = User.objects.create_user(
                username="Manager", password="password123"
            )
            self.manager_client = Client(
                schema, context_value=TestContext(self.manager)
            )

            # User who will be granted permissions by the manager
            self.viewer = User.objects.create_user(
                username="Viewer", password="password123"
            )
            self.viewer_client = Client(schema, context_value=TestContext(self.viewer))

            # User with no permissions
            self.outsider = User.objects.create_user(
                username="Outsider", password="password123"
            )
            self.outsider_client = Client(
                schema, context_value=TestContext(self.outsider)
            )

        # Create a test corpus owned by the owner
        with transaction.atomic():
            self.corpus = Corpus.objects.create(
                title="Test Permissions Corpus", creator=self.owner, backend_lock=False
            )

        # Grant ALL permissions to the owner
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.ALL])

        # Convert corpus ID to global ID for GraphQL
        self.global_corpus_id = to_global_id("CorpusType", self.corpus.id)

        # Create global IDs for users
        self.global_owner_id = to_global_id("UserType", self.owner.id)
        self.global_manager_id = to_global_id("UserType", self.manager.id)
        self.global_viewer_id = to_global_id("UserType", self.viewer.id)
        self.global_outsider_id = to_global_id("UserType", self.outsider.id)

    def test_set_user_corpus_permissions(self):
        """
        Test the SetUserCorpusPermissions mutation functionality
        """
        logger.info("----- TEST SET USER CORPUS PERMISSIONS MUTATION -----")

        # Define the mutation
        set_permissions_mutation = """
        mutation SetUserCorpusPermissions($corpusId: ID!, $userId: ID!, $permissions: [PermissionTypes!]!) {
          permissionCorpusForUser(corpusId: $corpusId, userId: $userId, permissions: $permissions) {
            ok
            message
          }
        }
        """

        # 1. Test that owner can grant PERMISSION rights to manager
        variables = {
            "corpusId": self.global_corpus_id,
            "userId": self.global_manager_id,
            "permissions": ["PERMISSION", "READ", "UPDATE"],
        }

        response = self.owner_client.execute(
            set_permissions_mutation, variable_values=variables
        )
        logger.info(f"Owner granting permissions to manager: {response}")

        self.assertTrue(response["data"]["permissionCorpusForUser"]["ok"])

        # Verify manager now has the granted permissions
        self.assertTrue(
            user_has_permission_for_obj(
                self.manager, self.corpus, PermissionTypes.PERMISSION
            )
        )
        self.assertTrue(
            user_has_permission_for_obj(self.manager, self.corpus, PermissionTypes.READ)
        )
        self.assertTrue(
            user_has_permission_for_obj(
                self.manager, self.corpus, PermissionTypes.UPDATE
            )
        )
        self.assertFalse(
            user_has_permission_for_obj(
                self.manager, self.corpus, PermissionTypes.DELETE
            )
        )

        # 2. Test that manager can grant READ permission to viewer
        variables = {
            "corpusId": self.global_corpus_id,
            "userId": self.global_viewer_id,
            "permissions": ["READ"],
        }

        response = self.manager_client.execute(
            set_permissions_mutation, variable_values=variables
        )
        logger.info(f"Manager granting READ permission to viewer: {response}")

        self.assertTrue(response["data"]["permissionCorpusForUser"]["ok"])

        # Verify viewer now has READ permission
        self.assertTrue(
            user_has_permission_for_obj(self.viewer, self.corpus, PermissionTypes.READ)
        )
        self.assertFalse(
            user_has_permission_for_obj(
                self.viewer, self.corpus, PermissionTypes.UPDATE
            )
        )

        # 3. Test that outsider cannot grant permissions
        variables = {
            "corpusId": self.global_corpus_id,
            "userId": self.global_viewer_id,
            "permissions": ["UPDATE"],
        }

        response = self.outsider_client.execute(
            set_permissions_mutation, variable_values=variables
        )
        logger.info(f"Outsider attempting to grant permissions: {response}")

        self.assertFalse(response["data"]["permissionCorpusForUser"]["ok"])
        self.assertEqual(
            response["data"]["permissionCorpusForUser"]["message"],
            "You don't have permission to change permissions on this corpus",
        )

        # Verify viewer still doesn't have UPDATE permission
        self.assertFalse(
            user_has_permission_for_obj(
                self.viewer, self.corpus, PermissionTypes.UPDATE
            )
        )

        # 4. Test that viewer cannot grant permissions (even though they have READ access)
        variables = {
            "corpusId": self.global_corpus_id,
            "userId": self.global_outsider_id,
            "permissions": ["READ"],
        }

        response = self.viewer_client.execute(
            set_permissions_mutation, variable_values=variables
        )
        logger.info(f"Viewer attempting to grant permissions: {response}")

        self.assertFalse(response["data"]["permissionCorpusForUser"]["ok"])

        # Verify outsider still has no permissions
        self.assertFalse(
            user_has_permission_for_obj(
                self.outsider, self.corpus, PermissionTypes.READ
            )
        )

        # 5. Test granting ALL permissions
        variables = {
            "corpusId": self.global_corpus_id,
            "userId": self.global_manager_id,
            "permissions": ["ALL"],
        }

        response = self.owner_client.execute(
            set_permissions_mutation, variable_values=variables
        )
        logger.info(f"Owner granting ALL permissions to manager: {response}")

        self.assertTrue(response["data"]["permissionCorpusForUser"]["ok"])

        print(
            f"Permissions for manager: {get_users_permissions_for_obj(self.manager, self.corpus)}"
        )

        # Verify manager now has ALL permissions
        self.assertTrue(
            user_has_permission_for_obj(self.manager, self.corpus, PermissionTypes.ALL)
        )

        # 6. Test removing permissions by passing empty list
        variables = {
            "corpusId": self.global_corpus_id,
            "userId": self.global_viewer_id,
            "permissions": [],
        }

        response = self.owner_client.execute(
            set_permissions_mutation, variable_values=variables
        )
        logger.info(f"Owner removing all permissions from viewer: {response}")

        self.assertTrue(response["data"]["permissionCorpusForUser"]["ok"])

        # Verify viewer now has no permissions
        self.assertFalse(
            user_has_permission_for_obj(self.viewer, self.corpus, PermissionTypes.READ)
        )

    def test_corpus_visibility_after_permission_changes(self):
        """
        Test that corpus visibility changes appropriately when permissions are granted or revoked
        """
        logger.info("----- TEST CORPUS VISIBILITY AFTER PERMISSION CHANGES -----")

        # Query to fetch corpus
        corpus_query = """
        query GetCorpus($id: ID!) {
          corpus(id: $id) {
            id
            title
            myPermissions
          }
        }
        """

        # Query to fetch all corpuses
        all_corpuses_query = """
        query {
          corpuses {
            totalCount
            edges {
              node {
                id
                title
                myPermissions
              }
            }
          }
        }
        """

        # Set permissions mutation
        set_permissions_mutation = """
        mutation SetUserCorpusPermissions($corpusId: ID!, $userId: ID!, $permissions: [PermissionTypes!]!) {
          permissionCorpusForUser(corpusId: $corpusId, userId: $userId, permissions: $permissions) {
            ok
            message
          }
        }
        """

        # 1. Initially, viewer should not see any corpuses
        response = self.viewer_client.execute(all_corpuses_query)
        logger.info(f"Viewer's initial corpus list: {response}")
        self.assertEqual(response["data"]["corpuses"]["totalCount"], 0)

        # 2. Grant READ permission to viewer
        variables = {
            "corpusId": self.global_corpus_id,
            "userId": self.global_viewer_id,
            "permissions": ["READ"],
        }

        self.owner_client.execute(set_permissions_mutation, variable_values=variables)

        # 3. Now viewer should see the corpus
        response = self.viewer_client.execute(all_corpuses_query)
        logger.info(f"Viewer's corpus list after READ permission: {response}")
        self.assertEqual(response["data"]["corpuses"]["totalCount"], 1)
        self.assertEqual(
            response["data"]["corpuses"]["edges"][0]["node"]["myPermissions"],
            ["read_corpus"],
        )

        # 4. Viewer should be able to query the corpus directly
        variables = {"id": self.global_corpus_id}
        response = self.viewer_client.execute(corpus_query, variable_values=variables)
        logger.info(f"Viewer's direct corpus query: {response}")
        self.assertIsNotNone(response["data"]["corpus"])
        self.assertEqual(response["data"]["corpus"]["myPermissions"], ["read_corpus"])

        # 5. Remove READ permission from viewer
        variables = {
            "corpusId": self.global_corpus_id,
            "userId": self.global_viewer_id,
            "permissions": [],
        }

        self.owner_client.execute(set_permissions_mutation, variable_values=variables)

        # 6. Viewer should no longer see any corpuses
        response = self.viewer_client.execute(all_corpuses_query)
        logger.info(f"Viewer's corpus list after permission removal: {response}")
        self.assertEqual(response["data"]["corpuses"]["totalCount"], 0)

        # 7. Viewer should not be able to query the corpus directly
        variables = {"id": self.global_corpus_id}
        response = self.viewer_client.execute(corpus_query, variable_values=variables)
        logger.info(
            f"Viewer's direct corpus query after permission removal: {response}"
        )
        self.assertIsNone(response["data"]["corpus"])
