"""Citation abbreviation → (prefix, jurisdiction, authority_type) lookup tables.

Public, factual abbreviation data (jurisdiction + code names) — not protected
expression. Extending coverage is a data edit here, never a grammar change.
Keys are the abbreviation EXACTLY as it appears in text; the grammar matcher
escapes them and matches longest-first.
"""

from __future__ import annotations

from opencontractserver.enrichment import constants as C

# State statutory codes. prefix is the canonical_key namespace; jurisdiction is
# the hierarchical region code; type is the authority type.
STATE_CODE_ABBREVIATIONS: dict[str, tuple[str, str, str]] = {
    "Tex. Bus. Orgs. Code": ("tx-boc", "us-tx", C.AUTHORITY_TYPE_STATUTE),
    "Cal. Corp. Code": ("ca-corp", "us-ca", C.AUTHORITY_TYPE_STATUTE),
    "Cal. Lab. Code": ("ca-lab", "us-ca", C.AUTHORITY_TYPE_STATUTE),
    "N.Y. Bus. Corp. Law": ("ny-bcl", "us-ny", C.AUTHORITY_TYPE_STATUTE),
    "N.Y. Gen. Bus. Law": ("ny-gbl", "us-ny", C.AUTHORITY_TYPE_STATUTE),
    # "Del. Code Ann. tit. 8" IS the DGCL — reuse the existing prefix so the
    # Bluebook-style cite and the named cite dedup to one authority.
    "Del. Code Ann. tit. 8": ("dgcl", "us-de", C.AUTHORITY_TYPE_STATUTE),
    "Fla. Stat.": ("fl-stat", "us-fl", C.AUTHORITY_TYPE_STATUTE),
    "Mass. Gen. Laws": ("ma-gl", "us-ma", C.AUTHORITY_TYPE_STATUTE),
    "Wash. Rev. Code": ("wa-rcw", "us-wa", C.AUTHORITY_TYPE_STATUTE),
    "Ill. Comp. Stat.": ("il-ilcs", "us-il", C.AUTHORITY_TYPE_STATUTE),
}

# Municipal codes (Tier-2a, issue #1995). Forms are too heterogeneous for a
# single precise regex, so KNOWN city codes live here (exact name -> full
# taxonomy) and the open-vocabulary ``Municipal Code § N`` shape grammar in
# grammars.py catches the rest at lower confidence.
#
# The prefix is deliberately ``muni-<city-slug>`` — the SAME namespace the
# open-vocab grammar emits for a captured city. A known code therefore shares
# its canonical-key prefix with any open-vocab mention of the same city, so the
# two never fragment into rival authorities; the table merely upgrades the
# jurisdiction (full ``us-ca-san-francisco`` code, which free text can't supply
# reliably) and the confidence. Both spelled-out and Bluebook-abbreviated forms
# are listed because the abbreviation's city slug ("S.F." -> "s-f") differs from
# the canonical one ("san-francisco"), so the grammar can't canonicalise it.
MUNICIPAL_CODE_ABBREVIATIONS: dict[str, tuple[str, str, str]] = {
    # San Francisco, CA
    "San Francisco Municipal Code": (
        "muni-san-francisco",
        "us-ca-san-francisco",
        C.AUTHORITY_TYPE_MUNICIPAL,
    ),
    "San Francisco Mun. Code": (
        "muni-san-francisco",
        "us-ca-san-francisco",
        C.AUTHORITY_TYPE_MUNICIPAL,
    ),
    "S.F. Mun. Code": (
        "muni-san-francisco",
        "us-ca-san-francisco",
        C.AUTHORITY_TYPE_MUNICIPAL,
    ),
    # Los Angeles, CA
    "Los Angeles Municipal Code": (
        "muni-los-angeles",
        "us-ca-los-angeles",
        C.AUTHORITY_TYPE_MUNICIPAL,
    ),
    "L.A. Mun. Code": (
        "muni-los-angeles",
        "us-ca-los-angeles",
        C.AUTHORITY_TYPE_MUNICIPAL,
    ),
    # New York City, NY — the consolidated code IS the "Administrative Code"
    # ("Administrative Code" is intentionally kept OUT of the open-vocab grammar
    # because "Texas Administrative Code" is a STATE regulation, not municipal).
    "New York City Administrative Code": (
        "muni-new-york",
        "us-ny-new-york",
        C.AUTHORITY_TYPE_MUNICIPAL,
    ),
    "N.Y.C. Admin. Code": (
        "muni-new-york",
        "us-ny-new-york",
        C.AUTHORITY_TYPE_MUNICIPAL,
    ),
    # Chicago, IL
    "Chicago Municipal Code": (
        "muni-chicago",
        "us-il-chicago",
        C.AUTHORITY_TYPE_MUNICIPAL,
    ),
    "Municipal Code of Chicago": (
        "muni-chicago",
        "us-il-chicago",
        C.AUTHORITY_TYPE_MUNICIPAL,
    ),
    # Seattle, WA
    "Seattle Municipal Code": (
        "muni-seattle",
        "us-wa-seattle",
        C.AUTHORITY_TYPE_MUNICIPAL,
    ),
    # Houston, TX
    "Houston Code of Ordinances": (
        "muni-houston",
        "us-tx-houston",
        C.AUTHORITY_TYPE_MUNICIPAL,
    ),
}
