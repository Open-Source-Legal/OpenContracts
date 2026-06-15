"""Constants for the corpus reference enrichment engine.

No magic numbers / strings in the engine modules — they import from here.
"""

# Mention annotation labels (one per reference type).
LABEL_REF_LAW = "OC_REF_LAW"
LABEL_REF_DOC = "OC_REF_DOC"
LABEL_REF_SECTION = "OC_REF_SECTION"
LABEL_REF_TERM = "OC_REF_TERM"

# Relationship label used for within-document reference links (section->section,
# definition->usage). One label keeps the relationship graph legible.
LABEL_RELATIONSHIP = "OC_REFERENCES"

# Reference type discriminators — must match CorpusReference.REFERENCE_TYPE_CHOICES.
REF_LAW = "LAW"
REF_DOCUMENT = "DOCUMENT"
REF_SECTION = "SECTION"
REF_DEFINED_TERM = "DEFINED_TERM"

# Resolution statuses — must match CorpusReference.RESOLUTION_STATUS_CHOICES.
STATUS_RESOLVED = "RESOLVED"
STATUS_UNRESOLVED = "UNRESOLVED"
STATUS_EXTERNAL = "EXTERNAL"

LABEL_FOR_TYPE = {
    REF_LAW: LABEL_REF_LAW,
    REF_DOCUMENT: LABEL_REF_DOC,
    REF_SECTION: LABEL_REF_SECTION,
    REF_DEFINED_TERM: LABEL_REF_TERM,
}

# Authority name (as it appears in text, lowercased) -> canonical_key prefix.
AUTHORITY_PREFIX = {
    "delaware general corporation law": "dgcl",
    "dgcl": "dgcl",
    "securities act": "securities-act",
    "securities exchange act": "exchange-act",
    "exchange act": "exchange-act",
    "internal revenue code": "irc",
    "investment company act": "ica",
    "investment advisers act": "iaa",
}

# Canonical-key prefix for bare SEC rule citations ("Rule 506(b)") — these are
# 17 CFR rules cited without a named authority.
SEC_RULE_PREFIX = "sec-rule"

# Document-level relationship type for graph rollups — must match
# DocumentRelationship.RELATIONSHIP_TYPE_CHOICES.
DOC_REL_RELATIONSHIP = "RELATIONSHIP"

# Provenance analyzer identity for enrichment runs. The task name is the
# REAL registered Celery task (the @corpus_analyzer_task adapter in
# opencontractserver/tasks/corpus_analysis_tasks.py) so the analyzer row the
# service creates is dispatchable via run_task_name_analyzer / CorpusAction.
ENRICHMENT_ANALYZER_TASK = (
    "opencontractserver.tasks.corpus_analysis_tasks.corpus_reference_enrichment"
)
ENRICHMENT_ANALYZER_ID = "corpus-reference-enrichment"
ENRICHMENT_ANALYZER_TITLE = "Corpus Reference Enrichment"

# Governance-graph vocabulary (node kinds / edge types / corpus roles) — the
# contract between GovernanceGraphService, the GraphQL types, and the frontend
# panel. Mirrors demo/export_governance_graph.py.
GRAPH_EDGE_LAW = "LAW"  # resolved law citation -> statute document
GRAPH_EDGE_LAW_EXTERNAL = "LAW_EXTERNAL"  # citation with no visible target doc
GRAPH_EDGE_DOCUMENT = "DOCUMENT"  # DocumentRelationship rollup (doc -> doc)
GRAPH_NODE_PRIMARY = "primary"
GRAPH_NODE_EXHIBIT = "exhibit"
GRAPH_NODE_STATUTE = "statute"
GRAPH_NODE_EXTERNAL = "external"  # ghost node for an unresolved canonical key
GRAPH_CORPUS_FILING = "filing"
GRAPH_CORPUS_AUTHORITY = "authority"

