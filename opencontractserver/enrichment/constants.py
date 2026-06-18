"""Constants for the corpus reference enrichment engine.

No magic numbers / strings in the engine modules — they import from here.
"""

import re as _re

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

# --- Phase 5: crawl analyzer identity (dispatchable via the analyzer framework) ---
CRAWL_ANALYZER_TASK = "opencontractserver.tasks.corpus_analysis_tasks.crawl_authorities"
CRAWL_ANALYZER_ID = "bounded-authority-crawl"
CRAWL_ANALYZER_TITLE = "Bounded Authority Crawl"

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

# --- Phase 5: bounded recursive authority crawl --------------------------------
CRAWL_DEFAULT_MAX_DEPTH = 2  # authority-to-authority hops past depth-0 seeds
CRAWL_DEFAULT_MIN_DEMAND = 2  # skip frontier rows with mention_count below this
CRAWL_DEFAULT_MAX_AUTHORITIES = 50  # hard cap on discover_and_bootstrap calls per run
CRAWL_DEFAULT_PER_JURISDICTION_CAP = 15  # max ingests per (jurisdiction) per run
CRAWL_DEFAULT_TOKEN_BUDGET = (
    2_000_000  # cumulative est. tokens (text len / 4) before stop
)
CRAWL_DEFAULT_DOLLAR_BUDGET = 0.0  # 0 == unbounded; LLM-tier extraction is opt-in
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
ALL_DETECTION_TIERS = (
    DETECTION_TIER_REGISTRY,
    DETECTION_TIER_GRAMMAR,
    DETECTION_TIER_LLM,
)

# --- Phase 2: Tier-2b LLM citation detection ------------------------------- #
# Verified spans below this self-rated confidence go to the review bucket
# (surfaced, never auto-promoted to mentions).
LLM_CONFIDENCE_FLOOR = 0.7
# Offset-preserving sliding-window chunking for the LLM pass (chars). The window
# is sized large (vs the old 2000) so a document yields FAR fewer chunks: a
# modern model handles ~2K-token windows comfortably, the LLM returns
# chunk-relative offsets (and verify_and_place recovers by raw-text search when
# they drift), and a 400-char overlap is only ~5% redundant at this width.
LLM_CHUNK_WINDOW = 8000
LLM_CHUNK_OVERLAP = 400
# Max concurrent per-chunk LLM calls within a single document's extraction.
# Chunks are independent, so they run via asyncio.gather behind a Semaphore —
# bounded so we never exceed the provider's rate limits or cost-spike. This is
# the dominant speedup over the old strictly-sequential await loop.
LLM_MAX_CONCURRENCY = 8
# pydantic-ai output-validation retries for the structured call.
LLM_STRUCTURED_RETRIES = 3


def llm_max_concurrency() -> int:
    """Effective global cap on concurrent LLM extraction calls.

    ``LLM_MAX_CONCURRENCY`` is the conservative code default; a deployment can
    raise it (more provider throughput, but higher rate-limit / cost exposure)
    via the ``ENRICHMENT_LLM_MAX_CONCURRENCY`` env var / Django setting without a
    code change. Read lazily so importing this module never requires configured
    settings, and so the constant stays the single numeric source of truth.
    """
    from django.conf import settings

    override = getattr(settings, "ENRICHMENT_LLM_MAX_CONCURRENCY", None)
    return override if override else LLM_MAX_CONCURRENCY

# --- Phase 3: prefix classifier ---------------------------------------- #
_USC_PREFIX_RE = _re.compile(r"^usc-\d+$")
_CFR_PREFIX_RE = _re.compile(r"^cfr-\d+$")

# Grammar-emitted federal-statute meta-prefixes. Unlike the named registry
# bodies in PREFIX_CLASSIFICATION, these are catch-alls — ``act`` for an
# unrecognised named Act, ``publ`` for a Public Law (e.g. publ:107-56), ``stat``
# for Statutes at Large (e.g. stat:135.429). The bare-Act grammar already
# assumes us-federal for these (state-act disambiguation is a documented
# follow-up), so classifying them here keeps the frontier queue and
# governance-graph ghost nodes from being stranded at (None, None). They are
# kept OUT of PREFIX_CLASSIFICATION so the AuthorityNamespace seed (migration
# 0082) never materialises a spurious "act"/"publ"/"stat" body of law.
GRAMMAR_STATUTE_META_PREFIXES = frozenset({"act", "publ", "stat"})


def classify_prefix(prefix: str) -> tuple:
    """(jurisdiction, authority_type) for a canonical_key prefix.

    Handles three title-scoped federal families by shape:
    - ``usc-NN`` (statute): any US Code title number → (us-federal, statute)
    - ``cfr-NN`` (regulation): any CFR title number → (us-federal, regulation)
    - ``fedreg`` (admin-rule): Federal Register → (us-federal, admin-rule)

    Falls back to ``PREFIX_CLASSIFICATION`` for named registry bodies (dgcl,
    exchange-act, irc, …) and returns ``(None, None)`` for unknown prefixes.
    """
    if _USC_PREFIX_RE.match(prefix):
        return (JURISDICTION_US_FEDERAL, AUTHORITY_TYPE_STATUTE)
    if _CFR_PREFIX_RE.match(prefix):
        return (JURISDICTION_US_FEDERAL, AUTHORITY_TYPE_REGULATION)
    if prefix == "fedreg":
        return (JURISDICTION_US_FEDERAL, AUTHORITY_TYPE_ADMIN_RULE)
    if prefix in GRAMMAR_STATUTE_META_PREFIXES:
        return (JURISDICTION_US_FEDERAL, AUTHORITY_TYPE_STATUTE)
    return PREFIX_CLASSIFICATION.get(prefix, (None, None))
