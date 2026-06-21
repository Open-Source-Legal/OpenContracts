"""Curated act-section <-> USC canonical-key equivalence pairs.

These pairs are hand-verified against the USLM ``<sourceCredit>`` cross-
references and the USC Popular Names table.  The USLM provider augments
these at ingest time by parsing ``<sourceCredit>`` elements; the seed
provides a reliable baseline that works before any title has been ingested.

Direction convention: ``from_key`` is the popular-name act citation that
filings use; ``to_key`` is the USC codification the OLRC provider
materialises a document under.  ``find_authority_target`` queries both
columns so the direction is for documentation only.
"""

from __future__ import annotations

# FROZEN: superseded by enrichment/data/authority_mappings.yaml as the source of
# truth for equivalences. Retained ONLY for migration 0087 (historical seed) and
# 0092 (one-time manual->baseline reclassification). Do NOT edit these dicts; add
# new pairs to the YAML.

# Securities Exchange Act of 1934 (15 U.S.C. Chapter 2B)
EXCHANGE_ACT_TO_USC: dict[str, str] = {
    "exchange-act:9": "usc-15:78i",
    "exchange-act:10": "usc-15:78j",
    "exchange-act:12": "usc-15:78l",
    "exchange-act:13": "usc-15:78m",
    "exchange-act:14": "usc-15:78n",
    "exchange-act:14a": "usc-15:78n",
    "exchange-act:16": "usc-15:78p",
    "exchange-act:17": "usc-15:78q",
    "exchange-act:20": "usc-15:78t",
    "exchange-act:21": "usc-15:78u",
}

# Securities Act of 1933 (15 U.S.C. Chapter 2A)
SECURITIES_ACT_TO_USC: dict[str, str] = {
    "securities-act:2": "usc-15:77b",
    "securities-act:3": "usc-15:77c",
    "securities-act:4": "usc-15:77d",
    "securities-act:5": "usc-15:77e",
    "securities-act:7": "usc-15:77g",
    "securities-act:10": "usc-15:77j",
    "securities-act:11": "usc-15:77k",
    "securities-act:12": "usc-15:77l",
    "securities-act:15": "usc-15:77o",
}

# Flattened list of (from_key, to_key) tuples for migration use.
CURATED_EQUIVALENCES: list[tuple[str, str]] = [
    *EXCHANGE_ACT_TO_USC.items(),
    *SECURITIES_ACT_TO_USC.items(),
]