# Defaults / thresholds.
DEFAULT_SAMPLE_N = 10
MAX_DEFINED_TERMS = 50  # cap to control precision/volume in v1
# Per-authority cap on the keys surfaced by the wanted-authorities queue.
WANTED_AUTHORITIES_TOP_KEYS = 10
# Punctuation stripped from the tail of a captured defined term
# (e.g. (the "Notes," ...) -> "Notes").
TRAILING_PUNCT = ",.;:"
ALL_REFERENCE_TYPES = (REF_LAW, REF_DOCUMENT, REF_SECTION, REF_DEFINED_TERM)
# Defined-terms are opt-in (precision risk); not scanned/applied by default.
DEFAULT_REFERENCE_TYPES = (REF_LAW, REF_DOCUMENT, REF_SECTION)

# --- Phase 0: jurisdiction + authority-type taxonomy ----------------------- #
# Jurisdiction codes are hierarchical, '-' separated: "us-ca" is an ancestor of
# "us-ca-san-francisco". Stored on CorpusReference / AuthorityNamespace.
JURISDICTION_US_FEDERAL = "us-federal"

# Authority types — controlled vocabulary (CorpusReference.authority_type).
AUTHORITY_TYPE_STATUTE = "statute"
AUTHORITY_TYPE_REGULATION = "regulation"
AUTHORITY_TYPE_ADMIN_RULE = "admin-rule"
AUTHORITY_TYPE_MUNICIPAL = "municipal-ordinance"
AUTHORITY_TYPE_CASE = "case"
AUTHORITY_TYPE_CONSTITUTION = "constitution"
AUTHORITY_TYPE_COURT_RULE = "court-rule"
AUTHORITY_TYPE_GUIDANCE = "guidance"
AUTHORITY_TYPE_TREATY = "treaty"
ALL_AUTHORITY_TYPES = (
    AUTHORITY_TYPE_STATUTE,
    AUTHORITY_TYPE_REGULATION,
    AUTHORITY_TYPE_ADMIN_RULE,
    AUTHORITY_TYPE_MUNICIPAL,
    AUTHORITY_TYPE_CASE,
    AUTHORITY_TYPE_CONSTITUTION,
    AUTHORITY_TYPE_COURT_RULE,
    AUTHORITY_TYPE_GUIDANCE,
    AUTHORITY_TYPE_TREATY,
)

# Classification for every prefix the engine ships (drives the namespace seed
# and the CorpusReference backfill). prefix -> (jurisdiction, authority_type).
PREFIX_CLASSIFICATION = {
    "dgcl": ("us-de", AUTHORITY_TYPE_STATUTE),
    "securities-act": (JURISDICTION_US_FEDERAL, AUTHORITY_TYPE_STATUTE),
    "exchange-act": (JURISDICTION_US_FEDERAL, AUTHORITY_TYPE_STATUTE),
    "irc": (JURISDICTION_US_FEDERAL, AUTHORITY_TYPE_STATUTE),
    "ica": (JURISDICTION_US_FEDERAL, AUTHORITY_TYPE_STATUTE),
    "iaa": (JURISDICTION_US_FEDERAL, AUTHORITY_TYPE_STATUTE),
    SEC_RULE_PREFIX: (JURISDICTION_US_FEDERAL, AUTHORITY_TYPE_REGULATION),
}

# Human-readable body-of-law names for the namespace seed.
PREFIX_DISPLAY_NAME = {
    "dgcl": "Delaware General Corporation Law",
    "securities-act": "Securities Act of 1933",
    "exchange-act": "Securities Exchange Act of 1934",
    "irc": "Internal Revenue Code",
    "ica": "Investment Company Act of 1940",
    "iaa": "Investment Advisers Act of 1940",
    SEC_RULE_PREFIX: "SEC Rules (17 C.F.R.)",
}

# Detection provenance — which layer found a mention (CorpusReference.detection_tier).
DETECTION_TIER_REGISTRY = "registry"  # Tier 1: static/DB alias grammars (trusted)
DETECTION_TIER_GRAMMAR = "grammar"  # Tier 2a: generic citation-shape grammars
DETECTION_TIER_LLM = "llm"  # Tier 2b: LLM extraction (future phase)
