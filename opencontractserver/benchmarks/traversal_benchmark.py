"""A/B measurement harness: heavy-RAG vs RAG + agentic traversal.

This mirrors the discipline of the Qodo post *"We built a state-of-the-art RAG
system… then took most of it out"* — **measure your own best work honestly**
before deciding what to trim. It runs the SAME corpus questions under two agent
tool configurations and reports tokens, tool-call counts, latency and
authority-grounding hit rate side by side:

    A — heavy RAG        : ``similarity_search`` only (today's default entry point)
    B — RAG + traversal  : ``similarity_search`` + the graph-navigation tools
                           (``get_document_references`` / ``read_reference_target``
                           / ``find_documents_citing`` / ``get_reference_neighborhood``)

It is deliberately NOT part of the 30-minute test suite — it makes real LLM
calls and needs a populated corpus (ideally one with an applied reference
enrichment + a bootstrapped authority corpus so traversal has edges to walk).
Drive it with ``manage.py benchmark_traversal``.

The point is the instrument, not a verdict: it produces the numbers that would
let us later decide, with data, whether heavy eager indexing still earns its
keep for a given corpus — we do not trim anything here.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# The graph-navigation tools whose marginal value this harness measures.
TRAVERSAL_TOOL_NAMES: tuple[str, ...] = (
    "get_document_references",
    "read_reference_target",
    "find_documents_citing",
    "get_reference_neighborhood",
)
# The semantic entry point — present in BOTH configs so the comparison isolates
# the *traversal* delta, not "search vs no search".
RAG_ENTRY_TOOL = "similarity_search"

CONFIG_HEAVY_RAG = "A_heavy_rag"
CONFIG_RAG_TRAVERSAL = "B_rag_traversal"

CONFIG_TOOL_SETS: dict[str, set[str]] = {
    CONFIG_HEAVY_RAG: {RAG_ENTRY_TOOL},
    CONFIG_RAG_TRAVERSAL: {RAG_ENTRY_TOOL, *TRAVERSAL_TOOL_NAMES},
}


@dataclass
class TraversalQuestion:
    """One benchmark item: a question over a corpus, with optional gold keys."""

    corpus_id: int
    question: str
    label: str = ""
    # Canonical keys (e.g. "dgcl:145") the answer SHOULD ground in. Optional —
    # when empty the item still reports tokens/tool-calls, just no hit rate.
    expected_keys: list[str] = field(default_factory=list)


@dataclass
class RunResult:
    """The metrics captured for one (question, config) run."""

    config: str
    label: str
    tokens: int | None = None
    tool_call_count: int = 0
    tool_names: list[str] = field(default_factory=list)
    latency_s: float = 0.0
    source_count: int = 0
    grounded_keys: list[str] = field(default_factory=list)
    expected_key_count: int = 0
    grounding_hit_rate: float | None = None
    answer_chars: int = 0
    error: str = ""


def load_questions(path: str | Path) -> list[TraversalQuestion]:
    """Load the question set from a YAML (or JSON) file."""
    text = Path(path).read_text(encoding="utf-8")
    try:
        import yaml

        raw = yaml.safe_load(text)
    except ModuleNotFoundError:  # pragma: no cover - yaml ships with the project
        raw = json.loads(text)
    items = raw["questions"] if isinstance(raw, dict) else raw
    return [
        TraversalQuestion(
            corpus_id=int(item["corpus_id"]),
            question=str(item["question"]),
            label=str(item.get("label", "")),
            expected_keys=[str(k) for k in item.get("expected_keys", [])],
        )
        for item in items
    ]


def _usage_tokens(usage: Any) -> int | None:
    """Best-effort total-token count from the pydantic-ai usage dict."""
    if not isinstance(usage, dict):
        return None
    for key in ("total_tokens", "total"):
        if usage.get(key):
            return int(usage[key])
    req = usage.get("request_tokens") or usage.get("input_tokens") or 0
    resp = usage.get("response_tokens") or usage.get("output_tokens") or 0
    total = int(req) + int(resp)
    return total or None


def _key_grounded(key: str, answer: str, sources_blob: str) -> bool:
    """Did the answer / its sources ground in a gold canonical key?

    Matches the full key (``dgcl:145``), and — because an answer often phrases a
    statute in prose ("Section 145") rather than by canonical key — the section
    number *when it is adjacent to a citation token* (``§`` / section / sec /
    rule / art). Requiring the token avoids counting a bare "145" that is really
    a page number or an unrelated section, which would bias this benchmark
    toward false "traversal wins". Still a coarse signal, not a precision
    metric — but deliberately no longer a loose substring match.
    """
    key_l = key.lower()
    haystack = f"{answer}\n{sources_blob}".lower()
    if key_l in haystack:
        return True
    section = key_l.split(":", 1)[-1]
    if len(section) < 2:
        return False
    # Section number must follow a citation token and not run into more digits
    # (so "section 145" grounds but "section 1450" / "page 145" do not).
    pattern = rf"(§|section|sec\.?|rule|art\.?)\s*{re.escape(section)}(?!\d)"
    return re.search(pattern, haystack) is not None


async def run_one(
    question: TraversalQuestion,
    config: str,
    *,
    user_id: int,
    model: str | None,
) -> RunResult:
    """Run a single question under one tool configuration and capture metrics."""
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.llms import agents

    result = RunResult(config=config, label=question.label or question.question[:60])
    result.expected_key_count = len(question.expected_keys)

    try:
        corpus = await Corpus.objects.aget(pk=question.corpus_id)
    except Corpus.DoesNotExist:
        result.error = f"corpus {question.corpus_id} not found"
        return result

    agent = await agents.for_corpus(
        corpus,
        user_id=user_id,
        model=model,
        streaming=False,
        # Isolate the comparison to exactly the tools under test.
        restrict_tool_names=CONFIG_TOOL_SETS[config],
    )

    t0 = time.perf_counter()
    try:
        response = await agent.chat(question.question)
    except Exception as exc:  # noqa: BLE001 - report, don't crash the sweep
        result.error = f"{type(exc).__name__}: {exc}"
        result.latency_s = round(time.perf_counter() - t0, 3)
        return result
    result.latency_s = round(time.perf_counter() - t0, 3)

    answer = response.content or ""
    result.answer_chars = len(answer)
    result.source_count = len(response.sources or [])

    metadata = response.metadata or {}
    result.tokens = _usage_tokens(metadata.get("usage"))
    timeline = metadata.get("timeline") or []
    calls = [
        e for e in timeline if isinstance(e, dict) and e.get("type") == "tool_call"
    ]
    result.tool_call_count = len(calls)
    result.tool_names = [str(e.get("tool")) for e in calls if e.get("tool")]

    if question.expected_keys:
        sources_blob = json.dumps(
            [s.to_dict() for s in (response.sources or [])], default=str
        )
        grounded = [
            k for k in question.expected_keys if _key_grounded(k, answer, sources_blob)
        ]
        result.grounded_keys = grounded
        result.grounding_hit_rate = round(
            len(grounded) / len(question.expected_keys), 3
        )

    return result


async def run_benchmark_traversal(
    questions: list[TraversalQuestion],
    *,
    user_id: int,
    model: str | None,
) -> list[RunResult]:
    """Run every question under both configs (serially — real LLM calls)."""
    results: list[RunResult] = []
    for question in questions:
        for config in (CONFIG_HEAVY_RAG, CONFIG_RAG_TRAVERSAL):
            results.append(
                await run_one(question, config, user_id=user_id, model=model)
            )
    return results


def _mean(values: list[float]) -> float | None:
    vals = [v for v in values if v is not None]
    return round(sum(vals) / len(vals), 3) if vals else None


def summarize(results: list[RunResult]) -> dict[str, dict[str, Any]]:
    """Aggregate per-config means across the sweep."""
    summary: dict[str, dict[str, Any]] = {}
    for config in (CONFIG_HEAVY_RAG, CONFIG_RAG_TRAVERSAL):
        block = [r for r in results if r.config == config and not r.error]
        summary[config] = {
            "runs": len(block),
            "errors": len([r for r in results if r.config == config and r.error]),
            "mean_tokens": _mean([r.tokens for r in block if r.tokens is not None]),
            "mean_tool_calls": _mean([float(r.tool_call_count) for r in block]),
            "mean_latency_s": _mean([r.latency_s for r in block]),
            "mean_grounding_hit_rate": _mean(
                [
                    r.grounding_hit_rate
                    for r in block
                    if r.grounding_hit_rate is not None
                ]
            ),
        }
    return summary


def render_markdown(results: list[RunResult]) -> str:
    """A side-by-side A-vs-B markdown report."""
    summary = summarize(results)
    lines: list[str] = ["# Traversal benchmark: heavy-RAG vs RAG + traversal", ""]

    lines.append("## Aggregate (mean per config)")
    lines.append("")
    lines.append(
        "| Config | Runs | Errors | Tokens | Tool calls | Latency (s) | Grounding |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for config in (CONFIG_HEAVY_RAG, CONFIG_RAG_TRAVERSAL):
        s = summary[config]
        lines.append(
            f"| {config} | {s['runs']} | {s['errors']} | {s['mean_tokens']} | "
            f"{s['mean_tool_calls']} | {s['mean_latency_s']} | "
            f"{s['mean_grounding_hit_rate']} |"
        )
    lines.append("")

    lines.append("## Per question")
    lines.append("")
    lines.append(
        "| Label | Config | Tokens | Tool calls | Latency (s) | Sources | Grounding | Error |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in results:
        grounding = (
            f"{len(r.grounded_keys)}/{r.expected_key_count}"
            if r.expected_key_count
            else "—"
        )
        lines.append(
            f"| {r.label} | {r.config} | {r.tokens} | {r.tool_call_count} | "
            f"{r.latency_s} | {r.source_count} | {grounding} | {r.error or ''} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_report(results: list[RunResult], run_dir: str | Path) -> Path:
    """Write ``report.md`` + ``report.json`` to ``run_dir`` and return the dir."""
    out = Path(run_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text(render_markdown(results), encoding="utf-8")
    (out / "report.json").write_text(
        json.dumps(
            {
                "summary": summarize(results),
                "results": [asdict(r) for r in results],
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    return out
