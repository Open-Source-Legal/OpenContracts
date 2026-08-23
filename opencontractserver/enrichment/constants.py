"""Constants for the corpus reference enrichment engine.

No magic numbers / strings in the engine modules — they import from here.
"""

import re as _re
from pathlib import Path as _Path

from opencontractserver.enrichment.data import mappings as _mappings

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
# Derived from the ``prefixes:`` section of authority_mappings.yaml (the single
# editable source); the literal dict that used to live here is gone. Built once
# at import — a malformed prefix entry fails fast here rather than silently
# mis-resolving downstream.
AUTHORITY_PREFIX = _mappings.authority_prefix_map()

# Canonical-key prefix for bare SEC rule citations ("Rule 506(b)") — these are
# 17 CFR rules cited without a named authority.
SEC_RULE_PREFIX = "sec-rule"

# Canonical-key prefix for HTS tariff-code citations ("subheading 3924.90.5650,
# HTSUS") — references into the Harmonized Tariff Schedule of the United States.
# Like SEC_RULE_PREFIX, the prefix is also declared in authority_mappings.yaml
# (display name / classification / aliases) so it seeds AuthorityNamespace and
# classifies via PREFIX_CLASSIFICATION.
HTSUS_PREFIX = "htsus"

# Canonical-key prefix for US case-reporter citations ("569 F.3d 326"). Like
# HTSUS_PREFIX this is a SHAPE-level prefix, not a body of law: the grammar
# recognises the citation form without knowing which court, jurisdiction or
# case-law corpus (if any) is installed.
#
# Deliberately NOT the prefix a case-law pack binds to its own corpus. Packs key
# opinions however they like — by party name, docket, or slug — and map the
# reporter form to their own key with one ``equivalences`` row, exactly as they
# already do for every other surface form. Emitting a pack's key from core would
# bake one pack's naming convention into the grammar.
CASE_REPORTER_PREFIX = "usreporter"

# Canonical-key prefix for Export Control Classification Numbers ("ECCN
# 3A611"). A SHAPE-level prefix for the same reason as the two above: the
# literal "ECCN" anchors the form, so the grammar recognises it without knowing
# whether a Commerce Control List corpus is installed or what prefix it binds.
#
# Deliberately NOT ``ccl``. That is the prefix one pack happens to give its CCL
# corpus, and emitting it from core would hardcode that pack's naming into the
# framework — the failure the CASE_REPORTER_PREFIX note above describes. A pack
# carrying the CCL maps ``eccn:3a611`` to its own key with one ``equivalences``
# row.
#
# Keys are lowercased by the shared candidate builder. That is required, not
# incidental: ECCNs are conventionally written uppercase and authority-key
# matching is case-sensitive on the section part, so an uppercase key would be
# unreachable from any real citation.
ECCN_PREFIX = "eccn"

# --- Title-identifier document citations (customs-ruling grammar) ---------- #
# CBP CROSS-style corpora are "title-as-identifier" shaped: each document's
# title IS an external identifier (a ruling number like ``H022844`` or
# ``A83482``, possibly still carrying its materialized filename extension,
# ``A83482.doc``), and documents cite each other by that identifier in their
# own text. The grammar tier detects those citations (REF_DOCUMENT) and the
# resolver links them to sibling documents by title.
#
# The identifier shape (shared by the citation grammar and the resolver's
# title index): 1 letter + 5-6 digits (modern N######/H######; legacy A#####,
# K#####, …) or 2 letters + 6 digits (two-letter legacy). Bare 6-digit legacy
# ruling numbers are deliberately NOT matched — dollar amounts, statute
# numbers, and "STATE + 5-digit ZIP" ("NY 10022") are common false positives
# for that shape. UPPERCASE-only by design, for both sides: titles are
# uppercased before the fullmatch (document_identifier_from_title), and for
# text mining a lowercase/mixed-case token ("a83482") is far more likely
# prose or a serial number than a ruling citation — CROSS text prints ruling
# numbers uppercase. Used with ``finditer`` over text and ``fullmatch`` over
# canonicalized titles.
DOC_IDENTIFIER_RE = _re.compile(r"\b([A-Z]\d{5,6}|[A-Z]{2}\d{6})\b")
# The identifier grammar only activates on corpora that actually speak this
# vocabulary: at least MIN_DOCS identifier-shaped titles AND at least FRACTION
# of the corpus's non-empty titles identifier-shaped. An ordinary corpus (zero
# or incidental identifier titles) never emits these candidates, so serial /
# order / patent numbers in unrelated corpora are not mined as citations.
DOC_IDENTIFIER_TITLE_GATE_MIN_DOCS = 2
DOC_IDENTIFIER_TITLE_GATE_FRACTION = 0.5
# ``Candidate.normalized_data`` / ``CorpusReference.normalized_data`` key
# carrying the cited identifier — shared by the grammar (writer side) and the
# resolver (lookup side) so the contract has a single edit point.
KEY_DOCUMENT_IDENTIFIER = "document_identifier"


