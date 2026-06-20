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

ALLOWED_SCHEMES: frozenset[str] = frozenset({"https"})  # gov sources are all TLS
MAX_REDIRECTS: int = 5
CONNECT_TIMEOUT_SECONDS: float = 5.0
READ_TIMEOUT_SECONDS: float = 60.0  # OLRC title ZIPs are large

# Conservative DEFAULT body cap. Most authority fetches (FR JSON, eCFR/FR raw
# text bodies) are well under this; a constrained worker should never buffer
# hundreds of MB by default. Callers that genuinely need a larger body (only the
# OLRC title-ZIP loader today) pass an explicit ``max_bytes=`` override.
MAX_RESPONSE_BYTES: int = 50 * 1024 * 1024  # 50 MB default cap

# Per-call override for the OLRC US Code title-ZIP loader. The largest title
# (Title 26, Tax) ships well under 100 MB, so 200 MB is generous headroom while
# still bounding a runaway download far below the old 500 MB blanket default.
OLRC_TITLE_ZIP_MAX_BYTES: int = 200 * 1024 * 1024  # 200 MB
