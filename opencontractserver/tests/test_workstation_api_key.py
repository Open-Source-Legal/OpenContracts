"""
Tests for workstation API key authentication.

Tests the WorkstationApiKey model, the WorkstationKeyMiddleware,
and the CreateWorkstationApiKey / RevokeWorkstationApiKey mutations.
"""

from datetime import timedelta
from unittest.mock import MagicMock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from graphene.test import Client as GrapheneClient

from config.graphql.schema import schema
from opencontractserver.bulk_ingestion.middleware import WorkstationKeyMiddleware
from opencontractserver.bulk_ingestion.models import (
    BulkIngestionJob,
    BulkIngestionJobStatus,
    IngestionSourceType,
    ParsingStrategy,
    WorkstationApiKey,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class TestContext:
    def __init__(self, user, auth_header=""):
        self.user = user
        self.META = {"HTTP_AUTHORIZATION": auth_header}
        self.POST = {}


CREATE_KEY_MUTATION = """
    mutation CreateWorkstationApiKey(
        $name: String!
        $jobId: ID
        $expiresInHours: Int
    ) {
        createWorkstationApiKey(
            name: $name
            jobId: $jobId
            expiresInHours: $expiresInHours
        ) {
            ok
            message
            rawKey
            apiKey {
                id
                name
                keyPrefix
                isActive
                expiresAt
            }
        }
    }
"""

REVOKE_KEY_MUTATION = """
    mutation RevokeWorkstationApiKey($keyId: ID!) {
        revokeWorkstationApiKey(keyId: $keyId) {
            ok
            message
        }
    }
"""


class WorkstationApiKeyModelTest(TestCase):
    """Tests for the WorkstationApiKey model."""

    def test_generate_key_format(self):
        """Generated key starts with wsk_ and is 68 chars long."""
        raw_key, key_hash = WorkstationApiKey.generate_key()
        self.assertTrue(raw_key.startswith("wsk_"))
        self.assertEqual(len(raw_key), 68)  # 4 prefix + 64 hex
        self.assertEqual(len(key_hash), 64)  # SHA-256 hex digest

    def test_generate_key_unique(self):
        """Each call produces a different key."""
        key1, hash1 = WorkstationApiKey.generate_key()
        key2, hash2 = WorkstationApiKey.generate_key()
        self.assertNotEqual(key1, key2)
        self.assertNotEqual(hash1, hash2)

    def test_hash_key_consistency(self):
        """hash_key produces the same hash as generate_key for the same raw key."""
        raw_key, expected_hash = WorkstationApiKey.generate_key()
        self.assertEqual(WorkstationApiKey.hash_key(raw_key), expected_hash)

    def test_str_representation(self):
        """String repr shows prefix and user ID."""
        user = User.objects.create_user(username="keytest", password="pass")
        raw_key, key_hash = WorkstationApiKey.generate_key()
        api_key = WorkstationApiKey.objects.create(
            creator=user,
            name="test-key",
            key_prefix=raw_key[:12],
            key_hash=key_hash,
        )
        self.assertIn(raw_key[:12], str(api_key))


class CreateWorkstationApiKeyTest(TestCase):
    """Tests for the CreateWorkstationApiKey mutation."""

    def setUp(self):
        self.user = User.objects.create_superuser(
            username="testuser",
            password="testpass",
            is_usage_capped=False,
        )
        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            description="Test",
            creator=self.user,
        )
        set_permissions_for_obj_to_user(
            self.user, self.corpus, [PermissionTypes.CRUD]
        )
        self.job = BulkIngestionJob.objects.create(
            corpus=self.corpus,
            creator=self.user,
            source_type=IngestionSourceType.PRE_PARSED,
            source_config={},
            parsing_strategy=ParsingStrategy.PRE_PARSED,
        )
        self.client = GrapheneClient(schema)

    def test_create_key_basic(self):
        """Create a key and verify it returns a raw key."""
        result = self.client.execute(
            CREATE_KEY_MUTATION,
            variables={"name": "my-workstation"},
            context_value=TestContext(self.user),
        )
        data = result["data"]["createWorkstationApiKey"]
        self.assertTrue(data["ok"])
        self.assertTrue(data["rawKey"].startswith("wsk_"))
        self.assertEqual(len(data["rawKey"]), 68)
        self.assertEqual(data["apiKey"]["name"], "my-workstation")
        self.assertTrue(data["apiKey"]["isActive"])

    def test_create_key_with_job_scope(self):
        """Key scoped to a job is created successfully."""
        result = self.client.execute(
            CREATE_KEY_MUTATION,
            variables={"name": "scoped-key", "jobId": str(self.job.id)},
            context_value=TestContext(self.user),
        )
        data = result["data"]["createWorkstationApiKey"]
        self.assertTrue(data["ok"])
        # Verify job FK was set
        api_key = WorkstationApiKey.objects.get(name="scoped-key")
        self.assertEqual(api_key.job_id, self.job.id)

    def test_create_key_with_expiry(self):
        """Key with expiry has expires_at set."""
        result = self.client.execute(
            CREATE_KEY_MUTATION,
            variables={"name": "expiring-key", "expiresInHours": 48},
            context_value=TestContext(self.user),
        )
        data = result["data"]["createWorkstationApiKey"]
        self.assertTrue(data["ok"])
        self.assertIsNotNone(data["apiKey"]["expiresAt"])

    def test_create_key_invalid_job(self):
        """Creating a key with a nonexistent job returns error."""
        result = self.client.execute(
            CREATE_KEY_MUTATION,
            variables={"name": "bad-key", "jobId": "99999"},
            context_value=TestContext(self.user),
        )
        data = result["data"]["createWorkstationApiKey"]
        self.assertFalse(data["ok"])
        self.assertIn("Job not found", data["message"])

    def test_create_key_other_users_job(self):
        """Cannot scope a key to another user's job."""
        other_user = User.objects.create_user(
            username="otheruser", password="pass"
        )
        result = self.client.execute(
            CREATE_KEY_MUTATION,
            variables={"name": "bad-key", "jobId": str(self.job.id)},
            context_value=TestContext(other_user),
        )
        data = result["data"]["createWorkstationApiKey"]
        self.assertFalse(data["ok"])

    def test_raw_key_authenticates_via_hash(self):
        """The raw key can be verified against the stored hash."""
        result = self.client.execute(
            CREATE_KEY_MUTATION,
            variables={"name": "verify-key"},
            context_value=TestContext(self.user),
        )
        raw_key = result["data"]["createWorkstationApiKey"]["rawKey"]
        key_hash = WorkstationApiKey.hash_key(raw_key)
        api_key = WorkstationApiKey.objects.get(key_hash=key_hash)
        self.assertEqual(api_key.creator, self.user)