def document_identifier_from_title(title: str | None) -> str:
    """Canonicalize a document title to the identifier it names.

    Titles are set at ingest time from the materialized filename — some ingest
    paths use the bare stem (``A83482``), others keep the original filename
    including its extension (``A83482.doc``). The citation grammar only ever
    extracts the bare form (DOC_IDENTIFIER_RE has no ``.doc``/``.pdf`` in its
    character class), so a title carrying an extension would never match the
    resolver's title index and every citation into that document would
    silently read as unresolved. ``Path(...).stem`` strips at most one
    trailing extension and is a no-op on titles that are already
    extension-free. Single-strip is an accepted tradeoff: a multi-suffix
    title ("A83482.v2.doc" -> "A83482.V2") won't fullmatch the identifier
    shape and simply stays out of the gate/index — CBP materialized
    filenames carry exactly one extension, and a non-matching title
    degrades to "not identifier-titled", never to a wrong link.

    A title containing a path separator is NOT a bare materialized filename
    (titles are user-editable), so it is returned whole rather than fed to
    ``Path.stem`` — which would otherwise silently discard the leading
    segments and make "Reports/N301234" LOOK identifier-titled.
    """
    name = (title or "").strip()
    if "/" in name:
        return name.upper()
    return _Path(name).stem.upper()


# Series-token legacy document citations. Legacy CBP rulings (the bulk of
# pre-2000 HQ/NY output) have BARE numeric ruling numbers and are cited as
# "<series token> <6 digits>": "HQ 084665", "HRL 087392", "NY 812345". A bare
# number alone is never mined (dollar amounts, statute numbers, entry
# numbers), but a number immediately preceded by a CBP ruling-series token is
# a citation with near-zero ambiguity — measured on a 500-document
# official-export slice: 707 instances, no false positives. Exactly SIX
# digits on purpose: 5 digits after "NY" is almost always a New York ZIP code
# ("New York, NY 10176" — 148/149 sampled), and ZIP+4 ("10001-3060") never
# forms a 6-digit run. ``\s+`` spans hard line wraps and column whitespace
# inside the token/number pair.
LEGACY_DOC_IDENTIFIER_CITE_RE = _re.compile(
    r"\b(?:HQ|HRL|NY(?:RL)?|PD|DD|IA)\s+(\d{6})\b"
)

# Identity-side shape for legacy documents: the official CROSS bulk exporter's
# path basename IS the bare (zero-padded) ruling number, e.g. ``HQ/084665.txt``.
BARE_DOC_IDENTIFIER_RE = _re.compile(r"\d{5,6}")

# Namespace for a durable document identity carried on
# ``DocumentPath.external_id`` (e.g. ``cross:H022844``), populated by the ZIP
# import's optional ``external_id`` meta.csv column. Outranks path/title
# derivation because it survives document renames.
DOC_IDENTIFIER_EXTERNAL_ID_NAMESPACE = "cross:"


def canonical_document_identifier(value: str | None) -> str | None:
    """Canonical lookup key for a document identifier, or ``None`` if not one.

    Two disjoint namespaces share the resolver index: prefixed identifiers
    (``H022844``) are keyed verbatim (uppercased), bare legacy numbers are
    keyed with leading zeros stripped so the zero-padded document identity
    (``084665``) and however a citation pads it agree on one key. The two
    shapes cannot collide (one starts with a letter, the other is all
    digits).
    """
    v = (value or "").strip().upper()
    if DOC_IDENTIFIER_RE.fullmatch(v):
        return v
    if BARE_DOC_IDENTIFIER_RE.fullmatch(v):
        return v.lstrip("0") or "0"
    return None


