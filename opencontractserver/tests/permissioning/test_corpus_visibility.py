"""
Tests for SetCorpusVisibility mutation.

These tests verify that:
1. Corpus owners (creators) can change visibility
2. Users with PERMISSION permission can change visibility
3. Superusers can change visibility on any corpus
4. Users with only UPDATE permission CANNOT change visibility (security)
5. Anonymous users cannot change visibility
6. Random users cannot change visibility
7. IDOR protection - same error for non-existent and unauthorized
8. Already public/private returns success without change

Part of Phase 1 sharing implementation - see docs/architecture/sharing.md
"""

import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.corpuses.models import Corpus
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class TestContext:
    """Test context for GraphQL client."""

    def __init__(self, user):
        self.user = user


class AnonymousContext:
    """Anonymous user context for GraphQL client."""

    class AnonymousUser:
        is_authenticated = False
        is_superuser = False
        id = None

        def is_anonymous(self):
            return True

    user = AnonymousUser()


class TestSetCorpusVisibilityMutation(TestCase):
    """Tests for SetCorpusVisibility mutation."""

    MUTATION = """
        mutation SetCorpusVisibility($corpusId: ID!, $isPublic: Boolean!) {
            setCorpusVisibility(corpusId: $corpusId, isPublic: $isPublic) {
                ok
                message
            }
        }
    """

    def setUp(self):
        """Set up test data."""
        # Use unique usernames to avoid conflicts in parallel test runs
        unique_id = uuid.uuid4().hex[:8]
        self.owner = User.objects.create_user(
            username=f"owner_{unique_id}", password="test"
        )
        self.other_user = User.objects.create_user(
            username=f"other_user_{unique_id}", password="test"
        )
        self.superuser = User.objects.create_superuser(
            username=f"admin_{unique_id}", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.owner, is_public=False
        )

    # =========================================================================
    # PERMISSION GRANTED TESTS
    # =========================================================================

    def test_owner_can_make_corpus_public(self):
        """Owner (creator) can make their corpus public."""
        variables = {
            "corpusId": to_global_id("CorpusType", self.corpus.id),
            "isPublic": True,
        }

        client = Client(schema, context_value=TestContext(self.owner))

        # Mock the celery task to avoid async issues in tests
        with patch(
            "opencontractserver.tasks.permissioning_tasks.make_corpus_public_task"
        ) as mock_task:
            mock_task.si.return_value.apply_async.return_value = None
            result = client.execute(self.MUTATION, variable_values=variables)

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["setCorpusVisibility"]["ok"])
        self.assertIn(
            "public", result["data"]["setCorpusVisibility"]["message"].lower()
        )

        # Verify task was called. ``CorpusService.set_visibility`` passes the
        # corpus's integer pk; the former inline mutation passed the string
        # returned by ``from_global_id`` — the task accepts either.
        mock_task.si.assert_called_once_with(corpus_id=self.corpus.id)

    def test_owner_can_make_corpus_private(self):
        """Owner can make their corpus private."""
        # Start with public corpus
        self.corpus.is_public = True
        self.corpus.save()

        variables = {
            "corpusId": to_global_id("CorpusType", self.corpus.id),
            "isPublic": False,
        }

        client = Client(schema, context_value=TestContext(self.owner))
        result = client.execute(self.MUTATION, variable_values=variables)

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["setCorpusVisibility"]["ok"])
        self.assertIn(
            "private", result["data"]["setCorpusVisibility"]["message"].lower()
        )

        # Verify corpus was updated
        self.corpus.refresh_from_db()
        self.assertFalse(self.corpus.is_public)

    def test_user_with_permission_perm_can_change_visibility(self):
        """User with READ + PERMISSION can change visibility.

        Phase D (#1658) rule: READ is a precondition for any other
        permission op. Granting PERMISSION without READ is unsupported —
        the mutation now filters the corpus through ``visible_to_user``
        before checking PERMISSION, so the caller must also be able to
        see the corpus.
        """
        set_permissions_for_obj_to_user(
            self.other_user,
            self.corpus,
            [PermissionTypes.READ, PermissionTypes.PERMISSION],
        )

        variables = {
            "corpusId": to_global_id("CorpusType", self.corpus.id),
            "isPublic": True,
        }

        client = Client(schema, context_value=TestContext(self.other_user))

        with patch(
            "opencontractserver.tasks.permissioning_tasks.make_corpus_public_task"
        ) as mock_task:
            mock_task.si.return_value.apply_async.return_value = None
            result = client.execute(self.MUTATION, variable_values=variables)

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["setCorpusVisibility"]["ok"])

    def test_superuser_can_change_any_corpus_visibility(self):
        """Superuser can change visibility on any corpus."""
        variables = {
            "corpusId": to_global_id("CorpusType", self.corpus.id),
            "isPublic": True,
        }

        client = Client(schema, context_value=TestContext(self.superuser))

        with patch(
            "opencontractserver.tasks.permissioning_tasks.make_corpus_public_task"
        ) as mock_task:
            mock_task.si.return_value.apply_async.return_value = None
            result = client.execute(self.MUTATION, variable_values=variables)

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["setCorpusVisibility"]["ok"])

    # =========================================================================
    # PERMISSION DENIED TESTS (Security)
    # =========================================================================

    def test_user_with_only_update_cannot_change_visibility(self):
        """
        User with UPDATE permission but NOT PERMISSION cannot change visibility.

        This is a critical security test - UPDATE should not grant visibility control.
        """
        # Grant only UPDATE permission (not PERMISSION)
        set_permissions_for_obj_to_user(
            self.other_user, self.corpus, [PermissionTypes.UPDATE]
        )

        variables = {
            "corpusId": to_global_id("CorpusType", self.corpus.id),
            "isPublic": True,
        }

        client = Client(schema, context_value=TestContext(self.other_user))
        result = client.execute(self.MUTATION, variable_values=variables)

        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["setCorpusVisibility"]["ok"])
        # IDOR protection - message should not reveal corpus exists
        self.assertIn(
            "not found or you don't have permission",
            result["data"]["setCorpusVisibility"]["message"],
        )

    def test_random_user_cannot_change_visibility(self):
        """User with no permissions cannot change visibility."""
        variables = {
            "corpusId": to_global_id("CorpusType", self.corpus.id),
            "isPublic": True,
        }

        client = Client(schema, context_value=TestContext(self.other_user))
        result = client.execute(self.MUTATION, variable_values=variables)

        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["setCorpusVisibility"]["ok"])

    def test_user_with_crud_but_not_permission_cannot_change_visibility(self):
        """
        User with full CRUD but NOT PERMISSION cannot change visibility.

        This tests that CRUD permissions don't accidentally include PERMISSION.
        """
        # Grant CRUD (but CRUD doesn't include PERMISSION)
        set_permissions_for_obj_to_user(
            self.other_user, self.corpus, [PermissionTypes.CRUD]
        )

        variables = {
            "corpusId": to_global_id("CorpusType", self.corpus.id),
            "isPublic": True,
        }

        client = Client(schema, context_value=TestContext(self.other_user))
        result = client.execute(self.MUTATION, variable_values=variables)

        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["setCorpusVisibility"]["ok"])

    # =========================================================================
    # IDOR PROTECTION TESTS
    # =========================================================================

    def test_nonexistent_corpus_returns_same_error_as_unauthorized(self):
        """
        Non-existent corpus returns same error message as unauthorized.

        This prevents attackers from discovering which corpus IDs exist.
        """
        fake_id = to_global_id("CorpusType", 999999)
        variables = {
            "corpusId": fake_id,
            "isPublic": True,
        }

        client = Client(schema, context_value=TestContext(self.other_user))
        result = client.execute(self.MUTATION, variable_values=variables)

        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["setCorpusVisibility"]["ok"])
        # Same message as unauthorized
        self.assertIn(
            "not found or you don't have permission",
            result["data"]["setCorpusVisibility"]["message"],
        )

    def test_invalid_id_format_returns_error(self):
        """Invalid corpus ID format returns the unified IDOR-safe response.

        Phase D (#1658) routes the lookup through ``get_for_user_or_none``,
        which catches ValueError/TypeError from the ORM on garbage pks and
        returns None — so malformed IDs now surface as the same
        ``ok=False`` / unified message that "doesn't exist" and "no
        permission" return, rather than bubbling up as a GraphQL error.
        That collapses one more enumeration channel.
        """
        variables = {
            "corpusId": "invalid-id-format",
            "isPublic": True,
        }

        client = Client(schema, context_value=TestContext(self.owner))
        result = client.execute(self.MUTATION, variable_values=variables)

        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["setCorpusVisibility"]["ok"])
        self.assertIn(
            "not found or you don't have permission",
            result["data"]["setCorpusVisibility"]["message"],
        )

    # =========================================================================
    # IDEMPOTENCY TESTS
    # =========================================================================

    def test_already_public_returns_success(self):
        """Setting public on already-public corpus returns success."""
        self.corpus.is_public = True
        self.corpus.save()

        variables = {
            "corpusId": to_global_id("CorpusType", self.corpus.id),
            "isPublic": True,
        }

        client = Client(schema, context_value=TestContext(self.owner))
        result = client.execute(self.MUTATION, variable_values=variables)

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["setCorpusVisibility"]["ok"])
        self.assertIn(
            "already public", result["data"]["setCorpusVisibility"]["message"]
        )

    def test_already_private_returns_success(self):
        """Setting private on already-private corpus returns success."""
        variables = {
            "corpusId": to_global_id("CorpusType", self.corpus.id),
            "isPublic": False,
        }

        client = Client(schema, context_value=TestContext(self.owner))
        result = client.execute(self.MUTATION, variable_values=variables)

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["setCorpusVisibility"]["ok"])
        self.assertIn(
            "already private", result["data"]["setCorpusVisibility"]["message"]
        )


