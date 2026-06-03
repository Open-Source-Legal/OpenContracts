"""Constants for the deep-research agent loop.

The system-prompt template and the read-only retrieval tool list live
here so they can be referenced by both ``research_tasks.py`` (loop
runner) and the kickoff tool / tests.
"""

from __future__ import annotations

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
DEEP_RESEARCH_READ_ONLY_TOOLS: list[str] = [
    "similarity_search",
    "search_exact_text_as_sources",
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
            + "`finalize_report` with an executive summary and the final markdown "
            + 'body. The body MUST use `<cite ids="a,b">claim text</cite>` '
            + "placeholder tags for every cited claim — the system converts these "
            + "to footnote markers and a Sources section.",
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
