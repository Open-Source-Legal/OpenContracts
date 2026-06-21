- **AgenticWebLocatorProvider** (Phase 4): opt-in, lowest-priority (9999) universal
  fallback that uses a bounded tool-using LLM agent to locate official public-domain
  authority text when no deterministic provider can handle a canonical key.
  Located at `opencontractserver/pipeline/authority_source_providers/agentic_web_locator_provider.py`.
  Key properties: `enabled=False` (opt-in per deployment); `requires_approval=True` so
  results are parked at `pending_approval` by the Phase 3 gate and never auto-ingested;
  the agent receives only the normalised citation + jurisdiction (never document text,
  for privacy); its fetch tool routes every URL through `safe_fetch_text` (SSRF-safe,
  non-allowlisted hosts return a `[blocked: ...]` string rather than raising so the
  agent loop survives). Agent construction follows the Phase 2 (`LLMCitationExtractor`)
  pattern: `resolve_model_spec` → `abuild_agent_model` → `make_pydantic_ai_agent`
  with `output_type=_LocatorOutput`, `tools=[...]`; result accessor is `result.output`.
  Covered by 17 unit + integration tests in `opencontractserver/tests/test_agentic_web_locator.py`;
  all mock `_run_agent` so no LLM calls or network requests are made in CI.
