"""Constants for the deep-research agent loop.

The system-prompt template and the read-only retrieval tool list live
here so they can be referenced by both ``research_tasks.py`` (loop
runner) and the kickoff tool / tests.
"""

from __future__ import annotations

from opencontractserver.constants.annotations import OC_SECTION_LABEL
from opencontractserver.utils.prompt_sanitization import (
    UNTRUSTED_CONTENT_NOTICE,
    fence_user_content,
    warn_if_content_large,
)

# Retrieval tools the deep-research agent is allowed to call. Strict subset
# of the existing FUNCTION_MAP entries — write-side tools (add_note_*,
# update_corpus_description, add_*_annotation, ...) are deliberately
# excluded so the agent cannot mutate corpus state.
#
# ``similarity_search`` is always attached by the corpus-agent factory
# (it's the embedded vector-store tool) and is not toggleable through
# ``restrict_tool_names``; the list below is intersected with the agent's
# default tool set so any tool that isn't a recognised registry name is
# silently dropped.
# ``search_exact_text_as_sources`` is deliberately NOT here (issue #2201): it
# returns ad-hoc matches with SYNTHETIC NEGATIVE annotation ids, which
# ``record_finding`` rejects and ``finalize`` drops. Steering the agent at it
# for "pinpoint anchors" (the #2180 prompt rule) therefore sent it hunting for
# an id it could never obtain — a 3M-token run that never finalized. The
# ``find_citable_passages`` closure (research_tasks) replaces it: same
# exact-phrase lookup, but over real Annotation rows, so every hit carries a
# ready-to-paste cite handle.
DEEP_RESEARCH_READ_ONLY_TOOLS: list[str] = [
    "similarity_search",
    "load_document_md_summary",
    "get_md_summary_token_length",
    "load_document_text",
    "get_document_text_length",
    "get_remaining_context_budget",
    "get_summary_content",
    "get_notes_for_document_corpus",
    "get_note_content_token_length",
    "get_partial_note_content",
    "get_corpus_description",
    "list_documents",
    # ``ask_document`` is intentionally excluded: its sub-agent surfaces
    # annotation IDs in ``DocAnswer.sources`` but does NOT append them to
    # ``PydanticAIDependencies.retrieved_annotation_ids`` (the citation
    # whitelist that ``record_finding`` validates against). Re-adding it
    # without first wiring the sub-agent's source IDs back into the
    # accumulator would silently break the closed-citation-graph
    # invariant for any annotation seen only via ``ask_document``.
]


# Hard ceilings to keep user-supplied inputs from blowing past a sensible
# budget. ``settings.DEEP_RESEARCH_*`` knobs still parametrise defaults;
# these constants only cap the user-facing surface.

# Max characters accepted for the research prompt. Roughly aligns with
# 2.5k tokens at the conservative 1 token / 4 chars heuristic, well below
# any model's prompt-window. Anything beyond this is almost certainly an
# accidental dump (a whole document pasted into the modal).
MAX_RESEARCH_PROMPT_CHARS = 10_000

# Absolute ceiling on per-job tool-call budget. A misbehaving agent at
# the default step budget already costs real money; we refuse to let
# a single user-supplied ``max_steps`` push past this no matter what.
MAX_RESEARCH_STEPS_CEILING = 500

# Default ``max_steps`` used when no ``DEEP_RESEARCH_DEFAULT_MAX_STEPS``
# setting is configured. Surfaced as a constant so the ``ResearchReport``
# model field default and the service-layer fallback agree (per
# CLAUDE.md rule 4 — no magic numbers).
DEFAULT_MAX_STEPS_FALLBACK = 60


# ---------------------------------------------------------------------------
# Durable context-management caps (plan + memory)
# ---------------------------------------------------------------------------
# The deep-research agent offloads state it cannot keep in-context to two
# durable sidecars on the report: a single high-level ``plan`` string and a
# key->entry ``memory`` store. Both are re-surfaced every run so the agent
# recovers cleanly after context compaction or a worker crash. The caps below
# keep a misbehaving agent from writing an unbounded blob into Postgres while
# still leaving room to store far more than fits in the context window.

