"""Allowlist + resource caps for the SSRF-safe authority fetch helper."""

# Public-domain government source hosts. Authority text may ONLY be ingested
# from these. Match is exact-host or registrable-suffix (".house.gov" matches
# "uscode.house.gov"). Keep alphabetised; every addition is a trust decision.
#
# Only the bare registrable domains are listed: host_on_allowlist() matches any
# subdomain via the dotted-suffix rule, so "ecfr.gov" already covers
# "www.ecfr.gov", "federalregister.gov" covers the FR API + raw_text host, etc.
# Listing the www. variants explicitly would be redundant.
PUBLIC_DOMAIN_SOURCE_HOSTS: frozenset[str] = frozenset(
    {
        "ecfr.gov",  # eCFR Versioner API (CFR) — incl. www. subdomain
        "federalregister.gov",  # FR API v1 + raw_text bodies — incl. www.
        "govinfo.gov",  # GPO bulk data (future providers) — incl. www.
        "gpo.gov",  # eCFR raw_text bodies served from the GPO CDN — incl. www.
        "uscode.house.gov",  # OLRC US Code release-point XML
    }
)

# HTTPS only. ``http://`` is intentionally excluded even for local/test
# convenience: a downgraded hop is an SSRF/MITM foothold and every allowlisted
# .gov source serves TLS. Do NOT add "http" here to make a test pass — mock the
# transport instead (see test_safe_http.py::TestValidateUrlScheme).
ALLOWED_SCHEMES: frozenset[str] = frozenset({"https"})
MAX_REDIRECTS: int = 5
CONNECT_TIMEOUT_SECONDS: float = 5.0
READ_TIMEOUT_SECONDS: float = 60.0  # OLRC title ZIPs are large

# RFC 6598 Carrier-Grade NAT / shared address space. ``ipaddress`` does NOT
# classify this block as private/reserved/global on any current CPython
# (verified False for is_private AND is_reserved on 3.11 and 3.12) — it is simply
# absent from CPython's ``ipaddress`` ``_private_networks`` list — so the
# property-based denylist in ``_assert_public_ip`` would let a host resolving
# here slip through. Rejected explicitly and version-independently; the behaviour
# is pinned by ``test_safe_http.py::test_cgnat_shared_address_space_rejected``
# (re-run it to re-verify the gap after a Python upgrade).
CGNAT_SHARED_ADDRESS_SPACE_CIDR: str = "100.64.0.0/10"

# Identifies OpenContracts to public-domain .gov servers when a caller does not
# supply its own User-Agent (the FR/CFR providers pass a more specific one that
# overrides this). Sending a real UA — rather than the bare ``httpx`` default —
# is polite and reduces the chance of being rate-limited or outright blocked.
DEFAULT_USER_AGENT: str = (
    "OpenContracts/1.0 "
    "(+https://github.com/Open-Source-Legal/OpenContracts; "
    "contact: opensource@opencontracts.dev)"
)

# Specific UA the deterministic authority-source providers (Federal Register,
# eCFR) send, overriding DEFAULT_USER_AGENT. Single source of truth so the two
# providers cannot drift the contact address / URL apart.
AUTHORITY_PROVIDER_USER_AGENT: str = (
    "OpenContracts-authority-provider/1.0 "
    "(+https://github.com/Open-Source-Legal/OpenContracts; "
    "contact: opensource@opencontracts.dev)"
)

# Per-service credential headers stripped when ``safe_fetch_bytes`` follows a
# redirect to a DIFFERENT host (RFC 9110 §15.4). httpx — unlike browsers and
# ``requests`` — forwards request headers verbatim across a cross-origin
# redirect, so a caller-supplied Authorization/Cookie must not leak from one
# allowlisted .gov service to another. Lowercase for case-insensitive matching.
#
# NOTE: this is the standard credential set, NOT an exhaustive safe-list.
# Non-standard per-service headers (``X-Api-Key``, ``X-Auth-Token``, …) are NOT
# stripped, so a caller that sends such a header for a specific service must not
# rely on this set to protect it across a cross-host redirect.
# Size ceiling for a single operator-supplied extra CA certificate PEM loaded
# by an authority pack. A CA bundle is a handful of KiB; anything approaching
# this is a misconfiguration (or a pointer at the wrong file), and reading it
# unbounded would let a pack manifest pull an arbitrarily large file into memory
# at validation time.
MAX_EXTRA_CA_CERTIFICATE_BYTES: int = 1024 * 1024

CROSS_HOST_STRIPPED_HEADERS: frozenset[str] = frozenset(
    {"authorization", "cookie", "proxy-authorization"}
)

# Conservative DEFAULT body cap. Most authority fetches (FR JSON, eCFR/FR raw
# text bodies) are well under this; a constrained worker should never buffer
# hundreds of MB by default. Callers that genuinely need a larger body (only the
# OLRC title-ZIP loader today) pass an explicit ``max_bytes=`` override.
MAX_RESPONSE_BYTES: int = 50 * 1024 * 1024  # 50 MB default cap

# Per-call override for the OLRC US Code title-ZIP loader. The largest title
# (Title 26, Tax) ships well under 100 MB, so 200 MB is generous headroom while
# still bounding a runaway download far below the old 500 MB blanket default.
OLRC_TITLE_ZIP_MAX_BYTES: int = 200 * 1024 * 1024  # 200 MB

# UTF-8 worst-case encodes one Unicode scalar in up to 4 bytes. Callers that cap
# *characters* (e.g. the agentic locator's ``max_fetch_chars``) multiply by this
# to derive the *byte* cap passed to ``safe_fetch_*`` — so streaming aborts at
# the byte ceiling instead of buffering a huge body before truncating to chars.
UTF8_MAX_BYTES_PER_CHAR: int = 4