class RevokeWorkstationApiKeyTest(TestCase):
    """Tests for the RevokeWorkstationApiKey mutation."""

    def setUp(self):
        self.user = User.objects.create_superuser(
            username="testuser",
            password="testpass",
            is_usage_capped=False,
        )
        raw_key, key_hash = WorkstationApiKey.generate_key()
        self.api_key = WorkstationApiKey.objects.create(
            creator=self.user,
            name="to-revoke",
            key_prefix=raw_key[:12],
            key_hash=key_hash,
        )
        self.client = GrapheneClient(schema)

    def test_revoke_key(self):
        """Revoking a key sets is_active to False."""
        result = self.client.execute(
            REVOKE_KEY_MUTATION,
            variables={"keyId": str(self.api_key.id)},
            context_value=TestContext(self.user),
        )
        data = result["data"]["revokeWorkstationApiKey"]
        self.assertTrue(data["ok"])
        self.api_key.refresh_from_db()
        self.assertFalse(self.api_key.is_active)

    def test_revoke_already_revoked(self):
        """Cannot revoke an already-revoked key."""
        self.api_key.is_active = False
        self.api_key.save()
        result = self.client.execute(
            REVOKE_KEY_MUTATION,
            variables={"keyId": str(self.api_key.id)},
            context_value=TestContext(self.user),
        )
        data = result["data"]["revokeWorkstationApiKey"]
        self.assertFalse(data["ok"])
        self.assertIn("already revoked", data["message"])

    def test_revoke_other_users_key(self):
        """Cannot revoke another user's key."""
        other_user = User.objects.create_user(
            username="otheruser", password="pass"
        )
        result = self.client.execute(
            REVOKE_KEY_MUTATION,
            variables={"keyId": str(self.api_key.id)},
            context_value=TestContext(other_user),
        )
        data = result["data"]["revokeWorkstationApiKey"]
        self.assertFalse(data["ok"])
        self.assertIn("not found", data["message"])

    def test_revoke_nonexistent_key(self):
        """Revoking a nonexistent key returns error."""
        result = self.client.execute(
            REVOKE_KEY_MUTATION,
            variables={"keyId": "99999"},
            context_value=TestContext(self.user),
        )
        data = result["data"]["revokeWorkstationApiKey"]
        self.assertFalse(data["ok"])