# Max characters retained for the living plan. Generous enough for a
# structured multi-section plan; anything beyond is truncated (tail dropped)
# with a marker so the head — usually the task restatement + next steps —
# always survives.
MAX_RESEARCH_PLAN_CHARS = 8_000

# Memory store caps. Per-key, per-value, total-store and key-count ceilings
# are all enforced in the service layer so the tool surface cannot grow the
# JSON column without bound.
MAX_RESEARCH_MEMORY_KEYS = 64
MAX_RESEARCH_MEMORY_KEY_CHARS = 128
MAX_RESEARCH_MEMORY_VALUE_CHARS = 20_000
MAX_RESEARCH_MEMORY_TOTAL_CHARS = 200_000

# How many matching lines ``search_memory`` returns before truncating, and
# how much of each memory entry to preview in the recovery digest / index.
RESEARCH_MEMORY_SEARCH_MAX_HITS = 30
RESEARCH_MEMORY_PREVIEW_CHARS = 160

# How many recent findings to fold into the recovery digest that primes the
# system prompt on a resume. Older findings stay in the DB (and are reachable
# via ``search_memory`` once mirrored), but only the tail is replayed inline
# so the preamble itself stays small.
RESEARCH_RECOVERY_FINDINGS_DIGEST = 20


# Annotation labels that mark a section header / heading rather than an
# operative passage. The deep-research citation lint (issue #2180) flags a
# footnote whose anchor carries one of these labels, matched case- and
# separator-insensitively against ``Annotation.annotation_label.text``.
#
# Keyed on the LABEL, never on ``Annotation.structural``: the parsing pipeline
# sets ``structural=True`` on ALL of its layout output — body paragraphs,
# tables, list items, sentence chunks, … (see ``oc_text_parser`` /
# ``llamaparse_parser``), not just headers — while the bookmark-derived
# OC_SECTION headers that repro'd #2180 are explicitly ``structural=False``
# (``pdf_outline_enricher``). The structural flag would thus both flood false
# positives (every body-paragraph citation) and miss the real headers. The
# label is the precise signal. ``Title`` / ``Section Header`` / ``Heading`` /
# ``Page Header`` are the LlamaParse layout heading labels
# (``LlamaParseParser.ELEMENT_TYPE_MAPPING``); ``OC_SECTION`` is the canonical
# cross-parser section label.
RESEARCH_HEADER_ANCHOR_LABELS: frozenset[str] = frozenset(
    {
        OC_SECTION_LABEL,  # "OC_SECTION" — canonical section layer (issue #2180)
        "Title",
        "Section Header",
        "Heading",
        "Page Header",
    }
)


# ---------------------------------------------------------------------------
# Quotation verification (issue #2189)
# ---------------------------------------------------------------------------
# Steered to quote the passages it cites, the deep-research agent was observed
# fabricating quotation-marked strings that occur nowhere in the corpus yet are
# attached to real annotation anchors — a report that *looks* rigorously cited
# but isn't. At finalize every quoted passage inside a ``<cite>`` span is checked
# against the ``raw_text`` of that span's cited annotation(s); a quote that does
# not match is demoted to plain paraphrase (its quotation marks are stripped) and
# the report is flagged. See ``research_reports._verify_cite_spans``, which runs
# this check alongside the #2200/#2201 guards in one pass over the cite spans.
#
# Only quotes of at least this many words are verified. Shorter quoted strings
# (defined terms like "Confidential Information", scare-quotes, single words) are
# left untouched: they are rarely fabricated passages and are the main source of
# false positives. The quotes fabricated in #2189 were all long passages (8+
# words).
RESEARCH_QUOTE_MIN_WORDS = 5

