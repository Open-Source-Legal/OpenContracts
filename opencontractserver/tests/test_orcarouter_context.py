"""Dynamic OrcaRouter context-window resolution (``llms/orcarouter_context.py``).

Unit tests drive the ``/models`` fetch through a real ``httpx.Client`` backed by
``httpx.MockTransport``, so request construction, status handling and JSON
parsing run for real without touching the network. The integration test
checks the end-to-end path: an agent build primes the cache and
``get_context_window_for_model`` then serves the gateway's value.
"""

from __future__ import annotations

import json
import os
from unittest import mock

import httpx
from django.test import SimpleTestCase, TestCase

from opencontractserver.constants.context_guardrails import (
    ORCAROUTER_FALLBACK_CONTEXT_WINDOW,
    ORCAROUTER_MODELS_CACHE_TTL_SECONDS,
)
from opencontractserver.documents.models import PipelineSettings
from opencontractserver.llms import orcarouter_context
from opencontractserver.llms.context_guardrails import get_context_window_for_model
from opencontractserver.llms.model_factory import build_agent_model
from opencontractserver.llms.orcarouter_context import (
    clear_orcarouter_context_cache,
    get_orcarouter_context_window,
    refresh_orcarouter_context_windows,
)
from opencontractserver.pipeline.registry import reset_registry

BASE_URL = "https://gateway.test/v1"

LISTING = {
    "object": "list",
    "data": [
        {"id": "orcarouter/auto", "context_length": 200_000},
        {"id": "google/gemini-3.5-flash", "context_window": 1_048_576},
        {"id": "openai/gpt-4o"},  # no window advertised
        {"id": "bad/flag", "context_length": True},  # bool is not a size
        {"id": "bad/zero", "context_length": 0},
        {"context_length": 99},  # no id
    ],
}