class TestUpdateCorpusMutationCannotSetVisibility(TestCase):
    """
    Security tests ensuring UpdateCorpusMutation cannot change is_public.

    This verifies that removing is_public from Arguments and making it
    read-only in the serializer prevents bypass attacks.
    """

    UPDATE_MUTATION = """
        mutation UpdateCorpus($id: String!, $title: String, $isPublic: Boolean) {
            updateCorpus(id: $id, title: $title, isPublic: $isPublic) {
                ok
                message
            }
        }
    """

    def setUp(self):
        """Set up test data."""
        self.owner = User.objects.create_user(username="owner", password="test")
        self.corpus = Corpus.objects.create(
            title="Test Corpus", creator=self.owner, is_public=False
        )
        # Owner has UPDATE permission
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.CRUD])

    def test_update_corpus_ignores_is_public_parameter(self):
        """
        UpdateCorpusMutation should ignore is_public parameter.

        Even if someone passes is_public, it should not change the value.
        """
        variables = {
            "id": to_global_id("CorpusType", self.corpus.id),
            "title": "Updated Title",
            "isPublic": True,  # Should be ignored
        }

        client = Client(schema, context_value=TestContext(self.owner))
        _ = client.execute(self.UPDATE_MUTATION, variable_values=variables)

        # The mutation should succeed (title update works)
        # Note: GraphQL may return an error for unknown field, which is fine
        # If it doesn't error, is_public should remain unchanged

        # Verify is_public was NOT changed
        self.corpus.refresh_from_db()
        self.assertFalse(self.corpus.is_public)


class TestCreateCorpusMutationGrantsPermission(TestCase):
    """Test that CreateCorpusMutation grants PERMISSION to creators."""

    CREATE_MUTATION = """
        mutation CreateCorpus($title: String!) {
            createCorpus(title: $title) {
                ok
                message
                objId
            }
        }
    """

    def test_creator_receives_permission_permission(self):
        """New corpus creator should have PERMISSION permission."""
        user = User.objects.create_user(username="testuser", password="test")

        variables = {
            "title": "My New Corpus",
        }

        client = Client(schema, context_value=TestContext(user))
        result = client.execute(self.CREATE_MUTATION, variable_values=variables)

        self.assertIsNone(result.get("errors"))
        self.assertTrue(result["data"]["createCorpus"]["ok"])

        # Get the created corpus
        corpus = Corpus.objects.get(creator=user, title="My New Corpus")

        # Verify user has PERMISSION permission
        has_permission = corpus.user_can(user, PermissionTypes.PERMISSION)
        self.assertTrue(
            has_permission, "Creator should have PERMISSION permission on new corpus"
        )
