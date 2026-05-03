"""Regression tests for ``opencontractserver.llms.agents.pydantic_ai_factory``.

These tests defend the behaviour described in CLAUDE.md pitfall #14 and
issue #1451: pydantic-ai silently drops the ``system_prompt=`` argument
when ``message_history`` is non-empty (which is always the case in
OpenContracts' chat() flow), so all agent construction must funnel
through ``make_pydantic_ai_agent``, which:

1. Refuses ``system_prompt=`` outright (loud failure).
2. Honours ``instructions=`` such that the system instruction is
   actually delivered to the model when ``message_history`` is non-empty.

The second test is the version-pinning canary: if a future pydantic-ai
release changes precedence so that ``instructions=`` is also dropped (or
its delivery semantics change), this test fails loudly so the regression
is caught before silently shipping.
"""

from __future__ import annotations

import asyncio

import pytest
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.models.test import TestModel

from opencontractserver.llms.agents.pydantic_ai_factory import (
    make_pydantic_ai_agent,
)

# A unique sentinel string we can grep for inside the messages the agent
# delivers to the model. Anything other than this exact value indicates
# either a precedence change or a regression in the factory itself.
SENTINEL_INSTRUCTION = "OPENCONTRACTS_SENTINEL_INSTRUCTION_ISSUE_1451"


def test_factory_blocks_system_prompt_keyword() -> None:
    """Passing ``system_prompt=<str>`` must fail loudly."""
    with pytest.raises(TypeError, match="system_prompt"):
        make_pydantic_ai_agent(
            model=TestModel(),
            system_prompt="this would be silently dropped at run() time",
        )


def test_factory_blocks_system_prompt_even_when_none() -> None:
    """Even ``system_prompt=None`` must fail.

    The guard is sentinel-based (not ``is not None``) so callers cannot
    accidentally bypass it by passing an explicit ``None``.
    """
    with pytest.raises(TypeError, match="system_prompt"):
        make_pydantic_ai_agent(model=TestModel(), system_prompt=None)


def test_factory_returns_real_agent_with_instructions() -> None:
    """Happy path: ``instructions=`` is forwarded and an Agent is returned."""
    from pydantic_ai.agent import Agent as PydanticAIAgent

    agent = make_pydantic_ai_agent(
        model=TestModel(),
        instructions=SENTINEL_INSTRUCTION,
    )
    assert isinstance(agent, PydanticAIAgent)


def test_instructions_survive_non_empty_message_history() -> None:
    """Pin pydantic-ai precedence: ``instructions=`` reaches the model even
    when ``message_history`` is non-empty.

    OpenContracts' ``chat()`` flow persists the user's HUMAN message
    *before* invoking ``Agent.run()``, so ``message_history`` is never
    empty. This test reproduces that condition and asserts the system
    instruction reaches the model — pinning the behaviour against the
    currently pinned pydantic-ai version (see ``requirements/base.txt``
    and issue #1451).

    A future pydantic-ai version that changes precedence will cause this
    test to fail, surfacing the regression before it ships silently.

    The test wraps the async ``Agent.run()`` call with ``asyncio.run`` so
    it executes under pytest's default sync runner — pytest-asyncio is
    not configured in this repo (see ``pytest.ini``).
    """
    test_model = TestModel(custom_output_text="ok")
    agent = make_pydantic_ai_agent(
        model=test_model,
        instructions=SENTINEL_INSTRUCTION,
    )

    # Pre-existing history mirroring the chat() flow: a prior user turn
    # plus the assistant's response. With this present, the agent's
    # internal "first run" branch — the only branch that materialises
    # ``system_prompt=`` into the model request — is bypassed.
    preexisting_history: list[ModelMessage] = [
        ModelRequest(parts=[UserPromptPart(content="prior user message")]),
        ModelResponse(parts=[TextPart(content="prior assistant reply")]),
    ]

    result = asyncio.run(
        agent.run(
            "next user prompt",
            message_history=preexisting_history,
        )
    )

    all_msgs = result.all_messages()

    # The instruction can surface in either place depending on the
    # pydantic-ai release: as a SystemPromptPart inside a ModelRequest,
    # or on the ModelRequest's ``instructions`` attribute. Either is an
    # acceptable delivery — what we are pinning is that *one of them*
    # carries the sentinel. If both vanish, that is the regression.
    found_in_system_prompt_part = any(
        isinstance(msg, ModelRequest)
        and any(
            isinstance(part, SystemPromptPart) and SENTINEL_INSTRUCTION in part.content
            for part in msg.parts
        )
        for msg in all_msgs
    )
    found_in_request_instructions = any(
        isinstance(msg, ModelRequest)
        and SENTINEL_INSTRUCTION in (getattr(msg, "instructions", None) or "")
        for msg in all_msgs
    )

    assert found_in_system_prompt_part or found_in_request_instructions, (
        "instructions= was dropped by pydantic-ai when message_history was "
        "non-empty. This is the regression that issue #1451 was designed to "
        "prevent. Either the pinned pydantic-ai version changed its "
        "precedence rules, or the factory has been refactored incorrectly. "
        f"All messages observed: {all_msgs!r}"
    )
