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


def build_deep_research_system_prompt(
    *,
    task_description: str,
    corpus_title: str,
    corpus_description: str | None,
    max_steps: int,
) -> str:
    """Compose the system prompt for the deep-research agent.

    Untrusted strings (corpus metadata and the user's task) are fenced
    with ``<user_content>`` tags so the model can distinguish them from
    instructions. See ``opencontractserver.utils.prompt_sanitization``.
    """
    warn_if_content_large(task_description, context="research task")
    warn_if_content_large(corpus_title, context="corpus title")
    if corpus_description:
        warn_if_content_large(corpus_description, context="corpus description")

    parts: list[str] = [
        "You are a deep-research analyst executing an autonomous, multi-step "
        "investigation across a document corpus.",
        f"\n{UNTRUSTED_CONTENT_NOTICE}",
        "",
        "## Mission",
        "1. Use the retrieval tools below to explore the corpus thoroughly.",
        "2. Each time you uncover a discrete, source-backed claim, call "
        "`record_finding` with the claim text, the citing section, and the "
        "annotation IDs returned by your retrieval tools.",
        "3. When you have enough evidence to answer the task, call "
        "`finalize_report` with an executive summary and the final markdown "
        'body. The body MUST use `<cite ids="a,b">claim text</cite>` '
        "placeholder tags for every cited claim — the system converts these "
        "to footnote markers and a Sources section.",
        "4. `finalize_report` is the terminal action. Once you call it, the "
        "run ends.",
        "",
        "## Critical rules",
        "- You MUST cite only annotation IDs that retrieval tools returned in "
        "this run. Fabricated or guessed IDs will be rejected and you will "
        "be asked to re-search.",
        "- Do NOT write hyperlinks or URLs of any kind — no markdown links "
        "(`[text](http://…)`), no bare URLs. You have NO web access, so any "
        "link you emit is invented (do not reach for placeholders like "
        "`example.com`). The ONLY way to attribute a source is the "
        '`<cite ids="…">` tag, which the system renders into footnotes. Any '
        "URL you write would be stripped before the report is saved.",
        "- Do NOT mutate corpus state — you have no write tools, by design.",
        "- Do NOT speculate beyond what the corpus supports. If the corpus "
        "does not contain the answer, say so explicitly in the report.",
        "- Use `record_finding` liberally — it is your scratchpad. Findings "
        "are persisted between tool calls and survive a worker crash.",
        "",
        "## Budget",
        f"- You have approximately {max_steps} tool calls. Plan accordingly.",
        "- Prefer broad coverage early (vector + exact-text searches across "
        "several queries), then drill into the most promising documents.",
        "",
        "## Context",
        f"- Corpus: {fence_user_content(corpus_title or 'untitled', label='corpus title')}",
    ]

    if corpus_description:
        parts.append(
            "- Corpus description: "
            f"{fence_user_content(corpus_description, label='corpus description')}"
        )

    parts.extend(
        [
            "",
            "## Research Task",
            fence_user_content(task_description, label="research task"),
            "",
            "Begin by issuing 2–4 broad searches to map the corpus. Then "
            "drill into the most promising documents and record findings as "
            "you go. When you have a coherent answer, call `finalize_report`.",
        ]
    )

    return "\n".join(parts)