# A quote counts as grounded when it is a whitespace-/case-normalized substring
# of a cited annotation's text, OR its longest contiguous run that appears
# verbatim in that text covers at least this fraction of the quote. The high bar
# tolerates a trailing-punctuation / whitespace / single-character drift while
# still stripping a quote whose wording diverges (an invented tail, a reworded
# clause). Built on ``difflib.SequenceMatcher`` like the annotation-anchor fuzzy
# match in ``opencontractserver/utils/annotation_anchoring.py`` — but that path
# aggregates with ``.ratio()`` (overall similarity), whereas this uses
# longest-contiguous-block coverage (``find_longest_match().size / len(quote)``),
# a stricter test that a real run of the quote appears verbatim.
RESEARCH_QUOTE_MATCH_THRESHOLD = 0.92

# Upper bound on the length of a single quoted passage the verifier will inspect.
# The extraction regex is linear (a negated character class, no backtracking), so
# this is not a ReDoS guard — it bounds a pathological match when a lone opening
# quote has no nearby close, and keeps the fuzzy comparison cheap. Set generously
# so realistic block quotes are still verified; a quote longer than this is left
# untouched (a >2000-char fabricated verbatim quote is implausible).
RESEARCH_QUOTE_MAX_CHARS = 2000


# ---------------------------------------------------------------------------
# Report composition + claim-support verification (issues #2200, #2201)
# ---------------------------------------------------------------------------
# ``finalize`` composes ONE document (executive summary + body) and runs the
# citation post-processors over it exactly once. Three deterministic guards run
# in that pass; the constants they key on live here.

# 1. Duplicate-summary suppression (#2200). The agent was observed passing the
#    WHOLE report as ``executive_summary`` as well as ``markdown_body``, so the
#    report rendered twice. The summary is dropped when it merely restates the
#    body: a normalized-substring hit, or a contiguous run of the summary's
#    first ``…PROBE_CHARS`` characters covering ``…THRESHOLD`` of that probe
#    inside the body. Probing the head (rather than diffing two multi-KB
#    strings) keeps this linear-ish — a genuine copy always matches from its
#    first sentence.
RESEARCH_SUMMARY_DUPLICATE_THRESHOLD = 0.8
RESEARCH_SUMMARY_DUPLICATE_PROBE_CHARS = 400

# 2. Echoed-cite collapse (#2200). The successor of #2183's sentence-doubling:
#    the agent writes the claim as prose and then repeats it verbatim inside the
#    `<cite>` tag, so every bullet reads twice. When a span's inner text merely
#    echoes the prose immediately before it, the span collapses to the
#    self-closing marker form (`<cite ids="…"/>`), which renders as a bare
#    footnote on the existing sentence. The threshold is the contiguous-run
#    coverage of the span text within the preceding prose.
RESEARCH_CITE_ECHO_THRESHOLD = 0.9

# How far back a self-closing `<cite ids="…"/>` marker looks for the sentence it
# decorates (also the echo-comparison window). Generous for a long legal
# sentence, bounded so the lookback stays O(1) per marker rather than O(document).
RESEARCH_SENTENCE_LOOKBACK_CHARS = 1200

