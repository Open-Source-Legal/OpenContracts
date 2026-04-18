"""Specialist + orchestrator agents for the Bolivian Laws RAG service.

Two factory functions:

- ``build_specialist_agent(area)`` — wraps ``agents.for_corpus`` with
  area-specific persona/instructions, bound to that area's corpus.
- ``build_orchestrator_agent()`` — a top-level pydantic_ai agent whose
  tools are async functions that delegate to specialist agents. It
  decides which specialist(s) to consult and synthesises the answer.

Both are async-only (the underlying OC agent API is async-only).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from asgiref.sync import sync_to_async
from django.conf import settings

from opencontractserver.bolivian_laws.constants import (
    AREA_PROFILES,
    ORCHESTRATOR_PERSONA,
    LegalArea,
    get_profile,
)
from opencontractserver.bolivian_laws.models import LegalAreaCorpus
from opencontractserver.llms import agents as oc_agents
from opencontractserver.llms.agents.core_agents import (
    CoreAgent,
    SourceNode,
    UnifiedChatResponse,
)

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorSource:
    """A source node tagged with the specialist area it came from."""

    area: str
    document_id: Optional[int]
    snippet: str
    similarity_score: float = 1.0


@dataclass
class OrchestratorResponse:
    """Aggregated response from the orchestrator across one or more
    specialists.
    """

    answer: str
    consulted_areas: list[str]
    sources: list[OrchestratorSource]
    conversation_id: Optional[int] = None


def _format_sources(area: str, sources: list[SourceNode]) -> list[OrchestratorSource]:
    out: list[OrchestratorSource] = []
    for s in sources:
        doc_id = None
        meta = s.metadata or {}
        if isinstance(meta, dict):
            doc_id = meta.get("document_id") or meta.get("doc_id")
        out.append(
            OrchestratorSource(
                area=area,
                document_id=doc_id,
                snippet=(s.content or "")[:600],
                similarity_score=getattr(s, "similarity_score", 1.0) or 1.0,
            )
        )
    return out


@sync_to_async
def _resolve_area_corpus_id(area: str) -> Optional[int]:
    """Look up the corpus_id for a given area, or None if not yet ingested."""
    binding = (
        LegalAreaCorpus.objects.filter(area=area)
        .values_list("corpus_id", flat=True)
        .first()
    )
    return binding


async def build_specialist_agent(
    area: str,
    *,
    user_id: Optional[int] = None,
    conversation_id: Optional[int] = None,
    model: Optional[str] = None,
    streaming: bool = False,
) -> CoreAgent:
    """Create a corpus agent specialised for the given legal area.

    Raises ``LookupError`` if the area's corpus has not been created
    (i.e. nothing has been ingested for that area yet).
    """
    if area not in AREA_PROFILES:
        raise ValueError(f"Unknown legal area: {area!r}")

    corpus_id = await _resolve_area_corpus_id(area)
    if corpus_id is None:
        raise LookupError(
            f"No corpus exists for area={area!r}. Ingest documents first."
        )

    profile = get_profile(area)
    chosen_model = (
        model or getattr(settings, "BOLIVIAN_LAWS_SPECIALIST_MODEL", None) or None
    )

    return await oc_agents.for_corpus(
        corpus=corpus_id,
        user_id=user_id,
        conversation_id=conversation_id,
        system_prompt=f"{profile.agent_persona}\n\n{profile.agent_instructions}",
        model=chosen_model,
        streaming=streaming,
    )


async def consult_specialist(
    area: str,
    question: str,
    *,
    user_id: Optional[int] = None,
) -> tuple[str, list[OrchestratorSource]]:
    """Run a single question against one specialist; return its answer +
    formatted sources tagged with the area.
    """
    try:
        agent = await build_specialist_agent(area, user_id=user_id)
    except LookupError as exc:
        return (
            f"[{area}] Sin corpus disponible: {exc}",
            [],
        )

    response: UnifiedChatResponse = await agent.chat(question)
    return response.content, _format_sources(area, response.sources)


async def ask_specialists(
    areas: list[str],
    question: str,
    *,
    user_id: Optional[int] = None,
) -> OrchestratorResponse:
    """Skip orchestration: call N specialists in parallel and concatenate
    their answers verbatim. Cheaper than the orchestrator when the
    caller already knows which areas are relevant.
    """
    results = await asyncio.gather(
        *(consult_specialist(a, question, user_id=user_id) for a in areas),
        return_exceptions=True,
    )

    parts: list[str] = []
    sources: list[OrchestratorSource] = []
    consulted: list[str] = []

    for area, result in zip(areas, results):
        if isinstance(result, Exception):
            parts.append(f"### {area}\n_Error: {result}_")
            consulted.append(area)
            continue
        answer, srcs = result
        parts.append(f"### {get_profile(area).title}\n{answer}")
        sources.extend(srcs)
        consulted.append(area)

    return OrchestratorResponse(
        answer="\n\n".join(parts),
        consulted_areas=consulted,
        sources=sources,
    )


async def ask_orchestrator(
    question: str,
    *,
    user_id: Optional[int] = None,
    conversation_id: Optional[int] = None,
    model: Optional[str] = None,
) -> OrchestratorResponse:
    """Route the question through the orchestrator.

    Builds a pydantic_ai Agent whose tools are async wrappers around the
    specialist consultations. The orchestrator chooses which to invoke
    and synthesises the final answer.
    """
    from pydantic_ai import Agent
    from pydantic_ai.tools import Tool

    chosen_model = (
        model
        or getattr(settings, "BOLIVIAN_LAWS_ORCHESTRATOR_MODEL", None)
        or "gpt-4o-mini"
    )

    # Mutable bag captured by the closures so we can collect every source
    # the orchestrator ends up surfacing through tool calls.
    captured_sources: list[OrchestratorSource] = []
    captured_areas: list[str] = []

    def _make_tool(area: str):
        async def _tool(question_for_specialist: str) -> str:
            answer, srcs = await consult_specialist(
                area, question_for_specialist, user_id=user_id
            )
            captured_sources.extend(srcs)
            if area not in captured_areas:
                captured_areas.append(area)
            return answer

        _tool.__name__ = f"consultar_{area}"
        _tool.__doc__ = (
            f"Consulta al especialista en derecho {get_profile(area).title}. "
            "Pásale la pregunta tal como la formularías a un abogado experto."
        )
        return _tool

    tools = [Tool(_make_tool(area.value)) for area in LegalArea]

    agent = Agent(
        chosen_model,
        instructions=ORCHESTRATOR_PERSONA,
        output_type=str,  # type: ignore[arg-type]
        tools=tools,
    )

    result = await agent.run(question)

    return OrchestratorResponse(
        answer=result.output or "",
        consulted_areas=captured_areas,
        sources=captured_sources,
        conversation_id=conversation_id,
    )