def document_identifier_from_path(path: str) -> str:
    """Canonicalize a corpus path to the identifier in its basename stem.

    The official CROSS bulk exporter writes ``{COLLECTION}/{number}.txt``
    (e.g. ``HQ/084665.txt`` or ``HQ/H022844.txt``), so the active
    ``DocumentPath`` basename is the exporter's own canonical identity for
    the document — unlike the title, which the official export fills with
    the human-readable SUBJECT (non-unique, control-character-laden display
    metadata).
    """
    return _Path(path).stem.upper()


# ``AuthorityNamespace.baseline_origin`` stamp for rows written from the shipped
# core ``authority_mappings.yaml`` (loader default path + post_migrate seed).
# Pack loads stamp the pack's manifest ``name`` instead, so two baseline writers
# on the same prefix are distinguishable and the loader can refuse to clobber a
# prefix another origin owns (see ``AuthorityMappingLoader.load_namespaces``).
BASELINE_ORIGIN_CORE = "core"

# Column width of ``AuthorityNamespace.baseline_origin`` (migration 0101). A
# pack's manifest ``name`` becomes the stamp verbatim, so ``load_authority_pack``
# fail-fasts a longer name up-front rather than surfacing a DB DataError
# mid-load.
BASELINE_ORIGIN_MAX_LENGTH = 64

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
MAX_DEFINED_TERMS = 50  # cap on UNIQUE defined terms emitted per document (v1)
# Separate, larger raw-scan ceiling: bounds total regex hits inspected so a
# document that is mostly DUPLICATE definition sites cannot iterate unboundedly
# hunting for the Nth unique term. Duplicates do NOT consume the unique-term
# quota above, so this budget is deliberately larger than MAX_DEFINED_TERMS.
DEFINED_TERM_SCAN_MULTIPLIER = 10  # named so the "why 10?" is a one-line edit
MAX_DEFINED_TERM_SCAN = DEFINED_TERM_SCAN_MULTIPLIER * MAX_DEFINED_TERMS
# Per-authority cap on the keys surfaced by the wanted-authorities queue.
WANTED_AUTHORITIES_TOP_KEYS = 10

# --- Agentic graph-navigation tool bounds -------------------------------------
# The read-only navigation tools (llms/tools/core_tools/graph_navigation.py) let
# an agent *walk* the already-materialised reference graph one hop at a time.
# These caps keep any single tool call's payload bounded — an LLM must not pull
# an unbounded reference list or a whole statute corpus into one turn.
NAV_DEFAULT_MAX_REFERENCES = 25  # references returned per direction by default
NAV_MAX_REFERENCES = 100  # hard ceiling on references per direction
NAV_DEFAULT_MAX_CITING = 25  # citing documents returned by default
NAV_MAX_CITING = 100  # hard ceiling on citing documents
NAV_MAX_SAMPLE_CITATIONS = 3  # sample citing clauses kept per citing document
NAV_SNIPPET_MAX_CHARS = 300  # citing-clause snippet length
NAV_TARGET_TEXT_MAX_CHARS = 8_000  # bounded authority/target text per read hop
NAV_NEIGHBORHOOD_DEFAULT_NODE_CAP = 40  # governance-graph slice size default
NAV_NEIGHBORHOOD_MAX_NODE_CAP = 150  # governance-graph slice hard ceiling
NAV_NEIGHBORHOOD_MAX_DEPTH = 3  # max hops from a focus document
# When a focus document is given, get_reference_neighborhood builds the FULL
# corpus graph (GovernanceGraphService.build only *truncates its output* by
# global degree — building the whole thing costs the same DB work — so a
# low-degree focus is not dropped before the neighbourhood BFS runs). This
# bounds that intermediate build; the returned neighbourhood is then capped to
# the caller's node_cap. A corpus whose reference graph exceeds this is beyond
# first-pass scope (the focus would only be lost if it were also below the
# top-N by global degree).
NAV_NEIGHBORHOOD_FULL_BUILD_CAP = 5_000
# find_documents_citing computes ranking + mention counts in the DB (bounded to
# `limit`); only the small citing-clause previews read individual rows. This
# bounds that preview read so a widely-cited authority can't trigger a large
# in-memory scan.
NAV_CITING_SAMPLE_SCAN = 500

# --- Phase 2 (issue #2054): listing-index discovery bounds ---------------------
# Hard cap on candidates a single BaseAuthorityDiscoveryProvider.discover_candidates()
# run may return/seed, mirroring the CRAWL_DEFAULT_*/CRAWL_MAX_* pair below: a
# publisher's listing page with tens of thousands of rows must not flood the
# frontier in one operator-triggered run.
DISCOVERY_DEFAULT_MAX_CANDIDATES = 200
# Absolute ceiling — a caller-supplied max_candidates is clamped to this even if
# it asks for more, so a mistaken/hostile override cannot make one run unbounded.
DISCOVERY_MAX_MAX_CANDIDATES = 2_000