def _transport(
    requests: list[httpx.Request], *, status: int = 200, body: object = LISTING
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        content = body if isinstance(body, (bytes, str)) else json.dumps(body)
        return httpx.Response(status, content=content)

    return httpx.MockTransport(handler)


def _patched_get(transport: httpx.MockTransport):
    """Route module-level ``httpx.get`` through ``transport``."""

    def fake_get(url, **kwargs):
        with httpx.Client(transport=transport) as client:
            return client.get(url, **kwargs)

    return mock.patch.object(orcarouter_context.httpx, "get", side_effect=fake_get)


class OrcaRouterContextCacheTests(SimpleTestCase):
    def setUp(self):
        clear_orcarouter_context_cache()
        self.addCleanup(clear_orcarouter_context_cache)

    def test_fallback_before_any_fetch(self):
        self.assertEqual(
            get_orcarouter_context_window("orcarouter/auto"),
            ORCAROUTER_FALLBACK_CONTEXT_WINDOW,
        )

    def test_fetch_parses_listing_and_sends_key_to_models_endpoint(self):
        requests: list[httpx.Request] = []
        with _patched_get(_transport(requests)):
            refresh_orcarouter_context_windows(BASE_URL + "/", "sk-orca")

        self.assertEqual(len(requests), 1)
        self.assertEqual(str(requests[0].url), f"{BASE_URL}/models")
        self.assertEqual(requests[0].headers["Authorization"], "Bearer sk-orca")
        self.assertEqual(get_orcarouter_context_window("orcarouter/auto"), 200_000)
        self.assertEqual(
            get_orcarouter_context_window("google/gemini-3.5-flash"), 1_048_576
        )
        for missing in ("openai/gpt-4o", "bad/flag", "bad/zero", "unlisted/x"):
            self.assertEqual(
                get_orcarouter_context_window(missing),
                ORCAROUTER_FALLBACK_CONTEXT_WINDOW,
                missing,
            )

    def test_redirects_are_not_followed(self):
        """The bearer key must never be forwarded to a redirect target."""
        with mock.patch.object(orcarouter_context.httpx, "get") as get:
            get.return_value = httpx.Response(
                200, json=LISTING, request=httpx.Request("GET", BASE_URL)
            )
            refresh_orcarouter_context_windows(BASE_URL, "sk-orca")
        self.assertIs(get.call_args.kwargs["follow_redirects"], False)

    def test_cache_is_reused_within_ttl_and_refetched_after(self):
        requests: list[httpx.Request] = []
        with _patched_get(_transport(requests)), mock.patch.object(
            orcarouter_context.time, "monotonic", return_value=1_000.0
        ) as clock:
            refresh_orcarouter_context_windows(BASE_URL, "k")
            refresh_orcarouter_context_windows(BASE_URL, "k")
            self.assertEqual(len(requests), 1)

            clock.return_value = 1_000.0 + ORCAROUTER_MODELS_CACHE_TTL_SECONDS
            refresh_orcarouter_context_windows(BASE_URL, "k")
            self.assertEqual(len(requests), 2)

    def test_http_error_keeps_previous_windows_and_is_not_retried_in_ttl(self):
        ok: list[httpx.Request] = []
        with _patched_get(_transport(ok)):
            refresh_orcarouter_context_windows(BASE_URL, "k")
        self.assertEqual(get_orcarouter_context_window("orcarouter/auto"), 200_000)

        # Force staleness, then fail: the old listing must survive.
        orcarouter_context._cache.last_fetch_at = None
        failed: list[httpx.Request] = []
        with _patched_get(_transport(failed, status=401)), self.assertLogs(
            "opencontractserver.llms.orcarouter_context", level="WARNING"
        ):
            refresh_orcarouter_context_windows(BASE_URL, "bad-key")
            refresh_orcarouter_context_windows(BASE_URL, "bad-key")
        self.assertEqual(len(failed), 1)
        self.assertEqual(get_orcarouter_context_window("orcarouter/auto"), 200_000)

    def test_network_error_falls_back_without_raising(self):
        def boom(url, **kwargs):
            raise httpx.ConnectError("unreachable")

        with mock.patch.object(
            orcarouter_context.httpx, "get", side_effect=boom
        ), self.assertLogs(
            "opencontractserver.llms.orcarouter_context", level="WARNING"
        ):
            refresh_orcarouter_context_windows(BASE_URL, "k")
        self.assertEqual(
            get_orcarouter_context_window("orcarouter/auto"),
            ORCAROUTER_FALLBACK_CONTEXT_WINDOW,
        )

    def test_malformed_endpoint_falls_back_without_raising(self):
        """A scheme-valid but malformed base_url makes httpx raise InvalidURL
        (not an HTTPError) before any I/O; it must still never propagate."""
        with self.assertLogs(
            "opencontractserver.llms.orcarouter_context", level="WARNING"
        ):
            refresh_orcarouter_context_windows("http://[::1", "k")
        self.assertEqual(
            get_orcarouter_context_window("orcarouter/auto"),
            ORCAROUTER_FALLBACK_CONTEXT_WINDOW,
        )

    def test_non_json_and_windowless_listings_fall_back(self):
        bodies: tuple[object, ...] = (
            b"<html>gateway error</html>",
            {"data": [{"id": "a/b"}]},
            [],
        )
        for body in bodies:
            clear_orcarouter_context_cache()
            with _patched_get(_transport([], body=body)), self.assertLogs(
                "opencontractserver.llms.orcarouter_context", level="WARNING"
            ):
                refresh_orcarouter_context_windows(BASE_URL, "k")
            self.assertEqual(
                get_orcarouter_context_window("a/b"),
                ORCAROUTER_FALLBACK_CONTEXT_WINDOW,
                body,
            )

    def test_generic_lookup_routes_orcarouter_specs_to_cache(self):
        with _patched_get(_transport([])):
            refresh_orcarouter_context_windows(BASE_URL, "k")
        self.assertEqual(
            get_context_window_for_model("orcarouter:orcarouter/auto"), 200_000
        )
        # Non-OrcaRouter specs still use the static table, even when the
        # routed id text overlaps a known model name.
        self.assertEqual(
            get_context_window_for_model("anthropic:claude-opus-4-6"), 200_000
        )


class OrcaRouterContextBuildIntegrationTests(TestCase):
    """Building an ``orcarouter:`` agent model primes the window used later
    by compaction, using the DB-configured endpoint."""

    def setUp(self):
        reset_registry()
        self.addCleanup(reset_registry)
        PipelineSettings.clear_cache()
        self.addCleanup(PipelineSettings.clear_cache)
        clear_orcarouter_context_cache()
        self.addCleanup(clear_orcarouter_context_cache)
        env = mock.patch.dict(os.environ, {"ORCAROUTER_API_KEY": "sk-orca-env"})
        env.start()
        self.addCleanup(env.stop)

    def test_build_then_lookup_uses_gateway_window(self):
        from opencontractserver.pipeline.registry import (
            get_llm_provider_by_key_cached,
        )

        defn = get_llm_provider_by_key_cached("orcarouter")
        assert defn is not None
        instance = PipelineSettings.get_instance()
        instance.component_settings = {defn.class_name: {"base_url": BASE_URL}}
        instance.save()

        self.assertEqual(
            get_context_window_for_model("orcarouter:orcarouter/auto"),
            ORCAROUTER_FALLBACK_CONTEXT_WINDOW,
        )
        requests: list[httpx.Request] = []
        with _patched_get(_transport(requests)):
            build_agent_model("orcarouter:orcarouter/auto")

        self.assertEqual(len(requests), 1)
        self.assertEqual(str(requests[0].url), f"{BASE_URL}/models")
        self.assertEqual(requests[0].headers["Authorization"], "Bearer sk-orca-env")
        self.assertEqual(
            get_context_window_for_model("orcarouter:orcarouter/auto"), 200_000
        )
