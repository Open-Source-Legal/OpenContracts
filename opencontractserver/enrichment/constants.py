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
# Punctuation stripped from the tail of a captured defined term
# (e.g. (the "Notes," ...) -> "Notes").
TRAILING_PUNCT = ",.;:"
ALL_REFERENCE_TYPES = (REF_LAW, REF_DOCUMENT, REF_SECTION, REF_DEFINED_TERM)
# Defined-terms are opt-in (precision risk); not scanned/applied by default.
DEFAULT_REFERENCE_TYPES = (REF_LAW, REF_DOCUMENT, REF_SECTION)