# The authority body's licence value gating ingestion/discovery to public-domain
# sources only. Single source of truth for the (currently) hardcoded default on
# BaseAuthorityDiscoveryProvider.license / ListingIndexDiscoveryProvider.license
# (CLAUDE.md item 4: no magic strings). BaseAuthoritySourceProvider.license
# still carries its own pre-existing literal — out of scope for this constant's
# introduction, but a candidate for a future consolidation.
AUTHORITY_LICENSE_PUBLIC_DOMAIN = "public-domain"

# --- Phase 5: bounded recursive authority crawl --------------------------------
CRAWL_DEFAULT_MAX_DEPTH = 2  # authority-to-authority hops past depth-0 seeds
CRAWL_DEFAULT_MIN_DEMAND = 2  # skip frontier rows with mention_count below this
CRAWL_DEFAULT_MAX_AUTHORITIES = 50  # hard cap on discover_and_bootstrap calls per run
CRAWL_DEFAULT_PER_JURISDICTION_CAP = 15  # max ingests per (jurisdiction) per run
CRAWL_DEFAULT_TOKEN_BUDGET = (
    2_000_000  # cumulative est. tokens (text len / 4) before stop
)
# Security limits for user/LLM-triggered crawl runs. These caps keep exposed
# tool parameters from turning one corpus action into an unbounded crawler.
CRAWL_MAX_MAX_DEPTH = 5
CRAWL_MAX_MIN_DEMAND = 1_000
CRAWL_MAX_MAX_AUTHORITIES = 50
CRAWL_MAX_PER_JURISDICTION_CAP = 15
# Equal to CRAWL_DEFAULT_TOKEN_BUDGET today (both 2_000_000): the cap must
# always be >= the default (the default is what a non-positive request maps
# to; see _sanitize_token_budget), but the two are independent knobs — the
# default can be lowered without lowering the hard cap, or raised up to it.
CRAWL_MAX_TOKEN_BUDGET = 2_000_000
# Lower floors for caps where 0/negative is not a meaningful "unbounded"
# sentinel but a degenerate value. ``per_jurisdiction_cap`` of 0 parks every
# dequeued row at ``deferred_cap`` (blocks the whole run); a floor of 1 keeps at
# least one authority per jurisdiction processable.
CRAWL_MIN_PER_JURISDICTION_CAP = 1
# Hard ceiling on a caller-supplied ``max_depth`` at the GraphQL dispatch
# surface (the RunCorpusEnrichment mutation's ``_validate_crawl_bounds``,
# config/graphql/enrichment_mutations.py): a request above this is REJECTED
# outright before a worker job is even queued. This is a different enforcement
# point than CRAWL_MAX_MAX_DEPTH above, which SILENTLY CLAMPS the
# service/tool/analyzer-schema layer (reached by paths that bypass the
# mutation, e.g. direct analyzer dispatch or the LLM tool). Both gate the same
# BFS-depth knob and currently agree at 5, but are deliberately independent so
# either surface's limit can move without the other.
CRAWL_MAX_ALLOWED_DEPTH = 5
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

# Stable canonical-key relationship vocabulary used by authority packs. These
# are deliberately separate from ``ALL_AUTHORITY_TYPES``: the latter classifies
# a source, while these values describe edges between sources across corpora.
AUTHORITY_RELATIONSHIP_TYPES = (
    "CITES",
    "AMENDS",
    "SUPERSEDES",
    "SUPERSEDED_BY",
    "ADOPTS",
    "PARTIALLY_ADOPTS",
    "REJECTS",
    "IMPLEMENTS",
    "INTERPRETS",
    "FILED_IN",
    "RESPONDS_TO",
    "REVISES",
    "INCORPORATES",
    "REQUIRES_FORM",
    "EXCEPTION_TO",
    "EFFECTIVE_VERSION_OF",
)

# Classification for every prefix the engine ships (drives the namespace seed
# and the CorpusReference backfill). prefix -> (jurisdiction, authority_type).
# Derived from authority_mappings.yaml ``prefixes:`` — the completeness test
# (tests/test_authority_mappings_file.py) pins every authority_type into
# ALL_AUTHORITY_TYPES and every prefix to a jurisdiction + display name.
PREFIX_CLASSIFICATION = _mappings.prefix_classification()

