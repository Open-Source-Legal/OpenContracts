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


def _agent_capabilities(agent) -> list:
    """Return the agent's capability list.

    Reaches into ``Agent.root_capability.capabilities`` — a pydantic-ai
    internal accessor that isn't promised by the public API. Centralised
    here so a future rename surfaces in a single, well-marked spot
    instead of three near-identical tests. The wrapping ``AttributeError``
    fails the test with a precise pointer to this contract.

    Upstream source pointers (pydantic-ai ~1.102.x, the version pinned in
    ``requirements/base.txt``):

    - ``pydantic_ai/agent/__init__.py`` — ``_root_capability =
      CombinedCapability(capabilities)`` is constructed in ``Agent``'s
      ``__init__``-time setup; ``root_capability`` is exposed as a
      ``@property`` on ``AbstractAgent`` (``pydantic_ai/agent/abstract.py``)
      and forwarded through ``Agent`` / ``AgentWrapper``.
    - ``pydantic_ai/capabilities/combined.py`` — ``CombinedCapability``
      stores the underlying list as the ``capabilities`` attribute.

    When bumping pydantic-ai, sanity-check those two files first; the
    ``AttributeError`` tripwire below names this docstring so the
    diagnosis path is obvious.
    """
    try:
        return list(agent.root_capability.capabilities)
    except AttributeError as exc:  # pragma: no cover - tripwire path
        raise AssertionError(
            "pydantic-ai changed its internal capability accessor "
            "(``Agent.root_capability.capabilities``). See the upstream "
            "pointers in _agent_capabilities() above; update this helper "
            "to match the new shape. Original error: " + repr(exc)
        ) from exc


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


def test_factory_injects_in_run_history_processor() -> None:
    """The factory installs shrink_old_artifacts_processor as the first
    ProcessHistory capability on every constructed Agent."""
    from pydantic_ai.capabilities import ProcessHistory

    from opencontractserver.llms.history_processors import (
        shrink_old_artifacts_processor,
    )

    agent = make_pydantic_ai_agent(
        model=TestModel(),
        instructions="placeholder",
    )

    caps = _agent_capabilities(agent)
    process_history_caps = [c for c in caps if isinstance(c, ProcessHistory)]
    assert len(process_history_caps) >= 1
    assert process_history_caps[0].processor is shrink_old_artifacts_processor


def test_factory_preserves_legacy_history_processors_after_ours() -> None:
    """Caller-supplied history_processors=[...] (legacy form) are each
    wrapped in ProcessHistory and appended after ours."""
    from pydantic_ai.capabilities import ProcessHistory

    from opencontractserver.llms.history_processors import (
        shrink_old_artifacts_processor,
    )

    async def caller_proc_one(messages):
        return messages

    async def caller_proc_two(messages):
        return messages

    agent = make_pydantic_ai_agent(
        model=TestModel(),
        instructions="placeholder",
        history_processors=[caller_proc_one, caller_proc_two],
    )

    caps = _agent_capabilities(agent)
    process_history_caps = [c for c in caps if isinstance(c, ProcessHistory)]
    assert len(process_history_caps) == 3
    assert process_history_caps[0].processor is shrink_old_artifacts_processor
    assert process_history_caps[1].processor is caller_proc_one
    assert process_history_caps[2].processor is caller_proc_two


def test_factory_preserves_caller_capabilities_after_ours() -> None:
    """Caller-supplied capabilities=[...] are appended after our
    ProcessHistory entry — the new API path is also accepted."""
    from pydantic_ai.capabilities import ProcessHistory

    from opencontractserver.llms.history_processors import (
        shrink_old_artifacts_processor,
    )

    async def caller_proc(messages):
        return messages

    caller_capability = ProcessHistory(caller_proc)

    agent = make_pydantic_ai_agent(
        model=TestModel(),
        instructions="placeholder",
        capabilities=[caller_capability],
    )

    caps = _agent_capabilities(agent)
    process_history_caps = [c for c in caps if isinstance(c, ProcessHistory)]
    assert len(process_history_caps) == 2
    assert process_history_caps[0].processor is shrink_old_artifacts_processor
    assert process_history_caps[1] is caller_capability
