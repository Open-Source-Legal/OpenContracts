"""Opt-in agentic fallback authority source provider (Phase 4).

``AgenticWebLocatorProvider`` is a universal last-resort that uses a bounded
tool-using LLM agent to locate official public-domain authority text when no
deterministic provider can handle a canonical key.

Design constraints
------------------
- **Opt-in** (``enabled = False`` by default); a deployment must explicitly
  set the ClassVar to True (or subclass) to activate it.
- **Lowest priority** (``priority = 9999``); only reached after every
  deterministic provider declines the key.
- **Privacy**: only the normalised citation + optional jurisdiction are passed
  to the agent — the citing document text is NEVER transmitted.
- **Approval-gated**: ``requires_approval = True`` so the verify+license gate
  parks results at ``pending_approval`` rather than ingesting automatically.
  A human must approve before the authority corpus is created.
- **SSRF-safe tools**: the fetch tool routes every URL through
  ``safe_fetch_text`` — the agent cannot reach non-allowlisted or
  private hosts even if the underlying LLM is tricked by prompt injection.
"""

from __future__ import annotations

import logging
import re
from typing import ClassVar

from asgiref.sync import async_to_sync, sync_to_async
from pydantic import BaseModel, Field

from opencontractserver.enrichment.authorities import AuthoritySection
from opencontractserver.pipeline.base.base_authority_source_provider import (
    AuthorityRequest,
    BaseAuthoritySourceProvider,
)

logger = logging.getLogger(__name__)

# Maximum characters to return from a fetched page — keeps agent context bounded.
_MAX_FETCH_CHARS = 50_000

# Hard ceiling on model requests per agent run. discover_and_bootstrap runs from
# a Celery task, so a misbehaving model or a provider that never converges must
# not loop indefinitely — pydantic-ai raises UsageLimitExceeded past this bound.
_MAX_AGENT_REQUESTS = 10


class _LocatorOutput(BaseModel):
    """Structured output the agent must produce."""

    found: bool
    source_url: str
    heading: str
    text: str
    # Bounded so a stray LLM value (e.g. -0.5 or 999) can't slip through.
    confidence: float = Field(ge=0.0, le=1.0)


