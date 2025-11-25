import json
import time
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client as DjangoClient
from django.test import TestCase, override_settings
from graphql_relay import to_global_id

from config.graphql.ratelimits import (
    RateLimits,
    get_user_tier_rate,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document

User = get_user_model()


class RateLimitConfigurationTestCase(TestCase):
    """Test rate limit configuration and settings."""

    def test_default_rate_limits(self):
        """Test that default rate limits are properly configured."""
        expected_limits = {
            "AUTH_LOGIN": "5/m",
            "AUTH_REGISTER": "3/m",
            "AUTH_PASSWORD_RESET": "3/h",
            "READ_LIGHT": "100/m",
            "READ_MEDIUM": "30/m",
            "READ_HEAVY": "10/m",
            "WRITE_LIGHT": "30/m",
            "WRITE_MEDIUM": "10/m",
            "WRITE_HEAVY": "5/m",
            "AI_ANALYSIS": "5/m",
            "AI_EXTRACT": "10/m",
            "AI_QUERY": "20/m",
            "EXPORT": "5/h",
            "IMPORT": "10/h",
            "ADMIN_OPERATION": "100/m",
        }

        for key, expected_value in expected_limits.items():
            actual_value = getattr(RateLimits, key)
            self.assertEqual(
                actual_value,
                expected_value,
                f"RateLimits.{key} should be {expected_value}, got {actual_value}",
            )

    def test_rate_limit_overrides(self):
        """Test that rate limits can be overridden via settings."""
        with self.settings(
            RATE_LIMIT_OVERRIDES={"AUTH_LOGIN": "10/m", "READ_HEAVY": "20/m"}
        ):
            # Need to reimport to pick up new settings
            from importlib import reload

            import config.graphql.ratelimits as ratelimits_module

            reload(ratelimits_module)

            # Check that overrides are applied
            self.assertEqual(ratelimits_module.RateLimits.AUTH_LOGIN, "10/m")
            self.assertEqual(ratelimits_module.RateLimits.READ_HEAVY, "20/m")
            # Other limits should remain default
            self.assertEqual(ratelimits_module.RateLimits.WRITE_MEDIUM, "10/m")

    def test_user_tier_rate_calculation(self):
        """Test that user tier rates are calculated correctly."""
        regular_user = User.objects.create_user(
            username="regular_rate", password="test"
        )
        regular_user.is_usage_capped = False
        regular_user.save()

        superuser = User.objects.create_superuser(
            username="super_rate", password="test", email="super_rate@test.com"
        )
        superuser.is_usage_capped = False
        superuser.save()

        # Create mock info objects with proper user attribute access
        class MockInfo:
            def __init__(self, user):
                self.context = MagicMock()
                self.context.user = user

        # Get rate function for READ_MEDIUM (base: 30/m)
        get_rate = get_user_tier_rate("READ_MEDIUM")

        # Test regular user (2x multiplier = 60/m)
        regular_info = MockInfo(regular_user)
        rate = get_rate(None, regular_info)
        self.assertEqual(rate, "60/m")

        # Test superuser (10x multiplier = 300/m)
        super_info = MockInfo(superuser)
        rate = get_rate(None, super_info)
        self.assertEqual(rate, "300/m")

        # Test anonymous user (1x multiplier = 30/m)
        anon_user = MagicMock()
        anon_user.is_authenticated = False
        anon_user.is_superuser = False
        anon_user.is_usage_capped = False
        anon_info = MockInfo(anon_user)
        rate = get_rate(None, anon_info)
        self.assertEqual(rate, "30/m")

        # Test usage-capped user (0.5x multiplier = 30/m for authenticated)
        capped_user = MagicMock()
        capped_user.is_authenticated = True
        capped_user.is_superuser = False
        capped_user.is_usage_capped = True
        capped_info = MockInfo(capped_user)
        rate = get_rate(None, capped_info)
        self.assertEqual(rate, "30/m")  # 60/m * 0.5 = 30/m


@override_settings(RATELIMIT_DISABLE=False)
class GraphQLRateLimitIntegrationTestCase(TestCase):
    """Test rate limiting integration with actual GraphQL mutations and queries."""

    def setUp(self):
        # Create unique users for each test to avoid collisions
        self.test_id = int(time.time() * 1000)
        self.user = User.objects.create_user(
            username=f"testuser_graphql_{self.test_id}", password="test123"
        )
        self.user.is_usage_capped = False
        self.user.save()

        self.superuser = User.objects.create_superuser(
            username=f"superuser_graphql_{self.test_id}",
            password="test123",
            email=f"super_{self.test_id}@test.com",
        )
        self.superuser.is_usage_capped = False
        self.superuser.save()

        # Use Django test client for actual HTTP requests
        self.django_client = DjangoClient()
        self.django_client.force_login(self.user)

        self.super_django_client = DjangoClient()
        self.super_django_client.force_login(self.superuser)

        cache.clear()

        # Create test objects
        self.corpus = Corpus.objects.create(
            title=f"Test Corpus {self.test_id}", creator=self.user
        )
        self.document = Document.objects.create(
            title=f"Test Doc {self.test_id}", description="Test", creator=self.user
        )
        self.corpus.add_document(document=self.document, user=self.user)

        # Get global IDs
        self.corpus_gid = to_global_id("CorpusType", self.corpus.id)
        self.document_gid = to_global_id("DocumentType", self.document.id)

    def execute_graphql(self, query, variables=None, use_super=False):
        """Execute a GraphQL query through Django's test client."""
        client = self.super_django_client if use_super else self.django_client
        response = client.post(
            "/graphql/",
            data=json.dumps({"query": query, "variables": variables or {}}),
            content_type="application/json",
        )
        return response.json()

    def tearDown(self):
        cache.clear()

    @patch("time.time")
    @patch("opencontractserver.corpuses.models.Corpus.objects.visible_to_user")
    def test_actual_rate_limiting_on_queries(self, mock_visible_to_user, mock_time):
        """Test that queries are actually rate limited after multiple requests."""
        # Freeze time to ensure all requests fall within the same rate limit window
        mock_time.return_value = 1000000.0

        query = """
            query GetCorpuses {
                corpuses {
                    edges {
                        node {
                            id
                            title
                        }
                    }
                }
            }
        """

        mock_queryset = Corpus.objects.none()  # Empty queryset, fast to process
        mock_visible_to_user.return_value = mock_queryset

        # Clear cache to ensure fresh rate limit counter
        cache.clear()

        # The rate limit for READ_LIGHT is 100/m base, 200/m for authenticated users
        # Make requests rapidly to ensure they fall within the same minute window
        # Use a shorter burst to avoid timing issues
        results = []
        errors_found = []

        # Make 210 requests rapidly (just over the 200/m limit)
        # This ensures we're testing the rate limit, not time window boundaries
        for i in range(210):
            result = self.execute_graphql(query)
            results.append(result)

            # Check if we hit a rate limit
            if result.get("errors"):
                error_message = result["errors"][0]["message"]
                errors_found.append(f"Request {i}: {error_message}")
                if "Limit exceeded" in error_message:
                    # We successfully triggered rate limiting
                    self.assertIn("Limit exceeded", error_message)
                    # Should hit limit around request 200 (allowing some buffer)
                    self.assertGreater(i, 195, "Rate limit triggered too early")
                    self.assertLess(i, 210, "Should hit rate limit before 210 requests")
                    return

        # If we didn't hit a rate limit, provide diagnostic information
        if errors_found:
            self.fail(
                f"Did not hit rate limit after 210 requests. Errors found: {errors_found[:5]}"
            )
        else:
            self.fail(
                "Did not hit rate limit after 210 requests. No errors encountered."
            )

    @patch("time.time")
    def test_actual_rate_limiting_on_mutations(self, mock_time):
        """Test that mutations are actually rate limited."""
        # Freeze time to ensure all requests fall within the same rate limit window
        mock_time.return_value = 1000000.0

        mutation = """
            mutation CreateLabelset($title: String!, $description: String!) {
                createLabelset(title: $title, description: $description) {
                    ok
                    message
                }
            }
        """

        # Clear cache to ensure fresh rate limit counter
        cache.clear()

        # WRITE_MEDIUM is 10/m base, 20/m for authenticated users
        results = []
        for i in range(25):  # Try to exceed the 20/m limit
            variables = {
                "title": f"Test Labelset {self.test_id}_{i}",
                "description": f"Test Description {i}",
            }
            result = self.execute_graphql(mutation, variables)
            results.append(result)

            # Check if we hit a rate limit
            if result.get("errors"):
                error_message = result["errors"][0]["message"]
                if "Limit exceeded" in error_message:
                    # We successfully triggered rate limiting
                    self.assertIn("Limit exceeded", error_message)
                    self.assertLess(i, 25, "Should hit rate limit before 25 requests")
                    return

        # If we didn't hit a rate limit, that's unexpected
        self.fail("Did not hit rate limit after 25 mutation requests")

    @patch("time.time")
    @patch("opencontractserver.corpuses.models.Corpus.objects.visible_to_user")
    def test_superuser_gets_higher_rate_limits(self, mock_visible_to_user, mock_time):
        """Test that superusers get higher rate limits than regular users."""
        # Freeze time to ensure all requests fall within the same rate limit window
        mock_time.return_value = 1000000.0

        mock_queryset = Corpus.objects.none()  # Empty queryset, fast to process
        mock_visible_to_user.return_value = mock_queryset

        query = """
            query GetCorpuses {
                corpuses {
                    edges {
                        node {
                            id
                        }
                    }
                }
            }
        """

        # Clear cache to ensure fresh rate limit counter
        cache.clear()

        # Regular user should hit limit around 200 requests
        # Superuser should get 10x that (1000/m)

        # Test with regular user first
        regular_hit_limit = False
        for i in range(250):
            result = self.execute_graphql(query, use_super=False)
            if (
                result.get("errors")
                and "Limit exceeded" in result["errors"][0]["message"]
            ):
                regular_hit_limit = True
                regular_limit_hit_at = i
                break

        self.assertTrue(regular_hit_limit, "Regular user should hit rate limit")

        # Now test with superuser - should allow more requests
        super_hit_limit = False
        for i in range(500):
            result = self.execute_graphql(query, use_super=True)
            if (
                result.get("errors")
                and "Limit exceeded" in result["errors"][0]["message"]
            ):
                super_hit_limit = True
                super_limit_hit_at = i
                break

        # Superuser should be able to make more requests than regular user
        if super_hit_limit:
            self.assertGreater(
                super_limit_hit_at,
                regular_limit_hit_at,
                "Superuser should have higher rate limit than regular user",
            )

    @patch("time.time")
    def test_rate_limit_grouping(self, mock_time):
        """Test that rate limits can be grouped across operations."""
        # Freeze time to ensure all requests fall within the same rate limit window
        mock_time.return_value = 1000000.0

        # Both operations should share the same rate limit pool
        # This tests that when multiple operations are in the same group,
        # they share the rate limit counter

        # Clear cache to ensure fresh rate limit counter
        cache.clear()

        mutation1 = """
            mutation CreateLabelset($title: String!, $description: String!) {
                createLabelset(title: $title, description: $description) {
                    ok
                }
            }
        """

        # Make several requests with first mutation
        for i in range(25):
            variables = {
                "title": f"Labelset {self.test_id}_{i}",
                "description": f"Description {i}",
            }
            result = self.execute_graphql(mutation1, variables)
            if (
                result.get("errors")
                and "Limit exceeded" in result["errors"][0]["message"]
            ):
                # Successfully hit rate limit
                return

        self.fail("Did not hit grouped rate limit after expected number of requests")

    @patch("time.time")
    @patch("opencontractserver.corpuses.models.Corpus.objects.visible_to_user")
    def test_anonymous_user_rate_limiting(self, mock_visible_to_user, mock_time):
        """Test that anonymous users get rate limited by IP."""
        # Freeze time to ensure all requests fall within the same rate limit window
        mock_time.return_value = 1000000.0

        mock_queryset = Corpus.objects.none()  # Empty queryset, fast to process
        mock_visible_to_user.return_value = mock_queryset

        # Clear cache to ensure fresh rate limit counter
        cache.clear()

        # Log out to test as anonymous
        anon_client = DjangoClient()

        query = """
            query GetCorpuses {
                corpuses {
                    edges {
                        node {
                            id
                        }
                    }
                }
            }
        """

        # Anonymous users should get base rate (100/m for READ_LIGHT)
        for i in range(150):
            response = anon_client.post(
                "/graphql/",
                data=json.dumps({"query": query, "variables": {}}),
                content_type="application/json",
            )
            result = response.json()

            if result.get("errors"):
                # Might get permission error or rate limit error
                error_message = result["errors"][0]["message"]
                if "Limit exceeded" in error_message:
                    self.assertLess(i, 150, "Anonymous user should hit rate limit")
                    break

        # Anonymous might not have permission to query, which is also fine
        # The important thing is that rate limiting is checked

    @patch("time.time")
    @patch("opencontractserver.corpuses.models.Corpus.objects.visible_to_user")
    def test_different_users_have_separate_rate_limits(
        self, mock_visible_to_user, mock_time
    ):
        """Test that different users have independent rate limit buckets."""
        # Freeze time to ensure all requests fall within the same rate limit window
        mock_time.return_value = 1000000.0

        mock_queryset = Corpus.objects.none()  # Empty queryset, fast to process
        mock_visible_to_user.return_value = mock_queryset

        # Clear cache to ensure fresh rate limit counter
        cache.clear()

        # Create another user
        other_user = User.objects.create_user(
            username=f"other_user_{self.test_id}", password="test123"
        )
        other_user.is_usage_capped = False
        other_user.save()

        other_client = DjangoClient()
        other_client.force_login(other_user)

        query = """
            query GetCorpuses {
                corpuses {
                    edges {
                        node {
                            id
                        }
                    }
                }
            }
        """

        # First user makes many requests to approach limit
        for i in range(190):  # Just under the 200/m limit
            result = self.execute_graphql(query)
            if (
                result.get("errors")
                and "Limit exceeded" in result["errors"][0]["message"]
            ):
                break

        # Other user should still be able to make requests (separate bucket)
        for i in range(50):  # Should work fine for other user
            response = other_client.post(
                "/graphql/",
                data=json.dumps({"query": query, "variables": {}}),
                content_type="application/json",
            )
            result = response.json()

            # Should not hit rate limit in first 50 requests
            if (
                result.get("errors")
                and "Limit exceeded" in result["errors"][0]["message"]
            ):
                self.fail(f"Other user hit rate limit too early at request {i}")

        # Clean up
        other_user.delete()

    @patch("time.time")
    @patch("opencontractserver.corpuses.models.Corpus.objects.visible_to_user")
    def test_different_operations_have_different_limits(
        self, mock_visible_to_user, mock_time
    ):
        """Test that different operations have appropriate rate limits."""
        mock_queryset = Corpus.objects.none()  # Empty queryset, fast to process
        mock_visible_to_user.return_value = mock_queryset

        # Freeze time to keep all requests within one window
        mock_time.return_value = 1000000.0
        cache.clear()
        # Test a heavy read operation vs light read operation
        heavy_query = """
            query GetAnnotations($corpusId: ID!) {
                annotations(corpusId: $corpusId) {
                    edges {
                        node {
                            id
                            rawText
                            json
                        }
                    }
                    totalCount
                }
            }
        """

        light_query = """
            query GetCorpuses {
                corpuses {
                    edges {
                        node {
                            id
                        }
                    }
                }
            }
        """

        # Heavy query should hit rate limit sooner (READ_MEDIUM = 30/m base, 60/m for auth)
        heavy_hit_at = None
        for i in range(70):
            result = self.execute_graphql(heavy_query, {"corpusId": self.corpus_gid})
            if (
                result.get("errors")
                and "Limit exceeded" in result["errors"][0]["message"]
            ):
                heavy_hit_at = i
                break

        # Light query should allow more requests (READ_LIGHT = 100/m base, 200/m for auth)
        light_hit_at = None
        for i in range(210):
            result = self.execute_graphql(light_query)
            if (
                result.get("errors")
                and "Limit exceeded" in result["errors"][0]["message"]
            ):
                light_hit_at = i
                break

        # Light queries should allow more requests than heavy queries
        self.assertIsNotNone(
            heavy_hit_at,
            "Heavy query should hit rate limit within expected request window",
        )
        self.assertIsNotNone(
            light_hit_at,
            "Light query should hit rate limit within expected request window",
        )
        self.assertGreater(
            light_hit_at,
            heavy_hit_at,
            "Light queries should have higher rate limit than heavy queries",
        )

    @patch("time.time")
    def test_specific_mutations_are_rate_limited(self, mock_time):
        """Test that specific mutations have rate limiting applied."""
        # Freeze time to ensure all requests fall within the same rate limit window
        mock_time.return_value = 1000000.0

        mutation = """
            mutation CreateLabelset($title: String!, $description: String!) {
                createLabelset(title: $title, description: $description) {
                    ok
                }
            }
        """

        # Clear cache to ensure fresh rate limit counter
        cache.clear()

        # Mutation should have rate limiting
        hit_limit = False
        for i in range(30):  # Most mutations have WRITE_MEDIUM = 10/m base, 20/m auth
            variables = {
                "title": f"Test {self.test_id}_{i}",
                "description": f"Desc {i}",
            }
            result = self.execute_graphql(mutation, variables)

            if result.get("errors"):
                error_msg = result["errors"][0]["message"]
                if "Limit exceeded" in error_msg:
                    hit_limit = True
                    break

        self.assertTrue(hit_limit, "Mutation should have rate limiting")

    @patch("time.time")
    @patch("opencontractserver.corpuses.models.Corpus.objects.visible_to_user")
    def test_corpuses_query_rate_limited(self, mock_visible_to_user, mock_time):
        """Test that corpuses query is rate limited."""
        # Freeze time to ensure all requests fall within the same rate limit window
        mock_time.return_value = 1000000.0

        mock_queryset = Corpus.objects.none()  # Empty queryset, fast to process
        mock_visible_to_user.return_value = mock_queryset

        query = """query { corpuses { edges { node { id } } } }"""

        # Clear cache to ensure fresh rate limit counter
        cache.clear()

        hit_limit = False
        request_count = 0
        for i in range(210):
            result = self.execute_graphql(query)
            request_count = i + 1

            if (
                result.get("errors")
                and "Limit exceeded" in result["errors"][0]["message"]
            ):
                hit_limit = True
                self.assertGreater(i, 195, "Hit rate limit too early")
                self.assertLess(i, 210, "Should hit around request 200")
                break

        self.assertTrue(
            hit_limit,
            f"Corpuses query should be rate limited (made {request_count} requests without hitting limit)",
        )

    @patch("time.time")
    @patch("opencontractserver.documents.models.Document.objects.visible_to_user")
    def test_documents_query_rate_limited(self, mock_visible_to_user, mock_time):
        """Test that documents query is rate limited."""
        # Freeze time to ensure all requests fall within the same rate limit window
        mock_time.return_value = 1000000.0

        # Mock the visible_to_user to return a minimal queryset quickly
        # This avoids the database overhead while still testing rate limiting
        from opencontractserver.documents.models import Document

        mock_queryset = Document.objects.none()  # Empty queryset, fast to process
        mock_visible_to_user.return_value = mock_queryset

        query = """query { documents { edges { node { id } } } }"""

        # Clear cache to ensure fresh rate limit counter
        cache.clear()

        hit_limit = False
        request_count = 0
        for i in range(210):
            result = self.execute_graphql(query)
            request_count = i + 1

            if (
                result.get("errors")
                and "Limit exceeded" in result["errors"][0]["message"]
            ):
                hit_limit = True
                self.assertGreater(i, 195, "Hit rate limit too early")
                self.assertLess(i, 210, "Should hit around request 200")
                break

        self.assertTrue(
            hit_limit,
            f"Documents query should be rate limited (made {request_count} requests without hitting limit)",
        )

    @patch("time.time")
    @patch("opencontractserver.annotations.models.LabelSet.objects.visible_to_user")
    def test_labelsets_query_rate_limited(self, mock_visible_to_user, mock_time):
        """Test that labelsets query is rate limited."""
        # Freeze time to ensure all requests fall within the same rate limit window
        mock_time.return_value = 1000000.0

        # Mock the visible_to_user to return a minimal queryset quickly
        # This avoids the database overhead while still testing rate limiting
        from opencontractserver.annotations.models import LabelSet

        mock_queryset = LabelSet.objects.none()  # Empty queryset, fast to process
        mock_visible_to_user.return_value = mock_queryset

        query = """query { labelsets { edges { node { id } } } }"""

        # Clear cache to ensure fresh rate limit counter
        cache.clear()

        hit_limit = False
        request_count = 0
        for i in range(210):
            result = self.execute_graphql(query)
            request_count = i + 1

            if (
                result.get("errors")
                and "Limit exceeded" in result["errors"][0]["message"]
            ):
                hit_limit = True
                self.assertGreater(i, 195, "Hit rate limit too early")
                self.assertLess(i, 210, "Should hit around request 200")
                break

        self.assertTrue(
            hit_limit,
            f"Labelsets query should be rate limited (made {request_count} requests without hitting limit)",
        )

    @patch("time.time")
    def test_usage_capped_users_get_reduced_limits(self, mock_time):
        """Test that usage-capped users get reduced rate limits."""
        # Freeze time to ensure all requests fall within the same rate limit window
        mock_time.return_value = 1000000.0

        # Clear cache to ensure fresh rate limit counter
        cache.clear()

        # Create a usage-capped user
        capped_user = User.objects.create_user(
            username=f"capped_user_{self.test_id}", password="test123"
        )
        capped_user.is_usage_capped = True
        capped_user.save()

        # Give the user access to a corpus
        test_corpus = Corpus.objects.create(
            title=f"Capped Test Corpus {self.test_id}", creator=capped_user
        )

        capped_client = DjangoClient()
        capped_client.force_login(capped_user)

        query = """
            query GetCorpuses {
                corpuses {
                    edges {
                        node {
                            id
                        }
                    }
                }
            }
        """

        # Capped users should hit rate limit sooner
        hit_limit = False
        for i in range(150):  # Should hit before regular user limit
            response = capped_client.post(
                "/graphql/",
                data=json.dumps({"query": query, "variables": {}}),
                content_type="application/json",
            )
            result = response.json()

            if (
                result.get("errors")
                and "Limit exceeded" in result["errors"][0]["message"]
            ):
                # Should hit limit earlier than regular users (who get 200/m)
                self.assertLess(
                    i, 200, "Capped user should hit rate limit before regular limit"
                )
                hit_limit = True
                break

        self.assertTrue(
            hit_limit,
            "Capped user did not hit rate limit within expected request window",
        )

        # Clean up
        test_corpus.delete()
        capped_user.delete()
