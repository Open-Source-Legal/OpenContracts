"""Allowlist + resource caps for the SSRF-safe authority fetch helper."""

# Public-domain government source hosts. Authority text may ONLY be ingested
# from these. Match is exact-host or registrable-suffix (".house.gov" matches
# "uscode.house.gov"). Keep alphabetised; every addition is a trust decision.
PUBLIC_DOMAIN_SOURCE_HOSTS: frozenset[str] = frozenset(
    {
        "ecfr.gov",
        "federalregister.gov",
        "govinfo.gov",
        "gpo.gov",
        "uscode.house.gov",  # OLRC US Code release-point XML
        "www.ecfr.gov",  # eCFR Versioner API (CFR)
        "www.federalregister.gov",  # Federal Register API v1 + raw_text bodies
        "www.govinfo.gov",  # GPO bulk data (future providers)
        # eCFR raw_text bodies are sometimes served from this GPO CDN host:
        "www.gpo.gov",
    }
)

ALLOWED_SCHEMES: frozenset[str] = frozenset({"https"})  # gov sources are all TLS
MAX_REDIRECTS: int = 5
CONNECT_TIMEOUT_SECONDS: float = 5.0
READ_TIMEOUT_SECONDS: float = 60.0  # OLRC title ZIPs are large
MAX_RESPONSE_BYTES: int = 500 * 1024 * 1024  # 500 MB cap (OLRC title ZIP ceiling)
