- **Authority discovery Phase-4 code-review follow-ups (issue #2026).**
  - `opencontractserver/utils/safe_http.py::safe_fetch_bytes` now sends a
    default `User-Agent` (`DEFAULT_USER_AGENT`) so the US Code title-ZIP loader
    and the agentic fetch tool identify OpenContracts to `.gov` servers instead
    of going out as an anonymous `httpx` client (politeness + fewer rate-limit
    blocks); a caller-supplied `User-Agent` (the FR/CFR providers) still
    overrides it. This applies to **every** no-`headers` caller of
    `safe_fetch_bytes`/`safe_fetch_text`, not only the providers — notably
    `enrichment/services/popular_name_importer.py`, which now sends
    `DEFAULT_USER_AGENT` instead of the bare `httpx` default (no test asserts on
    the old UA string, so nothing regresses). The two byte-identical `_USER_AGENT` literals in
    `cfr_provider.py` / `federal_register_provider.py` are consolidated into a
    single `AUTHORITY_PROVIDER_USER_AGENT` constant (same `constants/safe_http.py`
    neighbourhood) so the contact address can no longer drift between them, and
    `us_code_provider.py` (the third deterministic authority provider, previously
    sending the generic default) now sends the same UA so all three present
    consistently to `.gov` hosts. The default/caller merge uses `httpx.Headers`
    (case-insensitive), so a caller passing `user-agent` in any casing overrides
    the default rather than emitting two conflicting `User-Agent` lines.
    `AUTHORITY_PROVIDER_USER_AGENT` also gains a `+` before its info URL
    (`(+https://github.com/...)`, the conventional "informational URL" marker)
    to match `DEFAULT_USER_AGENT` — a cosmetic change to the UA bytes the
    FR/CFR/US Code providers send to `.gov` hosts, with no behavioural impact.
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
  - Moved the agentic provider's private `_sanitize_for_prompt` helper into
    `opencontractserver/utils/prompt_sanitization.py` as the public
    `sanitize_for_prompt_strict` (its stricter, ASCII-only companion to the
    existing `sanitize_plaintext_for_prompt`), so this security helper is
    discoverable alongside the other prompt-injection utilities rather than
    buried in a provider file. Tests moved to `test_prompt_sanitization.py`.
  - Hardened the Federal Register provider's step-1 redirect parsing: the
    document-number capture in `_LOCATION_DOC_NUMBER_RE` is now `[\d-]+` (real FR
    numbers are `YYYY-NNNNN`), so a malformed/attacker-influenced `Location`
    carrying letters, underscores, or URL-special characters (`?`, `#`) fails to
    match and raises instead of silently being interpolated into the step-2 URL
    (wrong endpoint, no error). The step-1 `requests.get` magic `timeout=15` is
    replaced with the shared `(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS)`
    constants.
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