# 3. Claim-support check (#2201). Generalizes the #2189 quote verifier from "is
#    this quote verbatim" to "does the cited passage say this at all". A cited
#    sentence must share at least ``…MIN_COVERAGE`` of its content words with
#    the text of the annotation(s) it cites; below that the citation is stripped
#    (the prose survives as uncited analysis) and the report is flagged.
#
#    This is a deliberately cheap, deterministic lexical floor — no LLM call, no
#    embedding round-trip at finalize. It decisively kills the two anchoring
#    failures from #2201: a one-word mention span cited for a full sentence, and
#    prompt-derived background decorated with a loosely-related entity anchor —
#    both score near zero. What it does NOT catch, so the prompt rules still
#    matter: a well-anchored sentence carrying an invented tail (#2201's
#    over-attributed paraphrase — "don't extend a cited sentence" is the guard
#    there), and a fabricated figure, since one differing number moves the ratio
#    by only 1/N (see ...MIN_TOKEN_CHARS for why numeric parity is not enforced).
#    Meaning inversion IS caught, by the polarity guard below. Swapping
#    ``_claim_is_supported`` for an entailment call is the drop-in upgrade that
#    would close the remaining two.
#
#    Only claims of at least ``…MIN_WORDS`` words are checked: short spans
#    (fragments, defined terms, a cited clause name) have too few content words
#    for a coverage ratio to mean anything and are the main false-positive
#    source. The floor is set low because stripping a CORRECT citation is worse
#    than keeping a weak one — a genuine paraphrase of its anchor clears 0.25
#    comfortably, while the failure modes above land under 0.15.
RESEARCH_CLAIM_SUPPORT_MIN_WORDS = 12
RESEARCH_CLAIM_SUPPORT_MIN_COVERAGE = 0.25

#    Polarity guard. Bag-of-words coverage is blind to negation: "the tenant is
#    NOT liable for repairs" and "the tenant is liable for repairs" differ by one
#    token and score the same against the same anchor — an inversion of the
#    source's meaning, presented with a footnote. In legal text this is the
#    highest-stakes misattribution there is (liable/not liable, permitted/
#    prohibited, terminable/non-terminable). Note that merely dropping "not"
#    from the stopword list does NOT close it: the ratio moves from ~1.0 to
#    ~0.86, still far above the floor. Parity is what catches it.
#
#    So: when a claim otherwise reads as a near-verbatim restatement of its
#    anchor (coverage at or above ...INVERSION_COVERAGE) but the two disagree on
#    whether a negation marker is present, treat it as unsupported. The high
#    coverage gate is what keeps this from firing on honest paraphrase — legal
#    text often negates lexically ("prohibited", "except", "unless") rather than
#    with a marker, but such a paraphrase shares far fewer words with the anchor
#    and never reaches the gate. Checked on the normalized text, not on
#    ``_content_words``, so the stopword list cannot hide a marker.
RESEARCH_CLAIM_INVERSION_COVERAGE = 0.8
RESEARCH_SUPPORT_NEGATION_TOKENS: frozenset[str] = frozenset(
    {"not", "no", "never", "cannot", "neither", "nor", "without", "non"}
)

# Content-word extraction for the support check: tokens shorter than this are
# dropped along with the stopword list, so the ratio is computed over the terms
# that actually carry meaning (parties, amounts, defined terms, verbs).
# Digit-bearing tokens are EXEMPT from the floor — "10", "5%" and "$5" are two
# characters but are exactly the figures a report must not fabricate, and the
# floor was silently dropping them from both sides of the ratio so a swapped
# amount produced no signal at all. Note the exemption only restores signal; it
# does not by itself catch a fabricated figure (one differing number moves the
# ratio by 1/N). Numeric *parity*, the analogue of the polarity guard, is
# deliberately NOT applied: legal text writes the same amount as "30", "thirty
# (30)", "$5" and "$5,000,000", so parity would strip correct citations far more
# often than it caught invented ones.
RESEARCH_SUPPORT_MIN_TOKEN_CHARS = 3
RESEARCH_SUPPORT_STOPWORDS: frozenset[str] = frozenset("""
    the and for that this with from are was were will would can could may might
    shall should must have has had been being not but our its their there these
    those they them then than when where which who whom what while into onto
    over under about above below after before during such any all each other
    some more most both same own very just also only own per via upon within
    without because however therefore thus does did doing done here out off
    """.split())


# Plan + memory tool names. Unioned into the deep-research agent's
# ``restrict_tool_names`` set alongside the scratchpad tools. The closures
# themselves are appended as caller-supplied tools (never filtered), so this
# union is documentary/defensive — it keeps the "allowed surface" set honest.
DEEP_RESEARCH_MEMORY_TOOL_NAMES: set[str] = {
    "update_research_plan",
    "get_research_plan",
    "write_memory",
    "read_memory",
    "list_memory",
    "search_memory",
    "delete_memory",
}


