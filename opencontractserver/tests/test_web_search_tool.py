"""
Tests for the web search agent tool.

Covers:
  - BaseTool class and Settings schema
  - Database-level enablement gating via is_configured()
  - Tool registration in AVAILABLE_TOOLS and ToolFunctionRegistry
  - SearchResult formatting
  - Rate limiter behaviour
  - Provider implementations (mocked HTTP)
  - Settings retrieval from PipelineSettings
  - aweb_search() end-to-end with mocked provider
  - GraphQL tool-secrets mutations
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from django.test import TestCase, override_settings

from opencontractserver.constants.web_search import (
    BRAVE_PROVIDER,
    TAVILY_PROVIDER,
    WEB_SEARCH_MAX_SNIPPET_CHARS,
    WEB_SEARCH_SETTINGS_KEY,
)
from opencontractserver.llms.tools.base_tool import BaseTool
from opencontractserver.llms.tools.tool_registry import (
    AVAILABLE_TOOLS,
    ToolCategory,
    ToolFunctionRegistry,
)
from opencontractserver.llms.tools.web_search_tools import (
    _PROVIDERS,
    SearchResult,
    WebSearchTool,
    _RateLimiter,
    aweb_search,
)

# ============================================================================
# BaseTool class tests
# ============================================================================


class TestBaseTool:
    """Test the BaseTool base class."""

    def test_full_settings_key(self):
        assert WebSearchTool.full_settings_key() == "tool:web_search"

    def test_full_settings_key_requires_tool_key(self):
        class BadTool(BaseTool):
            tool_key = ""

        with pytest.raises(ValueError, match="non-empty"):
            BadTool.full_settings_key()

    def test_get_schema(self):
        schema = WebSearchTool.get_schema()
        assert "api_key" in schema
        assert "provider" in schema
        assert schema["api_key"]["type"] == "secret"
        assert schema["api_key"]["required"] is True
        assert schema["provider"]["type"] == "optional"

    def test_is_configured_false_when_no_settings(self):
        with patch.object(WebSearchTool, "get_settings", return_value={}):
            assert WebSearchTool.is_configured() is False

    def test_is_configured_false_when_empty_api_key(self):
        with patch.object(
            WebSearchTool,
            "get_settings",
            return_value={"api_key": "", "provider": "brave"},
        ):
            assert WebSearchTool.is_configured() is False

    def test_is_configured_true_when_api_key_present(self):
        with patch.object(
            WebSearchTool,
            "get_settings",
            return_value={"api_key": "test-key", "provider": "brave"},
        ):
            assert WebSearchTool.is_configured() is True

    def test_tool_without_settings_always_configured(self):
        class SimpleTool(BaseTool):
            tool_key = "simple"

        assert SimpleTool.is_configured() is True

    def test_validate_returns_list(self):
        with patch.object(WebSearchTool, "get_settings", return_value={}):
            is_valid, errors = WebSearchTool.validate()
            assert isinstance(errors, list)


# ============================================================================
# Registration tests
# ============================================================================


class TestWebSearchRegistration:
    """Verify the web_search tool is properly registered."""

    def test_web_search_in_available_tools(self):
        tool = next((t for t in AVAILABLE_TOOLS if t.name == "web_search"), None)
        assert tool is not None, "web_search not in AVAILABLE_TOOLS"
        assert tool.category == ToolCategory.WEB

    def test_web_search_parameters(self):
        tool = next(t for t in AVAILABLE_TOOLS if t.name == "web_search")
        param_names = [p[0] for p in tool.parameters]
        assert "query" in param_names
        assert "num_results" in param_names
        assert "search_type" in param_names

    def test_web_search_in_function_registry(self):
        registry = ToolFunctionRegistry.get()
        entry = registry.resolve("web_search")
        assert entry is not None, "web_search not in ToolFunctionRegistry"
        assert asyncio.iscoroutinefunction(entry.async_func)

    def test_web_search_has_tool_class(self):
        registry = ToolFunctionRegistry.get()
        entry = registry.resolve("web_search")
        assert entry.tool_class is WebSearchTool

    def test_web_search_alias(self):
        registry = ToolFunctionRegistry.get()
        entry = registry.resolve("search_web")
        assert entry is not None, "search_web alias not registered"
        assert entry.definition.name == "web_search"


# ============================================================================
# Database-level enablement gating
# ============================================================================


class TestEnablementGating:
    """Test that to_core_tool() respects is_configured() gate."""

    def test_to_core_tool_returns_tool_when_configured(self):
        registry = ToolFunctionRegistry.get()
        with patch.object(WebSearchTool, "is_configured", return_value=True):
            core_tool = registry.to_core_tool("web_search")
        assert core_tool is not None
        assert core_tool.metadata.name == "web_search"

    def test_to_core_tool_returns_none_when_not_configured(self):
        registry = ToolFunctionRegistry.get()
        with patch.object(WebSearchTool, "is_configured", return_value=False):
            core_tool = registry.to_core_tool("web_search")
        assert core_tool is None

    def test_to_core_tool_skips_on_config_check_error(self):
        registry = ToolFunctionRegistry.get()
        with patch.object(
            WebSearchTool, "is_configured", side_effect=RuntimeError("DB down")
        ):
            core_tool = registry.to_core_tool("web_search")
        assert core_tool is None

    def test_tools_without_tool_class_always_resolve(self):
        """Non-BaseTool tools resolve unconditionally."""
        registry = ToolFunctionRegistry.get()
        # load_document_summary has no tool_class
        entry = registry.resolve("load_document_summary")
        assert entry is not None
        assert entry.tool_class is None
        core_tool = registry.to_core_tool("load_document_summary")
        assert core_tool is not None


# ============================================================================
# SearchResult formatting
# ============================================================================


class TestSearchResult:
    def test_basic_format(self):
        test_url = "https://example.com"
        r = SearchResult(title="Test", url=test_url, snippet="Hello")
        formatted = r.format(1)
        assert "### Result 1" in formatted
        assert "**Test**" in formatted
        assert test_url in formatted
        assert "Hello" in formatted

    def test_snippet_truncation(self):
        long_snippet = "x" * (WEB_SEARCH_MAX_SNIPPET_CHARS + 100)
        r = SearchResult(title="T", url="https://x.com", snippet=long_snippet)
        formatted = r.format(1)
        assert "..." in formatted
        # The snippet portion should be truncated
        assert len(formatted) < len(long_snippet) + 200

    def test_optional_fields(self):
        r = SearchResult(
            title="T",
            url="https://x.com",
            snippet="S",
            published_date="2024-01-01",
            source="example.com",
        )
        formatted = r.format(1)
        assert "Published: 2024-01-01" in formatted
        assert "Source: example.com" in formatted


# ============================================================================
# Rate limiter
# ============================================================================


class TestRateLimiter:
    def test_allows_within_limit(self):
        async def _run():
            limiter = _RateLimiter(max_per_minute=5)
            for _ in range(5):
                await limiter.acquire()
            # Should not block or raise

        asyncio.run(_run())

    def test_tracks_timestamps(self):
        async def _run():
            limiter = _RateLimiter(max_per_minute=3)
            await limiter.acquire()
            await limiter.acquire()
            assert len(limiter._timestamps) == 2

        asyncio.run(_run())

    def test_blocks_when_capacity_full(self):
        """The limiter should sleep when the window is full."""

        async def _run():
            limiter = _RateLimiter(max_per_minute=2)
            # Fill up the window
            await limiter.acquire()
            await limiter.acquire()

            # The next acquire should trigger asyncio.sleep because the
            # window is now full.
            with patch("asyncio.sleep", new_callable=AsyncMock):
                # Advance timestamps so the oldest slot expires on next check
                limiter._timestamps[0] = limiter._timestamps[0] - 61.0
                await limiter.acquire()
                # sleep may or may not be called depending on timing, but the
                # acquire should succeed.  If timestamps were not expired
                # naturally, sleep would have been called.
                assert len(limiter._timestamps) == 2  # old one evicted, new one added

        asyncio.run(_run())

    def test_blocks_and_sleeps_when_window_full(self):
        """Verify asyncio.sleep is called when all slots are occupied."""

        async def _run():
            limiter = _RateLimiter(max_per_minute=1)
            await limiter.acquire()
            assert len(limiter._timestamps) == 1

            # Patch sleep to simulate waiting and then expire the timestamp
            original_sleep = asyncio.sleep

            async def fake_sleep(duration):
                # Simulate time passing by expiring the oldest timestamp
                limiter._timestamps[0] = limiter._timestamps[0] - 61.0
                await original_sleep(0)  # yield control

            with patch("asyncio.sleep", side_effect=fake_sleep) as mock_sleep:
                await limiter.acquire()
                mock_sleep.assert_called_once()

        asyncio.run(_run())


# ============================================================================
# Provider tests (mocked HTTP)
# ============================================================================


class TestBraveSearchProvider:
    def test_brave_search_parses_response(self):
        from opencontractserver.llms.tools.web_search_tools import BraveSearchProvider

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "web": {
                "results": [
                    {
                        "title": "Test Result",
                        "url": "https://example.com/test",
                        "description": "A test result snippet",
                        "page_age": "2024-01-15",
                        "meta_url": {"hostname": "example.com"},
                    },
                ]
            }
        }

        provider = BraveSearchProvider()

        async def _run():
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client_cls.return_value = mock_client

                return await provider.search(
                    query="test", num_results=5, api_key="test-key"
                )

        results = asyncio.run(_run())

        assert len(results) == 1
        assert results[0].title == "Test Result"
        assert results[0].url == "https://example.com/test"
        assert results[0].snippet == "A test result snippet"
        assert results[0].published_date == "2024-01-15"
        assert results[0].source == "example.com"


class TestTavilySearchProvider:
    def test_tavily_search_parses_response(self):
        from opencontractserver.llms.tools.web_search_tools import TavilySearchProvider

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {
                    "title": "Tavily Result",
                    "url": "https://example.com/tavily",
                    "content": "Tavily content snippet",
                    "published_date": "2024-02-01",
                },
            ]
        }

        provider = TavilySearchProvider()

        async def _run():
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_client_cls.return_value = mock_client

                return await provider.search(
                    query="test", num_results=5, api_key="test-key"
                )

        results = asyncio.run(_run())

        assert len(results) == 1
        assert results[0].title == "Tavily Result"
        assert results[0].snippet == "Tavily content snippet"


# ============================================================================
# aweb_search() integration tests (mocked settings + provider)
# ============================================================================


class TestAwebSearch:
    def test_empty_query(self):
        result = asyncio.run(aweb_search(query=""))
        assert "Error" in result
        assert "empty" in result.lower()

    def test_missing_api_key(self):
        async def _run():
            with patch(
                "opencontractserver.llms.tools.web_search_tools.WebSearchTool.get_settings",
                return_value={},
            ):
                return await aweb_search(query="test query")

        result = asyncio.run(_run())
        assert "not configured" in result.lower()

    def test_unknown_provider(self):
        async def _run():
            with patch(
                "opencontractserver.llms.tools.web_search_tools.WebSearchTool.get_settings",
                return_value={"api_key": "key", "provider": "nonexistent"},
            ):
                return await aweb_search(query="test query")

        result = asyncio.run(_run())
        assert "unknown search provider" in result.lower()

    def test_successful_search(self):
        mock_results = [
            SearchResult(
                title="Result 1",
                url="https://example.com/1",
                snippet="First result",
            ),
            SearchResult(
                title="Result 2",
                url="https://example.com/2",
                snippet="Second result",
            ),
        ]

        async def _run():
            with patch(
                "opencontractserver.llms.tools.web_search_tools.WebSearchTool.get_settings",
                return_value={"api_key": "test-key", "provider": BRAVE_PROVIDER},
            ), patch(
                "opencontractserver.llms.tools.web_search_tools._get_limiter"
            ) as mock_limiter_fn, patch.object(
                _PROVIDERS[BRAVE_PROVIDER],
                "search",
                new_callable=AsyncMock,
                return_value=mock_results,
            ):
                mock_limiter = MagicMock()
                mock_limiter.acquire = AsyncMock()
                mock_limiter_fn.return_value = mock_limiter

                return await aweb_search(query="test query", num_results=2)

        result = asyncio.run(_run())
        assert "Result 1" in result
        assert "Result 2" in result
        assert "https://example.com/1" in result

    def test_provider_error_handled(self):
        async def _run():
            with patch(
                "opencontractserver.llms.tools.web_search_tools.WebSearchTool.get_settings",
                return_value={"api_key": "test-key", "provider": BRAVE_PROVIDER},
            ), patch(
                "opencontractserver.llms.tools.web_search_tools._get_limiter"
            ) as mock_limiter_fn, patch.object(
                _PROVIDERS[BRAVE_PROVIDER],
                "search",
                new_callable=AsyncMock,
                side_effect=ConnectionError("network error"),
            ):
                mock_limiter = MagicMock()
                mock_limiter.acquire = AsyncMock()
                mock_limiter_fn.return_value = mock_limiter

                return await aweb_search(query="test")

        result = asyncio.run(_run())
        assert "Error" in result
        assert "ConnectionError" in result

    def test_no_results(self):
        async def _run():
            with patch(
                "opencontractserver.llms.tools.web_search_tools.WebSearchTool.get_settings",
                return_value={"api_key": "test-key", "provider": BRAVE_PROVIDER},
            ), patch(
                "opencontractserver.llms.tools.web_search_tools._get_limiter"
            ) as mock_limiter_fn, patch.object(
                _PROVIDERS[BRAVE_PROVIDER],
                "search",
                new_callable=AsyncMock,
                return_value=[],
            ):
                mock_limiter = MagicMock()
                mock_limiter.acquire = AsyncMock()
                mock_limiter_fn.return_value = mock_limiter

                return await aweb_search(query="obscure query xyz")

        result = asyncio.run(_run())
        assert "No results" in result

    def test_num_results_clamped(self):
        """num_results should be clamped to [1, MAX]."""

        async def _run():
            with patch(
                "opencontractserver.llms.tools.web_search_tools.WebSearchTool.get_settings",
                return_value={"api_key": "key", "provider": BRAVE_PROVIDER},
            ), patch(
                "opencontractserver.llms.tools.web_search_tools._get_limiter"
            ) as mock_limiter_fn, patch.object(
                _PROVIDERS[BRAVE_PROVIDER],
                "search",
                new_callable=AsyncMock,
                return_value=[],
            ) as mock_search:
                mock_limiter = MagicMock()
                mock_limiter.acquire = AsyncMock()
                mock_limiter_fn.return_value = mock_limiter

                await aweb_search(query="test", num_results=100)
                # num_results should be clamped to MAX
                call_kwargs = mock_search.call_args
                assert call_kwargs[1]["num_results"] <= 20

        asyncio.run(_run())

    def test_invalid_search_type_defaults(self):
        """Invalid search_type should default to 'general'."""

        async def _run():
            with patch(
                "opencontractserver.llms.tools.web_search_tools.WebSearchTool.get_settings",
                return_value={"api_key": "key", "provider": BRAVE_PROVIDER},
            ), patch(
                "opencontractserver.llms.tools.web_search_tools._get_limiter"
            ) as mock_limiter_fn, patch.object(
                _PROVIDERS[BRAVE_PROVIDER],
                "search",
                new_callable=AsyncMock,
                return_value=[],
            ) as mock_search:
                mock_limiter = MagicMock()
                mock_limiter.acquire = AsyncMock()
                mock_limiter_fn.return_value = mock_limiter

                await aweb_search(query="test", search_type="invalid")
                assert mock_search.call_args[1]["search_type"] == "general"

        asyncio.run(_run())


# ============================================================================
# PipelineSettings tool secrets integration
# ============================================================================


class TestPipelineSettingsToolSecrets(TestCase):
    """Test PipelineSettings tool secret helpers."""

    def setUp(self):
        """Invalidate the singleton cache so each test sees fresh DB state.

        Without this, parallel xdist workers can hand back a cached instance
        whose ``modified_by`` FK references a User row deleted by a sibling
        test, causing ``SET CONSTRAINTS ALL IMMEDIATE`` to fail at teardown.
        """
        from opencontractserver.documents.models import PipelineSettings

        PipelineSettings._invalidate_cache()

    def tearDown(self):
        """Clean up tool settings to avoid leaking state to other tests."""
        from opencontractserver.documents.models import PipelineSettings

        # Bypass cache to read live DB state; null out any stale modified_by
        # FK so the post-test ``SET CONSTRAINTS`` check doesn't fail when a
        # previously-deleted user remains referenced.
        ps = PipelineSettings.get_instance(use_cache=False)
        ps.modified_by = None
        ps.delete_tool_settings(WEB_SEARCH_SETTINGS_KEY)
        ps.save()

    @override_settings(
        PIPELINE_SETTINGS_CACHE_TTL_SECONDS=0,
    )
    def test_get_tool_settings_empty(self):
        from opencontractserver.documents.models import PipelineSettings

        ps = PipelineSettings.get_instance()
        settings = ps.get_tool_settings(WEB_SEARCH_SETTINGS_KEY)
        assert settings == {}

    @override_settings(
        PIPELINE_SETTINGS_CACHE_TTL_SECONDS=0,
    )
    def test_update_and_get_tool_settings(self):
        from opencontractserver.documents.models import PipelineSettings

        ps = PipelineSettings.get_instance()
        ps.update_tool_settings(
            WEB_SEARCH_SETTINGS_KEY,
            settings={"provider": BRAVE_PROVIDER},
            secrets={"api_key": "test-brave-key-123"},
        )
        ps.save()

        # Re-fetch
        ps.refresh_from_db()
        settings = ps.get_tool_settings(WEB_SEARCH_SETTINGS_KEY)
        assert settings["provider"] == BRAVE_PROVIDER
        assert settings["api_key"] == "test-brave-key-123"

    @override_settings(
        PIPELINE_SETTINGS_CACHE_TTL_SECONDS=0,
    )
    def test_delete_tool_settings(self):
        from opencontractserver.documents.models import PipelineSettings

        ps = PipelineSettings.get_instance()
        ps.update_tool_settings(
            WEB_SEARCH_SETTINGS_KEY,
            settings={"provider": TAVILY_PROVIDER},
            secrets={"api_key": "tavily-key"},
        )
        ps.save()

        ps.delete_tool_settings(WEB_SEARCH_SETTINGS_KEY)
        ps.save()

        ps.refresh_from_db()
        assert ps.get_tool_settings(WEB_SEARCH_SETTINGS_KEY) == {}

    @override_settings(
        PIPELINE_SETTINGS_CACHE_TTL_SECONDS=0,
    )
    def test_get_tools_with_secrets(self):
        from opencontractserver.documents.models import PipelineSettings

        ps = PipelineSettings.get_instance()
        ps.update_tool_settings(
            WEB_SEARCH_SETTINGS_KEY,
            settings={},
            secrets={"api_key": "key123"},
        )
        ps.save()

        ps.refresh_from_db()
        tools = ps.get_tools_with_secrets()
        assert WEB_SEARCH_SETTINGS_KEY in tools

    @override_settings(
        PIPELINE_SETTINGS_CACHE_TTL_SECONDS=0,
    )
    def test_tool_secrets_separate_from_component_secrets(self):
        """Tool secrets should not interfere with pipeline component secrets."""
        from opencontractserver.documents.models import PipelineSettings

        ps = PipelineSettings.get_instance()

        # Store both tool and component secrets
        ps.update_secrets("some.pipeline.Component", {"api_key": "comp-key"})
        ps.update_tool_settings(
            WEB_SEARCH_SETTINGS_KEY,
            settings={},
            secrets={"api_key": "tool-key"},
        )
        ps.save()

        ps.refresh_from_db()

        # Tool helper should only return tool keys
        tools = ps.get_tools_with_secrets()
        assert WEB_SEARCH_SETTINGS_KEY in tools
        assert "some.pipeline.Component" not in tools

        # Component secret should still be accessible
        comp_secrets = ps.get_component_secrets("some.pipeline.Component")
        assert comp_secrets["api_key"] == "comp-key"


# ============================================================================
# GraphQL mutation tests for tool secrets
# ============================================================================


class TestToolSecretsMutations(TestCase):
    """Test GraphQL mutations for tool secrets (UpdateToolSecrets, DeleteToolSecrets)."""

    def setUp(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.superuser = User.objects.create_superuser(
            username="tool_admin",
            password="testpass123",
            email="tool_admin@test.com",
        )
        self.regular_user = User.objects.create_user(
            username="tool_regular",
            password="testpass123",
            email="tool_regular@test.com",
        )

    @override_settings(
        PIPELINE_SETTINGS_CACHE_TTL_SECONDS=0,
    )
    def test_update_tool_secrets_superuser(self):
        from graphene.test import Client

        from config.graphql.schema import schema

        client = Client(schema)
        context = MagicMock()
        context.user = self.superuser

        result = client.execute(
            """
            mutation {
                updateToolSecrets(
                    toolKey: "tool:web_search"
                    secrets: {api_key: "brave-test-key"}
                    settings: {provider: "brave"}
                ) {
                    ok
                    message
                    toolsWithSecrets
                }
            }
            """,
            context=context,
        )

        data = result["data"]["updateToolSecrets"]
        assert data["ok"] is True
        assert "tool:web_search" in data["toolsWithSecrets"]

    @override_settings(
        PIPELINE_SETTINGS_CACHE_TTL_SECONDS=0,
    )
    def test_update_tool_secrets_regular_user_rejected(self):
        from graphene.test import Client

        from config.graphql.schema import schema

        client = Client(schema)
        context = MagicMock()
        context.user = self.regular_user

        result = client.execute(
            """
            mutation {
                updateToolSecrets(
                    toolKey: "tool:web_search"
                    secrets: {api_key: "should-fail"}
                ) {
                    ok
                    message
                }
            }
            """,
            context=context,
        )

        data = result["data"]["updateToolSecrets"]
        assert data["ok"] is False
        assert "superuser" in data["message"].lower()

    @override_settings(
        PIPELINE_SETTINGS_CACHE_TTL_SECONDS=0,
    )
    def test_unsupported_provider_rejected(self):
        from graphene.test import Client

        from config.graphql.schema import schema

        client = Client(schema)
        context = MagicMock()
        context.user = self.superuser

        result = client.execute(
            """
            mutation {
                updateToolSecrets(
                    toolKey: "tool:web_search"
                    secrets: {api_key: "some-key"}
                    settings: {provider: "duckduckgo"}
                ) {
                    ok
                    message
                }
            }
            """,
            context=context,
        )

        data = result["data"]["updateToolSecrets"]
        assert data["ok"] is False
        assert "Unsupported provider" in data["message"]

    @override_settings(
        PIPELINE_SETTINGS_CACHE_TTL_SECONDS=0,
    )
    def test_invalid_tool_key_rejected(self):
        from graphene.test import Client

        from config.graphql.schema import schema

        client = Client(schema)
        context = MagicMock()
        context.user = self.superuser

        result = client.execute(
            """
            mutation {
                updateToolSecrets(
                    toolKey: "invalid_no_prefix"
                    secrets: {api_key: "key"}
                ) {
                    ok
                    message
                }
            }
            """,
            context=context,
        )

        data = result["data"]["updateToolSecrets"]
        assert data["ok"] is False
        assert "tool:" in data["message"]

    @override_settings(
        PIPELINE_SETTINGS_CACHE_TTL_SECONDS=0,
    )
    def test_delete_tool_secrets(self):
        from opencontractserver.documents.models import PipelineSettings

        # First store some secrets
        ps = PipelineSettings.get_instance()
        ps.update_tool_settings(
            WEB_SEARCH_SETTINGS_KEY,
            settings={"provider": "brave"},
            secrets={"api_key": "to-delete"},
        )
        ps.save()

        from graphene.test import Client

        from config.graphql.schema import schema

        client = Client(schema)
        context = MagicMock()
        context.user = self.superuser

        result = client.execute(
            """
            mutation {
                deleteToolSecrets(toolKey: "tool:web_search") {
                    ok
                    message
                    toolsWithSecrets
                }
            }
            """,
            context=context,
        )

        data = result["data"]["deleteToolSecrets"]
        assert data["ok"] is True
        assert "tool:web_search" not in (data["toolsWithSecrets"] or [])