class WorkstationKeyMiddlewareTest(TestCase):
    """Tests for the WorkstationKeyMiddleware Graphene middleware."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="wsuser", password="testpass"
        )
        raw_key, key_hash = WorkstationApiKey.generate_key()
        self.raw_key = raw_key
        self.api_key = WorkstationApiKey.objects.create(
            creator=self.user,
            name="middleware-test",
            key_prefix=raw_key[:12],
            key_hash=key_hash,
        )
        self.middleware = WorkstationKeyMiddleware()

    def _make_info(self, auth_header=""):
        """Build a mock GraphQL info object with the given auth header."""
        context = MagicMock()
        context.META = {"HTTP_AUTHORIZATION": auth_header}
        context._workstation_auth_checked = False
        # Remove the attribute so hasattr returns False
        del context._workstation_auth_checked
        info = MagicMock()
        info.context = context
        return info

    def test_valid_key_authenticates(self):
        """A valid WSK token sets context.user to the key's creator."""
        info = self._make_info(f"WSK {self.raw_key}")
        next_fn = MagicMock(return_value="resolved")

        result = self.middleware.resolve(next_fn, None, info)

        self.assertEqual(result, "resolved")
        info.context.__setattr__.assert_any_call("user", self.user)

    def test_revoked_key_does_not_authenticate(self):
        """A revoked key is rejected."""
        self.api_key.is_active = False
        self.api_key.save()
        info = self._make_info(f"WSK {self.raw_key}")
        next_fn = MagicMock(return_value="resolved")

        self.middleware.resolve(next_fn, None, info)

        # user should NOT have been set (no call with our user)
        for call in info.context.__setattr__.call_args_list:
            if call[0][0] == "user":
                self.assertNotEqual(call[0][1], self.user)

    def test_expired_key_does_not_authenticate(self):
        """An expired key is rejected."""
        self.api_key.expires_at = timezone.now() - timedelta(hours=1)
        self.api_key.save()
        info = self._make_info(f"WSK {self.raw_key}")
        next_fn = MagicMock(return_value="resolved")

        self.middleware.resolve(next_fn, None, info)

        for call in info.context.__setattr__.call_args_list:
            if call[0][0] == "user":
                self.assertNotEqual(call[0][1], self.user)

    def test_unknown_key_does_not_authenticate(self):
        """An unknown key is silently ignored."""
        info = self._make_info("WSK wsk_0000000000000000000000000000000000000000000000000000000000000000")
        next_fn = MagicMock(return_value="resolved")

        result = self.middleware.resolve(next_fn, None, info)
        self.assertEqual(result, "resolved")

    def test_non_wsk_header_passthrough(self):
        """Bearer tokens are passed through untouched."""
        info = self._make_info("Bearer eyJhbGciOiJIUzI1NiJ9.test.sig")
        next_fn = MagicMock(return_value="resolved")

        result = self.middleware.resolve(next_fn, None, info)
        self.assertEqual(result, "resolved")
        # Authorization header should NOT be cleared
        self.assertEqual(
            info.context.META["HTTP_AUTHORIZATION"],
            "Bearer eyJhbGciOiJIUzI1NiJ9.test.sig",
        )

    def test_empty_header_passthrough(self):
        """Requests with no Authorization header pass through."""
        info = self._make_info("")
        next_fn = MagicMock(return_value="resolved")

        result = self.middleware.resolve(next_fn, None, info)
        self.assertEqual(result, "resolved")

    def test_last_used_at_updated(self):
        """Successful auth updates last_used_at on the key."""
        info = self._make_info(f"WSK {self.raw_key}")
        next_fn = MagicMock(return_value="resolved")

        self.middleware.resolve(next_fn, None, info)

        self.api_key.refresh_from_db()
        self.assertIsNotNone(self.api_key.last_used_at)

    def test_auth_header_cleared_after_success(self):
        """After successful WSK auth, Authorization header is cleared."""
        info = self._make_info(f"WSK {self.raw_key}")
        next_fn = MagicMock(return_value="resolved")

        self.middleware.resolve(next_fn, None, info)

        self.assertEqual(info.context.META["HTTP_AUTHORIZATION"], "")