# Retrieval closures the deep-research loop binds itself (rather than pulling
# from the shared tool registry) because they need the run's citation
# accumulator. Same documentary/defensive role as the memory set above.
DEEP_RESEARCH_RETRIEVAL_CLOSURE_TOOLS: set[str] = {"find_citable_passages"}

# Max rows ``find_citable_passages`` returns per call, and how much of each
# anchor's text to show. Bounded so a common phrase cannot dump a corpus-worth
# of annotations back into the context window.
RESEARCH_CITABLE_PASSAGE_MAX_HITS = 10
RESEARCH_CITABLE_PASSAGE_PREVIEW_CHARS = 600


def build_deep_research_system_prompt(
    *,
    task_description: str,
    corpus_title: str,
    corpus_description: str | None,
    max_steps: int,
    plan: str | None = None,
    findings_digest: str | None = None,
    memory_index: str | None = None,
    resuming: bool = False,
) -> str:
    """Compose the system prompt for the deep-research agent.

    Untrusted strings (corpus metadata and the user's task) are fenced
    with ``<user_content>`` tags so the model can distinguish them from
    instructions. See ``opencontractserver.utils.prompt_sanitization``.

    ``plan``, ``findings_digest`` and ``memory_index`` are the durable
    recovery surface: they are folded into the prompt every run so the
    agent's high-level plan and prior progress are *always* present in the
    context window — surviving both in-run compaction (the system prompt is
    never compacted) and a worker restart. When ``resuming`` is True a short
    preamble tells the agent it is continuing an interrupted run rather than
    starting fresh.
    """
    warn_if_content_large(task_description, context="research task")
    warn_if_content_large(corpus_title, context="corpus title")
    if corpus_description:
        warn_if_content_large(corpus_description, context="corpus description")

    # NOTE: every multi-fragment string below uses explicit ``+`` concatenation
    # rather than Python's implicit adjacent-literal concatenation. They render
    # identically, but the explicit operator keeps CodeQL's
    # ``py/implicit-string-concatenation-in-list`` rule (a "did you forget a
    # comma?" heuristic) quiet inside these list displays. Parentheses do NOT
    # help — they leave the AST unchanged — so ``+`` is the canonical fix.
    parts: list[str] = [
        "You are a deep-research analyst executing an autonomous, multi-step "
        + "investigation across a document corpus.",
        f"\n{UNTRUSTED_CONTENT_NOTICE}",
    ]

    if resuming:
        parts.extend(
            [
                "",
                "## You are RESUMING an interrupted run",
                "A previous worker began this task and was interrupted (crash, "
                + "restart, or time limit). Your plan, prior findings, and memory "
                + "store below were preserved. Do NOT start over: read your plan "
                + "and memory first, reconcile what is already done, and continue "
                + "from where you left off. Re-issue a search only when you "
                + "genuinely need a fresh annotation ID to cite.",
            ]
        )

    parts.extend(
        [
            "",
            "## Mission",
            "1. Use the retrieval tools below to explore the corpus thoroughly.",
            "2. Each time you uncover a discrete, source-backed claim, call "
            + "`record_finding` with the claim text, the citing section, and the "
            + "annotation IDs returned by your retrieval tools.",
            "3. When you have enough evidence to answer the task, call "
            + "`finalize_report`. `executive_summary` is 2–4 sentences of "
            + "top-line answer; `markdown_body` is the full report. They are "
            + "DIFFERENT texts — never pass the report as both, and never write "
            + "your own `## Executive Summary` or `## Sources` headings: the "
            + "system adds them and renders the footnote table.",
            "4. `finalize_report` is the terminal action. Once you call it, the "
            + "run ends.",
            "",
            "## Managing your context window",
            "Your context window is finite and older tool results may be "
            + "compacted away mid-run. Three durable stores survive compaction "
            + "AND a worker restart — use them so you never lose progress:",
            "- `update_research_plan(plan)` — keep a living high-level plan: the "
            + "task restated in your own words, the sub-questions, what is done, "
            + "and the next steps. Call this early and update it whenever your "
            + "strategy changes. It is re-injected at the top of every run, so it "
            + "is the one thing guaranteed to always be in context. Read it back "
            + "any time with `get_research_plan()`.",
            "- `write_memory(key, content, mode)` — offload anything you want to "
            + "remember but cannot keep in context: extracted quotes, per-document "
            + "notes, running tallies. `mode='append'` adds to an existing key; "
            + "`mode='replace'` overwrites. Retrieve with `read_memory(key)`, "
            + "enumerate with `list_memory()`, and grep across everything with "
            + "`search_memory(query)`. Prefer many small, well-named keys (e.g. "
            + "`doc-1421-summary`) over one giant blob.",
            "- `record_finding(...)` — your citation-backed scratchpad (above). "
            + "`search_memory` greps findings alongside memory entries, but "
            + "findings are NOT memory keys: add them with `record_finding`, not "
            + "`write_memory`, and you cannot `read_memory` a finding's section.",
            "Offload eagerly. If you read a long document, write the salient "
            + "points to memory immediately rather than trusting them to stay in "
            + "the conversation history.",
            "",
            "## Critical rules",
            "- You MUST cite only annotation IDs that retrieval tools returned in "
            + "this run. Fabricated or guessed IDs will be rejected and you will "
            + "be asked to re-search.",
            "- Do NOT write hyperlinks or URLs of any kind — no markdown links "
            + "(`[text](http://…)`), no bare URLs. You have NO web access, so any "
            + "link you emit is invented (do not reach for placeholders like "
            + "`example.com`). The ONLY way to attribute a source is the "
            + '`<cite ids="…">` tag, which the system renders into footnotes. Any '
            + "URL you write would be stripped before the report is saved.",
            "- Do NOT mutate corpus state — you have no write tools, by design.",
            "- Do NOT speculate beyond what the corpus supports. If the corpus "
            + "does not contain the answer, say so explicitly in the report.",
            "",
            "## Citation discipline",
            "Citations are this product's core promise: a reader who clicks a "
            + "footnote must land on the exact words that prove the sentence. "
            + "Apply these rules to every `<cite>` tag and every `record_finding` "
            + "call:",
            "- Citing is cheap — cite what you retrieved. Every retrieval result "
            + "carries an `annotation_id`; that number IS the cite handle. Write "
            + 'the sentence, then attach `<cite ids="123,456"/>` (self-closing, '
            + "no inner text) right after it. Use the wrapping form "
            + '`<cite ids="123">…</cite>` ONLY to scope part of a sentence, and '
            + "never put a copy of the sentence inside the tag — a tag that "
            + "echoes its own sentence is collapsed to a bare marker at "
            + "finalize.",
            "- Anchor the passage whose OWN words support the claim — never a "
            + "bare section header. An annotation whose text is only a heading "
            + "(e.g. `ITEM 1A. RISK FACTORS`) marks the top of a section, not the "
            + "evidence, and neither does a bare entity mention. When you know "
            + "the language you want but not its annotation, call "
            + "`find_citable_passages(phrase)` — it returns the real annotations "
            + "containing that phrase, tightest first, each with its cite handle. "
            + "Do not go hunting with repeated broad searches for something to "
            + "cite.",
            "- Cite the document that actually CONTAINS the language. If you "
            + "reached a passage through a cross-reference or an "
            + "incorporated-by-reference pointer (common in SEC filings — a 10-Q "
            + "Item 1A that only says 'see Item 1A of our Form 10-K'), follow the "
            + "reference to the source document and anchor the operative text "
            + "there, not the referring cross-reference.",
            "- Cite only claims grounded in retrieved passages. A sentence that "
            + "merely restates the task, the prompt, or the background you were "
            + "handed carries NO citation — leave it uncited rather than forcing "
            + "on a corpus anchor that cannot support it. Uncited background is "
            + "honest; a miscited anchor is not.",
            "- One anchor must carry the WHOLE sentence it is attached to. Do "
            + "not extend a cited sentence with detail the passage does not "
            + "contain — split it into a cited sentence and a separate, uncited "
            + "analysis sentence. And do not reuse a convenient nearby anchor "
            + "for a second, different claim it cannot support. At finalize "
            + "every cited sentence is checked against the words of its cited "
            + "annotation(s); a sentence its anchor does not support LOSES its "
            + "footnote and the report is flagged.",
            "- Quote only what you can copy verbatim. Put a passage in quotation "
            + "marks ONLY when it is copied exactly, word for word, from the "
            + "retrieved passage cited on that same sentence. If you are "
            + "paraphrasing or summarising, do NOT use quotation marks. At "
            + "finalize every quoted passage is checked against the text of its "
            + "cited annotation; a quote that does not match is stripped of its "
            + "quotation marks (demoted to paraphrase) and the report is flagged. "
            + "When you need the exact words, call `find_citable_passages` to "
            + "pull the passage and cite the annotation it returns — never "
            + "reconstruct a quote from memory.",
            "- State each claim once. Write the sentence, then attach the "
            + "citation — do NOT write the claim as plain prose and then repeat "
            + "it as a cited restatement. Keep normal spacing and punctuation "
            + "around the tags so the sentence reads cleanly.",
            "",
            "## Budget",
            f"- You have approximately {max_steps} tool calls. Plan accordingly.",
            "- Prefer broad coverage early (vector + exact-text searches across "
            + "several queries), then drill into the most promising documents.",
            "",
            "## Context",
            f"- Corpus: {fence_user_content(corpus_title or 'untitled', label='corpus title')}",
        ]
    )

    if corpus_description:
        parts.append(
            "- Corpus description: "
            + f"{fence_user_content(corpus_description, label='corpus description')}"
        )

    parts.extend(
        [
            "",
            "## Research Task",
            fence_user_content(task_description, label="research task"),
        ]
    )

    # Durable recovery surface. Plan / findings / memory are agent-authored,
    # not user-supplied, so they are NOT fenced as untrusted content — fencing
    # them would teach the model to ignore its own notes.
    #
    # Accepted residual risk (indirect prompt injection): the agent populates
    # memory by reading corpus documents, so a malicious document could embed
    # text that mimics instructions, get written to memory, and be re-injected
    # here on a later run. Fencing the agent's own notes would defeat their
    # purpose, so we accept this trade-off. It is bounded: the research agent is
    # strictly read-only over corpus state (see ``DEEP_RESEARCH_READ_ONLY_TOOLS``
    # — no write tool reaches this surface), so an attacker would already need
    # write access to a corpus document to plant the payload.
    if plan and plan.strip():
        parts.extend(["", "## Your current plan", plan.strip()])

    if findings_digest and findings_digest.strip():
        parts.extend(["", "## Findings recorded so far", findings_digest.strip()])

    if memory_index and memory_index.strip():
        parts.extend(
            [
                "",
                "## Your memory store (keys — read with read_memory)",
                memory_index.strip(),
            ]
        )

    closing = (
        "Reconcile your plan and memory with the task, then continue from "
        + "where the interrupted run left off. When you have a coherent answer, "
        + "call `finalize_report`."
        if resuming
        else (
            "Begin by drafting a short plan with `update_research_plan`, then "
            + "issue 2–4 broad searches to map the corpus. Drill into the most "
            + "promising documents, offload notes to memory, and record findings "
            + "as you go. When you have a coherent answer, call `finalize_report`."
        )
    )
    parts.extend(["", closing])

    return "\n".join(parts)
