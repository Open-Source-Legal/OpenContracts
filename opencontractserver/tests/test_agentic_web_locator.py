"""Unit and integration tests for AgenticWebLocatorProvider (Phase 4).

All tests mock ``_run_agent`` so no LLM calls or network requests are made.
Integration tests use TransactionTestCase and require --create-db.
"""

from __future__ import annotations

import asyncio
from unittest import TestCase
from unittest.mock import AsyncMock, patch

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase

from opencontractserver.annotations.models import AuthorityFrontier
from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.authorities import AuthoritySection
from opencontractserver.pipeline.authority_source_providers.agentic_web_locator_provider import (
    AgenticWebLocatorProvider,
    _LocatorOutput,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Helper: enabled subclass for tests (avoids mutating the real ClassVar)
# ---------------------------------------------------------------------------


class _EnabledLocator(AgenticWebLocatorProvider):
    """AgenticWebLocatorProvider with enabled=True for testing."""

    enabled = True


# ---------------------------------------------------------------------------
# Unit tests — no DB, no LLM
# ---------------------------------------------------------------------------


class CanHandleTests(TestCase):
    """can_handle reflects the enabled ClassVar."""

    def test_disabled_by_default(self):
        provider = AgenticWebLocatorProvider()
        # Default enabled=False → never selected.
        self.assertFalse(provider.can_handle("usc-15:78j"))
        self.assertFalse(provider.can_handle("act:some-obscure-law"))
        self.assertFalse(provider.can_handle("mystery-zz:99"))

    def test_enabled_claims_everything(self):
        provider = _EnabledLocator()
        self.assertTrue(provider.can_handle("usc-15:78j"))
        self.assertTrue(provider.can_handle("act:some-obscure-law"))
        self.assertTrue(provider.can_handle("cfr-40:part-60"))
        self.assertTrue(provider.can_handle("mystery-zz:99"))


class LocateImplTests(TestCase):
    """_locate_impl is pure — carries only citation + jurisdiction, never doc text."""

    def _locate(self, key: str, **kw):
        return AgenticWebLocatorProvider()._locate_impl(key, **kw)

    def test_url_is_empty(self):
        req = self._locate("act:some-obscure-law")
        self.assertEqual(
            req.url, "", "URL must be empty string (agent decides at fetch time)"
        )

    def test_canonical_key_preserved(self):
        req = self._locate("act:some-obscure-law")
        self.assertEqual(req.canonical_key, "act:some-obscure-law")

    def test_citation_defaults_to_key(self):
        req = self._locate("act:some-obscure-law")
        self.assertEqual(req.citation, "act:some-obscure-law")

    def test_citation_kwarg_overrides_key(self):
        req = self._locate("act:some-obscure-law", citation="Some Obscure Law § 1")
        self.assertEqual(req.citation, "Some Obscure Law § 1")

    def test_jurisdiction_in_extra(self):
        req = self._locate("act:some-obscure-law", jurisdiction="us-federal")
        self.assertEqual(req.extra.get("jurisdiction"), "us-federal")

    def test_jurisdiction_defaults_to_empty_string(self):
        req = self._locate("act:some-obscure-law")
        self.assertEqual(req.extra.get("jurisdiction"), "")

    def test_no_document_text_leaked(self):
        # Even if caller passes doc_text via kwargs, it must NOT appear in the request.
        req = self._locate("act:some-obscure-law", doc_text="SECRET DOCUMENT TEXT")
        self.assertNotIn("doc_text", req.extra)
        self.assertNotIn("SECRET", str(req))


class FetchImplFoundTests(TestCase):
    """_fetch_impl delegates to _run_agent; converts found=True result to AuthoritySection."""

    def _found_output(self) -> _LocatorOutput:
        return _LocatorOutput(
            found=True,
            source_url="https://uscode.house.gov/download/t15.zip",
            heading="Some Heading",
            text="Official statutory text here.",
            confidence=0.9,
        )

    def test_found_true_returns_one_section(self):
        provider = AgenticWebLocatorProvider()
        from opencontractserver.pipeline.base.base_authority_source_provider import (
            AuthorityRequest,
        )

        req = AuthorityRequest(
            canonical_key="act:some-obscure-law",
            url="",
            citation="act:some-obscure-law",
            extra={"jurisdiction": ""},
        )

        with patch.object(
            provider,
            "_run_agent",
            new=AsyncMock(return_value=self._found_output()),
        ):
            sections = provider._fetch_impl(req)

        self.assertEqual(len(sections), 1)
        sec = sections[0]
        self.assertIsInstance(sec, AuthoritySection)
        self.assertEqual(sec.key, "act:some-obscure-law")
        self.assertEqual(sec.heading, "Some Heading")
        self.assertEqual(sec.text, "Official statutory text here.")
        self.assertEqual(sec.source_url, "https://uscode.house.gov/download/t15.zip")

    def test_found_false_returns_empty_list(self):
        provider = AgenticWebLocatorProvider()
        from opencontractserver.pipeline.base.base_authority_source_provider import (
            AuthorityRequest,
        )

        req = AuthorityRequest(
            canonical_key="act:some-obscure-law",
            url="",
            citation="act:some-obscure-law",
            extra={"jurisdiction": ""},
        )
        not_found = _LocatorOutput(
            found=False,
            source_url="",
            heading="",
            text="",
            confidence=0.0,
        )

        with patch.object(
            provider,
            "_run_agent",
            new=AsyncMock(return_value=not_found),
        ):
            sections = provider._fetch_impl(req)

        self.assertEqual(sections, [])

    def test_found_true_empty_source_url_returns_empty_list(self):
        """found=True but no source_url is treated as not-found."""
        provider = AgenticWebLocatorProvider()
        from opencontractserver.pipeline.base.base_authority_source_provider import (
            AuthorityRequest,
        )

        req = AuthorityRequest(
            canonical_key="act:some-obscure-law",
            url="",
            citation="act:some-obscure-law",
            extra={"jurisdiction": ""},
        )
        bad_output = _LocatorOutput(
            found=True,
            source_url="",
            heading="X",
            text="Y",
            confidence=0.5,
        )

        with patch.object(
            provider,
            "_run_agent",
            new=AsyncMock(return_value=bad_output),
        ):
            sections = provider._fetch_impl(req)

        self.assertEqual(sections, [])

    def test_found_true_empty_text_returns_empty_list(self):
        """found=True with a source_url but blank/whitespace text is not-found."""
        provider = AgenticWebLocatorProvider()
        from opencontractserver.pipeline.base.base_authority_source_provider import (
            AuthorityRequest,
        )

        req = AuthorityRequest(
            canonical_key="act:some-obscure-law",
            url="",
            citation="act:some-obscure-law",
            extra={"jurisdiction": ""},
        )
        blank_text = _LocatorOutput(
            found=True,
            source_url="https://uscode.house.gov/download/t15.zip",
            heading="Some Heading",
            text="   \n\t  ",
            confidence=0.8,
        )

        with patch.object(
            provider,
            "_run_agent",
            new=AsyncMock(return_value=blank_text),
        ):
            sections = provider._fetch_impl(req)

        self.assertEqual(sections, [])


class ToolFetchAllowlistedTests(TestCase):
    """_tool_fetch_allowlisted survives SSRFValidationError without raising."""

    def _run(self, coro):
        return asyncio.run(coro)

    def test_ssrf_error_returns_blocked_string(self):
        from opencontractserver.utils.safe_http import SSRFValidationError

        provider = AgenticWebLocatorProvider()

        async def _direct():
            # Patch the SOURCE module, not the provider module:
            # ``_tool_fetch_allowlisted`` does a lazy in-function
            # ``from opencontractserver.utils.safe_http import safe_fetch_text``,
            # which re-reads the name from the source module at call time — so
            # patching it there is what the running function actually sees. If
            # that import is ever hoisted to module level, switch the target to
            # ``...agentic_web_locator_provider.safe_fetch_text``.
            with patch(
                "opencontractserver.utils.safe_http.safe_fetch_text",
                side_effect=SSRFValidationError("blocked"),
            ):
                return await provider._tool_fetch_allowlisted(
                    "http://evil.internal/secret"
                )

        result = self._run(_direct())

        self.assertTrue(
            result.startswith("[blocked:"),
            f"Expected '[blocked:' prefix, got: {result!r}",
        )

    def test_ssrf_error_does_not_raise(self):
        """The agent loop must not see a raised exception from blocked URLs."""
        from opencontractserver.utils.safe_http import SSRFValidationError

        provider = AgenticWebLocatorProvider()

        async def _inner():
            with patch(
                "opencontractserver.utils.safe_http.safe_fetch_text",
                side_effect=SSRFValidationError("host not on allowlist"),
            ):
                # Must not raise
                return await provider._tool_fetch_allowlisted(
                    "https://evil.example.com/law.txt"
                )

        result = asyncio.run(_inner())
        self.assertIsInstance(result, str)
        self.assertIn("blocked", result)


class ToolWebSearchTests(TestCase):
    """_tool_web_search delegates to aweb_search and propagates its result/errors."""

    def test_delegates_to_aweb_search_and_forwards_query(self):
        provider = AgenticWebLocatorProvider()

        async def _run():
            # Patch at the SOURCE module: _tool_web_search lazily imports
            # aweb_search from web_search_tools at call time, so the running
            # function reads the patched name there (same rationale as the
            # safe_fetch_text patch in ToolFetchAllowlistedTests).
            with patch(
                "opencontractserver.llms.tools.web_search_tools.aweb_search",
                new=AsyncMock(return_value="formatted results"),
            ) as mock_search:
                result = await provider._tool_web_search("15 USC 78j official source")
                return result, mock_search

        result, mock_search = asyncio.run(_run())
        self.assertEqual(result, "formatted results")
        mock_search.assert_awaited_once()
        # The query is forwarded verbatim (sanitization guards the LLM input,
        # not this search-tool output path — see _tool_web_search docstring).
        _, kwargs = mock_search.call_args
        self.assertEqual(kwargs.get("query"), "15 USC 78j official source")
        # num_results comes from the tunable ClassVar, not a hardcoded literal,
        # so dropping num_results=self.web_search_results would fail here.
        self.assertEqual(kwargs.get("num_results"), provider.web_search_results)

    def test_search_error_propagates(self):
        """A search-backend error propagates so the agent run surfaces it."""
        provider = AgenticWebLocatorProvider()

        async def _run():
            with patch(
                "opencontractserver.llms.tools.web_search_tools.aweb_search",
                new=AsyncMock(side_effect=RuntimeError("search backend down")),
            ):
                return await provider._tool_web_search("q")

        with self.assertRaises(RuntimeError):
            asyncio.run(_run())


# ---------------------------------------------------------------------------
# Integration tests — require DB (--create-db)
# ---------------------------------------------------------------------------


class AgenticLocatorPendingApprovalIntegrationTests(TransactionTestCase):
    """Gate parks agentic result at pending_approval, never ingests automatically.

    Uses a key (act:some-obscure-law) that no deterministic provider can handle,
    so the enabled AgenticWebLocatorProvider is selected.

    _run_agent is patched so no LLM call is made.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="agentic-test-user", password="testpass"
        )

    def _make_frontier(self, key: str) -> AuthorityFrontier:
        return AuthorityFrontier.objects.create(
            canonical_key=key,
            authority=key.split(":")[0],
            jurisdiction=C.JURISDICTION_US_FEDERAL,
            authority_type=C.AUTHORITY_TYPE_STATUTE,
            discovery_state="queued",
        )

    def _found_output(self) -> _LocatorOutput:
        return _LocatorOutput(
            found=True,
            source_url="https://uscode.house.gov/download/t99.zip",
            heading="Some Obscure Law Section 1",
            text="The text of this obscure law.",
            confidence=0.85,
        )

    def test_agentic_result_lands_at_pending_approval(self):
        """When the agentic provider finds a result, the frontier row must be
        pending_approval (not ingested), and candidate_sources records the outcome."""
        key = "act:some-obscure-law"
        frontier_row = self._make_frontier(key)

        found_output = self._found_output()

        # Temporarily enable the agentic provider by patching the ClassVar.
        with patch.object(AgenticWebLocatorProvider, "enabled", True):
            with patch.object(
                AgenticWebLocatorProvider,
                "_run_agent",
                new=AsyncMock(return_value=found_output),
            ):
                from opencontractserver.enrichment.services import (
                    AuthorityDiscoveryService,
                )

                result = AuthorityDiscoveryService.discover_and_bootstrap(
                    creator_id=self.user.id,
                    frontier_row=frontier_row,
                    make_public=True,
                    relink_async=False,
                )

        self.assertEqual(
            result["status"],
            "pending_approval",
            f"Agentic result must land at pending_approval, got: {result}",
        )

        frontier_row.refresh_from_db()
        self.assertEqual(
            frontier_row.discovery_state,
            "pending_approval",
            "Frontier row must be pending_approval, not ingested",
        )

        # candidate_sources must record the outcome.
        sources = frontier_row.candidate_sources or []
        self.assertTrue(len(sources) > 0, "candidate_sources must be non-empty")
        last = sources[-1]
        self.assertEqual(
            last.get("outcome"),
            "pending_approval",
            f"candidate_sources last entry outcome must be pending_approval: {last}",
        )

    def test_agentic_not_ingested(self):
        """No Document must be created from an agentic result (approval required)."""
        from opencontractserver.documents.models import Document

        key = "act:some-obscure-law"
        frontier_row = self._make_frontier(key)

        found_output = self._found_output()

        with patch.object(AgenticWebLocatorProvider, "enabled", True):
            with patch.object(
                AgenticWebLocatorProvider,
                "_run_agent",
                new=AsyncMock(return_value=found_output),
            ):
                from opencontractserver.enrichment.services import (
                    AuthorityDiscoveryService,
                )

                AuthorityDiscoveryService.discover_and_bootstrap(
                    creator_id=self.user.id,
                    frontier_row=frontier_row,
                    make_public=True,
                    relink_async=False,
                )

        # No authority document must have been created.
        self.assertFalse(
            Document.objects.filter(custom_meta__canonical_key=key).exists(),
            "Agentic result must NOT create a Document before human approval",
        )

    def test_agentic_not_found_marks_unlocated(self):
        """When the agent returns found=False, the frontier row is marked unlocated."""
        key = "act:some-obscure-law"
        frontier_row = self._make_frontier(key)

        not_found = _LocatorOutput(
            found=False,
            source_url="",
            heading="",
            text="",
            confidence=0.0,
        )

        with patch.object(AgenticWebLocatorProvider, "enabled", True):
            with patch.object(
                AgenticWebLocatorProvider,
                "_run_agent",
                new=AsyncMock(return_value=not_found),
            ):
                from opencontractserver.enrichment.services import (
                    AuthorityDiscoveryService,
                )

                result = AuthorityDiscoveryService.discover_and_bootstrap(
                    creator_id=self.user.id,
                    frontier_row=frontier_row,
                    make_public=True,
                    relink_async=False,
                )

        self.assertEqual(result["status"], "unlocated", result)

        frontier_row.refresh_from_db()
        self.assertEqual(frontier_row.discovery_state, "unlocated")


# ---------------------------------------------------------------------------
# _run_agent construction and sanitization tests
# ---------------------------------------------------------------------------


class RunAgentSanitizationTests(TestCase):
    """Verify that _run_agent sanitizes citation and jurisdiction inputs.

    The agent is not actually invoked — we patch make_pydantic_ai_agent and
    abuild_agent_model so no LLM calls or network requests are made.
    """

    def _run(self, coro):
        return asyncio.run(coro)

    def test_run_agent_sanitizes_citation_in_place(self):
        """_run_agent strips non-printable chars from citation before building instructions.

        Sanitization happens INSIDE _run_agent.  We call _run_agent directly with
        tainted inputs, patch the model factory and agent so no real LLM is invoked,
        and capture the instructions string passed to make_pydantic_ai_agent to
        verify control characters have been removed.
        """
        import unittest.mock

        provider = AgenticWebLocatorProvider()
        captured_instructions: list[str] = []

        found_output = _LocatorOutput(
            found=False,
            source_url="",
            heading="",
            text="",
            confidence=0.0,
        )
        mock_run_result = unittest.mock.MagicMock()
        mock_run_result.output = found_output
        mock_agent = unittest.mock.MagicMock()
        mock_agent.run = AsyncMock(return_value=mock_run_result)

        def capture_agent(model, instructions, **kw):
            captured_instructions.append(instructions)
            return mock_agent

        async def _inner():
            # get_default_llm_spec is patched because _run_agent now threads
            # the live PipelineSettings.default_llm tier into the resolver
            # (issue #2078) — this is a DB read, and these are plain unittest
            # TestCases with no database access.
            with patch(
                "opencontractserver.pipeline.utils.get_default_llm_spec",
                return_value="",
            ), patch(
                "opencontractserver.llms.llm_registry.resolve_model_spec",
                return_value=unittest.mock.MagicMock(),
            ), patch(
                "opencontractserver.llms.model_factory.abuild_agent_model",
                new=AsyncMock(return_value=unittest.mock.MagicMock()),
            ), patch(
                "opencontractserver.llms.agents.pydantic_ai_factory.make_pydantic_ai_agent",
                side_effect=capture_agent,
            ):
                return await provider._run_agent(
                    citation="15 USC\x00\x01 78j",
                    jurisdiction="us-federal\x02",
                )

        self._run(_inner())

        self.assertTrue(
            captured_instructions, "make_pydantic_ai_agent must have been called"
        )
        instructions = captured_instructions[0]
        self.assertNotIn("\x00", instructions, "NUL must be stripped from instructions")
        self.assertNotIn("\x01", instructions, "SOH must be stripped from instructions")
        self.assertNotIn("\x02", instructions, "STX in jurisdiction must be stripped")

    def test_run_agent_construction_does_not_raise(self):
        """_run_agent can be constructed without raising even with unusual inputs.

        We patch resolve_model_spec (so the test does not depend on a deployment
        model being configured), abuild_agent_model (to avoid real LLM config),
        and the agent's run() call (to avoid a real inference call).  The test
        verifies that the sanitization, tool wiring, and agent construction code
        path completes without error.
        """
        import unittest.mock

        provider = AgenticWebLocatorProvider()

        found_output = _LocatorOutput(
            found=False,
            source_url="",
            heading="",
            text="",
            confidence=0.0,
        )

        # Minimal fake agent whose .run() returns a result with .output set.
        mock_run_result = unittest.mock.MagicMock()
        mock_run_result.output = found_output

        mock_agent = unittest.mock.MagicMock()
        mock_agent.run = AsyncMock(return_value=mock_run_result)

        async def _inner():
            # get_default_llm_spec is patched because _run_agent now threads
            # the live PipelineSettings.default_llm tier into the resolver
            # (issue #2078) — this is a DB read, and these are plain unittest
            # TestCases with no database access.
            with patch(
                "opencontractserver.pipeline.utils.get_default_llm_spec",
                return_value="",
            ), patch(
                "opencontractserver.llms.llm_registry.resolve_model_spec",
                return_value=unittest.mock.MagicMock(),
            ), patch(
                "opencontractserver.llms.model_factory.abuild_agent_model",
                new=AsyncMock(return_value=unittest.mock.MagicMock()),
            ), patch(
                "opencontractserver.llms.agents.pydantic_ai_factory.make_pydantic_ai_agent",
                return_value=mock_agent,
            ):
                return await provider._run_agent(
                    citation="15 U.S.C. § 78j",
                    jurisdiction="us-federal",
                )

        result = self._run(_inner())
        self.assertIsInstance(result, _LocatorOutput)