# Human-readable body-of-law names for the namespace seed.
PREFIX_DISPLAY_NAME = _mappings.prefix_display_name()

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
# Max document coroutines kept live at once in the concurrent apply path. The
# chunk-level LLM cap above bounds provider load, but every in-flight document
# coroutine also pins its full text + candidate list in memory, so a large
# corpus (hundreds/thousands of docs) launched all at once via asyncio.gather
# would spike memory. This caps how many documents are simultaneously resolving.
DOC_MAX_CONCURRENCY = 32
# Max AuthorityFrontier rows a single RunAuthorityDiscovery mutation may queue.
# discover_selected processes rows sequentially in one Celery task, so an
# unbounded batch could run a worker for an unbounded time; cap it (superuser
# can re-issue for the remainder).
AUTHORITY_DISCOVERY_MAX_BATCH = 500
# pydantic-ai output-validation retries for the structured call.
LLM_STRUCTURED_RETRIES = 3
# Max chars of a candidate's raw_text echoed into the review-candidate
# serialisation (a preview, not the full span — keeps payloads bounded).
REVIEW_CANDIDATE_RAW_TEXT_MAX_LEN = 120


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
    # ``is not None`` (not truthiness): an explicit ``0`` is a deliberate value,
    # not "unset". Folding 0 into the default would silently ignore an operator
    # who set it — a misconfiguration is better surfaced loudly than masked.
    return override if override is not None else LLM_MAX_CONCURRENCY


def doc_max_concurrency() -> int:
    """Effective cap on how many document coroutines resolve at once.

    Bounds peak memory in the concurrent apply path (each live document
    coroutine pins its text + candidates). ``DOC_MAX_CONCURRENCY`` is the code
    default; override via the ``ENRICHMENT_DOC_MAX_CONCURRENCY`` Django setting.
    Read lazily so importing this module never requires configured settings.
    """
    from django.conf import settings

    override = getattr(settings, "ENRICHMENT_DOC_MAX_CONCURRENCY", None)
    # ``is not None`` (not truthiness): an explicit ``0`` is a deliberate value,
    # not "unset" — see ``llm_max_concurrency`` above.
    return override if override is not None else DOC_MAX_CONCURRENCY


# --- Phase 3: prefix classifier ---------------------------------------- #
# Public (no leading underscore): these are imported cross-module by the USC /
# CFR authority source providers' ``can_handle`` overrides, so they are part of
# the package's intentional surface, not module-private helpers.
USC_PREFIX_RE = _re.compile(r"^usc-\d+$")
CFR_PREFIX_RE = _re.compile(r"^cfr-\d+$")
# Municipal grammar keys (issue #1995): the ``muni`` catch-all (bare "Municipal
# Code § N") and per-city ``muni-<city-slug>`` keys (both the table-keyed codes
# and open-vocab city captures). Matched by shape so a city added to the table
# later needs no entry here. Like the state-code prefixes, these are NOT in
# PREFIX_CLASSIFICATION — table candidates carry the full jurisdiction, and this
# rule only supplies the always-known authority_type.
_MUNI_PREFIX_RE = _re.compile(r"^muni(?:-[a-z0-9-]+)?$")

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


# --- Phase 3/5: AuthorityFrontier discovery-state machine ------------------ #
# Single source of truth for the frontier state vocabulary (CLAUDE.md item 4:
# no magic strings). The model field choices (annotations.models.AuthorityFrontier
# .DISCOVERY_STATE_CHOICES), the transition primitive (AuthorityFrontierService
# .mark), the discovery orchestrator, and the crawl driver all reference these
# names so a rename is a one-line edit. The verify+license gate
# (AuthorityGateService) reuses the overlapping subset for its GATE_* verdicts.
DISCOVERY_STATE_QUEUED = "queued"
DISCOVERY_STATE_IN_PROGRESS = "in_progress"
DISCOVERY_STATE_INGESTED = "ingested"
DISCOVERY_STATE_FAILED = "failed"
DISCOVERY_STATE_UNSUPPORTED = "unsupported"
# Phase 4: visible, non-silent gate outcomes.
DISCOVERY_STATE_BLOCKED_LICENSE = "blocked_license"
DISCOVERY_STATE_BLOCKED_DOMAIN = "blocked_domain"
DISCOVERY_STATE_UNLOCATED = "unlocated"
DISCOVERY_STATE_PENDING_APPROVAL = "pending_approval"
# Phase 5: per-jurisdiction cap reached; row parked so dequeue can skip it.
DISCOVERY_STATE_DEFERRED_CAP = "deferred_cap"