class AgenticWebLocatorProvider(BaseAuthoritySourceProvider):
    """Universal fallback: a bounded tool-using LLM agent locates authority text.

    Selected only when no deterministic provider ``can_handle`` the key
    (``priority = 9999``).  Opt-in (``enabled`` defaults to ``False``).

    Results carry ``requires_approval = True`` so the gate parks them at
    ``pending_approval`` before any ingest; a human must approve.
    """

    title = "Agentic Web Locator"
    description = (
        "LLM agent that locates public-domain authority text via "
        "web search and SSRF-safe fetch."
    )
    license: ClassVar[str] = "public-domain"  # gate still re-checks source_domain
    priority: ClassVar[int] = 9_999  # absolute last resort
    requires_approval: ClassVar[bool] = True
    enabled: ClassVar[bool] = False  # opt-in per deployment/settings
    supported_prefixes: ClassVar[tuple[str, ...]] = ()

    def can_handle(self, canonical_key: str) -> bool:
        """Claims every key when enabled; disabled → never selected."""
        return bool(self.enabled)

    def _locate_impl(self, canonical_key: str, **kw) -> AuthorityRequest:
        """Pure (no I/O): carry only citation + jurisdiction — never document text."""
        return AuthorityRequest(
            canonical_key=canonical_key,
            url="",  # agent decides URLs at fetch time
            citation=kw.get("citation") or canonical_key,
            extra={"jurisdiction": kw.get("jurisdiction") or ""},
        )

    def _fetch_impl(self, request: AuthorityRequest, **kw) -> list[AuthoritySection]:
        """Invoke the async agent synchronously via async_to_sync."""
        out: _LocatorOutput = async_to_sync(self._run_agent)(
            citation=request.citation or request.canonical_key,
            jurisdiction=(request.extra or {}).get("jurisdiction", ""),
        )
        if not out.found or not out.source_url:
            return []  # gate records GATE_UNLOCATED
        return [
            AuthoritySection(
                key=request.canonical_key,
                heading=out.heading,
                text=out.text,
                source_url=out.source_url,
            )
        ]

    async def _run_agent(self, *, citation: str, jurisdiction: str) -> _LocatorOutput:
        """Build and run the bounded LLM agent; return structured output.

        The agent is given two tools:
        - ``web_search``: search for official public-domain sources.
        - ``fetch_allowlisted_url``: fetch text from a gov-domain URL
          (SSRF-safe; non-allowlisted hosts are rejected and returned as an
          error string so the agent loop survives).

        ``output_type`` is passed to ``make_pydantic_ai_agent`` so pydantic-ai
        enforces the structured output schema on every model response.
        ``result.output`` is the validated ``_LocatorOutput`` instance.
        """
        from pydantic_ai.usage import UsageLimits

        from opencontractserver.llms.agents.pydantic_ai_factory import (
            make_pydantic_ai_agent,
        )
        from opencontractserver.llms.llm_registry import resolve_model_spec
        from opencontractserver.llms.model_factory import abuild_agent_model
        from opencontractserver.llms.tools.pydantic_ai_tools import (
            PydanticAIDependencies,
            PydanticAIToolFactory,
        )
        from opencontractserver.llms.tools.tool_factory import CoreTool

        # Sanitize inputs before embedding in instructions: strip non-printable
        # characters and collapse whitespace to prevent prompt injection via
        # malformed citation or jurisdiction strings.
        citation = re.sub(r"[^\x20-\x7E]", " ", citation)
        citation = re.sub(r"\s+", " ", citation).strip()
        jurisdiction = re.sub(r"[^\x20-\x7E]", " ", jurisdiction)
        jurisdiction = re.sub(r"\s+", " ", jurisdiction).strip()

        # Resolve the deployment-configured model spec (no explicit override).
        spec = resolve_model_spec(explicit=None)
        model = await abuild_agent_model(spec)

        # Wrap bound methods as pydantic-ai tools.  The wrapper adds
        # ctx: RunContext[PydanticAIDependencies] as the first parameter,
        # runs permission checks (which short-circuit when user_id is None),
        # and applies tool-output truncation.
        tools = [
            PydanticAIToolFactory.create_tool(
                CoreTool.from_function(
                    self._tool_web_search,
                    name="web_search",
                    description=(
                        "Search the public web for an official source of a "
                        "legal citation. Returns formatted results."
                    ),
                )
            ),
            PydanticAIToolFactory.create_tool(
                CoreTool.from_function(
                    self._tool_fetch_allowlisted,
                    name="fetch_allowlisted_url",
                    description=(
                        "Fetch text from a public-domain government URL "
                        "(SSRF-safe; non-allowlisted hosts are rejected and "
                        "return a blocked error string rather than raising)."
                    ),
                )
            ),
        ]

        jurisdiction_clause = f" (jurisdiction: {jurisdiction})" if jurisdiction else ""
        instructions = (
            "You are an authority-text locator. Your job is to find the OFFICIAL, "
            "public-domain full text of a single legal citation: "
            f"{citation}{jurisdiction_clause}. "
            "Steps: (1) Use web_search to find candidate official .gov sources for "
            "this citation. (2) Use fetch_allowlisted_url to retrieve the text from "
            "the most promising official URL. "
            "RULES: ONLY return text from a public-domain government source "
            "(e.g. uscode.house.gov, ecfr.gov, federalregister.gov). "
            "If you cannot confirm an official source with the actual text, set "
            "found=false. Do NOT fabricate text or invent sources."
        )

        # output_type goes to make_pydantic_ai_agent (NOT to agent.run).
        # result.output is the validated _LocatorOutput instance.
        agent = make_pydantic_ai_agent(
            model,
            instructions=instructions,
            output_type=_LocatorOutput,
            deps_type=PydanticAIDependencies,
            tools=tools,
        )

        result = await agent.run(
            f"Locate the official text of: {citation}",
            deps=PydanticAIDependencies(),
            usage_limits=UsageLimits(request_limit=_MAX_AGENT_REQUESTS),
        )
        return result.output  # type: ignore[return-value]

    # --- agent tools (must be async; PydanticAIToolWrapper enforces this) -----

    async def _tool_web_search(self, query: str) -> str:
        """Search the public web. Returns formatted result text."""
        from opencontractserver.llms.tools.web_search_tools import aweb_search

        return await aweb_search(query=query, num_results=5)

    async def _tool_fetch_allowlisted(self, url: str) -> str:
        """Fetch text from a gov-domain URL.

        Non-allowlisted or private hosts return a '[blocked: ...]' string and
        transient network errors return an '[error: ...]' string rather than
        raising, so the agent loop is never interrupted — by an SSRF safety
        failure or by a plain HTTP/connection error on a .gov host.
        """
        import httpx

        from opencontractserver.utils.safe_http import (
            SSRFValidationError,
            safe_fetch_text,
        )

        try:
            # Cap the download at the character budget (UTF-8 worst case is 4
            # bytes/char) so safe_fetch_text aborts streaming at the cap instead
            # of buffering an entire multi-hundred-MB body before truncating.
            text, _ = await sync_to_async(safe_fetch_text)(
                url, max_bytes=_MAX_FETCH_CHARS * 4
            )
            return text[:_MAX_FETCH_CHARS]
        except SSRFValidationError as exc:
            return f"[blocked: {exc}]"
        except (httpx.HTTPError, OSError) as exc:
            return f"[error: {exc}]"
