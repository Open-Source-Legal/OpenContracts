"""Registry-backed one-shot LLM text completion.

This is the sanctioned path for lightweight, non-agentic "infra" LLM calls
(e.g. conversation-title generation) that are NOT a deliberate model override.
Such calls must honour the same model-resolution chain as the agent factory —
per-call ``model`` → per-corpus ``preferred_llm`` → install-wide
``PipelineSettings.default_llm`` → Django settings — instead of hardcoding a
provider/model.

It is provider-agnostic (OpenAI, Anthropic, Google, Ollama, …) because it builds
the model through the same credential-aware model factory the chat path uses
(:func:`opencontractserver.llms.model_factory.abuild_agent_model`) and the single
sanctioned ``pydantic_ai.Agent`` construction chokepoint
(:func:`opencontractserver.llms.agents.pydantic_ai_factory.make_pydantic_ai_agent`).
"""

from __future__ import annotations

import logging
from typing import Any

from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)


async def agenerate_text(
    prompt: str,
    *,
    instructions: str | None = None,
    model: str | None = None,
    corpus_preferred: str | None = None,
    temperature: float | None = 0.7,
    max_tokens: int | None = None,
) -> str:
    """Run a single-turn LLM completion using the project LLM registry.

    Args:
        prompt: The user prompt to send.
        instructions: Optional system instruction. Passed as ``instructions=``
            (never ``system_prompt=`` — see CLAUDE.md pitfall #14).
        model: Explicit per-call model spec override (highest priority). Leave
            ``None`` to defer to the corpus / install-wide default.
        corpus_preferred: The corpus's ``preferred_llm`` (when operating in a
            corpus context), so the call defaults to the corpus model before
            falling back to ``PipelineSettings.default_llm`` / Django settings.
        temperature: Sampling temperature. Pass ``None`` to omit it entirely —
            some backends (e.g. reasoning models) reject an explicit temperature.
        max_tokens: Optional response token cap.

    Returns:
        The model's text output, stripped of surrounding whitespace.

    Note:
        A fresh ``pydantic-ai`` ``Agent`` is constructed per call. This is
        intended for infrequent one-shot calls (e.g. title generation); hot
        paths should build an agent once and reuse it.
    """
    from opencontractserver.llms.agents.pydantic_ai_factory import (
        make_pydantic_ai_agent,
    )
    from opencontractserver.llms.llm_registry import resolve_model_spec
    from opencontractserver.llms.model_factory import abuild_agent_model
    from opencontractserver.pipeline.utils import get_default_llm_spec

    # Walk the canonical priority chain. ``get_default_llm_spec`` performs ORM
    # access (reads the PipelineSettings singleton), so it is threaded in via
    # sync_to_async; ``resolve_model_spec`` itself stays ORM-free.
    spec = resolve_model_spec(
        explicit=model,
        corpus_preferred=corpus_preferred,
        settings_default=await sync_to_async(get_default_llm_spec)(),
    )
    # DB-wins / env-fallback credentialed model (or the bare spec string).
    built_model = await abuild_agent_model(spec)

    # Only inject settings the caller actually specified — mirrors max_tokens so
    # backends that reject an explicit temperature aren't forced to receive one.
    model_settings: dict[str, Any] = {}
    if temperature is not None:
        model_settings["temperature"] = temperature
    if max_tokens is not None:
        model_settings["max_tokens"] = max_tokens

    agent_kwargs: dict[str, Any] = {"model_settings": model_settings}
    if instructions:
        agent_kwargs["instructions"] = instructions

    agent = make_pydantic_ai_agent(built_model, **agent_kwargs)
    result = await agent.run(prompt)
    # No output_type is set, so pydantic-ai returns a bare string. Guard against
    # a None output (model refusal / future API shape) so a caller's
    # ``value or fallback`` guard sees "" rather than the truthy literal "None".
    output = result.output
    return str(output).strip() if output is not None else ""
