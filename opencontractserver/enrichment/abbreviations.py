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
