- Hardened the authority SSRF-safe fetch path in response to PR #2000 review:
  - `opencontractserver/constants/safe_http.py`: lowered the default
    `MAX_RESPONSE_BYTES` cap from 500 MB to **50 MB** so a single fetch can no
    longer OOM a constrained worker; added a dedicated
    `OLRC_TITLE_ZIP_MAX_BYTES` (200 MB) that only the US Code title-ZIP loader
    (`us_code_provider._load_title_xml`) passes as an explicit `max_bytes=`
    override.
  - `federal_register_provider._fetch_impl`: routed step 2 (document JSON) through
    `safe_fetch_bytes` instead of redirect-following `requests.get`, closing an
    SSRF gap where the FR API response could redirect step 2 to a private/internal
    host. Every redirect hop is now re-validated against the allowlist +
    public-IP check; an off-allowlist hop raises and is not swallowed.
  - `agentic_web_locator_provider`: documented that prompt-injection
    sanitization is intentionally ASCII-only (every bidi/zero-width/homoglyph
    vector lies above U+007E and is already stripped) and extracted the logic
    into `_sanitize_for_prompt`; `_fetch_impl` now also rejects a `found=True`
    result whose body text is blank/whitespace.
