- **Authority discovery Phase-4 code-review follow-ups (issue #2026).**
  - `opencontractserver/utils/safe_http.py::safe_fetch_bytes` now sends a
    default `User-Agent` (`DEFAULT_USER_AGENT`) so the US Code title-ZIP loader
    and the agentic fetch tool identify OpenContracts to `.gov` servers instead
    of going out as an anonymous `httpx` client (politeness + fewer rate-limit
    blocks); a caller-supplied `User-Agent` (the FR/CFR providers) still
    overrides it.
  - Replaced the bare `* 4` UTF-8 worst-case byte factor in
    `opencontractserver/pipeline/authority_source_providers/agentic_web_locator_provider.py`
    with the named `UTF8_MAX_BYTES_PER_CHAR` constant
    (`opencontractserver/constants/safe_http.py`).
  - Removed the unused `source_url` override parameter from
    `AuthorityGateService.evaluate`
    (`opencontractserver/enrichment/services/authority_gate_service.py`): no
    caller passed it and no test exercised it, so it was speculative API surface
    over a single source of truth (the domain gate reads
    `sections[0].source_url`).
  - Documented the deliberate trust boundary on the agentic
    `_tool_web_search` query (LLM-generated, forwarded unsanitized to a
    text-only search tool — no SSRF surface), why `AuthorityGateService` does
    not extend `BaseService` (stateless, no user context), and why the redirect
    loop in `safe_fetch_bytes` does not `r.read()` the redirect body (unbounded
    read that would bypass the per-hop size cap).
- **New backend test coverage (issue #2026).**
  `test_safe_http.py` adds the CGNAT rejection + boundary cases, the
  `MAX_REDIRECTS` exhaustion path, and the default/overridden `User-Agent`
  behaviour; `test_federal_register_provider.py` adds the step-3 raw-text
  size-cap `SSRFValidationError`→abstract fallback regression; `test_authority_gate.py`
  adds the no-colon `canonical_key` heading-fallback edge case; and
  `test_agentic_web_locator.py` adds `_tool_web_search` delegation/error-propagation
  coverage.