# (value, human label) pairs for the model field. The labels live with the
# vocabulary so the model, admin, and any serializer share one definition.
# NOTE: the historical ``discovered`` and ``resolved`` states were retired
# (Authority Console Phase 4): no production code path ever assigned them
# (discovery jumps in_progress -> ingested, and the resolution outcome lives on
# the relink result / Analysis, not the frontier row), so carrying them as
# choices was a dead-vocabulary trap.
DISCOVERY_STATE_CHOICES = [
    (DISCOVERY_STATE_QUEUED, "Queued"),
    (DISCOVERY_STATE_IN_PROGRESS, "In progress"),
    (DISCOVERY_STATE_INGESTED, "Document imported"),
    (DISCOVERY_STATE_FAILED, "No source found"),
    (DISCOVERY_STATE_UNSUPPORTED, "No provider can_handle"),
    (DISCOVERY_STATE_BLOCKED_LICENSE, "Provider license is not public-domain"),
    (
        DISCOVERY_STATE_BLOCKED_DOMAIN,
        "Source domain not on the public-domain allowlist",
    ),
    (
        DISCOVERY_STATE_UNLOCATED,
        "Located text did not verify against the requested key",
    ),
    (DISCOVERY_STATE_PENDING_APPROVAL, "Found, awaiting human approval before ingest"),
    (DISCOVERY_STATE_DEFERRED_CAP, "Deferred: per-jurisdiction cap reached"),
]

# States that represent a successful terminal ingest. ``mark()`` clears
# ``last_error`` when transitioning into one of these, so a healthy row never
# retains a stale error string from an earlier failed attempt. Only "ingested"
# qualifies today ("resolved" was retired — see the note above).
DISCOVERY_SUCCESS_STATES = frozenset({DISCOVERY_STATE_INGESTED})


def classify_prefix(prefix: str) -> tuple:
    """(jurisdiction, authority_type) for a canonical_key prefix.

    Handles federal families + municipal keys by shape:
    - ``usc-NN`` (statute): any US Code title number → (us-federal, statute)
    - ``cfr-NN`` (regulation): any CFR title number → (us-federal, regulation)
    - ``fedreg`` (admin-rule): Federal Register → (us-federal, admin-rule)
    - ``muni`` / ``muni-<city>`` (municipal): → (None, municipal-ordinance)

    Falls back to ``PREFIX_CLASSIFICATION`` for named registry bodies (dgcl,
    exchange-act, irc, …) and returns ``(None, None)`` for unknown prefixes.
    """
    if USC_PREFIX_RE.match(prefix):
        return (JURISDICTION_US_FEDERAL, AUTHORITY_TYPE_STATUTE)
    if CFR_PREFIX_RE.match(prefix):
        return (JURISDICTION_US_FEDERAL, AUTHORITY_TYPE_REGULATION)
    if prefix == "fedreg":
        return (JURISDICTION_US_FEDERAL, AUTHORITY_TYPE_ADMIN_RULE)
    if prefix in GRAMMAR_STATUTE_META_PREFIXES:
        return (JURISDICTION_US_FEDERAL, AUTHORITY_TYPE_STATUTE)
    if _MUNI_PREFIX_RE.match(prefix):
        # Jurisdiction stays None — free text reveals the city but not its state
        # (a table-keyed code supplies the full ``us-ca-san-francisco`` instead).
        # The authority_type is always recoverable, so a muni key is never
        # stranded at (None, None).
        return (None, AUTHORITY_TYPE_MUNICIPAL)
    named = PREFIX_CLASSIFICATION.get(prefix)
    if named is not None:
        return named
    # Pack-declared shape families: a pack's authority_mappings ``shape_rules``
    # let a new jurisdiction's numbered-code family (e.g. ``bo-ley-<n>``) classify
    # without a core edit — the citation vocabulary travels with the pack. The
    # shipped baseline above always wins; packs only extend. Lazy import: this
    # module is imported very early and the pack scan reaches the pipeline
    # registry, so a top-level import would cycle.
    from opencontractserver.enrichment.services.authority_pack_config import (
        pack_declared_shape_rules,
    )

    for pattern, jur, typ in pack_declared_shape_rules():
        if pattern.match(prefix):
            return (jur, typ)
    return (None, None)
