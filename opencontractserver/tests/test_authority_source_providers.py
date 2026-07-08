"""Tests for the authority source-provider registry read surface (Phase 4).

``AuthoritySourceProviderService.list_providers`` surfaces the auto-discovered
provider classes (US Code / eCFR / Federal Register / agentic web locator) with
their ClassVars + a ``has_credentials`` flag, superuser-gated. This is the first
time the providers ("scrapers") are visible through the API at all.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.enrichment.services import AuthoritySourceProviderService

User = get_user_model()


class AuthoritySourceProviderServiceTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_user(
            username="root", password="p", is_superuser=True, is_staff=True
        )
        self.regular = User.objects.create_user(username="joe", password="p")

    def test_lists_registered_providers_for_admin(self):
        rows = AuthoritySourceProviderService.list_providers(self.superuser)
        assert rows, "expected the registry to surface providers"
        names = {r["name"] for r in rows}
        # The shipped public-domain providers are auto-discovered.
        assert "USCodeAuthoritySourceProvider" in names
        # Every row carries the registry ClassVars + the vault flag.
        sample = next(r for r in rows if r["name"] == "USCodeAuthoritySourceProvider")
        assert isinstance(sample["supported_prefixes"], list)
        assert sample["supported_prefixes"], "USC provider declares prefixes"
        assert sample["license"] == "public-domain"
        assert sample["enabled"] is True
        assert sample["has_credentials"] is False  # no secrets stored
        assert "requires_approval" in sample
        assert "priority" in sample

    def test_ordered_by_priority_then_name(self):
        rows = AuthoritySourceProviderService.list_providers(self.superuser)
        priorities = [(r["priority"] or 0) for r in rows]
        assert priorities == sorted(priorities)

    def test_empty_for_non_admin(self):
        assert AuthoritySourceProviderService.list_providers(self.regular) == []

    def test_vault_read_failure_does_not_break_listing(self):
        # A secrets-vault read error must NOT break the provider listing: the
        # service logs a warning, treats secrets as empty, and still returns the
        # registry rows with has_credentials=False.
        from unittest import mock

        with mock.patch(
            "opencontractserver.documents.models.PipelineSettings.get_instance",
            side_effect=RuntimeError("vault down"),
        ):
            rows = AuthoritySourceProviderService.list_providers(self.superuser)
        assert rows, "listing must survive a vault read failure"
        assert all(r["has_credentials"] is False for r in rows)


class _Ctx:
    def __init__(self, user):
        self.user = user
        self.META = {}


def _run(query, user):
    from config.graphql.schema import schema
    from config.graphql.testing import Client

    return Client(schema, context_value=_Ctx(user)).execute(query)


_PROVIDERS_QUERY = """
    query {
      authoritySourceProviders {
        name title supportedPrefixes license priority
        requiresApproval enabled hasCredentials
      }
    }
"""


class AuthoritySourceProvidersGraphQLTests(TestCase):
    """The provider registry exercised through the GraphQL query the Scrapers tab
    calls — superuser sees rows, non-admin sees an empty list."""

    def setUp(self):
        self.superuser = User.objects.create_user(
            username="root", password="p", is_superuser=True, is_staff=True
        )
        self.regular = User.objects.create_user(username="joe", password="p")

    def test_query_returns_providers_for_admin(self):
        res = _run(_PROVIDERS_QUERY, self.superuser)
        self.assertIsNone(res.get("errors"), res.get("errors"))
        rows = res["data"]["authoritySourceProviders"]
        names = {r["name"] for r in rows}
        assert "USCodeAuthoritySourceProvider" in names
        sample = next(r for r in rows if r["name"] == "USCodeAuthoritySourceProvider")
        assert sample["enabled"] is True
        assert sample["hasCredentials"] is False
        assert isinstance(sample["supportedPrefixes"], list)

    def test_query_empty_for_non_admin(self):
        res = _run(_PROVIDERS_QUERY, self.regular)
        self.assertIsNone(res.get("errors"), res.get("errors"))
        assert res["data"]["authoritySourceProviders"] == []
